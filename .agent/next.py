from pathlib import Path
import os
import subprocess


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one match, found {count}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


path = 'packages/compiler/src/frontend/lowering/lower-containers.ts'
old = '''    const recT = iterable.type;
    const iv = shape.indexValue;
    const keysT = arrayOf(STRING);
    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;
    L.scopes.push(new Map());
    try {
      const src = L.declareHiddenLocal("%objEntriesSrc", recT);
      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);
      const i = L.declareHiddenLocal("%objEntriesIndex", F64);
      i.mutable = true;
      const ref = (localId: string, type: IrType): IrExpr => ({ kind: "varRef", localId, type, loc });
      const num = (value: number): IrExpr => ({ kind: "numLit", value, type: F64, loc });
      const keyRead = (): IrExpr => ({
        kind: "arrayGet",
        arr: ref(keys.id, keysT),
        index: ref(i.id, F64),
        type: STRING,
        loc,
      });
      const k = L.declareLocal(els[0]!.name, els[0]!.name.text, STRING, isLet);
      const v = L.declareLocal(els[1]!.name, els[1]!.name.text, iv, isLet);
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
      const body = L.inCtl("loop", () => L.lowerScopedBlock(stmt.statement));
      const loop: IrStmt = {
        kind: "for",
        init: { kind: "varDecl", localId: i.id, init: num(0), loc },
        cond: {
          kind: "bin",
          op: "<",
          left: ref(i.id, F64),
          right: { kind: "arrIntrinsic", method: "length", receiver: ref(keys.id, keysT), args: [], type: F64, loc },
          type: BOOL,
          loc,
        },
        update: {
          kind: "assign",
          localId: i.id,
          value: { kind: "bin", op: "+", left: ref(i.id, F64), right: num(1), type: F64, loc },
          loc,
        },
        body: [...binds, ...body],
        loc,
      };
      return {
        kind: "block",
        body: [
          { kind: "varDecl", localId: src.id, init: iterable, loc },
          {
            kind: "varDecl",
            localId: keys.id,
            init: { kind: "recordOvfKeys", obj: ref(src.id, recT), shapeId: recT.shapeId, type: keysT, loc },
            loc,
          },
          loop,
        ],
        loc,
      };
'''
new = '''    const recT = iterable.type;
    const iv = shape.indexValue;
    const keysT = arrayOf(STRING);
    const valuesT = arrayOf(iv);
    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;
    L.scopes.push(new Map());
    try {
      const src = L.declareHiddenLocal("%objEntriesSrc", recT);
      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);
      const values = L.declareHiddenLocal("%objEntriesValues", valuesT);
      const snapI = L.declareHiddenLocal("%objEntriesSnapIndex", F64);
      const i = L.declareHiddenLocal("%objEntriesIndex", F64);
      snapI.mutable = true;
      i.mutable = true;
      const ref = (localId: string, type: IrType): IrExpr => ({ kind: "varRef", localId, type, loc });
      const num = (value: number): IrExpr => ({ kind: "numLit", value, type: F64, loc });
      const keyAt = (indexLocalId: string): IrExpr => ({
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
      });
      const k = L.declareLocal(els[0]!.name, els[0]!.name.text, STRING, isLet);
      const v = L.declareLocal(els[1]!.name, els[1]!.name.text, iv, isLet);
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
        body: [
          {
            kind: "exprStmt",
            expr: {
              kind: "arrIntrinsic",
              method: "push",
              receiver: ref(values.id, valuesT),
              args: [
                {
                  kind: "recordKeyGet",
                  obj: ref(src.id, recT),
                  shapeId: recT.shapeId,
                  key: keyAt(snapI.id),
                  overflowOnly: true,
                  type: iv,
                  loc,
                },
              ],
              type: F64,
              loc,
            },
            loc,
          },
        ],
        loc,
      };
      const body = L.inCtl("loop", () => L.lowerScopedBlock(stmt.statement));
      const loop: IrStmt = {
        kind: "for",
        init: { kind: "varDecl", localId: i.id, init: num(0), loc },
        cond: {
          kind: "bin",
          op: "<",
          left: ref(i.id, F64),
          right: { kind: "arrIntrinsic", method: "length", receiver: ref(keys.id, keysT), args: [], type: F64, loc },
          type: BOOL,
          loc,
        },
        update: {
          kind: "assign",
          localId: i.id,
          value: { kind: "bin", op: "+", left: ref(i.id, F64), right: num(1), type: F64, loc },
          loc,
        },
        body: [...binds, ...body],
        loc,
      };
      return {
        kind: "block",
        body: [
          { kind: "varDecl", localId: src.id, init: iterable, loc },
          {
            kind: "varDecl",
            localId: keys.id,
            init: { kind: "recordOvfKeys", obj: ref(src.id, recT), shapeId: recT.shapeId, type: keysT, loc },
            loc,
          },
          { kind: "varDecl", localId: values.id, init: { kind: "arrayLit", elems: [], type: valuesT, loc }, loc },
          snapshotLoop,
          loop,
        ],
        loc,
      };
'''
replace_once(path, old, new)

corpus = Path('tests/corpus/3003-object-entries-forof.ts')
text = corpus.read_text(encoding='utf-8')
append = '''\n\n// Object.entries snapshots VALUES at call time too. Mutating a later source\n// value during the first loop body must not affect the already-created row.\nconst snapshot: Record<string, string> = {};\nsnapshot["first"] = "A";\nsnapshot["second"] = "B";\nfor (const [key, value] of Object.entries(snapshot)) {\n  console.log("snapshot", key, value);\n  if (key === "first") snapshot["second"] = "CHANGED";\n}\nconsole.log("source-after", snapshot["second"]);\n'''
if 'source-after' not in text:
    corpus.write_text(text + append, encoding='utf-8')

NODE_VERSION = Path('.node-version').read_text(encoding='utf-8').strip()
NODE_DIR = Path(f'/tmp/node-v{NODE_VERSION}-linux-x64')
ENV = os.environ.copy()

def run(args, *, env=None):
    print('+', ' '.join(args), flush=True)
    subprocess.run(args, check=True, env=env or ENV, timeout=1800)

if not (NODE_DIR / 'bin/node').exists():
    archive = Path(f'/tmp/node-v{NODE_VERSION}-linux-x64.tar.xz')
    run(['curl', '-fsSL', f'https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz', '-o', str(archive)])
    run(['tar', '-xJf', str(archive), '-C', '/tmp'])
ENV['PATH'] = f"{NODE_DIR / 'bin'}:{ENV.get('PATH', '')}"
run(['node', '--version'])
run(['corepack', 'enable'])
run(['corepack', 'prepare', 'pnpm@11.1.3', '--activate'])
run(['pnpm', 'install', '--frozen-lockfile'])
run(['pnpm', 'build'])
run(['pnpm', 'lint'])
for san in (False, True):
    e = ENV.copy()
    if san: e['SCRIPTC_SAN'] = '1'
    else: e.pop('SCRIPTC_SAN', None)
    run(['pnpm', 'exec', 'vitest', 'run', 'tests/harness/differential.test.ts', '-t', '3003-object-entries-forof'], env=e)
    run(['pnpm', 'exec', 'vitest', 'run', 'tests/harness/llvm-differential.test.ts', '-t', '3003-object-entries-forof'], env=e)
print('OBJECT_ENTRIES_EXACT_VALIDATION_OK', flush=True)
