from pathlib import Path

needles = ["Object.keys", "Object.values", "Object.entries", "lowerForOf", "for-of", "objectKeys", "objectValues"]
for p in Path('packages/compiler/src').rglob('*.ts'):
    try:
        lines = p.read_text(encoding='utf-8').splitlines()
    except Exception:
        continue
    hits = [i for i, line in enumerate(lines) if any(n in line for n in needles)]
    if not hits:
        continue
    print(f'### {p}')
    for i in hits:
        lo, hi = max(0, i-4), min(len(lines), i+10)
        print(f'--- around {i+1} ---')
        for j in range(lo, hi): print(f'{j+1}: {lines[j]}')
raise SystemExit(42)
