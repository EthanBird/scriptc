from pathlib import Path
import os,re,shutil,subprocess,traceback
SRC=Path('packages/compiler/src/frontend/lowering/lower-classes.ts'); orig=SRC.read_text(); REPORT=Path('WORKER_CLASSVAL_SET_RESULT.txt'); FAIL=Path('WORKER_CLASSVAL_SET_FAILURE.txt'); log=[]
def run(args,cwd=None,env=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); out=cp.stdout or ''; log.extend(['$ '+' '.join(map(str,args)),*out.splitlines()[-220:],f'[exit {cp.returncode}]']); return cp.returncode,out
ok=True
try:
 old='''        const targs = L.checker.getTypeArguments(tsType as ts.TypeReference);\n        if (targs[0]) {\n          L.unsupported(\n            "SC1090",\n            expr,\n            `Set elements of type '${L.checker.typeToString(targs[0])}' ` +\n'''
 new='''        const targs = L.checker.getTypeArguments(tsType as ts.TypeReference);\n        // `new Set()` in generated JavaScript infers Set<any>. Mirror the\n        // existing Map<any, any>/WeakSet loose-JS posture: construct an\n        // opaque checked-dynamic identity value so the containing class or\n        // module can compile; reached methods still fence at their use.\n        if (\n          L.looseJs && isJsSourceFile(expr.getSourceFile()) &&\n          (expr.arguments?.length ?? 0) === 0 &&\n          targs.length > 0 && targs.every((t) => (t.flags & ts.TypeFlags.Any) !== 0)\n        ) {\n          return { kind: "dynObjLit", type: DYN, loc };\n        }\n        if (targs[0]) {\n          L.unsupported(\n            "SC1090",\n            expr,\n            `Set elements of type '${L.checker.typeToString(targs[0])}' ` +\n'''
 if orig.count(old)!=1: raise RuntimeError(f'Set anchor count={orig.count(old)}')
 SRC.write_text(orig.replace(old,new,1))
except Exception as e: log += ['PATCH '+repr(e),traceback.format_exc()]; ok=False
ENV=os.environ.copy()
if ok:
 for cmd in (["pnpm","build"],["pnpm","lint"]):
  rc,_=run(cmd,env=ENV)
  if rc: ok=False; break
if ok:
 root=Path('/tmp/set-worker'); root.mkdir(exist_ok=True)
 f=root/'probe.js'; f.write_text('''class C { s = new Set(); add(v){ this.s.add(v); } }\nnew C();\nconsole.log("ok");\n''')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build',str(f),'--dynamic','--loose-js','-o',str(root/'probe-bin')],env=ENV,timeout=900)
 if rc!=0: ok=False
 if rc==0:
  rr,ro=run([str(root/'probe-bin')],env=ENV,timeout=60)
  if rr!=0 or ro.strip()!='ok': ok=False; log.append('Set loose-js runtime mismatch')
 rc2,out2=run(['node',cli,'build',str(f),'--dynamic','-o',str(root/'strict-bin')],env=ENV,timeout=900)
 if rc2==0 and (root/'strict-bin').exists():
  rr2,ro2=run([str(root/'strict-bin')],env=ENV,timeout=60)
  if rr2==0 or not ("unknown'-typed class fields" in ro2 or 'Set elements of type' in ro2):
   ok=False; log.append('strict JS did not preserve historical dynamic-field/Set fence')
 elif rc2!=0 and not ("unknown'-typed class fields" in out2 or 'Set elements of type' in out2):
  ok=False; log.append('strict JS failed for an unrelated reason')
prime=[]
if ok:
 p=Path('/tmp/prime-classval-set'); shutil.rmtree(p,ignore_errors=True)
 rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],env=ENV,timeout=300)
 if rc==0: rc,_=run(['npm','ci'],cwd=p,env=ENV,timeout=1200)
 if rc==0: rc,_=run(['npm','run','build'],cwd=p,env=ENV,timeout=1200)
 bs=126; ss=125; bout=''; sout=''
 if rc==0:
  cli=str(Path.cwd()/'packages/cli/dist/main.js'); outbin='/tmp/prime-classval-set-bin'
  bs,bout=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',outbin],cwd=p,env=ENV,timeout=1200)
  if bs==0 and Path(outbin).exists(): ss,sout=run(['timeout','20s',outbin,'--help'],cwd=p,env=ENV,timeout=30)
 diags=[x for x in bout.splitlines() if re.search(r'\bSC\d{4}:',x)]
 prime=[f'prime_build_status={bs}',f'prime_smoke_status={ss}',f'prime_diagnostic_count={len(diags)}','--- diagnostics ---',*diags,'--- smoke ---',*sout.splitlines()[-100:]]
if not ok:
 SRC.write_text(orig); FAIL.write_text('\n'.join(log+['CLASSVAL_SET=FAIL; source reverted'])+'\n')
else:
 if FAIL.exists(): FAIL.unlink()
 REPORT.write_text('\n'.join(['CLASSVAL_SET=PASS',*prime])+'\n')
