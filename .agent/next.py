from pathlib import Path
import os, subprocess

SOURCE = Path('packages/compiler/src/frontend/lowering/lower-containers.ts')
CORPUS = Path('tests/corpus/3003-object-entries-forof.ts')
FAIL = Path('OBJECT_ENTRIES_EXACT_FAILURE.txt')
LOG: list[str] = []


def replace_once(old: str, new: str) -> None:
    text = SOURCE.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'expected one source anchor, found {count}: {old[:96]!r}')
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
        '    const keysT = arrayOf(STRING);\n    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;',
        '    const keysT = arrayOf(STRING);\n    const valuesT = arrayOf(iv);\n    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;',
    )
    replace_once(
        '      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);\n      const i = L.declareHiddenLocal("%objEntriesIndex", F64);\n      i.mutable = true;',
        '      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);\n      const values = L.declareHiddenLocal("%objEntriesValues", valuesT);\n      const snapI = L.declareHiddenLocal("%objEntriesSnapIndex", F64);\n      const i = L.declareHiddenLocal("%objEntriesIndex", F64);\n      snapI.mutable = true;\n      i.mutable = true;',
    )
    replace_once(
        '''      const keyRead = (): IrExpr => ({
        kind: "arrayGet",
        arr: ref(keys.id, keysT),
        index: ref(i.id, F64),
        type: STRING,
        loc,
      });''',
        '''      const keyAt = (indexLocalId: string): IrExpr => ({
        kind: "arrayGet",
        arr: ref(keys.id, keysT),
        index: ref(indexLocalId, F64),
        type: STRING,
        loc,
      });
      const keyRead = (): IrExpr => keyAt(i.id);
      const valueRead = (): IrExpr => ({
        kind: "arrayGet",
        arr: ref(values.id, valuesT),
        index: ref(i.id, F64),
        type: iv,
        loc,
      });''',
    )
    replace_once(
        '''      const v = L.declareLocal(els[1]!.name, els[1]!.name.text, iv, isLet);
      const kRef: IrExpr = { kind: "varRef", localId: k.id, type: STRING, loc };
      const binds: IrStmt[] = [
        { kind: "varDecl", localId: k.id, init: keyRead(), loc },
        {
          kind: "varDecl",
          localId: v.id,
          init: {
            kind: "recordKeyGet",
            obj: ref(src.id, recT),
            shapeId: recT.shapeId,
            key: kRef,
            overflowOnly: true,
            type: iv,
            loc,
          },
          loc,
        },
      ];
      const body = L.inCtl("loop", () => L.lowerScopedBlock(stmt.statement));''',
        '''      const v = L.declareLocal(els[1]!.name, els[1]!.name.text, iv, isLet);
      const binds: IrStmt[] = [
        { kind: "varDecl", localId: k.id, init: keyRead(), loc },
        { kind: "varDecl", localId: v.id, init: valueRead(), loc },
      ];
      // Object.entries materializes all [key, value] pairs before the
      // consumer starts iterating. Snapshot VALUES as well as keys so a
      // body mutation of a later source property cannot leak into an
      // already-created entry.
      const snapshotLoop: IrStmt = {
        kind: "for",
        init: { kind: "varDecl", localId: snapI.id, init: num(0), loc },
        cond: {
          kind: "bin",
          op: "<",
          left: ref(snapI.id, F64),
          right: { kind: "arrIntrinsic", method: "length", receiver: ref(keys.id, keysT), args: [], type: F64, loc },
          type: BOOL,
          loc,
        },
        update: {
          kind: "assign",
          localId: snapI.id,
          value: { kind: "bin", op: "+", left: ref(snapI.id, F64), right: num(1), type: F64, loc },
          loc,
        },
        body: [{
          kind: "exprStmt",
          expr: {
            kind: "arrIntrinsic",
            method: "push",
            receiver: ref(values.id, valuesT),
            args: [{
              kind: "recordKeyGet",
              obj: ref(src.id, recT),
              shapeId: recT.shapeId,
              key: keyAt(snapI.id),
              overflowOnly: true,
              type: iv,
              loc,
            }],
            type: F64,
            loc,
          },
          loc,
        }],
        loc,
      };
      const body = L.inCtl("loop", () => L.lowerScopedBlock(stmt.statement));''',
    )
    replace_once(
        '''          {
            kind: "varDecl",
            localId: keys.id,
            init: { kind: "recordOvfKeys", obj: ref(src.id, recT), shapeId: recT.shapeId, type: keysT, loc },
            loc,
          },
          loop,''',
        '''          {
            kind: "varDecl",
            localId: keys.id,
            init: { kind: "recordOvfKeys", obj: ref(src.id, recT), shapeId: recT.shapeId, type: keysT, loc },
            loc,
          },
          { kind: "varDecl", localId: values.id, init: { kind: "arrayLit", elems: [], type: valuesT, loc }, loc },
          snapshotLoop,
          loop,''',
    )

    # Keep this corpus deliberately non-generic. Generic constraint recovery
    # is a separate compatibility item and gets its own corpus after this
    # fundamental Record<string, T> path is stable.
    text = CORPUS.read_text(encoding='utf-8')
    cut = text.find('\nfunction copyColors')
    if cut >= 0:
        text = text[:cut].rstrip() + '\n'
    if 'source-after' not in text:
        text += '''\n// Object.entries snapshots VALUES at call time too. Mutating a later source
// value during the first body execution must not affect the second row.
const snapshot: Record<string, string> = {};
snapshot["first"] = "A";
snapshot["second"] = "B";
for (const [key, value] of Object.entries(snapshot)) {
  console.log("snapshot", key, value);
  if (key === "first") snapshot["second"] = "CHANGED";
}
console.log("source-after", snapshot["second"]);
'''
    CORPUS.write_text(text, encoding='utf-8')
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
            ok = run(['pnpm', 'exec', 'vitest', 'run', harness, '-t', '3003-object-entries-forof'], test_env) and ok

if ok:
    if FAIL.exists():
        FAIL.unlink()
    print('OBJECT_ENTRIES_EXACT=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', str(SOURCE), str(CORPUS)], check=False)
    LOG.append('OBJECT_ENTRIES_EXACT=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('OBJECT_ENTRIES_EXACT=FAIL', flush=True)
