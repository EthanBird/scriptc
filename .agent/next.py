from pathlib import Path
import re,shutil,subprocess,traceback
REPORT=Path('PRIME_CURRENT_FRONTIER.txt')
def run(args,cwd=None,timeout=1800):
 cp=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); return cp.returncode,cp.stdout or ''
try:
 rc,out=run(['pnpm','build'],timeout=1200)
 if rc: raise RuntimeError(out[-6000:])
 p=Path('/tmp/prime-current-frontier'); shutil.rmtree(p,ignore_errors=True)
 rc,out=run(['git','clone','--depth','1','https://github.com/EthanBird/prime-agent.git',str(p)],timeout=300)
 if rc: raise RuntimeError(out[-5000:])
 for cmd in (['npm','ci'],['npm','run','build']):
  rc,out=run(cmd,cwd=p,timeout=1200)
  if rc: raise RuntimeError(out[-10000:])
 cli=str(Path.cwd()/'packages/cli/dist/main.js'); outbin='/tmp/prime-current-frontier-bin'
 bs,bout=run(['node',cli,'build','packages/coding-agent/dist/bundle/cli.js','--dynamic','--loose-js','-o',outbin],cwd=p,timeout=1200)
 ss=125; sout=''
 if bs==0 and Path(outbin).exists(): ss,sout=run(['timeout','20s',outbin,'--help'],cwd=p,timeout=30)
 diags=[x for x in bout.splitlines() if re.search(r'\bSC\d{4}:',x)]
 REPORT.write_text('\n'.join([f'prime_build_status={bs}',f'prime_smoke_status={ss}',f'prime_diagnostic_count={len(diags)}','--- diagnostics ---',*diags,'--- smoke ---',*sout.splitlines()[-120:]])+'\n')
except Exception as e:
 REPORT.write_text('FRONTIER_FAIL\n'+repr(e)+'\n'+traceback.format_exc())
