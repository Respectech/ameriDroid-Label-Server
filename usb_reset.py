import fcntl
import sys
import os
import subprocess

def reset_usb_device(vendor_id="04f9", product_id="209c"):
    device_path = None
    try:
        # Run lsusb to find the device
        lsusb_output = subprocess.run(["lsusb"], capture_output=True, text=True)
        for line in lsusb_output.stdout.splitlines():
            if f"{vendor_id}:{product_id}" in line:
                parts = line.split()
                bus = parts[1]
                device = parts[3][:3]
                device_path = f"/dev/bus/usb/{bus}/{device}"
                print(f"Found USB device at {device_path}")
                break
        else:
            print(f"USB device {vendor_id}:{product_id} not found in lsusb output")
            sys.exit(1)
    except Exception as e:
        print(f"Error running lsusb: {e}")
        sys.exit(1)

    # Log device permissions
    try:
        stat = os.stat(device_path)
        perms = oct(stat.st_mode)[-3:]
        owner = stat.st_uid
        group = stat.st_gid
        print(f"Device permissions: {perms}, UID: {owner}, GID: {group}")
    except Exception as e:
        print(f"Failed to stat {device_path}: {e}")

    # Check if usblp is loaded
    try:
        lsmod = subprocess.run(["lsmod"], capture_output=True, text=True)
        if "usblp" in lsmod.stdout:
            print("usblp driver loaded, attempting to detach")
            subprocess.run(["sudo", "-n", "/sbin/rmmod", "usblp"], check=True)
            print("Detached usblp driver")
    except subprocess.CalledProcessError as e:
        print(f"Failed to detach usblp: {e}")
    except Exception as e:
        print(f"Error checking usblp: {e}")

    # Attempt reset
    try:
        with open(device_path, 'wb') as fd:
            fcntl.ioctl(fd, 21780, 0)  # USBDEVFS_RESET
        print(f"Successfully reset USB device {device_path}")
    except Exception as e:
        print(f"Failed to reset USB device {device_path}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    reset_usb_device()
