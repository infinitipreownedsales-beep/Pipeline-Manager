// Builds a fully self-contained, double-clickable caddie.html from src/CaddieOS.jsx.
// React + ReactDOM + the app are bundled and INLINED — no CDN, no runtime Babel, no
// network at all. Works offline, on any phone or desktop browser, and on GitHub Pages.
// window.storage is shimmed over localStorage inside the bundle.
//
//   node build/gen-html.mjs   →   writes ./caddie.html
//
import esbuild from "esbuild";
import fs from "fs";
import path from "path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

const result = await esbuild.build({
  entryPoints: [path.join(root, "build/entry.jsx")],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2018"],
  loader: { ".jsx": "jsx" },
  jsx: "automatic",   // inject react/jsx-runtime per file — CaddieOS.jsx never imports React itself
  define: { "process.env.NODE_ENV": '"production"' },
  write: false,
});
const js = result.outputFiles[0].text;

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<meta name="apple-mobile-web-app-capable" content="yes"/>
<meta name="mobile-web-app-capable" content="yes"/>
<meta name="theme-color" content="#1a3a2e"/>
<title>CaddieOS</title>
<style>html,body{margin:0;background:#f2f2f7;-webkit-tap-highlight-color:transparent}
#root{min-height:100vh}</style>
</head>
<body>
<div id="root">Loading your caddie…</div>
<script>${js}</script>
</body>
</html>
`;

fs.writeFileSync(path.join(root, "caddie.html"), html);
console.log("Wrote caddie.html (" + (html.length / 1024).toFixed(0) + " kb, fully self-contained). Open it in any browser.");
