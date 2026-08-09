from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, got {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

replace_once(
    "packages/compiler/src/ir/nodes.ts",
    '''  /** ES `Set<T>` — heap, refcounted, insertion-ordered. Map's sibling with
   * the value slot removed: ONE runtime representation (the backend lowers
   * sets onto the map runtime with a constant unit value), elements are
   * exactly Map's KEY types — f64 or string, SameValueZero. Same container
   * fences as map (no union arms, no array elements, no map values, no sets
   * of sets, not JSON-safe) and never cycle-capable: elements are scalars
   * or strings, which cannot point back. */
  | { kind: "set"; elem: IrType }
''',
    '''  /** ES `Set<T>` — heap, refcounted, insertion-ordered. Map's sibling with
   * the value slot removed: ONE runtime representation (the backend lowers
   * sets onto the map runtime with a constant unit value). Primitive keys
   * use SameValueZero (f64/string); selected heap values whose JS identity
   * is their stable runtime pointer (class instances, promises, server
   * handles, symbols) use SCR_MAP_KEY_REF. A ref-key set is cycle-capable
   * exactly when its element type is: the runtime traces key edges just as
   * ref-valued Maps trace value edges. Other identity worlds (records,
   * unions, dyn/jsval wrappers) remain fenced until their identity model is
   * proven stable. Sets remain non-JSON and outside union/array slots. */
  | { kind: "set"; elem: IrType }
''',
)
replace_once(
    "packages/compiler/src/ir/nodes.ts",
    '''/** The Set ELEMENT fence — Map's key fence plus the refcounted HANDLE
 * kinds stored under identity hashing (SameValueZero for JS objects IS
 * reference identity, so a Set of server handles — portless's auxiliary-
 * server registry — is honest hashed storage; SCR_MAP_KEY_REF in the
 * runtime). netServer is the one handle admitted so far: it drops its
 * listener closures at close, so a set-in-listener cycle is temporary —
 * the child precedent's story. Symbols are identity values by DESIGN —
 * SameValueZero on a symbol IS pointer identity, so a Set of symbols (the
 * sentinel-registry idiom) is the same honest hashed storage with no
 * cycle risk at all (symbols hold only strings). */
export function isSupportedSetElem(t: IrType): boolean {
  return isSupportedMapKey(t) || t.kind === "netServer" || t.kind === "symbol";
}
''',
    '''/** The Set ELEMENT fence — Map's scalar key fence plus values whose
 * JavaScript object identity is exactly their stable runtime pointer.
 * class instances and promises need strong-key cycle tracing (a member can
 * point back at the Set); server handles and symbols are acyclic identity
 * values. Structural records/unions and dyn/jsval wrappers stay fenced:
 * their lowering may copy/rebox, so pointer identity is not yet a proof of
 * JavaScript identity. */
export function isSupportedSetElem(t: IrType): boolean {
  return (
    isSupportedMapKey(t) ||
    t.kind === "object" ||
    t.kind === "promise" ||
    t.kind === "netServer" ||
    t.kind === "symbol"
  );
}
''',
)
replace_once(
    "packages/compiler/src/backend/emission/emit-types.ts",
    '''  if (key.kind === "netServer" || key.kind === "symbol") return "ref";
  throw new Error(`emitter bug: map key of ${key.kind} (frontend rejects these)`);
''',
    '''  if (
    key.kind === "netServer" || key.kind === "symbol" ||
    key.kind === "object" || key.kind === "promise"
  ) return "ref";
  throw new Error(`emitter bug: map key of ${key.kind} (frontend rejects these)`);
''',
)
replace_once(
    "packages/runtime/src/scr_runtime.h",
    '''  /* SCR_MAP_KEY_REF only (scr_set_new_ref); NULL otherwise. */
  void *(*key_retain)(void *);
  void (*key_release)(void *);
  size_t nentries; /* dense entries used, tombstones included */
''',
    '''  /* SCR_MAP_KEY_REF only (scr_set_new_ref); NULL otherwise. A non-NULL
   * key_trace means the key type carries a cycle header, so ref-key Sets
   * allocate with the collector header and trace every live key edge. */
  void *(*key_retain)(void *);
  void (*key_release)(void *);
  ScrTraceFn key_trace;
  size_t nentries; /* dense entries used, tombstones included */
''',
)
replace_once(
    "packages/runtime/src/scr_runtime.h",
    '''ScrMap *scr_set_new_ref(void *(*elem_retain)(void *), void (*elem_release)(void *));
''',
    '''ScrMap *scr_set_new_ref(void *(*elem_retain)(void *), void (*elem_release)(void *),
                            ScrTraceFn elem_trace);
''',
)
replace_once(
    "packages/runtime/src/scr_map.c",
    '''static void scr_map_trace(void *o, ScrTraceVisit visit, void *ctx) {
  ScrMap *m = (ScrMap *)o;
  for (size_t e = 0; e < m->nentries; e++) {
    if (m->entries[e].live) visit(scr_map_slot_to_ptr(m->entries[e].val), ctx);
  }
}

/* Collector teardown: the trace visits every live VALUE (traced edges were
 * already accounted), so the complement released here is the keys. */
static void scr_map_gcfree(void *o) {
  ScrMap *m = (ScrMap *)o;
  for (size_t e = 0; e < m->nentries; e++) {
    if (m->entries[e].live) scr_map_release_key(m, m->entries[e].key);
  }
  free(m->entries);
  free(m->buckets);
#ifdef SCR_RC_AUDIT
  scr_live_maps--;
#endif
  scr_cyc_free(m);
}

ScrMap *scr_map_new(ScrMapKeyKind key_kind, ScrMapValKind val_kind,
                     void *(*val_retain)(void *), void (*val_release)(void *),
                     ScrTraceFn val_trace) {
  ScrMap *m;
  if (val_trace) {
    /* Cycle-capable values can point back: collector header + trace. */
    m = scr_cyc_alloc(sizeof *m, &scr_map_trace, &scr_map_gcfree);
  } else {
    m = calloc(1, sizeof *m);
    if (!m) scr_map_oom();
  }
  m->rc = 1;
  m->key_kind = key_kind;
  m->val_kind = val_kind;
  m->val_retain = val_retain;
  m->val_release = val_release;
  m->val_trace = val_trace;
#ifdef SCR_RC_AUDIT
  scr_live_maps++;
#endif
  return m;
}
''',
    '''static bool scr_map_is_traced(const ScrMap *m) {
  return m->key_trace != NULL || m->val_trace != NULL;
}

static void scr_map_trace(void *o, ScrTraceVisit visit, void *ctx) {
  ScrMap *m = (ScrMap *)o;
  for (size_t e = 0; e < m->nentries; e++) {
    if (!m->entries[e].live) continue;
    if (m->key_trace) visit(scr_map_slot_to_ptr(m->entries[e].key), ctx);
    if (m->val_trace) visit(scr_map_slot_to_ptr(m->entries[e].val), ctx);
  }
}

/* Collector teardown releases exactly the complement of the edges visited
 * above. Traced key/value edges were trial-deleted by the collector; the
 * acyclic side still needs its ordinary release here. */
static void scr_map_gcfree(void *o) {
  ScrMap *m = (ScrMap *)o;
  for (size_t e = 0; e < m->nentries; e++) {
    if (!m->entries[e].live) continue;
    if (!m->key_trace) scr_map_release_key(m, m->entries[e].key);
    if (!m->val_trace) scr_map_release_val(m, m->entries[e].val);
  }
  free(m->entries);
  free(m->buckets);
#ifdef SCR_RC_AUDIT
  scr_live_maps--;
#endif
  scr_cyc_free(m);
}

static ScrMap *scr_map_new_full(
    ScrMapKeyKind key_kind, ScrMapValKind val_kind,
    void *(*val_retain)(void *), void (*val_release)(void *), ScrTraceFn val_trace,
    void *(*key_retain)(void *), void (*key_release)(void *), ScrTraceFn key_trace) {
  ScrMap *m;
  if (key_trace || val_trace) {
    m = scr_cyc_alloc(sizeof *m, &scr_map_trace, &scr_map_gcfree);
  } else {
    m = calloc(1, sizeof *m);
    if (!m) scr_map_oom();
  }
  m->rc = 1;
  m->key_kind = key_kind;
  m->val_kind = val_kind;
  m->val_retain = val_retain;
  m->val_release = val_release;
  m->val_trace = val_trace;
  m->key_retain = key_retain;
  m->key_release = key_release;
  m->key_trace = key_trace;
#ifdef SCR_RC_AUDIT
  scr_live_maps++;
#endif
  return m;
}

ScrMap *scr_map_new(ScrMapKeyKind key_kind, ScrMapValKind val_kind,
                     void *(*val_retain)(void *), void (*val_release)(void *),
                     ScrTraceFn val_trace) {
  return scr_map_new_full(key_kind, val_kind, val_retain, val_release, val_trace,
                          NULL, NULL, NULL);
}
''',
)
replace_once(
    "packages/runtime/src/scr_map.c",
    '''ScrMap *scr_map_retain(ScrMap *m) {
  if (m->rc != SIZE_MAX) {
    m->rc++;
    if (m->val_trace) scr_cyc_mark_live(m);
  }
  return m;
}

void scr_map_release(ScrMap *m) {
  if (!m || m->rc == SIZE_MAX) return; /* NULL: an uninitialized `let` local */
  if (--m->rc == 0) {
    if (m->val_trace) scr_cyc_on_dead(m);
''',
    '''ScrMap *scr_map_retain(ScrMap *m) {
  if (m->rc != SIZE_MAX) {
    m->rc++;
    if (scr_map_is_traced(m)) scr_cyc_mark_live(m);
  }
  return m;
}

void scr_map_release(ScrMap *m) {
  if (!m || m->rc == SIZE_MAX) return; /* NULL: an uninitialized `let` local */
  if (--m->rc == 0) {
    if (scr_map_is_traced(m)) scr_cyc_on_dead(m);
''',
)
replace_once(
    "packages/runtime/src/scr_map.c",
    '''    if (m->val_trace) scr_cyc_free(m);
    else free(m);
  } else if (m->val_trace) {
    scr_cyc_on_release(m); /* possible cycle root; may collect — m is done */
  }
}
''',
    '''    if (scr_map_is_traced(m)) scr_cyc_free(m);
    else free(m);
  } else if (scr_map_is_traced(m)) {
    scr_cyc_on_release(m); /* possible cycle root; may collect — m is done */
  }
}
''',
)
replace_once(
    "packages/runtime/src/scr_map.c",
    '''ScrMap *scr_set_new_ref(void *(*elem_retain)(void *), void (*elem_release)(void *)) {
  ScrMap *m = scr_map_new(SCR_MAP_KEY_REF, SCR_MAP_VAL_F64, NULL, NULL, NULL);
  m->key_retain = elem_retain;
  m->key_release = elem_release;
  return m;
}
''',
    '''ScrMap *scr_set_new_ref(void *(*elem_retain)(void *), void (*elem_release)(void *),
                            ScrTraceFn elem_trace) {
  return scr_map_new_full(SCR_MAP_KEY_REF, SCR_MAP_VAL_F64,
                          NULL, NULL, NULL,
                          elem_retain, elem_release, elem_trace);
}
''',
)
replace_once(
    "packages/compiler/src/backend/emission/emitter.ts",
    '''        case "map":
          return cycleCapable(t.value);
        // An array is cycle-capable exactly when its ELEMENT type is —
''',
    '''        case "map":
          return cycleCapable(t.value);
        case "set":
          return cycleCapable(t.elem);
        // An array is cycle-capable exactly when its ELEMENT type is —
''',
)
replace_once(
    "packages/compiler/src/backend/emission/emit-shapes.ts",
    '''      case "map":
        return E.traceAdapterC(t.value) !== null ? "scr_map_trace_v" : null;
      // Arrays mirror maps: cycle-capable exactly when the ELEMENT type is
''',
    '''      case "map":
        return E.traceAdapterC(t.value) !== null ? "scr_map_trace_v" : null;
      case "set":
        return E.traceAdapterC(t.elem) !== null ? "scr_map_trace_v" : null;
      // Arrays mirror maps: cycle-capable exactly when the ELEMENT type is
''',
)
replace_once(
    "packages/compiler/src/backend/emission/emit-exprs.ts",
    '''          rcAdapters
            ? `scr_set_new_ref(&${rcAdapters.retain}, &${rcAdapters.release})`
            : `scr_map_new(${mapKeyKindC(e.type.elem)}, SCR_MAP_VAL_F64, NULL, NULL, NULL)`,
''',
    '''          rcAdapters
            ? `scr_set_new_ref(&${rcAdapters.retain}, &${rcAdapters.release}, ${E.traceArgC(e.type.elem)})`
            : `scr_map_new(${mapKeyKindC(e.type.elem)}, SCR_MAP_VAL_F64, NULL, NULL, NULL)`,
''',
)
replace_once(
    "packages/compiler/src/backend/llvm/shapes.ts",
    '''      case "map":
        return cycleCapable(t.value);
      case "array":
        return cycleCapable(t.elem);
''',
    '''      case "map":
        return cycleCapable(t.value);
      case "set":
        return cycleCapable(t.elem);
      case "array":
        return cycleCapable(t.elem);
''',
)
replace_once(
    "packages/compiler/src/backend/llvm/shapes.ts",
    '''    case "map":
      if (traceAdapter(host, t.value) === null) return null;
      host.declare(`declare void @scr_map_trace_v(ptr, ptr, ptr)`);
      return "@scr_map_trace_v";
    case "array":
''',
    '''    case "map":
      if (traceAdapter(host, t.value) === null) return null;
      host.declare(`declare void @scr_map_trace_v(ptr, ptr, ptr)`);
      return "@scr_map_trace_v";
    case "set":
      if (traceAdapter(host, t.elem) === null) return null;
      host.declare(`declare void @scr_map_trace_v(ptr, ptr, ptr)`);
      return "@scr_map_trace_v";
    case "array":
''',
)
replace_once(
    "packages/compiler/src/backend/llvm/shapes.ts",
    '''  if (key.kind === "symbol") return "ref";
  if (key.kind === "netServer") return "ref"; // handle identity (Set<Server>)
  throw new LlvmUnsupportedError(`mapKey:${key.kind}`);
''',
    '''  if (key.kind === "symbol") return "ref";
  if (key.kind === "netServer") return "ref"; // handle identity (Set<Server>)
  if (key.kind === "object" || key.kind === "promise") return "ref";
  throw new LlvmUnsupportedError(`mapKey:${key.kind}`);
''',
)
replace_once(
    "packages/compiler/src/backend/llvm/emitter.ts",
    '''      const rc = vAdapters(this, e.type.elem);
      this.declare(`declare ptr @scr_set_new_ref(ptr, ptr)`);
      B.line(`${s} = call ptr @scr_set_new_ref(ptr ${rc.retain}, ptr ${rc.release})`);
''',
    '''      const rc = vAdapters(this, e.type.elem);
      this.declare(`declare ptr @scr_set_new_ref(ptr, ptr, ptr)`);
      B.line(`${s} = call ptr @scr_set_new_ref(ptr ${rc.retain}, ptr ${rc.release}, ptr ${traceArg(this, e.type.elem)})`);
''',
)
case = Path("tests/corpus/3001-set-ref-identity.ts")
if case.exists():
    raise SystemExit(f"{case}: already exists")
case.write_text('''// Strong-reference Set identity: class instances and promises use their
// stable runtime pointer as SameValueZero identity. The class self-cycle is
// intentional: sanitized/RC-audit runs must reclaim Node -> Set -> Node at
// the final cycle sweep, proving ref-key Sets participate in tracing.
class Node {
  peers = new Set<Node>();
}

function classCycle(): void {
  const n = new Node();
  n.peers.add(n);
  n.peers.add(n);
  console.log(n.peers.has(n), n.peers.size);
}
classCycle();

async function answer(): Promise<number> {
  return 42;
}
const p = answer();
const pending = new Set<Promise<number>>();
pending.add(p);
pending.add(p);
console.log(pending.has(p), pending.size);
''', encoding="utf-8")
print("enabled cycle-safe Set<object|promise> identity")
