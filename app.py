"""Painel unificado Tuya/SmartLife com medicao de energia.
Modos: local (LAN, rapido, sem cota) e nuvem (remoto, IoT Core).
Auto = tenta local, cai para nuvem se falhar.
"""
import json
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import history
import tuya_cloud

try:
    import tinytuya
    HAS_TUYA = True
except ImportError:
    HAS_TUYA = False

app = Flask(__name__)
BASE = Path(__file__).parent
DEVICES_FILE = BASE / "devices.json"

_cache = {"ts": 0, "data": []}
CACHE_TTL = 4  # segundos
DEFAULT_MODE = "auto"  # auto | local | cloud


def load_devices():
    if not DEVICES_FILE.exists():
        return []
    try:
        return json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Erro lendo devices.json: {e}")
        return []


def parse_dps(dps: dict) -> dict:
    """Normaliza DPS de tomadas Tuya com energia.

    Mapeamentos comuns:
      Novo (3.3/3.4): 1=switch, 18=corrente mA, 19=potencia 0.1W, 20=tensao 0.1V
      Antigo (3.1):    1=switch, 4=corrente mA, 5=potencia 0.1W, 6=tensao 0.1V
      Consumo acumulado: 17, 27 ou 29 (kWh *100 ou *1000 dependendo do firmware)
    """
    dps = dps or {}
    on = dps.get("1", dps.get(1))

    def has(*keys):
        return any((str(k) in dps or k in dps) for k in keys)

    def pick(*keys):
        for k in keys:
            if str(k) in dps:
                return dps[str(k)]
            if k in dps:
                return dps[k]
        return None

    # Variante A (desktop/setup): 18=mA, 19=0.1W, 20=0.1V
    # Variante B (sp modem e similares): 21=mA, 22=0.1W, 23=0.1V
    if has(19):
        raw_power, raw_current, raw_voltage = pick(19), pick(18), pick(20)
    elif has(22):
        raw_power, raw_current, raw_voltage = pick(22), pick(21), pick(23)
    else:
        raw_power = pick(19, 22, 5)
        raw_current = pick(18, 21, 4)
        raw_voltage = pick(20, 23, 6)
    raw_energy = pick(17, 29, 27)  # kWh acumulado, se existir

    watts = (raw_power / 10.0) if isinstance(raw_power, (int, float)) else None
    amps = (raw_current / 1000.0) if isinstance(raw_current, (int, float)) else None
    volts = (raw_voltage / 10.0) if isinstance(raw_voltage, (int, float)) else None

    energy_kwh = None
    if isinstance(raw_energy, (int, float)):
        # DPS 17/29 (add_ele) geralmente vem em 0.01 kWh. Ex: 83 -> 0.83 kWh
        energy_kwh = round(raw_energy / 100.0, 3)

    return {
        "on": bool(on) if on is not None else None,
        "watts": watts,
        "amps": amps,
        "volts": volts,
        "energy_kwh": energy_kwh,
        "countdown": pick(9),
        "raw": dps,
    }


def query_device(dev: dict, timeout=4) -> dict:
    name = dev.get("name", dev.get("id", "?")[:8])
    base = {"name": name, "id": dev.get("id"), "ip": dev.get("ip"),
            "online": False, "on": None, "watts": None,
            "amps": None, "volts": None, "energy_kwh": None, "error": None,
            "countdown": None,
            "source": "local"}
    if not HAS_TUYA:
        base["error"] = "tinytuya nao instalado"
        return base
    try:
        d = tinytuya.OutletDevice(
            dev["id"], dev["ip"], dev["key"]
        )
        d.set_version(float(dev.get("version", 3.3)))
        d.set_socketTimeout(timeout)
        data = d.status()
        if not data or "dps" not in data:
            # Alguns plugs precisam de UPDATEDPS para atualizar energia
            try:
                payload = d.generate_payload(tinytuya.UPDATEDPS)
                d.send(payload)
                data = d.status()
            except Exception:
                pass
        if data and "dps" in data:
            parsed = parse_dps(data["dps"])
            base.update(parsed)
            base.pop("raw", None)
            base["online"] = True
        else:
            base["error"] = str(data)[:200] if data else "sem resposta"
    except Exception as e:
        base["error"] = str(e)[:200]
    return base


