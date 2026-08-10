// import.meta.url is a file-backed ESM module constant. Avoid printing the
// checkout's absolute path; assert the stable URL properties differentially.
console.log(import.meta.url.startsWith("file:"));
console.log(import.meta.url.includes("3002-import-meta-url.ts"));
console.log(!import.meta.url.includes(" "));
