from pathlib import Path
import os,re,shutil,subprocess,traceback
REPORT=Path('WORKER_CLASSVAL_CONTEXT.txt')
def run(args,cwd=None,timeout=1800):
    cp=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    return cp.returncode,cp.stdout or ''
try:
    rc,_=run(['pnpm','build'])
    if rc: raise RuntimeError('scriptc build failed')
    prime=Path('/tmp/prime-classval')
    if prime.exists(): shutil.rmtree(prime)
    rc,out=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(prime)],timeout=300)
    if rc: raise RuntimeError(out[-4000:])
    for cmd in (['npm','ci'],['npm','run','build']):
        rc,out=run(cmd,cwd=prime,timeout=1200)
        if rc: raise RuntimeError(out[-8000:])
    cli=str(Path.cwd()/'packages/cli/dist/main.js')
    rc,out=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o','/tmp/prime-classval-bin'],cwd=prime,timeout=1200)
    matches=list(re.finditer(r'([^\n:]+\.js):(\d+):(\d+) - error SC1090: constructing through a class value whose class has no lowering',out))
    if not matches: raise RuntimeError('class-value blockers not found\n'+out[-10000:])
    lines=[]
    for n,m in enumerate(matches,1):
        file=Path(m.group(1)); center=int(m.group(2)); text=file.read_text(encoding='utf-8').splitlines()
        lines += [f'\n=== BLOCKER {n}: {file}:{center} ===']
        a=max(1,center-35); b=min(len(text),center+35)
        lines.extend(f'{i:06d}: {text[i-1]}' for i in range(a,b+1))
        # Parse the constructor identifiers on the blocker lines and locate their class definitions/assignments.
        src=text[center-1]
        ids=re.findall(r'new\s+([A-Za-z_$][\w$]*)',src)
        for ident in ids:
            hits=[]
            pats=(f'class {ident}',f'var {ident} = class',f'{ident} = class',f'let {ident} = class',f'const {ident} = class')
            for i,s in enumerate(text):
                if any(p in s for p in pats): hits.append(i+1)
            lines.append(f'identifier={ident} class_definition_candidates={hits}')
            for h in hits[:5]:
                aa=max(1,h-30); bb=min(len(text),h+140)
                lines.append(f'--- {ident} definition context {aa}-{bb} ---')
                lines.extend(f'{i:06d}: {text[i-1]}' for i in range(aa,bb+1))
    # Also retain all diagnostics from the same chunk to reveal the class declaration's own deferred/runtime fence.
    chunks=sorted(set(str(Path(m.group(1))) for m in matches))
    lines.append('\n=== ALL CURRENT DIAGNOSTICS IN CLASSVAL CHUNKS ===')
    for diag in out.splitlines():
        if any(c in diag for c in chunks) and 'error SC' in diag: lines.append(diag)
    REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
except Exception as e:
    REPORT.write_text('CLASSVAL_CONTEXT=FAIL\n'+repr(e)+'\n'+traceback.format_exc(),encoding='utf-8')
