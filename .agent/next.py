from pathlib import Path
import os,re,shutil,subprocess,traceback
SRC=Path('packages/compiler/src/frontend/lowering/lower-classes.ts')
REPORT=Path('WORKER_METHODVAL_RESULT.txt'); FAIL=Path('WORKER_METHODVAL_FAILURE.txt')
orig=SRC.read_text(encoding='utf-8'); log=[]
def run(args,cwd=None,env=None,timeout=1800):
    cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    out=cp.stdout or ''; log.extend(['$ '+' '.join(map(str,args)),*out.splitlines()[-220:],f'[exit {cp.returncode}]']); return cp.returncode,out
def rep(text,a,b,label):
    n=text.count(a)
    if n!=1: raise RuntimeError(f'{label}: expected one anchor, found {n}')
    return text.replace(a,b,1)
ok=True
try:
    helper='''\n/** `--loose-js` whole-program dead field elimination for generated JS\n * aliases such as Marked's `options = this.setOptions`. A prototype method\n * READ is side-effect-free. If the field's own symbol has no reference\n * anywhere in the non-declaration program graph, defining that own property\n * is unobservable to ordinary code and the problematic first-class method\n * value need not materialize. This is deliberately narrow: a single named\n * reference to the field disables the optimization and preserves the normal\n * bound-method-reference fence. Reflection-only observation is part of the\n * loose-js compatibility posture; regular JS/TS never takes this path. */\nfunction looseJsDeadMethodAliasField(\n  L: Lowerer,\n  decl: ts.ClassLikeDeclaration,\n  member: ts.PropertyDeclaration,\n): boolean {\n  if (!L.looseJs || !isJsSourceFile(decl.getSourceFile())) return false;\n  if (!ts.isIdentifier(member.name) || member.initializer === undefined) return false;\n  const fieldName = member.name.text;\n  let init: ts.Expression = member.initializer;\n  while (ts.isParenthesizedExpression(init)) init = init.expression;\n  if (!ts.isPropertyAccessExpression(init) || init.expression.kind !== ts.SyntaxKind.ThisKeyword) return false;\n  const methodSym = L.checker.getSymbolAtLocation(init.name);\n  if (!methodSym) return false;\n  const realOwnMethod = L.checker.declarationsOf(methodSym).some(\n    (d) => ts.isMethodDeclaration(d) && d.parent === decl && !d.modifiers?.some((m) => m.kind === ts.SyntaxKind.StaticKeyword),\n  );\n  if (!realOwnMethod) return false;\n  const fieldSym = L.checker.getSymbolAtLocation(member.name);\n  if (!fieldSym) return false;\n  let referenced = false;\n  for (const sf of L.program.getSourceFiles()) {\n    if (sf.isDeclarationFile || referenced) continue;\n    ts.walkPreorder(sf, (node) => {\n      if (referenced) return \"skip\";\n      if (node === member.name) return undefined;\n      if (!ts.isIdentifier(node) || node.text !== fieldName) return undefined;\n      const sym = L.checker.getSymbolAtLocation(node);\n      if (sym === fieldSym) { referenced = true; return \"skip\"; }\n      return undefined;\n    });\n  }\n  return !referenced;\n}\n\n'''
    anchor='export function collectClassShapeInner(L: Lowerer, decl: ts.ClassLikeDeclaration, jsNameOverride?: string,\n'
    text=rep(orig,anchor,helper+anchor,'helper insertion')
    anchor2='''          const type = L.irTypeOf(member.name);\n          if (type.kind === "void") L.badType(member.name, L.typeOf(member.name));\n'''
    text=rep(text,anchor2,'''          if (looseJsDeadMethodAliasField(L, decl, member)) continue;\n          const type = L.irTypeOf(member.name);\n          if (type.kind === "void") L.badType(member.name, L.typeOf(member.name));\n''','field insertion')
    SRC.write_text(text,encoding='utf-8')
except Exception as e:
    log += ['PATCH EXCEPTION '+repr(e),traceback.format_exc()]; ok=False
ENV=os.environ.copy()
if ok:
    for cmd in (["pnpm","build"],["pnpm","lint"]):
        rc,_=run(cmd,env=ENV)
        if rc: ok=False; break
if ok:
    root=Path('/tmp/methodval-worker'); root.mkdir(exist_ok=True)
    dead=root/'dead.js'; dead.write_text('''class M {\n  options = this.setOptions;\n  value = 1;\n  setOptions(o) { this.value = o; return this; }\n}\nconst m = new M();\nconsole.log(m.value);\n''')
    live=root/'live.js'; live.write_text('''class M {\n  options = this.setOptions;\n  value = 1;\n  setOptions(o) { this.value = o; return this; }\n}\nconst m = new M();\nconsole.log(typeof m.options);\n''')
    cli=str(Path.cwd()/'packages/cli/dist/main.js')
    rc,out=run(['node',cli,'build',str(dead),'--dynamic','--loose-js','-o',str(root/'dead-bin')],env=ENV,timeout=900)
    if rc!=0: ok=False
    if rc==0:
        rr,ro=run([str(root/'dead-bin')],env=ENV,timeout=60)
        if rr!=0 or ro.strip()!='1': ok=False; log.append('dead-field runtime mismatch')
    rc_live,out_live=run(['node',cli,'build',str(live),'--dynamic','--loose-js','-o',str(root/'live-bin')],env=ENV,timeout=900)
    if rc_live==0 or 'bound method references' not in out_live:
        ok=False; log.append('live field unexpectedly lost method-value fence')
prime=[]
if ok:
    p=Path('/tmp/prime-methodval-final'); shutil.rmtree(p,ignore_errors=True)
    rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],env=ENV,timeout=300)
    if rc==0: rc,_=run(['npm','ci'],cwd=p,env=ENV,timeout=1200)
    if rc==0: rc,_=run(['npm','run','build'],cwd=p,env=ENV,timeout=1200)
    bs=126; ss=125; bout=''; sout=''
    if rc==0:
        cli=str(Path.cwd()/'packages/cli/dist/main.js'); outbin='/tmp/prime-methodval-bin'
        bs,bout=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',outbin],cwd=p,env=ENV,timeout=1200)
        if bs==0 and Path(outbin).exists(): ss,sout=run(['timeout','20s',outbin,'--help'],cwd=p,env=ENV,timeout=30)
    diags=[x for x in bout.splitlines() if re.search(r'\bSC\d{4}:',x)]
    prime=[f'prime_build_status={bs}',f'prime_smoke_status={ss}',f'prime_diagnostic_count={len(diags)}','--- diagnostics ---',*diags,'--- smoke ---',*sout.splitlines()[-80:]]
if not ok:
    SRC.write_text(orig,encoding='utf-8')
    FAIL.write_text('\n'.join(log+['METHODVAL_WORKER=FAIL; source reverted'])+'\n',encoding='utf-8')
else:
    if FAIL.exists(): FAIL.unlink()
    REPORT.write_text('\n'.join(['METHODVAL_WORKER=PASS',*prime])+'\n',encoding='utf-8')
