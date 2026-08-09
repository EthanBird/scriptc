from pathlib import Path

needles = ["os.totalmem", "scr_os_totalmem", "os.homedir", "scr_os_homedir"]
for p in Path('.').rglob('*'):
    if not p.is_file() or '.git' in p.parts or 'node_modules' in p.parts:
        continue
    try:
        lines = p.read_text(encoding='utf-8').splitlines()
    except Exception:
        continue
    hits = [(i + 1, line.rstrip()) for i, line in enumerate(lines) if any(n in line for n in needles)]
    if not hits:
        continue
    print(f'### {p}')
    for n, line in hits:
        print(f'{n}: {line}')
raise SystemExit(42)
