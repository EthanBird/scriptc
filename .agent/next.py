from pathlib import Path
import os, subprocess

FILES = {
    'nodes': Path('packages/compiler/src/ir/nodes.ts'),
    'surfaces': Path('packages/compiler/src/frontend/lowering/surfaces.ts'),
    'builtins': Path('packages/compiler/src/frontend/lowering/lower-builtins.ts'),
    'fallback': Path('packages/compiler/ambient/scriptc-node-fallback.d.ts'),
    'runtime_h': Path('packages/runtime/src/scr_runtime.h'),
    'runtime_c': Path('packages/runtime/src/scr_async.c'),
    'llvm': Path('packages/compiler/src/backend/llvm/emitter.ts'),
}
CORPUS = Path('tests/corpus/3008-fsp-access.ts')
FAIL = Path('FSP_ACCESS_FAILURE.txt')
LOG: list[str] = []


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected one anchor, found {count}: {old[:150]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def run(args: list[str], env: dict[str, str]) -> bool:
    LOG.append('$ ' + ' '.join(args))
    try:
        cp = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
        LOG.extend((cp.stdout or '').splitlines()[-320:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode == 0
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        return False


ok = True
try:
    replace_once(
        FILES['nodes'],
        '  | "fsp.writeFile"\n  | "fsp.mkdir"',
        '  | "fsp.writeFile"\n  | "fsp.access"\n  | "fsp.mkdir"',
    )
    replace_once(
        FILES['surfaces'],
        '    writeFile: { fn: "fsp.writeFile", params: [STRING, STRING], result: { kind: "promise", inner: VOID } },\n    mkdir:',
        '    writeFile: { fn: "fsp.writeFile", params: [STRING, STRING], result: { kind: "promise", inner: VOID } },\n    // access(path, mode?) is special-cased to complete omitted mode to F_OK (0).\n    access: { fn: "fsp.access", params: [STRING, F64], result: { kind: "promise", inner: VOID } },\n    mkdir:',
    )
    replace_once(
        FILES['builtins'],
        '''    // fs.promises.writeFile(path, string, "utf8" | "utf-8"):
    // the third argument only selects the encoding the existing''',
        '''    // fs.promises.access(path, mode?): accessSync's promise twin.
    // Run the same permission probe, but the runtime converts a pending fs
    // exception into a rejected Promise before returning to compiled code.
    if (bi.module === "fs/promises" && bi.member === "access") {
      if (expr.arguments.length < 1 || expr.arguments.length > 2) {
        L.noLowering(`fs.promises.access with ${expr.arguments.length} arguments`, expr);
      }
      const path = L.lowerExprExpecting(expr.arguments[0]!, STRING);
      const mode: IrExpr = expr.arguments[1]
        ? L.lowerExprExpecting(expr.arguments[1], F64)
        : { kind: "numLit", value: 0, type: F64, loc };
      const type: IrType = { kind: "promise", inner: VOID };
      return { kind: "libCall", fn: "fsp.access", args: [path, mode], type, loc };
    }
    // fs.promises.writeFile(path, string, "utf8" | "utf-8"):
    // the third argument only selects the encoding the existing''',
    )
    replace_once(
        FILES['fallback'],
        '  export function writeFile(path: string, data: string): Promise<void>;\n',
        '  export function access(path: string, mode?: number): Promise<void>;\n  export function writeFile(path: string, data: string): Promise<void>;\n',
    )
    replace_once(
        FILES['runtime_h'],
        'ScrPromise *scr_fsp_write_file(ScrStr *path, ScrStr *data);\nScrPromise *scr_fsp_mkdir',
        'ScrPromise *scr_fsp_write_file(ScrStr *path, ScrStr *data);\nScrPromise *scr_fsp_access(ScrStr *path, double mode);\nScrPromise *scr_fsp_mkdir',
    )
    replace_once(
        FILES['runtime_c'],
        '''ScrPromise *scr_fsp_write_file(ScrStr *path, ScrStr *data) {
  scr_fs_write_file(path, data);
  return scr_promise_settled_void();
}

ScrPromise *scr_fsp_mkdir''',
        '''ScrPromise *scr_fsp_write_file(ScrStr *path, ScrStr *data) {
  scr_fs_write_file(path, data);
  return scr_promise_settled_void();
}

ScrPromise *scr_fsp_access(ScrStr *path, double mode) {
  scr_fs_access(path, mode);
  return scr_promise_settled_void();
}

ScrPromise *scr_fsp_mkdir''',
    )
    replace_once(
        FILES['llvm'],
        '  "fsp.writeFile": "scr_fsp_write_file",\n  "fsp.mkdir":',
        '  "fsp.writeFile": "scr_fsp_write_file",\n  "fsp.access": "scr_fsp_access",\n  "fsp.mkdir":',
    )
    CORPUS.write_text('''import { access } from "node:fs/promises";

await access("package.json");
await access("package.json", 4);
console.log("fsp access ok");

try {
  await access("scriptc-3008-definitely-missing-file", 4);
  console.log("unexpected access success");
} catch {
  console.log("fsp access rejected");
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
    for sanitized in (False, True):
        test_env = env.copy()
        test_env.pop('SCRIPTC_SAN', None)
        if sanitized:
            test_env['SCRIPTC_SAN'] = '1'
        for harness in ('tests/harness/differential.test.ts', 'tests/harness/llvm-differential.test.ts'):
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3008-fsp-access'], test_env) and ok

if ok:
    if FAIL.exists():
        FAIL.unlink()
    print('FSP_ACCESS=PASS', flush=True)
else:
    for path in FILES.values():
        subprocess.run(['git', 'checkout', '--', str(path)], check=False)
    if CORPUS.exists():
        CORPUS.unlink()
    LOG.append('FSP_ACCESS=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('FSP_ACCESS=FAIL', flush=True)
