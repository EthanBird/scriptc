from pathlib import Path

path = Path("packages/compiler/src/frontend/lowering/lower-exprs.ts")
text = path.read_text()
old = '''      // A union-typed field read narrows like an identifier when the
      // checker has narrowed this use to one arm.
      if (handled) return L.maybeNarrow(handled, expr);
      // `globalThis.<name>` that no lowering above claimed
'''
new = '''      // A union-typed field read narrows like an identifier when the
      // checker has narrowed this use to one arm.
      if (handled) return L.maybeNarrow(handled, expr);
      // Representation-first array length: some ambient APIs expose
      // arrays whose ELEMENT type is intentionally outside the static
      // structural set (for example node:os CpuInfo[]). The checker type
      // therefore cannot map as an array even though the call lowerer has
      // already produced an honest runtime array/island array value. The
      // container's length does not inspect or materialize any element, so
      // it is valid to read from the actual lowered representation. This
      // is the same value-is-truth discipline used by array method calls
      // and checker-union bridges above.
      if (expr.name.text === "length" && !expr.questionDotToken) {
        const recv = L.lowerExpr(expr.expression);
        if (recv.type.kind === "array") {
          return {
            kind: "arrIntrinsic",
            method: "length",
            receiver: recv,
            args: [],
            type: F64,
            loc,
          };
        }
        if (recv.type.kind === "jsval") {
          const read: IrExpr = {
            kind: "jsOp",
            op: "getProp",
            name: "length",
            args: [recv],
            type: JSVAL,
            loc,
          };
          return { kind: "jsExit", value: read, type: F64, loc };
        }
      }
      // `globalThis.<name>` that no lowering above claimed
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one handled/property-fallback site, found {count}")
path.write_text(text.replace(old, new))
