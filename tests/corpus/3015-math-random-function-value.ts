const first = Math.random;
const second = Math.random;
console.log("identity", first === second);

function inRange(random: () => number = Math.random): boolean {
  const value = random();
  return value >= 0 && value < 1;
}
console.log("default", inRange());
console.log("direct", inRange(Math.random));
