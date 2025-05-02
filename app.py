import socket
from flask import Flask, jsonify, request, send_from_directory, render_template_string
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

# Setup logger
logger = logging.getLogger('label_printer.config')
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler('/home/odroid/label_printer_web/app.log')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Try importing label_printer modules
try:
    from label_printer.routes import init_routes
    from label_printer.printing import print_qr_code
    from label_printer.history import ensure_history_file
    from label_printer.utils import resolve_usb_conflicts
except ImportError as e:
    logger.error(f"Failed to import label_printer modules: {str(e)}")
    init_routes = lambda x: None
    print_qr_code = lambda x: subprocess.CompletedProcess(args=['mock'], returncode=1, stdout='', stderr=str(e))
    ensure_history_file = lambda: None
    resolve_usb_conflicts = lambda: None

app = Flask(__name__)

def clear_qr_code_directory():
    """
    Delete all files in the static/qr_codes directory on startup.
    """
    logger.debug("Clearing QR code directory")
    try:
        save_dir = "/home/odroid/label_printer_web/static/qr_codes"
        os.makedirs(save_dir, exist_ok=True)
        for filename in os.listdir(save_dir):
            file_path = os.path.join(save_dir, filename)
            if os.path.isfile(file_path):
                os.unlink=file_path)
                logger.info(f"Deleted QR code file: {file_path}")
    except Exception as e:
        logger.error(f"Failed to clear QR code directory: {str(e)}")

def get_ip_address(interface):
    """
    Get the IP address of the specified network interface.
    """
    logger.debug(f"Attempting to get IP address for interface: {interface}")
    try:
        result = subprocess.run(
            ['ip', 'addr', 'show', interface],
            capture_output=True,
            text=True,
            check=True
        )
        logger.debug(f"ip addr show {interface} output: {result.stdout}")
        for line in result.stdout.splitlines():
            if 'inet ' in line:
                ip = line.strip().split()[1].split('/')[0]
                logger.debug(f"Found IP address {ip} for {interface}")
                return ip
        logger.warning(f"No IP address found for interface {interface}")
        return None
    except subprocess.CalledProcessError as e:
        logger.warning(f"Could not determine IP address for {interface}: {e}, stderr: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting IP for {interface}: {str(e)}")
        return None

def load_wifi_ap_details(hostapd_conf="/etc/hostapd/hostapd.conf", dnsmasq_conf="/etc/dnsmasq.conf"):
    """
    Load Wi-Fi AP details from hostapd.conf and cross-reference with dnsmasq.conf.
    Returns a dictionary with interface, SSID, password, security, and gateway IP.
    """
    logger.debug("Loading Wi-Fi AP details")
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
    logger.debug(f"Generated Wi-Fi QR string: {qr_string}")
    return qr_string

