import socket
from flask import Flask, jsonify, request, send_from_directory, render_template_string
from label_printer.routes import init_routes
from label_printer.printing import print_qr_code
from label_printer.history import ensure_history_file
from label_printer.utils import resolve_usb_conflicts
from label_printer.config import logger
import os
import json
import time
import threading
import subprocess
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import qrcode
from datetime import datetime
import logging

# Ensure logger writes to app.log
file_handler = logging.FileHandler('/home/odroid/label_printer_web/app.log')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

app = Flask(__name__)

def clear_qr_code_directory():
    """
    Delete all files in the static/qr_codes directory on startup.
    """
    try:
        save_dir = "/home/odroid/label_printer_web/static/qr_codes"
        os.makedirs(save_dir, exist_ok=True)
        for filename in os.listdir(save_dir):
            file_path = os.path.join(save_dir, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
                logger.info(f"Deleted QR code file: {file_path}")
    except Exception as e:
        logger.error(f"Failed to clear QR code directory: {str(e)}")

def get_ip_address(interface):
    """
    Get the IP address of the specified network interface.
    """
    try:
        result = subprocess.run(
            ['ip', 'addr', 'show', interface],
            capture_output=True,
            text=True,
            check=True
        )
        for line in result.stdout.splitlines():
            if 'inet ' in line:
                ip = line.strip().split()[1].split('/')[0]
                return ip
        logger.error(f"No IP address found for interface {interface}")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Could not determine IP address for {interface}: {e}")
        return None

def load_wifi_ap_details(hostapd_conf="/etc/hostapd/hostapd.conf", dnsmasq_conf="/etc/dnsmasq.conf"):
    """
    Load Wi-Fi AP details from hostapd.conf and cross-reference with dnsmasq.conf.
    Returns a dictionary with interface, SSID, password, security, and gateway IP.
    """
    wifi_details = {
        "interface": "wlan0",
        "ssid": "LabelPrinterAP",
        "password": "",
        "security": "nopass",
        "gateway_ip": "192.168.4.1"
    }

    try:
        with open(hostapd_conf, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    if key == "interface":
                        wifi_details["interface"] = value
                    elif key == "ssid":
                        wifi_details["ssid"] = value
                    elif key == "wpa_passphrase":
                        wifi_details["password"] = value
                    elif key == "wpa":
                        wifi_details["security"] = "WPA" if value in ["1", "2"] else "nopass"
        logger.debug(f"Loaded hostapd.conf details: {wifi_details}")
    except Exception as e:
        logger.error(f"Error reading {hostapd_conf}: {e}. Using fallback Wi-Fi details.")

    try:
        with open(dnsmasq_conf, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("dhcp-range="):
                    parts = line.split("=")[1].split(",")
                    if len(parts) >= 3:
                        gateway_ip = parts[0].rsplit(".", 1)[0] + ".1"
                        wifi_details["gateway_ip"] = gateway_ip
        logger.debug(f"Loaded dnsmasq.conf gateway IP: {wifi_details['gateway_ip']}")
    except Exception as e:
        logger.error(f"Error reading {dnsmasq_conf}: {e}. Using fallback gateway IP.")

    return wifi_details

def generate_wifi_qr_string(wifi_details):
    """
    Generate a QR code string for Wi-Fi connection.
    Format: WIFI:S:<SSID>;T:<security>;P:<password>;;
    """
    ssid = wifi_details["ssid"]
    security = wifi_details["security"]
    password = wifi_details["password"] if security != "nopass" else ""
    qr_string = f"WIFI:S:{ssid};T:{security};P:{password};;"
    return qr_string

def save_qr_code(data, filename_prefix):
    """
    Generate a QR code with the given data, add the data text below it, and save as a PNG in static/qr_codes.
    Returns the filename (relative to static/qr_codes) or None if saving fails.
    """
    try:
        # Define save directory
        save_dir = "/home/odroid/label_printer_web/static/qr_codes"
        os.makedirs(save_dir, exist_ok=True)

        # Check write permissions
        if not os.access(save_dir, os.W_OK):
            logger.error(f"No write permission for {save_dir}")
            return None

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # Create QR code image
        qr_img = qr.make_image(fill_color="black", back_color="white")

        # Calculate text size and create a new image with space for text
        font_size = 20
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        text_bbox = font.getbbox(data)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # Create a new image with extra space for text
        qr_width, qr_height = qr_img.size
        new_height = qr_height + text_height + 10  # 10px padding
        new_width = max(qr_width, text_width + 20)  # 20px padding
        new_img = Image.new('RGB', (new_width, new_height), 'white')
        new_img.paste(qr_img, ((new_width - qr_width) // 2, 0))

        # Add text below the QR code
        draw = ImageDraw.Draw(new_img)
        text_x = (new_width - text_width) // 2
        text_y = qr_height + 5
        draw.text((text_x, text_y), data, font=font, fill='black')

        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.png"
        full_path = os.path.join(save_dir, filename)

        # Save image
        new_img.save(full_path)
        logger.info(f"Saved QR code with text to {full_path}")
        return filename
    except Exception as e:
        logger.error(f"Failed to save QR code for {filename_prefix}: {str(e)}")
        return None

def load_default_settings():
    settings_file = "/home/odroid/label_printer_web/settings.txt"
    defaults = {}
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r") as f:
                defaults = json.load(f)
            logger.debug(f"Loaded default settings: {defaults}")
        except Exception as e:
            logger.error(f"Error loading settings.txt: {e}")
    return defaults

@app.route('/qr_codes/<filename>')
def serve_qr_code(filename):
    """
    Serve QR code images from static/qr_codes directory.
    """
    try:
        return send_from_directory('static/qr_codes', filename)
    except Exception as e:
        logger.error(f"Error serving QR code {filename}: {str(e)}")
        return jsonify({'message': f'QR code not found: {str(e)}'}), 404

@app.route('/qr_codes')
def list_qr_codes():
    """
    Display a listing of QR code files in the static/qr_codes directory.
    """
    try:
        save_dir = "/home/odroid/label_printer_web/static/qr_codes"
        files = [f for f in os.listdir(save_dir) if f.endswith('.png')]
        files.sort(reverse=True)  # Newest first
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>QR Codes</title>
        </head>
        <body>
            <h1>QR Code Files</h1>
            <ul>
                {% for file in files %}
                    <li><a href="/qr_codes/{{ file }}">{{ file }}</a></li>
                {% endfor %}
            </ul>
        </body>
        </html>
        """
        return render_template_string(html, files=files)
    except Exception as e:
        logger.error(f"Error listing QR codes: {str(e)}")
        return jsonify({'message': f'Error listing QR codes: {str(e)}'}), 500

def check_and_update_ip_port():
    logger.debug("Entering check_and_update_ip_port")
    # Load Wi-Fi details
    wifi_details = load_wifi_ap_details()
    wifi_interface = wifi_details["interface"]
    ethernet_interface = "eth0"  # Hardcoded for Ethernet

    # Get IP addresses
    wifi_ip = get_ip_address(wifi_interface) or wifi_details["gateway_ip"]
    ethernet_ip = get_ip_address(ethernet_interface)
    port = app.config.get("PORT", 5001)

    # Prepare addresses
    addresses = []
    if wifi_ip:
        addresses.append(("wifi", wifi_ip, f"http://{wifi_ip}:{port}"))
    if ethernet_ip:
        addresses.append(("ethernet", ethernet_ip, f"http://{ethernet_ip}:{port}"))

    ip_file = "/home/odroid/label_printer_web/ip.txt"
    previous_addresses = {}
    if os.path.exists(ip_file):
        try:
            with open(ip_file, "r") as f:
                previous_addresses = json.load(f)
        except Exception as e:
            logger.error(f"Error reading {ip_file}: {e}")

    current_addresses = {interface: url for interface, _, url in addresses}
    if previous_addresses != current_addresses:
        logger.info(f"Addresses changed from {previous_addresses} to {current_addresses}. Printing new QR codes.")
        # Save the new addresses
        try:
            with open(ip_file, "w") as f:
                json.dump(current_addresses, f)
        except Exception as e:
            logger.error(f"Error writing to {ip_file}: {e}")

        # Process each interface
        for interface, ip, url in addresses:
            # Save and print URL QR code
            url_qr_filename = save_qr_code(url, f"{interface}_url_qr")
            if url_qr_filename:
                logger.info(f"{interface.capitalize()} URL QR code saved as {url_qr_filename}, accessible at /qr_codes/{url_qr_filename}")
            for attempt in range(3):
                try:
                    result = print_qr_code(url)
                    if "Printing was successful" in result.stdout:
                        logger.info(f"{interface.capitalize()} URL QR code printed successfully.")
                        break
                    else:
                        logger.error(f"Failed to print {interface} URL QR code (attempt {attempt + 1}/3): {result.stderr}")
                        resolve_usb_conflicts()
                        time.sleep(2)
                except Exception as e:
                    logger.error(f"Error printing {interface} URL QR code at startup (attempt {attempt + 1}/3): {e}")
                    resolve_usb_conflicts()
                    time.sleep(2)
            else:
                logger.error(f"Failed to print {interface} URL QR code after 3 attempts.")

            # Save and print Wi-Fi QR code (only for Wi-Fi interface)
            if interface == "wifi":
                wifi_qr_string = generate_wifi_qr_string(wifi_details)
                wifi_qr_filename = save_qr_code(wifi_qr_string, "wifi_qr")
                if wifi_qr_filename:
                    logger.info(f"Wi-Fi QR code saved as {wifi_qr_filename}, accessible at /qr_codes/{wifi_qr_filename}")
                for attempt in range(3):
                    try:
                        result = print_qr_code(wifi_qr_string)
                        if "Printing was successful" in result.stdout:
                            logger.info("Wi-Fi QR code printed successfully.")
                            break
                        else:
                            logger.error(f"Failed to print Wi-Fi QR code (attempt {attempt + 1}/3): {result.stderr}")
                            resolve_usb_conflicts()
                            time.sleep(2)
                    except Exception as e:
                        logger.error(f"Error printing Wi-Fi QR code at startup (attempt {attempt + 1}/3): {e}")
                        resolve_usb_conflicts()
                        time.sleep(2)
                else:
                    logger.error("Failed to print Wi-Fi QR code after 3 attempts.")
    else:
        logger.debug("Addresses unchanged, no QR codes printed.")

@app.route('/restart', methods=['POST'])
def restart():
    logger.info(f"Restart requested from {request.remote_addr}")
    try:
        logger.debug("Starting restart endpoint")
        time.sleep(1)
        logger.debug("Initiating systemctl restart label-printer.service")
        process = subprocess.Popen(
            ['sudo', '/bin/systemctl', 'restart', 'label-printer.service'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.debug(f"Started systemctl restart with PID {process.pid}")
        return jsonify({
            'message': 'Webserver restart initiated. Please wait a few seconds and refresh.',
            'reload': True,
            'redirect': '/'
        })
    except Exception as e:
        logger.error(f"Failed to initiate server restart: {str(e)}")
        return jsonify({'message': f'Failed to initiate server restart: {str(e)}'}), 500

@app.route('/printer_status', methods=['GET'])
def printer_status():
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True)
        online = '04f9:209c' in result.stdout
        logger.debug(f"Printer status check: {'online' if online else 'offline'}")
        return jsonify({'online': online})
    except Exception as e:
        logger.error(f"Error checking printer status: {str(e)}")
        return jsonify({'online': False}), 500

@app.route('/save_template', methods=['POST'])
def save_template():
    try:
        template_name = request.form.get('template_name')
        template_config = request.form.get('template_config')
        template_preview = request.form.get('template_preview')

        if not template_name or not template_config:
            logger.error("Missing template name or configuration")
            return jsonify({'message': 'Template name and configuration are required'}), 400

        import re
        if not re.match(r'^[a-zA-Z0-9\s_-]+$', template_name):
            logger.error(f"Invalid template name: {template_name}")
            return jsonify({'message': 'Template name can only contain letters, numbers, underscores, hyphens, and spaces'}), 400

        template_name = re.sub(r'\s+', ' ', template_name.strip())

        try:
            config = json.loads(template_config)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid template config JSON: {str(e)}")
            return jsonify({'message': 'Invalid template configuration'}), 400

        labels_dir = "/home/odroid/label_printer_web/labels"
        os.makedirs(labels_dir, exist_ok=True)

        json_path = os.path.join(labels_dir, f"{template_name}.json")
        if os.path.exists(json_path):
            logger.error(f"Template '{template_name}' already exists")
            return jsonify({'message': f"Template '{template_name}' already exists"}), 400

        preview_path = os.path.join(labels_dir, f"{template_name}.png")
        try:
            if template_preview.startswith('data:image/png;base64,'):
                base64_string = template_preview.split(',')[1]
                img_data = base64.b64decode(base64_string)
                img = Image.open(BytesIO(img_data))
                img.save(preview_path, 'PNG')
            else:
                logger.error("Invalid preview image format")
                return jsonify({'message': 'Invalid preview image format'}), 400
        except Exception as e:
            logger.error(f"Error saving preview image: {str(e)}")
            return jsonify({'message': 'Error saving preview image'}), 500

        template = {
            'name': template_name,
            'config': config,
            'preview_image': f"{template_name}.png",
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        try:
            with open(json_path, "w") as f:
                json.dump(template, f, indent=2)
            logger.info(f"Saved template '{template_name}' to {json_path}")
            return jsonify({'message': f"Template '{template_name}' saved successfully"}), 200
        except Exception as e:
            logger.error(f"Error saving template JSON: {str(e)}")
            if os.path.exists(preview_path):
                os.remove(preview_path)
            return jsonify({'message': 'Error saving template'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in save_template: {str(e)}")
        return jsonify({'message': f'Unexpected error: {str(e)}'}), 500

@app.route('/get_templates', methods=['GET'])
def get_templates():
    try:
        labels_dir = "/home/odroid/label_printer_web/labels"
        templates = []

        if not os.path.exists(labels_dir):
            logger.debug("Labels directory does not exist")
            return jsonify({'templates': []}), 200

        for filename in os.listdir(labels_dir):
            if filename.endswith('.json'):
                json_path = os.path.join(labels_dir, filename)
                try:
                    with open(json_path, 'r') as f:
                        template = json.load(f)
                    preview_path = os.path.join(labels_dir, template.get('preview_image', ''))
                    preview_base64 = ''
                    if os.path.exists(preview_path):
                        with open(preview_path, 'rb') as img_file:
                            preview_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                    templates.append({
                        'name': template['name'],
                        'config': template['config'],
                        'preview_image': f'data:image/png;base64,{preview_base64}' if preview_base64 else ''
                    })
                except Exception as e:
                    logger.error(f"Error reading template {filename}: {str(e)}")
                    continue

        templates.sort(key=lambda x: x['name'].lower())
        logger.debug(f"Retrieved {len(templates)} templates")
        return jsonify({'templates': templates}), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_templates: {str(e)}")
        return jsonify({'message': f'Unexpected error: {str(e)}'}), 500

@app.route('/delete_template', methods=['POST'])
def delete_template():
    try:
        template_name = request.form.get('template_name')
        if not template_name:
            logger.error("Missing template name")
            return jsonify({'message': 'Template name is required'}), 400

        import re
        if not re.match(r'^[a-zA-Z0-9\s_-]+$', template_name):
            logger.error(f"Invalid template name: {template_name}")
            return jsonify({'message': 'Template name can only contain letters, numbers, underscores, hyphens, and spaces'}), 400

        template_name = re.sub(r'\s+', ' ', template_name.strip())

        labels_dir = "/home/odroid/label_printer_web/labels"
        json_path = os.path.join(labels_dir, f"{template_name}.json")
        preview_path = os.path.join(labels_dir, f"{template_name}.png")

        if not os.path.exists(json_path):
            logger.error(f"Template '{template_name}' does not exist")
            return jsonify({'message': f"Template '{template_name}' does not exist"}), 404

        try:
            os.remove(json_path)
            if os.path.exists(preview_path):
                os.remove(preview_path)
            logger.info(f"Deleted template '{template_name}'")
            return jsonify({'message': f"Template '{template_name}' deleted successfully"}), 200
        except Exception as e:
            logger.error(f"Error deleting template '{template_name}': {str(e)}")
            return jsonify({'message': f"Error deleting template: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error in delete_template: {str(e)}")
        return jsonify({'message': f'Unexpected error: {str(e)}'}), 500

@app.route('/update_codebase', methods=['POST'])
def update_codebase():
    logger.info(f"Update codebase requested from {request.remote_addr}")
    try:
        logger.debug("Starting update_codebase endpoint")
        codebase_dir = "/home/odroid/label_printer_web"
        logger.debug(f"Checking codebase directory: {codebase_dir}")
        if not os.path.exists(codebase_dir):
            logger.error(f"Codebase directory {codebase_dir} does not exist")
            return jsonify({'message': f'Codebase directory {codebase_dir} does not exist'}), 500

        git_dir = os.path.join(codebase_dir, ".git")
        logger.debug(f"Checking .git directory: {git_dir}")
        if not os.path.exists(git_dir):
            logger.error(f"Git repository not found at {git_dir}")
            return jsonify({'message': 'Git repository not initialized in codebase directory'}), 500

        logger.debug("Checking git installation")
        try:
            subprocess.run(['git', '--version'], capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error(f"Git is not installed or not accessible: {str(e)}")
            return jsonify({'message': 'Git is not installed on the server'}), 500

        logger.debug("Executing git pull origin main")
        env = os.environ.copy()
        env['HOME'] = '/home/odroid'
        try:
            result = subprocess.run(
                ['git', '-C', codebase_dir, 'pull', 'origin', 'main'],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
                env=env
            )
            logger.info(f"Git pull stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"Git pull stderr: {result.stderr}")
        except subprocess.TimeoutExpired as e:
            logger.error(f"Git pull timed out after 30 seconds: stdout={e.stdout}, stderr={e.stderr}")
            return jsonify({'message': 'Git pull operation timed out'}), 500
        except subprocess.CalledProcessError as e:
            logger.error(f"Git pull failed: stdout={e.stdout}, stderr={e.stderr}")
            return jsonify({'message': f'Failed to update codebase: {e.stderr}'}), 500
        except Exception as e:
            logger.error(f"Unexpected error during git pull: {str(e)}")
            return jsonify({'message': f'Unexpected error during git pull: {str(e)}'}), 500

        logger.debug("Initiating systemctl restart label-printer.service")
        try:
            process = subprocess.Popen(
                ['sudo', '/bin/systemctl', 'restart', 'label-printer.service'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            logger.debug(f"Started systemctl restart with PID {process.pid}")
            return jsonify({
                'message': 'Codebase update initiated. Server is restarting. Please wait a few seconds and refresh.',
                'reload': True,
                'redirect': '/'
            })
        except Exception as e:
            logger.error(f"Failed to initiate server restart: {str(e)}")
            return jsonify({'message': f'Codebase updated, but failed to initiate server restart: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in update_codebase: {str(e)}")
        return jsonify({'message': f'Unexpected error: {str(e)}'}), 500
        
if __name__ == "__main__":
    logger.info("Starting Flask application")
    try:
        # Clear QR code directory on startup
        clear_qr_code_directory()

        ensure_history_file()
        resolve_usb_conflicts()
        defaults = load_default_settings()
        app.config['DEFAULTS'] = defaults
        check_and_update_ip_port()
        init_routes(app)
        
        try:
            from watch_print_dir import watch_print_directory
            logger.info("Successfully imported watch_print_directory")
        except ImportError as e:
            logger.error(f"Failed to import watch_print_directory: {str(e)}")
            watch_print_directory = None

        if watch_print_directory:
            try:
                watcher_thread = threading.Thread(target=watch_print_directory, daemon=True)
                watcher_thread.start()
                logger.info("Started directory watcher thread")
            except Exception as e:
                logger.error(f"Failed to start directory watcher: {str(e)}")
        
        app.run(host='0.0.0.0', port=5001)
    except Exception as e:
        logger.error(f"Fatal error starting Flask application: {str(e)}")
        raise
