from pathlib import Path
import os, subprocess

SOURCE = Path('packages/compiler/src/frontend/types.ts')
FAIL = Path('HEADER_CANONICALIZATION_FAILURE.txt')
LOG: list[str] = []


def replace_once(old: str, new: str) -> None:
    text = SOURCE.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'expected one anchor, found {count}: {old[:100]!r}')
    SOURCE.write_text(text.replace(old, new, 1), encoding='utf-8')


def run(args: list[str], env: dict[str, str]) -> bool:
    LOG.append('$ ' + ' '.join(args))
    try:
        cp = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
        LOG.extend((cp.stdout or '').splitlines()[-260:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode == 0
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        return False


ok = True
try:
    replace_once(
        '''  if (indexValue?.kind === "union") {
    const slotDef = ctx.unions.get(indexValue.unionId);''',
        '''  // Do not canonicalize a declaration-free Record<string, V> merely
  // because V contains string[]. Header interfaces/spread results carry
  // declared well-known header properties; a pure Record does not. Without
  // this guard, Record<string, string | string[] | undefined> was silently
  // widened with a number arm from OutgoingHttpHeaders.
  const headerProps = checker.getPropertiesOfType(widened);
  if (indexValue?.kind === "union" && headerProps.length > 0) {
    const slotDef = ctx.unions.get(indexValue.unionId);''',
    )
    replace_once(
        '      if (checker.getPropertiesOfType(widened).every((p) => fits(mapType(checker.getTypeOfSymbol(p), ctx)))) {',
        '      if (headerProps.every((p) => fits(mapType(checker.getTypeOfSymbol(p), ctx)))) {',
    )
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
    pattern = '3003-object-entries-forof|header'
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
    print('HEADER_CANONICALIZATION=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(SOURCE)], check=False)
    LOG.append('HEADER_CANONICALIZATION=FAIL; source reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('HEADER_CANONICALIZATION=FAIL', flush=True)
