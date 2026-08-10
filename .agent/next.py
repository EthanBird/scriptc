from pathlib import Path
import subprocess, traceback
REPORT=Path('WORKER_CLASSVAL_MINIMAL.txt')
def run(args,timeout=900):
 cp=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout); return cp.returncode,cp.stdout or ''
try:
 rc,out=run(['pnpm','build'],1200)
 if rc: raise RuntimeError(out[-5000:])
 cli=str(Path.cwd()/'packages/cli/dist/main.js'); root=Path('/tmp/classval-min'); root.mkdir(exist_ok=True)
 probes={
 'untyped': '''class MatchRecord { store = new Map(); add(t,e){ this.store.set(t,e); } get(t){ return this.store.get(t); } } class P { matches = new MatchRecord(); } const p=new P(); p.matches.add("x",3); console.log(p.matches.get("x"));''',
 'typed-string': '''class MatchRecord { /** @type {Map<string, number>} */ store = new Map(); add(t,e){ this.store.set(t,e); } get(t){ return this.store.get(t); } } class P { matches = new MatchRecord(); } const p=new P(); p.matches.add("x",3); console.log(p.matches.get("x"));''',
 'typed-object': '''class Key { constructor(n){this.n=n;} } class SubWalks { /** @type {Map<Key, string[]>} */ store=new Map(); add(t,e){ const s=this.store.get(t); s?s.push(e):this.store.set(t,[e]); } get(t){return this.store.get(t);} } class P { subwalks=new SubWalks(); } const p=new P(), k=new Key(1); p.subwalks.add(k,"a"); console.log(p.subwalks.get(k).join(","));'''
 }
 lines=[]
 for name,src in probes.items():
  f=root/(name+'.js'); f.write_text(src+'\n'); outbin=str(root/(name+'.bin'))
  rc,out=run(['node',cli,'build',str(f),'--dynamic','--loose-js','-o',outbin])
  lines += [f'\n=== {name} build={rc} ===',*out.splitlines()[-160:]]
  if rc==0:
   rr,ro=run([outbin],60); lines += [f'run={rr}',repr(ro)]
 REPORT.write_text('\n'.join(lines)+'\n')
except Exception as e:
 REPORT.write_text('CLASSVAL_MINIMAL=FAIL\n'+repr(e)+'\n'+traceback.format_exc())
