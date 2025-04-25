from flask import render_template, request
from label_printer.config import logger
from label_printer.history import load_history, save_history
from label_printer.fonts import font_families, get_font_path  # Updated import
from label_printer.printing import print_label, print_qr_code
from label_printer.image import generate_label_image
from label_printer.utils import resolve_usb_conflicts
from datetime import datetime
import os
import json
import time

from flask import render_template, request
from label_printer.config import logger
from label_printer.history import load_history, save_history
from label_printer.fonts import font_families, get_font_path
from label_printer.printing import print_label, print_qr_code
from label_printer.image import generate_label_image
from label_printer.utils import resolve_usb_conflicts
from datetime import datetime
import os
import json
import time

def init_routes(app):
    @app.route('/', methods=['GET', 'POST'])
    def print_new_label():
        defaults = app.config.get('DEFAULTS', {})
        form_data = request.form.to_dict() if request.method == 'POST' else defaults
        if request.method == 'POST' and request.form.get('action') == 'Print Label':
            logger.debug(f"POST data: {request.form}")
            try:
                text1 = request.form.get('text1', '')
                text2 = request.form.get('text2', '')
                text3 = request.form.get('text3', '')
                length_mm = int(request.form.get('length', defaults.get('length_mm', 100)))
                size1 = int(request.form.get('size1', 48))
                size2 = int(request.form.get('size2', 48))
                size3 = int(request.form.get('size3', 48))
                face1 = request.form.get('face1', 'DejaVuSans')
                face2 = request.form.get('face2', 'DejaVuSans')
                face3 = request.form.get('face3', 'DejaVuSans')
                bold1 = bool(request.form.get('bold1'))
                bold2 = bool(request.form.get('bold2'))
                bold3 = bool(request.form.get('bold3'))
                italic1 = bool(request.form.get('italic1'))
                italic2 = bool(request.form.get('italic2'))
                italic3 = bool(request.form.get('italic3'))
                underline1 = bool(request.form.get('underline1'))
                underline2 = bool(request.form.get('underline2'))
                underline3 = bool(request.form.get('underline3'))
                bg1 = request.form.get('bg1', 'white')
                bg2 = request.form.get('bg2', 'white')
                bg3 = request.form.get('bg3', 'white')
                orientation = request.form.get('orientation', defaults.get('orientation', 'rotated'))
                tape_type = request.form.get('tape_type', defaults.get('tape_type', 'black'))
                justify1 = request.form.get('justify1', 'left')
                justify2 = request.form.get('justify2', 'left')
                justify3 = request.form.get('justify3', 'left')
                spacing1 = int(request.form.get('spacing1', 10))
                spacing2 = int(request.form.get('spacing2', 10))

                result = print_label(text1, text2, text3, length_mm, size1, size2, size3, face1, face2, face3, bold1, bold2, bold3, italic1, italic2, italic3, underline1, underline2, underline3, bg1, bg2, bg3, orientation, tape_type, justify1, justify2, justify3, spacing1, spacing2)

                # Handle dictionary response from print_label
                if isinstance(result, dict):
                    if result['status'] == 'success':
                        message = "Label printed successfully!"
                    else:
                        message = f"Error: {result['message']}"
                else:
                    # Fallback for unexpected result type
                    message = "Error: Unexpected response from printer"

                entry = {
                    "text1": text1,
                    "text2": text2,
                    "text3": text3,
                    "length_mm": length_mm,
                    "size1": size1,
                    "size2": size2,
                    "size3": size3,
                    "face1": face1,
                    "face2": face2,
                    "face3": face3,
                    "bold1": bold1,
                    "bold2": bold2,
                    "bold3": bold3,
                    "italic1": italic1,
                    "italic2": italic2,
                    "italic3": italic3,
                    "underline1": underline1,
                    "underline2": underline2,
                    "underline3": underline3,
                    "bg1": bg1,
                    "bg2": bg2,
                    "bg3": bg3,
                    "orientation": orientation,
                    "tape_type": tape_type,
                    "justify1": justify1,
                    "justify2": justify2,
                    "justify3": justify3,
                    "spacing1": spacing1,
                    "spacing2": spacing2,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_history(entry)

                preview_image = generate_label_image(text1, text2, text3, length_mm, size1, size2, size3, face1, face2, face3, bold1, bold2, bold3, italic1, italic2, italic3, underline1, underline2, underline3, bg1, bg2, bg3, orientation, tape_type, justify1, justify2, justify3, spacing1, spacing2)
                return render_template('index.html', message=message, history=load_history(), font_families=sorted(font_families.keys()), preview_image=preview_image, **entry)
            except Exception as e:
                logger.error(f"Error processing form: {str(e)}")
                return render_template('index.html', message=f"Error: {str(e)}", history=load_history(), font_families=sorted(font_families.keys()), **form_data), 400
        return render_template('index.html', history=load_history(), font_families=sorted(font_families.keys()), **form_data)
    
    @app.route('/preview', methods=['POST'])
    def preview_label():
        defaults = app.config.get('DEFAULTS', {})
        logger.debug(f"Preview POST data: {request.form}")
        try:
            text1 = request.form.get('text1', '')
            text2 = request.form.get('text2', '')
            text3 = request.form.get('text3', '')
            length_mm = int(request.form.get('length', defaults.get('length_mm', 100)))
            size1 = int(request.form.get('size1', 48))
            size2 = int(request.form.get('size2', 48))
            size3 = int(request.form.get('size3', 48))
            face1 = request.form.get('face1', 'DejaVuSans')
            face2 = request.form.get('face2', 'DejaVuSans')
            face3 = request.form.get('face3', 'DejaVuSans')
            bold1 = bool(request.form.get('bold1'))
            bold2 = bool(request.form.get('bold2'))
            bold3 = bool(request.form.get('bold3'))
            italic1 = bool(request.form.get('italic1'))
            italic2 = bool(request.form.get('italic2'))
            italic3 = bool(request.form.get('italic3'))
            underline1 = bool(request.form.get('underline1'))
            underline2 = bool(request.form.get('underline2'))
            underline3 = bool(request.form.get('underline3'))
            bg1 = request.form.get('bg1', 'white')
            bg2 = request.form.get('bg2', 'white')
            bg3 = request.form.get('bg3', 'white')
            orientation = request.form.get('orientation', defaults.get('orientation', 'rotated'))
            tape_type = request.form.get('tape_type', defaults.get('tape_type', 'black'))
            justify1 = request.form.get('justify1', 'left')
            justify2 = request.form.get('justify2', 'left')
            justify3 = request.form.get('justify3', 'left')
            spacing1 = int(request.form.get('spacing1', 10))
            spacing2 = int(request.form.get('spacing2', 10))

            preview_image = generate_label_image(text1, text2, text3, length_mm, size1, size2, size3, face1, face2, face3, bold1, bold2, bold3, italic1, italic2, italic3, underline1, underline2, underline3, bg1, bg2, bg3, orientation, tape_type, justify1, justify2, justify3, spacing1, spacing2)

            entry = {
                "text1": text1,
                "text2": text2,
                "text3": text3,
                "length_mm": length_mm,
                "size1": size1,
                "size2": size2,
                "size3": size3,
                "face1": face1,
                "face2": face2,
                "face3": face3,
                "bold1": bold1,
                "bold2": bold2,
                "bold3": bold3,
                "italic1": italic1,
                "italic2": italic2,
                "italic3": italic3,
                "underline1": underline1,
                "underline2": underline2,
                "underline3": underline3,
                "bg1": bg1,
                "bg2": bg2,
                "bg3": bg3,
                "orientation": orientation,
                "tape_type": tape_type,
                "justify1": justify1,
                "justify2": justify2,
                "justify3": justify3,
                "spacing1": spacing1,
                "spacing2": spacing2
            }
            return render_template('index.html', message="Label preview generated", history=load_history(), font_families=sorted(font_families.keys()), preview_image=preview_image, **entry)
        except Exception as e:
            logger.error(f"Error generating preview: {str(e)}")
            return render_template('index.html', message=f"Error: {str(e)}", history=load_history(), font_families=sorted(font_families.keys()), **request.form.to_dict()), 400

    @app.route('/print_qr', methods=['POST'])
    def print_qr():
        defaults = app.config.get('DEFAULTS', {})
        try:
            url = request.url_root.rstrip('/')
            logger.debug(f"Generating QR code for URL: {url}")
            for attempt in range(3):
                try:
                    result = print_qr_code(url)
                    if "Printing was successful" in result.stdout or "Printing was successful" in result.stderr:
                        logger.info("QR code printed successfully.")
                        return render_template('index.html', message="QR code printed successfully!", history=load_history(), font_families=sorted(font_families.keys()), **defaults)
                    logger.error(f"Print attempt {attempt + 1}/3 failed: {result.stderr}")
                    resolve_usb_conflicts()
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error printing QR code (attempt {attempt + 1}/3): {e}")
                    resolve_usb_conflicts()
                    time.sleep(2)
            logger.error("Failed to print QR code after 3 attempts.")
            return render_template('index.html', message="Failed to print QR code after retries", history=load_history(), font_families=sorted(font_families.keys()), **defaults), 500
        except Exception as e:
            logger.error(f"Error printing QR code: {str(e)}")
            return render_template('index.html', message=f"Error: {str(e)}", history=load_history(), font_families=sorted(font_families.keys()), **defaults), 400

    @app.route('/print_qr_custom', methods=['POST'])
    def print_qr_custom():
        defaults = app.config.get('DEFAULTS', {})
        try:
            qr_text = request.form.get('qr_text', '')
            exclude_text = bool(request.form.get('exclude_text'))
            if not qr_text:
                return render_template('index.html', message="Error: No text provided for QR code", history=load_history(), font_families=sorted(font_families.keys()), **defaults)
            logger.debug(f"Generating QR code for custom text: {qr_text}, exclude_text: {exclude_text}")
            for attempt in range(3):
                try:
                    result = print_qr_code(qr_text, exclude_text=exclude_text)
                    if "Printing was successful" in result.stdout or "Printing was successful" in result.stderr:
                        logger.info("Custom QR code printed successfully.")
                        return render_template('index.html', message="Custom QR code printed successfully!", history=load_history(), font_families=sorted(font_families.keys()), qr_text=qr_text, exclude_text=exclude_text, **defaults)
                    logger.error(f"Print attempt {attempt + 1}/3 failed: {result.stderr}")
                    resolve_usb_conflicts()
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error printing custom QR code (attempt {attempt + 1}/3): {e}")
                    resolve_usb_conflicts()
                    time.sleep(2)
            logger.error("Failed to print custom QR code after 3 attempts.")
            return render_template('index.html', message="Failed to print custom QR code after retries", history=load_history(), font_families=sorted(font_families.keys()), qr_text=qr_text, exclude_text=exclude_text, **defaults), 500
        except Exception as e:
            logger.error(f"Error printing custom QR code: {str(e)}")
            return render_template('index.html', message=f"Error: {str(e)}", history=load_history(), font_families=sorted(font_families.keys()), **defaults), 400

    @app.route('/save_defaults', methods=['POST'])
    def save_defaults():
        defaults = app.config.get('DEFAULTS', {})
        try:
            length_mm = int(request.form.get('length', defaults.get('length_mm', 100)))
            orientation = request.form.get('orientation', defaults.get('orientation', 'rotated'))
            tape_type = request.form.get('tape_type', defaults.get('tape_type', 'black'))
            
            settings = {
                "length_mm": length_mm,
                "orientation": orientation,
                "tape_type": tape_type
            }
            settings_file = "/home/odroid/label_printer_web/settings.txt"
            with open(settings_file, "w") as f:
                json.dump(settings, f)
            logger.debug(f"Saved default settings: {settings}")
            
            app.config['DEFAULTS'] = settings
            
            form_data = request.form.to_dict()
            form_data['length_mm'] = length_mm
            
            return render_template('index.html', message="Defaults saved successfully!", history=load_history(), font_families=sorted(font_families.keys()), **form_data)
        except Exception as e:
            logger.error(f"Error saving defaults: {str(e)}")
            return render_template('index.html', message=f"Error: {str(e)}", history=load_history(), font_families=sorted(font_families.keys()), **defaults), 400

    @app.route('/reprint', methods=['POST'])
    def reprint_label():
        defaults = app.config.get('DEFAULTS', {})
        label_id = int(request.form.get('label_id', -1))
        history = load_history()[::-1]
        if 0 <= label_id < len(history):
            label = history[label_id]
            return render_template('index.html', message="Label loaded for editing", history=load_history(), font_families=sorted(font_families.keys()), **label)
        return render_template('index.html', message="Invalid label selection", history=load_history(), font_families=sorted(font_families.keys()), **defaults)
