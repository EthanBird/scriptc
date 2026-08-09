from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


containers = "packages/compiler/src/frontend/lowering/lower-containers.ts"
stmts = "packages/compiler/src/frontend/lowering/lower-stmts.ts"

helper_anchor = '''  export function lowerForOfMap(L: Lowerer, stmt: ts.ForOfStatement,
    iterable: IrExpr,
    mapT: IrType & { kind: "map" },
    proj?: ForOfIterProjection,): IrStmt {
'''
helper = '''  /** `for (const [k, v] of Object.entries(r))` over a PURE
   * index-signature record (`Record<string, T>`): consume the entries view
   * directly instead of materializing `Array<[string, T]>`. Arrays of tuple
   * records are deliberately not a general ScriptC representation yet, but
   * the iterator is fully observable without one: Object.entries snapshots
   * own enumerable keys at the call, then each yielded pair contains the
   * value read at snapshot-construction time. Pure index-signature records
   * cannot add/delete keys through aliases while the snapshot is built by
   * this lowering, so build a key snapshot and read the corresponding value
   * before entering the user body for each row. The pair itself never
   * materializes when the head is the dominant `[k, v]` identifier pattern.
   *
   * Kept intentionally narrow: hybrid records have declared-field/overflow
   * ordering and heterogeneous value questions already handled by the full
   * Object.entries helper, and non-plain heads retain that honest fence. */
  export function lowerForOfObjectEntriesIndexRecord(
    L: Lowerer,
    stmt: ts.ForOfStatement,
    iterable: IrExpr & { type: IrType & { kind: "record" } },
    shape: IrRecordShape,
  ): IrStmt | null {
    if (!shape.indexValue || shape.fields.length !== 0) return null;
    if (!ts.isVariableDeclarationList(stmt.initializer)) return null;
    const list = stmt.initializer;
    if ((list.flags & ts.NodeFlags.Using) !== 0) return null;
    const isVar = (list.flags & ts.NodeFlags.BlockScoped) === 0;
    if (isVar) return null;
    const decl = list.declarations[0];
    if (!decl || !ts.isArrayBindingPattern(decl.name) || decl.name.elements.length !== 2) return null;
    const isPlainIdent = (el: ts.ArrayBindingElement): el is ts.BindingElement & { name: ts.Identifier } =>
      ts.isBindingElement(el) && el.name !== undefined && ts.isIdentifier(el.name) && !el.initializer && !el.dotDotDotToken;
    if (!decl.name.elements.every(isPlainIdent)) return null;
    const els = decl.name.elements as readonly (ts.BindingElement & { name: ts.Identifier })[];
    const keyTsT = L.mapTypeOf(L.checker.getTypeAtLocation(els[0]!.name));
    const valueTsT = L.mapTypeOf(L.checker.getTypeAtLocation(els[1]!.name));
    if (keyTsT?.kind !== "string" || !valueTsT || !typeEquals(valueTsT, shape.indexValue)) return null;

    const loc = locOf(stmt);
    const recT = iterable.type;
    const iv = shape.indexValue;
    const keysT = arrayOf(STRING);
    const isLet = (list.flags & ts.NodeFlags.Let) !== 0;
    L.scopes.push(new Map());
    try {
      const src = L.declareHiddenLocal("%objEntriesSrc", recT);
      const keys = L.declareHiddenLocal("%objEntriesKeys", keysT);
      const i = L.declareHiddenLocal("%objEntriesIndex", F64);
      i.mutable = true;
      const ref = (localId: string, type: IrType): IrExpr => ({ kind: "varRef", localId, type, loc });
      const num = (value: number): IrExpr => ({ kind: "numLit", value, type: F64, loc });
      const keyRead = (): IrExpr => ({
        kind: "arrayGet",
        arr: ref(keys.id, keysT),
        index: ref(i.id, F64),
        type: STRING,
        loc,
      });
      const k = L.declareLocal(els[0]!.name, els[0]!.name.text, STRING, isLet);
      const v = L.declareLocal(els[1]!.name, els[1]!.name.text, iv, isLet);
      const kRef: IrExpr = { kind: "varRef", localId: k.id, type: STRING, loc };
      const binds: IrStmt[] = [
        { kind: "varDecl", localId: k.id, init: keyRead(), loc },
        {
          kind: "varDecl",
          localId: v.id,
          init: {
            kind: "recordKeyGet",
            obj: ref(src.id, recT),
            shapeId: recT.shapeId,
            key: kRef,
            overflowOnly: true,
            type: iv,
            loc,
          },
          loc,
        },
      ];
      const body = L.inCtl("loop", () => L.lowerScopedBlock(stmt.statement));
      const loop: IrStmt = {
        kind: "for",
        init: { kind: "varDecl", localId: i.id, init: num(0), loc },
        cond: {
          kind: "bin",
          op: "<",
          left: ref(i.id, F64),
          right: { kind: "arrIntrinsic", method: "length", receiver: ref(keys.id, keysT), args: [], type: F64, loc },
          type: BOOL,
          loc,
        },
        update: {
          kind: "assign",
          localId: i.id,
          value: { kind: "bin", op: "+", left: ref(i.id, F64), right: num(1), type: F64, loc },
          loc,
        },
        body: [...binds, ...body],
        loc,
      };
      return {
        kind: "block",
        body: [
          { kind: "varDecl", localId: src.id, init: iterable, loc },
          {
            kind: "varDecl",
            localId: keys.id,
            init: { kind: "recordOvfKeys", obj: ref(src.id, recT), shapeId: recT.shapeId, type: keysT, loc },
            loc,
          },
          loop,
        ],
        loc,
      };
    } finally {
      L.scopes.pop();
    }
  }

'''
replace_once(containers, helper_anchor, helper + helper_anchor)

