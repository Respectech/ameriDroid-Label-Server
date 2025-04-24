import os
import logging

HISTORY_FILE = os.path.expanduser("~/label_printer_web/label_history.json")

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

#FONT_DIR = "/usr/share/fonts/truetype/"
FONT_DIR = "/home/odroid/label_printer_web/static/fonts/"

