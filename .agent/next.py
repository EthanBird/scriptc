from pathlib import Path
import os, subprocess

SRC=Path('packages/compiler/src/frontend/lowering/lower-classes.ts')
CORPUS=Path('tests/corpus/3014-js-error-message-coercion.js')
FAIL=Path('JS_ERROR_MESSAGE_COERCION_FAILURE.txt')
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
  old='''    if (value.kind === "unitLit" && value.unit === "undefined") {
      return { kind: "strLit", value: "", type: STRING, loc };
    }
    L.unsupported(
'''
  new='''    if (value.kind === "unitLit" && value.unit === "undefined") {
      return { kind: "strLit", value: "", type: STRING, loc };
    }
    // Plain/generated JavaScript has no TypeScript `message?: string`
    // author contract. Error(message) follows ECMAScript: every defined
    // message is ToString(message). Reuse the frontend's shared String()
    // coercion path here (island `toStr` for checker-any/jsval, native
    // dispatch for dyn/scalars); a user toString/valueOf throw propagates.
    // TypeScript sources keep the strict declaration-level string rule.
    if (isJsSourceFile(args[0]!.getSourceFile())) {
      return L.ensureString(value, args[0]!);
    }
    L.unsupported(
'''
  if old not in s: raise RuntimeError('errorMessageArg anchor changed')
  SRC.write_text(s.replace(old,new,1))
  CORPUS.write_text('''// @dynamic
class WrappedError extends Error {
  constructor(message) {
    super(message);
  }
}

console.log(new WrappedError("text").toString());
console.log(new WrappedError(42).toString());
console.log(new WrappedError(false).toString());
console.log(new WrappedError(null).toString());
console.log(new WrappedError(undefined).toString());
''')
  checks=[
    (["pnpm","build"],None),(["pnpm","lint"],None),
    (["pnpm","exec","vitest","run","tests/harness/differential.test.ts","-t","3014-js-error-message-coercion"],None),
    (["pnpm","exec","vitest","run","tests/harness/differential.test.ts","-t","3014-js-error-message-coercion"],{"SCRIPTC_SAN":"1"}),
    (["pnpm","exec","vitest","run","tests/harness/llvm-differential.test.ts","-t","3014-js-error-message-coercion"],None),
    (["pnpm","exec","vitest","run","tests/harness/llvm-differential.test.ts","-t","3014-js-error-message-coercion"],{"SCRIPTC_SAN":"1"}),
  ]
  for cmd,env in checks:
    if not run(cmd,env):
      restore(); FAIL.write_text(''.join(log)+'\nJS_ERROR_MESSAGE_COERCION=FAIL; source/corpus reverted\n'); break
  else:
    FAIL.unlink(missing_ok=True); print('JS_ERROR_MESSAGE_COERCION=PASS')
except Exception as e:
  restore(); FAIL.write_text(''.join(log)+f'\nTASK EXCEPTION: {e!r}\nJS_ERROR_MESSAGE_COERCION=FAIL; source/corpus reverted\n')
