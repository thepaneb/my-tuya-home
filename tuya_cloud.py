"""Camada nuvem Tuya (IoT Core) — remota, com cotas. Complementa o modo local."""
import json
from functools import lru_cache
from pathlib import Path

BASE = Path(__file__).parent

try:
    import tinytuya
    HAS_TUYA = True
except ImportError:
    HAS_TUYA = False

_cloud = None
_cloud_error = None


def is_configured() -> bool:
    if not HAS_TUYA:
        return False
    # tinytuya.json (gerado pelo wizard) ou cloud.json manual
    return (BASE / "tinytuya.json").exists() or (BASE / "cloud.json").exists()


def get_cloud():
    global _cloud, _cloud_error
    if _cloud is not None:
        return _cloud
    if not is_configured():
        raise RuntimeError("Nuvem nao configurada (rode: python -m tinytuya wizard)")
    try:
        cfg_path = str(BASE / "cloud.json") if (BASE / "cloud.json").exists() else None
        _cloud = tinytuya.Cloud(configFile=cfg_path) if cfg_path else tinytuya.Cloud()
        return _cloud
    except Exception as e:
        _cloud_error = str(e)
        raise


def parse_cloud_status(result_list: list) -> dict:
    """Converte [{code, value}] da nuvem para o mesmo formato do local."""
    m = {x.get("code"): x.get("value") for x in (result_list or []) if isinstance(x, dict)}
    on = m.get("switch_1", m.get("switch"))
    w_raw = m.get("cur_power")
    a_raw = m.get("cur_current")
    v_raw = m.get("cur_voltage")
    e_raw = m.get("add_ele")
    return {
        "on": bool(on) if on is not None else None,
        "watts": (w_raw / 10.0) if isinstance(w_raw, (int, float)) else None,
        "amps": (a_raw / 1000.0) if isinstance(a_raw, (int, float)) else None,
        "volts": (v_raw / 10.0) if isinstance(v_raw, (int, float)) else None,
        "energy_kwh": round(e_raw / 100.0, 3) if isinstance(e_raw, (int, float)) else None,
        "countdown": m.get("countdown_1"),
        "fault": m.get("fault", 0),
        "relay_status": m.get("relay_status"),
        "light_mode": m.get("light_mode"),
        "child_lock": m.get("child_lock"),
        "overcharge": m.get("overcharge_switch"),
        "codes": m,
    }


ALLOWED_CMDS = {"switch_1", "switch", "countdown_1", "relay_status",
                "light_mode", "child_lock", "overcharge_switch"}


def cloud_send(device_id: str, commands: dict) -> dict:
    """Envia comandos de configuração (countdown, proteções, etc.)."""
    cmds = {k: v for k, v in (commands or {}).items() if k in ALLOWED_CMDS}
    if not cmds:
        return {"ok": False, "error": "nenhum comando valido"}
    if "countdown_1" in cmds:
        try:
            cmds["countdown_1"] = max(0, min(86400, int(cmds["countdown_1"])))
        except (TypeError, ValueError):
            return {"ok": False, "error": "countdown invalido (0-86400s)"}
    c = get_cloud()
    try:
        r = c.sendcommand(device_id, {"commands": [{"code": k, "value": v} for k, v in cmds.items()]})
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "source": "cloud"}
    if isinstance(r, dict) and r.get("success"):
        return {"ok": True, "source": "cloud"}
    err = (r.get("msg") if isinstance(r, dict) else str(r)) or "falha no comando"
    return {"ok": False, "error": str(err)[:300], "source": "cloud"}


def cloud_detail(device_id: str, log_limit: int = 15) -> dict:
    """Tudo da nuvem num pacote: status + funções + últimos logs."""
    c = get_cloud()
    status = cloud_status(device_id)
    try:
        fn = c.getfunctions(device_id)
        functions = fn.get("result", {}).get("functions", []) if isinstance(fn, dict) else []
    except Exception as e:
        functions = [{"error": str(e)[:200]}]
    try:
        lg = c.getdevicelog(device_id)
        logs = (lg.get("result", {}).get("logs", []) if isinstance(lg, dict) else [])[:log_limit]
    except Exception as e:
        logs = [{"error": str(e)[:200]}]
    return {"id": device_id, "source": "cloud", "status": status,
            "functions": functions, "logs": logs}


