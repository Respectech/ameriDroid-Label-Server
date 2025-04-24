import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from label_printer.printing import print_file
from label_printer.config import logger

PRINT_DIR = "/home/odroid/label_printer_web/print"

class PrintHandler(FileSystemEventHandler):
    def on_created(self, event):
        self.process_event(event)

    def on_modified(self, event):
        self.process_event(event)

    def process_event(self, event):
        if event.is_directory:
            return
        file_path = event.src_path
        logger.debug(f"File event detected: {file_path} (event: {event.event_type})")
        time.sleep(2)  # Increased delay for Samba to finish writing
        if os.path.exists(file_path):  # Ensure file still exists
            logger.debug(f"Processing file: {file_path}")
            result = print_file(file_path)
            if result is None:
                # Invalid file or failed after retries
                logger.info(f"Removing invalid or unprintable file: {file_path}")
                os.remove(file_path)
            elif "Printing was successful" in result.stderr:
                logger.info(f"Successfully printed {file_path}, removing file")
                os.remove(file_path)
            else:
                logger.error(f"Failed to print {file_path}, keeping file for review")
        else:
            logger.debug(f"File {file_path} no longer exists, skipping")

def watch_print_directory():
    event_handler = PrintHandler()
    observer = Observer()
    observer.schedule(event_handler, PRINT_DIR, recursive=False)
    observer.start()
    logger.info(f"Started watching {PRINT_DIR}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    watch_print_directory()
