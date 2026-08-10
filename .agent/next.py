from pathlib import Path
import os, re, shutil, subprocess, traceback

FILES = {
    'nodes': Path('packages/compiler/src/ir/nodes.ts'),
    'validate': Path('packages/compiler/src/ir/validate.ts'),
    'classes': Path('packages/compiler/src/frontend/lowering/lower-classes.ts'),
    'cemit': Path('packages/compiler/src/backend/emission/emit-exprs.ts'),
    'hdr': Path('packages/runtime/src/scr_runtime.h'),
    'island': Path('packages/runtime/src/scr_island.c'),
}
CORPUS = Path('tests/corpus/3014-js-error-message-coercion.js')
REPORT = Path('WORKER_ERROR_ISLAND_RESULT.txt')
FAIL = Path('WORKER_ERROR_ISLAND_FAILURE.txt')
orig = {k: p.read_text(encoding='utf-8') for k,p in FILES.items()}
orig_corpus = CORPUS.read_text(encoding='utf-8') if CORPUS.exists() else None
log=[]

def run(args,cwd=None,env=None,timeout=1800):
    log.append('$ '+' '.join(map(str,args)))
    try:
        cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        out=cp.stdout or ''
        log.extend(out.splitlines()[-240:]); log.append(f'[exit {cp.returncode}]')
        return cp.returncode,out
    except Exception as e:
        log.append(f'RUN EXCEPTION {e!r}'); log.extend(traceback.format_exc().splitlines()); return 127,''

def rep(key,old,new,count=1):
    text=FILES[key].read_text(encoding='utf-8'); n=text.count(old)
    if n!=count: raise RuntimeError(f'{key}: expected {count} matches, found {n} for {old[:120]!r}')
    FILES[key].write_text(text.replace(old,new,count),encoding='utf-8')

ok=True
try:
    rep('nodes','  | "island.eval"\n','  | "island.eval"\n  | "island.errorMessage"\n')
    rep('nodes','  "island.eval",\n  "island.import",','  "island.eval",\n  "island.errorMessage",\n  "island.import",')
    rep('validate','  "island.eval": { argTypes: [STRING], result: STRING },\n','  "island.eval": { argTypes: [STRING], result: STRING },\n  "island.errorMessage": { argTypes: [JSVAL], result: STRING },\n')
    old='''    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    L.unsupported(\n'''
    new='''    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    if (value.type.kind === "jsval") {\n      return { kind: "libCall", fn: "island.errorMessage", args: [value], type: STRING, loc };\n    }\n    L.unsupported(\n'''
    rep('classes',old,new)
    anchor='''          case "island.import":\n'''
    inserted='''          case "island.errorMessage":\n            // Error(message) on an island value: runtime undefined is the\n            // omitted-message case; every other value uses engine String().\n            // May throw when user coercion throws; finish emits the pending check.\n            return finish(`scr_jsval_error_message(${arg(0)})`);\n          case "island.import":\n'''
    rep('cemit',anchor,inserted)
    rep('hdr','ScrStr *scr_jsval_to_str(ScrJsval *a); /* String(v); NULL = bridged */\n','ScrStr *scr_jsval_to_str(ScrJsval *a); /* String(v); NULL = bridged */\nScrStr *scr_jsval_error_message(ScrJsval *a); /* Error(message): undefined => empty */\n')
    anchor='''ScrStr *scr_jsval_to_str(ScrJsval *a) {\n  isl_entry();\n  return isl_js_to_str(a->v); /* NULL = bridged (e.g. a symbol) */\n}\n'''
    inserted=anchor+'''\nScrStr *scr_jsval_error_message(ScrJsval *a) {\n  isl_entry();\n  if (JS_IsUndefined(a->v)) return scr_str_new("", 0);\n  return isl_js_to_str(a->v); /* NULL = bridged coercion exception */\n}\n'''
    rep('island',anchor,inserted)
    CORPUS.write_text('''// @dynamic\n// Error(message) coerces a present message with String(), except undefined\n// is exactly the omitted-message case. The expression must evaluate once.\nconst values = ["text", 42, false, null, undefined];\nfor (const v of values) console.log(String(new Error(v)));\nclass WrappedError extends Error { constructor(message) { super(message); } }\nfor (const v of values) console.log(String(new WrappedError(v)));\nlet calls = 0;\nfunction once() { calls++; return 123; }\nconsole.log(String(new Error(once())), calls);\n''',encoding='utf-8')
except Exception as e:
    log.append(f'PATCH EXCEPTION: {e!r}'); log.extend(traceback.format_exc().splitlines()); ok=False

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

prime_lines=[]
if ok:
    prime=Path('/tmp/prime-worker-error')
    if prime.exists(): shutil.rmtree(prime)
    rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(prime)],env=ENV,timeout=300)
    if rc==0: rc,_=run(['npm','ci'],cwd=prime,env=ENV,timeout=1200)
    if rc==0: rc,_=run(['npm','run','build'],cwd=prime,env=ENV,timeout=1200)
    build_status=126; smoke_status=125; build_out=''; smoke_out='prime prep failed'
    if rc==0:
        out='/tmp/prime-worker-error-bin'
        try: Path(out).unlink()
        except FileNotFoundError: pass
        cli=str(Path.cwd()/'packages/cli/dist/main.js')
        build_status,build_out=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',out],cwd=prime,env=ENV,timeout=1200)
        if build_status==0 and Path(out).exists(): smoke_status,smoke_out=run(['timeout','20s',out,'--help'],cwd=prime,env=ENV,timeout=30)
    diags=[x for x in build_out.splitlines() if re.search(r'\bSC\d{4}:',x)]
    prime_lines=[f'prime_build_status={build_status}',f'prime_smoke_status={smoke_status}',f'prime_diagnostic_count={len(diags)}','--- prime diagnostics ---',*diags,'--- smoke tail ---',*smoke_out.splitlines()[-80:]]

if not ok:
    for k,p in FILES.items(): p.write_text(orig[k],encoding='utf-8')
    if orig_corpus is None:
        if CORPUS.exists(): CORPUS.unlink()
    else: CORPUS.write_text(orig_corpus,encoding='utf-8')
    FAIL.write_text('\n'.join(log+['ERROR_ISLAND_WORKER=FAIL; changes reverted'])+'\n',encoding='utf-8')
    raise SystemExit(0)
else:
    if FAIL.exists(): FAIL.unlink()
    REPORT.write_text('\n'.join(['ERROR_ISLAND_WORKER=PASS',*prime_lines])+'\n',encoding='utf-8')
