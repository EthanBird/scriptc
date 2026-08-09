from pathlib import Path
import os, subprocess

SOURCE = Path('packages/compiler/src/frontend/lowering/lower-containers.ts')
CORPUS = Path('tests/corpus/3009-array-from-set.ts')
FAIL = Path('ARRAY_FROM_SET_FAILURE.txt')
LOG: list[str] = []


def replace_once(old: str, new: str) -> None:
    text = SOURCE.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'expected one anchor, found {count}: {old[:140]!r}')
    SOURCE.write_text(text.replace(old, new, 1), encoding='utf-8')


def run(args: list[str], env: dict[str, str]) -> bool:
    LOG.append('$ ' + ' '.join(args))
    try:
        cp = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
        LOG.extend((cp.stdout or '').splitlines()[-300:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode == 0
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        return False


ok = True
try:
    replace_once(
        '''    // `Array.from(s)` on a STRING: the string iterator's code-point walk
    // into a fresh string[] (astral characters stay whole, where a
    // charAt/index walk would truncate the surrogate halves) — the same
    // interned helper `[...s]` lowers through.
    if (args.length === 1 && !ts.isObjectLiteralExpression(args[0]!)) {
      const src = L.lowerExpr(args[0]!);
      if (src.type.kind === "string") return strCharsCall(L, src, loc);
      L.noLowering(
        "Array.from with this argument shape",
        call,
        "Array.from({ length: n }, (v, i) => ...) and Array.from(aString) are the lowered " +
          "forms — copy arrays with [...a] and drain Map/Set iterators where they are made",
      );
    }''',
        '''    // `Array.from(s)` on a STRING: the string iterator's code-point walk
    // into a fresh string[] (astral characters stay whole, where a
    // charAt/index walk would truncate the surrogate halves) — the same
    // interned helper `[...s]` lowers through. A Set<T> is the other direct
    // iterable with a native snapshot operation: toArray drains its current
    // insertion order into a fresh T[] (later Set mutations cannot affect
    // the returned Array, exactly Array.from's materialization semantics).
    if (args.length === 1 && !ts.isObjectLiteralExpression(args[0]!)) {
      const src = L.lowerExpr(args[0]!);
      if (src.type.kind === "string") return strCharsCall(L, src, loc);
      if (src.type.kind === "set") {
        const resultT = L.mapTypeOf(L.typeOf(call));
        if (resultT?.kind !== "array" || !typeEquals(resultT.elem, src.type.elem)) {
          L.badType(call, L.typeOf(call));
        }
        return {
          kind: "setIntrinsic",
          method: "toArray",
          receiver: src,
          args: [],
          type: arrayOf(src.type.elem),
          loc,
        };
      }
      L.noLowering(
        "Array.from with this argument shape",
        call,
        "Array.from({ length: n }, (v, i) => ...), Array.from(aString), and Array.from(aSet) " +
          "are the lowered forms — copy arrays with [...a] and keep general iterator objects explicit",
      );
    }''',
    )
    CORPUS.write_text('''const values = new Set<string>();
values.add("beta");
values.add("alpha");
values.add("beta");

const first = Array.from(values);
console.log("first", first.length, first.join("|"));
values.add("gamma");
console.log("snapshot", first.join("|"));
console.log("second", Array.from(values).join("|"));
''', encoding='utf-8')
except Exception as exc:
    LOG.append(f'PATCH FAILURE: {type(exc).__name__}: {exc}')
    ok = False

version = Path('.node-version').read_text(encoding='utf-8').strip()
node_dir = Path(f'/tmp/node-v{version}-linux-x64')
env = os.environ.copy()
if ok and not (node_dir / 'bin/node').exists():
    archive = Path(f'/tmp/node-v{version}-linux-x64.tar.xz')
    ok = run(['curl', '-fsSL', f'https://nodejs.org/dist/v{version}/node-v{version}-linux-x64.tar.xz', '-o', str(archive)], env) and ok
    if ok:
        ok = run(['tar', '-xJf', str(archive), '-C', '/tmp'], env) and ok
env['PATH'] = f"{node_dir / 'bin'}:{env.get('PATH', '')}"
for cmd in [
    ['node', '--version'],
    ['corepack', 'enable'],
    ['corepack', 'prepare', 'pnpm@11.1.3', '--activate'],
    ['pnpm', 'install', '--frozen-lockfile'],
    ['pnpm', 'build'],
    ['pnpm', 'lint'],
]:
    if ok:
        ok = run(cmd, env) and ok

if ok:
    for sanitized in (False, True):
        test_env = env.copy()
        test_env.pop('SCRIPTC_SAN', None)
        if sanitized:
            test_env['SCRIPTC_SAN'] = '1'
        for harness in ('tests/harness/differential.test.ts', 'tests/harness/llvm-differential.test.ts'):
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3009-array-from-set'], test_env) and ok

if ok:
    if FAIL.exists(): FAIL.unlink()
    print('ARRAY_FROM_SET=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(SOURCE)], check=False)
    if CORPUS.exists(): CORPUS.unlink()
    LOG.append('ARRAY_FROM_SET=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('ARRAY_FROM_SET=FAIL', flush=True)
