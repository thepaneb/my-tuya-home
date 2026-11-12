# AGENTS.md — guia para agentes de código neste repo

## Stack

Python 3.14 + Flask (web) + Flet 1.x (nativo) + tinytuya (LAN + Cloud) + SQLite stdlib.
Sem build step no web; `pip install -r requirements.txt` basta.

## Comandos

```powershell
python app.py            # web em http://localhost:5000 (debug)
python app_flet.py       # app nativo (janela). Entry: ft.run(main)
python -c "import py_compile; py_compile.compile('app_flet.py', doraise=True)"
flet build windows|apk   # empacotar (ver PUBLISH.md)
```

Flet 1.x quebrou APIs antigas — **não usar**: `ft.app`, `ft.ElevatedButton`,
`Dropdown(on_change=)`, `ft.Tabs` com `Tab(content=)`, `LineChart` top-level.
Usar: `ft.run`, `ft.FilledButton`/`ft.OutlinedButton`/`ft.TextButton`,
`Dropdown(on_select=)`, troca de telas via Dropdown + container, barras com `Container`.

## Arquitetura

- `app.py`: Flask + cache 4s (`_cache`), logger 30s em thread daemon (`start_logger`).
  Rotas: `/`, `/dashboard`, `/setup`, `/api/status?mode=`, `/api/toggle|set`,
  `/api/history`, `/api/stats`, `/api/modes`, `/api/health`, `/api/setup/*`,
  `/api/device/<id>/info|logs`.
- `tuya_cloud.py`: singleton `tinytuya.Cloud()` (lê `tinytuya.json` ou `cloud.json`);
  `parse_cloud_status` converte `switch_1/cur_power/cur_current/cur_voltage/add_ele`
  para o formato local.
- `core_setup.py`: setup in-app (salvar nuvem, `cloud_fetch_devices`, `scan_start/poll`,
  `save_devices` com validação, `test_device`). Compartilhado entre Flask e Flet.
- `history.py`: `history.db`, `log_many` (só rows `online`), `get_stats` integra W→kWh.
- `app_flet.py`: importa `app`/`core_setup`/`history`; **não duplicar lógica de devices**.

## Regras de domínio (não quebrar)

1. **DPS por variante** (`parse_dps`): se tem DPS 19 → `18/19/20`; senão se tem 22 →
   `21/22/23`; senão fallback `19,22,5 / 18,21,4 / 20,23,6`. Energia: `add_ele/17/29 ÷ 100`.
   `sp modem` é variante B (21/22/23). Testar com: `python -c "from app import get_all_status; ... mode='auto'"`.
2. **Hierarquia**: `devices.json[].parent` = id do pai. `apply_hierarchy` calcula
   `watts_own = medido − filhos` e totais somam **só raízes**. Manter em `/api/status`,
   `/`, `/api/stats` (`total_kwh_roots`).
3. **Modos**: `auto` = local, fallback nuvem; `cloud` direto; `local` direto.
   Endpoints aceitam `?mode=` e `{"mode": ...}` no POST.
4. **Segredos**: nunca logar/retornar `key`/`apiSecret` inteiros (só sufixo `…xxxx` em logs
   de scan). `devices.json`, `tinytuya.json`, `cloud.json`, `history.db`, `snapshot.json`,
   `tuya-raw.json` estão no `.gitignore` — não commitar, não colar conteúdo em respostas.
5. **Demo mode**: sem `devices.json`, `get_all_status` retorna demo e UI funciona.
6. **Encoding Windows**: ao escrever JSON com `ensure_ascii=False`, abrir com
   `encoding="utf-8"` (o cp1252 padrão corrompe acentos — já aconteceu uma vez).
7. **Linguagem visual da cascata (única, em tudo)**: raiz = azul `#2a6df4`;
   filho = prefixo `↳` + verde `#2f7d4f`/`#7ee2ae` + nota "incluído no pai";
   aninhamento = card tonalizado (`KID_CARD`/`#1a2233`) recuado com conector azul
   à esquerda + rótulo "EM CASCATA". Vale para Painel, Energia e gráficos
   (no gráfico de linhas o filho usa a cor da família tracejada). Não criar
   segunda representação paralela (mapa separado, chips, etc.).
8. **Histórico**: `readings` cru 60 dias; `hourly`/`daily` para sempre (anual ok).
   `rollup(full)` após backfill; incremental a cada 10 min no logger.
   `/api/series?range=2h|24h|7d|30d|12m`. Nuvem só tem ~7 dias de logs
   (`tinytuya` não pagina sozinho — usar `next_row_key` manual, ver `fetch_logs_range`).
   Backfill: `core_setup.backfill_all` (~30 calls/tomada, usar com moderação).

## Testes rápidos

```powershell
python -c "from app import app; c=app.test_client(); print([(p,c.get(p).status_code) for p in ['/','/dashboard','/setup','/api/modes','/api/health','/api/status?mode=auto','/api/history','/api/stats']])"
python -c "import core_setup; print(core_setup.setup_status())"
```

## Docs

`README.md` (visão geral) · `FEATURES.md` (matriz modos × features + cascata) ·
`COMO_USAR.md` (passo a passo Tuya + troubleshooting `Sem permissão`) ·
`PUBLISH.md` (build Flet).
