// @dynamic
import { Box, getConfig } from "data-alias";
import type { BoxAlias, Config } from "data-alias";
const remote: Config = getConfig();
console.log("remote", remote.label, remote.value());
const box: BoxAlias = new Box("boxed");
console.log("box", box.value());
