from pathlib import Path

needles = [
    "emitSetNew", "scr_set_new_ref", "isSupportedSetElem", "mapKeyAccess",
    "case \"set\"", "Set elements", "Set ELEMENT", "Set<T>"
]
for p in Path('packages').rglob('*'):
    if not p.is_file() or 'node_modules' in p.parts:
        continue
    try:
        lines = p.read_text(encoding='utf-8').splitlines()
    except Exception:
        continue
    hits = [i for i, line in enumerate(lines) if any(n in line for n in needles)]
    if not hits:
        continue
    print(f'### {p}')
    for i in hits:
        lo, hi = max(0, i - 3), min(len(lines), i + 8)
        print(f'--- around {i+1} ---')
        for j in range(lo, hi):
            print(f'{j+1}: {lines[j]}')
raise SystemExit(42)
