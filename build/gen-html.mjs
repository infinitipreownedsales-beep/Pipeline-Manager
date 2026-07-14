// Generates a self-contained, double-clickable caddie.html from src/CaddieOS.jsx.
// No bundler needed: React 18 (UMD) + Babel-standalone from CDN transpile the JSX
// in the browser, and window.storage is shimmed over localStorage so the app's
// save/load works exactly like it does in the Claude artifact runtime.
//
//   node build/gen-html.mjs   →   writes ./caddie.html
//
import fs from "fs";
import path from "path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
let src = fs.readFileSync(path.join(root, "src/CaddieOS.jsx"), "utf8");

// The artifact imports React and default-exports the component. In a UMD/global
// setup neither works, so rewrite both to the standalone equivalents.
src = src.replace(/^\s*import\s*\{([^}]*)\}\s*from\s*["']react["'];?\s*$/m,
                  "const {$1} = React;");
src = src.replace(/export\s+default\s+function\s+CaddieOS/, "function CaddieOS");

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>CaddieOS</title>
<style>html,body{margin:0;background:#f2f2f7;-webkit-tap-highlight-color:transparent}</style>
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js" crossorigin></script>
</head>
<body>
<div id="root">Loading your caddie…</div>
<script>
// Persist across sessions in this browser, matching the artifact's storage API.
window.storage = window.storage || {
  get: async (k) => { try { const v = localStorage.getItem(k); return v != null ? { value: v } : null; } catch (e) { return null; } },
  set: async (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} }
};
</script>
<script type="text/babel" data-presets="react">
${src}
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(React.createElement(CaddieOS));
</script>
</body>
</html>
`;

fs.writeFileSync(path.join(root, "caddie.html"), html);
console.log("Wrote caddie.html (" + (html.length / 1024).toFixed(0) + " kb). Open it in any browser.");
