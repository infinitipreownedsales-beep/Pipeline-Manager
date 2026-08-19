// TEMPORARY FIELD BRIDGE build — a self-contained phone-usable CaddieOS_Field_Bridge_12_1.html.
// Identical source to the canonical app, but compiled with FIELD_BRIDGE=true, which:
//   - makes automatic in-round club Bench INERT (no club is ever hard-locked);
//   - removes the auto-bench prompt (performance still warns/ranks, never confiscates);
//   - strips stale bench state when a prior round is restored;
//   - exposes a manual "use any club" override the golfer can always reach.
// This is a FIELD-TEST CANDIDATE, not a canonical product build. It does NOT overwrite
// caddie.html / artifact.html, and does NOT touch the 12.0 rollback artifact.
//
//   node build/gen-field-bridge.mjs   →   writes ./CaddieOS_Field_Bridge_12_1.html
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
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"', "FIELD_BRIDGE": "true" },
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
<title>CaddieOS Field Bridge 12.1</title>
<style>html,body{margin:0;background:#f2f2f7;-webkit-tap-highlight-color:transparent}
#root{min-height:100vh}</style>
</head>
<body>
<div id="root">Loading your caddie…</div>
<script>${js}</script>
</body>
</html>
`;

fs.writeFileSync(path.join(root, "CaddieOS_Field_Bridge_12_1.html"), html);
console.log("Wrote CaddieOS_Field_Bridge_12_1.html (" + (html.length / 1024).toFixed(0) + " kb, self-contained field-test candidate).");
