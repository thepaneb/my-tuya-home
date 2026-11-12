"""App nativa multiplataforma (Windows/macOS/Linux/Android/iOS) com Flet + Flutter.
Reusa 100% do core Python: app.py (local/nuvem/hierarquia) + history.py + core_setup.
Rodar:  python app_flet.py [--web]   |   Publicar: flet build windows | flet build apk ...
"""
import asyncio

import flet as ft

import app as core
import core_setup
import history

# --- Tema próprio do app (visual premium escuro, energia) ---
BG = "#0A0E1A"
SURFACE = "#141B2D"
SURFACE2 = "#1B2440"
BORDER = "#26314D"
TEXT = "#F2F5FF"
MUTED = "#8B93B0"
ACCENT = "#4F7CFF"
PURPLE = "#9B5CFF"
GREEN = "#34D399"
AMBER = "#FBBF24"
RED = "#F87171"
KID_CARD = "#1a2233"
GRADIENT = ft.LinearGradient(colors=[ACCENT, PURPLE])


def fmt(v, unit="", nd=1):
    if v is None:
        return "–"
    return f"{round(v, nd)} {unit}".strip()


async def refresh_data(mode):
    loop = asyncio.get_event_loop()
    data, _ = await loop.run_in_executor(None, lambda: core.get_all_status(force=True, mode=mode))
    total = round(sum((x.get("watts") or 0) for x in data
                      if x.get("online") and not x.get("parent")), 1)
    return data, total


def status_pill(dev):
    on = dev.get("on")
    if not dev.get("online"):
        return _pill("OFFLINE", "#3A4358", MUTED)
    if on:
        return _pill("● LIGADA", "#0E3B2E", GREEN)
    if on is False:
        return _pill("○ DESLIGADA", "#3A4358", MUTED)
    return _pill("?", "#3A4358", MUTED)


def _pill(text, bg, color):
    return ft.Container(
        content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, color=color),
        bgcolor=bg, border_radius=20, padding=ft.padding.Padding(10, 4, 10, 4),
    )


def _bd(color, w=1):
    side = ft.border.BorderSide(w, color)
    return ft.border.Border(side, side, side, side)


def icon_dot(icon, bg):
    return ft.Container(
        content=ft.Icon(icon, size=20, color=TEXT),
        bgcolor=bg, border_radius=14, padding=8,
    )


