from pathlib import Path
import os
import subprocess
import textwrap

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
    log.append("$ " + " ".join(cmd) + "\n")
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=merged)
    log.append(p.stdout)
    log.append(f"[exit {p.returncode}]\n")
    return p.returncode == 0


def restore() -> None:
    for p, data in original.items():
        p.write_text(data)

try:
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
    new = '''  // Erased aliases from EXTERNAL npm packages still describe values whose
  // implementation lives in the island. Registered WORKSPACE packages are
  // different: their dist/*.d.ts commonly exports data aliases shared with
  // the compiled application. The alias name itself has no runtime identity,
  // so a workspace alias is ignored here and its UNDERLYING type continues
  // through structural mapping. This preserves native Record/config shapes
  // without staticizing TypeBox/Zod-style aliases from external packages.
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

  // Runtime-bearing symbols keep the old rule for BOTH external and
  // workspace packages. Thus `type X = PackageClass` still maps to jsval
  // through the underlying class symbol; only erased workspace DATA aliases
  // lose alias-level dynamic provenance.
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
    FILES[0].write_text(types.replace(old, new, 1))

    # External npm alias control: must remain in the island.
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
        export type Config = { label: string; value(): string };
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

    # Real symlink workspace fixture inside npm.test.ts.
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
      symlinkSync(pkgDir, join(modulesDir, "workspace-data-alias"), process.platform === "win32" ? "junction" : "dir");
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
        outPath: join(outDir, "program"), outDir, sanitize, dynamic: true,
      });
      if (!result.ok) {
        throw new Error("workspace alias fixture failed to compile:\n" + result.diagnostics.map((d) => `${d.code}: ${d.message}`).join("\n"));
      }
      const [nodeRes, nativeRes] = await Promise.all([
        runBinary("node", [entry]), runBinary(result.binaryPath, []),
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
        raise RuntimeError("npm.test.ts insertion anchor changed")
    FILES[1].write_text(npm.replace(insert_anchor, workspace_test + insert_anchor, 1))

    checks = [
        (["pnpm", "build"], None),
        (["pnpm", "lint"], None),
        (["pnpm", "exec", "vitest", "run", "tests/harness/differential.test.ts", "-t", "3011-dynamic-package-data-alias"], None),
        (["pnpm", "exec", "vitest", "run", "tests/harness/differential.test.ts", "-t", "3011-dynamic-package-data-alias"], {"SCRIPTC_SAN": "1"}),
        (["pnpm", "exec", "vitest", "run", "tests/harness/llvm-differential.test.ts", "-t", "3011-dynamic-package-data-alias"], None),
        (["pnpm", "exec", "vitest", "run", "tests/harness/llvm-differential.test.ts", "-t", "3011-dynamic-package-data-alias"], {"SCRIPTC_SAN": "1"}),
        (["pnpm", "exec", "vitest", "run", "tests/harness/npm.test.ts", "-t", "workspace d.ts data aliases stay structural"], None),
        (["pnpm", "exec", "vitest", "run", "tests/harness/npm.test.ts", "-t", "workspace d.ts data aliases stay structural"], {"SCRIPTC_SAN": "1"}),
        (["pnpm", "exec", "vitest", "run", "tests/harness/npm.test.ts"], None),
    ]
    for cmd, env in checks:
        if not run(cmd, env):
            restore()
            FAIL.write_text("".join(log) + "\nWORKSPACE_ALIAS_REFINEMENT=FAIL; source/tests reverted\n")
            break
    else:
        if FAIL.exists(): FAIL.unlink()
        print("WORKSPACE_ALIAS_REFINEMENT=PASS")
except Exception as exc:
    restore()
    FAIL.write_text("".join(log) + f"\nTASK EXCEPTION: {exc!r}\nWORKSPACE_ALIAS_REFINEMENT=FAIL; source/tests reverted\n")
