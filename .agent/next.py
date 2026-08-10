from pathlib import Path
import os, subprocess, traceback

MOD=Path('packages/compiler/src/frontend/lowering/lower-modules.ts')
FIX=Path('tests/loose-js-var-hoist.js')
FAIL=Path('LOOSE_JS_VAR_HOIST_FAILURE.txt')
LOG=[]; orig=MOD.read_text(encoding='utf-8'); orig_fix=FIX.read_text(encoding='utf-8') if FIX.exists() else None

def rep(old,new,n=1):
 s=MOD.read_text(encoding='utf-8'); c=s.count(old)
 if c!=n: raise RuntimeError(f'expected {n} matches, found {c} for {old[:100]!r}')
 MOD.write_text(s.replace(old,new,n),encoding='utf-8')

def run(args,timeout=1800):
 LOG.append('$ '+' '.join(map(str,args)))
 try:
  cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
  out=cp.stdout or ''; LOG.extend(out.splitlines()[-240:]); LOG.append(f'[exit {cp.returncode}]'); return cp.returncode,out
 except Exception as e:
  LOG.append(f'[exception {type(e).__name__}: {e}]'); LOG.extend(traceback.format_exc().splitlines()); return 127,''

ok=True
try:
 anchor='''function jsDynHoldableInitializer(L: Lowerer, init: ts.Expression | undefined): boolean {'''
 helper='''/** Generated bundles commonly hoist `var x` below class/function text that\n * mentions x, while the read itself happens only later at runtime. In strict\n * TS/static JS a non-undefined slot cannot model the hoist. Under\n * --loose-js --dynamic, detect exactly this textual-forward-var family and\n * give the module binding an island slot: entry initializes it to real JS\n * undefined, the declaration later stores the actual value, and early\n * accidental execution still observes Node's undefined rather than NULL. */\nfunction looseJsForwardVar(\n  L: Lowerer,\n  sf: ts.SourceFile,\n  decl: ts.VariableDeclaration,\n  symbol: ts.Symbol | undefined,\n): boolean {\n  if (!L.looseJs || !L.dynamic || !symbol || !isVarDeclared(decl)) return false;\n  const declStart = decl.getStart(sf);\n  for (const stmt of sf.statements) {\n    if (stmt.getStart(sf) >= declStart) break;\n    let found = false;\n    ts.walkPreorder(stmt, (node) => {\n      if (ts.isIdentifier(node) && L.checker.getSymbolAtLocation(node) === symbol) {\n        found = true;\n        return \"stop\";\n      }\n      return undefined;\n    });\n    if (found) return true;\n  }\n  return false;\n}\n\n'''+anchor
 rep(anchor,helper)
 insert='''            if (type.kind === "void") L.badType(nameNode, L.typeOf(nameNode));\n            // A JS file-scope FUNCTION binding whose unannotated return'''
 replacement='''            if (type.kind === "void") L.badType(nameNode, L.typeOf(nameNode));\n            // --loose-js generated-bundle forward `var`: preserve JS hoisting\n            // by storing the binding in the island. This must happen before\n            // the function/record-specific slot refinements below.\n            if (\n              looseJsForwardVar(L, sf, decl, L.checker.getSymbolAtLocation(nameNode))\n            ) {\n              type = JSVAL;\n            }\n            // A JS file-scope FUNCTION binding whose unannotated return'''
 rep(insert,replacement)
 FIX.write_text('''class PaletteUser {\n  value = source_default.green("ok");\n}\n\nvar source_default = {\n  green(value) { return `G:${value}`; },\n};\n\nconsole.log(new PaletteUser().value);\n''',encoding='utf-8')
except Exception as e:
 LOG.append(f'PATCH EXCEPTION: {e!r}'); LOG.extend(traceback.format_exc().splitlines()); ok=False
if ok:
 for cmd in (["pnpm","build"],["pnpm","lint"]):
  if run(cmd)[0]: ok=False; break
if ok:
 node_rc,node_out=run(['node',str(FIX)])
 cli=str(Path.cwd()/'packages/cli/dist/main.js'); out='/tmp/scriptc-loose-var-hoist'
 build_rc,build_out=run(['node',cli,'build',str(FIX),'--dynamic','--loose-js','-o',out],timeout=1200)
 native_rc,native_out=(127,'')
 if build_rc==0: native_rc,native_out=run([out],timeout=30)
 strict_rc,strict_out=run(['node',cli,'build',str(FIX),'--dynamic','-o','/tmp/scriptc-strict-var-hoist'],timeout=1200)
 if node_rc or build_rc or native_rc or node_out!=native_out or strict_rc==0 or 'SC1030' not in strict_out:
  LOG += ['loose-js var-hoist differential/strict-gate mismatch','NODE='+repr(node_out),'NATIVE='+repr(native_out),'STRICT_RC='+str(strict_rc)]
  ok=False
if not ok:
 MOD.write_text(orig,encoding='utf-8')
 if orig_fix is None:
  if FIX.exists(): FIX.unlink()
 else: FIX.write_text(orig_fix,encoding='utf-8')
 LOG.append('LOOSE_JS_VAR_HOIST=FAIL; reverted'); FAIL.write_text('\n'.join(LOG)+'\n',encoding='utf-8')
else:
 if FAIL.exists(): FAIL.unlink()
