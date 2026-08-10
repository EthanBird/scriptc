from pathlib import Path
import os, re, shutil, subprocess

SOURCE=Path('packages/compiler/src/frontend/lowering/lower-classes.ts')
CORPUS=Path('tests/corpus/3014-js-error-message-coercion.js')
FAIL=Path('JS_ERROR_MESSAGE_COERCION_FAILURE.txt')
PRIME=Path('PRIME_LOOSE_JS_RESULT.txt')
LOG=[]
orig_source=SOURCE.read_text(encoding='utf-8')
orig_corpus=CORPUS.read_text(encoding='utf-8') if CORPUS.exists() else None

def run(args, cwd=None, env=None, timeout=1800):
    LOG.append('$ ' + ' '.join(args))
    cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    out=cp.stdout or ''
    LOG.extend(out.splitlines()[-400:])
    LOG.append(f'[exit {cp.returncode}]')
    return cp.returncode,out

def replace_once(text, old, new, what):
    n=text.count(old)
    if n!=1: raise RuntimeError(f'{what}: expected one match, found {n}')
    return text.replace(old,new,1)

ok=True
try:
    old='''/** The single message argument of a builtin Error construction or\n   * super() call: "" when omitted or explicitly undefined (Node's message\n   * property default), the string otherwise. The lib signature's second\n   * parameter (options/cause) has no lowering. */\n  export function errorMessageArg(L: Lowerer, args: readonly ts.Expression[], loc: SrcLoc, blame: ts.Node): IrExpr {\n    if (args.length > 1) {\n      L.unsupported("SC1090", args[1] ?? blame, "Error constructor options ('cause')");\n    }\n    if (args.length === 0) return { kind: "strLit", value: "", type: STRING, loc };\n    const value = L.lowerExpr(args[0]!);\n    if (value.type.kind === "string") return value;\n    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    L.unsupported(\n      "SC1090",\n      args[0]!,\n      `Error messages of type '${L.fmt(value.type)}' (the message must be a string)`,\n    );\n  }\n'''
    new='''/** The JS `Error(message)` coercion helper for an island value. The\n   * argument is evaluated ONCE by the caller and enters as one jsval param;\n   * explicit/runtime undefined is the constructor's omitted-message case\n   * (message == "" in our ScrError representation), every other value uses\n   * the engine's exact String(value) coercion. `typeof v` is used for the\n   * undefined test so no new runtime/IR primitive is needed. */\n  function errorJsvalMessageHelper(L: Lowerer, loc: SrcLoc): string {\n    const key = "error:jsval-message";\n    const existing = L.widthHelpers.get(key);\n    if (existing) return existing;\n    const name = `%error.message.${L.widthHelpers.size}`;\n    L.widthHelpers.set(key, name);\n    const value: IrExpr = { kind: "varRef", localId: "v.0", type: JSVAL, loc };\n    const typeofValue: IrExpr = { kind: "jsOp", op: "typeof", args: [value], type: STRING, loc };\n    const isUndefined: IrExpr = {\n      kind: "bin",\n      op: "===",\n      left: typeofValue,\n      right: { kind: "strLit", value: "undefined", type: STRING, loc },\n      type: BOOL,\n      loc,\n    };\n    const stringValue: IrExpr = { kind: "jsOp", op: "toStr", args: [value], type: STRING, loc };\n    const result: IrExpr = {\n      kind: "ternary",\n      cond: isUndefined,\n      then: { kind: "strLit", value: "", type: STRING, loc },\n      else_: stringValue,\n      type: STRING,\n      loc,\n    };\n    L.liftedFns.push({\n      name,\n      params: [{ localId: "v.0", name: "v", type: JSVAL }],\n      returnType: STRING,\n      locals: [{ id: "v.0", name: "v", type: JSVAL, mutable: true }],\n      body: [{ kind: "return", value: result, loc }],\n      loc,\n    });\n    return name;\n  }\n\n/** The single message argument of a builtin Error construction or\n   * super() call: omitted/undefined means no message; strings pass through;\n   * JavaScript `any`/island values apply Error's ToString semantics. The lib\n   * signature's second parameter (options/cause) has no lowering. */\n  export function errorMessageArg(L: Lowerer, args: readonly ts.Expression[], loc: SrcLoc, blame: ts.Node): IrExpr {\n    if (args.length > 1) {\n      L.unsupported("SC1090", args[1] ?? blame, "Error constructor options ('cause')");\n    }\n    if (args.length === 0) return { kind: "strLit", value: "", type: STRING, loc };\n    const value = L.lowerExpr(args[0]!);\n    if (value.type.kind === "string") return value;\n    if (value.kind === "unitLit" && value.unit === "undefined") {\n      return { kind: "strLit", value: "", type: STRING, loc };\n    }\n    if (value.type.kind === "jsval") {\n      const helper = errorJsvalMessageHelper(L, loc);\n      return { kind: "call", callee: helper, args: [value], type: STRING, loc };\n    }\n    if (value.type.kind === "dyn") {\n      // Checked-dynamic values already have JS-exact String() dispatch.\n      // The undefined singleton is observable through the dyn walker; Error\n      // needs the special omitted-message case, so route through a tiny dyn\n      // conditional using the existing nullish/typeof machinery later. For\n      // now loose bundled JS reaches this path as jsval, not dyn.\n      L.unsupported("SC1090", args[0]!, "Error messages from checked-dynamic unknown values");\n    }\n    L.unsupported(\n      "SC1090",\n      args[0]!,\n      `Error messages of type '${L.fmt(value.type)}' (the message must be a string)`,\n    );\n  }\n'''
    SOURCE.write_text(replace_once(orig_source,old,new,'errorMessageArg'),encoding='utf-8')
    CORPUS.write_text('''// JS Error constructors apply ToString to every present non-undefined message.\n// Runtime undefined is special: it is exactly the omitted-message case.\nconst values = ["text", 42, false, null, undefined];\nfor (const v of values) console.log(String(new Error(v)));\n\nclass WrappedError extends Error {\n  constructor(message) { super(message); }\n}\nfor (const v of values) console.log(String(new WrappedError(v)));\n\nlet calls = 0;\nfunction once() { calls++; return 123; }\nconsole.log(String(new Error(once())), calls);\n''',encoding='utf-8')
