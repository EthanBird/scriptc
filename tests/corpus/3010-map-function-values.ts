// Function values in Map use ScrClosure strong ownership and tracing.
const handlers = new Map<string, () => void>();
const a = (): void => console.log("handler-a");
const b = (): void => console.log("handler-b");
handlers.set("a", a);
handlers.set("same", a);
handlers.set("b", b);
console.log("map-fn", handlers.size, handlers.get("a") === a, handlers.get("same") === a);
handlers.get("b")!();

// Strong cycle regression: Holder -> Map -> closure -> captured Holder.
// The sanitized/RC-audit lanes must reclaim this at the final cycle sweep.
class Holder {
  readonly handlers = new Map<string, () => void>();

  arm(): void {
    const cb = (): void => {
      console.log("cycle-map-callback", this.handlers.size);
    };
    this.handlers.set("self", cb);
    this.handlers.set("self", cb);
    console.log("cycle-map", this.handlers.size, this.handlers.get("self") === cb);
    cb();
  }
}

function makeCycle(): void {
  const holder = new Holder();
  holder.arm();
}
makeCycle();
