from pathlib import Path

path = Path("packages/compiler/src/frontend/npm.ts")
text = path.read_text()

repls = []
repls.append(('''interface PkgJson {
  name?: string;
  main?: string;
  module?: string;
  type?: string;
  exports?: unknown;
}
''', '''interface PkgJson {
  name?: string;
  main?: string;
  module?: string;
  type?: string;
  exports?: unknown;
  imports?: unknown;
}
'''))

anchor = '''export function resolveExports(
  exports: unknown,
  subpath: string,
  mode: "import" | "require",
): string | null {
'''
if text.count(anchor) != 1:
    raise SystemExit("resolveExports anchor mismatch")
# Insert resolveImports after the complete resolveExports function, at the next NodeImportRefusal doc.
marker = '''/** A bare-specifier import edge Node's ESM resolution REFUSES, with Node's
'''
helper = r'''/** package.json "imports" resolution for package-internal `#name`
 * specifiers. The target grammar mirrors exports: exact keys before `*`
 * patterns, longest literal prefix, object-key condition order, arrays as
 * fallbacks, and the edge-kind condition set (node + import/require +
 * default). The returned target is deliberately still a SPECIFIER: a
 * `./local.js` target resolves inside the owning package scope, while a
 * package or another `#alias` target re-enters the ordinary resolver. */
export function resolveImports(
  imports: unknown,
  specifier: string,
  mode: "import" | "require",
): string | null {
  if (!imports || typeof imports !== "object" || Array.isArray(imports)) return null;
  const map = imports as Record<string, unknown>;
  const enabled = new Set([mode, "node", "default"]);
  const resolveTarget = (target: unknown, wildcard: string | null): string | null => {
    if (typeof target === "string") {
      return wildcard === null ? target : target.split("*").join(wildcard);
    }
    if (Array.isArray(target)) {
      for (const item of target) {
        const found = resolveTarget(item, wildcard);
        if (found !== null) return found;
      }
      return null;
    }
    if (target && typeof target === "object") {
      for (const [condition, value] of Object.entries(target)) {
        if (enabled.has(condition)) {
          const found = resolveTarget(value, wildcard);
          if (found !== null) return found;
        }
      }
    }
    return null;
  };
  if (Object.prototype.hasOwnProperty.call(map, specifier)) {
    return resolveTarget(map[specifier], null);
  }
  let best: { key: string; prefix: string; suffix: string } | null = null;
  for (const key of Object.keys(map)) {
    const star = key.indexOf("*");
    if (star < 0) continue;
    const prefix = key.slice(0, star);
    const suffix = key.slice(star + 1);
    if (
      specifier.startsWith(prefix) &&
      specifier.length >= prefix.length + suffix.length &&
      specifier.endsWith(suffix) &&
      (!best || prefix.length > best.prefix.length)
    ) {
      best = { key, prefix, suffix };
    }
  }
  if (best === null) return null;
  const wildcard = specifier.slice(best.prefix.length, specifier.length - best.suffix.length);
  return resolveTarget(map[best.key], wildcard);
}

'''
if text.count(marker) != 1:
    raise SystemExit("NodeImportRefusal marker mismatch")
text = text.replace(marker, helper + marker)

old_sig = '''  private resolvePackage(
    fromDir: string,
    specifier: string,
    mode: "import" | "require",
    ctx: { importer: string; chain: readonly string[] },
  ): string | null {
    const name = packageNameOf(specifier);
'''
new_sig = r'''  private resolvePackage(
    fromDir: string,
    specifier: string,
    mode: "import" | "require",
    ctx: { importer: string; chain: readonly string[] },
    importsDepth = 0,
  ): string | null {
    // Node's PACKAGE_IMPORTS_RESOLVE runs in the nearest package scope and
    // never probes node_modules for the `#name` itself. Targets may be a
    // package-relative file, another #alias, or an external package. Keep
    // this in the npm graph resolver (rather than teaching the engine) so
    // the resolved physical module is embedded and cached like every other
    // dependency edge.
    if (specifier.startsWith("#")) {
      if (importsDepth > 16) {
        this.errors.push({
          message: `package imports alias cycle while resolving '${specifier}' from ${ctx.importer}`,
        });
        return null;
      }
      let scopeDir: string | null = null;
      let scopePkg: PkgJson | null = null;
      for (let dir = fromDir; ; ) {
        const pkg = this.pkgJsonOf(dir);
        if (pkg !== null) {
          scopeDir = dir;
          scopePkg = pkg;
          break;
        }
        const parent = dirname(dir);
        if (parent === dir) break;
        dir = parent;
      }
      if (scopeDir === null || scopePkg === null || scopePkg.imports === undefined) {
        this.errors.push({
          message: `package import specifier '${specifier}' is not defined by a package.json "imports" map (imported from ${ctx.importer})`,
        });
        return null;
      }
      const target = resolveImports(scopePkg.imports, specifier, mode);
      if (target === null) {
        this.errors.push({
          message: `package import specifier '${specifier}' is not defined by ${join(scopeDir, "package.json")} "imports" (imported from ${ctx.importer})`,
        });
        return null;
      }
      if (target.startsWith("./")) {
        const resolved = this.resolveFile(join(scopeDir, target));
        if (resolved === null) {
          this.errors.push({
            message: `package import '${specifier}' resolves to '${target}', which does not exist (imported from ${ctx.importer})`,
          });
          return null;
        }
        return this.host.realpath(resolved);
      }
      return this.resolvePackage(scopeDir, target, mode, ctx, importsDepth + 1);
    }
    const name = packageNameOf(specifier);
'''
if text.count(old_sig) != 1:
    raise SystemExit("resolvePackage signature mismatch")
text = text.replace(old_sig, new_sig)

for old, new in repls:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one replacement, found {count}: {old[:60]!r}")
    text = text.replace(old, new)

path.write_text(text)
