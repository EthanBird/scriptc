from pathlib import Path
import subprocess, traceback
REPORT=Path('WORKER_CLASSVAL_ROOT_CAUSE.txt')
TMP=Path('/tmp/scriptc-classval-probes'); TMP.mkdir(exist_ok=True)
def run(args,cwd=None,timeout=600):
    cp=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    return cp.returncode,cp.stdout or ''
try:
    rc,out=run(['pnpm','build'])
    if rc: raise RuntimeError(out[-5000:])
    cli=str(Path.cwd()/'packages/cli/dist/main.js')
    probes={
      'matchrecord-untyped': '''class MatchRecord { store = new Map(); add(t,e,s){ let i=(e?2:0)|(s?1:0),r=this.store.get(t); this.store.set(t,r===void 0?i:i&r); } entries(){ return [...this.store.entries()].map(([t,e])=>[t,!!(e&2),!!(e&1)]); } } class P { matches=new MatchRecord(); } console.log(new P().matches.entries().length);''',
      'matchrecord-jsdoc': '''class MatchRecord { /** @type {Map<string, number>} */ store = new Map(); add(t,e,s){ let i=(e?2:0)|(s?1:0),r=this.store.get(t); this.store.set(t,r===void 0?i:i&r); } entries(){ return [...this.store.entries()].map(([t,e])=>[t,!!(e&2),!!(e&1)]); } } class P { matches=new MatchRecord(); } console.log(new P().matches.entries().length);''',
      'subwalks-untyped': '''class SubWalks { store=new Map(); add(t,e){ let s=this.store.get(t); s?s.push(e):this.store.set(t,[e]); } get(t){ let e=this.store.get(t); if(!e) throw new Error("missing"); return e; } entries(){ return [...this.store.entries()]; } } class P { subwalks=new SubWalks(); } console.log(new P().subwalks.entries().length);''',
      'subwalks-string-key': '''class SubWalks { /** @type {Map<string, string[]>} */ store=new Map(); add(t,e){ let s=this.store.get(t); s?s.push(e):this.store.set(t,[e]); } entries(){ return [...this.store.entries()]; } } class P { subwalks=new SubWalks(); } console.log(new P().subwalks.entries().length);''',
      'map-only': '''class C { store=new Map(); } console.log(new C().store.size);''',
    }
    lines=[]
    for name,src in probes.items():
        f=TMP/(name+'.js'); f.write_text(src+'\n',encoding='utf-8')
        outbin=str(TMP/(name+'.bin'))
        rc,out=run(['node',cli,'build',str(f),'--dynamic','--loose-js','-o',outbin])
        lines += [f'\n=== {name} build={rc} ===',*out.splitlines()[-160:]]
        if rc==0:
            rr,ro=run([outbin]); lines += [f'run={rr}',*ro.splitlines()[-40:]]
    REPORT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
except Exception as e:
    REPORT.write_text('CLASSVAL_ROOT_CAUSE=FAIL\n'+repr(e)+'\n'+traceback.format_exc(),encoding='utf-8')
