#!/bin/bash

# Install script for ameriDroid-Label-Server on ODROID-C4 with Ubuntu 22.04
# Installs prerequisites system-wide, clones GitHub repo, configures WiFi access point and Ethernet,
# fixes ODROID repository, and sets up systemd service. Runs natively without a virtual environment.

# Configuration variables
REPO_URL="https://github.com/Respectech/ameriDroid-Label-Server.git"
INSTALL_DIR="/home/odroid/label_printer_web"
PYTHON_EXEC="/usr/bin/python3"
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

# Fix hostname resolution warnings
echo "Fixing hostname resolution..."
echo "127.0.0.1 odroid" >> /etc/hosts

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
echo "deb http://deb.odroid.in/c4 jammy main" | sudo tee /etc/apt/sources.list.d/odroid.list
echo "Created/updated /etc/apt/sources.list.d/odroid.list" | tee -a "$LOG_FILE"

# Add Hardkernel PPA with trusted fallback
echo "Adding Hardkernel PPA..."
echo "deb [trusted=yes] http://ppa.launchpad.net/hardkernel/ppa/ubuntu jammy main" | sudo tee /etc/apt/sources.list.d/hardkernel-ubuntu-ppa-jammy.list
echo "Added Hardkernel PPA with trusted=yes" | tee -a "$LOG_FILE"

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
    python3 python3-dev python3-pip \
    git \
    libusb-1.0-0-dev \
    fontconfig \
    imagemagick \
    libfreetype6-dev libjpeg-dev zlib1g-dev \
    python3-usb \
    python3-packaging \
    hostapd \
    dnsmasq \
    linux-firmware \
    samba \
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
    "$PYTHON_EXEC" -m pip install --no-deps -r "$INSTALL_DIR/requirements.txt" || {
        echo "Failed to install Python packages from requirements.txt" | tee -a "$LOG_FILE"
        exit 1
    }
else
    echo "requirements.txt not found, installing core packages..."
    "$PYTHON_EXEC" -m pip install --no-deps \
        brother_ql \
        Pillow \
        qrcode \
        PyPDF2 \
        attrs \
        watchdog \
        || {
        echo "Failed to install core Python packages" | tee -a "$LOG_FILE"
        exit 1
    }
    # Install Flask with dependencies
    "$PYTHON_EXEC" -m pip install --ignore-installed flask || {
        echo "Failed to install Flask with dependencies" | tee -a "$LOG_FILE"
        exit 1
    }
fi

# Verify WiFi interface
echo "Verifying WiFi interface $WIFI_IFACE..."
if ! ip link show "$WIFI_IFACE" &> /dev/null; then
    echo "Error: WiFi interface $WIFI_IFACE not found. Available interfaces:" | tee -a "$LOG_FILE"
    ip link show | grep -E '^[0-9]+: ' | awk '{print $2}' | cut -d':' -f1 | tee -a "$LOG_FILE"
    echo "Please update WIFI_IFACE in the script and re-run." | tee -a "$LOG_FILE"
    exit 1
fi

# Check if WiFi dongle supports AP mode
echo "Checking AP mode support for $WIFI_IFACE..."
iw list > /tmp/iw_list_output.txt
if ! grep -A 10 "Supported interface modes" /tmp/iw_list_output.txt | grep -q "AP"; then
    echo "Error: WiFi dongle does not support AP mode." | tee -a "$LOG_FILE"
    echo "Full iw list output saved to /tmp/iw_list_output.txt for debugging." | tee -a "$LOG_FILE"
    echo "Try updating firmware (sudo apt install linux-firmware) or installing a new driver:" | tee -a "$LOG_FILE"
    echo "  sudo apt install dkms git build-essential linux-headers-$(uname -r)" | tee -a "$LOG_FILE"
    echo "  git clone https://github.com/morrownr/8821cu-20210118.git /home/odroid/8821cu-20210118" | tee -a "$LOG_FILE"
    echo "  cd /home/odroid/8821cu-20210118 && sudo ./install-driver.sh" | tee -a "$LOG_FILE"
    exit 1
fi

# Disable systemd-resolved to free port 53 for dnsmasq
echo "Disabling systemd-resolved to avoid port 53 conflict..."
systemctl stop systemd-resolved || {
    echo "Failed to stop systemd-resolved" | tee -a "$LOG_FILE"
}
systemctl disable systemd-resolved || {
    echo "Failed to disable systemd-resolved" | tee -a "$LOG_FILE"
}
# Configure external DNS servers
echo "Configuring external DNS servers..."
# Ensure /etc/resolv.conf is not a symlink
if [ -L /etc/resolv.conf ]; then
    sudo rm /etc/resolv.conf
fi
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf
# Attempt to make resolv.conf immutable, ignore if filesystem doesn't support
chattr +i /etc/resolv.conf || {
    echo "Warning: Failed to make /etc/resolv.conf immutable, continuing..." | tee -a "$LOG_FILE"
}
# Disable NetworkManager DNS management
echo "Disabling NetworkManager DNS management..."
if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
    sed -i '/^\[main\]/a dns=none' /etc/NetworkManager/NetworkManager.conf || {
        echo "Failed to disable NetworkManager DNS" | tee -a "$LOG_FILE"
    }
    systemctl restart NetworkManager || {
        echo "Failed to restart NetworkManager" | tee -a "$LOG_FILE"
        exit 1
    }
fi

# Verify DNS resolution
echo "Verifying DNS resolution..."
if ! nslookup pypi.org > /dev/null; then
    echo "Error: DNS resolution failed, cannot proceed with package installation" | tee -a "$LOG_FILE"
    exit 1
