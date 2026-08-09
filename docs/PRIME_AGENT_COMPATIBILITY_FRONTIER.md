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
- 46 native-build diagnostics.

The net count stayed at 46 while the blocker composition changed: readonly-tuple Set failures and the three-argument UTF-8 `fs.promises.writeFile` failure disappeared, while downstream failures such as `fs.promises.access` became visible. This is expected for poison-based whole-program lowering: capability closure exposes code that was previously skipped.

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
- function-identity Sets: `Set<() => void>` uses REF identity with closure retain/release/trace callbacks; the sanitized corpus includes a real `Holder → Set → closure → Holder` cycle
- `node:fs/promises.access(path, mode?)`: reuses `fs.access` semantics but settles/rejects through a Promise, including C/LLVM emitter and validator wiring

Each retained recent source increment passed:

- `pnpm build`
- `pnpm lint`
- C differential test
- C differential with `SCRIPTC_SAN=1` (ASan + RC audit)
- LLVM differential test
- LLVM differential with `SCRIPTC_SAN=1`

## Object.entries Prime probe

A temporary compiler probe was run against the real `EthanBird/prime-agent` workspace and then automatically removed from ScriptC source. Its tracked result is `PRIME_OBJECT_ENTRIES_PROBE.txt`.

The probe established two different problems rather than one:

### Theme path

`resolveThemeColors` is instantiated into a **fixed 55-field record** whose fields are all `number | string`; it has `index=none`. Therefore trying to recover the original generic `Record<string, ...>` index signature is the wrong model. The correct compatibility capability is direct head-consumed `Object.entries` iteration over a fixed record, snapshotting its declared keys and values without materializing `Array<[string,V]>`.

### Extension runner path

The `runner.ts` call did **not** reach the probe inside the `recT` branch at all. Therefore its `resolvedKeybindings` source currently maps/probes to something other than a record. A second, shallower probe must log the checker type, index infos, `mapType(arg)`, and `probeLower(arg)` even when `recT` is null. Do not broaden Object.entries based on guesses before that probe.

## Next work

1. Run the shallow runner probe and identify why `KeybindingsConfig` is not producing a record representation.
2. Independently add fixed-record direct `for...of Object.entries(...)` for homogeneous/convertible declared fields, which should close the theme blocker.
3. Re-run the Prime raw oracle after these changes and measure the new frontier.
4. Continue with high-closure items such as Promise widening, record/index-signature width capture, module namespace values, `Array.from(Set)`, and weak containers.

Keep `Buffer.isBuffer(Uint8Array)` fenced until Buffer branding is represented: Buffer is a Uint8Array subclass, but a plain Uint8Array is not a Buffer, so returning a constant based on the shared bytes representation would be wrong.

## Prime oracle policy

After focused tests pass, run the Prime Agent oracle:

1. official Prime workspace build
2. ScriptC native build with `--dynamic`
3. native binary smoke if an executable is produced
4. full ScriptC `coverage --dynamic`
5. inspect the raw uploaded status files and build diagnostics artifact

Only the raw artifact is authoritative for the compatibility count.