def cloud_status(device_id: str) -> dict:
    c = get_cloud()
    r = c.getstatus(device_id)
    if isinstance(r, dict) and r.get("success") and isinstance(r.get("result"), list):
        p = parse_cloud_status(r["result"])
        return {"online": True, "source": "cloud", **p, "error": None}
    err = (r.get("msg") if isinstance(r, dict) else str(r)) or "erro nuvem"
    return {"online": False, "source": "cloud", "on": None, "watts": None,
            "amps": None, "volts": None, "energy_kwh": None, "error": str(err)[:200]}


def cloud_set(device_id: str, turn_on: bool) -> dict:
    c = get_cloud()
    # switch_1 é o code padrão das tomadas; fallback para switch
    for code in ("switch_1", "switch"):
        try:
            r = c.sendcommand(device_id, {"commands": [{"code": code, "value": turn_on}]})
            if isinstance(r, dict) and r.get("success"):
                return {"ok": True, "on": turn_on, "source": "cloud"}
        except Exception:
            continue
    return {"ok": False, "error": "falha ao enviar comando na nuvem", "source": "cloud"}


def cloud_info(device_id: str) -> dict:
    """Info + functions + properties (recursos exclusivos da nuvem)."""
    c = get_cloud()
    out = {}
    for fn, arg in (("getfunctions", device_id), ("getproperties", device_id),
                    ("getdps", device_id)):
        try:
            out[fn] = getattr(c, fn)(arg)
        except Exception as e:
            out[fn] = {"error": str(e)[:200]}
    return out


def cloud_logs(device_id: str, limit: int = 20) -> dict:
    c = get_cloud()
    try:
        return c.getdevicelog(device_id)
    except Exception as e:
        return {"error": str(e)[:200]}


def fetch_logs_range(device_id: str, days: int = 7, max_pages: int = 45) -> dict:
    """Puxa logs de DP da nuvem com paginacao manual (tinytuya nao pagina sozinho).
    ~18 relatorios/hora; 7 dias ~= 3000 logs ~= 30 chamadas. Retorna {logs, pages, oldest_ts}."""
    import time as _time
    c = get_cloud()
    all_logs, rk, pages = [], None, 0
    cutoff = int(_time.time() * 1000) - days * 86400 * 1000
    for _ in range(max_pages):
        try:
            r = c.getdevicelog(device_id, start=-days, evtype=7, size=100,
                               max_fetches=1, start_row_key=rk)
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "logs": all_logs, "pages": pages}
        res = (r.get("result", {}) if isinstance(r, dict) else {}) or {}
        logs = res.get("logs", [])
        if not logs:
            break
        all_logs.extend(logs)
        pages += 1
        if logs[-1].get("event_time", 0) < cutoff:
            break
        if not res.get("has_next") or not res.get("next_row_key"):
            break
        rk = res["next_row_key"]
    oldest = min((l.get("event_time", 0) for l in all_logs), default=0)
    return {"ok": True, "logs": all_logs, "pages": pages,
            "oldest_ts": oldest // 1000 if oldest else None}


def backfill_device(device_id: str, name: str, days: int = 7) -> dict:
    """Importa N dias da nuvem p/ o history local + roda rollup. Retorna resumo."""
    import history as _h
    f = fetch_logs_range(device_id, days=days)
    if not f.get("ok"):
        return f
    added = _h.import_cloud_logs(device_id, name, f["logs"])
    try:
        _h.rollup(full=False)
    except Exception as e:
        return {"ok": True, "added": added, "pages": f["pages"],
                "oldest_ts": f.get("oldest_ts"), "rollup_error": str(e)[:200]}
    return {"ok": True, "added": added, "pages": f["pages"], "oldest_ts": f.get("oldest_ts")}
