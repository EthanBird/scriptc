from pathlib import Path
import os,re,shutil,subprocess,traceback
REPORT=Path('WORKER_VAR_HOIST_CONTEXT.txt')
log=[]
def run(args,cwd=None,timeout=1800):
    cp=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    return cp.returncode,cp.stdout or ''
try:
    rc,_=run(['pnpm','build'])
    if rc: raise RuntimeError('scriptc build failed')
    prime=Path('/tmp/prime-var-hoist')
    if prime.exists(): shutil.rmtree(prime)
    rc,out=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(prime)],timeout=300)
    if rc: raise RuntimeError(out[-4000:])
    for cmd in (['npm','ci'],['npm','run','build']):
        rc,out=run(cmd,cwd=prime,timeout=1200)
        if rc: raise RuntimeError(out[-8000:])
    cli=str(Path.cwd()/'packages/cli/dist/main.js')
    rc,out=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o','/tmp/prime-var-bin'],cwd=prime,timeout=1200)
    m=re.search(r'([^\n:]+\.js):(\d+):(\d+) - error SC1030: the reference to \'source_default\'',out)
    if not m: raise RuntimeError('source_default SC1030 not found in current frontier\n'+out[-10000:])
    file=Path(m.group(1)); line=int(m.group(2)); text=file.read_text(encoding='utf-8').splitlines()
    occ=[i+1 for i,s in enumerate(text) if 'source_default' in s]
    sections=[]
    sections += [f'build_status={rc}',f'file={file}',f'use_line={line}',f'all_occurrences={occ}']
    for center in occ:
        a=max(1,center-22); b=min(len(text),center+22)
        sections.append(f'\n=== source_default context {a}-{b} (center {center}) ===')
        sections.extend(f'{i:06d}: {text[i-1]}' for i in range(a,b+1))
    # Also inspect nearby esbuild module-boundary comments / init helpers.
    for needle in ('source_default =','var source_default','source_default;'):
        hits=[i+1 for i,s in enumerate(text) if needle in s]
        sections.append(f'needle {needle!r}: {hits}')
    REPORT.write_text('\n'.join(sections)+'\n',encoding='utf-8')
except Exception as e:
    REPORT.write_text('VAR_HOIST_CONTEXT=FAIL\n'+repr(e)+'\n'+traceback.format_exc(),encoding='utf-8')
