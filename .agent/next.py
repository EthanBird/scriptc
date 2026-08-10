from pathlib import Path
import re,shutil,subprocess,traceback
REPORT=Path('WORKER_METHODVAL_CONTEXT.txt')
def run(args,cwd=None,timeout=1800):
    cp=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    return cp.returncode,cp.stdout or ''
try:
    rc,_=run(['pnpm','build'])
    if rc: raise RuntimeError('scriptc build failed')
    prime=Path('/tmp/prime-methodval')
    if prime.exists(): shutil.rmtree(prime)
    rc,out=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(prime)],timeout=300)
    if rc: raise RuntimeError(out[-4000:])
    for cmd in (['npm','ci'],['npm','run','build']):
        rc,out=run(cmd,cwd=prime,timeout=1200)
        if rc: raise RuntimeError(out[-8000:])
    cli=str(Path.cwd()/'packages/cli/dist/main.js')
    rc,out=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o','/tmp/prime-methodval-bin'],cwd=prime,timeout=1200)
    m=re.search(r'([^\n:]+\.js):(\d+):(\d+) - error SC1090: bound method references \(call \'setOptions\' directly\)',out)
    if not m: raise RuntimeError('setOptions blocker not found\n'+out[-10000:])
    file=Path(m.group(1)); center=int(m.group(2)); text=file.read_text(encoding='utf-8').splitlines()
    lines=[f'build_status={rc}',f'file={file}',f'blocker_line={center}']
    # Wide class context, then every assignment/use of setOptions/options/parse/parseInline in this chunk.
    a=max(1,center-120); b=min(len(text),center+220)
    lines.append(f'\n=== wide context {a}-{b} ===')
    lines.extend(f'{i:06d}: {text[i-1]}' for i in range(a,b+1))
    for needle in ('setOptions','this.options','\.options\(','this.parse','parseInline','parseMarkdown'):
        rx=re.compile(needle)
        hits=[i+1 for i,s in enumerate(text) if rx.search(s)]
        lines.append(f'\nneedle={needle!r} hits={hits[:120]}')
        for h in hits[:30]:
            aa=max(1,h-4); bb=min(len(text),h+6)
            lines.extend(f'{i:06d}: {text[i-1]}' for i in range(aa,bb+1))
    # Locate the nearest enclosing class declaration by scanning backwards.
    for i in range(center-1,max(-1,center-1200),-1):
        if re.search(r'\bclass\s+[A-Za-z_$]|= class(?:\s|\{)',text[i]):
            h=i+1; aa=max(1,h-20); bb=min(len(text),h+350)
            lines.append(f'\n=== probable enclosing class at {h}, context {aa}-{bb} ===')
            lines.extend(f'{j:06d}: {text[j-1]}' for j in range(aa,bb+1))
            break
    REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
except Exception as e:
    REPORT.write_text('METHODVAL_CONTEXT=FAIL\n'+repr(e)+'\n'+traceback.format_exc(),encoding='utf-8')
