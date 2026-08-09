from pathlib import Path
import os
import subprocess

SOURCE = 'packages/compiler/src/frontend/lowering/lower-containers.ts'
CORPUS = 'tests/corpus/3003-object-entries-forof.ts'
FAIL = Path('OBJECT_ENTRIES_EXACT_FAILURE.txt')
LOG = []


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{path}: expected one match, found {n}: {old[:80]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def run(args, env, timeout=1800):
    LOG.append('$ ' + ' '.join(args))
    try:
        cp = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        lines = (cp.stdout or '').splitlines()
        LOG.extend(lines[-300:])
        LOG.append(f'[exit {cp.returncode}]')
        return cp.returncode == 0
    except Exception as e:
        LOG.append(f'[exception {type(e).__name__}: {e}]')
        return False


def patch() -> None:
    replace_once(SOURCE,
'''    const keysT = arrayOf(STRING);
    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;''',
'''    const keysT = arrayOf(STRING);
    const valuesT = arrayOf(iv);
    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;''')

    replace_once(SOURCE,
'''      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);
      const i = L.declareHiddenLocal("%objEntriesIndex", F64);
      i.mutable = true;''',
'''      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);
      const values = L.declareHiddenLocal("%objEntriesValues", valuesT);
      const snapI = L.declareHiddenLocal("%objEntriesSnapIndex", F64);
      const i = L.declareHiddenLocal("%objEntriesIndex", F64);
      snapI.mutable = true;
      i.mutable = true;''')

    replace_once(SOURCE,
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
      });''')

    replace_once(SOURCE,
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
      const body = L.inCtl("loop", () => L.lowerScopedBlock(stmt.statement));''')

    replace_once(SOURCE,
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
          loop,''')

    corpus = Path(CORPUS)
    text = corpus.read_text(encoding='utf-8')
    if 'source-after' not in text:
        corpus.write_text(text + '''\n\n// Object.entries snapshots VALUES at call time too. Mutating a later source\n// value during the first loop body must not affect the already-created row.\nconst snapshot: Record<string, string> = {};\nsnapshot["first"] = "A";\nsnapshot["second"] = "B";\nfor (const [key, value] of Object.entries(snapshot)) {\n  console.log("snapshot", key, value);\n  if (key === "first") snapshot["second"] = "CHANGED";\n}\nconsole.log("source-after", snapshot["second"]);\n''', encoding='utf-8')


ok = True
try:
    patch()
except Exception as e:
    LOG.append(f'PATCH FAILURE: {type(e).__name__}: {e}')
    ok = False

NODE_VERSION = Path('.node-version').read_text(encoding='utf-8').strip()
NODE_DIR = Path(f'/tmp/node-v{NODE_VERSION}-linux-x64')
ENV = os.environ.copy()
if ok and not (NODE_DIR / 'bin/node').exists():
    archive = Path(f'/tmp/node-v{NODE_VERSION}-linux-x64.tar.xz')
    ok = run(['curl', '-fsSL', f'https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz', '-o', str(archive)], ENV) and ok
    if ok: ok = run(['tar', '-xJf', str(archive), '-C', '/tmp'], ENV) and ok
ENV['PATH'] = f"{NODE_DIR / 'bin'}:{ENV.get('PATH', '')}"
for cmd in [
    ['node', '--version'],
    ['corepack', 'enable'],
    ['corepack', 'prepare', 'pnpm@11.1.3', '--activate'],
    ['pnpm', 'install', '--frozen-lockfile'],
    ['pnpm', 'build'],
    ['pnpm', 'lint'],
]:
    if ok: ok = run(cmd, ENV) and ok
if ok:
    for san in (False, True):
        e = ENV.copy()
        if san: e['SCRIPTC_SAN'] = '1'
        else: e.pop('SCRIPTC_SAN', None)
        for testfile in ('tests/harness/differential.test.ts', 'tests/harness/llvm-differential.test.ts'):
            this = run(['pnpm', 'exec', 'vitest', 'run', testfile, '-t', '3003-object-entries-forof'], e)
            ok = this and ok

if ok:
    if FAIL.exists(): FAIL.unlink()
    print('OBJECT_ENTRIES_EXACT_VALIDATION=PASS', flush=True)
else:
    subprocess.run(['git', 'checkout', '--', SOURCE, CORPUS], check=False)
    LOG.append('OBJECT_ENTRIES_EXACT_VALIDATION=FAIL; source/corpus reverted')
    FAIL.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    print('OBJECT_ENTRIES_EXACT_VALIDATION=FAIL', flush=True)
