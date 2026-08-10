from pathlib import Path
import os,re,shutil,subprocess,traceback
FILES={k:Path(p) for k,p in {
'nodes':'packages/compiler/src/ir/nodes.ts','validate':'packages/compiler/src/ir/validate.ts','classes':'packages/compiler/src/frontend/lowering/lower-classes.ts','cemit':'packages/compiler/src/backend/emission/emit-exprs.ts','hdr':'packages/runtime/src/scr_runtime.h','island':'packages/runtime/src/scr_island.c'}.items()}
CORPUS=Path('tests/corpus/3014-js-error-message-coercion.js'); orig_corpus=CORPUS.read_text() if CORPUS.exists() else None
orig={k:p.read_text() for k,p in FILES.items()}; REPORT=Path('WORKER_ERROR_ISLAND_RESULT.txt'); FAIL=Path('WORKER_ERROR_ISLAND_FAILURE.txt'); log=[]
def run(args,cwd=None,env=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); out=cp.stdout or ''; log.extend(['$ '+' '.join(map(str,args)),*out.splitlines()[-180:],f'[exit {cp.returncode}]']); return cp.returncode,out
def rep(k,a,b):
 t=FILES[k].read_text(); n=t.count(a)
 if n!=1: raise RuntimeError(f'{k} anchor {n}: {a[:100]!r}')
 FILES[k].write_text(t.replace(a,b,1))
ok=True
try:
 rep('nodes','  | "island.eval"\n','  | "island.eval"\n  | "island.errorMessage"\n')
 rep('nodes','  "island.eval",\n  "island.import",','  "island.eval",\n  "island.errorMessage",\n  "island.import",')
 rep('validate','  "island.eval": { argTypes: [STRING], result: STRING },\n','  "island.eval": { argTypes: [STRING], result: STRING },\n  "island.errorMessage": { argTypes: [JSVAL], result: STRING },\n')
 old='''    if (value.type.kind === "string") return value;\n    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    L.unsupported(\n'''
 new='''    if (value.type.kind === "string") return value;\n    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    if (value.kind === "unitLit" && value.unit === "null") {\n      return { kind: "strLit", value: "null", type: STRING, loc };\n    }\n    if (value.type.kind === "f64" || value.type.kind === "bool") {\n      return L.ensureString(value, args[0]!);\n    }\n    if (value.type.kind === "jsval") {\n      return { kind: "libCall", fn: "island.errorMessage", args: [value], type: STRING, loc };\n    }\n    L.unsupported(\n'''
 rep('classes',old,new)
 rep('cemit','          case "island.import":\n','          case "island.errorMessage":\n            return finish(`scr_jsval_error_message(${arg(0)})`);\n          case "island.import":\n')
 rep('hdr','ScrStr *scr_jsval_to_str(ScrJsval *a); /* String(v); NULL = bridged */\n','ScrStr *scr_jsval_to_str(ScrJsval *a); /* String(v); NULL = bridged */\nScrStr *scr_jsval_error_message(ScrJsval *a); /* Error(message): undefined => empty */\n')
 a='''ScrStr *scr_jsval_to_str(ScrJsval *a) {\n  isl_entry();\n  return isl_js_to_str(a->v); /* NULL = bridged (e.g. a symbol) */\n}\n'''
 rep('island',a,a+'''\nScrStr *scr_jsval_error_message(ScrJsval *a) {\n  isl_entry();\n  if (JS_IsUndefined(a->v)) return scr_str_new("", 0);\n  return isl_js_to_str(a->v);\n}\n''')
 CORPUS.write_text('''// @dynamic\nconsole.log(String(new Error("text")));\nconsole.log(String(new Error(42)));\nconsole.log(String(new Error(false)));\nconsole.log(String(new Error(null)));\nconsole.log(String(new Error(undefined)));\nclass WrappedError extends Error { constructor(message) { super(message); } }\nconsole.log(String(new WrappedError("text")));\nconsole.log(String(new WrappedError(42)));\nconsole.log(String(new WrappedError(false)));\nconsole.log(String(new WrappedError(null)));\nconsole.log(String(new WrappedError(undefined)));\nlet calls=0; function once(){ calls++; return 123; }\nconsole.log(String(new Error(once())), calls);\n''')
except Exception as e: log += ['PATCH '+repr(e),traceback.format_exc()]; ok=False
ENV=os.environ.copy()
if ok:
 for cmd in (["pnpm","build"],["pnpm","lint"]):
  rc,_=run(cmd,env=ENV)
  if rc: ok=False; break
if ok:
 pat='3014-js-error-message-coercion|3015-math-random-function-value'
 for san in (False,True):
  env=ENV.copy(); env.pop('SCRIPTC_SAN',None)
  if san: env['SCRIPTC_SAN']='1'
  for tf in ('tests/harness/differential.test.ts','tests/harness/llvm-differential.test.ts'):
   rc,_=run(['pnpm','exec','vitest','run',tf,'-t',pat],env=env)
   if rc: ok=False
prime=[]
if ok:
 p=Path('/tmp/prime-error-final'); shutil.rmtree(p,ignore_errors=True)
 rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],timeout=300)
 if rc==0: rc,_=run(['npm','ci'],cwd=p,timeout=1200)
 if rc==0: rc,_=run(['npm','run','build'],cwd=p,timeout=1200)
 bout=''; bs=126; ss=125; sout=''
 if rc==0:
  cli=str(Path.cwd()/'packages/cli/dist/main.js'); out='/tmp/prime-error-final-bin'
  bs,bout=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',out],cwd=p,timeout=1200)
  if bs==0 and Path(out).exists(): ss,sout=run(['timeout','20s',out,'--help'],cwd=p,timeout=30)
 diags=[x for x in bout.splitlines() if re.search(r'\bSC\d{4}:',x)]
 prime=[f'prime_build_status={bs}',f'prime_smoke_status={ss}',f'prime_diagnostic_count={len(diags)}','--- diagnostics ---',*diags,'--- smoke ---',*sout.splitlines()[-80:]]
if not ok:
 for k,p in FILES.items(): p.write_text(orig[k])
 if orig_corpus is None:
  if CORPUS.exists(): CORPUS.unlink()
 else: CORPUS.write_text(orig_corpus)
 FAIL.write_text('\n'.join(log+['ERROR_ISLAND=FAIL; reverted'])+'\n'); raise SystemExit(0)
if FAIL.exists(): FAIL.unlink()
REPORT.write_text('\n'.join(['ERROR_ISLAND=PASS',*prime])+'\n')
