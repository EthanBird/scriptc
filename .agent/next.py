from pathlib import Path
import re, shutil, subprocess

OUT=Path('PRIME_WORKSPACE_STATIC_PROBE.txt')
work=Path('/tmp/scriptc-prime-workspace-static-probe')
if work.exists(): shutil.rmtree(work)

def run(cmd,cwd=None,timeout=900):
    p=subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    return p.returncode,p.stdout

code,text=run(['pnpm','build'],timeout=300)
if code:
    OUT.write_text('scriptc build failed\n'+text); raise SystemExit(0)
code,text=run(['git','clone','--depth=1','https://github.com/EthanBird/prime-agent.git',str(work)],timeout=300)
if code:
    OUT.write_text('Prime clone failed\n'+text); raise SystemExit(0)
for cmd in (['npm','ci'],['npm','run','build']):
    code,text=run(cmd,cwd=work,timeout=900)
    if code:
        OUT.write_text('Prime setup failed: '+' '.join(cmd)+'\n'+text); raise SystemExit(0)

cli=str(Path.cwd()/'packages/cli/dist/main.js')
entry='packages/coding-agent/src/cli-main.ts'
variants=[
 ('dynamic',['--dynamic']),
 ('npm-static-auto',['--dynamic','--npm-static','auto']),
 ('workspace-explicit',['--dynamic','--npm-static','@earendil-works/pi-tui,@earendil-works/pi-agent-core,@earendil-works/pi-ai']),
]
sections=[]
for name,flags in variants:
    out=Path('/tmp')/f'prime-{name}'
    out.unlink(missing_ok=True)
    try: status,body=run(['node',cli,'build',entry,*flags,'-o',str(out)],cwd=work,timeout=900)
    except subprocess.TimeoutExpired as e:
        status=124; body=(e.stdout or '')+'\n[TIMEOUT]\n'
    diags=[l for l in body.splitlines() if 'error SC' in l or re.search(r'\bSC\d{4}: ',l)]
    codes={}
    for l in diags:
        m=re.search(r'(SC\d{4})',l)
        if m: codes[m.group(1)]=codes.get(m.group(1),0)+1
    smoke_status=125; smoke='no executable'
    if status==0 and out.exists():
        try: smoke_status,smoke=run([str(out),'--help'],cwd=work,timeout=30)
        except subprocess.TimeoutExpired as e: smoke_status,smoke=124,(e.stdout or '')+'\n[TIMEOUT]\n'
    sections.append(
      f'## {name}\n'
      f'build_status={status}\nexecutable={out.exists()}\nsmoke_status={smoke_status}\n'
      f'diagnostic_lines={len(diags)}\ncodes={dict(sorted(codes.items()))}\n\n'
      '### first diagnostics\n'+'\n'.join(diags[:120])+'\n\n'
      '### build tail\n'+'\n'.join(body.splitlines()[-160:])+'\n\n'
      '### smoke tail\n'+'\n'.join(smoke.splitlines()[-100:])+'\n')
OUT.write_text('# Prime Agent workspace staticization probe\n\n'+
 'Compares dynamic-only, npm-static auto, and explicit Prime workspace staticization on the same Prime main.\n\n'+
 '\n\n'.join(sections))
