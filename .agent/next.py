from pathlib import Path
import os
import re
import shutil
import subprocess

OUT = Path("PRIME_WORKSPACE_STATIC_PROBE.txt")
work = Path("/tmp/scriptc-prime-workspace-static-probe")
if work.exists(): shutil.rmtree(work)
log: list[str] = []

def run(cmd, cwd=None, timeout=900):
    p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    return p.returncode, p.stdout

code, text = run(["pnpm", "build"], timeout=300)
if code != 0:
    OUT.write_text("scriptc build failed\n" + text)
    raise SystemExit(0)

code, text = run(["git", "clone", "--depth=1", "https://github.com/EthanBird/prime-agent.git", str(work)], timeout=300)
if code != 0:
    OUT.write_text("Prime clone failed\n" + text)
    raise SystemExit(0)
code, text = run(["npm", "ci"], cwd=work, timeout=900)
if code != 0:
    OUT.write_text("Prime npm ci failed\n" + text)
    raise SystemExit(0)
code, text = run(["npm", "run", "build"], cwd=work, timeout=900)
if code != 0:
    OUT.write_text("Prime baseline build failed\n" + text)
    raise SystemExit(0)

cli = str(Path.cwd() / "packages/cli/dist/main.js")
entry = "packages/coding-agent/src/cli-main.ts"
variants = [
    ("dynamic", ["--dynamic"]),
    ("npm-static-auto", ["--dynamic", "--npm-static", "auto"]),
    ("workspace-explicit", ["--dynamic", "--npm-static", "@earendil-works/pi-tui,@earendil-works/pi-agent-core,@earendil-works/pi-ai"]),
]
sections = []
for name, flags in variants:
    out = Path("/tmp") / f"prime-{name}"
    out.unlink(missing_ok=True)
    cmd = ["node", cli, "build", entry, *flags, "-o", str(out)]
    try:
        status, body = run(cmd, cwd=work, timeout=900)
    except subprocess.TimeoutExpired as e:
        status = 124
        body = (e.stdout or "") + "\n[TIMEOUT]\n"
    diag_lines = [line for line in body.splitlines() if "error SC" in line or re.search(r"\bSC\d{4}: ", line)]
    codes = {}
    for line in diag_lines:
        m = re.search(r"(SC\d{4})", line)
        if m: codes[m.group(1)] = codes.get(m.group(1), 0) + 1
    smoke_status = 125
    smoke = "no executable"
    if status == 0 and out.exists():
        try:
            smoke_status, smoke = run([str(out), "--help"], cwd=work, timeout=30)
        except subprocess.TimeoutExpired as e:
            smoke_status, smoke = 124, (e.stdout or "") + "\n[TIMEOUT]\n"
    sections.append(
        f"## {name}\n"
        f"build_status={status}\n"
        f"executable={out.exists()}\n"
        f"smoke_status={smoke_status}\n"
        f"diagnostic_lines={len(diag_lines)}\n"
        f"codes={dict(sorted(codes.items()))}\n\n"
        "### first diagnostics\n" + "\n".join(diag_lines[:80]) + "\n\n"
        "### build tail\n" + "\n".join(body.splitlines()[-120:]) + "\n\n"
        "### smoke tail\n" + "\n".join(smoke.splitlines()[-80:]) + "\n"
    )
OUT.write_text(
    "# Prime Agent workspace staticization probe\n\n"
    "Compares the same Prime main against dynamic-only, npm-static auto, and explicit Prime workspace staticization.\n\n" +
    "\n\n".join(sections)
)
