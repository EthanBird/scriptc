from pathlib import Path
import os, subprocess, textwrap

FILES=[
 Path('packages/compiler/src/frontend/types.ts'),
 Path('tests/harness/npm.test.ts'),
 Path('tests/corpus/3011-dynamic-package-data-alias/main.ts'),
 Path('tests/corpus/3011-dynamic-package-data-alias/node_modules/data-alias/index.d.ts'),
 Path('tests/corpus/3011-dynamic-package-data-alias/node_modules/data-alias/index.js'),
]
FAIL=Path('WORKSPACE_ALIAS_REFINEMENT_FAILURE.txt')
orig={p:p.read_text() for p in FILES}
log=[]

def run(cmd, env=None):
    e=os.environ.copy(); e.update(env or {})
    log.append('$ '+' '.join(cmd)+'\n')
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=e)
    log.append(p.stdout); log.append(f'[exit {p.returncode}]\n')
    return p.returncode==0

def restore():
    for p,s in orig.items(): p.write_text(s)

try:
    t=FILES[0].read_text()
    imp='import { isJsSourceFile, isNodeTypesPath } from "./program.js";\n'
    if 'workspacePackageOfPath' not in t:
        if imp not in t: raise RuntimeError('types import anchor changed')
        t=t.replace(imp,imp+'import { workspacePackageOfPath } from "./shared.js";\n',1)
    old='''  const npmSym = widened.getSymbol();
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
    new='''  // Erased aliases from EXTERNAL npm packages still describe values whose
  // implementation lives in the island. Registered WORKSPACE packages are
  // different: their dist/*.d.ts commonly exports data aliases shared with
  // the compiled application. Ignore workspace alias provenance and map the
  // underlying type structurally; keep external aliases dynamic.
  const npmAliasSym = widened.getAliasSymbol();
  const npmAliasDecls = npmAliasSym ? checker.declarationsOf(npmAliasSym) : undefined;
  if (
    npmAliasDecls && npmAliasDecls.length > 0 &&
    npmAliasDecls.every((d) => {
      const sf = d.getSourceFile();
      return sf.isDeclarationFile && !ctx.isStdlibFile(sf) &&
        !ctx.isExternalTypeFile(sf) && workspacePackageOfPath(sf.fileName) === null;
    })
  ) {
    return ctx.dynamic ? JSVAL : null;
  }

  // Runtime-bearing declaration symbols (classes/interfaces/module objects)
  // keep the existing island rule even for workspace packages. Thus an alias
  // to a workspace class remains jsval through the underlying class symbol.
  const npmSym = widened.getSymbol();
  const npmDecls = npmSym ? checker.declarationsOf(npmSym) : undefined;
  if (
    npmDecls && npmDecls.length > 0 &&
    npmDecls.every((d) => {
      const sf = d.getSourceFile();
      return sf.isDeclarationFile && !ctx.isStdlibFile(sf) && !ctx.isExternalTypeFile(sf);
    })
  ) {
    return ctx.dynamic ? JSVAL : null;
  }
'''
    if old not in t: raise RuntimeError('npm provenance block changed')
    FILES[0].write_text(t.replace(old,new,1))

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
export declare class Box { constructor(value: string); value(): string; }
export type BoxAlias = Box;
'''))
    FILES[4].write_text(textwrap.dedent('''\
export function getConfig() { return { label: "external", value() { return "external-value"; } }; }
export class Box { constructor(value) { this._value = value; } value() { return this._value; } }
'''))

    n=FILES[1].read_text()
    oldfs='import { globSync, mkdirSync, readFileSync, realpathSync } from "node:fs";'
    newfs='import { globSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";'
    if oldfs not in n: raise RuntimeError('npm fs import anchor changed')
    n=n.replace(oldfs,newfs,1)
    pa='import { join } from "node:path";\n'
    n=n.replace(pa,pa+'import { tmpdir } from "node:os";\n',1)
    anchor='describe(`npm differential (${cases.length} programs${sanitize ? ", sanitized" : ""}${shardSuffix()})`, () => {'
    test=r'''
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
      writeFileSync(join(pkgDir, "package.json"), JSON.stringify({ name: "workspace-data-alias", version: "1.0.0", type: "module", main: "./index.js", types: "./index.d.ts" }));
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
  if (value === undefined) console.log("local", key, "undefined");
  else if (Array.isArray(value)) console.log("local", key, value.join("|"));
  else console.log("local", key, value);
}
const remote: Config = getConfig();
const alpha = remote["alpha"];
console.log("remote", typeof alpha === "string" ? alpha : "bad", Array.isArray(remote["list"]));
const box: BoxAlias = new Box("boxed");
console.log("box", box.value());
`);
      const result = await compile(entry, { outPath: join(outDir, "program"), outDir, sanitize, dynamic: true });
      if (!result.ok) throw new Error("workspace alias fixture failed to compile:\n" + result.diagnostics.map((d) => `${d.code}: ${d.message}`).join("\n"));
      const [nodeRes, nativeRes] = await Promise.all([runBinary("node", [entry]), runBinary(result.binaryPath, [])]);
      expect(nativeRes.stdout.toString("utf8")).toBe(nodeRes.stdout.toString("utf8"));
      expect(nativeRes.exitCode).toBe(nodeRes.exitCode);
    } finally { rmSync(root, { recursive: true, force: true }); }
  }, 120_000);
});

'''
    if anchor not in n: raise RuntimeError('npm describe anchor changed')
    FILES[1].write_text(n.replace(anchor,test+anchor,1))

    checks=[
      (["pnpm","build"],None),(["pnpm","lint"],None),
      (["pnpm","exec","vitest","run","tests/harness/differential.test.ts","-t","3011-dynamic-package-data-alias"],None),
      (["pnpm","exec","vitest","run","tests/harness/differential.test.ts","-t","3011-dynamic-package-data-alias"],{"SCRIPTC_SAN":"1"}),
      (["pnpm","exec","vitest","run","tests/harness/llvm-differential.test.ts","-t","3011-dynamic-package-data-alias"],None),
      (["pnpm","exec","vitest","run","tests/harness/llvm-differential.test.ts","-t","3011-dynamic-package-data-alias"],{"SCRIPTC_SAN":"1"}),
      (["pnpm","exec","vitest","run","tests/harness/npm.test.ts","-t","workspace d.ts data aliases stay structural"],None),
      (["pnpm","exec","vitest","run","tests/harness/npm.test.ts","-t","workspace d.ts data aliases stay structural"],{"SCRIPTC_SAN":"1"}),
      (["pnpm","exec","vitest","run","tests/harness/npm.test.ts"],None),
    ]
    for cmd,env in checks:
      if not run(cmd,env):
        restore(); FAIL.write_text(''.join(log)+'\nWORKSPACE_ALIAS_REFINEMENT=FAIL; source/tests reverted\n'); break
    else:
      if FAIL.exists(): FAIL.unlink()
      print('WORKSPACE_ALIAS_REFINEMENT=PASS')
except Exception as e:
    restore(); FAIL.write_text(''.join(log)+f'\nTASK EXCEPTION: {e!r}\nWORKSPACE_ALIAS_REFINEMENT=FAIL; source/tests reverted\n')