def query_device_cloud(dev: dict) -> dict:
    base = {"name": dev.get("name", dev.get("id", "?")[:8]), "id": dev.get("id"),
            "ip": dev.get("ip"), "online": False, "on": None, "watts": None,
            "amps": None, "volts": None, "energy_kwh": None, "error": None,
            "source": "cloud"}
    try:
        r = tuya_cloud.cloud_status(dev["id"])
        base.update(r)
        base["name"] = dev.get("name", base.get("name"))
        base["id"] = dev.get("id")
        base["ip"] = dev.get("ip")
    except Exception as e:
        base["error"] = str(e)[:200]
    return base


def query_device_auto(dev: dict, timeout=4) -> dict:
    """Auto: local primeiro (rapido, sem cota); fallback nuvem se offline."""
    local = query_device(dev, timeout=timeout)
    if local.get("online"):
        return local
    if tuya_cloud.is_configured():
        cloud = query_device_cloud(dev)
        if cloud.get("online"):
            cloud["error"] = None
            cloud["fallback"] = "☁ via nuvem (fora do alcance local agora)"
            return cloud
    return local


def apply_hierarchy(status_list, cfg_list):
    """Cascata fisica: filho consome dentro do pai. Evita soma dobrada.

    Ex: desktop ligado no setup -> setup medido inclui desktop.
    watts_own(pai) = medido - soma(filhos online). Total = soma das raizes.
    """
    by_id = {s.get("id"): s for s in status_list}
    cfg_by = {c.get("id"): c for c in (cfg_list or [])}
    for s in status_list:
        parent = (cfg_by.get(s.get("id"), {}) or {}).get("parent")
        s["parent"] = parent
        s["is_child"] = bool(parent)
        s["children"] = []
        s["children_names"] = []
    for s in status_list:
        p = s.get("parent")
        if p and p in by_id:
            by_id[p]["children"].append(s["id"])
            by_id[p]["children_names"].append(s["name"])
    for s in status_list:
        kids = [by_id[c] for c in s.get("children", []) if c in by_id]
        kids_w = sum((k.get("watts") or 0) for k in kids if k.get("online"))
        if s.get("online") and kids and s.get("watts") is not None:
            s["watts_own"] = max(0, round((s["watts"] or 0) - kids_w, 1))
        else:
            s["watts_own"] = s.get("watts")
        kids_e = sum((k.get("energy_kwh") or 0) for k in kids if k.get("energy_kwh") is not None)
        if s.get("energy_kwh") is not None and kids and kids_e:
            s["energy_kwh_own"] = max(0, round(s["energy_kwh"] - kids_e, 3))
        else:
            s["energy_kwh_own"] = s.get("energy_kwh")
    total_roots = round(sum((s.get("watts") or 0) for s in status_list
                            if s.get("online") and not s.get("parent")), 1)
    return total_roots


def get_all_status(force=False, mode=DEFAULT_MODE):
    now = time.time()
    use_cache = (mode == (_cache.get("mode") or DEFAULT_MODE))
    if not force and use_cache and (now - _cache["ts"] < CACHE_TTL) and _cache["data"]:
        return _cache["data"], True
    devices = load_devices()
    if not devices:
        # Modo demonstracao: UI funciona sem devices.json
        demo = [
            {"name": "Tomada 1 (demo)", "id": "demo1", "ip": "-", "online": False,
             "on": True, "watts": 42.5, "amps": 0.35, "volts": 121.0,
             "energy_kwh": 1.2, "error": "Configure devices.json", "source": "demo"},
            {"name": "Tomada 2 (demo)", "id": "demo2", "ip": "-", "online": False,
             "on": False, "watts": 0.0, "amps": 0.0, "volts": None,
             "energy_kwh": None, "error": "Configure devices.json", "source": "demo"},
        ]
        _cache.update(ts=now, data=demo, mode=mode)
        return demo, False
    if mode == "local":
        out = [query_device(d) for d in devices]
    elif mode == "cloud":
        out = [query_device_cloud(d) for d in devices]
    else:
        out = [query_device_auto(d) for d in devices]
    total_roots = apply_hierarchy(out, devices)
    _cache.update(ts=now, data=out, mode=mode, total_roots=total_roots)
    try:
        history.log_many(out)
    except Exception as e:
        print(f"history: {e}")
    return out, False


_logger_started = False

def start_logger(interval=30):
    """Thread que registra leituras periodicamente para o dashboard."""
    global _logger_started
    if _logger_started:
        return
    _logger_started = True

    def loop():
        while True:
            try:
                if load_devices():
                    get_all_status(force=True)
            except Exception as e:
                print(f"logger: {e}")
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()


