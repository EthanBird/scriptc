// Strong-reference Set identity: class instances and promises use their
// stable runtime pointer as SameValueZero identity. The class self-cycle is
// intentional: sanitized/RC-audit runs must reclaim Node -> Set -> Node at
// the final cycle sweep, proving ref-key Sets participate in tracing.
class Node {
  peers = new Set<Node>();
}

function classCycle(): void {
  const n = new Node();
  n.peers.add(n);
  n.peers.add(n);
  console.log(n.peers.has(n), n.peers.size);
}
classCycle();

async function answer(): Promise<number> {
  return 42;
}
const p = answer();
const pending = new Set<Promise<number>>();
pending.add(p);
pending.add(p);
console.log(pending.has(p), pending.size);
