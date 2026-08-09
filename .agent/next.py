from pathlib import Path
import os, shutil, subprocess

TYPES = Path('packages/compiler/src/frontend/types.ts')
ROOT = Path('tests/corpus/3011-dynamic-package-data-alias')
FAIL = Path('WORKSPACE_DATA_ALIAS_FAILURE.txt')
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
        cp = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=2400)
        LOG.extend((cp.stdout or '').splitlines()[-420:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode == 0
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        return False


ok = True
try:
    replace_once(
        TYPES,
        'import { isJsSourceFile, isNodeTypesPath } from "./program.js";\n',
        'import { isJsSourceFile, isNodeTypesPath } from "./program.js";\nimport { workspacePackageOfPath } from "./shared.js";\n',
    )
    replace_once(
        TYPES,
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
  const npmSym = widened.getSymbol();
  const npmDecls = npmSym ? checker.declarationsOf(npmSym) : undefined;''',
        '''  // Types with a RUNTIME identity declared by a shipped .d.ts are
  // island handles under --dynamic. An ERASED type alias is different: it
  // has no runtime object of its own. For PROJECT WORKSPACE packages we let
  // such aliases describe static data (the monorepo contract: a local
  // parameter typed by a sibling package's `type Config = Record<...>` is
  // still ordinary data), while the underlying runtime symbol continues to
  // decide aliases to classes/interfaces. External npm aliases keep the
  // conservative historical JSVAL stance: package declaration surfaces such
  // as TypeBox schema descriptors model package-owned runtime objects and
  // should not be recursively pulled into the native type graph merely
  // because they are spelled with `type`.
  //
  // In short: workspace erased alias -> underlying symbol; external alias ->
  // alias provenance; no alias -> underlying symbol. This separates type
  // ownership from value execution domain without broadening third-party npm.
  const aliasSym = widened.getAliasSymbol();
  const aliasDecls = aliasSym ? checker.declarationsOf(aliasSym) : [];
  const workspaceErasedAlias =
    aliasDecls.length > 0 &&
    aliasDecls.every((d) =>
      ts.isTypeAliasDeclaration(d) &&
      d.getSourceFile().isDeclarationFile &&
      workspacePackageOfPath(d.getSourceFile().fileName) !== null,
    );
  const npmSym = workspaceErasedAlias ? widened.getSymbol() : (aliasSym ?? widened.getSymbol());
  const npmDecls = npmSym ? checker.declarationsOf(npmSym) : undefined;''',
    )

    # Rebuild the corpus as a real mini-workspace plus one external npm
    # control. The resolver recognizes copied workspace packages, while Node
    # resolves the node_modules copy normally.
    shutil.rmtree(ROOT, ignore_errors=True)
    ws_real = ROOT / 'packages/data-alias'
    ws_copy = ROOT / 'node_modules/data-alias'
    ext = ROOT / 'node_modules/external-handle'
    for p in (ws_real, ws_copy, ext): p.mkdir(parents=True, exist_ok=True)

    (ROOT / 'package.json').write_text('''{
  "name": "scriptc-data-alias-workspace-fixture",
  "private": true,
  "type": "module",
  "workspaces": ["packages/*"]
}\n''', encoding='utf-8')

    ws_pkg = '''{
  "name": "data-alias",
  "version": "1.0.0",
  "type": "module",
  "main": "./index.js",
  "types": "./index.d.ts"
}\n'''
    ws_dts = '''export type ConfigValue = string | string[] | undefined;
export type Config = Record<string, ConfigValue>;
export declare function getConfig(): Config;
export declare class Box {
  constructor(value: string);
  value(): string;
}
export type BoxAlias = Box;
'''
    ws_js = '''export function getConfig() {
  return { alpha: "A", list: ["x", "y"], missing: undefined };
}
export class Box {
  constructor(value) { this._value = value; }
  value() { return this._value; }
}
'''
    for p in (ws_real, ws_copy):
        (p / 'package.json').write_text(ws_pkg, encoding='utf-8')
        (p / 'index.d.ts').write_text(ws_dts, encoding='utf-8')
        (p / 'index.js').write_text(ws_js, encoding='utf-8')

    (ext / 'package.json').write_text('''{
  "name": "external-handle",
  "version": "1.0.0",
  "type": "module",
  "main": "./index.js",
  "types": "./index.d.ts"
}\n''', encoding='utf-8')
    (ext / 'index.d.ts').write_text('''export type Handle = { value(): string };
export declare function getHandle(): Handle;
''', encoding='utf-8')
    (ext / 'index.js').write_text('''export function getHandle() {
  return { value() { return "external-dynamic"; } };
}
''', encoding='utf-8')

    (ROOT / 'main.ts').write_text('''// @dynamic
import { Box, getConfig } from "data-alias";
import type { BoxAlias, Config } from "data-alias";
import { getHandle } from "external-handle";

const local: Config = {};
local["save"] = "ctrl+s";
local["open"] = ["ctrl+o", "alt+o"];
local["unset"] = undefined;
for (const [key, value] of Object.entries(local)) {
  if (value === undefined) console.log("local", key, "undefined");
  else if (Array.isArray(value)) console.log("local", key, value.join("|"));
  else console.log("local", key, value);
}

const remote: Config = getConfig();
console.log("remote", remote["alpha"], Array.isArray(remote["list"]));

// Workspace alias -> underlying CLASS still retains runtime identity.
const box: BoxAlias = new Box("boxed");
console.log("box", box.value());

// External npm alias remains a dynamic package-owned object. If external
// aliases were accidentally structuralized, this method-bearing value would
// require an impossible static record/function boundary and the corpus fails.
console.log("external", getHandle().value());
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
    if ok: ok = run(['tar', '-xJf', str(archive), '-C', '/tmp'], env) and ok
env['PATH'] = f"{node_dir / 'bin'}:{env.get('PATH', '')}"
for cmd in [
    ['node', '--version'],
    ['corepack', 'enable'],
    ['corepack', 'prepare', 'pnpm@11.1.3', '--activate'],
    ['pnpm', 'install', '--frozen-lockfile'],
    ['pnpm', 'build'],
    ['pnpm', 'lint'],
]:
    if ok: ok = run(cmd, env) and ok

if ok:
    for sanitized in (False, True):
        test_env = env.copy(); test_env.pop('SCRIPTC_SAN', None)
        if sanitized: test_env['SCRIPTC_SAN'] = '1'
        for harness in ('tests/harness/differential.test.ts', 'tests/harness/llvm-differential.test.ts'):
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3011-dynamic-package-data-alias'], test_env) and ok

if ok:
    npm_env = env.copy(); npm_env.pop('SCRIPTC_TEST_SHARD', None)
    ok = run(['pnpm', 'exec', 'vitest', 'run', 'tests/harness/npm.test.ts'], npm_env) and ok

if ok:
    if FAIL.exists(): FAIL.unlink()
    print('WORKSPACE_DATA_ALIAS=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(TYPES)], check=False)
    # Restore the currently-validated broad-alias fixture/source state; the
    # git checkout above restores TYPES, while corpus rollback uses HEAD.
    subprocess.run(['git', 'checkout', '--', str(ROOT)], check=False)
    LOG.append('WORKSPACE_DATA_ALIAS=FAIL; source/fixture reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('WORKSPACE_DATA_ALIAS=FAIL', flush=True)
