from pathlib import Path
import os,re,shutil,subprocess,traceback
SRC=Path('packages/compiler/src/frontend/lowering/lower-stmts.ts'); orig=SRC.read_text(); REPORT=Path('WORKER_VAR_HOIST_FIX_RESULT.txt'); FAIL=Path('WORKER_VAR_HOIST_FIX_FAILURE.txt'); log=[]
def run(args,cwd=None,env=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); out=cp.stdout or ''; log.extend(['$ '+' '.join(map(str,args)),*out.splitlines()[-240:],f'[exit {cp.returncode}]']); return cp.returncode,out
ok=True
try:
 old='''    const type = varBindingType(L, nameNode);\n    if (!type) return false;\n    const wrapped = type.kind === "dyn" ? dynUndefinedExpr(locOf(decl)) : L.unassignedSlotInit(type, locOf(decl));\n    if (!wrapped) return false;\n    const root = L.activeStmtLists.find((e) => e.ctx === ctx)!;\n'''
 new='''    let type = varBindingType(L, nameNode);\n    if (!type) return false;\n    let wrapped = type.kind === "dyn" ? dynUndefinedExpr(locOf(decl)) : L.unassignedSlotInit(type, locOf(decl));\n    // Bundled/generated JavaScript routinely captures a concrete `var T`\n    // from code text that precedes its declaration while executing the\n    // capture only after assignment. JavaScript nevertheless hoists the\n    // binding itself to function entry and its true pre-init value is\n    // undefined. In --loose-js, widen the INTERNAL storage to T|undefined\n    // when T has no native undefined sentinel. The declaration later\n    // writes through lowerVarDecl's existing coerceInto(hoisted.type),\n    // and normal read sites narrow/check against the checker's T.\n    if (\n      !wrapped && L.looseJs && isJsSourceFile(nameNode.getSourceFile()) &&\n      type.kind !== "void" && type.kind !== "dyn" && type.kind !== "jsval"\n    ) {\n      const widened = type.kind === "union" ? L.withUndefinedArmOf(type) : L.withUndefinedArm(type);\n      if (widened) {\n        type = widened;\n        wrapped = L.unassignedSlotInit(type, locOf(decl));\n      }\n    }\n    if (!wrapped) return false;\n    const root = L.activeStmtLists.find((e) => e.ctx === ctx)!;\n'''
 n=orig.count(old)
 if n!=1: raise RuntimeError(f'forward-var anchor count={n}')
 SRC.write_text(orig.replace(old,new,1))
except Exception as e: log += ['PATCH '+repr(e),traceback.format_exc()]; ok=False
ENV=os.environ.copy()
if ok:
 for cmd in (["pnpm","build"],["pnpm","lint"]):
  rc,_=run(cmd,env=ENV)
  if rc: ok=False; break
if ok:
 root=Path('/tmp/var-hoist-fix'); root.mkdir(exist_ok=True)
 after=root/'after.js'; after.write_text('''class Chalk { green(s) { return s; } }\nfunction main() {\n  const make = () => source_default.green("prime-agent> ");\n  var source_default = new Chalk();\n  return make();\n}\nconsole.log(`${main()}`);\n''')
 early=root/'early.js'; early.write_text('''class Chalk { green(s) { return s; } }\nfunction main() {\n  const make = () => source_default.green("x");\n  const out = make();\n  var source_default = new Chalk();\n  return out;\n}\nconsole.log(`${main()}`);\n''')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build',str(after),'--dynamic','--loose-js','-o',str(root/'after-bin')],env=ENV,timeout=900)
 if rc!=0: ok=False
 if rc==0:
  rr,ro=run([str(root/'after-bin')],env=ENV,timeout=60)
  if rr!=0 or ro.strip()!='prime-agent>': ok=False; log.append('assigned-before-read forward var mismatch')
 rc2,out2=run(['node',cli,'build',str(early),'--dynamic','--loose-js','-o',str(root/'early-bin')],env=ENV,timeout=900)
 if rc2!=0: ok=False; log.append('loose early-read should compile to runtime semantics')
 if rc2==0:
  rr2,ro2=run([str(root/'early-bin')],env=ENV,timeout=60)
  if rr2==0 or 'SC1030' in ro2 or 'Uncaught' not in ro2:
   ok=False; log.append('true pre-init read did not fail at runtime after successful compile')
 # Non-loose JS preserves historical compile/runtime-fence behavior.
 rc3,out3=run(['node',cli,'build',str(after),'--dynamic','-o',str(root/'strict-bin')],env=ENV,timeout=900)
 if rc3==0 and (root/'strict-bin').exists():
  rr3,ro3=run([str(root/'strict-bin')],env=ENV,timeout=60)
  if rr3==0 or 'SC1030' not in ro3: ok=False; log.append('non-loose JS lost SC1030 posture')
 elif rc3!=0 and 'SC1030' not in out3:
  ok=False; log.append('non-loose JS failed for unrelated reason')
prime=[]
if ok:
 p=Path('/tmp/prime-var-hoist-fix'); shutil.rmtree(p,ignore_errors=True)
 rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],env=ENV,timeout=300)
 if rc==0: rc,_=run(['npm','ci'],cwd=p,env=ENV,timeout=1200)
 if rc==0: rc,_=run(['npm','run','build'],cwd=p,env=ENV,timeout=1200)
 bs=126; ss=125; bout=''; sout=''
 if rc==0:
  cli=str(Path.cwd()/'packages/cli/dist/main.js'); outbin='/tmp/prime-var-hoist-fix-bin'
  bs,bout=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',outbin],cwd=p,env=ENV,timeout=1200)
  if bs==0 and Path(outbin).exists(): ss,sout=run(['timeout','20s',outbin,'--help'],cwd=p,env=ENV,timeout=30)
 diags=[x for x in bout.splitlines() if re.search(r'\bSC\d{4}:',x)]
 prime=[f'prime_build_status={bs}',f'prime_smoke_status={ss}',f'prime_diagnostic_count={len(diags)}','--- diagnostics ---',*diags,'--- smoke ---',*sout.splitlines()[-100:]]
if not ok:
 SRC.write_text(orig); FAIL.write_text('\n'.join(log+['VAR_HOIST_FIX=FAIL; source reverted'])+'\n')
else:
 if FAIL.exists(): FAIL.unlink()
 REPORT.write_text('\n'.join(['VAR_HOIST_FIX=PASS',*prime])+'\n')
