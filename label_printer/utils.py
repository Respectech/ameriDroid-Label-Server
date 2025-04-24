import subprocess
from label_printer.config import logger

def resolve_usb_conflicts():
    usb_device = "usb://0x04f9:0x209c"
    logger.debug(f"Starting USB conflict resolution for {usb_device}")

    # Step 1: Verify USB device presence
    try:
        lsusb_output = subprocess.run(["lsusb"], capture_output=True, text=True)
        logger.debug(f"lsusb output:\n{lsusb_output.stdout}")
        if lsusb_output.stderr:
            logger.error(f"lsusb error: {lsusb_output.stderr}")
        usb_path = None
        for line in lsusb_output.stdout.splitlines():
            if "04f9:209c" in line:
                parts = line.split()
                bus = parts[1]
                device = parts[3][:3]
                usb_path = f"/dev/bus/usb/{bus}/{device}"
                logger.debug(f"Found USB device at {usb_path}")
                break
        else:
            logger.warning(f"Printer {usb_device} not found in lsusb output.")
            return
    except Exception as e:
        logger.error(f"Error running lsusb: {e}")
        return

    # Step 2: Run wrapper script for fuser and kill
    try:
        logger.debug("Running resolve-usb-conflicts.sh to handle processes")
        result = subprocess.run(["sudo", "-n", "/usr/local/bin/resolve-usb-conflicts.sh"], capture_output=True, text=True, check=True)
        logger.debug(f"resolve-usb-conflicts.sh stdout: '{result.stdout}'")
        logger.debug(f"resolve-usb-conflicts.sh stderr: '{result.stderr}'")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to run resolve-usb-conflicts.sh: {e.stderr}")
    except Exception as e:
        logger.error(f"Error running resolve-usb-conflicts.sh: {e}")

    # Step 3: Stop ippusbxd service
    try:
        ippusbxd_status = subprocess.run(["/bin/systemctl", "is-active", "ippusbxd"], capture_output=True, text=True)
        logger.debug(f"ippusbxd status: {ippusbxd_status.stdout.strip()}")
        if ippusbxd_status.stdout.strip() == "active":
            logger.info("ippusbxd service is active, stopping it")
            subprocess.run(["sudo", "-n", "/bin/systemctl", "stop", "ippusbxd"], check=True)
            subprocess.run(["sudo", "-n", "/bin/systemctl", "disable", "ippusbxd"], check=True)
            logger.info("Stopped and disabled ippusbxd service")
        else:
            logger.debug("ippusbxd service is not active")
    except Exception as e:
        logger.error(f"Error managing ippusbxd service: {e}")

    # Step 4: Reset USB device
    try:
        logger.debug("Attempting to reset USB device 0x04f9:0x209c")
        result = subprocess.run(["sudo", "-n", "python3", "/home/odroid/label_printer_web/usb_reset.py", "1", "4"], capture_output=True, text=True, check=True)
        logger.info(f"USB device reset successfully: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to reset USB device: {e.stderr}")
    except Exception as e:
        logger.error(f"Error running usb_reset.py: {e}")

    # Step 5: Detach kernel drivers
    try:
        logger.debug("Checking loaded kernel drivers")
        lsmod_output = subprocess.run(["lsmod"], capture_output=True, text=True)
        logger.debug(f"lsmod output:\n{lsmod_output.stdout}")
        for driver in ["lp", "usbhid", "usblp"]:
            if driver in lsmod_output.stdout:
                logger.debug(f"Detaching kernel driver: {driver}")
                subprocess.run(["sudo", "-n", "/sbin/rmmod", driver], check=True)
                logger.info(f"Detached kernel driver: {driver}")
            else:
                logger.debug(f"Kernel driver {driver} not loaded")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to detach kernel driver: {e.stderr}")
    except Exception as e:
        logger.error(f"Error detaching kernel drivers: {e}")
