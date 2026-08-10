from pathlib import Path
import os, subprocess

LOWERER=Path('packages/compiler/src/frontend/lowering/lowerer.ts')
CALLS=Path('packages/compiler/src/frontend/lowering/lower-calls.ts')
INDEX=Path('packages/compiler/src/index.ts')
FIX=Path('tests/loose-js-return-inference.js')
FAIL=Path('LOOSE_JS_RETURN_INFERENCE_FAILURE.txt')
files=[LOWERER,CALLS,INDEX,FIX]
orig={p:(p.read_text() if p.exists() else None) for p in files}
log=[]

def restore():
  for p,v in orig.items():
    if v is None: p.unlink(missing_ok=True)
    else: p.write_text(v)

def run(cmd,env=None,timeout=300):
  e=os.environ.copy(); e.update(env or {})
  log.append('$ '+' '.join(cmd)+'\n')
  try:
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=e,timeout=timeout)
    log.append(p.stdout+f'\n[exit {p.returncode}]\n'); return p.returncode,p.stdout
  except subprocess.TimeoutExpired as x:
    out=(x.stdout or '')+'\n[TIMEOUT]\n'; log.append(out); return 124,out

try:
  # 1) Thread the explicit bundle-ingestion posture into lowering. It does
  # not change normal JS or npm-static behavior.
  s=LOWERER.read_text()
  anchor='''  dynamic?: boolean;\n  /** Coverage: additionally lower the unreached remainder'''
  repl='''  dynamic?: boolean;\n  /** Explicit generated/bundled-JS mode. This only affects the JS inference\n   * heuristics below; TypeScript and ordinary JS keep their existing ABI\n   * choices. */\n  looseJs?: boolean;\n  /** Coverage: additionally lower the unreached remainder'''
  if anchor not in s: raise RuntimeError('LowerOptions dynamic anchor changed')
  s=s.replace(anchor,repl,1)
  mode_anchor='''export interface LowererMode {\n  /** Names of bodies the discovery pass reached; null lowers everything. */'''
  mode_repl='''export interface LowererMode {\n  /** Generated/bundled-JS inference posture, forwarded to every pass. */\n  looseJs?: boolean;\n  /** Names of bodies the discovery pass reached; null lowers everything. */'''
  if mode_anchor not in s: raise RuntimeError('LowererMode anchor changed')
  s=s.replace(mode_anchor,mode_repl,1)
  prop='''  readonly targetPlatform: string;\n  /** LowererMode.startupCrash'''
  prop_repl='''  readonly targetPlatform: string;\n  /** True only for explicit generated/bundled-JS ingestion. */\n  readonly looseJs: boolean;\n  /** LowererMode.startupCrash'''
  if prop not in s: raise RuntimeError('Lowerer property anchor changed')
  s=s.replace(prop,prop_repl,1)
  ctor='''    this.targetPlatform = mode.targetPlatform ?? process.platform;\n    this.startupCrash = mode.startupCrash ?? null;'''
  ctor_repl='''    this.targetPlatform = mode.targetPlatform ?? process.platform;\n    this.looseJs = mode.looseJs ?? false;\n    this.startupCrash = mode.startupCrash ?? null;'''
  if ctor not in s: raise RuntimeError('Lowerer ctor anchor changed')
  s=s.replace(ctor,ctor_repl,1)
  # Pass through every validation/discovery/emission/remainder Lowerer.
  s=s.replace('''  const validation = new Lowerer(program, entry, moduleOrder, dynamic, {\n    targetPlatform,''','''  const validation = new Lowerer(program, entry, moduleOrder, dynamic, {\n    looseJs: options.looseJs ?? false,\n    targetPlatform,''',1)
  s=s.replace('''    : new Lowerer(program, entry, moduleOrder, dynamic, {\n        targetPlatform,''','''    : new Lowerer(program, entry, moduleOrder, dynamic, {\n        looseJs: options.looseJs ?? false,\n        targetPlatform,''',1)
  s=s.replace('''  const emit = new Lowerer(program, entry, moduleOrder, dynamic, {\n    reachable,''','''  const emit = new Lowerer(program, entry, moduleOrder, dynamic, {\n    looseJs: options.looseJs ?? false,\n    reachable,''',1)
  s=s.replace('''  const remainder = new Lowerer(program, entry, moduleOrder, dynamic, {\n    reachable,''','''  const remainder = new Lowerer(program, entry, moduleOrder, dynamic, {\n    looseJs: options.looseJs ?? false,\n    reachable,''',1)
  LOWERER.write_text(s)

  # 2) Reuse implicit-any monomorphization in loose bundled JS as well as
  # npm-static JS. For zero-parameter helpers, opt in only when the checker
  # return is any/unknown: that is precisely when return inference is needed.
  s=CALLS.read_text()
  s=s.replace('implicitMonoFile(decl.getSourceFile())','implicitMonoFile(L, decl.getSourceFile())')
  old='''  export function implicitMonoFile(sf: ts.SourceFile): boolean {\n    return isJsSourceFile(sf) && npmStaticPackageOfPath(sf.fileName) !== null;\n  }'''
  new='''  export function implicitMonoFile(L: Lowerer, sf: ts.SourceFile): boolean {\n    return isJsSourceFile(sf) && (npmStaticPackageOfPath(sf.fileName) !== null || L.looseJs);\n  }'''
  if old not in s: raise RuntimeError('implicitMonoFile definition changed')
  s=s.replace(old,new,1)
  old='''    if (decl.typeParameters !== undefined) return null; // real generics own the machinery\n    if (decl.parameters.length === 0) return null;\n    // The variadic-`arguments` form keeps its dynRest story whole.'''
  new='''    if (decl.typeParameters !== undefined) return null; // real generics own the machinery\n    if (decl.parameters.length === 0) {\n      // Generated bundles contain many erased generic/data helpers whose\n      // zero-argument call is typed any/unknown after bundling. There is no\n      // parameter tuple to specialize, but the existing implicit-instance\n      // return-inference machinery is still exactly what we need: one empty\n      // instance, body-lowered eagerly, with its return type inferred from\n      // the real IR values. Ordinary JS/npm-static keeps the old path.\n      if (!L.looseJs) return null;\n      const sig = L.checker.getSignatureFromDeclaration(decl);\n      if (!sig) return null;\n      const ret = L.checker.getReturnTypeOfSignature(sig);\n      return (ret.flags & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) !== 0 ? [] : null;\n    }\n    // The variadic-`arguments` form keeps its dynRest story whole.'''
  if old not in s: raise RuntimeError('zero-param implicit gate changed')
  s=s.replace(old,new,1)
  old='''      if (retTs.flags & ts.TypeFlags.Any) return null;\n      return L.mapTypeOf(retTs);'''
  new='''      if (retTs.flags & ts.TypeFlags.Any) return null;\n      if (L.looseJs && retTs.flags & ts.TypeFlags.Unknown) return null;\n      return L.mapTypeOf(retTs);'''
  if old not in s: raise RuntimeError('implicitDeclaredReturn anchor changed')
  s=s.replace(old,new,1)
  CALLS.write_text(s)

  # 3) Compile/analyze must pass looseJs into lowering, not only preflight.
  s=INDEX.read_text()
  first='''      dynamic: opts.dynamic ?? false,\n      coverage: true,'''
  first_repl='''      dynamic: opts.dynamic ?? false,\n      looseJs: opts.looseJs ?? false,\n      coverage: true,'''
  if first not in s: raise RuntimeError('analyze lower anchor changed')
  s=s.replace(first,first_repl,1)
  second='''        dynamic: opts.dynamic ?? false,\n        targetPlatform: buildTargetPlatform(),'''
  second_repl='''        dynamic: opts.dynamic ?? false,\n        looseJs: opts.looseJs ?? false,\n        targetPlatform: buildTargetPlatform(),'''
  if second not in s: raise RuntimeError('compile lower anchor changed')
  s=s.replace(second,second_repl,1)
  INDEX.write_text(s)

  FIX.write_text('''function createDeferred() {\n  let settled = false;\n  let resolvePromise;\n  let rejectPromise;\n  const promise = new Promise((resolve, reject) => {\n    resolvePromise = resolve;\n    rejectPromise = reject;\n  });\n  return {\n    promise,\n    settle: (value) => {\n      if (settled) return false;\n      settled = true;\n      resolvePromise(value);\n      return true;\n    },\n    reject: (error) => {\n      if (settled) return false;\n      settled = true;\n      rejectPromise(error);\n      return true;\n    },\n  };\n}\n\nclass Ticket {\n  accepted = createDeferred();\n}\n\nasync function main() {\n  const ticket = new Ticket();\n  console.log("settle", ticket.accepted.settle("ok"), ticket.accepted.settle("late"));\n  console.log("value", await ticket.accepted.promise);\n}\nmain();\n''')

  # Focused four-lane check: this fixture intentionally needs --loose-js.
  code,node_out=run(['node',str(FIX)])
  if code: raise RuntimeError('node oracle failed')
  for backend in ['c','llvm']:
    for san in [False,True]:
      out=f'/tmp/loose-return-{backend}-{"san" if san else "plain"}'
      cmd=['node','packages/cli/dist/main.js','build',str(FIX),'--dynamic','--loose-js','--backend',backend,'-o',out]
      if san: cmd.append('--sanitize')
      code,build_out=run(cmd,timeout=300)
      if code: raise RuntimeError(f'{backend} {san} compile failed:\n'+build_out[-8000:])
      code,native_out=run([out],timeout=60)
      if code or native_out != node_out:
        raise RuntimeError(f'{backend} {san} output mismatch node={node_out!r} native={native_out!r} code={code}')
  # Existing build/lint keeps default modes honest.
  for cmd in [['pnpm','build'],['pnpm','lint']]:
    code,out=run(cmd)
    if code: raise RuntimeError(' '.join(cmd)+' failed')
  FAIL.unlink(missing_ok=True); print('LOOSE_JS_RETURN_INFERENCE=PASS')
except Exception as e:
  restore(); FAIL.write_text(''.join(log)+f'\nTASK EXCEPTION: {e!r}\nLOOSE_JS_RETURN_INFERENCE=FAIL; source reverted\n')