except Exception as e:
    LOG.append(f'PATCH EXCEPTION: {e!r}')
    ok=False

ENV=os.environ.copy()
if ok:
    for cmd in (["pnpm","build"],["pnpm","lint"]):
        rc,_=run(cmd,env=ENV)
        if rc: ok=False; break
if ok:
    pat='3014-js-error-message-coercion|3015-math-random-function-value'
    for san in (False,True):
        e=ENV.copy(); e.pop('SCRIPTC_SAN',None)
        if san: e['SCRIPTC_SAN']='1'
        for tf in ('tests/harness/differential.test.ts','tests/harness/llvm-differential.test.ts'):
            rc,_=run(['pnpm','exec','vitest','run',tf,'-t',pat],env=e)
            if rc: ok=False

if not ok:
    SOURCE.write_text(orig_source,encoding='utf-8')
    if orig_corpus is None:
        if CORPUS.exists(): CORPUS.unlink()
    else: CORPUS.write_text(orig_corpus,encoding='utf-8')
    LOG.append('JS_ERROR_MESSAGE_COERCION=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG)+'\n',encoding='utf-8')
else:
    if FAIL.exists(): FAIL.unlink()
    LOG.append('JS_ERROR_MESSAGE_COERCION=PASS')
    # Re-run the real Prime official bundle immediately, because this is the\n    # acceptance metric that matters. Prime source remains untouched.\n    prime_dir=Path('/tmp/prime-agent-error-coercion')
    if prime_dir.exists(): shutil.rmtree(prime_dir)
    rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(prime_dir)],env=ENV,timeout=300)
    if rc==0:
        rc,_=run(['npm','ci'],cwd=prime_dir,env=ENV,timeout=1200)
    if rc==0:
        rc,_=run(['npm','run','build'],cwd=prime_dir,env=ENV,timeout=1200)
    build_status=126; smoke_status=125; build_out=''
    if rc==0:
        out='/tmp/prime-agent-scriptc-loose'
        try: Path(out).unlink()
        except FileNotFoundError: pass
        build_status,build_out=run([str(Path.cwd()/ 'node_modules/.bin/scriptc'),'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',out],cwd=prime_dir,env=ENV,timeout=1200)
        if build_status==0 and Path(out).exists():
            smoke_status,smoke_out=run(['timeout','20s',out,'--help'],cwd=prime_dir,env=ENV,timeout=30)
        else:
            smoke_out='build did not produce executable'
    else:
        smoke_out='Prime oracle preparation failed'
    diags=[line for line in build_out.splitlines() if re.search(r'\bSC\d{4}:',line)]
    PRIME.write_text('\n'.join([\n        f'head_task=JS Error(any) coercion + Math.random validation',\n        f'build_status={build_status}',\n        f'smoke_status={smoke_status}',\n        f'diagnostic_count={len(diags)}',\n        '--- diagnostics ---',\n        *diags,\n        '--- smoke tail ---',\n        *smoke_out.splitlines()[-120:],\n    ])+'\n',encoding='utf-8')
