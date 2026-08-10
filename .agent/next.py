from pathlib import Path
import os, subprocess

LOWERER=Path('packages/compiler/src/frontend/lowering/lowerer.ts')
CORPUS=Path('tests/corpus/3012-index-record-fixed-projection.ts')
FAIL=Path('INDEX_RECORD_PROJECTION_FAILURE.txt')
orig_lowerer=LOWERER.read_text()
orig_corpus=CORPUS.read_text() if CORPUS.exists() else None
log=[]

def restore():
    LOWERER.write_text(orig_lowerer)
    if orig_corpus is None: CORPUS.unlink(missing_ok=True)
    else: CORPUS.write_text(orig_corpus)

def run(cmd,env=None):
    e=os.environ.copy(); e.update(env or {})
    log.append('$ '+' '.join(cmd)+'\n')
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=e)
    log.append(p.stdout); log.append(f'[exit {p.returncode}]\n')
    return p.returncode==0

try:
    s=LOWERER.read_text()
    old='''      const helper =
        this.recordWidthHelper(expr.type.shapeId, expected.shapeId, expr.loc) ??
        lowerRecordOvfCaptureHelper(this, expr.type.shapeId, expected.shapeId, expr.loc);
'''
    new='''      const helper =
        this.recordWidthHelper(expr.type.shapeId, expected.shapeId, expr.loc) ??
        lowerRecordOvfCaptureHelper(this, expr.type.shapeId, expected.shapeId, expr.loc) ??
        this.indexRecordProjectionHelper(expr.type.shapeId, expected.shapeId, expr.loc);
'''
    if old not in s: raise RuntimeError('widthCoerce helper chain changed')
    s=s.replace(old,new,1)

    anchor='''  /** Interned `%arr.width.<n>(a)` — the per-element copy loop over
'''
    if anchor not in s: raise RuntimeError('record-width insertion anchor changed')
    helper=r'''  /** Planning half of an INDEX-SIGNATURE → FIXED-record checked
   * projection. TypeScript accepts a string-indexed dictionary wherever
   * every named destination property is covered by that index signature;
   * the JS value is still one ordinary object. ScriptC's fixed records are
   * monomorphic structs, so the flow needs a snapshot just like width
   * subtyping. For each destination field we either read the source's
   * same-named declared slot or its string-indexed overflow and then apply
   * the ordinary width-lift relation into the field type.
   *
   * A missing dynamic key is NOT silently defaulted: recordKeyGet already
   * throws the catchable TypeError when its result type has no undefined
   * arm. If the source index value itself includes undefined, the following
   * width lift/narrow performs the checked extraction. Thus a lying cast
   * fails at the projection boundary instead of manufacturing a fixed
   * record containing a value JavaScript never had. */
  indexRecordProjectionPlan(
    fromId: string,
    toId: string,
  ): Map<string, { src: IrType; lift: WidthLift; declared: boolean }> | null {
    const from = this.shapes.get(fromId);
    const to = this.shapes.get(toId);
    if (!from?.indexValue || !to || to.indexValue || from.tuple || to.tuple) return null;
    if (to.fields.some((f) => f.name.startsWith("%"))) return null;
    const key = `idxproj:${fromId}:${toId}`;
    // Recursive index-value projections need a named recursive plan before
    // they can be sound. Prime's config/theme dictionaries are finite data;
    // keep recursive shapes fenced rather than interning an incomplete map.
    if (this.widthPlanning.has(key)) return null;
    this.widthPlanning.add(key);
    try {
      const declared = new Map(from.fields.map((f) => [f.name, f] as const));
      const plan = new Map<string, { src: IrType; lift: WidthLift; declared: boolean }>();
      for (const tf of to.fields) {
        const sf = declared.get(tf.name);
        const src = sf?.type ?? from.indexValue;
        const lift = this.widthLiftPlan(src, tf.type);
        if (!lift) return null;
        plan.set(tf.name, { src, lift, declared: sf !== undefined });
      }
      return plan;
    } finally {
      this.widthPlanning.delete(key);
    }
  }

  /** Interned `%idx.proj.<n>(r)` — materializes the fixed target snapshot
   * from indexRecordProjectionPlan. Literal overflow reads are marked
   * overflowOnly when no same-named declared source field exists, avoiding
   * a needless declared-field switch and making the missing-key trap come
   * directly from the overflow read. */
  indexRecordProjectionHelper(fromId: string, toId: string, loc: SrcLoc): string | null {
    const from = this.shapes.get(fromId);
    const to = this.shapes.get(toId);
    if (!from || !to) return null;
    const plan = this.indexRecordProjectionPlan(fromId, toId);
    if (!plan) return null;
    const key = `idxproj:${fromId}:${toId}`;
    const existing = this.widthHelpers.get(key);
    if (existing) return existing;
    const name = `%idx.proj.${this.widthHelpers.size}`;
    this.widthHelpers.set(key, name);
    const fromT: IrType = { kind: "record", shapeId: fromId };
    const toT: IrType = { kind: "record", shapeId: toId };
    const r: IrExpr = { kind: "varRef", localId: "r.0", type: fromT, loc };
    this.liftedFns.push({
      name,
      params: [{ localId: "r.0", name: "r", type: fromT }],
      returnType: toT,
      locals: [{ id: "r.0", name: "r", type: fromT, mutable: true }],
      body: [
        {
          kind: "return",
          value: {
            kind: "recordLit",
            fields: to.fields.map((f) => {
              const p = plan.get(f.name)!;
              const read: IrExpr = p.declared
                ? { kind: "recordGet", obj: r, shapeId: fromId, field: f.name, type: p.src, loc }
                : {
                    kind: "recordKeyGet",
                    obj: r,
                    shapeId: fromId,
                    key: { kind: "strLit", value: f.name, type: STRING, loc },
                    overflowOnly: true,
                    type: p.src,
                    loc,
                  };
              return { name: f.name, value: this.applyWidthLift(p.lift, read, f.type, loc) };
            }),
            type: toT,
            loc,
          },
          loc,
        },
      ],
      loc,
    });
    return name;
  }

'''
    s=s.replace(anchor,helper+anchor,1)
    LOWERER.write_text(s)

    CORPUS.write_text('''type TextBag = Record<string, string>;
type FixedText = { alpha: string; beta: string };
const textBag: TextBag = { alpha: "A", beta: "B", ignored: "X" };
const fixedText = textBag as FixedText;
console.log("text", fixedText.alpha, fixedText.beta);

type ColorValue = string | number;
type ColorBag = Record<string, ColorValue>;
type FixedTheme = { accent: ColorValue; border: ColorValue; warning: ColorValue };
const colors: ColorBag = { accent: "#fff", border: 8, warning: "yellow", extra: 99 };
const theme = colors as FixedTheme;
console.log("theme", theme.accent, theme.border, theme.warning);
''')

    checks=[
      (["pnpm","build"],None),(["pnpm","lint"],None),
      (["pnpm","exec","vitest","run","tests/harness/differential.test.ts","-t","3012-index-record-fixed-projection"],None),
      (["pnpm","exec","vitest","run","tests/harness/differential.test.ts","-t","3012-index-record-fixed-projection"],{"SCRIPTC_SAN":"1"}),
      (["pnpm","exec","vitest","run","tests/harness/llvm-differential.test.ts","-t","3012-index-record-fixed-projection"],None),
      (["pnpm","exec","vitest","run","tests/harness/llvm-differential.test.ts","-t","3012-index-record-fixed-projection"],{"SCRIPTC_SAN":"1"}),
    ]
    for cmd,env in checks:
      if not run(cmd,env):
        restore(); FAIL.write_text(''.join(log)+'\nINDEX_RECORD_PROJECTION=FAIL; source/corpus reverted\n'); break
    else:
      FAIL.unlink(missing_ok=True)
      print('INDEX_RECORD_PROJECTION=PASS')
except Exception as e:
    restore(); FAIL.write_text(''.join(log)+f'\nTASK EXCEPTION: {e!r}\nINDEX_RECORD_PROJECTION=FAIL; source/corpus reverted\n')
