from pathlib import Path
import os
import subprocess
import sys

BASE = "7075e04a2eacb1e546e428c2935bcd2c45ee6f73:.agent/next.py"
cp = subprocess.run(["git", "show", BASE], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if cp.returncode != 0:
    raise SystemExit(cp.stderr)
script = cp.stdout
old = 'return function (left, right) { return flag ? left : right; };'
new = 'return function (left, right) { return flag ? String(left) : String(right); };'
if script.count(old) != 1:
    raise SystemExit(f"expected one parser fixture anchor, found {script.count(old)}")
script = script.replace(old, new, 1)
retry = Path('/tmp/scriptc-loose-return-typed-output.py')
retry.write_text(script, encoding='utf-8')
os.execv(sys.executable, [sys.executable, str(retry)])
