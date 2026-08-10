from pathlib import Path
import os, re, shutil, subprocess, traceback

OUT = Path('PRIME_LOOSE_JS_RESULT.txt')
LOG = []
ENV = os.environ.copy()

def run(args, cwd=None, timeout=1800):
    LOG.append('$ ' + ' '.join(map(str, args)))
    try:
        cp = subprocess.run(args, cwd=cwd, env=ENV, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        out = cp.stdout or ''
        LOG.extend(out.splitlines()[-260:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode, out
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        LOG.extend(traceback.format_exc().splitlines())
        return 127, ''

rc, _ = run(['pnpm', 'build'])
if rc != 0:
    OUT.write_text('\n'.join(['prime_bundle_probe=compiler-build-failed', *LOG]) + '\n', encoding='utf-8')
    raise SystemExit(0)

prime = Path('/tmp/prime-agent-current-frontier')
if prime.exists():
    shutil.rmtree(prime)
rc, _ = run(['git', 'clone', '--depth', '1', 'https://github.com/EthanBird/prime-agent.git', str(prime)], timeout=300)
if rc == 0:
    rc, _ = run(['npm', 'ci'], cwd=prime, timeout=1200)
if rc == 0:
    rc, _ = run(['npm', 'run', 'build'], cwd=prime, timeout=1200)

build_status = 126
smoke_status = 125
build_out = ''
smoke_out = 'Prime preparation failed'
out_path = '/tmp/prime-agent-scriptc-current'
if rc == 0:
    try:
        Path(out_path).unlink()
    except FileNotFoundError:
        pass
    cli = str(Path.cwd() / 'packages/cli/dist/main.js')
    build_status, build_out = run([
        'node', cli, 'build', 'packages/coding-agent/dist/bundle/cli.js',
        '--dynamic', '--loose-js', '-o', out_path,
    ], cwd=prime, timeout=1200)
    if build_status == 0 and Path(out_path).exists():
        smoke_status, smoke_out = run(['timeout', '20s', out_path, '--help'], cwd=prime, timeout=30)
    else:
        smoke_out = 'build did not produce executable'

diags = [line for line in build_out.splitlines() if re.search(r'\bSC\d{4}:', line)]
report = [
    'prime_bundle_probe=current branch',
    f'build_status={build_status}',
    f'smoke_status={smoke_status}',
    f'diagnostic_count={len(diags)}',
    '--- diagnostics ---',
    *diags,
    '--- smoke tail ---',
    *smoke_out.splitlines()[-120:],
]
OUT.write_text('\n'.join(report) + '\n', encoding='utf-8')
