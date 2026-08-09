from pathlib import Path

path = Path("packages/compiler/src/frontend/lowering/lower-exprs.ts")
text = path.read_text()
old = '''    if (value.type.kind !== "union") {
      throw new Error("lowerer bug: union-typed receiver lowered to a non-union");
    }
'''
new = '''    if (value.type.kind !== "union") {
      L.unsupported(
        "SC1090",
        expr,
        `property access on a checker-union receiver whose lowered runtime representation is '${L.fmt(value.type)}' (${NARROW_FIRST})`,
      );
    }
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one union receiver ICE site, found {count}")
path.write_text(text.replace(old, new))
