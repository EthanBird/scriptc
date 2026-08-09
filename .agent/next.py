from pathlib import Path

needles = ["os.totalmem", "scr_os_totalmem", "os.homedir", "scr_os_homedir"]
out = []
for p in Path('.').rglob('*'):
    if not p.is_file() or '.git' in p.parts or 'node_modules' in p.parts:
        continue
    try:
        lines = p.read_text(encoding='utf-8').splitlines()
    except Exception:
        continue
    hit_lines = [i for i, line in enumerate(lines) if any(n in line for n in needles)]
    if not hit_lines:
        continue
    out.append(f'### {p}')
    seen = set()
    for i in hit_lines:
        lo, hi = max(0, i - 4), min(len(lines), i + 5)
        for j in range(lo, hi):
            if j in seen:
                continue
            seen.add(j)
            out.append(f'{j + 1}: {lines[j]}')
        out.append('')
Path('.agent/os-wiring.txt').write_text('\n'.join(out) + '\n', encoding='utf-8')
print(f'wrote {len(out)} report lines')
