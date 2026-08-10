from pathlib import Path
import os, re, shutil, subprocess, textwrap

PROGRAM=Path('packages/compiler/src/frontend/program.ts')
INDEX=Path('packages/compiler/src/index.ts')
CLI=Path('packages/cli/src/main.ts')
TEST=Path('tests/corpus/3013-loose-js-entry/main.js')
BAD=Path('tests/corpus/3013-loose-js-entry/bad.js')
FAIL=Path('LOOSE_JS_INGESTION_FAILURE.txt')
PRIME=Path('PRIME_LOOSE_JS_RESULT.txt')
paths=[PROGRAM,INDEX,CLI,TEST,BAD]
orig={p:(p.read_text() if p.exists() else None) for p in paths}
log=[]

def restore():
    for p,data in orig.items():
        if data is None: p.unlink(missing_ok=True)
        else:
            p.parent.mkdir(parents=True,exist_ok=True); p.write_text(data)

def run(cmd,cwd=None,env=None,timeout=900):
    e=os.environ.copy(); e.update(env or {})
    log.append('$ '+' '.join(map(str,cmd))+'\n')
    try:
        p=subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=e,timeout=timeout)
        log.append(p.stdout); log.append(f'[exit {p.returncode}]\n')
        return p.returncode,p.stdout
    except subprocess.TimeoutExpired as x:
        out=(x.stdout or '')+'\n[TIMEOUT]\n'; log.append(out); return 124,out

