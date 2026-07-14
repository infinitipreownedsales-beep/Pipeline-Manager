# CaddieOS

A personal on-course caddie that learns your actual game. Single-file React
artifact (`src/CaddieOS.jsx`) that runs on the Claude `window.storage` API.

The angle isn't GPS — Garmin/Arccos/Shot Scope own that. It's **"your caddie that
learns your real numbers."** Upload your launch-monitor data, get a player profile,
and get shot-by-shot calls that reflect how *you* actually hit it.

## What it does
- **Upload → understand → recommend.** Drop an SC4 Pro (or any launch-monitor) CSV;
  it auto-detects the format, recognizes your clubs, filters mishits/duplicates/bad
  data, and derives your stock carries — with a confirmation screen before anything
  is saved.
- **Caddie Profile.** Longest club, best scoring club, least-trusted club, smart
  targets, and per-club reliability — all from your real shots.
- **Live round engine.** Shot-by-shot club calls that adapt to lie, wind, and how
  each club is performing *today* (hot/cold detection, one-tap bench, live carry
  recalibration).
- **Trends.** Rounds, ratings, and a per-club report over your whole history.

## Run it
- **In a browser (easiest):** open `caddie.html` — double-click it, or host it (e.g.
  GitHub Pages). It's fully self-contained: React is bundled in, no internet needed,
  and it persists to `localStorage`. On a phone, open the file and "Add to Home
  Screen" for an app-like launch.
- **As a Claude artifact:** paste `src/CaddieOS.jsx` into a Claude chat; it renders
  live using the `window.storage` API.

### Rebuilding `caddie.html` after editing the source
```
npm install      # one time (esbuild + react + react-dom)
npm run build    # regenerates caddie.html from src/CaddieOS.jsx
```

## Files
- `src/CaddieOS.jsx` — the app (canonical source).
- `caddie.html` — self-contained runnable build (generated).
- `build/gen-html.mjs` — regenerates `caddie.html` from the source.
- `AUDIT.md` — engineering audit: bugs fixed, the importer, and what's next.

## Note on data
The app reads **distance and left/right**: it learns each club's stock carry, its
reliability (dispersion), and its miss side from your export's side-carry tracing or
spin axis. If a file lacks side data entirely, side-miss is simply omitted — never
fabricated.
