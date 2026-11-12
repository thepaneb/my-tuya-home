# Modos de conexão × funcionalidades

| Funcionalidade | Local (LAN) | Nuvem (IoT Core) | Auto |
|---|---|---|---|
| Liga/desliga, toggle | ✅ `POST /api/set`, `POST /api/toggle` | ✅ mesmos endpoints com `mode=cloud` | ✅ tenta local, fallback nuvem |
| W / V / A instantâneo | ✅ direto do DPS (`18/19/20` ou `21/22/23`) | ✅ via `cur_power/cur_current/cur_voltage` | ✅ |
| kWh acumulado plug | ✅ `add_ele/17/29 ÷100` | ✅ `add_ele ÷100` | ✅ |
| Countdown | ✅ DPS 9 | ✅ `countdown_1` | ✅ |
| Latência | ms (socket local) | ~1s (HTTPS + cota) | melhor dos dois |
| Fora de casa | ❌ só mesma rede | ✅ qualquer internet | ✅ se local falhar |
| Device info/functions/specs | ❌ | ✅ `GET /api/device/<id>/info` | ✅ |
| Logs do device | ❌ | ✅ `GET /api/device/<id>/logs` | ✅ |
| Cenas/automações | ❌ (só timer local) | ✅ pelo portal Tuya | via portal |
| Histórico/gráficos | ✅ `history.db` via logger 30s (qualquer fonte) | ✅ mesma base | ✅ |
| Séries (min/hora/dia/mês) | ✅ `/api/series?range=2h\|24h\|7d\|30d\|12m` (rollup hora/dia, raw 60d, agregados p/ sempre) | logs dão ~7d p/ trás (backfill) | ✅ |
| Backfill nuvem | ✅ `POST /api/setup/backfill` ou aba Config (gasta ~30 calls/tomada, uma vez) | fonte dos 7 dias | ✅ |
| Requisitos | `devices.json` com `id/ip/key` | `tinytuya.json` ou `cloud.json` + trial IoT Core ativo | ambos |
| Limites | precisa mesmo Wi-Fi, IP pode mudar | cota trial (~26k calls/mês), trial expira | — |

Endpoints de modo: `?mode=auto|local|cloud` em `/`, `/dashboard`, `/api/status`; no POST envie `{"mode": "..."}`.
Diagnóstico: `GET /api/modes`, `GET /api/health`.

## Cascata física (ex: desktop ligado no setup)

Defina em `devices.json`: `{"name": "sp desktop", ..., "parent": "<id do setup>"}`.
- Card do pai mostra `W medido` vs `W próprio (= medido − filhos)` e `alimenta: ...`
- Card do filho mostra `ligado em: pai`
- Total do topo e `/api/status.total_watts` somam **só raízes** (sem dupla contagem)
- `/api/stats` retorna `total_kwh_roots` além do total bruto
