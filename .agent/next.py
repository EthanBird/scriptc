from pathlib import Path
import os
import subprocess

NODE_VERSION = Path('.node-version').read_text(encoding='utf-8').strip()
NODE_DIR = Path(f'/tmp/node-v{NODE_VERSION}-linux-x64')
ENV = os.environ.copy()


def run(args, *, env=None):
    print('+', ' '.join(args), flush=True)
    subprocess.run(args, check=True, env=env or ENV)


if not (NODE_DIR / 'bin/node').exists():
    archive = Path(f'/tmp/node-v{NODE_VERSION}-linux-x64.tar.xz')
    run(['curl', '-fsSL', f'https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz', '-o', str(archive)])
    run(['tar', '-xJf', str(archive), '-C', '/tmp'])
ENV['PATH'] = f"{NODE_DIR / 'bin'}:{ENV.get('PATH', '')}"
run(['node', '--version'])
run(['corepack', 'enable'])
run(['corepack', 'prepare', 'pnpm@11.1.3', '--activate'])
run(['pnpm', '--version'])
run(['pnpm', 'install', '--frozen-lockfile'])
run(['pnpm', 'build'])
run(['pnpm', 'lint'])

for san in (False, True):
    e = ENV.copy()
    if san:
        e['SCRIPTC_SAN'] = '1'
    else:
        e.pop('SCRIPTC_SAN', None)
    label = 'sanitized' if san else 'plain'
    print(f'=== C differential: {label} ===', flush=True)
    run(['pnpm', 'exec', 'vitest', 'run', 'tests/harness/differential.test.ts', '-t', '3003-object-entries-forof'], env=e)
    print(f'=== LLVM differential: {label} ===', flush=True)
    run(['pnpm', 'exec', 'vitest', 'run', 'tests/harness/llvm-differential.test.ts', '-t', '3003-object-entries-forof'], env=e)

print('OBJECT_ENTRIES_VALIDATION_OK', flush=True)
