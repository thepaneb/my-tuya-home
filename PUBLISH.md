# App nativa multiplataforma (Flet + Flutter)

O `app.py` (Flask) continua valendo como painel web. O `app_flet.py` é a **mesma lógica
(local/nuvem/hierarquia/histórico) numa janela nativa**, sem navegador, publicável.

## Rodar como app desktop (janela)

```powershell
pip install -r requirements.txt
flet run app_flet.py
# ou: python app_flet.py
```

Abas: **Painel** (liga/desliga, W medido/próprio, cascata) + **Dashboard** (kWh 24h + gráfico).
Seletor de modo Auto/Local/Nuvem no topo. Atualiza a cada ~8s + logger 30s em `history.db`.

## Publicar

```powershell
flet build windows      # instalador Windows (nesta máquina)
flet build linux        # (rodar no Linux)
flet build macos        # (rodar no Mac)
flet build apk          # Android (precisa Java/Android SDK — o Flet guia)
flet build ipa          # iOS (precisa Mac + Xcode)
```

Saída em `build/`. Primeiro build baixa o Flutter — demora na primeira vez, é normal.

## Notas
- Reusa `app.py`, `tuya_cloud.py`, `history.py`, `devices.json` — nada duplicado.
- Credenciais continuam locais: `devices.json` (LAN) + `tinytuya.json` (nuvem).
- Web (`python app.py`) e nativo (`flet run`) podem rodar juntos; o histórico é compartilhado.
