import subprocess
import re

# Get listening ports for msmdsrv
res = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
lines = res.stdout.splitlines()

# find pid of msmdsrv
res_task = subprocess.run(["tasklist", "/FI", "IMAGENAME eq msmdsrv.exe", "/FO", "CSV"], capture_output=True, text=True)
print("Tasklist:\n", res_task.stdout)

pids = []
for line in res_task.stdout.splitlines():
    if "msmdsrv.exe" in line:
        parts = [p.strip(' "') for p in line.split('","')]
        if len(parts) > 1:
            pids.append(parts[1])

print("msmdsrv PIDs:", pids)

found_ports = []
for line in lines:
    for pid in pids:
        if line.strip().endswith(pid) and "LISTENING" in line:
            parts = line.split()
            address = parts[1]
            port = address.split(":")[-1]
            found_ports.append((pid, port))
            print(f"PID {pid} is LISTENING on port {port}")

print("Found ports:", found_ports)
