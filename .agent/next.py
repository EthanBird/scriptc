from pathlib import Path
import os, subprocess, traceback

FILES = {
    'nodes': Path('packages/compiler/src/ir/nodes.ts'),
    'validate': Path('packages/compiler/src/ir/validate.ts'),
    'cemit': Path('packages/compiler/src/backend/emission/emitter.ts'),
    'llvm': Path('packages/compiler/src/backend/llvm/emitter.ts'),
    'header': Path('packages/runtime/src/scr_runtime.h'),
    'island': Path('packages/runtime/src/scr_island.c'),
    'classes': Path('packages/compiler/src/frontend/lowering/lower-classes.ts'),
    'corpus': Path('tests/corpus/3014-js-error-message-coercion.js'),
}
FAIL = Path('JS_ERROR_MESSAGE_COERCION_FAILURE.txt')
LOG=[]
originals={k:p.read_text(encoding='utf-8') for k,p in FILES.items() if p.exists()}

def rep(key, old, new, count=1):
    p=FILES[key]; text=p.read_text(encoding='utf-8'); n=text.count(old)
    if n != count: raise RuntimeError(f'{key}: expected {count} matches, found {n} for {old[:100]!r}')
    p.write_text(text.replace(old,new,count),encoding='utf-8')

def run(args, env=None, timeout=1800):
    LOG.append('$ '+' '.join(map(str,args)))
    try:
        cp=subprocess.run(args,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        out=cp.stdout or ''; LOG.extend(out.splitlines()[-320:]); LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode
    except Exception as e:
        LOG.append(f'[exception {type(e).__name__}: {e}]'); LOG.extend(traceback.format_exc().splitlines()); return 127

ok=True
try:
    rep('nodes', '  | "island.eval"\n', '  | "island.eval"\n  | "island.errorMessage"\n', 1)
    rep('nodes', '  "island.eval",\n', '  "island.eval",\n  "island.errorMessage",\n', 1)
    rep('validate', '  "island.eval": { argTypes: [STRING], result: STRING },\n', '  "island.eval": { argTypes: [STRING], result: STRING },\n  "island.errorMessage": { argTypes: [JSVAL], result: STRING },\n', 1)
    rep('cemit', '  "island.eval": "scr_island_eval",\n', '  "island.eval": "scr_island_eval",\n  "island.errorMessage": "scr_jsval_error_message",\n', 1)
    rep('llvm', '  "island.eval": "scr_island_eval",\n', '  "island.eval": "scr_island_eval",\n  "island.errorMessage": "scr_jsval_error_message",\n', 1)
    rep('header', 'ScrStr *scr_jsval_to_str(ScrJsval *a); /* String(v); NULL = bridged */\n', 'ScrStr *scr_jsval_to_str(ScrJsval *a); /* String(v); NULL = bridged */\nScrStr *scr_jsval_error_message(ScrJsval *a); /* Error(message): undefined -> "", else String(v) */\n', 1)
    rep('island', '''ScrStr *scr_jsval_to_str(ScrJsval *a) {\n  isl_entry();\n  return isl_js_to_str(a->v); /* NULL = bridged (e.g. a symbol) */\n}\n''', '''ScrStr *scr_jsval_to_str(ScrJsval *a) {\n  isl_entry();\n  return isl_js_to_str(a->v); /* NULL = bridged (e.g. a symbol) */\n}\n\nScrStr *scr_jsval_error_message(ScrJsval *a) {\n  isl_entry();\n  if (JS_IsUndefined(a->v)) return scr_str_new("", 0);\n  return isl_js_to_str(a->v); /* Error(message) performs ToString; NULL = bridged throw */\n}\n''', 1)
    old='''    const value = L.lowerExpr(args[0]!);\n    if (value.type.kind === "string") return value;\n    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    L.unsupported(\n      "SC1090",\n      args[0]!,\n      `Error messages of type '${L.fmt(value.type)}' (the message must be a string)`,\n    );\n'''
    new='''    const value = L.lowerExpr(args[0]!);\n    if (value.type.kind === "string") return value;\n    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    if (value.type.kind === "jsval") {\n      return { kind: "libCall", fn: "island.errorMessage", args: [value], type: STRING, loc };\n    }\n    L.unsupported(\n      "SC1090",\n      args[0]!,\n      `Error messages of type '${L.fmt(value.type)}' (the message must be a string)`,\n    );\n'''
    rep('classes',old,new,1)
    FILES['corpus'].write_text('''// @dynamic\n// Error(message): present non-undefined values use JS ToString; undefined is omitted.\nconst values = ["text", 42, false, null, undefined];\nfor (const v of values) console.log(String(new Error(v)));\nclass WrappedError extends Error { constructor(message) { super(message); } }\nfor (const v of values) console.log(String(new WrappedError(v)));\nlet calls = 0;\nfunction once() { calls++; return 123; }\nconsole.log(String(new Error(once())), calls);\n''',encoding='utf-8')
except Exception as e:
    LOG.append(f'PATCH EXCEPTION: {e!r}'); LOG.extend(traceback.format_exc().splitlines()); ok=False

ENV=os.environ.copy()
if ok:
    for cmd in (["pnpm","build"],["pnpm","lint"]):
        if run(cmd,ENV)!=0: ok=False; break
if ok:
    pattern='3014-js-error-message-coercion|3015-math-random-function-value'
    for san in (False,True):
        env=ENV.copy(); env.pop('SCRIPTC_SAN',None)
        if san: env['SCRIPTC_SAN']='1'
        for tf in ('tests/harness/differential.test.ts','tests/harness/llvm-differential.test.ts'):
            if run(['pnpm','exec','vitest','run',tf,'-t',pattern],env)!=0: ok=False

if not ok:
    for k,p in FILES.items():
        if k in originals: p.write_text(originals[k],encoding='utf-8')
    LOG.append('JS_ERROR_MESSAGE_ABI=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG)+'\n',encoding='utf-8')
else:
    if FAIL.exists(): FAIL.unlink()
    LOG.append('JS_ERROR_MESSAGE_ABI=PASS')