old_import = '''import { ForOfIterProjection, lowerForOfArrayIter, lowerForOfMap, lowerForOfSearchParams, lowerForOfSet, objectIterOverIndexShape, strCharsCall } from "./lower-containers.js";'''
new_import = '''import { ForOfIterProjection, lowerForOfArrayIter, lowerForOfMap, lowerForOfObjectEntriesIndexRecord, lowerForOfSearchParams, lowerForOfSet, objectIterOverIndexShape, strCharsCall } from "./lower-containers.js";'''
replace_once(stmts, old_import, new_import)

entries_anchor = '''    // `for (const k of m.keys())` / `.values()` / `.entries()`: the
    // iterator methods consumed DIRECTLY by a for-of head ride the
'''
entries_block = '''    // `for (const [k, v] of Object.entries(r))` over a pure
    // `Record<string, T>` consumes the entries view directly. The ordinary
    // Object.entries lowering would need an Array<[string, T]> value (an
    // array of tuple records); this head-only path preserves the observable
    // key/value iteration without inventing that broader representation.
    {
      let src: ts.Expression = stmt.expression;
      while (ts.isParenthesizedExpression(src)) src = src.expression;
      if (
        ts.isCallExpression(src) &&
        src.arguments.length === 1 &&
        !ts.isSpreadElement(src.arguments[0]!) &&
        !src.questionDotToken &&
        ts.isPropertyAccessExpression(src.expression) &&
        !src.expression.questionDotToken &&
        src.expression.name.text === "entries" &&
        L.isStdlibGlobal(src.expression.expression, "Object")
      ) {
        const arg = src.arguments[0]!;
        const mapped = L.mapTypeOf(L.typeOf(arg));
        const probed = mapped?.kind === "record" ? null : probeLower(L, arg);
        const recT = mapped?.kind === "record" ? mapped : probed?.type.kind === "record" ? probed.type : null;
        if (recT) {
          const shape = L.shapes.get(recT.shapeId);
          if (shape?.indexValue && shape.fields.length === 0) {
            const receiver = L.lowerExpr(arg);
            if (receiver.type.kind === "record") {
              const lowered = lowerForOfObjectEntriesIndexRecord(
                L,
                stmt,
                receiver as IrExpr & { type: IrType & { kind: "record" } },
                shape,
              );
              if (lowered) return lowered;
            }
          }
        }
      }
    }
'''
replace_once(stmts, entries_anchor, entries_block + entries_anchor)

Path("tests/corpus/3003-object-entries-forof.ts").write_text('''// Direct Object.entries for-of over pure index-signature records. The loop\n// must not require a first-class Array<[string, T]> representation.\n\ntype BindingValue = string | string[] | undefined;\nconst bindings: Record<string, BindingValue> = {};\nbindings["save"] = "ctrl+s";\nbindings["open"] = ["ctrl+o", "alt+o"];\nbindings["unset"] = undefined;\nfor (const [key, value] of Object.entries(bindings)) {\n  if (value === undefined) {\n    console.log(key, "undefined");\n  } else if (Array.isArray(value)) {\n    console.log(key, value.join("|"));\n  } else {\n    console.log(key, value);\n  }\n}\n\nfunction copyColors<T extends Record<string, string | number>>(colors: T): Record<string, string | number> {\n  const out: Record<string, string | number> = {};\n  for (const [key, value] of Object.entries(colors)) out[key] = value;\n  return out;\n}\nconst colors: Record<string, string | number> = {};\ncolors["accent"] = "#fff";\ncolors["level"] = 7;\nconsole.log(JSON.stringify(copyColors(colors)));\n''', encoding="utf-8")
