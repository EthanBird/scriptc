type Letter = "a" | "b" | "c";
type Modifier = "ctrl" | "alt";
type KeyId = Letter | `${Modifier}+${Letter}`;
type KeybindingsConfig = Record<string, KeyId | KeyId[] | undefined>;

const resolved: KeybindingsConfig = {};
resolved["submit"] = "ctrl+a";
resolved["copy"] = ["a", "alt+b"];
resolved["unset"] = undefined;

for (const [keybinding, keys] of Object.entries(resolved)) {
  if (keys === undefined) {
    console.log(keybinding, "unset");
    continue;
  }
  const list = Array.isArray(keys) ? keys : [keys];
  console.log(keybinding, list.join("|"));
}
