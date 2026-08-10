from pathlib import Path
import os, re, shutil, subprocess, traceback

SOURCE = Path('packages/compiler/src/frontend/lowering/lower-classes.ts')
CORPUS = Path('tests/corpus/3014-js-error-message-coercion.js')
FAIL = Path('JS_ERROR_MESSAGE_COERCION_FAILURE.txt')
PRIME = Path('PRIME_LOOSE_JS_RESULT.txt')
LOG = []
orig_source = SOURCE.read_text(encoding='utf-8')
orig_corpus = CORPUS.read_text(encoding='utf-8') if CORPUS.exists() else None

def run(args, cwd=None, env=None, timeout=1800):
    LOG.append('$ ' + ' '.join(map(str, args)))
    try:
        cp = subprocess.run(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        out = cp.stdout or ''
        LOG.extend(out.splitlines()[-320:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode, out
    except Exception as exc:
        LOG.append(f'[run exception {type(exc).__name__}: {exc}]')
        LOG.extend(traceback.format_exc().splitlines())
        return 127, ''

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 anchor, found {count}')
    return text.replace(old, new, 1)

ok = True
try:
    old = '''/** The single message argument of a builtin Error construction or
   * super() call: "" when omitted or explicitly undefined (Node's message
   * property default), the string otherwise. The lib signature's second
   * parameter (options/cause) has no lowering. */
  export function errorMessageArg(L: Lowerer, args: readonly ts.Expression[], loc: SrcLoc, blame: ts.Node): IrExpr {
    if (args.length > 1) {
      L.unsupported("SC1090", args[1] ?? blame, "Error constructor options ('cause')");
    }
    if (args.length === 0) return { kind: "strLit", value: "", type: STRING, loc };
    const value = L.lowerExpr(args[0]!);
    if (value.type.kind === "string") return value;
    if (value.kind === "unitLit" && value.unit === "undefined") {
      return { kind: "strLit", value: "", type: STRING, loc };
    }
    L.unsupported(
      "SC1090",
      args[0]!,
      `Error messages of type '${L.fmt(value.type)}' (the message must be a string)`,
    );
  }
'''
    new = '''/** A present JS `Error(message)` island value is evaluated exactly once.
   * Runtime undefined means the omitted-message case; all other values use
   * the engine's exact String(value) coercion. */
  function errorJsvalMessageHelper(L: Lowerer, loc: SrcLoc): string {
    const key = "error:jsval-message";
    const hit = L.widthHelpers.get(key);
    if (hit) return hit;
    const name = `%error.message.${L.widthHelpers.size}`;
    L.widthHelpers.set(key, name);
    const v: IrExpr = { kind: "varRef", localId: "v.0", type: JSVAL, loc };
    const typeofV: IrExpr = { kind: "jsOp", op: "typeof", args: [v], type: STRING, loc };
    const cond: IrExpr = {
      kind: "bin",
      op: "===",
      left: typeofV,
      right: { kind: "strLit", value: "undefined", type: STRING, loc },
      type: BOOL,
      loc,
    };
    const result: IrExpr = {
      kind: "ternary",
      cond,
      then: { kind: "strLit", value: "", type: STRING, loc },
      else_: { kind: "jsOp", op: "toStr", args: [v], type: STRING, loc },
      type: STRING,
      loc,
    };
    L.liftedFns.push({
      name,
      params: [{ localId: "v.0", name: "v", type: JSVAL }],
      returnType: STRING,
      locals: [{ id: "v.0", name: "v", type: JSVAL, mutable: true }],
      body: [{ kind: "return", value: result, loc }],
      loc,
    });
    return name;
  }

  /** The single message argument of a builtin Error construction or super(). */
  export function errorMessageArg(L: Lowerer, args: readonly ts.Expression[], loc: SrcLoc, blame: ts.Node): IrExpr {
    if (args.length > 1) {
      L.unsupported("SC1090", args[1] ?? blame, "Error constructor options ('cause')");
    }
    if (args.length === 0) return { kind: "strLit", value: "", type: STRING, loc };
    const value = L.lowerExpr(args[0]!);
    if (value.type.kind === "string") return value;
    if (value.kind === "unitLit" && value.unit === "undefined") {
      return { kind: "strLit", value: "", type: STRING, loc };
    }
    if (value.type.kind === "jsval") {
      return { kind: "call", callee: errorJsvalMessageHelper(L, loc), args: [value], type: STRING, loc };
    }
    L.unsupported(
      "SC1090",
      args[0]!,
      `Error messages of type '${L.fmt(value.type)}' (the message must be a string)`,
    );
  }
'''
    SOURCE.write_text(replace_once(orig_source, old, new, 'errorMessageArg'), encoding='utf-8')
    CORPUS.write_text('''// Present Error messages use JS ToString, except undefined == omitted.
const values = ["text", 42, false, null, undefined];
for (const v of values) console.log(String(new Error(v)));
class WrappedError extends Error { constructor(message) { super(message); } }
for (const v of values) console.log(String(new WrappedError(v)));
let calls = 0;
function once() { calls++; return 123; }
console.log(String(new Error(once())), calls);
''', encoding='utf-8')
except Exception as exc:
    LOG.append(f'PATCH EXCEPTION: {exc!r}')
    LOG.extend(traceback.format_exc().splitlines())
    ok = False

ENV = os.environ.copy()
if ok:
    for cmd in (["pnpm", "build"], ["pnpm", "lint"]):
        rc, _ = run(cmd, env=ENV)
        if rc:
            ok = False
            break
if ok:
    pattern = '3014-js-error-message-coercion|3015-math-random-function-value'
    for sanitized in (False, True):
        env = ENV.copy()
        env.pop('SCRIPTC_SAN', None)
        if sanitized:
            env['SCRIPTC_SAN'] = '1'
        for test_file in ('tests/harness/differential.test.ts', 'tests/harness/llvm-differential.test.ts'):
            rc, _ = run(['pnpm', 'exec', 'vitest', 'run', test_file, '-t', pattern], env=env)
            if rc:
                ok = False

if not ok:
    SOURCE.write_text(orig_source, encoding='utf-8')
    if orig_corpus is None:
        if CORPUS.exists():
            CORPUS.unlink()
    else:
        CORPUS.write_text(orig_corpus, encoding='utf-8')
    LOG.append('JS_ERROR_MESSAGE_COERCION=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
else:
    if FAIL.exists():
        FAIL.unlink()
    LOG.append('JS_ERROR_MESSAGE_COERCION=PASS')
    prime_dir = Path('/tmp/prime-agent-error-coercion')
    if prime_dir.exists():
        shutil.rmtree(prime_dir)
    rc, _ = run(['git', 'clone', '--depth', '1', 'https://github.com/EthanBird/prime-agent.git', str(prime_dir)], env=ENV, timeout=300)
    if rc == 0:
        rc, _ = run(['npm', 'ci'], cwd=prime_dir, env=ENV, timeout=1200)
    if rc == 0:
        rc, _ = run(['npm', 'run', 'build'], cwd=prime_dir, env=ENV, timeout=1200)
    build_status = 126
    smoke_status = 125
    build_out = ''
    smoke_out = 'Prime preparation failed'
    if rc == 0:
        out = '/tmp/prime-agent-scriptc-loose'
        try:
            Path(out).unlink()
        except FileNotFoundError:
            pass
        cli = str(Path.cwd() / 'packages/cli/dist/main.js')
        build_status, build_out = run(['node', cli, 'build', 'packages/coding-agent/dist/bundle/cli.js', '--dynamic', '--loose-js', '-o', out], cwd=prime_dir, env=ENV, timeout=1200)
        if build_status == 0 and Path(out).exists():
            smoke_status, smoke_out = run(['timeout', '20s', out, '--help'], cwd=prime_dir, env=ENV, timeout=30)
        else:
            smoke_out = 'build did not produce executable'
    diags = [line for line in build_out.splitlines() if re.search(r'\bSC\d{4}:', line)]
    report = [
        'head_task=JS Error(any) coercion + Math.random validation',
        f'build_status={build_status}',
        f'smoke_status={smoke_status}',
        f'diagnostic_count={len(diags)}',
        '--- diagnostics ---',
    ]
    report.extend(diags)
    report.append('--- smoke tail ---')
    report.extend(smoke_out.splitlines()[-120:])
    PRIME.write_text('\n'.join(report) + '\n', encoding='utf-8')
