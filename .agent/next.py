from pathlib import Path
import re,shutil,subprocess,traceback
SRC=Path('packages/compiler/src/frontend/lowering/lower-classes.ts'); orig=SRC.read_text(); REPORT=Path('WORKER_CLASS_DYNAMIC_CONTEXT.txt')
def run(args,cwd=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); return cp.returncode,cp.stdout or ''
try:
 old='''          if (type.kind === "dyn") {\n            L.unsupported("SC1090", member.name, "'unknown'-typed class fields");\n          }\n'''
 new='''          if (type.kind === "dyn" && !(L.looseJs && isJsSourceFile(decl.getSourceFile()))) {\n            L.unsupported("SC1090", member.name, "'unknown'-typed class fields");\n          }\n'''
 if orig.count(old)!=1: raise RuntimeError(f'dyn field anchor={orig.count(old)}')
 SRC.write_text(orig.replace(old,new,1))
 rc,out=run(['pnpm','build'],timeout=1200)
 if rc: raise RuntimeError(out[-6000:])
 p=Path('/tmp/prime-classdyn-context'); shutil.rmtree(p,ignore_errors=True)
 rc,out=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],timeout=300)
 if rc: raise RuntimeError(out[-5000:])
 for cmd in (['npm','ci'],['npm','run','build']):
  rc,out=run(cmd,cwd=p,timeout=1200)
  if rc: raise RuntimeError(out[-10000:])
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o','/tmp/prime-classdyn-bin'],cwd=p,timeout=1200)
 m=re.search(r'([^\n:]+\.js):(\d+):(\d+) - error SC1090: passing a value of type .*? into dynamically-executed',out)
 if not m: raise RuntimeError('class-dynamic blocker not found\n'+out[-12000:])
 f=Path(m.group(1)); center=int(m.group(2)); lines=f.read_text(encoding='utf-8').splitlines(); a=max(1,center-100); b=min(len(lines),center+120)
 report=[f'build_status={rc}',f'file={f}',f'line={center}',f'\n=== context {a}-{b} ===']+[f'{i:06d}: {lines[i-1]}' for i in range(a,b+1)]
 REPORT.write_text('\n'.join(report)+'\n')
except Exception as e:
 REPORT.write_text('CLASS_DYNAMIC_CONTEXT=FAIL\n'+repr(e)+'\n'+traceback.format_exc())
finally:
 SRC.write_text(orig)
