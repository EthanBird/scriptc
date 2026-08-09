from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{path}: expected one match, got {n}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

replace_once(
    'packages/compiler/src/frontend/lowering/lower-exprs.ts',
    'import { dirname } from "node:path";\n',
    'import { dirname } from "node:path";\nimport { pathToFileURL } from "node:url";\n',
)
replace_once(
    'packages/compiler/src/frontend/lowering/lower-exprs.ts',
    '''      // `require.main.filename` / `require.main?.filename` — CommonJS
      // entry-module identity: in a compiled binary require.main IS the
''',
    '''      // `import.meta.url` in a file-backed ES module is a module constant.
      // Bake the same file: URL Node constructs from this source file. This is
      // the ESM twin of our __filename/require.main.filename stance: exact
      // when the compiled binary runs from the same source tree, with URL
      // escaping (spaces, #, non-ASCII) delegated to Node's own build-time
      // pathToFileURL implementation instead of hand-rolling it.
      if (
        expr.name.text === "url" &&
        !expr.questionDotToken &&
        ts.isMetaProperty(expr.expression) &&
        expr.expression.keywordToken === ts.SyntaxKind.ImportKeyword
      ) {
        return {
          kind: "strLit",
          value: pathToFileURL(expr.getSourceFile().fileName).href,
          type: STRING,
          loc,
        };
      }
      // `require.main.filename` / `require.main?.filename` — CommonJS
      // entry-module identity: in a compiled binary require.main IS the
''',
)

case = Path('tests/corpus/3002-import-meta-url.ts')
if case.exists():
    raise SystemExit(f'{case}: already exists')
case.write_text('''// import.meta.url is a file-backed ESM module constant. Avoid printing the
// checkout's absolute path; assert the stable URL properties differentially.
console.log(import.meta.url.startsWith("file:"));
console.log(import.meta.url.includes("3002-import-meta-url.ts"));
console.log(!import.meta.url.includes(" "));
''', encoding='utf-8')
print('implemented import.meta.url constant lowering')
