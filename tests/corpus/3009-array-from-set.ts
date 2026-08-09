const values = new Set<string>();
values.add("beta");
values.add("alpha");
values.add("beta");

const first = Array.from(values);
console.log("first", first.length, first.join("|"));
values.add("gamma");
console.log("snapshot", first.join("|"));
console.log("second", Array.from(values).join("|"));
