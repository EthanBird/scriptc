from pathlib import Path
import os, subprocess

SOURCE = Path('packages/compiler/src/frontend/lowering/lower-classes.ts')
CORPUS = Path('tests/corpus/3004-set-readonly-tuple.ts')
FAIL = Path('SET_READONLY_TUPLE_FAILURE.txt')
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
        '''              // Any other lowered kind falls through to the named fence
              // below — never a mistyped seed into the validator.
            }
          }
        }
        // JavaScript's identity-Set idiom: `new Set([setTimeout, atob,''',
        '''              // Any other lowered kind falls through to the named fence
              // below — never a mistyped seed into the validator.
            }

            // A readonly tuple (`const names = ["a", "b"] as const`) is
            // represented as a fixed record, not an Array, but it is still
            // an Iterable accepted by Set. Snapshot its positional fields
            // into a fresh homogeneous array and reuse setNew. Keep this
            // deliberately narrow: every tuple slot must already have the
            // Set element representation, and the lowered receiver must be
            // pure so reusing the record reference for positional reads
            // cannot duplicate source effects. General iterables and
            // structural-record identity stay fenced.
            if (argIr?.kind === "record") {
              const tupleShape = L.shapes.get(argIr.shapeId);
              if (tupleShape?.tuple) {
                const receiver = L.lowerExpr(argNode);
                const byIndex = [...tupleShape.fields].sort((a, b) => Number(a.name) - Number(b.name));
                if (
                  receiver.type.kind === "record" &&
                  pureReemittable(receiver) &&
                  byIndex.every((field) => typeEquals(field.type, mapped.elem))
                ) {
                  const elems: IrExpr[] = byIndex.map((field) => ({
                    kind: "recordGet",
                    obj: receiver,
                    shapeId: argIr.shapeId,
                    field: field.name,
                    type: field.type,
                    loc,
                  }));
                  const seed: IrExpr = { kind: "arrayLit", elems, type: arrayOf(mapped.elem), loc };
                  return { kind: "setNew", seed, type: mapped, loc };
                }
              }
            }
          }
        }
        // JavaScript's identity-Set idiom: `new Set([setTimeout, atob,''',
    )
    CORPUS.write_text('''// Readonly tuples are valid Set iterables. ScriptC snapshots their fixed
// positional record representation into a fresh homogeneous seed array.
const SESSION_NAMES = ["compact", "refine", "goal", "autonomous"] as const;
const SESSION_NAME_SET: ReadonlySet<string> = new Set(SESSION_NAMES);
console.log(
  SESSION_NAME_SET.size,
  SESSION_NAME_SET.has("compact"),
  SESSION_NAME_SET.has("missing"),
  [...SESSION_NAME_SET].join(","),
);

const DUPLICATES = ["name", "kill", "name"] as const;
const UNIQUE: ReadonlySet<string> = new Set(DUPLICATES);
console.log(UNIQUE.size, [...UNIQUE].join("|"));
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
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3004-set-readonly-tuple'], test_env) and ok

if ok:
    if FAIL.exists():
        FAIL.unlink()
    print('SET_READONLY_TUPLE=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(SOURCE)], check=False)
    if CORPUS.exists():
        CORPUS.unlink()
    LOG.append('SET_READONLY_TUPLE=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('SET_READONLY_TUPLE=FAIL', flush=True)
