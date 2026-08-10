from pathlib import Path
import os,re,shutil,subprocess,traceback
SRC=Path('packages/compiler/src/frontend/lowering/lower-classes.ts'); orig=SRC.read_text(); REPORT=Path('WORKER_FIELDINIT_TARGETED_RESULT.txt'); FAIL=Path('WORKER_FIELDINIT_TARGETED_FAILURE.txt'); log=[]
def run(args,cwd=None,env=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); out=cp.stdout or ''; log.extend(['$ '+' '.join(map(str,args)),*out.splitlines()[-240:],f'[exit {cp.returncode}]']); return cp.returncode,out
ok=True
try:
 start=orig.index('export function fieldInitStmts'); end=orig.index('\n/**',start+50); seg=orig[start:end]
 old1='''      L.stats.statementsTotal++;\n      L.bumpFileStat(locOf(f.initializer).file, "total");\n      try {\n'''
 new1='''      L.stats.statementsTotal++;\n      L.bumpFileStat(locOf(f.initializer).file, "total");\n      const diagsBefore = L.diags.length;\n      try {\n'''
 if seg.count(old1)!=1: raise RuntimeError(f'field-init prologue anchor={seg.count(old1)}')
 seg=seg.replace(old1,new1,1)
 old2='''      } catch (e) {\n        if (!(e instanceof PoisonError)) throw e;\n        L.stats.statementsFailed++;\n        L.bumpFileStat(locOf(f.initializer).file, "failed");\n      }\n'''
 new2='''      } catch (e) {\n        if (!(e instanceof PoisonError)) throw e;\n        L.stats.statementsFailed++;\n        L.bumpFileStat(locOf(f.initializer).file, "failed");\n        if (L.looseJs && isJsSourceFile(f.initializer.getSourceFile()) && L.diagSink === null) {\n          const captured = L.diags.slice(diagsBefore);\n          const deferrable = captured.length > 0 && captured.every((d) =>\n            d.code !== "SC9001" && (\n              d.message.includes("into dynamically-executed ('any'-typed) code") ||\n              (d.message.includes("new TextDecoder") && d.message.includes("has no scriptc lowering yet"))\n            )\n          );\n          if (deferrable) {\n            L.diags.splice(diagsBefore);\n            L.runtimeFences.push(...captured);\n            const first = captured[0]!;\n            const fsf = L.program.getSourceFile(first.loc.file) ?? f.initializer.getSourceFile();\n            const pos = ts.getLineAndCharacterOfPosition(fsf, first.loc.start);\n            out.push({\n              kind: "runtimeFence",\n              code: first.code,\n              message: `${first.message} [${first.code} at ${first.loc.file}:${pos.line + 1}]`,\n              loc: locOf(f.initializer),\n            });\n          }\n        }\n      }\n'''
 if seg.count(old2)!=1: raise RuntimeError(f'field-init catch anchor={seg.count(old2)}')
 seg=seg.replace(old2,new2,1); SRC.write_text(orig[:start]+seg+orig[end:])
except Exception as e: log += ['PATCH '+repr(e),traceback.format_exc()]; ok=False
ENV=os.environ.copy()
if ok:
 for cmd in (["pnpm","build"],["pnpm","lint"]):
  rc,_=run(cmd,env=ENV)
  if rc: ok=False; break
if ok:
 root=Path('/tmp/fieldinit-targeted'); root.mkdir(exist_ok=True)
 cold=root/'cold.js'; cold.write_text('''class Context { constructor(value) { this.value = value; } }\nclass Connection { context = new Context(this); }\nconsole.log("ok");\n''')
 hot=root/'hot.js'; hot.write_text('''class Context { constructor(value) { this.value = value; } }\nclass Connection { context = new Context(this); }\nnew Connection();\nconsole.log("bad");\n''')
 tcold=root/'tcold.js'; tcold.write_text('''class DecoderHolder { decoder = new TextDecoder(); }\nconsole.log("ok");\n''')
 thot=root/'thot.js'; thot.write_text('''class DecoderHolder { decoder = new TextDecoder(); }\nnew DecoderHolder();\nconsole.log("bad");\n''')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 for name,f in [('cold',cold),('tcold',tcold)]:
  outbin=str(root/(name+'-bin')); rc,out=run(['node',cli,'build',str(f),'--dynamic','--loose-js','-o',outbin],env=ENV,timeout=900)
  if rc!=0: ok=False; log.append(name+' build failed'); continue
  rr,ro=run([outbin],env=ENV,timeout=60)
  if rr!=0 or ro.strip()!='ok': ok=False; log.append(name+' cold path mismatch')
 for name,f,needle in [('hot',hot,'dynamically-executed'),('thot',thot,'new TextDecoder')]:
  outbin=str(root/(name+'-bin')); rc,out=run(['node',cli,'build',str(f),'--dynamic','--loose-js','-o',outbin],env=ENV,timeout=900)
  if rc!=0: ok=False; log.append(name+' should compile to runtime fence'); continue
  rr,ro=run([outbin],env=ENV,timeout=60)
  if rr==0 or needle not in ro: ok=False; log.append(name+' did not execute targeted runtime fence')
prime=[]
if ok:
 p=Path('/tmp/prime-fieldinit-targeted'); shutil.rmtree(p,ignore_errors=True)
 rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],env=ENV,timeout=300)
 if rc==0: rc,_=run(['npm','ci'],cwd=p,env=ENV,timeout=1200)
 if rc==0: rc,_=run(['npm','run','build'],cwd=p,env=ENV,timeout=1200)
 bs=126; ss=125; bout=''; sout=''
 if rc==0:
  cli=str(Path.cwd()/'packages/cli/dist/main.js'); outbin='/tmp/prime-fieldinit-targeted-bin'
  bs,bout=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',outbin],cwd=p,env=ENV,timeout=1200)
  if bs==0 and Path(outbin).exists(): ss,sout=run(['timeout','20s',outbin,'--help'],cwd=p,env=ENV,timeout=30)
 diags=[x for x in bout.splitlines() if re.search(r'\bSC\d{4}:',x)]
 prime=[f'prime_build_status={bs}',f'prime_smoke_status={ss}',f'prime_diagnostic_count={len(diags)}','--- diagnostics ---',*diags,'--- smoke ---',*sout.splitlines()[-120:]]
if not ok:
 SRC.write_text(orig); FAIL.write_text('\n'.join(log+['FIELDINIT_TARGETED=FAIL; source reverted'])+'\n')
else:
 if FAIL.exists(): FAIL.unlink()
 REPORT.write_text('\n'.join(['FIELDINIT_TARGETED=PASS',*prime])+'\n')
