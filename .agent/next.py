from pathlib import Path
import os, subprocess

SOURCE = Path('packages/compiler/src/frontend/lowering/lower-containers.ts')
CORPUS = Path('tests/corpus/3006-object-entries-template-keyid.ts')
FAIL = Path('OBJECT_ENTRIES_KEYID_FAILURE.txt')
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
        LOG.extend((cp.stdout or '').splitlines()[-280:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode == 0
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        return False


ok = True
try:
    replace_once(
        '''    const els = decl.name.elements as readonly (ts.BindingElement & { name: ts.Identifier })[];
    const keyTsT = L.mapTypeOf(L.checker.getTypeAtLocation(els[0]!.name));
    const valueTsT = L.mapTypeOf(L.checker.getTypeAtLocation(els[1]!.name));
    if (keyTsT?.kind !== "string" || !valueTsT || !typeEquals(valueTsT, shape.indexValue)) return null;

    const loc = locOf(stmt);''',
        '''    const els = decl.name.elements as readonly (ts.BindingElement & { name: ts.Identifier })[];
    // The stdlib Object.entries overload over a pure string index signature
    // guarantees `[string, V]` regardless of how richly V is spelled in the
    // checker (template-literal unions such as Prime's KeyId can be too large
    // or contextual to map a second time at the binding node). The source
    // record already mapped V successfully as shape.indexValue, so that is
    // the one authoritative runtime representation for the yielded value.
    // Do not require an independent checker->IR remap of the two binding
    // identifiers here; TypeScript has already typechecked the destructure.

    const loc = locOf(stmt);''',
    )
    CORPUS.write_text(r'''type Letter = "a" | "b" | "c";
type Modifier = "ctrl" | "alt";
type KeyId = Letter | `${Modifier}+${Letter}`;
type KeybindingsConfig = Record<string, KeyId | KeyId[] | undefined>;

const resolved: KeybindingsConfig = {};
resolved["submit"] = "ctrl+a";
resolved["copy"] = ["a", "alt+b"];
resolved["unset"] = undefined;

for (const [keybinding, keys] of Object.entries(resolved)) {
  if (keys === undefined) {
    console.log(keybinding, "unset");
    continue;
  }
  const list = Array.isArray(keys) ? keys : [keys];
  console.log(keybinding, list.join("|"));
}
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
    pattern = '3003-object-entries-forof|3006-object-entries-template-keyid'
    for sanitized in (False, True):
        test_env = env.copy()
        test_env.pop('SCRIPTC_SAN', None)
        if sanitized:
            test_env['SCRIPTC_SAN'] = '1'
        for harness in ('tests/harness/differential.test.ts', 'tests/harness/llvm-differential.test.ts'):
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', pattern], test_env) and ok

if ok:
    if FAIL.exists():
        FAIL.unlink()
    print('OBJECT_ENTRIES_KEYID=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(SOURCE)], check=False)
    if CORPUS.exists():
        CORPUS.unlink()
    LOG.append('OBJECT_ENTRIES_KEYID=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('OBJECT_ENTRIES_KEYID=FAIL', flush=True)
