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
  log.append(p.stdout+f'\n[exit {p.returncode}]\n')
  return p.returncode==0

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
    // JavaScript's Error constructor accepts any message value: when the
    // argument is not undefined it performs the ordinary ECMAScript
    // ToString operation before defining `.message`. TypeScript sources
    // keep the declaration-level string discipline above; generated/plain
    // JavaScript has no such author contract, so use the same shared
    // String()/template coercion lowering the rest of the JS frontend uses.
    // This is especially important under --loose-js, where bundled library
    // constructors commonly carry checker-`any` parameters. jsval values
    // stay in the engine for JS-exact object-protocol coercion; dyn/scalars
    // use the existing native coercion machinery. Throws from user
    // toString/valueOf propagate catchably, exactly like Node.
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
    this.name = "WrappedError";
  }
}

const custom = { toString() { return "custom-object"; } };
console.log(new WrappedError(42).toString());
console.log(new WrappedError(false).toString());
console.log(new WrappedError(null).toString());
console.log(new WrappedError(undefined).toString());
console.log(new WrappedError(custom).toString());
console.log(new Error(17).toString());
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
