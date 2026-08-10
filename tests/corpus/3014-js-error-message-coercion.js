// @dynamic
console.log(String(new Error("text")));
console.log(String(new Error(42)));
console.log(String(new Error(false)));
console.log(String(new Error(null)));
console.log(String(new Error(undefined)));
class WrappedError extends Error { constructor(message) { super(message); } }
console.log(String(new WrappedError("text")));
console.log(String(new WrappedError(42)));
console.log(String(new WrappedError(false)));
console.log(String(new WrappedError(null)));
console.log(String(new WrappedError(undefined)));
let calls=0; function once(){ calls++; return 123; }
console.log(String(new Error(once())), calls);