def set_switch(device_id: str, turn_on: bool, mode=DEFAULT_MODE):
    devices = load_devices()
    dev = next((d for d in devices if d.get("id") == device_id), None)
    if not dev:
        return {"ok": False, "error": "device nao encontrado em devices.json"}
    if not HAS_TUYA:
        return {"ok": False, "error": "tinytuya nao instalado"}
    # Nuvem direta
    if mode == "cloud":
        try:
            return tuya_cloud.cloud_set(device_id, turn_on)
        except Exception as e:
            return {"ok": False, "error": str(e)[:300], "source": "cloud"}
    # Local primeiro
    try:
        d = tinytuya.OutletDevice(dev["id"], dev["ip"], dev["key"])
        d.set_version(float(dev.get("version", 3.3)))
        if turn_on:
            d.turn_on()
        else:
            d.turn_off()
        _cache["ts"] = 0  # invalida cache
        return {"ok": True, "on": turn_on, "source": "local"}
    except Exception as e:
        if mode == "auto" and tuya_cloud.is_configured():
            try:
                return tuya_cloud.cloud_set(device_id, turn_on)
            except Exception as e2:
                return {"ok": False, "error": f"local: {str(e)[:120]} | nuvem: {str(e2)[:120]}"}
        return {"ok": False, "error": str(e)[:300], "source": "local"}


@app.get("/")
def index():
    start_logger()
    mode = request.args.get("mode", DEFAULT_MODE)
    devices, _ = get_all_status(mode=mode)
    total_w = round(sum((x.get("watts") or 0) for x in devices
                        if x.get("online") and not x.get("parent")), 1)
    return render_template("index.html", devices=devices, total_w=total_w, mode=mode)


@app.get("/dashboard")
def dashboard():
    start_logger()
    mode = request.args.get("mode", DEFAULT_MODE)
    devices, _ = get_all_status(mode=mode)
    return render_template("dashboard.html", devices=devices, mode=mode)


@app.get("/api/modes")
def api_modes():
    return jsonify({
        "modes": ["auto", "local", "cloud"],
        "default": DEFAULT_MODE,
        "local_available": HAS_TUYA and bool(load_devices()),
        "cloud_available": tuya_cloud.is_configured(),
        "capabilities": {
            "local": ["on/off", "toggle", "W/V/A instantaneo", "kWh acumulado",
                      "countdown", "resposta ms", "sem cota", "historico 30s"],
            "cloud": ["on/off", "toggle", "status remoto", "W/V/A", "kWh",
                      "device info/functions", "logs", "cenas", "fora de casa"],
        },
    })


@app.get("/api/health")
def api_health():
    devices = load_devices()
    return jsonify({
        "devices_config": len(devices),
        "local_keys_ok": all(bool(d.get("key")) and bool(d.get("ip")) for d in devices) if devices else False,
        "cloud_configured": tuya_cloud.is_configured(),
        "tinytuya": HAS_TUYA,
    })


@app.get("/api/history")
def api_history():
    device_id = request.args.get("device", "all")
    hours = float(request.args.get("hours", 24))
    return jsonify(history.get_history(device_id=device_id, hours=hours))


@app.get("/api/series")
def api_series():
    rng = request.args.get("range", "24h")
    if rng not in ("2h", "24h", "7d", "30d", "12m"):
        rng = "24h"
    s = history.get_series(rng, device_id=request.args.get("device", "all"))
    cfg = {c.get("id"): c for c in load_devices()}
    devs = [{"id": did, "name": dd.get("name"),
             "parent": (cfg.get(did, {}) or {}).get("parent")}
            for did, dd in s.get("by_device", {}).items()]
    roots_total = round(sum(dd.get("total", 0)
                            for did, dd in s.get("by_device", {}).items()
                            if not (cfg.get(did, {}) or {}).get("parent")), 3)
    s["devices"] = devs
    s["roots_total_kwh"] = roots_total
    return jsonify(s)


@app.get("/api/stats")
def api_stats():
    hours = float(request.args.get("hours", 24))
    stats = history.get_stats(hours=hours)
    # Marca hierarquia e recalcula total sem dupla contagem (só raizes)
    cfg = {c.get("id"): c for c in load_devices()}
    for d in stats.get("devices", []):
        d["parent"] = (cfg.get(d.get("id"), {}) or {}).get("parent")
        d["is_child"] = bool(d["parent"])
    stats["total_kwh_roots"] = round(sum(
        d["kwh"] for d in stats.get("devices", []) if not d.get("parent")), 3)
    return jsonify(stats)


