from pathlib import Path
import os, subprocess

TYPES = Path('packages/compiler/src/frontend/types.ts')
ROOT = Path('tests/corpus/3011-dynamic-package-data-alias')
MAIN = ROOT / 'main.ts'
PKG = ROOT / 'node_modules/data-alias'
FAIL = Path('DYNAMIC_DATA_ALIAS_FAILURE.txt')
LOG: list[str] = []


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected one anchor, found {count}: {old[:180]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def run(args: list[str], env: dict[str, str]) -> bool:
    LOG.append('$ ' + ' '.join(args))
    try:
        cp = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
        LOG.extend((cp.stdout or '').splitlines()[-360:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode == 0
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        return False


ok = True
try:
    replace_once(
        TYPES,
        '''  // Types DECLARED by a shipped .d.ts — an npm package's, or a LOCAL
  // declaration file describing sibling JS the program loads dynamically
  // (an Emscripten factory's .d.mts): the .d.ts is trusted as the type
  // surface, but the values behind it live in the embedded engine — under
  // --dynamic they are island handles (jsval), and every operation on them
  // rides the engine ops with validated exits at typed boundaries.
  // Primitives/arrays/etc. REACHED THROUGH such types keep their
  // structural mapping (they were handled above or recurse normally); this
  // rule fires only when the type's own identity is declaration-file-
  // declared — interfaces, classes, type literals, and aliases from the
  // .d.ts. The standard library's declaration files are carved out (their
  // surfaces have static lowerings), as are declarations explicitly mapped
  // by --external-types: those describe project-owned structural data while
  // the Lowerer fences their imported runtime bindings. The program's own
  // compiled modules are never declaration files. Without --dynamic this
  // stays unmapped; badType reports the per-package requires-dynamic
  // diagnostic for node_modules types and the generic story otherwise.
  const npmSym = widened.getAliasSymbol() ?? widened.getSymbol();''',
        '''  // Types with a RUNTIME identity declared by a shipped .d.ts — an npm
  // package's, or a LOCAL declaration file describing sibling JS the
  // program loads dynamically — are island handles under --dynamic. The
  // runtime provenance must come from the UNDERLYING type symbol, however,
  // not from an erased TypeScript alias name. A declaration-file alias such
  // as `type Config = Record<string, string>` has no runtime object of its
  // own: local Config values are ordinary static data, and package-produced
  // Config values can cross the island through the normal validated data
  // boundary. Conversely `type X = PackageClass` still has the class as its
  // underlying symbol and remains a jsval handle. This separation of TYPE
  // provenance from VALUE execution domain is essential for monorepos whose
  // workspace packages publish structural aliases in dist/*.d.ts.
  //
  // Primitives/arrays/etc. reached through these types already structurally
  // map above/below. Standard-library declarations and --external-types are
  // carved out exactly as before. Without --dynamic, runtime-identity .d.ts
  // symbols remain unmapped and produce the package-specific diagnostic.
  const npmSym = widened.getSymbol();''',
    )

    PKG.mkdir(parents=True, exist_ok=True)
    (PKG / 'package.json').write_text('''{
  "name": "data-alias",
  "version": "1.0.0",
  "type": "module",
  "main": "./index.js",
  "types": "./index.d.ts"
}\n''', encoding='utf-8')
    (PKG / 'index.d.ts').write_text('''export type ConfigValue = string | string[] | undefined;
export type Config = Record<string, ConfigValue>;

export declare function getConfig(): Config;

export declare class Box {
  constructor(value: string);
  value(): string;
}
export type BoxAlias = Box;
''', encoding='utf-8')
    (PKG / 'index.js').write_text('''export function getConfig() {
  return { alpha: "A", list: ["x", "y"], missing: undefined };
}

export class Box {
  constructor(value) { this._value = value; }
  value() { return this._value; }
}
''', encoding='utf-8')
    MAIN.write_text('''// @dynamic
import { Box, getConfig } from "data-alias";
import type { BoxAlias, Config } from "data-alias";

const local: Config = {};
local["save"] = "ctrl+s";
local["open"] = ["ctrl+o", "alt+o"];
local["unset"] = undefined;
for (const [key, value] of Object.entries(local)) {
  if (value === undefined) console.log("local", key, "undefined");
  else if (Array.isArray(value)) console.log("local", key, value.join("|"));
  else console.log("local", key, value);
}

// The package returns a JS-engine object, but Config is pure data: the
// declared alias may exit through the validated static record boundary.
const remote: Config = getConfig();
console.log("remote", remote["alpha"], Array.isArray(remote["list"]));

// An alias to a package CLASS still follows the underlying runtime class
// identity and stays in the dynamic engine rather than becoming a record.
const box: BoxAlias = new Box("boxed");
console.log("box", box.value());
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
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3011-dynamic-package-data-alias'], test_env) and ok

# This touches the central npm/type-provenance rule: run the full package
# harness, not only the new corpus. The npm harness is already case-sharded
# in matrix CI; here an unsharded focused task intentionally exercises all.
if ok:
    npm_env = env.copy()
    npm_env.pop('SCRIPTC_TEST_SHARD', None)
    ok = run(['pnpm', 'exec', 'vitest', 'run', 'tests/harness/npm.test.ts'], npm_env) and ok

if ok:
    if FAIL.exists(): FAIL.unlink()
    print('DYNAMIC_DATA_ALIAS=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(TYPES)], check=False)
    if ROOT.exists():
        import shutil
        shutil.rmtree(ROOT)
    LOG.append('DYNAMIC_DATA_ALIAS=FAIL; source/fixture reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('DYNAMIC_DATA_ALIAS=FAIL', flush=True)
