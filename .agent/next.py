from pathlib import Path
import os, subprocess

NODES = Path('packages/compiler/src/ir/nodes.ts')
C_TYPES = Path('packages/compiler/src/backend/emission/emit-types.ts')
LL_TYPES = Path('packages/compiler/src/backend/llvm/shapes.ts')
CORPUS = Path('tests/corpus/3007-set-function-identity.ts')
FAIL = Path('SET_FUNCTION_IDENTITY_FAILURE.txt')
LOG: list[str] = []


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected one anchor, found {count}: {old[:140]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def run(args: list[str], env: dict[str, str]) -> bool:
    LOG.append('$ ' + ' '.join(args))
    try:
        cp = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
        LOG.extend((cp.stdout or '').splitlines()[-300:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode == 0
    except Exception as exc:
        LOG.append(f'[exception {type(exc).__name__}: {exc}]')
        return False


ok = True
try:
    replace_once(
        NODES,
        '''/** The Set ELEMENT fence — Map's scalar key fence plus values whose
 * JavaScript object identity is exactly their stable runtime pointer.
 * class instances and promises need strong-key cycle tracing (a member can
 * point back at the Set); server handles and symbols are acyclic identity
 * values. Structural records/unions and dyn/jsval wrappers stay fenced:
 * their lowering may copy/rebox, so pointer identity is not yet a proof of
 * JavaScript identity. */''',
        '''/** The Set ELEMENT fence — Map's scalar key fence plus values whose
 * JavaScript object identity is exactly their stable runtime pointer.
 * Class instances, promises, and closures need strong-key cycle tracing (a
 * member/capture can point back at the Set); server handles and symbols are
 * acyclic identity values. Structural records/unions and dyn/jsval wrappers
 * stay fenced: their lowering may copy/rebox, so pointer identity is not yet
 * a proof of JavaScript identity. */''',
    )
    replace_once(
        NODES,
        '''    t.kind === "object" ||
    t.kind === "promise" ||
    t.kind === "netServer" ||''',
        '''    t.kind === "object" ||
    t.kind === "promise" ||
    t.kind === "func" ||
    t.kind === "netServer" ||''',
    )
    replace_once(
        C_TYPES,
        '''    key.kind === "netServer" || key.kind === "symbol" ||
    key.kind === "object" || key.kind === "promise"
  ) return "ref";''',
        '''    key.kind === "netServer" || key.kind === "symbol" ||
    key.kind === "object" || key.kind === "promise" || key.kind === "func"
  ) return "ref";''',
    )
    replace_once(
        LL_TYPES,
        '''  if (key.kind === "netServer") return "ref"; // handle identity (Set<Server>)
  if (key.kind === "object" || key.kind === "promise") return "ref";''',
        '''  if (key.kind === "netServer") return "ref"; // handle identity (Set<Server>)
  if (key.kind === "object" || key.kind === "promise" || key.kind === "func") return "ref";''',
    )
    CORPUS.write_text('''// Closures have stable runtime pointer identity. A Set stores them as REF
// keys with closure retain/release and trace callbacks.
const a = (): void => console.log("same-body");
const b = (): void => console.log("same-body");
const ids = new Set<() => void>();
ids.add(a);
ids.add(a);
ids.add(b);
console.log("identity", ids.size, ids.has(a), ids.has(b));
a();

// Strong cycle regression: Holder -> Set -> closure -> captured Holder.
// The sanitized/RC-audit lanes must reclaim this at the final cycle sweep.
class Holder {
  readonly callbacks = new Set<() => void>();

  arm(): void {
    const cb = (): void => {
      console.log("cycle-callback", this.callbacks.size);
    };
    this.callbacks.add(cb);
    this.callbacks.add(cb);
    console.log("cycle-set", this.callbacks.size, this.callbacks.has(cb));
    cb();
  }
}

function makeCycle(): void {
  const holder = new Holder();
  holder.arm();
}
makeCycle();
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
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3007-set-function-identity'], test_env) and ok

if ok:
    if FAIL.exists():
        FAIL.unlink()
    print('SET_FUNCTION_IDENTITY=PASS', flush=True)
else:
    for path in (NODES, C_TYPES, LL_TYPES):
        subprocess.run(['git', 'checkout', '--', str(path)], check=False)
    if CORPUS.exists():
        CORPUS.unlink()
    LOG.append('SET_FUNCTION_IDENTITY=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('SET_FUNCTION_IDENTITY=FAIL', flush=True)
