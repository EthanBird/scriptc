from pathlib import Path
import os
import subprocess
import textwrap

ROOT = Path.cwd()
FILES = [
    Path("packages/compiler/src/frontend/types.ts"),
    Path("tests/harness/npm.test.ts"),
    Path("tests/corpus/3011-dynamic-package-data-alias/main.ts"),
    Path("tests/corpus/3011-dynamic-package-data-alias/node_modules/data-alias/index.d.ts"),
    Path("tests/corpus/3011-dynamic-package-data-alias/node_modules/data-alias/index.js"),
]
FAIL = Path("WORKSPACE_ALIAS_REFINEMENT_FAILURE.txt")
original = {p: p.read_text() for p in FILES}
log: list[str] = []


def run(cmd: list[str], env: dict[str, str] | None = None) -> bool:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    log.append("$ " + " ".join(cmd))
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=merged)
    log.append(p.stdout)
    log.append(f"[exit {p.returncode}]\n")
    return p.returncode == 0


def restore() -> None:
    for p, data in original.items():
        p.write_text(data)

try:
    # ------------------------------------------------------------------
    # 1) Type-domain refinement: erased aliases from registered workspace
    #    packages are structural; erased aliases from external npm packages
    #    still define the dynamic/island execution domain.
    # ------------------------------------------------------------------
    types = FILES[0].read_text()
    anchor_import = 'import { isJsSourceFile, isNodeTypesPath } from "./program.js";\n'
    if 'workspacePackageOfPath' not in types:
        if anchor_import not in types:
            raise RuntimeError("types.ts import anchor changed")
        types = types.replace(
            anchor_import,
            anchor_import + 'import { workspacePackageOfPath } from "./shared.js";\n',
            1,
        )

    old = '''  const npmSym = widened.getSymbol();
  const npmDecls = npmSym ? checker.declarationsOf(npmSym) : undefined;
  if (
    npmDecls &&
    npmDecls.length > 0 &&
    npmDecls.every((d) => {
      const sf = d.getSourceFile();
      return sf.isDeclarationFile && !ctx.isStdlibFile(sf) && !ctx.isExternalTypeFile(sf);
    })
  ) {
    return ctx.dynamic ? JSVAL : null;
  }
'''
    new = '''  // An ERASED alias declared by an EXTERNAL npm package is still part of
  // that package's runtime type surface: values typed through it live in
  // the island under --dynamic. A registered WORKSPACE package is
  // different: its dist/*.d.ts aliases frequently describe ordinary data
  // shared with the compiled application. The alias name itself has no
  // runtime identity, so ignore WORKSPACE alias provenance and continue
  // mapping its underlying type. This is what lets e.g. a workspace
  // `type KeybindingsConfig = Record<string, ...>` use the native record
  // representation without accidentally staticizing TypeBox/Zod-style
  // aliases from external npm packages.
  const npmAliasSym = widened.getAliasSymbol();
  const npmAliasDecls = npmAliasSym ? checker.declarationsOf(npmAliasSym) : undefined;
  if (
    npmAliasDecls &&
    npmAliasDecls.length > 0 &&
    npmAliasDecls.every((d) => {
      const sf = d.getSourceFile();
      return (
        sf.isDeclarationFile &&
        !ctx.isStdlibFile(sf) &&
        !ctx.isExternalTypeFile(sf) &&
        workspacePackageOfPath(sf.fileName) === null
      );
    })
  ) {
    return ctx.dynamic ? JSVAL : null;
  }

  // Runtime-bearing declaration symbols (classes/interfaces/module objects)
  // keep the existing rule regardless of whether their package is external
  // or workspace-linked. A workspace alias to a class therefore still maps
  // to jsval through the underlying class symbol; only erased DATA aliases
  // lose their alias-level dynamic provenance above.
  const npmSym = widened.getSymbol();
  const npmDecls = npmSym ? checker.declarationsOf(npmSym) : undefined;
  if (
    npmDecls &&
    npmDecls.length > 0 &&
    npmDecls.every((d) => {
      const sf = d.getSourceFile();
      return sf.isDeclarationFile && !ctx.isStdlibFile(sf) && !ctx.isExternalTypeFile(sf);
    })
  ) {
    return ctx.dynamic ? JSVAL : null;
  }
'''
    if old not in types:
        raise RuntimeError("types.ts npm provenance block changed")
    types = types.replace(old, new, 1)
    FILES[0].write_text(types)

    # ------------------------------------------------------------------
    # 2) Existing corpus becomes the EXTERNAL npm control: its erased alias
    #    must remain an island handle. If aliases are broadened globally
    #    again, the method-bearing object cannot cross as JSON-safe data and
    #    this fixture fails.
    # ------------------------------------------------------------------
    FILES[2].write_text(textwrap.dedent('''\
        // @dynamic
        import { Box, getConfig } from "data-alias";
        import type { BoxAlias, Config } from "data-alias";

        const remote: Config = getConfig();
        console.log("remote", remote.label, remote.value());

        const box: BoxAlias = new Box("boxed");
        console.log("box", box.value());
    '''))
    FILES[3].write_text(textwrap.dedent('''\
        export type Config = {
          label: string;
          value(): string;
        };

        export declare function getConfig(): Config;

        export declare class Box {
          constructor(value: string);
          value(): string;
        }
        export type BoxAlias = Box;
    '''))
    FILES[4].write_text(textwrap.dedent('''\
        export function getConfig() {
          return { label: "external", value() { return "external-value"; } };
        }

        export class Box {
          constructor(value) { this._value = value; }
          value() { return this._value; }
        }
    '''))

    # ------------------------------------------------------------------
    # 3) Real workspace test: create a package OUTSIDE node_modules and a
    #    node_modules symlink to it, exactly what the resolver calls a
    #    workspace package. Its data alias must be native while a class
    #    alias stays in the island.
    # ------------------------------------------------------------------
    npm = FILES[1].read_text()
    old_fs = 'import { globSync, mkdirSync, readFileSync, realpathSync } from "node:fs";'
    new_fs = 'import { globSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";'
    if old_fs not in npm:
        raise RuntimeError("npm.test.ts fs import anchor changed")
    npm = npm.replace(old_fs, new_fs, 1)
    path_anchor = 'import { join } from "node:path";\n'
    if path_anchor not in npm:
        raise RuntimeError("npm.test.ts path import anchor changed")
    npm = npm.replace(path_anchor, path_anchor + 'import { tmpdir } from "node:os";\n', 1)

    insert_anchor = 'describe(`npm differential (${cases.length} programs${sanitize ? ", sanitized" : ""}${shardSuffix()})`, () => {'
    workspace_test = r'''
describe(`workspace package type ownership (${sanitize ? "sanitized" : "plain"})`, () => {
  test("workspace d.ts data aliases stay structural while runtime classes stay island", async () => {
    const root = mkdtempSync(join(tmpdir(), "scriptc-workspace-alias-"));
    try {
      const pkgDir = join(root, "packages/workspace-data-alias");
      const appDir = join(root, "app");
      const modulesDir = join(appDir, "node_modules");
      const outDir = join(root, "out");
      mkdirSync(pkgDir, { recursive: true });
      mkdirSync(modulesDir, { recursive: true });
      mkdirSync(outDir, { recursive: true });

      writeFileSync(join(pkgDir, "package.json"), JSON.stringify({
        name: "workspace-data-alias",
        version: "1.0.0",
        type: "module",
        main: "./index.js",
        types: "./index.d.ts",
      }));
      writeFileSync(join(pkgDir, "index.d.ts"), `
export type ConfigValue = string | string[] | undefined;
export type Config = Record<string, ConfigValue>;
export declare function getConfig(): Config;
export declare class Box { constructor(value: string); value(): string; }
export type BoxAlias = Box;
`);
      writeFileSync(join(pkgDir, "index.js"), `
export function getConfig() { return { alpha: "A", list: ["x", "y"] }; }
export class Box { constructor(value) { this._value = value; } value() { return this._value; } }
`);
      symlinkSync(
        pkgDir,
        join(modulesDir, "workspace-data-alias"),
        process.platform === "win32" ? "junction" : "dir",
      );
      writeFileSync(join(appDir, "package.json"), JSON.stringify({ type: "module" }));
      const entry = join(appDir, "main.ts");
      writeFileSync(entry, `
// @dynamic
import { Box, getConfig } from "workspace-data-alias";
import type { BoxAlias, Config } from "workspace-data-alias";
const local: Config = {};
local["save"] = "ctrl+s";
local["open"] = ["ctrl+o", "alt+o"];
for (const [key, value] of Object.entries(local)) {
  if (Array.isArray(value)) console.log("local", key, value.join("|"));
  else console.log("local", key, value ?? "undefined");
}
const remote: Config = getConfig();
const alpha = remote["alpha"];
console.log("remote", typeof alpha === "string" ? alpha : "bad", Array.isArray(remote["list"]));
const box: BoxAlias = new Box("boxed");
console.log("box", box.value());
`);

      const result = await compile(entry, {
        outPath: join(outDir, "program"),
        outDir,
        sanitize,
        dynamic: true,
      });
      if (!result.ok) {
        throw new Error(
          "workspace alias fixture failed to compile:\n" +
            result.diagnostics.map((d) => `${d.code}: ${d.message}`).join("\n"),
        );
      }
      const [nodeRes, nativeRes] = await Promise.all([
        runBinary("node", [entry]),
        runBinary(result.binaryPath, []),
      ]);
      expect(nativeRes.stdout.toString("utf8")).toBe(nodeRes.stdout.toString("utf8"));
      expect(nativeRes.exitCode).toBe(nodeRes.exitCode);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 120_000);
});

'''
    if insert_anchor not in npm:
        raise RuntimeError("npm.test.ts differential describe anchor changed")
    npm = npm.replace(insert_anchor, workspace_test + insert_anchor, 1)
    FILES[1].write_text(npm)

    checks: list[tuple[list[str], dict[str, str] | None]] = [
        (["pnpm", "build"], None),
        (["pnpm", "lint"], None),
        (["pnpm", "exec", "vitest", "run", "tests/harness/differential.test.ts", "-t", "3011-dynamic-package-data-alias"], None),
        (["pnpm", "exec", "vitest", "run", "tests/harness/differential.test.ts", "-t", "3011-dynamic-package-data-alias"], {"SCRIPTC_SAN": "1"}),
        (["pnpm", "exec", "vitest", "run", "tests/harness/llvm-differential.test.ts", "-t", "3011-dynamic-package-data-alias"], None),
        (["pnpm", "exec", "vitest", "run", "tests/harness/llvm-differential.test.ts", "-t", "3011-dynamic-package-data-alias"], {"SCRIPTC_SAN": "1"}),
        (["pnpm", "exec", "vitest", "run", "tests/harness/npm.test.ts", "-t", "workspace d.ts data aliases stay structural"], None),
        (["pnpm", "exec", "vitest", "run", "tests/harness/npm.test.ts", "-t", "workspace d.ts data aliases stay structural"], {"SCRIPTC_SAN": "1"}),
        # Full npm regression: external-package aliases must remain in the
        # island across the existing package corpus, not merely this control.
        (["pnpm", "exec", "vitest", "run", "tests/harness/npm.test.ts"], None),
    ]
    ok = True
    for cmd, env in checks:
        if not run(cmd, env):
            ok = False
            break
    if not ok:
        restore()
        FAIL.write_text("".join(log) + "\nWORKSPACE_ALIAS_REFINEMENT=FAIL; source/tests reverted\n")
    else:
        if FAIL.exists():
            FAIL.unlink()
        print("WORKSPACE_ALIAS_REFINEMENT=PASS")
except Exception as exc:
    restore()
    FAIL.write_text("".join(log) + f"\nTASK EXCEPTION: {exc!r}\nWORKSPACE_ALIAS_REFINEMENT=FAIL; source/tests reverted\n")
