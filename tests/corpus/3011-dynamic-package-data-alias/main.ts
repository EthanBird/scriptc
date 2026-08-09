// @dynamic
import { Box, getConfig } from "data-alias";
import type { BoxAlias, Config } from "data-alias";

const local: Config = {};
local["save"] = "ctrl+s";
local["open"] = ["ctrl+o", "alt+o"];
local["unset"] = undefined;
for (const [key, value] of Object.entries(local)) {
  if (value === undefined) console.log("local", key, "undefined");
  else if (Array.isArray(value)) console.log("local", key, value.join("|"));
  else console.log("local", key, value);
}

// The package returns a JS-engine object, but Config is pure data: the
// declared alias may exit through the validated static record boundary.
const remote: Config = getConfig();
console.log("remote", remote["alpha"], Array.isArray(remote["list"]));

// An alias to a package CLASS still follows the underlying runtime class
// identity and stays in the dynamic engine rather than becoming a record.
const box: BoxAlias = new Box("boxed");
console.log("box", box.value());
