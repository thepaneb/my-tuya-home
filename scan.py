"""Varre a rede local procurando tomadas Tuya e ajuda a montar devices.json."""
import json

try:
    import tinytuya
except ImportError:
    raise SystemExit("Instale dependencias: pip install -r requirements.txt")

print("Varrendo rede local... deixe as tomadas ligadas.")
try:
    found = tinytuya.scan(timeout=20)
except Exception as e:
    print(f"Erro no scan: {e}")
    found = None

if not found:
    print("\nNenhum dispositivo respondeu ao broadcast.")
    print("Isso é comum no Windows (firewall) ou se PC/celular estão em redes diferentes.")
    print("\nFaça assim:")
    print("1. Confirme que o PC está no mesmo Wi-Fi 2.4GHz das tomadas (não no 5GHz isolado / rede guest).")
    print("2. Libere o Python no firewall quando o Windows pedir, ou rode como teste:")
    print("   python -m tinytuya scan")
    print("3. Alternativa rápida: abra o admin do roteador (http://192.168.0.1) > clientes DHCP")
    print("   e anote os IPs das tomadas. Ou use o wizard que já puxa IP + key:")
    print("   python -m tinytuya wizard")
    print("   Depois confira em snapshot.json / tuya-raw.json / devices.json gerados.")
else:
    print(f"\nEncontrados: {len(found)} dispositivo(s)\n")
    for ip, info in found.items():
        print(f"IP={ip} ID={info.get('gwId')} versao={info.get('version')}")

print("\n--- Proximo passo ---")
print("1. Rode o assistente UMA vez para puxar as chaves da nuvem Tuya:")
print("   python -m tinytuya wizard")
print("   (vai pedir API Key/Secret da iot.tuya.com + vincular app SmartLife)")
print("2. Ele gera tinytuya.json + devices.json. Copie os 4 blocos para seu devices.json,")
print("   adicione 'name' amigavel em cada um e ajuste o IP do scan acima se preciso.")
print("3. Exemplo de entrada em devices.json: veja devices.example.json")
