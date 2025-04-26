#!/bin/bash

# Install script for ameriDroid-Label-Server on ODROID-C4 with Ubuntu 20.04
# Installs prerequisites system-wide, clones GitHub repo, configures WiFi access point and Ethernet,
# fixes ODROID repository, and sets up systemd service. Runs natively without a virtual environment.

# Configuration variables
REPO_URL="https://github.com/Respectech/ameriDroid-Label-Server.git"
INSTALL_DIR="/home/odroid/label_printer_web"
PYTHON_EXEC="/usr/bin/python3.8"
SERVICE_NAME="label-printer"
LOG_FILE="/home/odroid/install_label_printer.log"
WIFI_SSID="LabelPrinter"
WIFI_PASS="printer123"
WIFI_IFACE="wlan0"
WIFI_IP="192.168.4.1"

# Ensure script is run with sudo
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (use sudo)" | tee -a "$LOG_FILE"
    exit 1
fi

# Redirect output to log file and console
exec > >(tee -a "$LOG_FILE") 2>&1
echo "Starting installation at $(date)"

# Fix ODROID repository configuration
echo "Fixing ODROID repository configuration..."
# Remove bionic references and backup files
for file in /etc/apt/sources.list.d/*.list; do
    if [ -f "$file" ]; then
        if grep -q "bionic" "$file"; then
            sudo rm "$file"
            echo "Removed $file containing bionic" | tee -a "$LOG_FILE"
        fi
    fi
done
for file in /etc/apt/sources.list.d/*.list.save; do
    if [ -f "$file" ]; then
        sudo rm "$file"
        echo "Removed backup file $file" | tee -a "$LOG_FILE"
    fi
done
# Ensure odroid.list is correct
echo "deb http://deb.odroid.in/c4 focal main" | sudo tee /etc/apt/sources.list.d/odroid.list
echo "Created/updated /etc/apt/sources.list.d/odroid.list" | tee -a "$LOG_FILE"

# Add Hardkernel PPA with multiple keyserver attempts
echo "Adding Hardkernel PPA..."
echo "deb http://ppa.launchpad.net/hardkernel/ppa/ubuntu focal main" | sudo tee /etc/apt/sources.list.d/hardkernel-ubuntu-ppa-focal.list
KEY_SERVERS=("keyserver.ubuntu.com" "keys.openpgp.org" "pgp.mit.edu" "hkp://pool.sks-keyservers.net")
KEY_ID="7A20836B"
KEY_IMPORTED=false
for server in "${KEY_SERVERS[@]}"; do
    echo "Trying keyserver $server for key $KEY_ID..." | tee -a "$LOG_FILE"
    if sudo apt-key adv --keyserver "$server" --recv-keys "$KEY_ID"; then
        KEY_IMPORTED=true
        break
    fi
    echo "Failed to fetch key from $server" | tee -a "$LOG_FILE"
    sleep 2
done
if ! $KEY_IMPORTED; then
    echo "Warning: Failed to add Hardkernel PPA key, using trusted repository as fallback" | tee -a "$LOG_FILE"
    echo "deb [trusted=yes] http://ppa.launchpad.net/hardkernel/ppa/ubuntu focal main" | sudo tee /etc/apt/sources.list.d/hardkernel-ubuntu-ppa-focal.list
fi

# Update package lists
echo "Updating system packages..."
apt update -y || {
    echo "Failed to update packages" | tee -a "$LOG_FILE"
    exit 1
}
apt full-upgrade -y || {
    echo "Failed to upgrade packages" | tee -a "$LOG_FILE"
    exit 1
}

# Install system dependencies
echo "Installing system dependencies..."
apt install -y \
    python3.8 python3.8-dev python3-pip \
    git \
    libusb-1.0-0-dev \
    fontconfig \
    imagemagick \
    libfreetype6-dev libjpeg-dev zlib1g-dev \
    python3-usb \
    python3-packaging \
    hostapd \
    dnsmasq \
    || {
    echo "Failed to install system dependencies, attempting pip fallback for pyusb..." | tee -a "$LOG_FILE"
    "$PYTHON_EXEC" -m pip install pyusb || {
        echo "Failed to install pyusb via pip" | tee -a "$LOG_FILE"
        exit 1
    }
}

# Upgrade pip system-wide
echo "Upgrading pip..."
"$PYTHON_EXEC" -m pip install --upgrade pip || {
    echo "Failed to upgrade pip" | tee -a "$LOG_FILE"
    exit 1
}

# Create installation directory
echo "Creating installation directory at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR" || {
    echo "Failed to create directory $INSTALL_DIR" | tee -a "$LOG_FILE"
    exit 1
}
chown odroid:odroid "$INSTALL_DIR"

# Clone the GitHub repository
echo "Cloning repository from $REPO_URL..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Repository already exists, pulling latest changes..."
    cd "$INSTALL_DIR" && sudo -u odroid git pull || {
        echo "Failed to pull repository" | tee -a "$LOG_FILE"
        exit 1
    }
else
    sudo -u odroid git clone "$REPO_URL" "$INSTALL_DIR" || {
        echo "Failed to clone repository" | tee -a "$LOG_FILE"
        exit 1
    }
fi

# Install Python dependencies system-wide
echo "Installing Python dependencies from requirements.txt..."
cd "$INSTALL_DIR"
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    "$PYTHON_EXEC" -m pip install -r "$INSTALL_DIR/requirements.txt" || {
        echo "Failed to install Python packages from requirements.txt" | tee -a "$LOG_FILE"
        exit 1
    }
else
    echo "requirements.txt not found, installing core packages..."
    "$PYTHON_EXEC" -m pip install \
        brother_ql \
        Flask \
        Pillow \
        qrcode \
        PyPDF2 \
        fontconfig \
        || {
        echo "Failed to install core Python packages" | tee -a "$LOG_FILE"
        exit 1
    }
fi

# Configure WiFi access point
echo "Configuring WiFi access point on $WIFI_IFACE..."
# Set static IP for wlan0
mkdir -p /etc/network/interfaces.d
cat > /etc/network/interfaces.d/$WIFI_IFACE <<EOF
auto $WIFI_IFACE
iface $WIFI_IFACE inet static
    address $WIFI_IP
    netmask 255.255.255.0
EOF

# Ensure eth0 uses DHCP
cat > /etc/network/interfaces.d/eth0 <<EOF
auto eth0
iface eth0 inet dhcp
EOF

# Configure hostapd
cat > /etc/hostapd/hostapd.conf <<EOF
interface=$WIFI_IFACE
driver=nl80211
ssid=$WIFI_SSID
hw_mode=g
channel=6
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$WIFI_PASS
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
echo "DAEMON_CONF=/etc/hostapd/hostapd.conf" | sudo tee -a /etc/default/hostapd

# Configure dnsmasq
cat > /etc/dnsmasq.conf <<EOF
interface=$WIFI_IFACE
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,12h
EOF

# Configure Network Manager to ignore wlan0
if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
    echo "Configuring Network Manager to ignore $WIFI_IFACE..."
    cat > /etc/NetworkManager/NetworkManager.conf <<EOF
[main]
plugins=ifupdown,keyfile

[ifupdown]
managed=false

[keyfile]
unmanaged-devices=interface-name:$WIFI_IFACE
EOF
    systemctl restart NetworkManager || {
        echo "Failed to restart NetworkManager" | tee -a "$LOG_FILE"
        exit 1
    }
fi

# Disable IP forwarding
echo "Disabling IP forwarding for standalone WiFi AP..."
sysctl -w net.ipv4.ip_forward=0

# Enable and start hostapd and dnsmasq
echo "Enabling and starting hostapd and dnsmasq services..."
systemctl unmask hostapd
systemctl enable hostapd dnsmasq || {
    echo "Failed to enable hostapd or dnsmasq" | tee -a "$LOG_FILE"
    exit 1
}
systemctl start hostapd dnsmasq || {
    echo "Failed to start hostapd or dnsmasq" | tee -a "$LOG_FILE"
    exit 1
}

# Create systemd service file
echo "Creating systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=ameriDroid Label Printer Web Interface
After=network.target

[Service]
User=odroid
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_EXEC $INSTALL_DIR/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
echo "Enabling and starting $SERVICE_NAME service..."
systemctl enable "$SERVICE_NAME" || {
    echo "Failed to enable service" | tee -a "$LOG_FILE"
    exit 1
}
systemctl start "$SERVICE_NAME" || {
    echo "Failed to start service" | tee -a "$LOG_FILE"
    exit 1
}

# Set permissions for printer USB access
echo "Configuring USB permissions for Brother QL-810W..."
usermod -a -G lp odroid
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="04f9", ATTR{idProduct}=="209c", MODE="0666", GROUP="lp"' > /etc/udev/rules.d/99-brother-ql810w.rules
udevadm control --reload-rules && udevadm trigger || {
    echo "Failed to configure USB permissions" | tee -a "$LOG_FILE"
    exit 1
}

# Verify installation
echo "Verifying installation..."
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Service $SERVICE_NAME is running" | tee -a "$LOG_FILE"
else
    echo "Service $SERVICE_NAME failed to start, check logs with: journalctl -u $SERVICE_NAME" | tee -a "$LOG_FILE"
    exit 1
fi
if systemctl is-active --quiet hostapd && systemctl is-active --quiet dnsmasq; then
    echo "WiFi access point services are running" | tee -a "$LOG_FILE"
else
    echo "WiFi access point services failed to start, check logs with: journalctl -u hostapd -u dnsmasq" | tee -a "$LOG_FILE"
    exit 1
fi
if ip addr show eth0 | grep -q "inet "; then
    echo "Ethernet interface eth0 is configured" | tee -a "$LOG_FILE"
else
    echo "Ethernet interface eth0 not configured, check network settings" | tee -a "$LOG_FILE"
fi

# Print completion message
echo "Installation completed successfully at $(date)" | tee -a "$LOG_FILE"
echo "Connect your phone to WiFi network '$WIFI_SSID' with password '$WIFI_PASS' and access at http://$WIFI_IP:5001"
echo "On Ethernet, access at http://$(ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1):5001"
echo "Logs are available at $LOG_FILE"
echo "Reboot the system to ensure all changes take effect: sudo reboot"
