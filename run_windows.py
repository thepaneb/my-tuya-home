import subprocess, sys, time, os, urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8504

try:
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app_flet*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
        capture_output=True, timeout=30)
except Exception as e:
    print("kill falhou:", e)

import socket
for _ in range(30):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", PORT))
        s.close()
        break
    except OSError:
        time.sleep(1)
else:
    print(f"porta {PORT} nao liberou")
    sys.exit(1)

subprocess.Popen([sys.executable, "-u", "app_flet.py", "--web", f"--port={PORT}"],
                 cwd=os.path.dirname(os.path.abspath(__file__)),
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f"subido na {PORT}")

for _ in range(30):
    try:
        if urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=5).status == 200:
            print("OK", PORT)
            break
    except Exception:
        time.sleep(1)
else:
    print("nao respondeu")
    sys.exit(1)
