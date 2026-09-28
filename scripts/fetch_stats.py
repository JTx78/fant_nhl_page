#!/usr/bin/env python3
"""Fetch per-game stats for every rostered player and Team pick.

Writes two files per season into --out-dir (e.g. data/2026-2027/): playerdata.json and
teamdata.json (or sample-playerdata.json / sample-teamdata.json with --prefix sample-).
Reads rosters.json from --out-dir by default (--rosters to override).

Skaters: one record per regular-season game (goals, assists, shots, PIM, TOI, power-play/
shorthanded/game-winning/OT goals, plus/minus, shifts, home/away, opponent) -- kept broad
so a future dashboard view doesn't need a backfill.

Teams: [date, goals_against, shutout] per regular-season game (GA = opponent's final
score, matching league standings; shutout = opponent scored 0). Team GA is schedule-level
and does not exclude empty-net goals -- that would need per-game play-by-play, a separate
and not-yet-built change to team_log(), not a schema question.

Any failed request aborts the run without touching either output file.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api-web.nhle.com/v1"
UA = "fant-nhl-page/1.0 (personal fantasy league tracker)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DONE_STATES = ("FINAL", "OFF")


def get(path):
    """GET JSON with retries. Returns None on 404 (e.g. no games yet), raises otherwise."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(API + path, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(0.15)
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except (urllib.error.URLError, TimeoutError) as e:
            err = e
        time.sleep(2 ** attempt)
    raise RuntimeError("GET %s failed: %s" % (path, err))


def roster_targets(rosters):
    players, teams = [], []
    for t in rosters["teams"]:
        for pos in ("F", "D"):
            players += [p["playerId"] for p in t["roster"][pos] if p]
        teams += [p["teamAbbrev"] for p in t["roster"]["T"] if p]
    return sorted(set(players)), sorted(set(teams))


def player_log(pid, season):
    j = get("/player/%d/game-log/%d/2" % (pid, season))
    rows = [{
        "date": g["gameDate"],
        "g": g["goals"],
        "a": g["assists"],
        "shots": g.get("shots", 0),
        "pim": g.get("pim", 0),
        "toi": g.get("toi"),
        "ppg": g.get("powerPlayGoals", 0),
        "ppp": g.get("powerPlayPoints", 0),
        "shg": g.get("shorthandedGoals", 0),
        "shp": g.get("shorthandedPoints", 0),
        "gwg": g.get("gameWinningGoals", 0),
        "otg": g.get("otGoals", 0),
        "pm": g.get("plusMinus", 0),
        "shifts": g.get("shifts", 0),
        "home": g.get("homeRoadFlag") == "H",
        "opp": g.get("opponentAbbrev"),
    } for g in (j or {}).get("gameLog", [])]
    return sorted(rows, key=lambda r: r["date"])


def team_log(abbr, season):
    j = get("/club-schedule-season/%s/%d" % (abbr, season))
    rows = []
    for g in (j or {}).get("games", []):
        if g["gameType"] != 2 or g["gameState"] not in DONE_STATES:
            continue
        opp = g["awayTeam"] if g["homeTeam"]["abbrev"] == abbr else g["homeTeam"]
        rows.append([g["gameDate"], opp["score"], 1 if opp["score"] == 0 else 0])
    return sorted(rows)


def write_json(path, obj, old_rows_by_key=None):
    """Write obj (a {"...": ..., <key>: {id: [rows]}} dict) atomically. If old_rows_by_key
    is given, refuse to write when any id's row count shrank versus the prior file."""
    if old_rows_by_key and os.path.exists(path):
        with open(path) as f:
            old = json.load(f)
        key = old_rows_by_key
        for k, rows in obj.get(key, {}).items():
            if len(rows) < len(old.get(key, {}).get(k, [])):
                sys.exit("refusing to write %s: %s %s shrank (%d -> %d rows)"
                         % (path, key, k, len(old[key][k]), len(rows)))
    text = json.dumps(obj, separators=(",", ":"), sort_keys=True) + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=20262027)
    ap.add_argument("--out-dir", required=True,
                     help="season directory to write into, e.g. data/2026-2027")
    ap.add_argument("--prefix", default="",
                     help="filename prefix, e.g. 'sample-' for sample-playerdata.json / sample-teamdata.json")
    ap.add_argument("--rosters", help="defaults to <out-dir>/rosters.json")
    args = ap.parse_args()
    rosters_path = args.rosters or os.path.join(args.out_dir, "rosters.json")

    with open(rosters_path) as f:
        rosters = json.load(f)
    pids, abbrs = roster_targets(rosters)

    players = {str(p): player_log(p, args.season) for p in pids}
    teams = {a: team_log(a, args.season) for a in abbrs}

    dates = [r["date"] for rows in players.values() for r in rows]
    dates += [r[0] for rows in teams.values() for r in rows]
    as_of = max(dates) if dates else None

    player_path = os.path.join(args.out_dir, args.prefix + "playerdata.json")
    team_path = os.path.join(args.out_dir, args.prefix + "teamdata.json")
    write_json(player_path, {"season": args.season, "asOf": as_of, "players": players}, old_rows_by_key="players")
    write_json(team_path, {"season": args.season, "asOf": as_of, "teams": teams}, old_rows_by_key="teams")
    print("season %d: %d players -> %s, %d teams -> %s, asOf %s"
          % (args.season, len(players), player_path, len(teams), team_path, as_of))


if __name__ == "__main__":
    main()
