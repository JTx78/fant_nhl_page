# Fantasy NHL Tracker

A static site tracking a 6-manager fantasy hockey league: live draft tracking during the
draft, then a season-long dashboard once games start. No build step, no server — plain
HTML/CSS/JS served by GitHub Pages, plus one small Python script and a GitHub Action to
keep the stats current.

## Pages

| Page | Purpose |
|---|---|
| `index.html` | Live 2026-27 lineup card — every manager's roster, filled slots, draft log |
| `dashboard.html` | Live 2026-27 season dashboard — standings, a cumulative-points race chart, hot/cold skaters |
| `index-2025.html` | Archive: the completed 2025-26 season's final rosters |
| `dashboard-2025.html` | Archive: the completed 2025-26 season's final dashboard |

`dashboard.html?sample` forces the pre-season sample data even after the real season data exists.

## League format

- 6 managers, 12 roster slots each: 8 Forwards, 3 Defense, 1 Team pick (an NHL team, not a player).
- Skaters score **2 × goals + 1 × assist**.
- The Team pick scores **−1 × goals against + 10 × shutouts** for that NHL team.
- No in-season trades, except a season-ending injury: the injured player's points are
  wiped, and the replacement's *full-season* points count from game one — not just from
  when they were added. This is why the data model stores per-game history rather than
  running point totals: a swap has to rewrite the past, and only per-game data lets it.

## Data layout

```
data/
  2025-2026/
    rosters.json         who owns whom, no draft log (season predates this tracker)
    playerdata.json       per-game skater stats
    teamdata.json          per-game Team-pick stats
  2026-2027/
    rosters.json         who owns whom + full pick-by-pick draft log
    playerdata.json       per-game skater stats (born on the season's first nightly run)
    teamdata.json          per-game Team-pick stats (same)
    sample-playerdata.json  pre-season fallback: last season's stats replayed on this year's rosters
    sample-teamdata.json
```

**`rosters.json`** is the source of truth for who's on which roster. Each skater carries a
verified NHL `playerId`; each team's roster has a `replaced: []` array for the injury rule
above. `draftLog` (2026-2027 only) is an ordered list of `{pick, teamId, name, pos}`.

**`playerdata.json`** holds one array of per-game records per player, keyed by playerId.
Each game record is intentionally broad — goals, assists, shots, PIM, TOI, power-play/
shorthanded/game-winning/OT goals, plus-minus, shifts, home/away, opponent — so a future
dashboard view doesn't require going back and re-fetching history.

**`teamdata.json`** holds one array of `[date, goals_against, shutout]` triples per NHL
team abbreviation. Goals against is schedule-level (the opponent's final score, including
empty-net and shootout-winning goals) — fast and verified exactly against league standings,
but *not* the same rule the 2025-26 season actually used (which excluded empty-net goals).
The archive's dashboard corrects for this: see "Known quirks" below.

Both dashboards' JS fetches `rosters.json` plus the two data files and merges them into the
`{season, asOf, players, teams}` shape that `dashboard-calc.js` expects. That file is pure
data-crunching with no DOM access, shared by both dashboards, and testable directly in Node.

## Running the fetch script

```fish
python3 scripts/fetch_stats.py --out-dir data/2026-2027
python3 scripts/fetch_stats.py --season 20252026 --out-dir data/2026-2027 --prefix sample-
```

Standard library only, no dependencies. `--season` defaults to the current season
(2026-27). It refuses to overwrite a file with fewer games than it already has for any
player or team (a defense against a partial/failed fetch silently erasing history), and
writes atomically (temp file + rename) so a crash mid-run can't corrupt the output.

## Nightly pipeline

`.github/workflows/nightly-stats.yml` runs the fetch script every night (`0 9 * * *` UTC —
late enough that West Coast games are long finished) and commits `data/2026-2027/
playerdata.json`/`teamdata.json` only if something actually changed. It also supports a
manual "Run workflow" trigger from the Actions tab, or `gh workflow run nightly-stats.yml`.
Runs on `ubuntu-26.04` (pinned explicitly, ahead of the `ubuntu-latest` migration, so a
future runner-image bump doesn't happen mid-season without anyone deciding it).

## Testing locally

Pages fetch JSON with `fetch()`, which doesn't work against a `file://` URL — serve the
directory instead:

```fish
python3 -m http.server 8000
```

## Known quirks worth knowing before touching this

- **NHL API is unofficial.** `api-web.nhle.com` has no SLA, no versioning guarantee, and
  its predecessor (`statsapi.web.nhle.com`) was killed without notice in 2023. Keep the
  fetch logic in one place (`scripts/fetch_stats.py`), fail loudly rather than silently,
  and don't hammer it — one polite request at a time is enough for a 6-person league.
- **A team roster mismatch is real, not a glitch.** Verify a player's current team by
  lookup every time rather than assuming an API discrepancy is a data error — players get
  traded in the offseason (this bit us with Brady Tkachuk, who'd moved OTT → FLA).
- **The 2025-26 archive's Team-pick GA is a hybrid.** The per-game numbers behind its
  chart come from the same schedule-level method the 2026-27 season uses (fast, but
  includes empty-net goals). The *season totals* shown in the standings table and on the
  lineup card come instead from that season's own tracking spreadsheet, which excluded
  empty-net goals per that year's rule. `dashboard-2025.html` reconciles the two: it shifts
  each team's cumulative chart line by a constant so the final total is exact, while the
  day-to-day shape is an approximation. This is disclosed in that page's own footer.
- **Whether 2026-27 should also exclude empty-net goals is an open, pending decision.**
  Doing it for real needs per-game play-by-play data (NHL API doesn't expose it at the
  schedule level), which means rewriting `team_log()` in `fetch_stats.py` to make roughly
  one API call per completed game per Team pick (~500/season) instead of one call per team
  for the whole season. Scoped, not started.
- **Git is the site owner's, not an assistant's, to drive.** Nothing here should ever be
  committed, pushed, or merged by an automated assistant without the repo owner running
  those commands themselves.
