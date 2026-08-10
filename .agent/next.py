from pathlib import Path
import subprocess,traceback
REPORT=Path('WORKER_VAR_HOIST_NARROW_PROBE.txt')
def run(args,timeout=900):
 cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); return cp.returncode,cp.stdout or ''
try:
 rc,out=run(['pnpm','build'],1200)
 if rc: raise RuntimeError(out[-5000:])
 f=Path('/tmp/var-forward-narrow.js')
 f.write_text('''function main() {\n  class Chalk { green(s) { return s; } }\n  class Prompt { prompt = source_default.green("prime-agent> "); }\n  const make = () => new Prompt();\n  var source_default = new Chalk();\n  return make().prompt;\n}\nconst result = main();\nconsole.log(`${result}`);\n''')
 cli=str(Path.cwd()/'packages/cli/dist/main.js')
 rc,out=run(['node',cli,'build',str(f),'--dynamic','--loose-js','-o','/tmp/var-forward-narrow-bin'])
 lines=[f'build_status={rc}',*out.splitlines()[-180:]]
 if rc==0:
  rr,ro=run(['/tmp/var-forward-narrow-bin'],60); lines += [f'run_status={rr}',repr(ro)]
 REPORT.write_text('\n'.join(lines)+'\n')
except Exception as e:
 REPORT.write_text('NARROW_PROBE_FAIL\n'+repr(e)+'\n'+traceback.format_exc())