def save_qr_code(data, filename_prefix):
    """
    Generate a QR code with the given data, add the data text below it, and save as a PNG in static/qr_codes.
    Returns the filename (relative to static/qr_codes) or None if saving fails.
    """
    logger.debug(f"Saving QR code for data: {data}, prefix: {filename_prefix}")
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
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        qr_width, qr_height = qr_img.size
        logger.debug(f"QR code image created, size: {qr_width}x{qr_height}")

        # Try to add text below the QR code
        font_size = 20
        text_width = 0
        text_height = 0
        new_img = qr_img  # Fallback to QR code without text if text fails
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
            logger.debug("Loaded DejaVuSans.ttf font")
        except Exception:
            font = ImageFont.load_default()
            logger.warning("Failed to load DejaVuSans.ttf, using default font")

        try:
            # Use getlength for text width and getbbox for height estimation
            text_width = int(font.getlength(data))
            text_bbox = font.getbbox("A")  # Use a single character to estimate height
            text_height = text_bbox[3] - text_bbox[1]
            logger.debug(f"Text dimensions: width={text_width}, height={text_height}")

            # Create a new image with extra space for text
            new_height = qr_height + text_height + 10  # 10px padding
            new_width = max(qr_width, text_width + 20)  # 20px padding
            new_img = Image.new('RGB', (new_width, new_height), 'white')
            new_img.paste(qr_img, ((new_width - qr_width) // 2, 0))

            # Add text below the QR code
            draw = ImageDraw.Draw(new_img)
            text_x = (new_width - text_width) // 2
            text_y = qr_height + 5
            draw.text((text_x, text_y), data, font=font, fill='black')
            logger.debug(f"Added text '{data}' at position ({text_x}, {text_y})")
        except Exception as e:
            logger.warning(f"Failed to add text to QR code: {str(e)}. Saving QR code without text.")
            new_img = qr_img  # Fallback to QR code only

        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.png"
        full_path = os.path.join(save_dir, filename)

        # Save image
        new_img.save(full_path)
        logger.info(f"Saved QR code to {full_path}")
        return filename
    except Exception as e:
        logger.error(f"Failed to save QR code for {filename_prefix}: {str(e)}")
        return None

def load_default_settings():
    logger.debug("Loading default settings")
    settings_file = "/home/odroid/label_printer_web/settings.txt"
    defaults = {}
    try:
        if os.path.exists(settings_file):
            with open(settings_file, "r") as f:
                defaults = json.load(f)
            logger.debug(f"Loaded default settings: {defaults}")
        else:
            logger.debug(f"Settings file {settings_file} does not exist")
    except Exception as e:
        logger.error(f"Error loading settings.txt: {str(e)}")
    return defaults

@app.route('/qr_codes/<filename>')
def serve_qr_code(filename):
    """
    Serve QR code images from static/qr_codes directory.
    """
    try:
        logger.debug(f"Serving QR code file: {filename}")
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
        logger.debug(f"Listing QR code files in {save_dir}")
        files = [f for f in os.listdir(save_dir) if f.endswith('.png')]
        files.sort(reverse=True)  # Newest first
        logger.debug(f"Found {len(files)} QR code files: {files}")
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
    try:
        # Load Wi-Fi details
        wifi_details = load_wifi_ap_details()
        wifi_interface = wifi_details["interface"]
        ethernet_interface = "eth0"
        logger.debug(f"Wi-Fi interface: {wifi_interface}, Ethernet interface: {ethernet_interface}")

        # Get IP addresses
        wifi_ip = get_ip_address(wifi_interface) or wifi_details["gateway_ip"]
        ethernet_ip = get_ip_address(ethernet_interface)
        port = app.config.get("PORT", 5001)
        logger.debug(f"Wi-Fi IP: {wifi_ip}, Ethernet IP: {ethernet_ip}, Port: {port}")

        # Prepare addresses
        addresses = []
        if wifi_ip:
            addresses.append(("wifi", wifi_ip, f"http://{wifi_ip}:{port}"))
        else:
            logger.warning("No Wi-Fi IP detected, using fallback gateway IP")
            addresses.append(("wifi", wifi_details["gateway_ip"], f"http://{wifi_details['gateway_ip']}:{port}"))
        if ethernet_ip:
            addresses.append(("ethernet", ethernet_ip, f"http://{ethernet_ip}:{port}"))
        else:
            logger.warning("No Ethernet IP detected")
        logger.debug(f"Addresses to process: {addresses}")

        ip_file = "/home/odroid/label_printer_web/ip.txt"
        previous_addresses = {}
        if os.path.exists(ip_file):
            try:
                with open(ip_file, "r") as f:
                    previous_addresses = json.load(f)
                logger.debug(f"Loaded previous addresses from {ip_file}: {previous_addresses}")
            except Exception as e:
                logger.error(f"Error reading {ip_file}: {e}")
                previous_addresses = {}
        else:
            logger.info(f"{ip_file} does not exist, forcing QR code generation")

        current_addresses = {interface: url for interface, _, url in addresses}
        logger.debug(f"Current addresses: {current_addresses}")

        # Force QR code generation if ip.txt is missing or addresses changed
        if not os.path.exists(ip_file) or previous_addresses != current_addresses or not addresses:
            logger.info(f"Addresses changed, ip.txt missing, or no addresses detected. Previous: {previous_addresses}, Current: {current_addresses}. Generating QR codes.")
            # Save the new addresses
            try:
                with open(ip_file, "w") as f:
                    json.dump(current_addresses, f)
                logger.debug(f"Saved current addresses to {ip_file}")
            except Exception as e:
                logger.error(f"Error writing to {ip_file}: {e}")

            # Ensure at least Wi-Fi QR codes are generated with fallback
            if not addresses:
                logger.warning("No valid addresses detected, generating Wi-Fi QR codes with fallback IP")
                addresses.append(("wifi", wifi_details["gateway_ip"], f"http://{wifi_details['gateway_ip']}:{port}"))

            # Process each interface
            for interface, ip, url in addresses:
                # Save and print URL QR code
                logger.debug(f"Generating URL QR code for {interface} with URL: {url}")
                url_qr_filename = save_qr_code(url, f"{interface}_url_qr")
                if url_qr_filename:
                    logger.info(f"{interface.capitalize()} URL QR code saved as {url_qr_filename}, accessible at /qr_codes/{url_qr_filename}")
                else:
                    logger.error(f"Failed to save URL QR code for {interface}")
                for attempt in range(3):
                    try:
                        result = print_qr_code(url)
                        if "Printing was successful" in result.stdout:
                            logger.info(f"{interface.capitalize()} URL QR code printed successfully")
                            break
                        else:
                            logger.error(f"Failed to print {interface} URL QR code (attempt {attempt + 1}/3): {result.stderr}")
                            resolve_usb_conflicts()
                            time.sleep(2)
                    except Exception as e:
                        logger.error(f"Error printing {interface} URL QR code (attempt {attempt + 1}/3): {e}")
                        resolve_usb_conflicts()
                        time.sleep(2)
                else:
                    logger.error(f"Failed to print {interface} URL QR code after 3 attempts")

                # Save and print Wi-Fi QR code (only for Wi-Fi interface)
                if interface == "wifi":
                    wifi_qr_string = generate_wifi_qr_string(wifi_details)
                    logger.debug(f"Generating Wi-Fi QR code with string: {wifi_qr_string}")
                    wifi_qr_filename = save_qr_code(wifi_qr_string, "wifi_qr")
                    if wifi_qr_filename:
                        logger.info(f"Wi-Fi QR code saved as {wifi_qr_filename}, accessible at /qr_codes/{wifi_qr_filename}")
                    else:
                        logger.error("Failed to save Wi-Fi QR code")
                    for attempt in range(3):
                        try:
                            result = print_qr_code(wifi_qr_string)
                            if "Printing was successful" in result.stdout:
                                logger.info("Wi-Fi QR code printed successfully")
                                break
                            else:
                                logger.error(f"Failed to print Wi-Fi QR code (attempt {attempt + 1}/3): {result.stderr}")
                                resolve_usb_conflicts()
                                time.sleep(2)
                        except Exception as e:
                            logger.error(f"Error printing Wi-Fi QR code (attempt {attempt + 1}/3): {e}")
                            resolve_usb_conflicts()
                            time.sleep(2)
                    else:
                        logger.error("Failed to print Wi-Fi QR code after 3 attempts")
        else:
            logger.debug("Addresses unchanged, no QR codes generated")
    except Exception as e:
        logger.error(f"Unexpected error in check_and_update_ip_port: {str(e)}")

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
    logger.debug("Processing save_template request")
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
            logger.debug(f"Template config: {config}")
            # Validate length_mm
            if 'length_mm' in config:
                if not isinstance(config['length_mm'], (int, float)) or config['length_mm'] <= 0:
                    logger.warning(f"Invalid length_mm in config: {config['length_mm']}, setting to default 100")
                    config['length_mm'] = 100
            else:
                logger.warning("length_mm not found in template config, setting to default 100")
                config['length_mm'] = 100
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
            if template_preview and template_preview.startswith('data:image/png;base64,'):
                base64_string = template_preview.split(',')[1]
                img_data = base64.b64decode(base64_string)
                img = Image.open(BytesIO(img_data))
                img.save(preview_path, 'PNG')
            else:
                logger.warning("Invalid or missing preview image, skipping preview save")
                preview_path = ''
        except Exception as e:
            logger.error(f"Error saving preview image: {str(e)}")
            return jsonify({'message': 'Error saving preview image'}), 500

        template = {
            'name': template_name,
            'config': config,
            'preview_image': f"{template_name}.png" if os.path.exists(preview_path) else '',
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
        logger.debug("Executing clear_qr_code_directory")
        clear_qr_code_directory()

        logger.debug("Executing ensure_history_file")
        ensure_history_file()

        logger.debug("Executing resolve_usb_conflicts")
        resolve_usb_conflicts()

        logger.debug("Executing load_default_settings")
        defaults = load_default_settings()
        app.config['DEFAULTS'] = defaults

        logger.debug("Executing check_and_update_ip_port")
        check_and_update_ip_port()

        logger.debug("Executing init_routes")
        init_routes(app)

        logger.debug("Attempting to import watch_print_directory")
        try:
            from watch_print_dir import watch_print_directory
            logger.info("Successfully imported watch_print_directory")
        except ImportError as e:
            logger.error(f"Failed to import watch_print_directory: {str(e)}")
            watch_print_directory = None

        if watch_print_directory:
            try:
                logger.debug("Starting directory watcher thread")
                watcher_thread = threading.Thread(target=watch_print_directory, daemon=True)
                watcher_thread.start()
                logger.info("Started directory watcher thread")
            except Exception as e:
                logger.error(f"Failed to start directory watcher: {str(e)}")

        logger.debug("Starting Flask app.run")
        app.run(host='0.0.0.0', port=5001)
    except Exception as e:
        logger.error(f"Fatal error starting Flask application: {str(e)}")
        raise
