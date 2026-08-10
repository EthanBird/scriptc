// @dynamic
const values = ["text", 42, false, null, undefined];
for (const v of values) console.log(String(new Error(v)));
class WrappedError extends Error { constructor(message) { super(message); } }
for (const v of values) console.log(String(new WrappedError(v)));
let calls = 0;
function once() { calls++; return 123; }
console.log(String(new Error(once())), calls);
