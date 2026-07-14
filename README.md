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

## Files
- `src/CaddieOS.jsx` — the app.
- `AUDIT.md` — engineering audit: bugs fixed, the importer, and what's next.

## Note on data
The SC4 Pro is a Doppler radar behind the ball: it measures distance/ball/club data,
not left/right offline. The app reports distance reliability honestly and only shows
side-miss when the uploaded file actually contains an offline column.
