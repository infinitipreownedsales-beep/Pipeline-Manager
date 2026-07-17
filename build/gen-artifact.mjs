// Builds artifact.html — the same self-contained bundle as caddie.html, but as
// body-content only (no <!doctype>/<html>/<head>/<body>), which is what the
// Claude Artifact host expects. Publishing this gives a hosted URL the user can
// open on any phone in a real browser (no file download, no in-app preview).
import esbuild from "esbuild";
import fs from "fs";
import path from "path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

const result = await esbuild.build({
  entryPoints: [path.join(root, "build/entry.jsx")],
  bundle: true, minify: true, format: "iife", target: ["es2018"],
  loader: { ".jsx": "jsx" }, jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  write: false,
});
const js = result.outputFiles[0].text;

const page = `<title>CaddieOS</title>
<style>#root{min-height:100vh}</style>
<div id="root">Loading your caddie…</div>
<script>
window.storage = window.storage || {
  get: async (k) => { try { const v = localStorage.getItem(k); return v != null ? { value: v } : null; } catch (e) { return null; } },
  set: async (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} }
};
</script>
<script>${js}</script>
`;

fs.writeFileSync(path.join(root, "artifact.html"), page);
console.log("Wrote artifact.html (" + (page.length / 1024).toFixed(0) + " kb).");
