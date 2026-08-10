from pathlib import Path
import os
import subprocess
import traceback

LOWERER = Path('packages/compiler/src/frontend/lowering/lowerer.ts')
CALLS = Path('packages/compiler/src/frontend/lowering/lower-calls.ts')
INDEX = Path('packages/compiler/src/index.ts')
FIXTURE = Path('tests/loose-js-concrete-returns.js')
FAIL = Path('LOOSE_JS_RETURN_INFERENCE_FAILURE.txt')
LOG = []
originals = {p: p.read_text(encoding='utf-8') for p in (LOWERER, CALLS, INDEX)}
orig_fixture = FIXTURE.read_text(encoding='utf-8') if FIXTURE.exists() else None

def rep(path, old, new, expected=1):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f'{path}: expected {expected} matches, found {count} for {old[:80]!r}')
    path.write_text(text.replace(old, new), encoding='utf-8')

def run(args, cwd=None, env=None, timeout=1800):
    LOG.append('$ ' + ' '.join(map(str, args)))
    try:
        cp = subprocess.run(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        out = cp.stdout or ''
        LOG.extend(out.splitlines()[-300:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode, out
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        LOG.extend(traceback.format_exc().splitlines())
        return 127, ''

ok = True
try:
    rep(LOWERER,
        '''  dynamic?: boolean;\n  /** Coverage: additionally lower the unreached remainder''',
        '''  dynamic?: boolean;\n  /** --loose-js: bundled/generated JavaScript may trust the checker's concrete\n   * inferred func/record return shapes instead of intentionally degrading them\n   * to checked-dynamic values. Ordinary JS keeps the historic identity-first\n   * fallback. */\n  looseJs?: boolean;\n  /** Coverage: additionally lower the unreached remainder''')
    rep(LOWERER,
        '''    readonly moduleOrder: ts.SourceFile[],\n    readonly dynamic: boolean,\n    mode: LowererMode = {},''',
        '''    readonly moduleOrder: ts.SourceFile[],\n    readonly dynamic: boolean,\n    readonly looseJs: boolean,\n    mode: LowererMode = {},''')
    rep(LOWERER,
        '''  const dynamic = options.dynamic ?? false;\n  const targetPlatform = options.targetPlatform ?? process.platform;''',
        '''  const dynamic = options.dynamic ?? false;\n  const looseJs = options.looseJs ?? false;\n  const targetPlatform = options.targetPlatform ?? process.platform;''')
    rep(LOWERER,
        '''new Lowerer(program, entry, moduleOrder, dynamic, {''',
        '''new Lowerer(program, entry, moduleOrder, dynamic, looseJs, {''',
        expected=4)
    rep(INDEX,
        '''    lower: (opts) => lowerToIr(finalLoad.program, finalLoad.entry, finalLoad.moduleOrder, {\n      ...opts,\n      startupCrash:''',
        '''    lower: (opts) => lowerToIr(finalLoad.program, finalLoad.entry, finalLoad.moduleOrder, {\n      ...opts,\n      looseJs,\n      startupCrash:''')
    rep(CALLS,
        '''    if (\n      isJsSourceFile(decl.getSourceFile()) &&\n      decl.type === undefined &&\n      L.mapTypeOf(retTsType)?.kind === "func"\n    ) {''',
        '''    if (\n      !L.looseJs &&\n      isJsSourceFile(decl.getSourceFile()) &&\n      decl.type === undefined &&\n      L.mapTypeOf(retTsType)?.kind === "func"\n    ) {''')
    rep(CALLS,
        '''    if (\n      isJsSourceFile(decl.getSourceFile()) &&\n      decl.type === undefined &&\n      L.mapTypeOf(retTsType)?.kind === "record" &&''',
        '''    if (\n      !L.looseJs &&\n      isJsSourceFile(decl.getSourceFile()) &&\n      decl.type === undefined &&\n      L.mapTypeOf(retTsType)?.kind === "record" &&''')
    FIXTURE.write_text('''// Generated/bundled JS: --loose-js trusts concrete checker inference.\nfunction makeParser(flag) {\n  return function (left, right) { return flag ? left : right; };\n}\n\nfunction createDeferred() {\n  let settled = false;\n  return {\n    value: "ready",\n    settle(value) { if (settled) return false; settled = true; return value === "ok"; },\n    reject() { if (settled) return false; settled = true; return true; },\n  };\n}\n\nclass BundleLike {\n  parse = this.parseMarkdown(true);\n  parseInline = this.parseMarkdown(false);\n  accepted = createDeferred();\n  parseMarkdown(block) { return makeParser(block); }\n}\n\nconst b = new BundleLike();\nconsole.log(b.parse("L", "R"), b.parseInline("L", "R"), b.accepted.value, b.accepted.settle("ok"), b.accepted.reject());\n''', encoding='utf-8')
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
    node_rc, node_out = run(['node', str(FIXTURE)], env=ENV)
    out = '/tmp/scriptc-loose-js-returns'
    cli = str(Path.cwd() / 'packages/cli/dist/main.js')
    build_rc, _ = run(['node', cli, 'build', str(FIXTURE), '--dynamic', '--loose-js', '-o', out], env=ENV, timeout=1200)
    native_rc, native_out = (127, '')
    if build_rc == 0:
        native_rc, native_out = run([out], env=ENV, timeout=30)
    if node_rc != 0 or build_rc != 0 or native_rc != 0 or node_out != native_out:
        LOG.append('loose-js concrete-return differential mismatch')
        LOG.append('NODE=' + repr(node_out))
        LOG.append('NATIVE=' + repr(native_out))
        ok = False

# Ordinary JS semantics must remain on the historical path; run a focused\n# existing dynamic-JS regression plus the new Error/Math corpus when present.
if ok:
    pattern = '3014-js-error-message-coercion|3015-math-random-function-value|2449-js-dyn-worlds'
    for test_file in ('tests/harness/differential.test.ts', 'tests/harness/llvm-differential.test.ts'):
        rc, _ = run(['pnpm', 'exec', 'vitest', 'run', test_file, '-t', pattern], env=ENV)
        if rc:
            ok = False

if not ok:
    for path, text in originals.items():
        path.write_text(text, encoding='utf-8')
    if orig_fixture is None:
        if FIXTURE.exists(): FIXTURE.unlink()
    else:
        FIXTURE.write_text(orig_fixture, encoding='utf-8')
    LOG.append('LOOSE_JS_CONCRETE_RETURNS=FAIL; source/fixture reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
else:
    if FAIL.exists(): FAIL.unlink()
    LOG.append('LOOSE_JS_CONCRETE_RETURNS=PASS')
