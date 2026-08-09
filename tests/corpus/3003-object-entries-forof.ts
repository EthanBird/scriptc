// Direct Object.entries for-of over pure index-signature records. The loop
// must not require a first-class Array<[string, T]> representation.

type BindingValue = string | string[] | undefined;
const bindings: Record<string, BindingValue> = {};
bindings["save"] = "ctrl+s";
bindings["open"] = ["ctrl+o", "alt+o"];
bindings["unset"] = undefined;
for (const [key, value] of Object.entries(bindings)) {
  if (value === undefined) {
    console.log(key, "undefined");
  } else if (Array.isArray(value)) {
    console.log(key, value.join("|"));
  } else {
    console.log(key, value);
  }
}

function copyColors<T extends Record<string, string | number>>(colors: T): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(colors)) out[key] = value;
  return out;
}
const colors: Record<string, string | number> = {};
colors["accent"] = "#fff";
colors["level"] = 7;
console.log(JSON.stringify(copyColors(colors)));