def metric_tile(icon, value, label, icon_bg):
    return ft.Container(
        content=ft.Row([
            icon_dot(icon, icon_bg),
            ft.Column([
                ft.Text(value, size=15, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Text(label, size=11, color=MUTED),
            ], spacing=0, expand=True),
        ], spacing=10),
        bgcolor=BG, border_radius=14, padding=10, expand=True,
    )


def mini_bars(device_id, hours=6, height=52, width=7):
    """Sparkline de barras das últimas leituras."""
    try:
        pts = history.get_history(device_id=device_id, hours=hours, max_points=30)
        vals = [r["watts"] or 0 for r in sorted(pts, key=lambda r: r["ts"])]
        if not vals:
            return ft.Text("sem histórico ainda", size=11, color=MUTED)
        mx = max(vals) or 1
        bars = []
        for i, v in enumerate(vals):
            h = max(4, v / mx * height)
            last = i == len(vals) - 1
            bars.append(ft.Container(width=width, height=h, border_radius=3,
                                     bgcolor=ACCENT if not last else GREEN))
        return ft.Row(bars, spacing=3, vertical_alignment=ft.CrossAxisAlignment.END)
    except Exception:
        return ft.Container()


def dev_hero(dev):
    return ft.Row([
        ft.Column([
            ft.Text(fmt(dev.get("watts"), "W"), size=34, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Text(f"{fmt(dev.get('watts_own'), 'W')} próprios · "
                    f"{fmt(dev.get('energy_kwh'), 'kWh', 2)} acumulado",
                    size=12, color=MUTED),
        ], spacing=0, expand=True),
        ft.Column([mini_bars(dev["id"])], spacing=8,
                  horizontal_alignment=ft.CrossAxisAlignment.END),
    ])


def dev_body(dev, on_toggle, on_info):
    src_local = (dev.get("source") or "local") != "cloud"
    return [
        ft.Row([
            icon_dot(ft.Icons.BOLT, "#22335C"),
            ft.Text(dev.get("name", "?"), size=17, weight=ft.FontWeight.BOLD, color=TEXT, expand=True),
            ft.Switch(value=bool(dev.get("on")),
                      disabled=dev.get("on") is None or not dev.get("online"),
                      active_color=GREEN,
                      on_change=lambda e, _id=dev["id"]: on_toggle(_id, e.control.value)),
            status_pill(dev),
            ft.Icon(ft.Icons.HOME if src_local else ft.Icons.CLOUD_OUTLINED,
                    tooltip="Rede local" if src_local else "Via nuvem",
                    size=18, color=GREEN if src_local else "#9fc0ff"),
            ft.IconButton(ft.Icons.SETTINGS, tooltip="Detalhes", icon_size=18,
                          icon_color=MUTED,
                          on_click=lambda e, _id=dev["id"]: on_info(_id)),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        dev_hero(dev),
        ft.Row([
            metric_tile(ft.Icons.SPEED, fmt(dev.get("amps"), "A", 2), "corrente", "#123B3B"),
            metric_tile(ft.Icons.ELECTRICAL_SERVICES, fmt(dev.get("volts"), "V"), "tensão", "#3B2F12"),
        ]),
        ft.Text(dev.get("fallback") or "", size=11, color=MUTED) if dev.get("fallback") else ft.Container(),
        ft.Text(dev.get("error") or "", size=11, color=AMBER) if dev.get("error") else ft.Container(),
    ]


def section_label(text, icon):
    return ft.Row([ft.Icon(icon, size=16, color=MUTED),
                   ft.Text(text, size=12, weight=ft.FontWeight.BOLD, color=MUTED)])


def device_card(dev, all_devs, on_toggle, on_info):
    kids = [d for d in all_devs if d.get("parent") == dev.get("id")]
    kid_cards = []
    for k in kids:
        kid_cards.append(
            ft.Container(
                content=ft.Column(dev_body(k, on_toggle, on_info), spacing=10),
                bgcolor=KID_CARD, border=_bd(BORDER), border_radius=18, padding=14,
            )
        )
    kids_block = ft.Container()
    if kid_cards:
        kids_block = ft.Column([
            section_label(f"EM CASCATA · incluídos nos {fmt(dev.get('watts'), 'W')} medidos", ft.Icons.ACCOUNT_TREE),
            ft.Container(
                content=ft.Column(kid_cards, spacing=10),
                border=ft.border.Border(ft.border.BorderSide(0, SURFACE),
                                        ft.border.BorderSide(3, ACCENT),
                                        ft.border.BorderSide(0, SURFACE),
                                        ft.border.BorderSide(0, SURFACE)),
                padding=ft.padding.Padding(10, 2, 0, 0),
            ),
        ], spacing=10)
    border_color = ACCENT if kids else (GREEN if dev.get("on") and dev.get("online") else BORDER)
    return ft.Container(
        content=ft.Column([*dev_body(dev, on_toggle, on_info), kids_block], spacing=12),
        bgcolor=SURFACE, border_radius=24, padding=18,
        border=ft.border.Border(*(ft.border.BorderSide(1.5, border_color) for _ in range(4))),
    )


def vbars(values, labels, color, height=110, max_labels=8):
    """Barras verticais com rótulos esparsos."""
    mx = max(values) if values else 0
    mx = mx or 1
    n = len(values)
    step = max(1, n // max_labels)
    cols = []
    for i, v in enumerate(values):
        h = max(4, (v or 0) / mx * height)
        lab = labels[i] if i < len(labels) else ""
        cols.append(ft.Column([
            ft.Container(width=14, height=h, border_radius=4,
                         bgcolor=color if (v or 0) > 0 else "#26314D"),
            ft.Text(lab if i % step == 0 else "", size=9, color=MUTED),
        ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True))
    return ft.Row(cols, spacing=2, vertical_alignment=ft.CrossAxisAlignment.END)


def dash_group_series(name, big, sub, own, values, labels, color, kids, unit):
    """Bloco de energia de uma raiz + filhos aninhados, mesma linguagem do Painel.
    kids: [{name, big, sub, values}]."""
    kid_cards = []
    for k in kids:
        kid_cards.append(ft.Container(
            content=ft.Column([
                ft.Text("↳ " + k["name"], size=14, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Text(f"{k['big']}", size=24, weight=ft.FontWeight.BOLD, color="#7ee2ae"),
                ft.Text(k["sub"], size=11, color=MUTED),
                vbars(k["values"], k.get("labels", labels), "#2f7d4f", height=70),
            ], spacing=6),
            bgcolor=KID_CARD, border=_bd(BORDER), border_radius=12, padding=12,
        ))
    kids_block = ft.Container()
    if kid_cards:
        kids_block = ft.Column([
            section_label("EM CASCATA", ft.Icons.ACCOUNT_TREE),
            ft.Container(
                content=ft.Column(kid_cards, spacing=8),
                border=ft.border.Border(ft.border.BorderSide(0, SURFACE),
                                        ft.border.BorderSide(3, ACCENT),
                                        ft.border.BorderSide(0, SURFACE),
                                        ft.border.BorderSide(0, SURFACE)),
                padding=ft.padding.Padding(10, 2, 0, 0),
            ),
        ], spacing=6)
    own_row = ft.Row([
        ft.Text(f"{big}", size=30, weight=ft.FontWeight.BOLD, color=TEXT),
        ft.Text(f"{unit}\nmedido", size=11, color=MUTED),
        ft.Text(f"{own}", size=30, weight=ft.FontWeight.BOLD, color="#7ee2ae"),
        ft.Text(f"{unit}\npróprios", size=11, color=MUTED),
    ], spacing=8) if (kids and own is not None) else ft.Row([
        ft.Text(f"{big}", size=30, weight=ft.FontWeight.BOLD, color=TEXT),
        ft.Text(f"{unit}\nno período", size=11, color=MUTED),
    ], spacing=8)
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text(name, size=15, weight=ft.FontWeight.BOLD, color="#9fc0ff", expand=True),
                ft.Text("RAIZ", size=10, weight=ft.FontWeight.BOLD, color=MUTED),
            ]),
            own_row,
            vbars(values, labels, color, height=110),
            kids_block,
        ], spacing=8),
        bgcolor=SURFACE, border_radius=20, padding=16,
    )


def section_card(title, icon, controls):
    return ft.Container(
        content=ft.Column([
            ft.Row([ft.Icon(icon, size=18, color=ACCENT),
                    ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=TEXT)]),
            *controls,
        ], spacing=10),
        bgcolor=SURFACE, border_radius=20, padding=16,
    )


def pill_tabs(options, get_sel, on_pick):
    """Segmentado próprio: zero dependência do tema (nada de amarelo padrão)."""
    row = ft.Row(spacing=6, alignment=ft.MainAxisAlignment.CENTER)

    def render():
        sel = get_sel()
        row.controls = [
            ft.Container(
                content=ft.Text(label, size=13, weight=ft.FontWeight.BOLD,
                                color="white" if value == sel else MUTED),
                bgcolor=ACCENT if value == sel else SURFACE2,
                border_radius=20, padding=ft.padding.Padding(16, 9, 16, 9),
                on_click=lambda e, _v=value: (on_pick(_v), render(), page_update()),
            )
            for value, label in options
        ]

    def page_update():
        try:
            row.page.update()
        except Exception:
            pass

    render()
    return row


def main(page: ft.Page):
    page.title = "Minhas Tomadas"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 14

    view_state = {"tab": "painel", "mode": "auto"}

    # --- Herói ---
    hero_total = ft.Text("–", size=44, weight=ft.FontWeight.BOLD, color="white")
    hero_sub = ft.Text("", size=13, color="#D6DCFF")
    hero = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.BOLT, size=26, color="white"),
                ft.Text("Minhas Tomadas", size=20, weight=ft.FontWeight.BOLD, color="white", expand=True),
                hero_kwh := ft.Container(
                    content=ft.Text("", size=12, weight=ft.FontWeight.BOLD, color="white"),
                    bgcolor="#00000066", border_radius=20,
                    padding=ft.padding.Padding(12, 6, 12, 6)),
            ]),
            ft.Text("CONSUMO TOTAL (raízes)", size=11, weight=ft.FontWeight.BOLD, color="#D6DCFF"),
            ft.Row([hero_total, ft.Text("W", size=20, color="#D6DCFF")], spacing=4,
                   vertical_alignment=ft.CrossAxisAlignment.END),
            hero_sub,
        ], spacing=6),
        gradient=GRADIENT, border_radius=26, padding=20,
    )

    SEG_STYLE = None  # (removido: pills próprias abaixo, sem cor de tema)
    nav = pill_tabs([("painel", "Painel"), ("dash", "Energia"), ("config", "Config"),
                     ("eventos", "Eventos")],
                    lambda: view_state["tab"], lambda v: show(v))
    mode_seg = pill_tabs([("auto", "Auto"), ("local", "Local"), ("cloud", "Nuvem")],
                         lambda: view_state["mode"], lambda v: on_mode_val(v))

    cards_col = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
    dash_col = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    # --- Config ---
    cfg_status = ft.Text("", color=MUTED, size=12)
    cloud_key = ft.TextField(label="Access ID", expand=True)
    cloud_secret = ft.TextField(label="Access Secret", password=True, expand=True)
    cloud_region = ft.Dropdown(label="Região",
        options=[ft.dropdown.Option("us", "us (Américas)"), ft.dropdown.Option("eu", "eu"),
                 ft.dropdown.Option("cn", "cn"), ft.dropdown.Option("in", "in")],
        value="us", width=170)
    cfg_out = ft.Text("", size=12, color=MUTED)
    scan_out = ft.Text("PC e tomadas no mesmo Wi-Fi.", size=12, color=MUTED)
    dev_rows = ft.Column(spacing=10)

    def reload_dev_rows():
        devs = core.load_devices()
        ctrls = []
        for d in devs:
            ctrls.append(section_card(f"🔌 {d.get('name', d['id'])}", ft.Icons.POWER, [
                ft.Row([ft.TextField(label="nome", value=d.get("name", ""), expand=True),
                        ft.TextField(label="ip", value=d.get("ip", ""), width=150)], wrap=True),
                ft.Row([ft.TextField(label="versão", value=str(d.get("version", 3.3)), width=90),
                        ft.Dropdown(label="alimentado por (pai)",
                            options=[ft.dropdown.Option("", "— raiz / direto na rede —")] +
                                    [ft.dropdown.Option(x["id"], x["name"]) for x in devs if x["id"] != d["id"]],
                            value=d.get("parent", "") or "", expand=True)], wrap=True),
            ]))
            ctrls[-1].data = {"id": d["id"], "key": d.get("key", ""),
                              "name_f": ctrls[-1].content.controls[1].controls[0],
                              "ip_f": ctrls[-1].content.controls[1].controls[1],
                              "ver_f": ctrls[-1].content.controls[2].controls[0],
                              "parent_dd": ctrls[-1].content.controls[2].controls[1]}
        dev_rows.controls = ctrls
        page.update()

    async def cfg_refresh():
        s = core_setup.setup_status()
        cfg_status.value = (f"devices: {s['devices_count']} · nuvem: {'ok' if s['cloud_configured'] else '—'} · "
                            f"tinytuya: {'ok' if s['tinytuya'] else 'falta'}")
        page.update()

    def on_save_cloud(e):
        r = core_setup.save_cloud_config(cloud_key.value, cloud_secret.value, cloud_region.value)
        cfg_out.value = "Nuvem salva." if r.get("ok") else f"Erro: {r.get('error')}"
        page.run_task(cfg_refresh); page.update()

    def on_fetch_cloud(e):
        async def _go():
            cfg_out.value = "Buscando na nuvem…"; page.update()
            loop = asyncio.get_event_loop()
            try:
                r = await loop.run_in_executor(None, core_setup.cloud_fetch_devices)
            except Exception as ex:
                cfg_out.value = f"Erro: {str(ex)[:200]}"; page.update(); return
            if not r.get("ok"):
                cfg_out.value = f"Erro: {r.get('error')}"; page.update(); return
            cur = {d["id"]: d for d in core.load_devices()}
            merged = []
            for nd in r["devices"]:
                old = cur.get(nd["id"], {})
                merged.append({**nd, "ip": old.get("ip", ""), "version": old.get("version", 3.3),
                               "parent": old.get("parent", ""), "name": old.get("name") or nd["name"]})
            rr = core_setup.save_devices(merged)
            cfg_out.value = f"{len(merged)} devices da nuvem, salvos: {rr.get('ok')}"
            reload_dev_rows(); await do_refresh()
        page.run_task(_go)

    def on_scan(e):
        async def _go():
            scan_out.value = "Varrendo rede (20s)…"; page.update()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: core_setup.scan_start(timeout=20))
            for _ in range(12):
                await asyncio.sleep(2)
                st = core_setup.scan_poll()
                if not st["running"]:
                    break
            st = core_setup.scan_poll()
            rows = st.get("result") or []
            if not rows:
                scan_out.value = "Nada encontrado (firewall/rede?)."
            else:
                lines = [str(r.get("ip")) + " <- ..." + str(r.get("id"))[-4:] + " v" + str(r.get("version")) for r in rows]
                scan_out.value = "Achados (copie o IP p/ a linha do mesmo ID):\n" + "\n".join(lines)
            page.update()
        page.run_task(_go)

    def on_backfill(e):
        async def _go():
            cfg_out.value = "Importando ~7 dias da nuvem (1-2 min)…"
            page.update()
            loop = asyncio.get_event_loop()
            try:
                r = await loop.run_in_executor(None, lambda: core_setup.backfill_all(days=7))
                n = r.get("added", 0)
                cfg_out.value = f"Importados: {n} leituras ({r.get('calls', 0)} chamadas API). Minuto/dia/semana agora saem do banco local."
            except Exception as ex:
                cfg_out.value = f"Erro: {str(ex)[:200]}"
            page.update()
            await do_refresh()
        page.run_task(_go)

    def on_save_devs(e):
        devs = []
        for card in dev_rows.controls:
            dd = card.data
            devs.append({"id": dd["id"], "key": dd["key"], "name": dd["name_f"].value,
                         "ip": dd["ip_f"].value, "version": dd["ver_f"].value or 3.3,
                         "parent": dd["parent_dd"].value})
        r = core_setup.save_devices(devs)
        cfg_out.value = f"Salvos: {r.get('count')} tomadas." if r.get("ok") else f"Erro: {r.get('error')}"
        page.run_task(do_refresh); page.update()

    config_tab = ft.Column([
        section_card("Nuvem Tuya", ft.Icons.CLOUD, [
            ft.Text("Access ID/Secret do projeto em platform.tuya.com → Overview.", size=12, color=MUTED),
            ft.Row([cloud_key, cloud_secret], wrap=True),
            ft.Row([cloud_region,
                    ft.FilledButton("Salvar nuvem", style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
                                    on_click=on_save_cloud),
                    ft.OutlinedButton("Buscar devices", on_click=on_fetch_cloud)], wrap=True),
            cfg_out,
        ]),
        section_card("Rede local", ft.Icons.WIFI, [
            ft.Row([ft.FilledButton("Varrer rede",
                                    style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
                                    on_click=on_scan),
                    ft.FilledButton("Importar 7 dias da nuvem",
                                    style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
                                    on_click=on_backfill)]),
            scan_out,
            cfg_out,
        ]),
        section_card("Tomadas + cascata", ft.Icons.POWER, [
            dev_rows,
            ft.Row([ft.FilledButton("Salvar tomadas",
                                    style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
                                    on_click=on_save_devs),
                    ft.OutlinedButton("Recarregar", on_click=lambda e: reload_dev_rows)], wrap=True),
        ]),
    ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    info_dlg = ft.AlertDialog(title=ft.Text("Detalhes"), content=ft.Text("", size=12),
                              actions=[ft.TextButton("Fechar", on_click=lambda e: _close())])

    def _close():
        try:
            page.pop_dialog()
        except Exception:
            pass
        page.update()

    def on_info(dev_id):
        async def _go():
            loop = asyncio.get_event_loop()
            try:
                import tuya_cloud
                det = await loop.run_in_executor(None, lambda: tuya_cloud.cloud_detail(dev_id))
            except Exception as ex:
                info_dlg.content = ft.Text(f"Erro: {ex}", size=13)
                page.show_dialog(info_dlg); page.update(); return
            st = det.get("status", {}) or {}
            try:
                cd_field = ft.TextField(label="segundos p/ desligar (0 cancela)",
                                        value=str(st.get("countdown") or 0), width=200,
                                        keyboard_type=ft.KeyboardType.NUMBER)
                relay_dd = ft.Dropdown(label="Ao voltar energia",
                    options=[ft.dropdown.Option(v, v) for v in ["last", "power_on", "power_off"]],
                    value=st.get("relay_status") or "last", width=200)
                light_dd = ft.Dropdown(label="LED",
                    options=[ft.dropdown.Option(v, v) for v in ["relay", "pos", "none"]],
                    value=st.get("light_mode") or "relay", width=170)
                lock_sw = ft.Switch(label="Trava infantil", value=bool(st.get("child_lock")))
                over_sw = ft.Switch(label="Anti-sobrecarga", value=bool(st.get("overcharge")))
                cfg_out_detail = ft.Text("", size=12, color=MUTED)

                def _send(cmds):
                    async def __go():
                        try:
                            import tuya_cloud as _tc
                            r = await loop.run_in_executor(None, lambda: _tc.cloud_send(dev_id, cmds))
                        except Exception as ex:
                            r = {"ok": False, "error": str(ex)}
                        cfg_out_detail.value = "Aplicado." if r.get("ok") else f"Falhou: {r.get('error')}"
                        page.update()
                        await do_refresh()
                    page.run_task(__go)

                fault = st.get("fault", 0)
                import datetime
                log_rows = []
                for l in (det.get("logs") or [])[:12]:
                    t = datetime.datetime.fromtimestamp((l.get("event_time") or 0) / 1000).strftime("%d/%m %H:%M") if l.get("event_time") else ""
                    log_rows.append(ft.Text(f"{l.get('code', 'evento')}: {l.get('value', l.get('event_value', ''))} · {t}",
                                            size=11, color=MUTED))
                info_dlg.content = ft.Column([
                    ft.Text("⚠ Falha: " + str(fault), color=RED) if fault else
                    ft.Text("✓ sem falhas", color=GREEN, size=12),
                    ft.Row([cd_field,
                            ft.FilledButton("Aplicar",
                                style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
                                on_click=lambda e: _send({"countdown_1": cd_field.value}))],
                           wrap=True),
                    ft.Row([relay_dd, light_dd], wrap=True),
                    ft.Row([
                        ft.FilledButton("Aplicar energia/LED",
                            style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
                            on_click=lambda e: _send({"relay_status": relay_dd.value,
                                                      "light_mode": light_dd.value}))],
                           wrap=True),
                    lock_sw, over_sw,
                    ft.Row([ft.FilledButton("Aplicar travas",
                            style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
                            on_click=lambda e: _send({"child_lock": lock_sw.value,
                                                      "overcharge_switch": over_sw.value}))]),
                    cfg_out_detail,
                    ft.Divider(),
                    ft.Text("Últimos eventos", weight=ft.FontWeight.BOLD, size=12),
                    *log_rows,
                ], spacing=8, scroll=ft.ScrollMode.AUTO, width=420, height=480)
            except Exception as ex:
                info_dlg.content = ft.Text(f"Erro: {ex}", size=13)
            try:
                page.show_dialog(info_dlg)
            except RuntimeError:
                try:
                    page.pop_dialog()
                except Exception:
                    pass
                page.show_dialog(info_dlg)
            page.update()
        page.run_task(_go)

    events_col = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
    events_state = {"loaded": False}

    async def load_events():
        events_col.controls = [ft.Text("Buscando eventos na nuvem…", color=MUTED)]
        page.update()
        loop = asyncio.get_event_loop()
        try:
            import tuya_cloud
            devs = core.load_devices()
            blocks = []
            for d in devs:
                try:
                    lg = await loop.run_in_executor(None, lambda _d=d: tuya_cloud.cloud_logs(_d["id"]))
                    logs = (lg.get("result", {}).get("logs", []) if isinstance(lg, dict) else [])[:15]
                except Exception as ex:
                    logs = [{"code": "erro", "value": str(ex)[:100]}]
                import datetime
                items = []
                for l in logs:
                    t = datetime.datetime.fromtimestamp((l.get("event_time") or 0) / 1000).strftime("%d/%m %H:%M") if l.get("event_time") else ""
                    items.append(ft.Row([
                        ft.Text(l.get("code", "evento"), size=12, weight=ft.FontWeight.BOLD, color=TEXT, expand=True),
                        ft.Text(f"{l.get('value', l.get('event_value', ''))} · {t}", size=11, color=MUTED),
                    ]))
                blocks.append(section_card(f"🔌 {d.get('name', d['id'])}", ft.Icons.HISTORY,
                                           items or [ft.Text("sem eventos recentes", color=MUTED, size=12)]))
            events_col.controls = [
                ft.Row([ft.FilledButton("Recarregar",
                        style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
                        on_click=lambda e: page.run_task(load_events))]),
                *blocks,
            ]
            events_state["loaded"] = True
        except Exception as ex:
            events_col.controls = [ft.Text(f"Erro: {ex}", color=RED)]
        page.update()

    content_host = ft.Column([cards_col], expand=True, scroll=ft.ScrollMode.AUTO)
    panels = {"painel": cards_col, "dash": dash_col, "config": config_tab, "eventos": events_col}

    def show(tab):
        view_state["tab"] = tab
        if tab == "eventos" and not events_state["loaded"]:
            page.run_task(load_events)
        content_host.controls = [panels[tab]]
        page.update()

    def show(tab):
        view_state["tab"] = tab
        content_host.controls = [panels[tab]]
        page.update()

    def on_nav(e):
        show(e.control.selected[0])

    def on_mode_val(v):
        view_state["mode"] = v
        page.run_task(do_refresh)

    erange = {"v": "24h"}

    def on_erange(v):
        erange["v"] = v
        page.run_task(do_refresh)

    range_pills = pill_tabs([("2h", "Minuto"), ("24h", "Dia"), ("7d", "Semana"),
                             ("30d", "Mês"), ("12m", "Ano")],
                            lambda: erange["v"], on_erange)

    async def build_energy():
        loop = asyncio.get_event_loop()
        s = await loop.run_in_executor(None, lambda: history.get_series(erange["v"]))
        cfg = {c.get("id"): c for c in core.load_devices()}
        bd = s.get("by_device", {}) or {}
        devs = [{"id": did, "name": dd.get("name"),
                 "parent": (cfg.get(did, {}) or {}).get("parent")} for did, dd in bd.items()]
        roots = [d for d in devs if not d.get("parent")]
        fam = ["#4F7CFF", "#34D399", "#9a6bff", "#FBBF24"]
        for i, d in enumerate(roots):
            d["color"] = fam[i % len(fam)]
        for d in devs:
            if d.get("parent"):
                p = next((r for r in roots if r["id"] == d["parent"]), None)
                d["color"] = (p or {}).get("color", "#9aa0ae")
        gran = s.get("gran")
        if gran == "min":
            title, unit = "MINUTO A MINUTO · POTÊNCIA (W)", "W"
        elif gran == "hour":
            title, unit = "POR HORA · kWh", "kWh"
        elif gran == "day":
            title, unit = "POR DIA · kWh", "kWh"
        else:
            title, unit = "POR MÊS · kWh", "kWh"
        rt = s.get("roots_total_kwh")
        if rt is None:
            rt = round(sum((bd.get(r["id"], {}) or {}).get("total", 0) for r in roots), 3)
        out = [range_pills,
               ft.Container(
                   content=ft.Column([
                       ft.Text(title + " · SÓ RAÍZES", size=11, weight=ft.FontWeight.BOLD, color="#D6DCFF"),
                       ft.Row([ft.Text(f"{rt}", size=34, weight=ft.FontWeight.BOLD, color="white"),
                               ft.Text(f"{unit}\nsem duplicar\ncascata", size=12, color="#D6DCFF")], spacing=6),
                   ], spacing=2),
                   gradient=GRADIENT, border_radius=22, padding=18)]
        for r in roots:
            rd = bd.get(r["id"], {}) or {}
            if gran == "min":
                vals = [p.get("w", 0) for p in rd.get("series", [])]
                labels = [__import__("datetime").datetime.fromtimestamp(p.get("t", 0)).strftime("%H:%M")
                          for p in rd.get("series", [])]
                big, sub = (f"{round(vals[-1], 1)}" if vals else "–"), "W agora"
            else:
                vals = rd.get("series", [])
                labels = [b["label"] for b in s.get("buckets", [])]
                big, sub = (f"{rd.get('total', 0)}", "kWh medido")
            kids = []
            for k in [d for d in devs if d.get("parent") == r["id"]]:
                kd = bd.get(k["id"], {}) or {}
                if gran == "min":
                    kv = [p.get("w", 0) for p in kd.get("series", [])]
                    import datetime as _dt
                    kl = [_dt.datetime.fromtimestamp(p.get("t", 0)).strftime("%H:%M")
                          for p in kd.get("series", [])]
                    kids.append({"name": k["name"], "big": f"{round(kv[-1], 1)}" if kv else "–",
                                 "sub": "W agora", "values": kv, "labels": kl})
                else:
                    kids.append({"name": k["name"], "big": f"{kd.get('total', 0)}",
                                 "sub": "kWh · incluído no pai", "values": kd.get("series", []),
                                 "labels": [b["label"] for b in s.get("buckets", [])]})
            if gran != "min":
                kid_sum = 0.0
                for k in [d for d in devs if d.get("parent") == r["id"]]:
                    kid_sum += (bd.get(k["id"], {}) or {}).get("total", 0) or 0
                own = max(0, round((rd.get("total", 0) or 0) - kid_sum, 3))
            else:
                own = None
            out.append(dash_group_series(r["name"], big, sub, own, vals, labels, r["color"], kids, unit))
        return out

    async def do_refresh():
        mode = view_state["mode"]
        try:
            data, total = await refresh_data(mode)
            online = sum(1 for d in data if d.get("online"))
            hero_total.value = f"{total}"
            hero_sub.value = f"{online}/{len(data)} online · modo {mode} · só raízes, sem duplicar cascata"
            try:
                stats = history.get_stats(hours=24)
                cfg = {c.get("id"): c for c in core.load_devices()}
                for d in stats.get("devices", []):
                    d["parent"] = (cfg.get(d.get("id"), {}) or {}).get("parent")
                total_roots = round(sum(d["kwh"] for d in stats.get("devices", []) if not d.get("parent")), 3)
                hero_kwh.content.value = f"⚡ {total_roots} kWh / 24h"
            except Exception:
                pass
            cards_col.controls = [device_card(d, data, do_toggle, on_info)
                                  for d in data if not d.get("parent")]
            try:
                dash_col.controls = await build_energy()
            except Exception as ex:
                dash_col.controls = [ft.Text(f"Energia indisponível: {ex}", color=MUTED)]
        except Exception as e:
            hero_sub.value = f"erro: {str(e)[:150]}"
        page.update()

    def do_toggle(dev_id, value=None):
        async def _go():
            loop = asyncio.get_event_loop()
            if value is None:
                data, _ = await loop.run_in_executor(None, lambda: core.get_all_status(mode=view_state["mode"]))
                cur = next((x for x in data if x.get("id") == dev_id), None)
                target = (not cur.get("on")) if cur and cur.get("on") is not None else True
            else:
                target = bool(value)
            await loop.run_in_executor(None, lambda: core.set_switch(dev_id, target, mode=view_state["mode"]))
            await do_refresh()
        page.run_task(_go)

    async def auto_loop():
        while True:
            await asyncio.sleep(8)
            try:
                await do_refresh()
            except Exception:
                pass

    page.add(
        hero,
        ft.Row([nav], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([ft.Text("Conexão", size=12, color=MUTED), mode_seg,
                ft.IconButton(ft.Icons.REFRESH, tooltip="Atualizar",
                              on_click=lambda e: page.run_task(do_refresh))]),
        content_host,
    )
    reload_dev_rows()
    page.run_task(cfg_refresh)
    page.run_task(do_refresh)
    page.run_task(auto_loop)


if __name__ == "__main__":
    import sys
    core.start_logger()
    if "--web" in sys.argv:
        port = 8503
        for a in sys.argv:
            if a.startswith("--port="):
                try:
                    port = int(a.split("=", 1)[1])
                except ValueError:
                    pass
        ft.run(main, view=ft.AppView.WEB_BROWSER, port=port)
    else:
        ft.run(main)
