from pathlib import Path
import re, shutil, subprocess

PROGRAM=Path('packages/compiler/src/frontend/program.ts')
INDEX=Path('packages/compiler/src/index.ts')
CLI=Path('packages/cli/src/main.ts')
TEST=Path('tests/loose-js-valid.js')
BAD=Path('tests/loose-js-invalid.js')
FAIL=Path('LOOSE_JS_INGESTION_FAILURE.txt')
PRIME=Path('PRIME_LOOSE_JS_RESULT.txt')
files=[PROGRAM,INDEX,CLI,TEST,BAD]
orig={p:(p.read_text() if p.exists() else None) for p in files}
log=[]

def restore():
  for p,v in orig.items():
    if v is None: p.unlink(missing_ok=True)
    else: p.write_text(v)

def run(cmd,cwd=None,timeout=900):
  log.append('$ '+' '.join(map(str,cmd))+'\n')
  try:
    p=subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    log.append(p.stdout+f'\n[exit {p.returncode}]\n'); return p.returncode,p.stdout
  except subprocess.TimeoutExpired as e:
    out=(e.stdout or '')+'\n[TIMEOUT]\n'; log.append(out); return 124,out

try:
  s=PROGRAM.read_text()
  old='export function checkPreflight(load: LoadResult): ScrDiagnostic[] {\n  const { diags, moduleOrder, startupCrash } = preflight7(load);'
  if old not in s: raise RuntimeError('checkPreflight anchor')
  s=s.replace(old,'export function checkPreflight(\n  load: LoadResult,\n  opts: { looseJs?: boolean } = {},\n): ScrDiagnostic[] {\n  const { diags, moduleOrder, startupCrash } = preflight7(load, opts.looseJs ?? false);',1)
  if 'function preflight7(load: LoadResult): {' not in s: raise RuntimeError('preflight signature')
  s=s.replace('function preflight7(load: LoadResult): {','function preflight7(load: LoadResult, looseJs = false): {',1)
  anchor='  const errorsOf = (p: ts.Program): ts.Diagnostic[] => {\n    const all = ts.getPreEmitDiagnostics(p);\n'
  repl='''  const errorsOf = (p: ts.Program): ts.Diagnostic[] => {\n    const all = ts.getPreEmitDiagnostics(p);\n    const syntactic = new Set<string>();\n    if (looseJs) for (const d of p.getSyntacticDiagnostics()) syntactic.add(`${d.fileName ?? ""}:${d.pos}:${d.end}:${d.code}`);\n    const looseJsSuppressed = (d: ts.Diagnostic): boolean => {\n      if (!looseJs || d.fileName === undefined || !isJsSourceFileName(d.fileName)) return false;\n      const key = `${d.fileName}:${d.pos}:${d.end}:${d.code}`;\n      if (!syntactic.has(key)) return true;\n      if (d.pos === undefined) return false;\n      const sf = p.getSourceFile(d.fileName);\n      return sf !== undefined && insideBlockComment(sf.text, d.pos);\n    };\n'''
  if anchor not in s: raise RuntimeError('errorsOf anchor')
  s=s.replace(anchor,repl,1)
  filt='        d.category === ts.DiagnosticCategory.Error &&\n        !suppressedJsStrictness7(d) &&'
  if filt not in s: raise RuntimeError('diagnostic filter')
  s=s.replace(filt,'        d.category === ts.DiagnosticCategory.Error &&\n        !looseJsSuppressed(d) &&\n        !suppressedJsStrictness7(d) &&',1)
  PROGRAM.write_text(s)

  s=INDEX.read_text()
  s=s.replace('  dynamic?: boolean;\n  /** Code generator for the program TU.','  dynamic?: boolean;\n  /** Explicit generated/bundled-JS ingestion policy. */\n  looseJs?: boolean;\n  /** Code generator for the program TU.',1)
  s=s.replace('  dynamic?: boolean;\n  /** --npm-static (see CompileOptions.npmStatic):','  dynamic?: boolean;\n  /** Analyze with generated/bundled-JS ingestion policy. */\n  looseJs?: boolean;\n  /** --npm-static (see CompileOptions.npmStatic):',1)
  old='function runFrontend(\n  entryPath: string,\n  npmStatic?: readonly string[] | "auto" | "lib",\n  externalTypes?: Readonly<Record<string, string>>,\n): Frontend {'
  if old not in s: raise RuntimeError('runFrontend')
  s=s.replace(old,'function runFrontend(\n  entryPath: string,\n  npmStatic?: readonly string[] | "auto" | "lib",\n  externalTypes?: Readonly<Record<string, string>>,\n  looseJs = false,\n): Frontend {',1)
  s=s.replace('checkPreflight(scout);','checkPreflight(scout, { looseJs });').replace('checkPreflight(load);','checkPreflight(load, { looseJs });').replace('checkPreflight(probe);','checkPreflight(probe, { looseJs });')
  s=s.replace('const fe = runFrontend(entryPath, opts.npmStatic, opts.externalTypes);','const fe = runFrontend(entryPath, opts.npmStatic, opts.externalTypes, opts.looseJs ?? false);',1)
  s=s.replace('const fe = runFrontend(entryPath, opts.npmStatic);','const fe = runFrontend(entryPath, opts.npmStatic, undefined, opts.looseJs ?? false);',1)
  INDEX.write_text(s)

  s=CLI.read_text()
  s=s.replace('      --dynamic      embed the dynamic engine (adds ~620KB; static stays the default)\\n','      --dynamic      embed the dynamic engine (adds ~620KB; static stays the default)\\n      --loose-js     generated/bundled JS: ignore TypeScript semantic/JSDoc errors; keep real JS syntax errors\\n',1)
  s=s.replace('  dynamic: { type: "boolean", default: false },','  dynamic: { type: "boolean", default: false },\n  "loose-js": { type: "boolean", default: false },',1)
  s=s.replace('if (values.dynamic || values.backend !== undefined','if (values.dynamic || values["loose-js"] || values.backend !== undefined',1)
  marker='  const ffiProfilePath = values.ffi !== undefined ? resolve(values.ffi) : undefined;'
  s=s.replace(marker,'  if (values["loose-js"] && !/\\.(?:js|mjs|cjs)$/.test(input)) fail(`--loose-js accepts only JavaScript entry files\\n\\n${USAGE}`);\n'+marker,1)
  s=s.replace('      dynamic: values.dynamic,\n      ...(npmStatic !== undefined','      dynamic: values.dynamic,\n      looseJs: values["loose-js"],\n      ...(npmStatic !== undefined',1)
  s=s.replace('      dynamic: values.dynamic,\n      ...(backend !== undefined','      dynamic: values.dynamic,\n      looseJs: values["loose-js"],\n      ...(backend !== undefined',1)
  CLI.write_text(s)

  TEST.write_text('/** @type {Array} */\nconst xs = [];\nconsole.log("loose", xs.length);\n')
  BAD.write_text('const broken = ;\n')
  for cmd in [['pnpm','build'],['pnpm','lint']]:
    c,o=run(cmd)
    if c: raise RuntimeError(' '.join(cmd))
  c,o=run(['node','packages/cli/dist/main.js','build',str(TEST),'--dynamic','-o','/tmp/loose-strict'])
  if c==0 or 'SC0001' not in o: raise RuntimeError('default JS semantic gate changed')
  c,o=run(['node','packages/cli/dist/main.js','build',str(TEST),'--dynamic','--loose-js','-o','/tmp/loose-ok'])
  if c: raise RuntimeError('loose valid failed: '+o[-5000:])
  c,o=run(['node','packages/cli/dist/main.js','build',str(BAD),'--dynamic','--loose-js','-o','/tmp/loose-bad'])
  if c==0 or 'SC0001' not in o: raise RuntimeError('true JS syntax error swallowed')

  # Focused compiler feature is now validated; Prime is a frontier probe.
  work=Path('/tmp/scriptc-prime-loose-js')
  if work.exists(): shutil.rmtree(work)
  c,o=run(['git','clone','--depth=1','https://github.com/EthanBird/prime-agent.git',str(work)],timeout=300)
  if c==0: c,o=run(['npm','ci'],cwd=work,timeout=900)
  if c==0: c,o=run(['npm','run','build'],cwd=work,timeout=900)
  if c:
    PRIME.write_text('Prime setup failed\n'+o)
  else:
    exe='/tmp/prime-loose-js'; entry='packages/coding-agent/dist/bundle/cli.js'
    c,body=run(['node',str(Path.cwd()/'packages/cli/dist/main.js'),'build',entry,'--dynamic','--loose-js','-o',exe],cwd=work,timeout=1200)
    diags=[l for l in body.splitlines() if 'error SC' in l or re.search(r'\bSC\d{4}: ',l)]
    smoke=125; st='no executable'
    if c==0 and Path(exe).exists(): smoke,st=run([exe,'--help'],cwd=work,timeout=45)
    PRIME.write_text('# Prime official bundle with --loose-js\n\n'+f'build_status={c}\nexecutable={Path(exe).exists()}\nsmoke_status={smoke}\ndiagnostic_lines={len(diags)}\n\n## first diagnostics\n'+'\n'.join(diags[:160])+'\n\n## build tail\n'+'\n'.join(body.splitlines()[-220:])+'\n\n## smoke tail\n'+'\n'.join(st.splitlines()[-120:])+'\n')
  FAIL.unlink(missing_ok=True)
  print('LOOSE_JS_INGESTION=PASS')
except Exception as e:
  restore(); FAIL.write_text(''.join(log)+f'\nTASK EXCEPTION: {e!r}\nLOOSE_JS_INGESTION=FAIL; source reverted\n')
