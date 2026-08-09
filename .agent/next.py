from pathlib import Path
import os, subprocess

SOURCE = Path('packages/compiler/src/frontend/lowering/lower-builtins.ts')
CORPUS = Path('tests/corpus/3005-fsp-writefile-utf8.ts')
FAIL = Path('FSP_WRITEFILE_UTF8_FAILURE.txt')
LOG: list[str] = []


def replace_once(old: str, new: str) -> None:
    text = SOURCE.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'expected one anchor, found {count}: {old[:120]!r}')
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
        '''    if (bi.module === "fs" && bi.member === "writeFileSync" && expr.arguments.length === 2) {''',
        '''    // fs.promises.writeFile(path, string, "utf8" | "utf-8"):
    // the third argument only selects the decoder the existing fsp.writeFile
    // runtime already implements. Drop that semantic no-op after proving
    // both the literal encoding and string data; every other options/encoding
    // form keeps the normal arity fence instead of silently changing bytes.
    if (bi.module === "fs/promises" && bi.member === "writeFile" && expr.arguments.length === 3) {
      const encNode = expr.arguments[2]!;
      const enc = L.typeOf(encNode);
      const stringData = L.mapTypeOf(L.typeOf(expr.arguments[1]!))?.kind === "string";
      if (
        enc.isStringLiteralType() &&
        (enc.value === "utf8" || enc.value === "utf-8") &&
        stringData
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

// Node and the compiled oracle may run concurrently; both write identical
// bytes to this ignored tmp-* path, so the test observes promise settlement
// rather than racing cleanup/readback.
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

if ok:
    if FAIL.exists():
        FAIL.unlink()
    print('FSP_WRITEFILE_UTF8=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(SOURCE)], check=False)
    if CORPUS.exists():
        CORPUS.unlink()
    LOG.append('FSP_WRITEFILE_UTF8=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('FSP_WRITEFILE_UTF8=FAIL', flush=True)
