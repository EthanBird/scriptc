from pathlib import Path
import re,shutil,subprocess,traceback
REPORT=Path('WORKER_VAR_HOIST_CONTEXT.txt')
def run(args,cwd=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); return cp.returncode,cp.stdout or ''
try:
 rc,out=run(['pnpm','build'],1200)
 if rc: raise RuntimeError(out[-5000:])
 p=Path('/tmp/prime-varctx'); shutil.rmtree(p,ignore_errors=True)
 rc,out=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],timeout=300)
 if rc: raise RuntimeError(out[-5000:])
 for cmd in (['npm','ci'],['npm','run','build']):
  rc,out=run(cmd,cwd=p,timeout=1200)
  if rc: raise RuntimeError(out[-10000:])
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o','/tmp/prime-varctx-bin'],cwd=p,timeout=1200)
 m=re.search(r'([^\n:]+\.js):(\d+):(\d+) - error SC1030: the reference to \'source_default\'',out)
 if not m: raise RuntimeError('source_default blocker not found\n'+out[-12000:])
 f=Path(m.group(1)); center=int(m.group(2)); text=f.read_text(encoding='utf-8').splitlines()
 occ=[i+1 for i,s in enumerate(text) if 'source_default' in s]
 lines=[f'build_status={rc}',f'file={f}',f'blocker_line={center}',f'occurrences={occ}']
 for h in occ:
  a=max(1,h-35); b=min(len(text),h+35)
  lines += [f'\n=== source_default context center={h} range={a}-{b} ===']
  lines.extend(f'{i:06d}: {text[i-1]}' for i in range(a,b+1))
 # Capture nearby bundler init helpers and the closest enclosing function/class.
 for h in occ:
  for i in range(h-1,max(-1,h-1000),-1):
   if re.search(r'^(?:var\s+)?(?:init_[\w$]+\s*=|function\s+[\w$]+|var\s+[\w$]+\s*=\s*class|class\s+[\w$]+)',text[i].lstrip()):
    a=max(1,i+1-15); b=min(len(text),i+1+100)
    lines += [f'\n=== enclosing candidate before occurrence {h}: line {i+1} ===']
    lines.extend(f'{j:06d}: {text[j-1]}' for j in range(a,b+1)); break
 REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
except Exception as e:
 REPORT.write_text('VAR_CONTEXT=FAIL\n'+repr(e)+'\n'+traceback.format_exc(),encoding='utf-8')
