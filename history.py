"""Persistencia local de leituras + agregacoes (hora/dia) para dashboards.
SQLite stdlib, sem dependencias. Raw 60 dias; hourly/daily para sempre (anual ok).
"""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).parent / "history.db"
RAW_KEEP_DAYS = 60

def _connect():
    con = sqlite3.connect(DB, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=30000")
    except Exception:
        pass
    return con

def init_db():
    con = _connect()
    con.execute("""CREATE TABLE IF NOT EXISTS readings (
        ts INTEGER NOT NULL,
        device_id TEXT NOT NULL,
        name TEXT,
        watts REAL,
        volts REAL,
        amps REAL,
        on_off INTEGER
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ts ON readings(ts)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_dev ON readings(device_id, ts)")
    try:
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dev_ts ON readings(device_id, ts)")
    except Exception:
        con.execute("DELETE FROM readings WHERE rowid NOT IN"
                    " (SELECT MAX(rowid) FROM readings GROUP BY device_id, ts)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dev_ts ON readings(device_id, ts)")
    for tbl in ("hourly", "daily"):
        con.execute(f"""CREATE TABLE IF NOT EXISTS {tbl} (
            bucket INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            name TEXT,
            kwh REAL,
            avg_w REAL,
            samples INTEGER,
            PRIMARY KEY (bucket, device_id)
        )""")
    con.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    con.commit()
    con.close()

def log_many(rows):
    """rows: lista de dicts {device_id,name,watts,volts,amps,on}"""
    if not rows:
        return
    init_db()
    ts = int(time.time())
    con = _connect()
    con.executemany(
        "INSERT OR IGNORE INTO readings (ts, device_id, name, watts, volts, amps, on_off) VALUES (?,?,?,?,?,?,?)",
        [(ts, r.get("id"), r.get("name"),
          r.get("watts"), r.get("volts"), r.get("amps"),
          (1 if r.get("on") else 0) if r.get("on") is not None else None)
         for r in rows if r.get("online")],
    )
    con.commit()
    con.close()
    # Rollup incremental de tempos em tempos (barato: janela de 3h)
    try:
        last = float((_connect().execute(
            "SELECT v FROM meta WHERE k='rollup'").fetchone() or [0])[0])
    except Exception:
        last = 0
    if ts - last > 600:
        try:
            rollup(full=False)
        except Exception as e:
            print(f"rollup: {e}")

def _integrate(pairs):
    """pairs: [(ts, watts)] ordenados -> (kwh, avg_w)."""
    energy_wh, w_sum, n = 0.0, 0.0, 0
    for (ta, wa), (tb, _wb) in zip(pairs, pairs[1:]):
        dt_h = max(0, min(tb - ta, 3600)) / 3600.0
        energy_wh += (wa or 0) * dt_h
        w_sum += wa or 0
        n += 1
    return energy_wh / 1000.0, (w_sum / n if n else 0.0)

def rollup(full=False):
    """Agrega readings -> hourly/daily e poda raw antigo. Idempotente."""
    init_db()
    now = int(time.time())
    con = _connect()
    if full:
        lo = 0
    else:
        lo = now - 3 * 3600 - 3600  # janela + 1h de sobreposicao p/ borda
    rows = con.execute(
        "SELECT device_id, name, ts, watts FROM readings WHERE ts>=? ORDER BY device_id, ts",
        (lo,)).fetchall()
    by_dev = {}
    for dev, name, ts, w in rows:
        by_dev.setdefault(dev, {"name": name, "pts": []})["pts"].append((ts, w or 0, name))
    for dev, info in by_dev.items():
        buckets = {}
        for ts, w, _ in info["pts"]:
            buckets.setdefault(ts // 3600 * 3600, []).append((ts, w))
        for b, pts in buckets.items():
            pts.sort()
            # ponto anterior p/ integrar do inicio do bucket
            prev = con.execute(
                "SELECT ts, watts FROM readings WHERE device_id=? AND ts<? ORDER BY ts DESC LIMIT 1",
                (dev, b)).fetchone()
            seq = ([(prev[0], prev[1] or 0)] if prev else []) + pts
            kwh, avg = _integrate(seq) if len(seq) > 1 else (0.0, pts[0][1])
            nm = next((n for _t, _w, n in info["pts"] if n), info["name"])
            con.execute(
                "INSERT OR REPLACE INTO hourly (bucket, device_id, name, kwh, avg_w, samples)"
                " VALUES (?,?,?,?,?,?)", (b, dev, nm, round(kwh, 4), round(avg, 1), len(pts)))
    con.commit()
    # daily a partir do hourly (ultimos 3 dias no incremental; tudo no full)
    dlo = 0 if full else (now - 3 * 86400) // 86400 * 86400
    days = con.execute(
        "SELECT bucket, device_id, name, kwh, avg_w, samples FROM hourly WHERE bucket>=?",
        (dlo,)).fetchall()
    by_day = {}
    for b, dev, name, kwh, avg, n in days:
        key = (b // 86400 * 86400, dev)
        by_day.setdefault(key, {"name": name, "kwh": 0.0, "wsum": 0.0, "n": 0})
        by_day[key]["kwh"] += kwh or 0
        by_day[key]["wsum"] += (avg or 0) * (n or 0)
        by_day[key]["n"] += n or 0
    for (day, dev), v in by_day.items():
        con.execute(
            "INSERT OR REPLACE INTO daily (bucket, device_id, name, kwh, avg_w, samples)"
            " VALUES (?,?,?,?,?,?)",
            (day, dev, v["name"], round(v["kwh"], 4),
             round(v["wsum"] / v["n"], 1) if v["n"] else 0, v["n"]))
    con.commit()
    con.execute("DELETE FROM readings WHERE ts < ?", (now - RAW_KEEP_DAYS * 86400,))
    con.commit()
    con.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('rollup', ?)", (str(now),))
    con.commit()
    con.close()

def import_cloud_logs(device_id, name, logs):
    """Converte logs da nuvem [{code,event_time(ms),value}] em leituras.
    Agrupa por timestamp: cur_power/10=W, cur_voltage/10=V, cur_current/1000=A.
    Retorna nº de leituras novas."""
    init_db()
    by_ts = {}
    for l in logs or []:
        try:
            ts = int(l.get("event_time", 0) // 60000) * 60  # balde de 1 min (relatorios do mesmo minuto se juntam)
        except (TypeError, ValueError):
            continue
        if ts <= 0:
            continue
        try:
            v = float(l.get("value", l.get("event_value", 0)))
        except (TypeError, ValueError):
            continue
        code = l.get("code", "")
        row = by_ts.setdefault(ts, {"w": None, "v": None, "a": None})
        if code == "cur_power":
            row["w"] = v / 10.0
        elif code == "cur_voltage":
            row["v"] = v / 10.0
        elif code == "cur_current":
            row["a"] = v / 1000.0
    rows = [(ts, device_id, name, r["w"], r["v"], r["a"], None)
            for ts, r in by_ts.items() if r["w"] is not None]
    if not rows:
        return 0
    con = _connect()
    before = con.total_changes
    con.executemany(
        "INSERT OR IGNORE INTO readings (ts, device_id, name, watts, volts, amps, on_off)"
        " VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    added = con.total_changes - before
    con.close()
    return added
    import datetime
    dt = datetime.datetime.fromtimestamp(bucket)
    if gran == "hour":
        return dt.strftime("%H:00")
    if gran == "day":
        return dt.strftime("%d/%m")
    if gran == "month":
        return dt.strftime("%b/%y").lower()
    return dt.strftime("%H:%M")

def _fmt_label(bucket, gran):
    import datetime
    dt = datetime.datetime.fromtimestamp(bucket)
    if gran == "hour":
        return dt.strftime("%H:00")
    if gran == "day":
        return dt.strftime("%d/%m")
    if gran == "month":
        return dt.strftime("%b/%y").lower()
    return dt.strftime("%H:%M")

def get_series(range_key="24h", device_id=None):
    """Series agregadas p/ graficos.
    2h -> minuto a minuto (W cru por device); 24h -> kWh por hora;
    7d/30d -> kWh por dia; 12m -> kWh por mes.
    Retorna {gran, buckets:[{t,label,total}], by_device:{id:{name,total,series:[...]}}, total_kwh}.
    """
    init_db()
    now = int(time.time())
    con = _connect()
    con.row_factory = sqlite3.Row
    devf = "" if (not device_id or device_id == "all") else "AND device_id='%s'" % device_id.replace("'", "")
    if range_key == "2h":
        since = now - 2 * 3600
        rows = con.execute(
            f"SELECT ts, device_id, name, watts FROM readings WHERE ts>=? {devf} ORDER BY ts",
            (since,)).fetchall()
        if len(rows) > 480:
            rows = rows[::len(rows) // 480]
        by_dev = {}
        for r in rows:
            d = by_dev.setdefault(r["device_id"], {"name": r["name"], "series": [], "total": 0})
            d["series"].append({"t": r["ts"], "w": r["watts"] or 0})
        con.close()
        return {"gran": "min", "buckets": [], "by_device": by_dev, "total_kwh": None}

    import datetime
    if range_key == "24h":
        gran, size, n, tbl = "hour", 3600, 24, "hourly"
    elif range_key in ("7d", "30d"):
        gran, size, n, tbl = "day", 86400, 7 if range_key == "7d" else 30, "daily"
    elif range_key == "12m":
        gran, size, n, tbl = "month", 0, 12, "daily"
    else:
        con.close()
        return {"gran": "day", "buckets": [], "by_device": {}, "total_kwh": 0}

    if gran == "month":
        months = []
        y, m = datetime.datetime.now().year, datetime.datetime.now().month
        for _ in range(n):
            months.append((y, m))
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        months.reverse()
        bounds = []
        for y, m in months:
            lo = int(datetime.datetime(y, m, 1).timestamp())
            hi = int(datetime.datetime(y + (m == 12), m % 12 + 1, 1).timestamp())
            bounds.append((lo, hi, lo))
        rows = con.execute(
            f"SELECT device_id, name, bucket, kwh FROM daily WHERE 1=1 {devf}").fetchall()
        by_dev = {}
        for r in rows:
            by_dev.setdefault(r["device_id"], {"name": r["name"], "buckets": {}})["buckets"][r["bucket"]] = r["kwh"] or 0
        buckets, dev_series = [], {}
        for lo, hi, t in bounds:
            tot = 0.0
            for did, dd in by_dev.items():
                v = sum(v for b, v in dd["buckets"].items() if lo <= b < hi)
                s = dev_series.setdefault(did, {"name": dd["name"], "series": [], "total": 0.0})
                s["series"].append(round(v, 3))
                s["total"] = round(s["total"] + v, 3)
                tot += v
            buckets.append({"t": t, "label": _fmt_label(t, "month"), "total": round(tot, 3)})
        con.close()
        return {"gran": gran, "buckets": buckets, "by_device": dev_series,
                "total_kwh": round(sum(b["total"] for b in buckets), 3)}

    since = now // size * size - (n - 1) * size
    rows = con.execute(
        f"SELECT bucket, device_id, name, COALESCE(SUM(kwh),0) k, COALESCE(AVG(avg_w),0) a"
        f" FROM {tbl} WHERE bucket>=? {devf} GROUP BY bucket, device_id ORDER BY bucket",
        (since,)).fetchall()
    con.close()
    labels = [since + i * size for i in range(n)]
    by_dev = {}
    for r in rows:
        by_dev.setdefault(r["device_id"], {"name": r["name"], "map": {}})["map"][r["bucket"]] = r["k"] or 0
    dev_series = {}
    for did, dd in by_dev.items():
        series = [round(dd["map"].get(b, 0), 3) for b in labels]
        dev_series[did] = {"name": dd["name"], "series": series, "total": round(sum(series), 3)}
    buckets = [{"t": b, "label": _fmt_label(b, gran),
                "total": round(sum(dd["map"].get(b, 0) for dd in by_dev.values()), 3)}
               for b in labels]
    return {"gran": gran, "buckets": buckets, "by_device": dev_series,
            "total_kwh": round(sum(b["total"] for b in buckets), 3)}

def get_history(device_id=None, hours=24, max_points=500):
    init_db()
    since = int(time.time()) - int(hours * 3600)
    con = _connect()
    con.row_factory = sqlite3.Row
    if device_id and device_id != "all":
        rows = con.execute(
            "SELECT * FROM readings WHERE device_id=? AND ts>=? ORDER BY ts",
            (device_id, since)).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM readings WHERE ts>=? ORDER BY ts", (since,)).fetchall()
    con.close()
    if len(rows) > max_points:
        step = len(rows) // max_points
        rows = rows[::step]
    return [dict(r) for r in rows]

def get_stats(hours=24):
    """Retorna por device: kWh estimado (integracao W ao longo do tempo), media W, tempo ligada."""
    hist = get_history(hours=hours, max_points=100000)
    by_dev = {}
    for r in hist:
        by_dev.setdefault(r["device_id"], {"name": r["name"], "pts": []})["pts"].append(r)
    out = []
    for dev_id, info in by_dev.items():
        pts = sorted(info["pts"], key=lambda x: x["ts"])
        energy_wh = 0.0
        w_sum, w_n, on_secs = 0.0, 0, 0
        for a, b in zip(pts, pts[1:]):
            dt_h = max(0, min((b["ts"] - a["ts"]), 3600)) / 3600.0
            w = a["watts"] or 0
            energy_wh += w * dt_h
            w_sum += w
            w_n += 1
            if a["on_off"]:
                on_secs += (b["ts"] - a["ts"])
        out.append({
            "id": dev_id, "name": info["name"],
            "kwh": round(energy_wh / 1000, 3),
            "avg_w": round(w_sum / w_n, 1) if w_n else 0,
            "points": len(pts),
        })
    total = round(sum(x["kwh"] for x in out), 3)
    return {"devices": out, "total_kwh": total, "hours": hours}
