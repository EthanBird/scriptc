// os.type(), os.totalmem(), and os.cpus().length — differential against
// the host's own Node. The CPU projection intentionally validates only
// the array length; CpuInfo row fields remain outside the static surface.
import * as os from "node:os";

const expected =
  process.platform === "darwin"
    ? "Darwin"
    : process.platform === "win32"
      ? "Windows_NT"
      : "Linux";
console.log(os.type() === expected);
console.log(os.type().length > 0);

const mem = os.totalmem();
console.log(mem > 0);
console.log(Number.isInteger(mem));

const cpuCount = os.cpus().length;
console.log(cpuCount > 0);
console.log(Number.isInteger(cpuCount));
