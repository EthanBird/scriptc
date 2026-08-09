import { writeFile } from "node:fs/promises";

await writeFile("tmp-3005-fsp-writefile-utf8.txt", "héllo ScriptC\n", "utf-8");
console.log("fsp writeFile utf-8 ok");
await writeFile("tmp-3005-fsp-writefile-utf8.txt", "utf8 alias\n", "utf8");
console.log("fsp writeFile utf8 ok");
