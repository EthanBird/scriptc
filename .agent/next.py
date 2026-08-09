from pathlib import Path
import os, subprocess

LOWER = Path('packages/compiler/src/frontend/lowering/lower-builtins.ts')
FALLBACK = Path('packages/compiler/ambient/scriptc-node-fallback.d.ts')
CORPUS = Path('tests/corpus/3005-fsp-writefile-utf8.ts')
TMP = Path('tmp-3005-fsp-writefile-utf8.txt')
FAIL = Path('FSP_WRITEFILE_UTF8_FAILURE.txt')
LOG: list[str] = []


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected one anchor, found {count}: {old[:120]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


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
        FALLBACK,
        '  export function writeFile(path: string, data: string): Promise<void>;\n',
        '  export function writeFile(path: string, data: string): Promise<void>;\n'
        '  /* The explicit UTF-8 spelling is semantically the same write the\n'
        '   * runtime performs; other encodings/options remain declared only\n'
        '   * by @types/node and fence at lowering. */\n'
        '  export function writeFile(path: string, data: string, encoding: "utf8" | "utf-8"): Promise<void>;\n',
    )
    replace_once(
        LOWER,
        '    if (bi.module === "fs" && bi.member === "writeFileSync" && expr.arguments.length === 2) {',
        '''    // fs.promises.writeFile(path, string, "utf8" | "utf-8"):
    // the third argument only selects the encoding the existing
    // fsp.writeFile runtime already writes. Prove the literal encoding and
    // string payload, then reuse the two-argument runtime ABI. Everything
    // else keeps the normal options/arity fence.
    if (bi.module === "fs/promises" && bi.member === "writeFile" && expr.arguments.length === 3) {
      const encNode = expr.arguments[2]!;
      const enc = L.typeOf(encNode);
      if (
        enc.isStringLiteralType() &&
        (enc.value === "utf8" || enc.value === "utf-8") &&
        L.mapTypeOf(L.typeOf(expr.arguments[1]!))?.kind === "string"
      ) {
        const path = L.lowerExprExpecting(expr.arguments[0]!, STRING);
        const data = L.lowerExprExpecting(expr.arguments[1]!, STRING);
        const type: IrType = { kind: "promise", inner: VOID };
        return { kind: "libCall", fn: "fsp.writeFile", args: [path, data], type, loc };
      }
      L.noLowering(
        "fs.promises.writeFile with 3 arguments",
        encNode,
        'the supported three-argument form is writeFile(path, stringData, "utf8" | "utf-8")',
      );
    }
    if (bi.module === "fs" && bi.member === "writeFileSync" && expr.arguments.length === 2) {''',
    )
    CORPUS.write_text('''import { writeFile } from "node:fs/promises";

await writeFile("tmp-3005-fsp-writefile-utf8.txt", "héllo ScriptC\\n", "utf-8");
console.log("fsp writeFile utf-8 ok");
await writeFile("tmp-3005-fsp-writefile-utf8.txt", "utf8 alias\\n", "utf8");
console.log("fsp writeFile utf8 ok");
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
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3005-fsp-writefile-utf8'], test_env) and ok

# Corpus executions intentionally exercise a filesystem side effect. Never
# let the runner scratch file become repository state.
if TMP.exists():
    TMP.unlink()

if ok:
    if FAIL.exists():
        FAIL.unlink()
    print('FSP_WRITEFILE_UTF8=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(LOWER), str(FALLBACK)], check=False)
    if CORPUS.exists():
        CORPUS.unlink()
    LOG.append('FSP_WRITEFILE_UTF8=FAIL; source/declarations/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('FSP_WRITEFILE_UTF8=FAIL', flush=True)
