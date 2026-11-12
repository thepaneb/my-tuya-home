# Minhas Tomadas

Painel limpo (sem anúncios) para tomadas inteligentes Tuya/SmartLife com medição de energia.
Fala direto com as tomadas na rede local e usa a nuvem Tuya só como fallback e para
recursos remotos. Web + app nativo multiplataforma, mesmo core Python.

## Telas

- **Painel** (`/`): cards por tomada — switch liga/desliga, status, W medido vs W próprio,
  V, A, kWh acumulado, ícone de origem (🏠 local / ☁ nuvem), hierarquia de cascata
  aninhada, countdown, Detalhes (proteções + logs).
- **Dashboard** (`/dashboard`): consumo minuto a minuto (2h), por hora (24h),
  por dia (7d/30d) e por mês (12m), com a mesma linguagem de cascata.
- **Eventos** (`/eventos` ou aba Eventos): log da nuvem por tomada.
- **Configuração** (`/setup` ou aba Config): tudo que antes era terminal —
  salvar credenciais da nuvem, buscar devices, varrer a rede, importar 7 dias
  de histórico, editar tomadas, definir cascata, testar leitura.

## Modos de conexão

| Modo | Quando usar | Recursos |
|---|---|---|
| `auto` (padrão) | dia a dia | Tenta LAN primeiro, cai pra nuvem se falhar |
| `local` | mesma Wi-Fi, sem internet | Resposta em ms, sem cota; só rede local |
| `cloud` | fora de casa | Status e comando remotos, info/functions/logs do device |

Detalhe em `FEATURES.md`. Diagnóstico: `GET /api/modes`, `GET /api/health`.

## Cascata física

Se uma tomada alimenta outra (ex: `sp desktop` ligado no `sp setup`), marque o
`parent` no `/setup`. O app calcula `W próprio = medido − filhos` e o total soma
**só as raízes**, sem dupla contagem.

## Como rodar

```powershell
pip install -r requirements.txt

# Painel web
python app.py            # http://localhost:5000

# App nativo (janela, sem navegador)
python app_flet.py
```

Do celular na mesma Wi-Fi: `http://<IP-do-PC>:5000`.

## Primeira configuração (1ª vez)

1. Crie o projeto em `https://platform.tuya.com/` (o `iot.tuya.com` antigo saiu do ar),
   assine o **IoT Core** grátis e vincule o app SmartLife em
   **Devices → Link App Account** (mesmo data center da sua conta).
2. Abra `/setup` (ou aba Config): salve Access ID/Secret → **Buscar devices** →
   **Varrer rede** para achar os IPs → ajuste nomes/versões → **Salvar tomadas**.
3. Se der `Sem permissão` no link, veja o checklist em `COMO_USAR.md`.

## Publicar o app nativo

```powershell
flet build windows      # instalador Windows
flet build apk          # Android
flet build macos | flet build linux | flet build ipa   # nas respectivas máquinas
```

Detalhes em `PUBLISH.md`.

## Estrutura

| Arquivo | Papel |
|---|---|
| `app.py` | Backend Flask: status, toggle, modos, hierarquia, histórico, setup |
| `app_flet.py` | App nativo Flet (mesmo core, mesmo visual do web) |
| `tuya_cloud.py` | Camada nuvem Tuya (status, comando, info, logs) |
| `core_setup.py` | Setup in-app (nuvem, scan, salvar devices, testar) |
| `history.py` | Persistência SQLite (`history.db`): raw 60d + agregados hora/dia p/ sempre, séries e backfill |
| `run_windows.py` | Sobe o app Flet local (mata sobras, espera a porta, confirma HTTP) |
| `templates/`, `static/` | UI web |
| `devices.json` | Suas tomadas (id/ip/key/parent) — **não commitar** |
| `FEATURES.md` | Matriz modos × funcionalidades |
| `COMO_USAR.md` | Passo a passo + troubleshooting Tuya |
| `PUBLISH.md` | Build multiplataforma |
| `AGENTS.md` | Guia para agentes de código |

Segredos (`devices.json`, `tinytuya.json`, `cloud.json`, `history.db`) estão no
`.gitignore` e nunca devem ir para o git.
