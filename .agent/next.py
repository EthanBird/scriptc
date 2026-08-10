from pathlib import Path
import os
import subprocess
import sys

BASE = "52d13847a66506e99a309c450501701784e86346:.agent/next.py"
cp = subprocess.run(["git", "show", BASE], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if cp.returncode != 0:
    raise SystemExit(cp.stderr)
script = cp.stdout

corpus_old = "CORPUS.write_text('''// Present Error messages use JS ToString, except undefined == omitted."
corpus_new = "CORPUS.write_text('''// @dynamic\n// Present Error messages use JS ToString, except undefined == omitted."
if script.count(corpus_old) != 1:
    raise SystemExit(f"expected one corpus anchor, found {script.count(corpus_old)}")
script = script.replace(corpus_old, corpus_new, 1)

cond_old = '''    const cond: IrExpr = {\n      kind: "bin",\n      op: "===",\n      left: typeofV,\n      right: { kind: "strLit", value: "undefined", type: STRING, loc },\n      type: BOOL,\n      loc,\n    };'''
cond_new = '''    const cond: IrExpr = {\n      kind: "strEq",\n      negated: false,\n      left: typeofV,\n      right: { kind: "strLit", value: "undefined", type: STRING, loc },\n      type: BOOL,\n      loc,\n    };'''
if script.count(cond_old) != 1:
    raise SystemExit(f"expected one condition anchor, found {script.count(cond_old)}")
script = script.replace(cond_old, cond_new, 1)

retry = Path("/tmp/scriptc-error-str-eq-valid.py")
retry.write_text(script, encoding="utf-8")
os.execv(sys.executable, [sys.executable, str(retry)])
