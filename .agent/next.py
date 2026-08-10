from pathlib import Path
import os, re, shutil, subprocess, traceback

OUT=Path('PRIME_BUNDLE_BLOCKER_CONTEXT.txt')
ENV=os.environ.copy()
LOG=[]

def run(args,cwd=None,timeout=1800):
    LOG.append('$ '+' '.join(map(str,args)))
    try:
        cp=subprocess.run(args,cwd=cwd,env=ENV,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        out=cp.stdout or ''; LOG.append(f'[exit {cp.returncode}]'); return cp.returncode,out
    except Exception as e:
        LOG.append(f'[exception {type(e).__name__}: {e}]'); LOG.extend(traceback.format_exc().splitlines()); return 127,''

rc,_=run(['pnpm','build'])
prime=Path('/tmp/prime-agent-context')
if prime.exists(): shutil.rmtree(prime)
if rc==0: rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(prime)],timeout=300)
if rc==0: rc,_=run(['npm','ci'],cwd=prime,timeout=1200)
if rc==0: rc,_=run(['npm','run','build'],cwd=prime,timeout=1200)
text=''
if rc==0:
    cli=str(Path.cwd()/'packages/cli/dist/main.js')
    _,text=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o','/tmp/prime-context-bin'],cwd=prime,timeout=1200)

pat=re.compile(r'^(.*?):(\d+):(\d+) - error (SC\d+): (.*)$')
items=[]
for line in text.splitlines():
    m=pat.match(line)
    if not m: continue
    file=Path(m.group(1)); ln=int(m.group(2)); code=m.group(4); msg=m.group(5)
    try:
        lines=file.read_text(encoding='utf-8').splitlines()
    except Exception:
        continue
    lo=max(1,ln-25); hi=min(len(lines),ln+25)
    snippet=[]
    for n in range(lo,hi+1):
        mark='>>' if n==ln else '  '
        snippet.append(f'{mark} {n:6d} | {lines[n-1]}')
    items.append((str(file.relative_to(prime) if file.is_relative_to(prime) else file),ln,code,msg,snippet))

report=['Prime bundled-JS blocker contexts','diagnostics='+str(len(items))]
for i,(file,ln,code,msg,snippet) in enumerate(items,1):
    report += ['',f'=== {i}. {file}:{ln} {code} ===',msg,*snippet]
if not items:
    report += ['','No diagnostics parsed. Raw build tail:',*text.splitlines()[-240:]]
OUT.write_text('\n'.join(report)+'\n',encoding='utf-8')
