"""Toda configuracao antes feita por comando, agora via app.
Cobre: credenciais nuvem, buscar devices na nuvem, scan LAN, editar devices.json + hierarquia, testar.
Usado pela tela Config do Flet e pela pagina /setup do Flask.
"""
import json
import threading
from pathlib import Path

BASE = Path(__file__).parent
DEVICES_FILE = BASE / "devices.json"

try:
    import tinytuya
    HAS_TUYA = True
except ImportError:
    HAS_TUYA = False

_scan_state = {"running": False, "result": None, "error": None}


def setup_status():
    import app as core
    import tuya_cloud
    return {
        "tinytuya": HAS_TUYA,
        "devices_file": DEVICES_FILE.exists(),
        "devices_count": len(core.load_devices()),
        "cloud_configured": tuya_cloud.is_configured(),
        "history_db": (BASE / "history.db").exists(),
    }


def save_cloud_config(apiKey, apiSecret, region="us", apiDeviceID=""):
    """Salva cloud.json (preferido pelo app) sem expor segredo no log."""
    apiKey, apiSecret = (apiKey or "").strip(), (apiSecret or "").strip()
    if not apiKey or not apiSecret:
        return {"ok": False, "error": "Preencha Access ID e Access Secret"}
    cfg = {"apiKey": apiKey, "apiSecret": apiSecret, "apiRegion": region or "us"}
    if apiDeviceID.strip():
        cfg["apiDeviceID"] = apiDeviceID.strip()
    (BASE / "cloud.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    # invalida singleton da nuvem
    import tuya_cloud
    tuya_cloud._cloud = None
    return {"ok": True}


def cloud_fetch_devices():
    """Busca devices na nuvem (equivale ao wizard) e retorna lista importavel."""
    import tuya_cloud
    c = tuya_cloud.get_cloud()
    raw = c.getdevices(verbose=True)
    if isinstance(raw, dict) and "result" in raw and isinstance(raw["result"], list):
        items = raw["result"]
    elif isinstance(raw, dict):
        # dict id -> device (modo nao-verbose)
        items = list(raw.values()) if all(isinstance(v, dict) for v in raw.values()) else []
        if not items:
            return {"ok": False, "error": str(raw)[:300]}
    else:
        return {"ok": False, "error": str(raw)[:300]}
    out = []
    for d in items:
        if not isinstance(d, dict):
            continue
        out.append({
            "id": d.get("id"),
            "name": d.get("name") or d.get("id", "")[-6:],
            "key": d.get("key") or d.get("local_key", ""),
            "ip": "",
            "category": d.get("category", ""),
            "product_name": d.get("product_name", ""),
            "product_id": d.get("product_id", ""),
        })
    return {"ok": True, "devices": [x for x in out if x["id"]]}


def scan_start(timeout=20):
    if _scan_state["running"]:
        return {"ok": False, "error": "scan ja em andamento"}
    _scan_state.update(running=True, result=None, error=None)

    def _run():
        try:
            found = tinytuya.scan(timeout=timeout) if HAS_TUYA else None
            rows = []
            for ip, info in (found or {}).items():
                rows.append({"ip": ip, "id": info.get("gwId"),
                             "version": str(info.get("version", ""))})
            _scan_state["result"] = rows
        except Exception as e:
            _scan_state["error"] = str(e)[:300]
        finally:
            _scan_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


def scan_poll():
    return dict(_scan_state)


def save_devices(devices):
    """Valida e salva devices.json. devices: [{name,id,ip,key,version,parent?}]"""
    clean = []
    for d in devices:
        _id = (d.get("id") or "").strip()
        if not _id:
            continue
        clean.append({
            "name": (d.get("name") or _id[-6:]).strip(),
            "id": _id,
            "ip": (d.get("ip") or "").strip(),
            "key": (d.get("key") or "").strip(),
            "version": float(d.get("version") or 3.3),
            **({"parent": d["parent"].strip()} if (d.get("parent") or "").strip() else {}),
        })
    if not clean:
        return {"ok": False, "error": "Nenhum device valido (id obrigatorio)"}
    ids = [c["id"] for c in clean]
    for c in clean:
        if c.get("parent") and c["parent"] not in ids:
            return {"ok": False, "error": f"parent invalido em {c['name']}"}
        if c.get("parent") == c["id"]:
            return {"ok": False, "error": f"{c['name']} nao pode ser pai de si mesmo"}
    DEVICES_FILE.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    import app as core
    core._cache["ts"] = 0
    return {"ok": True, "count": len(clean)}


def test_device(device_id, mode="auto"):
    import app as core
    devs = core.load_devices()
    dev = next((d for d in devs if d.get("id") == device_id), None)
    if not dev:
        return {"ok": False, "error": "device nao esta no devices.json"}
    if mode == "cloud":
        from app import query_device_cloud
        r = query_device_cloud(dev)
    elif mode == "local":
        from app import query_device
        r = query_device(dev)
    else:
        from app import query_device_auto
        r = query_device_auto(dev)
    return {"ok": bool(r.get("online")), "reading": r}


def backfill_all(days=7):
    """Importa historico da nuvem p/ todas as tomadas (uma por vez)."""
    import app as core
    import tuya_cloud
    out = []
    for d in core.load_devices():
        try:
            r = tuya_cloud.backfill_device(d["id"], d.get("name", d["id"]), days=days)
            out.append({"name": d.get("name"), "id": d["id"], **r})
        except Exception as e:
            out.append({"name": d.get("name"), "id": d["id"], "ok": False,
                        "error": str(e)[:200]})
    return {"results": out,
            "added": sum(x.get("added", 0) for x in out if x.get("ok")),
            "calls": sum(x.get("pages", 0) for x in out if x.get("ok"))}
