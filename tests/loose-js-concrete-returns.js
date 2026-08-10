// Generated/bundled JS: --loose-js trusts concrete checker inference.
function makeParser(flag) {
  return function (left, right) { return flag ? String(left) : String(right); };
}

function createDeferred() {
  let settled = false;
  return {
    value: "ready",
    settle(value) { if (settled) return false; settled = true; return value === "ok"; },
    reject() { if (settled) return false; settled = true; return true; },
  };
}

class BundleLike {
  parse = this.parseMarkdown(true);
  parseInline = this.parseMarkdown(false);
  accepted = createDeferred();
  parseMarkdown(block) { return makeParser(block); }
}

const b = new BundleLike();
console.log(b.parse("L", "R"), b.parseInline("L", "R"), b.accepted.value, b.accepted.settle("ok"), b.accepted.reject());
