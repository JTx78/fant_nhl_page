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
- The Team pick scores **−1 × real goals against + 10 × shutouts** for that NHL team.
  "Real" excludes empty-net goals — those are shown as a separate, non-scoring EN count.
  A goal still counts fully for the *skater* who scored it, empty-net or not.
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

**`teamdata.json`** holds one array of per-game records per NHL team abbreviation:
`{id, date, ga, en, so}`. `id` is the NHL game ID (also the incremental-fetch cursor —
see below); `ga` is real goals against, already excluding empty-net goals; `en` is the raw
empty-net-goal count for that game (shown on the site, never scored); `so` is 1 if `ga`
was 0. The 2025-26 archive still uses the older `[date, ga, so]` triple, computed by the
schedule-level (pre-empty-net-exclusion) method — see "Known quirks" below for how that's
reconciled.

Both dashboards' JS fetches `rosters.json` plus the two data files and merges them into the
`{season, asOf, players, teams}` shape that `dashboard-calc.js` expects. That file is pure
data-crunching with no DOM access, shared by both dashboards, and testable directly in Node.

## Running the fetch script

```fish
python3 scripts/fetch_stats.py --out-dir data/2026-2027
python3 scripts/fetch_stats.py --season 20252026 --out-dir data/2026-2027 --prefix sample-
python3 scripts/fetch_stats.py --out-dir data/2026-2027 --rebuild   # force a full refetch
```

Standard library only, no dependencies. `--season` defaults to the current season
(2026-27). Team data is fetched incrementally: each completed game's play-by-play is only
requested once, ever — a normal run only fetches whatever's finished since the last one,
by comparing against the game IDs already in the existing `teamdata.json`. `--rebuild`
ignores what's on disk and refetches every game from scratch (use it if a past game's data
ever needs correcting; the NHL amending a "FINAL" boxscore after the fact is rare, but a
previously-recorded game is never automatically re-verified otherwise). Skaters (via the
game-log endpoint) are always a full refetch — one API call returns a player's whole
season regardless, so there's no per-game cost to save, and it means a stat correction is
picked up automatically. The script also refuses to overwrite a file with fewer games than
it already has for any player or team (a defense against a partial/failed fetch silently
erasing history), and writes atomically (temp file + rename) so a crash mid-run can't
corrupt the output.

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
- **2026-27's empty-net exclusion needed real per-game data**, since the NHL doesn't expose
  it at the schedule level. Each game's `/gamecenter/{id}/landing` response tags every goal
  with `goalModifier: "empty-net"` or `"none"` — including shootout-winning goals, which
  appear in the same list under a `periodType: "SO"` entry and are never empty-net, so no
  special-casing was needed there. `team_log()` fetches this per completed game, cached
  across teams that happen to share a game, and merges incrementally (see above) rather
  than re-fetching a full season every run.
- **Git is the site owner's, not an assistant's, to drive.** Nothing here should ever be
  committed, pushed, or merged by an automated assistant without the repo owner running
  those commands themselves.
