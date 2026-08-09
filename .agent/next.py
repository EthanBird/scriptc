from pathlib import Path
import os, subprocess

NODES = Path('packages/compiler/src/ir/nodes.ts')
CLASSES = Path('packages/compiler/src/frontend/lowering/lower-classes.ts')
CORPUS = Path('tests/corpus/3010-map-function-values.ts')
FAIL = Path('MAP_FUNCTION_VALUES_FAILURE.txt')
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
        NODES,
        '''/** The Map VALUE fence: scalars plus every refcounted kind EXCEPT
 * func/promise/dyn/jsval (and map itself — no maps of maps).
 * Record/object/union values can point back at the map holding them, which
 * is exactly why ref-valued maps are cycle-capable (see the backend's
 * cycle analysis and docs/memory.md). Shared frontend/validator. */''',
        '''/** The Map VALUE fence: scalars plus selected refcounted kinds.
 * Records/objects/unions, promises, and closures can point back at the map
 * holding them, which is exactly why ref-valued maps are cycle-capable (see
 * the backend's cycle fixpoint and trace adapters). dyn/jsval and nested Map
 * values remain outside this native static Map surface. Shared
 * frontend/validator. */''',
    )
    replace_once(
        NODES,
        '''    case "promise":
      return true;
    // A class object''',
        '''    case "promise":
      return true;
    // Function values use stable ScrClosure pointer identity and ordinary
    // strong value ownership. scr_closure_trace_v visits captures, so a
    // registry closure that captures the object/map owning it participates
    // in the same cycle collector as Record<string, () => void> overflow.
    case "func":
      return true;
    // A class object''',
    )
    replace_once(
        CLASSES,
        '''              `(Map values must be number, string, boolean, records, class instances, ` +
              `arrays, promises, or unions of those — not functions, Maps, 'unknown', or 'any')`,''',
        '''              `(Map values must be number, string, boolean, records, class instances, ` +
              `arrays, promises, functions, class values, regexes, supported handles, or unions of supported data values — ` +
              `not nested Maps, 'unknown', or 'any')`,''',
    )
    CORPUS.write_text('''// Function values in Map use ScrClosure strong ownership and tracing.
const handlers = new Map<string, () => void>();
const a = (): void => console.log("handler-a");
const b = (): void => console.log("handler-b");
handlers.set("a", a);
handlers.set("same", a);
handlers.set("b", b);
console.log("map-fn", handlers.size, handlers.get("a") === a, handlers.get("same") === a);
handlers.get("b")!();

// Strong cycle regression: Holder -> Map -> closure -> captured Holder.
// The sanitized/RC-audit lanes must reclaim this at the final cycle sweep.
class Holder {
  readonly handlers = new Map<string, () => void>();

  arm(): void {
    const cb = (): void => {
      console.log("cycle-map-callback", this.handlers.size);
    };
    this.handlers.set("self", cb);
    this.handlers.set("self", cb);
    console.log("cycle-map", this.handlers.size, this.handlers.get("self") === cb);
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
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3010-map-function-values'], test_env) and ok

if ok:
    if FAIL.exists(): FAIL.unlink()
    print('MAP_FUNCTION_VALUES=PASS', flush=True)
else:
    for path in (NODES, CLASSES): subprocess.run(['git', 'checkout', '--', str(path)], check=False)
    if CORPUS.exists(): CORPUS.unlink()
    LOG.append('MAP_FUNCTION_VALUES=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('MAP_FUNCTION_VALUES=FAIL', flush=True)
