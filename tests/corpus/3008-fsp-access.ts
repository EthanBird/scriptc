import { access } from "node:fs/promises";

await access("package.json");
await access("package.json", 4);
console.log("fsp access ok");

try {
  await access("scriptc-3008-definitely-missing-file", 4);
  console.log("unexpected access success");
} catch {
  console.log("fsp access rejected");
}