@app.get("/api/status")
def api_status():
    force = request.args.get("force") == "1"
    mode = request.args.get("mode", _cache.get("mode") or DEFAULT_MODE)
    data, cached = get_all_status(force=force, mode=mode)
    total_w = round(sum((x.get("watts") or 0) for x in data
                        if x.get("online") and not x.get("parent")), 1)
    online = sum(1 for x in data if x.get("online"))
    return jsonify({"devices": data, "total_watts": total_w,
                    "online": online, "total": len(data), "cached": cached, "mode": mode,
                    "note": "total soma só raízes (filhos em cascata não duplicam)"})


@app.post("/api/toggle/<device_id>")
def api_toggle(device_id):
    body = request.get_json(force=True, silent=True) or {}
    mode = body.get("mode") or request.args.get("mode", DEFAULT_MODE)
    devices, _ = get_all_status(mode=mode)
    cur = next((x for x in devices if x.get("id") == device_id), None)
    if not cur:
        return jsonify({"ok": False, "error": "nao encontrado"}), 404
    target = not cur.get("on") if cur.get("on") is not None else True
    res = set_switch(device_id, target, mode=mode)
    return jsonify(res)


@app.post("/api/set/<device_id>")
def api_set(device_id):
    body = request.get_json(force=True, silent=True) or {}
    target = bool(body.get("on"))
    mode = body.get("mode") or request.args.get("mode", DEFAULT_MODE)
    return jsonify(set_switch(device_id, target, mode=mode))


@app.get("/api/device/<device_id>/info")
def api_device_info(device_id):
    """Exclusivo nuvem: functions/properties/dps map."""
    try:
        return jsonify({"id": device_id, "source": "cloud", **tuya_cloud.cloud_info(device_id)})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 502


@app.get("/api/device/<device_id>/detail")
def api_device_detail(device_id):
    """Pacote completo: status + funcoes + ultimos logs (nuvem)."""
    try:
        return jsonify(tuya_cloud.cloud_detail(device_id))
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 502


@app.post("/api/device/<device_id>/cmd")
def api_device_cmd(device_id):
    """Comandos de configuracao: countdown, relay, child_lock, etc. (nuvem)."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(tuya_cloud.cloud_send(device_id, body.get("commands", {})))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 502


@app.get("/eventos")
def eventos():
    start_logger()
    devices, _ = get_all_status()
    return render_template("events.html", devices=devices)


@app.get("/api/device/<device_id>/logs")
def api_device_logs(device_id):
    try:
        return jsonify({"id": device_id, "source": "cloud", "logs": tuya_cloud.cloud_logs(device_id)})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 502


@app.get("/setup")
def setup_page():
    start_logger()
    return render_template("setup.html", devices=load_devices())


@app.get("/api/setup/status")
def api_setup_status():
    import core_setup
    return jsonify(core_setup.setup_status())


@app.post("/api/setup/cloud")
def api_setup_cloud():
    import core_setup
    b = request.get_json(force=True, silent=True) or {}
    return jsonify(core_setup.save_cloud_config(
        b.get("apiKey", ""), b.get("apiSecret", ""),
        b.get("region", "us"), b.get("apiDeviceID", "")))


@app.get("/api/setup/cloud_fetch")
def api_setup_cloud_fetch():
    import core_setup
    try:
        return jsonify(core_setup.cloud_fetch_devices())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]})


@app.post("/api/setup/scan")
def api_setup_scan():
    import core_setup
    b = request.get_json(force=True, silent=True) or {}
    return jsonify(core_setup.scan_start(timeout=int(b.get("timeout", 20))))


@app.get("/api/setup/scan")
def api_setup_scan_poll():
    import core_setup
    return jsonify(core_setup.scan_poll())


@app.post("/api/setup/devices")
def api_setup_devices():
    import core_setup
    b = request.get_json(force=True, silent=True) or {}
    return jsonify(core_setup.save_devices(b.get("devices", [])))


@app.get("/api/setup/test/<device_id>")
def api_setup_test(device_id):
    import core_setup
    mode = request.args.get("mode", "auto")
    return jsonify(core_setup.test_device(device_id, mode=mode))


@app.post("/api/setup/backfill")
def api_setup_backfill():
    import core_setup
    b = request.get_json(force=True, silent=True) or {}
    try:
        days = max(1, min(30, int(b.get("days", 7))))
    except (TypeError, ValueError):
        days = 7
    try:
        return jsonify(core_setup.backfill_all(days=days))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]})


if __name__ == "__main__":
    print("Tinytuya disponivel:", HAS_TUYA)
    print("devices.json existe:", DEVICES_FILE.exists())
    app.run(host="0.0.0.0", port=5000, debug=True)
