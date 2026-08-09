from pathlib import Path
import os
import subprocess

NODE_VERSION = Path('.node-version').read_text(encoding='utf-8').strip()
NODE_DIR = Path(f'/tmp/node-v{NODE_VERSION}-linux-x64')
ENV = os.environ.copy()
LOG = []


def run(args, *, env=None):
    LOG.append('$ ' + ' '.join(args))
    try:
        cp = subprocess.run(args, env=env or ENV, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
        LOG.append(cp.stdout or '')
        LOG.append(f'[exit {cp.returncode}]\n')
        return cp.returncode == 0
    except Exception as e:
        LOG.append(f'[exception {type(e).__name__}: {e}]\n')
        return False


ok = True
if not (NODE_DIR / 'bin/node').exists():
    archive = Path(f'/tmp/node-v{NODE_VERSION}-linux-x64.tar.xz')
    ok = run(['curl', '-fsSL', f'https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz', '-o', str(archive)]) and ok
    if ok:
        ok = run(['tar', '-xJf', str(archive), '-C', '/tmp']) and ok
ENV['PATH'] = f"{NODE_DIR / 'bin'}:{ENV.get('PATH', '')}"
if ok: ok = run(['node', '--version']) and ok
if ok: ok = run(['corepack', 'enable']) and ok
if ok: ok = run(['corepack', 'prepare', 'pnpm@11.1.3', '--activate']) and ok
if ok: ok = run(['pnpm', '--version']) and ok
if ok: ok = run(['pnpm', 'install', '--frozen-lockfile']) and ok
if ok: ok = run(['pnpm', 'build']) and ok
if ok: ok = run(['pnpm', 'lint']) and ok

if ok:
    for san in (False, True):
        e = ENV.copy()
        if san:
            e['SCRIPTC_SAN'] = '1'
        else:
            e.pop('SCRIPTC_SAN', None)
        label = 'sanitized' if san else 'plain'
        LOG.append(f'=== C differential: {label} ===\n')
        this = run(['pnpm', 'exec', 'vitest', 'run', 'tests/harness/differential.test.ts', '-t', '3003-object-entries-forof'], env=e)
        ok = this and ok
        LOG.append(f'=== LLVM differential: {label} ===\n')
        this = run(['pnpm', 'exec', 'vitest', 'run', 'tests/harness/llvm-differential.test.ts', '-t', '3003-object-entries-forof'], env=e)
        ok = this and ok

LOG.append('OBJECT_ENTRIES_VALIDATION=' + ('PASS' if ok else 'FAIL') + '\n')
Path('.agent/object-entries-validation.log').write_text('\n'.join(LOG), encoding='utf-8')
print('validation captured:', 'PASS' if ok else 'FAIL')
