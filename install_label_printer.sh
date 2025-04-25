#!/bin/bash

# Install script for ameriDroid-Label-Server on ODROID-C4 with Ubuntu
# Installs prerequisites system-wide, clones GitHub repo, and configures systemd service
# Runs natively without a Python virtual environment

# Configuration variables
REPO_URL="https://github.com/Respectech/ameriDroid-Label-Server.git"
INSTALL_DIR="/home/odroid/label_printer_web"
PYTHON_EXEC="/usr/bin/python3.8"
SERVICE_NAME="label-printer"
LOG_FILE="/home/odroid/install_label_printer.log"

# Ensure script is run with sudo
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (use sudo)" | tee -a "$LOG_FILE"
    exit 1
fi

# Redirect output to log file and console
exec > >(tee -a "$LOG_FILE") 2>&1
echo "Starting installation at $(date)"

# Update package lists and upgrade system
echo "Updating system packages..."
apt update -y && apt full-upgrade -y || {
    echo "Failed to update packages" | tee -a "$LOG_FILE"
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
    python3-pyusb \
    python3-packaging \
    || {
    echo "Failed to install system dependencies" | tee -a "$LOG_FILE"
    exit 1
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

# Print completion message
echo "Installation completed successfully at $(date)" | tee -a "$LOG_FILE"
echo "Access the web interface at http://$(hostname -I | awk '{print $1}'):5001"
echo "Logs are available at $LOG_FILE"
echo "Reboot the system to ensure all changes take effect: sudo reboot"
