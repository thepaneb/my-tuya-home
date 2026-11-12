# Minhas Tomadas — painel local + app nativa, sem propaganda

Web: `python app.py` → http://localhost:5000 · Nativo: `flet run app_flet.py`
Tudo que era comando agora está em **/setup** (web) ou na aba **Config** (app nativo):
salvar nuvem, buscar devices, varrer rede, editar tomadas/hierarquia, testar.

Painel web que fala direto com as 4 tomadas SmartLife/Tuya na sua rede local.
Mostra liga/desliga + potência (W), tensão (V), corrente (A) e kWh quando o plug reporta.

## 1. Rodar agora (modo demo)

```powershell
pip install -r requirements.txt
python app.py
```
Abra http://localhost:5000 — vai mostrar 2 cards demo até configurar.

Do celular na mesma Wi-Fi: http://192.168.0.17:5000 (seu IP atual).

## 2. Uma única vez: pegar as chaves locais (obrigatório)

Controle local Tuya exige `id + ip + key` por tomada. A key só vem da nuvem Tuya:

1. Crie/conta em https://platform.tuya.com/ (novo portal — o iot.tuya.com antigo foi desativado) → **Cloud → Develop / Create Cloud Project** (tipo Smart Home, data center p/ Brasil: Western America ou Eastern America — teste o que lista seus devices).
2. Em **Service API / API Products**, assine grátis: `IoT Core`, `Device Status Notification`, `Smart Home Family/Scene` (nomes variam um pouco no portal novo — o essencial é IoT Core).
3. Em **Devices / Link App Account → Add App Account**: escaneie o QR com o app **SmartLife** (o mesmo das 4 tomadas).
4. Anote **Access ID** e **Access Secret** em Overview do projeto.
5. Aqui no PC:
```powershell
python -m tinytuya wizard
```
Cola ID/Secret, seleciona o projeto. Ele lista as 4 tomadas e gera `tuya-devices.json` com `id/key`.
6. Descubra os IPs:
```powershell
python scan.py
```
7. Copie `devices.example.json` → `devices.json` e preencha os 4 com `id`, `key`, `ip` reais + nome amigável. `version` deixe 3.3 (se der erro 914, use o `version` que o scan mostrou: 3.3/3.4/3.5).

> Dica: fixe o IP das tomadas no roteador (DHCP reservation 192.168.0.101-104) para não perder conexão.

### Se der "Sem permissão / No permissions" no Link App Account
É o erro mais comum, cheque nesta ordem no platform.tuya.com:
1. **Cloud → Cloud Services → IoT Core**: se estiver `Expired`, clique em **Extend Trial Period** e preencha o formulário (aprova em 1-2 dias úteis). Sem isso nada vincula.
2. **Seu projeto → Service API / Authorize**: precisa ter assinado e autorizado: `IoT Core`, `Authorization`, `Device Status Notification`, `Smart Home Scene Linkage`.
3. **Data center errado**: no SmartLife vá em `Eu → Configurações → Conta e segurança → Região`. Depois no portal, em **Devices → Link App Account**, selecione no canto superior direito o data center da sua região (Brasil geralmente = Western America ou Eastern America). Se escolher Europa/China dá erro de permissão.
4. Projeto precisa ser tipo **Smart Home** e criado depois de 2021. Se for Custom/Industry antigo, crie um novo.

## 3. Uso diário

```powershell
python app.py
```
- `/` painel, auto-atualiza a cada 5s
- `/dashboard` gráficos: potência ao longo do tempo + kWh estimado por tomada (registra a cada 30s em `history.db`)
- `/api/status` JSON p/ automações
- `POST /api/toggle/<id>` liga/desliga

Sem conta, sem nuvem, sem anúncio depois de configurado — tudo via LAN.

## Arquivos
- `app.py` — backend Flask + parser DPS (1=switch, 18/4=corrente, 19/5=potência, 20/6=tensão)
- `templates/index.html` + `static/style.css` — UI limpa
- `scan.py` — varredura LAN
- `devices.json` — suas chaves (NÃO commitar — já está no .gitignore)
