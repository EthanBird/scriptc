# Prime Agent compatibility frontier

This document is the recovery checkpoint for the `agent/prime-compat-phase1` workstream.

## Ground rules

- `EthanBird/prime-agent` is an external compatibility oracle. Do not patch Prime Agent merely to make ScriptC pass.
- Prefer reusable ScriptC language/runtime/Node compatibility over project-specific rewrites.
- Every compatibility increment must be covered by ScriptC tests and then measured against the Prime Agent native build.
- Do not count a green workflow step as compatibility unless the raw compiler/build/smoke exit status is green.

## Last trusted Prime Agent baseline

The last fully inspected Prime compatibility run reduced the native-build frontier from 66 blockers through 57, 55, and 53 to approximately 48 remaining blockers while full `coverage --dynamic` completed without a compiler ICE.

Already landed capabilities include:

- builtin admission for `node:process` and `node:readline/promises`
- checker-union/runtime-representation crash hardening and dynamic-island property bridging
- `package.json#imports` resolution in the embedded npm graph
- `os.cpus().length` lowering through an internal CPU-count scalar
- cycle-safe reference-identity `Set<Class>` / `Set<Promise>` support, including traced REF keys
- `import.meta.url` as a compile-time module URL
- initial direct `for...of Object.entries(Record<string, T>)` lowering

## Current work item

`for (const [k, v] of Object.entries(record))` is being made Node-exact without requiring a first-class `Array<[string, T]>` value. The first direct lowering passed focused build/lint/C/ASan/LLVM tests, but review found an observability issue: `Object.entries()` snapshots both keys and values before the loop body executes. The current work is therefore to use a key/value double snapshot and to add a mutation-during-iteration differential regression before declaring this capability finished.

Generic `T extends Record<string, ...>` handling is intentionally tracked separately from the non-generic `Record<string, T>` lowering so that generic constraint recovery does not destabilize the simpler path.

## Next high-yield items

1. Finish exact `Object.entries` direct iteration and re-run Prime oracle.
2. Support `new Set(readonlyTuple)` by snapshotting a homogeneous readonly tuple into an array before `setNew`; this targets Prime's `as const` command-name sets without weakening record identity semantics.
3. Support `node:fs/promises.writeFile(path, string, "utf-8")` by reusing the existing UTF-8 promise runtime operation.
4. Continue module namespace/value representation, WeakMap, common Object/Array surface, and native-addon/provider work according to measured blocker closure.

## Validation policy

For each new corpus case run, at minimum:

- `pnpm build`
- `pnpm lint`
- C differential test
- C differential with `SCRIPTC_SAN=1` (ASan + RC audit)
- LLVM differential test
- LLVM differential with `SCRIPTC_SAN=1`

After focused tests pass, run the Prime Agent oracle: official Prime workspace build, ScriptC native build with `--dynamic`, native smoke when a binary is produced, and full ScriptC coverage.
