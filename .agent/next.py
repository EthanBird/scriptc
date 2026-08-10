from pathlib import Path
import subprocess, traceback
REPORT=Path('WORKER_VAR_HOIST_MINIMAL.txt')
def run(args,timeout=900):
 cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); return cp.returncode,cp.stdout or ''
try:
 rc,out=run(['pnpm','build'],1200)
 if rc: raise RuntimeError(out[-5000:])
 tmp=Path('/tmp/var-hoist-minimal.js')
 tmp.write_text('''class Prompt {\n  prompt = source_default.green("prime-agent> ");\n}\nvar source_default = { green: (s) => s };\nconsole.log(new Prompt().prompt);\n''')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build',str(tmp),'--dynamic','--loose-js','-o','/tmp/var-hoist-minimal-bin'])
 lines=[f'build_status={rc}',*out.splitlines()[-160:]]
 if rc==0:
  rr,ro=run(['/tmp/var-hoist-minimal-bin'],60); lines += [f'run_status={rr}',repr(ro)]
 REPORT.write_text('\n'.join(lines)+'\n')
except Exception as e:
 REPORT.write_text('VAR_HOIST_MINIMAL=FAIL\n'+repr(e)+'\n'+traceback.format_exc())
