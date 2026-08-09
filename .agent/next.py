from pathlib import Path

path = Path("packages/compiler/src/frontend/lowering/lower-exprs.ts")
text = path.read_text()
old = '''    if (value.type.kind === "dyn") {
      const key: IrExpr = { kind: "strLit", value: expr.name.text, type: STRING, loc: locOf(expr.name) };
      return { kind: "dynKeyGet", key, value, type: DYN, loc: locOf(expr) };
    }
    if (value.type.kind === "record") {
'''
new = '''    if (value.type.kind === "dyn") {
      const key: IrExpr = { kind: "strLit", value: expr.name.text, type: STRING, loc: locOf(expr.name) };
      return { kind: "dynKeyGet", key, value, type: DYN, loc: locOf(expr) };
    }
    // A checker-union receiver whose VALUE already lives in the island
    // (a typed facade over package/any-backed state) reads through the
    // engine exactly like the ordinary island-property path above. The
    // checker describes the consumer-facing member type; primitive/bytes
    // results exit eagerly with validation while identity-bearing composite
    // values stay handles. This is a representation bridge, not a union
    // tag dispatch: there is no native union value left to inspect.
    if (value.type.kind === "jsval") {
      const loc = locOf(expr);
      const read: IrExpr = {
        kind: "jsOp",
        op: "getProp",
        name: expr.name.text,
        args: [value],
        type: JSVAL,
        loc,
      };
      const declared = L.mapTypeOf(L.typeOf(expr));
      if (
        declared &&
        (declared.kind === "f64" || declared.kind === "bool" || declared.kind === "string" ||
          (declared.kind === "bytes" && declared.elem === "u8"))
      ) {
        return { kind: "jsExit", value: read, type: declared, loc };
      }
      return read;
    }
    if (value.type.kind === "record") {
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one union dyn/record bridge site, found {count}")
path.write_text(text.replace(old, new))
