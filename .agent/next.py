from pathlib import Path
import re, shutil, subprocess

OUT=Path('PRIME_LOOSE_JS_FOCUSED_RESULT.txt')
work=Path('/tmp/scriptc-prime-loose-focused')
if work.exists(): shutil.rmtree(work)

def run(cmd,cwd=None,timeout=1200):
  try:
    p=subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    return p.returncode,p.stdout
  except subprocess.TimeoutExpired as e:
    return 124,(e.stdout or '')+'\n[TIMEOUT]\n'

code,out=run(['pnpm','build'],timeout=300)
if code:
  OUT.write_text('scriptc build failed\n'+out); raise SystemExit(0)
code,out=run(['git','clone','--depth=1','https://github.com/EthanBird/prime-agent.git',str(work)],timeout=300)
if code:
  OUT.write_text('Prime clone failed\n'+out); raise SystemExit(0)
for cmd in (['npm','ci'],['npm','run','build']):
  code,out=run(cmd,cwd=work,timeout=900)
  if code:
    OUT.write_text('Prime setup failed: '+' '.join(cmd)+'\n'+out); raise SystemExit(0)

entry='packages/coding-agent/dist/bundle/cli.js'
exe='/tmp/prime-loose-focused'
cli=str(Path.cwd()/'packages/cli/dist/main.js')
code,body=run(['node',cli,'build',entry,'--dynamic','--loose-js','-o',exe],cwd=work,timeout=1200)
diags=[l for l in body.splitlines() if 'error SC' in l or re.search(r'\bSC\d{4}: ',l)]
codes={}
for l in diags:
  m=re.search(r'(SC\d{4})',l)
  if m: codes[m.group(1)]=codes.get(m.group(1),0)+1
smoke=125; smoke_out='no executable'
if code==0 and Path(exe).exists(): smoke,smoke_out=run([exe,'--help'],cwd=work,timeout=60)
OUT.write_text(
  '# Prime official bundle on validated --loose-js\n\n'
  f'build_status={code}\nexecutable={Path(exe).exists()}\nsmoke_status={smoke}\n'
  f'diagnostic_lines={len(diags)}\ncodes={dict(sorted(codes.items()))}\n\n'
  '## first diagnostics\n'+'\n'.join(diags[:200])+'\n\n'
  '## build tail\n'+'\n'.join(body.splitlines()[-260:])+'\n\n'
  '## smoke tail\n'+'\n'.join(smoke_out.splitlines()[-160:])+'\n'
)
