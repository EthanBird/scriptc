from pathlib import Path
import os,re,shutil,subprocess,traceback
SRC=Path('packages/compiler/src/frontend/lowering/lower-classes.ts'); orig=SRC.read_text(); REPORT=Path('WORKER_FIELDINIT_FENCE_RESULT.txt'); FAIL=Path('WORKER_FIELDINIT_FENCE_FAILURE.txt'); log=[]
def run(args,cwd=None,env=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); out=cp.stdout or ''; log.extend(['$ '+' '.join(map(str,args)),*out.splitlines()[-240:],f'[exit {cp.returncode}]']); return cp.returncode,out
ok=True
try:
 start=orig.index('export function fieldInitStmts')
 end=orig.index('\n/**',start+50)
 seg=orig[start:end]
 old1='''      L.stats.statementsTotal++;\n      L.bumpFileStat(locOf(f.initializer).file, "total");\n      try {\n'''
 new1='''      L.stats.statementsTotal++;\n      L.bumpFileStat(locOf(f.initializer).file, "total");\n      const diagsBefore = L.diags.length;\n      try {\n'''
 if seg.count(old1)!=1: raise RuntimeError(f'field-init prologue anchor={seg.count(old1)}')
 seg=seg.replace(old1,new1,1)
 old2='''      } catch (e) {\n        if (!(e instanceof PoisonError)) throw e;\n        L.stats.statementsFailed++;\n        L.bumpFileStat(locOf(f.initializer).file, "failed");\n      }\n'''
 new2='''      } catch (e) {\n        if (!(e instanceof PoisonError)) throw e;\n        L.stats.statementsFailed++;\n        L.bumpFileStat(locOf(f.initializer).file, "failed");\n        // JS statements already defer unsupported lowering to a runtimeFence.\n        // Class field initializers are executable statements too, but historically\n        // left their poison diagnostic on the build. Under --loose-js mirror the\n        // statement rule: constructing this class reaches the fence; a program\n        // that never constructs it can still compile and run. ICEs remain build\n        // failures, and regular JS/TS keeps the historical posture.\n        if (L.looseJs && isJsSourceFile(f.initializer.getSourceFile()) && L.diagSink === null) {\n          const captured = L.diags.splice(diagsBefore);\n          const ice = captured.filter((d) => d.code === "SC9001");\n          if (ice.length > 0) {\n            L.diags.push(...captured);\n          } else {\n            L.runtimeFences.push(...captured);\n            const first = captured[0];\n            const floc = first?.loc ?? locOf(f.initializer);\n            const fsf = L.program.getSourceFile(floc.file) ?? f.initializer.getSourceFile();\n            const pos = ts.getLineAndCharacterOfPosition(fsf, floc.start);\n            out.push({\n              kind: "runtimeFence",\n              code: first?.code ?? "SC1090",\n              message: first\n                ? `${first.message} [${first.code} at ${floc.file}:${pos.line + 1}]`\n                : `this class field initializer has no static lowering [SC1090 at ${floc.file}:${pos.line + 1}]`,\n              loc: locOf(f.initializer),\n            });\n          }\n        }\n      }\n'''
 if seg.count(old2)!=1: raise RuntimeError(f'field-init catch anchor={seg.count(old2)}')
 seg=seg.replace(old2,new2,1)
 SRC.write_text(orig[:start]+seg+orig[end:])
except Exception as e: log += ['PATCH '+repr(e),traceback.format_exc()]; ok=False
ENV=os.environ.copy()
if ok:
 for cmd in (["pnpm","build"],["pnpm","lint"]):
  rc,_=run(cmd,env=ENV)
  if rc: ok=False; break
if ok:
 root=Path('/tmp/fieldinit-worker'); root.mkdir(exist_ok=True)
 cold=root/'cold.js'; cold.write_text('''class Context { constructor(value) { this.value = value; } }\nclass Connection { context = new Context(this); }\nconsole.log("ok");\n''')
 hot=root/'hot.js'; hot.write_text('''class Context { constructor(value) { this.value = value; } }\nclass Connection { context = new Context(this); }\nnew Connection();\nconsole.log("bad");\n''')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build',str(cold),'--dynamic','--loose-js','-o',str(root/'cold-bin')],env=ENV,timeout=900)
 if rc!=0: ok=False
 if rc==0:
  rr,ro=run([str(root/'cold-bin')],env=ENV,timeout=60)
  if rr!=0 or ro.strip()!='ok': ok=False; log.append('cold unsupported field initializer should not run its fence')
 rc2,out2=run(['node',cli,'build',str(hot),'--dynamic','--loose-js','-o',str(root/'hot-bin')],env=ENV,timeout=900)
 if rc2!=0: ok=False; log.append('hot unsupported field initializer should compile to runtime fence')
 if rc2==0:
  rr2,ro2=run([str(root/'hot-bin')],env=ENV,timeout=60)
  if rr2==0 or 'dynamically-executed' not in ro2: ok=False; log.append('hot field initializer did not execute the deferred boundary fence')
prime=[]
if ok:
 p=Path('/tmp/prime-fieldinit-fence'); shutil.rmtree(p,ignore_errors=True)
 rc,_=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],env=ENV,timeout=300)
 if rc==0: rc,_=run(['npm','ci'],cwd=p,env=ENV,timeout=1200)
 if rc==0: rc,_=run(['npm','run','build'],cwd=p,env=ENV,timeout=1200)
 bs=126; ss=125; bout=''; sout=''
 if rc==0:
  cli=str(Path.cwd()/'packages/cli/dist/main.js'); outbin='/tmp/prime-fieldinit-fence-bin'
  bs,bout=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',outbin],cwd=p,env=ENV,timeout=1200)
  if bs==0 and Path(outbin).exists(): ss,sout=run(['timeout','20s',outbin,'--help'],cwd=p,env=ENV,timeout=30)
 diags=[x for x in bout.splitlines() if re.search(r'\bSC\d{4}:',x)]
 prime=[f'prime_build_status={bs}',f'prime_smoke_status={ss}',f'prime_diagnostic_count={len(diags)}','--- diagnostics ---',*diags,'--- smoke ---',*sout.splitlines()[-120:]]
if not ok:
 SRC.write_text(orig); FAIL.write_text('\n'.join(log+['FIELDINIT_FENCE=FAIL; source reverted'])+'\n')
else:
 if FAIL.exists(): FAIL.unlink()
 REPORT.write_text('\n'.join(['FIELDINIT_FENCE=PASS',*prime])+'\n')
