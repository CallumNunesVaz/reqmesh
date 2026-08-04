/// <reference types="vite/client" />

// `tsconfig.json` sets `"types": []`, so no ambient packages are pulled in
// automatically and Vite's own declarations — `*.css`, `*.svg`, `import.meta.env`
// — were never loaded. TypeScript 5 let a side-effect CSS import through
// regardless; TypeScript 7 reports it (TS2882), which is the more honest answer:
// the modules genuinely had no declaration.
//
// Referenced here rather than added to `"types"`, so the empty list keeps doing
// its job of not sweeping in every @types package that happens to be installed.
