from pathlib import Path
import os, subprocess

SRC=Path('packages/compiler/src/frontend/lowering/lower-island.ts')
CORPUS=Path('tests/corpus/3015-math-random-function-value.ts')
FAIL=Path('MATH_RANDOM_FUNCTION_VALUE_FAILURE.txt')
orig_src=SRC.read_text(); orig_corpus=CORPUS.read_text() if CORPUS.exists() else None
log=[]

def restore():
  SRC.write_text(orig_src)
  if orig_corpus is None: CORPUS.unlink(missing_ok=True)
  else: CORPUS.write_text(orig_corpus)

def run(cmd,env=None):
  e=os.environ.copy(); e.update(env or {})
  log.append('$ '+' '.join(cmd)+'\n')
  p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=e)
  log.append(p.stdout+f'\n[exit {p.returncode}]\n'); return p.returncode==0

try:
  s=SRC.read_text()
  old_import='import { BOOL, BYTES_U8, DYN, F64, IrExpr, IrStmt, IrType, JSVAL, MAX_ISLAND_CALLBACK_ARITY, STRING, VOID, canConvertToDyn, canMarshalTypedFuncIntoIsland, islandPromisePayloadTag, isUnitType } from "../../ir/nodes.js";'
  new_import='import { BOOL, BYTES_U8, DYN, F64, IrExpr, IrStmt, IrType, JSVAL, MAX_ISLAND_CALLBACK_ARITY, STRING, VOID, canConvertToDyn, canMarshalTypedFuncIntoIsland, funcOf, islandPromisePayloadTag, isUnitType } from "../../ir/nodes.js";'
  if old_import not in s: raise RuntimeError('lower-island import anchor changed')
  s=s.replace(old_import,new_import,1)
  old='''    if (
      own(ISLAND_SURFACE.math.fns, member) !== undefined ||
      own(STATIC_MATH_FNS, member) !== undefined
    ) {
      L.unsupported("SC1090", expr, `Math methods as values (call '${member}' directly)`);
    }
'''
  new='''    if (member === "random" && own(STATIC_MATH_FNS, member) !== undefined) {
      // Builtin function VALUES need stable JS identity, not a fresh
      // closure on every property read. Zero-capture closures are interned
      // by fnName in both backends, so one synthetic helper is the exact
      // native representation of the singleton Math.random function.
      const fnName = "%builtin.Math.random";
      const fnT = funcOf([], F64);
      if (!L.liftedFns.some((fn) => fn.name === fnName)) {
        L.liftedFns.push({
          name: fnName,
          params: [],
          returnType: F64,
          locals: [],
          body: [
            {
              kind: "return",
              value: { kind: "libCall", fn: "math.random", args: [], type: F64, loc },
              loc,
            },
          ],
          loc,
        });
      }
      return { kind: "closure", fnName, captures: [], type: fnT, loc };
    }
    if (
      own(ISLAND_SURFACE.math.fns, member) !== undefined ||
      own(STATIC_MATH_FNS, member) !== undefined
    ) {
      L.unsupported("SC1090", expr, `Math methods as values (call '${member}' directly)`);
    }
'''
  if old not in s: raise RuntimeError('Math property function-value anchor changed')
  SRC.write_text(s.replace(old,new,1))
  CORPUS.write_text('''const first = Math.random;
const second = Math.random;
console.log("identity", first === second);

function inRange(random: () => number = Math.random): boolean {
  const value = random();
  return value >= 0 && value < 1;
}
console.log("default", inRange());
console.log("direct", inRange(Math.random));
''')
  checks=[
    (["pnpm","build"],None),(["pnpm","lint"],None),
    (["pnpm","exec","vitest","run","tests/harness/differential.test.ts","-t","3015-math-random-function-value"],None),
    (["pnpm","exec","vitest","run","tests/harness/differential.test.ts","-t","3015-math-random-function-value"],{"SCRIPTC_SAN":"1"}),
    (["pnpm","exec","vitest","run","tests/harness/llvm-differential.test.ts","-t","3015-math-random-function-value"],None),
    (["pnpm","exec","vitest","run","tests/harness/llvm-differential.test.ts","-t","3015-math-random-function-value"],{"SCRIPTC_SAN":"1"}),
  ]
  for cmd,env in checks:
    if not run(cmd,env):
      restore(); FAIL.write_text(''.join(log)+'\nMATH_RANDOM_FUNCTION_VALUE=FAIL; source/corpus reverted\n'); break
  else:
    FAIL.unlink(missing_ok=True); print('MATH_RANDOM_FUNCTION_VALUE=PASS')
except Exception as e:
  restore(); FAIL.write_text(''.join(log)+f'\nTASK EXCEPTION: {e!r}\nMATH_RANDOM_FUNCTION_VALUE=FAIL; source/corpus reverted\n')
