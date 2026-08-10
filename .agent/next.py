from pathlib import Path
import os,re,shutil,subprocess,traceback
SRC=Path('packages/compiler/src/frontend/lowering/lower-classes.ts'); orig=SRC.read_text(); REPORT=Path('WORKER_CLASSVAL_DYNFIELD_RESULT.txt'); FAIL=Path('WORKER_CLASSVAL_DYNFIELD_FAILURE.txt'); log=[]
def run(args,cwd=None,env=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); out=cp.stdout or ''; log.extend(['$ '+' '.join(map(str,args)),*out.splitlines()[-220:],f'[exit {cp.returncode}]']); return cp.returncode,out
ok=True
try:
 old='''          // dyn stays out of class fields (KEEP NARROW; record\n          // fields and array elements are unmappable via mapType already).\n          if (type.kind === "dyn") {\n            L.unsupported("SC1090", member.name, "'unknown'-typed class fields");\n          }\n'''
 new='''          // Generated/bundled JS may carry intentionally opaque values\n          // (notably untyped `new Map()`) in class fields. In --loose-js\n          // keep the class layout alive with a checked-dynamic slot;\n          // unsupported operations on that value still defer/fence at the\n          // method use site. Regular JS/TS preserves the narrow rule.\n          if (type.kind === "dyn" && !(L.looseJs && isJsSourceFile(decl.getSourceFile()))) {\n            L.unsupported("SC1090", member.name, "'unknown'-typed class fields");\n          }\n'''
 if orig.count(old)!=1: raise RuntimeError(f'anchor count={orig.count(old)}')
 SRC.write_text(orig.replace(old,new,1))
except Exception as e: log += ['PATCH '+repr(e),traceback.format_exc()]; ok=False
ENV=os.environ.copy()
if ok:
 for cmd in (["pnpm","build"],["pnpm","lint"]):
  rc,_=run(cmd,env=ENV)
  if rc: ok=False; break
if ok:
 root=Path('/tmp/dynfield-worker'); root.mkdir(exist_ok=True)
 src=root/'probe.js'; src.write_text('''class Box {\n  store = new Map();\n  add(k,v) { this.store.set(k,v); }\n  get(k) { return this.store.get(k); }\n}\nclass Holder { box = new Box(); }\nconsole.log(new Holder() instanceof Holder);\n''')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build',str(src),'--dynamic','--loose-js','-o',str(root/'probe-bin')],env=ENV,timeout=900)
 if rc!=0: ok=False
 if rc==0:
  rr,ro=run([str(root/'probe-bin')],env=ENV,timeout=60)
  if rr!=0 or ro.strip()!='true': ok=False; log.append('probe runtime mismatch')
 # Without loose-js the historical field fence must remain.
 rc2,out2=run(['node',cli,'build',str(src),'--dynamic','-o',str(root/'strict-bin')],env=ENV,timeout=900)
 if rc2==0 or "unknown'-typed class fields" not in out2:
  ok=False; log.append('strict lane unexpectedly accepted dynamic class field')
prime=[]
if ok:
 p=Path('/tmp/prime-classval-dynfield'); shutil.rmtree(p,ignore_errors=True)
 rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],env=ENV,timeout=300)
 if rc==0: rc,_=run(['npm','ci'],cwd=p,env=ENV,timeout=1200)
 if rc==0: rc,_=run(['npm','run','build'],cwd=p,env=ENV,timeout=1200)
 bs=126; ss=125; bout=''; sout=''
 if rc==0:
  cli=str(Path.cwd()/'packages/cli/dist/main.js'); outbin='/tmp/prime-classval-dynfield-bin'
  bs,bout=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',outbin],cwd=p,env=ENV,timeout=1200)
  if bs==0 and Path(outbin).exists(): ss,sout=run(['timeout','20s',outbin,'--help'],cwd=p,env=ENV,timeout=30)
 diags=[x for x in bout.splitlines() if re.search(r'\bSC\d{4}:',x)]
 prime=[f'prime_build_status={bs}',f'prime_smoke_status={ss}',f'prime_diagnostic_count={len(diags)}','--- diagnostics ---',*diags,'--- smoke ---',*sout.splitlines()[-100:]]
if not ok:
 SRC.write_text(orig); FAIL.write_text('\n'.join(log+['CLASSVAL_DYNFIELD=FAIL; source reverted'])+'\n')
else:
 if FAIL.exists(): FAIL.unlink()
 REPORT.write_text('\n'.join(['CLASSVAL_DYNFIELD=PASS',*prime])+'\n')
