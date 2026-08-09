// Readonly tuples are valid Set iterables. ScriptC snapshots their fixed
// positional record representation into a fresh homogeneous seed array.
const SESSION_NAMES = ["compact", "refine", "goal", "autonomous"] as const;
const SESSION_NAME_SET: ReadonlySet<string> = new Set(SESSION_NAMES);
console.log(
  SESSION_NAME_SET.size,
  SESSION_NAME_SET.has("compact"),
  SESSION_NAME_SET.has("missing"),
  [...SESSION_NAME_SET].join(","),
);

const DUPLICATES = ["name", "kill", "name"] as const;
const UNIQUE: ReadonlySet<string> = new Set(DUPLICATES);
console.log(UNIQUE.size, [...UNIQUE].join("|"));
