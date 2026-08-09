from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, got {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

# 1) IR function name: an internal scalar projection of os.cpus().length.
replace_once(
    "packages/compiler/src/ir/nodes.ts",
    '  /** os.totalmem(): total physical memory in bytes. Never throws. */\n  | "os.totalmem"\n',
    '  /** os.totalmem(): total physical memory in bytes. Never throws. */\n  | "os.totalmem"\n'
    '  /** os.cpus().length: the host logical CPU count without materializing\n'
    '   * CpuInfo[] (the element records remain outside the static surface). */\n'
    '  | "os.cpuCount"\n',
)

# 2) Validator contract.
replace_once(
    "packages/compiler/src/ir/validate.ts",
    '  "os.totalmem": { argTypes: [], result: F64 },\n',
    '  "os.totalmem": { argTypes: [], result: F64 },\n'
    '  "os.cpuCount": { argTypes: [], result: F64 },\n',
)

# 3) C backend mapping.
replace_once(
    "packages/compiler/src/backend/emission/emit-exprs.ts",
    '          case "os.totalmem":\n            return finish(`scr_os_totalmem()`);\n',
    '          case "os.totalmem":\n            return finish(`scr_os_totalmem()`);\n'
    '          case "os.cpuCount":\n            return finish(`scr_os_cpu_count()`);\n',
)

# 4) LLVM backend symbol table.
replace_once(
    "packages/compiler/src/backend/llvm/emitter.ts",
    '  "os.totalmem": "scr_os_totalmem",\n',
    '  "os.totalmem": "scr_os_totalmem",\n'
    '  "os.cpuCount": "scr_os_cpu_count",\n',
)

# 5) Runtime public prototype.
replace_once(
    "packages/runtime/src/scr_runtime.h",
    'double scr_os_totalmem(void); /* total physical memory, bytes */\n',
    'double scr_os_totalmem(void); /* total physical memory, bytes */\n'
    'double scr_os_cpu_count(void); /* logical processors reported by the host OS */\n',
)

# 6) Runtime implementation, shared by the platform arms.
replace_once(
    "packages/runtime/src/scr_lib.c",
    '#endif /* _WIN32 */\n\n/* ── os.networkInterfaces(): the getifaddrs(3) snapshot ────────────────\n',
    '#endif /* _WIN32 */\n\n'
    'double scr_os_cpu_count(void) {\n'
    '  /* os.cpus().length only: keep the rich CpuInfo records outside the\n'
    '   * static surface while preserving the observable host logical-CPU\n'
    '   * count Prime-style concurrency gates consume. */\n'
    '#ifdef _WIN32\n'
    '  DWORD n = GetActiveProcessorCount(ALL_PROCESSOR_GROUPS);\n'
    '  return n > 0 ? (double)n : 1.0;\n'
    '#else\n'
    '  long n = sysconf(_SC_NPROCESSORS_ONLN);\n'
    '  return n > 0 ? (double)n : 1.0;\n'
    '#endif\n'
    '}\n\n'
    '/* ── os.networkInterfaces(): the getifaddrs(3) snapshot ────────────────\n',
)

# 7) Frontend composed lowering. Do this before the ordinary property path
# lowers the cpus() call itself (which intentionally has no CpuInfo[] IR).
replace_once(
    "packages/compiler/src/frontend/lowering/lower-exprs.ts",
    '      if (isRequireMainFilename(L, expr)) {\n'
    '        return { kind: "strLit", value: L.entry.fileName, type: STRING, loc };\n'
    '      }\n'
    '      // Optional chaining `a?.b`: the guard lowers here (a tag test around\n',
    '      if (isRequireMainFilename(L, expr)) {\n'
    '        return { kind: "strLit", value: L.entry.fileName, type: STRING, loc };\n'
    '      }\n'
    '      // `os.cpus().length`: the array ELEMENT shape (CpuInfo) is too rich\n'
    '      // for the static IR, but its length is an independent scalar host\n'
    '      // observation. Claim the composed expression BEFORE lowering cpus()\n'
    '      // itself; any attempt to inspect a CpuInfo row keeps the ordinary\n'
    '      // os.cpus surface fence. Provenance comes from the builtin binding,\n'
    '      // so a user function/method named cpus never matches.\n'
    '      if (\n'
    '        expr.name.text === "length" &&\n'
    '        !expr.questionDotToken &&\n'
    '        ts.isCallExpression(expr.expression) &&\n'
    '        !expr.expression.questionDotToken &&\n'
    '        expr.expression.arguments.length === 0\n'
    '      ) {\n'
    '        const callee = expr.expression.expression;\n'
    '        const bi = ts.isIdentifier(callee)\n'
    '          ? L.builtinImportOf(callee)\n'
    '          : ts.isPropertyAccessExpression(callee)\n'
    '            ? L.builtinMemberOf(callee)\n'
    '            : null;\n'
    '        if (bi?.module === "os" && bi.member === "cpus") {\n'
    '          return { kind: "libCall", fn: "os.cpuCount", args: [], type: F64, loc };\n'
    '        }\n'
    '      }\n'
    '      // Optional chaining `a?.b`: the guard lowers here (a tag test around\n',
)

# Differential corpus: both namespace and host behavior are exercised by the
# existing os test; only length is consumed, deliberately not a CpuInfo field.
replace_once(
    "tests/corpus/2096-os-type.ts",
    '// os.type() and os.totalmem() — differential against the host\'s own Node:\n'
    '// type() is uname(2)\'s sysname (the process.platform mapping pins it per\n'
    '// host), totalmem() is the same physical-memory byte count Node reads.\n',
    '// os.type(), os.totalmem(), and os.cpus().length — differential against\n'
    '// the host\'s own Node. The CPU projection intentionally validates only\n'
    '// the array length; CpuInfo row fields remain outside the static surface.\n',
)
replace_once(
    "tests/corpus/2096-os-type.ts",
    'console.log(Number.isInteger(mem));\n',
    'console.log(Number.isInteger(mem));\n\n'
    'const cpuCount = os.cpus().length;\n'
    'console.log(cpuCount > 0);\n'
    'console.log(Number.isInteger(cpuCount));\n',
)

# No inspection artifacts survive the real edit.
Path('.agent/os-wiring.txt').unlink(missing_ok=True)
print('implemented os.cpus().length -> os.cpuCount')
