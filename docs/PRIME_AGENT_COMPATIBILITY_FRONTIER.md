# Prime Agent compatibility frontier

This document is the recovery checkpoint for the `agent/prime-compat-phase1` workstream.

## Ground rules

- `EthanBird/prime-agent` is an external compatibility oracle. Do not patch Prime Agent merely to make ScriptC pass.
- Prefer reusable ScriptC language/runtime/Node compatibility over project-specific rewrites.
- Every compatibility increment must be covered by ScriptC tests and then measured against the Prime Agent native build.
- Do not count a green workflow step as compatibility unless the raw compiler/build/smoke exit status is green.
- Development is checkpoint-first: keep small pushed commits; focused source changes are applied transactionally and are reverted automatically if their required tests fail.

## Last trusted Prime Agent raw baseline

The last fully inspected diagnostic artifact reported:

- `coverage = 0`
- `build = 1`
- `smoke = 125` (no executable because native build still has blockers)
- 46 native-build diagnostics, down from the earlier 66 → 57 → 55 → 53 → ~48 frontier.

That 46-diagnostic run already contained the header-family type fix, exact `Object.entries` value snapshots, and readonly-tuple Set support. It did **not** yet contain the subsequently validated `fs/promises.writeFile(..., "utf8" | "utf-8")` source commit nor the Prime-style template-`KeyId` Object.entries binding fix. A newer Prime oracle is running over the current source; do not claim a lower number until its raw artifact is inspected.

## Validated capabilities landed

- builtin admission for `node:process` and `node:readline/promises`
- checker-union/runtime-representation crash hardening and dynamic-island property bridging
- `package.json#imports` resolution in the embedded npm graph
- `os.cpus().length` lowering through an internal CPU-count scalar
- cycle-safe reference-identity `Set<Class>` / `Set<Promise>` support, including traced REF keys
- `import.meta.url` as a compile-time module URL
- HTTP header-family canonicalization narrowed so declaration-free `Record<string, V>` types are not silently widened to the outgoing-header value union
- direct `for...of Object.entries(Record<string, T>)` lowering without materializing `Array<[string,T]>`
- Node-exact Object.entries key **and value** snapshots, including mutation-during-iteration regression coverage
- Prime-style template-literal `KeyId | KeyId[] | undefined` Object.entries bindings use the already-proven index-signature runtime representation instead of requiring a redundant second type mapping
- `new Set(readonlyTuple)` for homogeneous readonly tuples such as `const NAMES = [...] as const`, preserving insertion order and duplicate collapse
- `node:fs/promises.writeFile(path, string, "utf8" | "utf-8")` through the existing promise write runtime, with fallback declaration support

Each of the recent source increments above was retained only after:

- `pnpm build`
- `pnpm lint`
- C differential test
- C differential with `SCRIPTC_SAN=1` (ASan + RC audit)
- LLVM differential test
- LLVM differential with `SCRIPTC_SAN=1`

## Current work item

The next targeted Prime blocker is `Set<() => void>` in the kernel lifecycle code. This is only safe to enable if closure values use stable pointer identity and the REF-key Set path owns and traces them correctly.

The existing infrastructure already strongly suggests this is a small missing gate rather than a new container implementation:

- closures are refcounted (`ScrClosure *`)
- C has closure retain/release adapters and `scr_closure_trace_v`
- Set REF keys already receive retain/release/trace callbacks
- the C/LLVM cycle-capability fixpoints already classify closures as cycle-capable
- LLVM has closure `_v` retain/release adapters

Before enabling the type, verify the LLVM key classifier and trace adapter, then add a regression that exercises both identity and a real `Holder → Set<closure> → closure capture → Holder` cycle. The sanitized RC audit must reclaim it.

## Remaining high-yield frontier

After function-identity Sets, prioritize by measured Prime closure rate rather than feature count:

1. generic `Object.entries` / generic Record instance recovery in the theme path
2. Promise covariance/widening needed by `Promise<void>` → `Promise<unknown>`
3. record/index-signature width capture used by keybindings/theme configuration
4. module namespace objects as first-class values
5. WeakMap/WeakSet semantics
6. common Array/Object surfaces (`Array.from`, computed `in`, spread-call shapes)
7. external-class/overloaded-function records
8. Proxy / Intl.Segmenter where required
9. native providers/addon interop (ZeroMQ, clipboard, photon) after the static/runtime core closes enough of the graph

Keep `Buffer.isBuffer(Uint8Array)` fenced until Buffer branding is represented: Buffer is a Uint8Array subclass, but a plain Uint8Array is not a Buffer, so returning a constant based on the shared bytes representation would be wrong.

## Prime oracle policy

After focused tests pass, run the Prime Agent oracle:

1. official Prime workspace build
2. ScriptC native build with `--dynamic`
3. native binary smoke if an executable is produced
4. full ScriptC `coverage --dynamic`
5. inspect the raw uploaded status files and build diagnostics artifact

Only the raw artifact is authoritative for the compatibility count.