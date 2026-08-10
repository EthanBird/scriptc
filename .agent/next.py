from pathlib import Path
import os
import subprocess
import sys

BASE = "52d13847a66506e99a309c450501701784e86346:.agent/next.py"
cp = subprocess.run(["git", "show", BASE], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if cp.returncode != 0:
    raise SystemExit(cp.stderr)
script = cp.stdout
needle = "CORPUS.write_text('''// Present Error messages use JS ToString, except undefined == omitted."
replacement = "CORPUS.write_text('''// @dynamic\n// Present Error messages use JS ToString, except undefined == omitted."
if script.count(needle) != 1:
    raise SystemExit(f"expected one corpus anchor, found {script.count(needle)}")
script = script.replace(needle, replacement, 1)
retry = Path("/tmp/scriptc-error-dynamic-retry.py")
retry.write_text(script, encoding="utf-8")
os.execv(sys.executable, [sys.executable, str(retry)])