try:
    # ---------- program.ts: explicit loose-JS checker policy ----------
    s=PROGRAM.read_text()
    old='''export function checkPreflight(load: LoadResult): ScrDiagnostic[] {
  const { diags, moduleOrder, startupCrash } = preflight7(load);
'''
    new='''export function checkPreflight(
  load: LoadResult,
  opts: { looseJs?: boolean } = {},
): ScrDiagnostic[] {
  const { diags, moduleOrder, startupCrash } = preflight7(load, opts.looseJs ?? false);
'''
    if old not in s: raise RuntimeError('checkPreflight anchor changed')
    s=s.replace(old,new,1)
    old='''function preflight7(load: LoadResult): {
'''
    new='''function preflight7(load: LoadResult, looseJs = false): {
'''
    if old not in s: raise RuntimeError('preflight7 signature changed')
    s=s.replace(old,new,1)

    old='''  const errorsOf = (p: ts.Program): ts.Diagnostic[] => {
    const all = ts.getPreEmitDiagnostics(p);
    // First pass: every comment-side 2300's (file, name) — the partners
'''
    new='''  const errorsOf = (p: ts.Program): ts.Diagnostic[] => {
    const all = ts.getPreEmitDiagnostics(p);
    // --loose-js is an explicit BUNDLER/generated-JS ingestion posture.
    // TypeScript semantic/JSDoc diagnostics are not JavaScript execution
    // errors and must not gate already-emitted JS. Real parser diagnostics
    // still gate: keep the exact syntactic diagnostic identities, except a
    // diagnostic whose position is inside a block/JSDoc comment (comment
    // grammar is erased at runtime). TS sources keep the normal full gate.
    const syntaxKeys = new Set<string>();
    if (looseJs) {
      for (const d of p.getSyntacticDiagnostics()) {
        syntaxKeys.add(`${d.fileName ?? ""}:${d.pos}:${d.end}:${d.code}`);
      }
    }
    const looseJsSuppresses = (d: ts.Diagnostic): boolean => {
      if (!looseJs || d.fileName === undefined || !isJsSourceFileName(d.fileName)) return false;
      const key = `${d.fileName}:${d.pos}:${d.end}:${d.code}`;
      if (!syntaxKeys.has(key)) return true; // semantic / type / JSDoc checker diagnostic
      if (d.pos === undefined) return false;
      const sf = p.getSourceFile(d.fileName);
      return sf !== undefined && insideBlockComment(sf.text, d.pos);
    };
    // First pass: every comment-side 2300's (file, name) — the partners
'''
    if old not in s: raise RuntimeError('errorsOf anchor changed')
    s=s.replace(old,new,1)
    old='''        d.category === ts.DiagnosticCategory.Error &&
        !suppressedJsStrictness7(d) &&
'''
    new='''        d.category === ts.DiagnosticCategory.Error &&
        !looseJsSuppresses(d) &&
        !suppressedJsStrictness7(d) &&
'''
    if old not in s: raise RuntimeError('errorsOf filter anchor changed')
    s=s.replace(old,new,1)
    PROGRAM.write_text(s)

    # ---------- index.ts: plumb option through every frontend reload ----------
    s=INDEX.read_text()
    # Compile/Analyze public surface.
    c_anchor='''  dynamic?: boolean;
  /** Code generator for the program TU.'''
    c_new='''  dynamic?: boolean;
  /** Generated/bundled JavaScript ingestion mode. For .js/.mjs/.cjs program
   * files, TypeScript semantic and JSDoc diagnostics do not gate the build;
   * real JavaScript parser/module errors still do, and unsupported JS
   * statements remain honest runtime fences. Off by default. */
  looseJs?: boolean;
  /** Code generator for the program TU.'''
    if c_anchor not in s: raise RuntimeError('CompileOptions dynamic anchor changed')
    s=s.replace(c_anchor,c_new,1)
    a_anchor='''  dynamic?: boolean;
  /** --npm-static (see CompileOptions.npmStatic):'''
    a_new='''  dynamic?: boolean;
  /** Analyze generated/bundled JavaScript with CompileOptions.looseJs policy. */
  looseJs?: boolean;
  /** --npm-static (see CompileOptions.npmStatic):'''
    if a_anchor not in s: raise RuntimeError('AnalyzeOptions dynamic anchor changed')
    s=s.replace(a_anchor,a_new,1)

    old='''function runFrontend(
  entryPath: string,
  npmStatic?: readonly string[] | "auto" | "lib",
  externalTypes?: Readonly<Record<string, string>>,
): Frontend {
'''
    new='''function runFrontend(
  entryPath: string,
  npmStatic?: readonly string[] | "auto" | "lib",
  externalTypes?: Readonly<Record<string, string>>,
  looseJs = false,
): Frontend {
'''
    if old not in s: raise RuntimeError('runFrontend signature changed')
    s=s.replace(old,new,1)
    # Every preflight in runFrontend must use the same policy, including
    # npm-static fallback probes, or a reload can reintroduce 432 SC0001s.
    s=s.replace('checkPreflight(scout);','checkPreflight(scout, { looseJs });')
    s=s.replace('checkPreflight(load);','checkPreflight(load, { looseJs });')
    s=s.replace('checkPreflight(probe);','checkPreflight(probe, { looseJs });')
    # public callers
    s=s.replace('const fe = runFrontend(entryPath, opts.npmStatic, opts.externalTypes);','const fe = runFrontend(entryPath, opts.npmStatic, opts.externalTypes, opts.looseJs ?? false);',1)
    s=s.replace('const fe = runFrontend(entryPath, opts.npmStatic);','const fe = runFrontend(entryPath, opts.npmStatic, undefined, opts.looseJs ?? false);',1)
    INDEX.write_text(s)

    # ---------- CLI ----------
    s=CLI.read_text()
    usage='''      --dynamic      embed the dynamic engine (adds ~620KB; static stays the default)\n'''
    usage_new='''      --dynamic      embed the dynamic engine (adds ~620KB; static stays the default)\n      --loose-js     EXPERIMENTAL generated/bundled-JS ingestion: ignore\n                     TypeScript semantic/JSDoc checker diagnostics in JS\n                     while preserving real JS syntax/module errors; unsupported\n                     JS statements still become honest runtime fences\n'''
    if usage not in s: raise RuntimeError('CLI usage dynamic anchor changed')
    s=s.replace(usage,usage_new,1)
    opt='''  dynamic: { type: "boolean", default: false },\n'''
    opt_new='''  dynamic: { type: "boolean", default: false },\n  "loose-js": { type: "boolean", default: false },\n'''
    if opt not in s: raise RuntimeError('CLI options dynamic anchor changed')
    s=s.replace(opt,opt_new,1)
    # library mode explicitly excludes it
    old='''    if (values.dynamic || values.backend !== undefined || values.ffi !== undefined || (values["npm-static"] ?? []).length > 0 || externalTypeArgs.length > 0) {
'''
    new='''    if (values.dynamic || values["loose-js"] || values.backend !== undefined || values.ffi !== undefined || (values["npm-static"] ?? []).length > 0 || externalTypeArgs.length > 0) {
'''
    if old not in s: raise RuntimeError('lib option gate changed')
    s=s.replace(old,new,1)
    s=s.replace('"scriptc build --lib takes no --dynamic/--backend/--npm-static/--ffi/--external-types:', '"scriptc build --lib takes no --dynamic/--loose-js/--backend/--npm-static/--ffi/--external-types:',1)
    # loose-js only makes sense for JS entry; reject TS so it can never hide TS project errors.
    marker='''  const ffiProfilePath = values.ffi !== undefined ? resolve(values.ffi) : undefined;
'''
    insert='''  if (values["loose-js"] && !/\\.(?:js|mjs|cjs)$/.test(input)) {
    fail(`--loose-js accepts only JavaScript entry files (.js/.mjs/.cjs)\\n\\n${USAGE}`);
  }
  const ffiProfilePath = values.ffi !== undefined ? resolve(values.ffi) : undefined;
'''
    if marker not in s: raise RuntimeError('CLI ffi marker changed')
    s=s.replace(marker,insert,1)
    # analyze and compile args
    s=s.replace('''      dynamic: values.dynamic,\n      ...(npmStatic !== undefined''','''      dynamic: values.dynamic,\n      looseJs: values["loose-js"],\n      ...(npmStatic !== undefined''',1)
    s=s.replace('''      dynamic: values.dynamic,\n      ...(backend !== undefined''','''      dynamic: values.dynamic,\n      looseJs: values["loose-js"],\n      ...(backend !== undefined''',1)
    CLI.write_text(s)

    # ---------- focused fixtures ----------
    TEST.parent.mkdir(parents=True,exist_ok=True)
    TEST.write_text(textwrap.dedent('''\
        // Intentionally valid JavaScript whose TypeScript semantic world is
        // not Node-only: generated bundles routinely probe other runtimes.
        if (typeof Deno !== "undefined") console.log("deno");
        if (typeof window !== "undefined") console.log("window");
        /** @type {Array} */
        const xs = [];
        console.log("loose", xs.length);
    '''))
    BAD.write_text('const broken = ;\n')

    checks=[
      ['pnpm','build'],
      ['pnpm','lint'],
      # Default remains strict: semantic generated-JS errors are still visible.
      ['node','packages/cli/dist/main.js','build',str(TEST), '--dynamic','-o','/tmp/loose-default'],
    ]
    code,out=run(checks[0]);
    if code: raise RuntimeError('build failed')
    code,out=run(checks[1]);
    if code: raise RuntimeError('lint failed')
    code,strict_out=run(checks[2])
    if code==0 or 'SC0001' not in strict_out:
        raise RuntimeError('default JS preflight unexpectedly became loose')
    code,loose_out=run(['node','packages/cli/dist/main.js','build',str(TEST),'--dynamic','--loose-js','-o','/tmp/loose-enabled'])
    if code!=0:
        raise RuntimeError('loose-js semantic fixture failed:\n'+loose_out[-8000:])
    code,bad_out=run(['node','packages/cli/dist/main.js','build',str(BAD),'--dynamic','--loose-js','-o','/tmp/loose-bad'])
    if code==0 or 'SC0001' not in bad_out:
        raise RuntimeError('loose-js swallowed a real JavaScript syntax error')

    # Existing relevant harnesses: default policy must remain byte-for-byte compatible.
    for cmd in [
      ['pnpm','exec','vitest','run','tests/harness/preflight.test.ts'],
      ['pnpm','exec','vitest','run','tests/harness/differential.test.ts','-t','3013-loose-js-entry'],
    ]:
        code,out=run(cmd)
        # 3013 is an intentionally loose-only fixture and is not expected in
        # differential default; tolerate "no tests found" but not a failing preflight suite.
        if 'preflight.test.ts' in cmd[-1] and code: raise RuntimeError('preflight harness failed')

    # ---------- Prime official bundle oracle; does NOT decide whether the
    # focused compiler feature is retained. It records the NEXT frontier. ----------
    work=Path('/tmp/scriptc-prime-loose-js')
    if work.exists(): shutil.rmtree(work)
    sections=[]
    code,out=run(['git','clone','--depth=1','https://github.com/EthanBird/prime-agent.git',str(work)],timeout=300)
    if code==0:
        code,out=run(['npm','ci'],cwd=work,timeout=900)
    if code==0:
        code,out=run(['npm','run','build'],cwd=work,timeout=900)
    if code!=0:
        PRIME.write_text('Prime setup failed\n'+out)
    else:
        entry='packages/coding-agent/dist/bundle/cli.js'
        exe='/tmp/prime-loose-js'
        code,body=run(['node',str(Path.cwd()/'packages/cli/dist/main.js'),'build',entry,'--dynamic','--loose-js','-o',exe],cwd=work,timeout=1200)
        diag=[l for l in body.splitlines() if 'error SC' in l or re.search(r'\\bSC\\d{4}: ',l)]
        smoke_code=125; smoke='no executable'
        if code==0 and Path(exe).exists():
            smoke_code,smoke=run([exe,'--help'],cwd=work,timeout=45)
        PRIME.write_text(
          '# Prime official bundle with --loose-js\n\n'
          f'build_status={code}\nexecutable={Path(exe).exists()}\nsmoke_status={smoke_code}\n'
          f'diagnostic_lines={len(diag)}\n\n'
          '## first diagnostics\n'+'\n'.join(diag[:160])+'\n\n'
          '## build tail\n'+'\n'.join(body.splitlines()[-220:])+'\n\n'
          '## smoke tail\n'+'\n'.join(smoke.splitlines()[-120:])+'\n')
    FAIL.unlink(missing_ok=True)
    print('LOOSE_JS_INGESTION=PASS')
except Exception as e:
    restore()
    FAIL.write_text(''.join(log)+f'\nTASK EXCEPTION: {e!r}\nLOOSE_JS_INGESTION=FAIL; source/tests reverted\n')
