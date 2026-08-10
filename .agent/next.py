from pathlib import Path
import subprocess, traceback
REPORT=Path('WORKER_ERROR_ISLAND_BACKEND_DIAG.txt')
# Re-apply the same minimal ABI patch, but this task is diagnostic: preserve source only in /tmp copy is unnecessary;
# patch the checkout and revert before exit so the report isolates backend behavior.
files={k:Path(p) for k,p in {
'nodes':'packages/compiler/src/ir/nodes.ts','validate':'packages/compiler/src/ir/validate.ts','classes':'packages/compiler/src/frontend/lowering/lower-classes.ts','cemit':'packages/compiler/src/backend/emission/emit-exprs.ts','hdr':'packages/runtime/src/scr_runtime.h','island':'packages/runtime/src/scr_island.c'}.items()}
orig={k:p.read_text() for k,p in files.items()}
fixture=Path('/tmp/error-island-diag.js')
fixture.write_text('// @dynamic\nconst v = 42; console.log(String(new Error(v)));\n')
def rep(k,a,b):
 t=files[k].read_text(); n=t.count(a)
 if n!=1: raise RuntimeError(f'{k} anchor {n}: {a[:80]!r}')
 files[k].write_text(t.replace(a,b,1))
def run(args,timeout=600):
 cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 return cp.returncode,cp.stdout or '',cp.stderr or ''
lines=[]
try:
 rep('nodes','  | "island.eval"\n','  | "island.eval"\n  | "island.errorMessage"\n')
 rep('nodes','  "island.eval",\n  "island.import",','  "island.eval",\n  "island.errorMessage",\n  "island.import",')
 rep('validate','  "island.eval": { argTypes: [STRING], result: STRING },\n','  "island.eval": { argTypes: [STRING], result: STRING },\n  "island.errorMessage": { argTypes: [JSVAL], result: STRING },\n')
 rep('classes','''    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    L.unsupported(\n''','''    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    if (value.type.kind === "jsval") return { kind: "libCall", fn: "island.errorMessage", args: [value], type: STRING, loc };\n    L.unsupported(\n''')
 rep('cemit','          case "island.import":\n','          case "island.errorMessage":\n            return finish(`scr_jsval_error_message(${arg(0)})`);\n          case "island.import":\n')
 rep('hdr','ScrStr *scr_jsval_to_str(ScrJsval *a); /* String(v); NULL = bridged */\n','ScrStr *scr_jsval_to_str(ScrJsval *a); /* String(v); NULL = bridged */\nScrStr *scr_jsval_error_message(ScrJsval *a);\n')
 a='''ScrStr *scr_jsval_to_str(ScrJsval *a) {\n  isl_entry();\n  return isl_js_to_str(a->v); /* NULL = bridged (e.g. a symbol) */\n}\n'''
 rep('island',a,a+'''\nScrStr *scr_jsval_error_message(ScrJsval *a) {\n  isl_entry();\n  if (JS_IsUndefined(a->v)) return scr_str_new("", 0);\n  return isl_js_to_str(a->v);\n}\n''')
 rc,so,se=run(['pnpm','build'],1200); lines += [f'pnpm_build={rc}',so,se]
 if rc: raise RuntimeError('build failed')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 for mode,args in [('c',['--backend','c']),('llvm',['--backend','llvm']),('default',[])]:
   out=f'/tmp/error-island-{mode}'
   rc,so,se=run(['node',cli,'build',str(fixture),'--dynamic',*args,'-o',out],1200)
   lines += [f'\n=== BUILD {mode} rc={rc} ===','stdout='+repr(so),'stderr='+repr(se)]
   if rc==0 and Path(out).exists():
     rr,rso,rse=run([out],60)
     lines += [f'RUN {mode} rc={rr}','stdout='+repr(rso),'stderr='+repr(rse)]
except Exception as e:
 lines += ['EXCEPTION='+repr(e),traceback.format_exc()]
finally:
 for k,p in files.items(): p.write_text(orig[k])
 REPORT.write_text('\n'.join(lines)+'\n')
