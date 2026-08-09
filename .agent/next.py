from pathlib import Path
import os, subprocess

SOURCE='packages/compiler/src/frontend/lowering/lower-containers.ts'
CORPUS='tests/corpus/3003-object-entries-forof.ts'
FAIL=Path('OBJECT_ENTRIES_EXACT_FAILURE.txt')
LOG=[]

def rep(old,new):
 p=Path(SOURCE); s=p.read_text(); n=s.count(old)
 if n!=1: raise RuntimeError(f'replace count {n}: {old[:70]!r}')
 p.write_text(s.replace(old,new,1))

def run(a,env):
 LOG.append('$ '+' '.join(a))
 cp=subprocess.run(a,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800)
 LOG.extend((cp.stdout or '').splitlines()[-220:]); LOG.append(f'[exit {cp.returncode}]')
 return cp.returncode==0

ok=True
try:
 rep('''    const keysT = arrayOf(STRING);\n    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;''','''    const keysT = arrayOf(STRING);\n    const valuesT = arrayOf(iv);\n    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;''')
 rep('''      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);\n      const i = L.declareHiddenLocal("%objEntriesIndex", F64);\n      i.mutable = true;''','''      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);\n      const values = L.declareHiddenLocal("%objEntriesValues", valuesT);\n      const snapI = L.declareHiddenLocal("%objEntriesSnapIndex", F64);\n      const i = L.declareHiddenLocal("%objEntriesIndex", F64);\n      snapI.mutable = true;\n      i.mutable = true;''')
 rep('''      const keyRead = (): IrExpr => ({\n        kind: "arrayGet",\n        arr: ref(keys.id, keysT),\n        index: ref(i.id, F64),\n        type: STRING,\n        loc,\n      });''','''      const keyAt = (indexLocalId: string): IrExpr => ({\n        kind: "arrayGet",\n        arr: ref(keys.id, keysT),\n        index: ref(indexLocalId, F64),\n        type: STRING,\n        loc,\n      });\n      const keyRead = (): IrExpr => keyAt(i.id);\n      const valueRead = (): IrExpr => ({ kind: "arrayGet", arr: ref(values.id, valuesT), index: ref(i.id, F64), type: iv, loc });''')
 rep('''      const v = L.declareLocal(els[1]!.name, els[1]!.name.text, iv, isLet);\n      const kRef: IrExpr = { kind: "varRef", localId: k.id, type: STRING, loc };\n      const binds: IrStmt[] = [\n        { kind: "varDecl", localId: k.id, init: keyRead(), loc },\n        {\n          kind: "varDecl",\n          localId: v.id,\n          init: {\n            kind: "recordKeyGet",\n            obj: ref(src.id, recT),\n            shapeId: recT.shapeId,\n            key: kRef,\n            overflowOnly: true,\n            type: iv,\n            loc,\n          },\n          loc,\n        },\n      ];\n      const body = L.inCtl("loop", () => L.lowerScopedBlock(stmt.statement));''','''      const v = L.declareLocal(els[1]!.name, els[1]!.name.text, iv, isLet);\n      const binds: IrStmt[] = [\n        { kind: "varDecl", localId: k.id, init: keyRead(), loc },\n        { kind: "varDecl", localId: v.id, init: valueRead(), loc },\n      ];\n      const snapshotLoop: IrStmt = {\n        kind: "for",\n        init: { kind: "varDecl", localId: snapI.id, init: num(0), loc },\n        cond: { kind: "bin", op: "<", left: ref(snapI.id, F64), right: { kind: "arrIntrinsic", method: "length", receiver: ref(keys.id, keysT), args: [], type: F64, loc }, type: BOOL, loc },\n        update: { kind: "assign", localId: snapI.id, value: { kind: "bin", op: "+", left: ref(snapI.id, F64), right: num(1), type: F64, loc }, loc },\n        body: [{ kind: "exprStmt", expr: { kind: "arrIntrinsic", method: "push", receiver: ref(values.id, valuesT), args: [{ kind: "recordKeyGet", obj: ref(src.id, recT), shapeId: recT.shapeId, key: keyAt(snapI.id), overflowOnly: true, type: iv, loc }], type: F64, loc }, loc }],\n        loc,\n      };\n      const body = L.inCtl("loop", () => L.lowerScopedBlock(stmt.statement));''')
 rep('''          },\n          loop,\n        ],\n        loc,\n      };\n    } finally {\n      L.scopes.pop();\n    }\n  }\n\n  export function lowerForOfMap''','''          },\n          { kind: "varDecl", localId: values.id, init: { kind: "arrayLit", elems: [], type: valuesT, loc }, loc },\n          snapshotLoop,\n          loop,\n        ],\n        loc,\n      };\n    } finally {\n      L.scopes.pop();\n    }\n  }\n\n  export function lowerForOfMap''')
 p=Path(CORPUS); s=p.read_text()
 marker='''\nfunction copyColors<T extends Record<string, string | number>>(colors: T): Record<string, string | number> {\n  const out: Record<string, string | number> = {};\n  for (const [key, value] of Object.entries(colors)) out[key] = value;\n  return out;\n}\nconst colors: Record<string, string | number> = {};\ncolors["accent"] = "#fff";\ncolors["level"] = 7;\nconsole.log(JSON.stringify(copyColors(colors)));'''
 if marker in s: s=s.replace(marker,'')
 if 'source-after' not in s:
  s+='''\n\n// Values are snapshotted by Object.entries before the first body executes.\nconst snapshot: Record<string, string> = {};\nsnapshot["first"] = "A";\nsnapshot["second"] = "B";\nfor (const [key, value] of Object.entries(snapshot)) {\n  console.log("snapshot", key, value);\n  if (key === "first") snapshot["second"] = "CHANGED";\n}\nconsole.log("source-after", snapshot["second"]);\n'''
 p.write_text(s)
except Exception as e:
 LOG.append(f'PATCH: {type(e).__name__}: {e}'); ok=False

ver=Path('.node-version').read_text().strip(); nd=Path(f'/tmp/node-v{ver}-linux-x64'); env=os.environ.copy()
if ok and not (nd/'bin/node').exists():
 ar=Path(f'/tmp/node-v{ver}-linux-x64.tar.xz'); ok=run(['curl','-fsSL',f'https://nodejs.org/dist/v{ver}/node-v{ver}-linux-x64.tar.xz','-o',str(ar)],env) and ok
 if ok: ok=run(['tar','-xJf',str(ar),'-C','/tmp'],env) and ok
env['PATH']=f"{nd/'bin'}:{env.get('PATH','')}"
for a in [['node','--version'],['corepack','enable'],['corepack','prepare','pnpm@11.1.3','--activate'],['pnpm','install','--frozen-lockfile'],['pnpm','build'],['pnpm','lint']]:
 if ok: ok=run(a,env) and ok
if ok:
 for san in (False,True):
  e=env.copy(); e.pop('SCRIPTC_SAN',None)
  if san: e['SCRIPTC_SAN']='1'
  for tf in ('tests/harness/differential.test.ts','tests/harness/llvm-differential.test.ts'):
   ok=run(['pnpm','exec','vitest','run',tf,'-t','3003-object-entries-forof'],e) and ok

if ok:
 if FAIL.exists(): FAIL.unlink()
 print('OBJECT_ENTRIES_NONGENERIC=PASS')
else:
 subprocess.run(['git','checkout','--',SOURCE,CORPUS],check=False)
 LOG.append('OBJECT_ENTRIES_NONGENERIC=FAIL; reverted')
 FAIL.write_text('\n'.join(LOG)+'\n')