fi

# Configure WiFi access point
echo "Configuring WiFi access point on $WIFI_IFACE..."
# Set static IP for wlan0
echo "Assigning static IP $WIFI_IP to $WIFI_IFACE..."
ip addr flush dev "$WIFI_IFACE"
ip addr add "$WIFI_IP/24" dev "$WIFI_IFACE" || {
    echo "Failed to assign IP $WIFI_IP to $WIFI_IFACE" | tee -a "$LOG_FILE"
    exit 1
}
ip link set "$WIFI_IFACE" up || {
    echo "Failed to bring up $WIFI_IFACE" | tee -a "$LOG_FILE"
    exit 1
}

# Configure hostapd
echo "Configuring hostapd..."
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
rsn_pairwise=CCMP
EOF
echo "DAEMON_CONF=/etc/hostapd/hostapd.conf" | sudo tee -a /etc/default/hostapd

# Configure dnsmasq
echo "Configuring dnsmasq..."
cat > /etc/dnsmasq.conf <<EOF
interface=$WIFI_IFACE
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,12h
EOF

# Configure NetworkManager to ignore wlan0
if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
    echo "Configuring NetworkManager to ignore $WIFI_IFACE..."
    cat > /etc/NetworkManager/NetworkManager.conf <<EOF
[main]
plugins=ifupdown,keyfile
dns=none

[ifupdown]
managed=false

[keyfile]
unmanaged-devices=interface-name:$WIFI_IFACE
EOF
    systemctl restart NetworkManager || {
        echo "Failed to restart NetworkManager" | tee -a "$LOG_FILE"
        exit 1
    }
    # Explicitly set wlan0 to unmanaged
    nmcli device set "$WIFI_IFACE" managed no || {
        echo "Failed to set $WIFI_IFACE to unmanaged in NetworkManager" | tee -a "$LOG_FILE"
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
systemctl start hostapd || {
    echo "Failed to start hostapd, check logs with: journalctl -u hostapd.service" | tee -a "$LOG_FILE"
    exit 1
}
systemctl start dnsmasq || {
    echo "Failed to start dnsmasq, check logs with: journalctl -u dnsmasq.service" | tee -a "$LOG_FILE"
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
RestartSec=5
StandardOutput=journal
StandardError=journal

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

# Create 'label' user and set password
echo "Creating 'label' user and setting password to 'label'..."
if ! id "label" &>/dev/null; then
    useradd -m -s /bin/bash label
fi
echo "label:label" | chpasswd

# Ensure Samba shares are configured
echo "Ensuring Samba shares are configured..."
if ! grep -q '\[print\]' /etc/samba/smb.conf; then
    cat >> /etc/samba/smb.conf <<EOL
[print]
    path = /home/odroid/label_printer_web/print
    browseable = yes
    read only = no
    writable = yes
    valid users = label
    create mask = 0666
    directory mask = 0777
    force user = odroid
    force group = odroid
EOL
fi

if ! grep -q '\[fonts\]' /etc/samba/smb.conf; then
    cat >> /etc/samba/smb.conf <<EOL
[fonts]
    path = /home/odroid/label_printer_web/static/fonts
    browseable = yes
    read only = no
    writable = yes
    valid users = label
    create mask = 0666
    directory mask = 0777
    force user = odroid
    force group = odroid
EOL
fi

# Test Samba configuration
echo "Testing Samba configuration..."
testparm

# Restart Samba services
echo "Restarting Samba services..."
systemctl restart smbd nmbd

# Set permissions for printer USB access
echo "Configuring USB permissions for Brother QL-810W..."
usermod -a -G lp odroid
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="04f9", ATTR{idProduct}=="209c", MODE="0666", GROUP="lp"' >/etc/udev/rules.d/99-brother-ql810w.rules
udevadm control --reload-rules && udevadm trigger || {
    echo "Failed to configure USB permissions" | tee -a "$LOG_FILE"
    exit 1
}

# Verify Flask is listening on port 5001
echo "Verifying Flask web server..."
if ! netstat -tulnp | grep -q ":5001.*python3"; then
    echo "Error: Flask web server not listening on port 5001, check logs with: journalctl -u $SERVICE_NAME" | tee -a "$LOG_FILE"
    exit 1
fi

# Open port 5001 in firewall if ufw is active
if ufw status | grep -q "Status: active"; then
    echo "Opening port 5001 in firewall..."
    ufw allow 5001/tcp || {
        echo "Failed to open port 5001 in firewall" | tee -a "$LOG_FILE"
        exit 1
    }
fi

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
    echo "WiFi access point services not fully running, check logs with: journalctl -u hostapd -u dnsmasq" | tee -a "$LOG_FILE"
    exit 1
fi
if ip addr show eth0 | grep -q "inet "; then
    echo "Ethernet interface eth0 is configured" | tee -a "$LOG_FILE"
else
    echo "Ethernet interface eth0 not configured, check network settings" | tee -a "$LOG_FILE"
    exit 1
fi

# Print completion message
echo "Installation completed successfully at $(date)" | tee -a "$LOG_FILE"
echo "Connect your phone to WiFi network '$WIFI_SSID' with password '$WIFI_PASS' and access at http://$WIFI_IP:5001"
echo "On Ethernet, access at http://$(ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1):5001"
echo "Logs are available at $LOG_FILE"
echo "Reboot the system to ensure all changes take effect: sudo reboot"
