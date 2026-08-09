// Closures have stable runtime pointer identity. A Set stores them as REF
// keys with closure retain/release and trace callbacks.
const a = (): void => console.log("same-body");
const b = (): void => console.log("same-body");
const ids = new Set<() => void>();
ids.add(a);
ids.add(a);
ids.add(b);
console.log("identity", ids.size, ids.has(a), ids.has(b));
a();

// Strong cycle regression: Holder -> Set -> closure -> captured Holder.
// The sanitized/RC-audit lanes must reclaim this at the final cycle sweep.
class Holder {
  readonly callbacks = new Set<() => void>();

  arm(): void {
    const cb = (): void => {
      console.log("cycle-callback", this.callbacks.size);
    };
    this.callbacks.add(cb);
    this.callbacks.add(cb);
    console.log("cycle-set", this.callbacks.size, this.callbacks.has(cb));
    cb();
  }
}

function makeCycle(): void {
  const holder = new Holder();
  holder.arm();
}
makeCycle();
