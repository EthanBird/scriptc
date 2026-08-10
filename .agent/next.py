from pathlib import Path
import subprocess, textwrap

PROGRAM=Path('packages/compiler/src/frontend/program.ts')
INDEX=Path('packages/compiler/src/index.ts')
CLI=Path('packages/cli/src/main.ts')
TEST=Path('tests/loose-js-valid.js')
BAD=Path('tests/loose-js-invalid.js')
FAIL=Path('LOOSE_JS_FOCUSED_FAILURE.txt')
files=[PROGRAM,INDEX,CLI,TEST,BAD]
orig={p:(p.read_text() if p.exists() else None) for p in files}
log=[]

def restore():
  for p,v in orig.items():
    if v is None: p.unlink(missing_ok=True)
    else: p.write_text(v)

def run(cmd):
  log.append('$ '+' '.join(cmd)+'\n')
  p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  log.append(p.stdout+f'\n[exit {p.returncode}]\n')
  return p.returncode,p.stdout

try:
  s=PROGRAM.read_text()
  s=s.replace('export function checkPreflight(load: LoadResult): ScrDiagnostic[] {\n  const { diags, moduleOrder, startupCrash } = preflight7(load);',
'''export function checkPreflight(\n  load: LoadResult,\n  opts: { looseJs?: boolean } = {},\n): ScrDiagnostic[] {\n  const { diags, moduleOrder, startupCrash } = preflight7(load, opts.looseJs ?? false);''',1)
  s=s.replace('function preflight7(load: LoadResult): {','function preflight7(load: LoadResult, looseJs = false): {',1)
  anchor='''  const errorsOf = (p: ts.Program): ts.Diagnostic[] => {\n    const all = ts.getPreEmitDiagnostics(p);\n'''
  repl='''  const errorsOf = (p: ts.Program): ts.Diagnostic[] => {\n    const all = ts.getPreEmitDiagnostics(p);\n    const syntactic = new Set<string>();\n    if (looseJs) {\n      for (const d of p.getSyntacticDiagnostics()) {\n        syntactic.add(`${d.fileName ?? ""}:${d.pos}:${d.end}:${d.code}`);\n      }\n    }\n    const looseJsSuppressed = (d: ts.Diagnostic): boolean => {\n      if (!looseJs || d.fileName === undefined || !isJsSourceFileName(d.fileName)) return false;\n      const key = `${d.fileName}:${d.pos}:${d.end}:${d.code}`;\n      if (!syntactic.has(key)) return true;\n      if (d.pos === undefined) return false;\n      const sf = p.getSourceFile(d.fileName);\n      return sf !== undefined && insideBlockComment(sf.text, d.pos);\n    };\n'''
  if anchor not in s: raise RuntimeError('errorsOf anchor')
  s=s.replace(anchor,repl,1)
  s=s.replace('''        d.category === ts.DiagnosticCategory.Error &&\n        !suppressedJsStrictness7(d) &&''','''        d.category === ts.DiagnosticCategory.Error &&\n        !looseJsSuppressed(d) &&\n        !suppressedJsStrictness7(d) &&''',1)
  PROGRAM.write_text(s)

  s=INDEX.read_text()
  s=s.replace('''  dynamic?: boolean;\n  /** Code generator for the program TU.''','''  dynamic?: boolean;\n  /** Explicit generated/bundled-JS ingestion policy. */\n  looseJs?: boolean;\n  /** Code generator for the program TU.''',1)
  s=s.replace('''  dynamic?: boolean;\n  /** --npm-static (see CompileOptions.npmStatic):''','''  dynamic?: boolean;\n  /** Analyze with generated/bundled-JS ingestion policy. */\n  looseJs?: boolean;\n  /** --npm-static (see CompileOptions.npmStatic):''',1)
  s=s.replace('''function runFrontend(\n  entryPath: string,\n  npmStatic?: readonly string[] | "auto" | "lib",\n  externalTypes?: Readonly<Record<string, string>>,\n): Frontend {''','''function runFrontend(\n  entryPath: string,\n  npmStatic?: readonly string[] | "auto" | "lib",\n  externalTypes?: Readonly<Record<string, string>>,\n  looseJs = false,\n): Frontend {''',1)
  s=s.replace('checkPreflight(scout);','checkPreflight(scout, { looseJs });')
  s=s.replace('checkPreflight(load);','checkPreflight(load, { looseJs });')
  s=s.replace('checkPreflight(probe);','checkPreflight(probe, { looseJs });')
  s=s.replace('const fe = runFrontend(entryPath, opts.npmStatic, opts.externalTypes);','const fe = runFrontend(entryPath, opts.npmStatic, opts.externalTypes, opts.looseJs ?? false);',1)
  s=s.replace('const fe = runFrontend(entryPath, opts.npmStatic);','const fe = runFrontend(entryPath, opts.npmStatic, undefined, opts.looseJs ?? false);',1)
  INDEX.write_text(s)

  s=CLI.read_text()
  s=s.replace('      --dynamic      embed the dynamic engine (adds ~620KB; static stays the default)\\n','      --dynamic      embed the dynamic engine (adds ~620KB; static stays the default)\\n      --loose-js     generated/bundled JS: ignore TypeScript semantic/JSDoc errors; keep real JS syntax errors\\n',1)
  s=s.replace('  dynamic: { type: "boolean", default: false },','  dynamic: { type: "boolean", default: false },\n  "loose-js": { type: "boolean", default: false },',1)
  s=s.replace('if (values.dynamic || values.backend !== undefined','if (values.dynamic || values["loose-js"] || values.backend !== undefined',1)
  marker='  const ffiProfilePath = values.ffi !== undefined ? resolve(values.ffi) : undefined;'
  s=s.replace(marker,'  if (values["loose-js"] && !/\\.(?:js|mjs|cjs)$/.test(input)) fail(`--loose-js accepts only JavaScript entry files\\n\\n${USAGE}`);\n'+marker,1)
  s=s.replace('''      dynamic: values.dynamic,\n      ...(npmStatic !== undefined''','''      dynamic: values.dynamic,\n      looseJs: values["loose-js"],\n      ...(npmStatic !== undefined''',1)
  s=s.replace('''      dynamic: values.dynamic,\n      ...(backend !== undefined''','''      dynamic: values.dynamic,\n      looseJs: values["loose-js"],\n      ...(backend !== undefined''',1)
  CLI.write_text(s)

  TEST.write_text(textwrap.dedent('''\
/** @type {Array} */
const xs = [];
console.log("loose", xs.length);
'''))
  BAD.write_text('const broken = ;\n')

  for cmd in [['pnpm','build'],['pnpm','lint']]:
    c,o=run(cmd)
    if c: raise RuntimeError(' '.join(cmd)+' failed')
  c,o=run(['node','packages/cli/dist/main.js','build',str(TEST),'--dynamic','-o','/tmp/loose-strict'])
  if c==0 or 'SC0001' not in o: raise RuntimeError('default JS mode lost strict semantic gate')
  c,o=run(['node','packages/cli/dist/main.js','build',str(TEST),'--dynamic','--loose-js','-o','/tmp/loose-ok'])
  if c: raise RuntimeError('loose valid JS failed: '+o[-5000:])
  c,o=run(['node','packages/cli/dist/main.js','build',str(BAD),'--dynamic','--loose-js','-o','/tmp/loose-bad'])
  if c==0 or 'SC0001' not in o: raise RuntimeError('loose mode swallowed true JS syntax error')
  c,o=run(['pnpm','exec','vitest','run','tests/harness/preflight.test.ts'])
  if c: raise RuntimeError('preflight regression')
  FAIL.unlink(missing_ok=True)
  print('LOOSE_JS_FOCUSED=PASS')
except Exception as e:
  restore(); FAIL.write_text(''.join(log)+f'\nTASK EXCEPTION: {e!r}\nLOOSE_JS_FOCUSED=FAIL; source reverted\n')
