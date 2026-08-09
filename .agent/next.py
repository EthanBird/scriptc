from pathlib import Path

needles = ["os.totalmem", "scr_os_totalmem", "os.homedir", "scr_os_homedir"]
for p in Path('.').rglob('*'):
    if not p.is_file() or '.git' in p.parts or 'node_modules' in p.parts:
        continue
    try:
        text = p.read_text(encoding='utf-8')
    except Exception:
        continue
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if any(n in line for n in needles):
            hits.append((i, line))
    if hits:
        print(f'### {p}')
        for i, line in hits:
            print(f'{i}: {line}')
raise SystemExit('inspection-only')
