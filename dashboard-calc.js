/* Pure scoring math for the dashboard. No DOM access, so it can be tested in node. */
(function (root) {
  function fp(g, a) { return 2 * g + a; }

  function daysBefore(iso, n) {
    const d = new Date(iso + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() - n);
    return d.toISOString().slice(0, 10);
  }

  // rosters: data/rosters.json, stats: data/stats.json (players: id -> [[date,g,a]], teams: abbr -> [[date,ga,so]])
  function buildModel(rosters, stats) {
    const dateSet = new Set();
    const players = [];

    const teams = rosters.teams.map(function (t) {
      const daily = {}; // date -> { pts, skPts, skGP }
      function day(d) { dateSet.add(d); return daily[d] || (daily[d] = { pts: 0, skPts: 0, skGP: 0 }); }
      const m = { id: t.id, name: t.name, f: 0, d: 0, t: 0, ga: 0, so: 0, filled: 0, skGP: 0, skFp: 0 };

      ['F', 'D'].forEach(function (pos) {
        t.roster[pos].forEach(function (p) {
          if (!p) return;
          m.filled++;
          const rows = (stats.players && stats.players[String(p.playerId)]) || [];
          const pl = { name: p.name, pos: pos, owner: t.id, ownerName: t.name, fp: 0, gp: 0, g: 0, a: 0, rows: [] };
          rows.forEach(function (r) {
            const pts = fp(r[1], r[2]);
            const x = day(r[0]);
            x.pts += pts; x.skPts += pts; x.skGP += 1;
            pl.fp += pts; pl.gp += 1; pl.g += r[1]; pl.a += r[2];
            pl.rows.push([r[0], pts, r[1], r[2]]);
          });
          m[pos.toLowerCase()] += pl.fp;
          m.skFp += pl.fp; m.skGP += pl.gp;
          players.push(pl);
        });
      });

      t.roster.T.forEach(function (p) {
        if (!p) return;
        m.filled++;
        ((stats.teams && stats.teams[p.teamAbbrev]) || []).forEach(function (r) {
          const pts = -r[1] + 10 * r[2];
          day(r[0]).pts += pts;
          m.t += pts; m.ga += r[1]; m.so += r[2];
        });
      });

      m.daily = daily;
      m.total = m.f + m.d + m.t;
      return m;
    });

    const dates = Array.from(dateSet).sort();
    teams.forEach(function (m) {
      const total = [], perGame = [], perNight = [];
      let cum = 0, cumSk = 0, cumGP = 0;
      dates.forEach(function (d, i) {
        const x = m.daily[d];
        if (x) { cum += x.pts; cumSk += x.skPts; cumGP += x.skGP; }
        total.push(cum);
        perGame.push(cumGP ? cumSk / cumGP : null);
        perNight.push(cum / (i + 1));
      });
      m.series = { total: total, perGame: perGame, perNight: perNight };
      m.perGame = m.skGP ? m.skFp / m.skGP : 0;
      m.perNight = dates.length ? m.total / dates.length : 0;
      delete m.daily;
    });

    const asOf = dates.length ? dates[dates.length - 1] : null;

    function hotCold(days, n) {
      if (!asOf) return { hot: [], cold: [] };
      const cutoff = daysBefore(asOf, days - 1);
      const win = players.map(function (p) {
        let pts = 0, gp = 0, g = 0, a = 0;
        p.rows.forEach(function (r) {
          if (r[0] >= cutoff) { pts += r[1]; gp++; g += r[2]; a += r[3]; }
        });
        return { name: p.name, pos: p.pos, ownerName: p.ownerName, owner: p.owner, fp: pts, gp: gp, g: g, a: a };
      }).filter(function (p) { return p.gp > 0; });
      win.sort(function (x, y) { return y.fp - x.fp || x.name.localeCompare(y.name); });
      return { hot: win.slice(0, n), cold: win.slice(-n).reverse() };
    }

    return { asOf: asOf, dates: dates, teams: teams, players: players, hotCold: hotCold };
  }

  const api = { buildModel: buildModel, fp: fp };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.DashCalc = api;
})(typeof self !== 'undefined' ? self : this);
