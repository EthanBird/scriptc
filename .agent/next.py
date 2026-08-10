from pathlib import Path
import subprocess,traceback
REPORT=Path('WORKER_VAR_HOIST_FUNCTION_PROBE.txt')
def run(args,timeout=900):
 cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); return cp.returncode,cp.stdout or ''
try:
 rc,out=run(['pnpm','build'],1200)
 if rc: raise RuntimeError(out[-5000:])
 f=Path('/tmp/var-forward-function.js')
 f.write_text('''function main() {\n  class Prompt { prompt = source_default.green("prime-agent> "); }\n  const make = () => new Prompt();\n  var source_default = { green: (s) => s };\n  return make().prompt;\n}\nconsole.log(main());\n''')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build',str(f),'--dynamic','--loose-js','-o','/tmp/var-forward-function-bin'])
 lines=[f'build_status={rc}',*out.splitlines()[-160:]]
 if rc==0:
  rr,ro=run(['/tmp/var-forward-function-bin'],60); lines += [f'run_status={rr}',repr(ro)]
 REPORT.write_text('\n'.join(lines)+'\n')
except Exception as e:
 REPORT.write_text('FUNCTION_PROBE_FAIL\n'+repr(e)+'\n'+traceback.format_exc())
