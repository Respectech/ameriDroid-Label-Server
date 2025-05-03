import subprocess
import os
from PIL import Image, ImageDraw, ImageFont
import io
import base64
import qrcode
import time
from label_printer.config import logger
import PyPDF2
from label_printer.utils import resolve_usb_conflicts
import re

def clean_filename(filename):
    """Replace problematic Unicode sequences with the '|' symbol."""
    # Replace Unicode \uf027 or similar with '|'
    cleaned = re.sub(r'\uf027', '|', filename)
    return cleaned

def print_label(text1, text2, text3, length_mm, size1, size2, size3, face1, face2, face3, bold1, bold2, bold3, italic1, italic2, italic3, underline1, underline2, underline3, bg1, bg2, bg3, orientation, tape_type, justify1='left', justify2='left', justify3='left', spacing1=10, spacing2=10):
    from label_printer.image import generate_label_image
    img_path = "/tmp/label.png"
    image = generate_label_image(text1, text2, text3, length_mm, size1, size2, size3, face1, face2, face3, bold1, bold2, bold3, italic1, italic2, italic3, underline1, underline2, underline3, bg1, bg2, bg3, orientation, tape_type, justify1, justify2, justify3, spacing1, spacing2)
    Image.open(io.BytesIO(base64.b64decode(image))).save(img_path)

    size_check = subprocess.run(["identify", img_path], capture_output=True, text=True)
    logger.debug(f"Image size: {size_check.stdout}")

    brother_ql_path = os.path.expanduser("~/.local/bin/brother_ql")
    print_cmd = [
        brother_ql_path, "--backend", "pyusb",
        "--model", "QL-810W", "--printer", "usb://0x04f9:0x209c",
        "print", "--label", "62"
    ]
    if tape_type == "red_black":
        print_cmd.append("--red")
    print_cmd.append(img_path)

    result = None
    for attempt in range(3):
        try:
            logger.debug(f"Executing print (attempt {attempt + 1}/3): {' '.join(print_cmd)}")
            result = subprocess.run(print_cmd, capture_output=True, text=True, check=True)
            logger.debug(f"Output: {result.stdout}")
            logger.debug(f"Error (if any): {result.stderr}")
            if "Printing was successful" in result.stderr:
                logger.info(f"Successfully printed label on attempt {attempt + 1}")
                break
            else:
                logger.warning(f"Print attempt {attempt + 1} failed with output: {result.stderr}")
                resolve_usb_conflicts()
                time.sleep(2)
        except subprocess.CalledProcessError as e:
            logger.warning(f"Print attempt {attempt + 1} failed with error: {e.stderr}")
            if "Resource busy" in e.stderr.lower() or "usberror" in e.stderr.lower():
                logger.info("Detected USB conflict, resolving...")
                resolve_usb_conflicts()
                time.sleep(2)
            else:
                logger.error(f"Unexpected subprocess error: {e.stderr}")
                break
        except Exception as e:
            logger.error(f"Unexpected error during print attempt {attempt + 1}: {str(e)}")
            if "Resource busy" in str(e).lower() or "USBError" in str(e):
                logger.info("Detected USB conflict, resolving...")
                resolve_usb_conflicts()
                time.sleep(2)
            else:
                logger.error(f"Non-USB error, aborting: {str(e)}")
                break
    else:
        logger.error("Failed to print label after 3 attempts")
        os.remove(img_path)
        return {'status': 'error', 'message': 'Failed to print label after 3 attempts'}

    # Filter out deprecation warning from stderr
    cleaned_output = []
    if result:
        for line in result.stderr.splitlines():
            if "deprecation warning" not in line.lower():
                cleaned_output.append(line)
    cleaned_message = "\n".join(cleaned_output) if cleaned_output else "Printing was successful."

    os.remove(img_path)
    return {'status': 'success', 'message': cleaned_message}

def print_qr_code(url, exclude_text=False):
    from label_printer.image import generate_qr_code_image
    img_path = "/tmp/qr_code.png"
    
    try:
        qr_img = generate_qr_code_image(url, box_size=10)
        logger.debug(f"Original QR code size: {qr_img.width}x{qr_img.height}px")
        
        raw_qr_path = "/home/odroid/raw_qr.png"
        qr_img.save(raw_qr_path)
        logger.debug(f"Saved raw QR image at {raw_qr_path}, size: {qr_img.width}x{qr_img.height}px")
        
        qr_img = qr_img.resize((150, 150), Image.LANCZOS)
        logger.debug(f"QR code size after resize: {qr_img.width}x{qr_img.height}px")
        
        canvas_width = 696
        canvas_height = 150 if exclude_text else 180
        padded_img = Image.new("RGB", (canvas_width, canvas_height), "white")
        draw = ImageDraw.Draw(padded_img)
        
        paste_x = (canvas_width - qr_img.width) // 2
        paste_y = 0
        padded_img.paste(qr_img, (paste_x, paste_y))
        
        if not exclude_text:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            font_size = 20
            font = ImageFont.truetype(font_path, font_size)
            text_bbox = draw.textbbox((0, 0), url, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = (canvas_width - text_width) // 2
            text_y = 150
            draw.text((text_x, text_y), url, font=font, fill="black")
        
        debug_path = "/home/odroid/test_qr.png"
        padded_img.save(debug_path)
        logger.debug(f"Saved debug image at {debug_path}, size: {padded_img.width}x{padded_img.height}px")
        
        padded_img.save(img_path)
        logger.debug(f"Padded image size: {padded_img.width}x{padded_img.height}px")

        brother_ql_path = os.path.expanduser("~/.local/bin/brother_ql")
        base_print_cmd = [
            brother_ql_path, "--backend", "pyusb",
            "--model", "QL-810W", "--printer", "usb://0x04f9:0x209c",
            "print", "--label", "62", img_path
        ]

        # Try printing without --red first (black on white)
        for attempt in range(3):
            try:
                print_cmd = base_print_cmd.copy()
                logger.debug(f"Executing QR print (black on white, attempt {attempt + 1}/3): {' '.join(print_cmd)}")
                result = subprocess.run(print_cmd, capture_output=True, text=True, check=True)
                logger.debug(f"Output: {result.stdout}")
                logger.debug(f"Error (if any): {result.stderr}")
                if "Printing was successful" in result.stderr:
                    logger.info(f"Successfully printed QR code (black on white) on attempt {attempt + 1}")
                    os.remove(img_path)
                    cleaned_output = [line for line in result.stderr.splitlines() if "deprecation warning" not in line.lower()]
                    return {'status': 'success', 'message': "\n".join(cleaned_output) or "Printing was successful."}
                else:
                    logger.warning(f"Print attempt {attempt + 1} (black on white) failed with output: {result.stderr}")
                    resolve_usb_conflicts()
                    time.sleep(2)
            except subprocess.CalledProcessError as e:
                logger.warning(f"Print attempt {attempt + 1} (black on white) failed with error: {e.stderr}")
                if "Resource busy" in e.stderr.lower() or "usberror" in e.stderr.lower():
                    logger.info("Detected USB conflict, resolving...")
                    resolve_usb_conflicts()
                    time.sleep(2)
                else:
                    logger.error(f"Unexpected subprocess error (black on white): {e.stderr}")
                    break
            except Exception as e:
                logger.error(f"Unexpected error during print attempt {attempt + 1} (black on white): {str(e)}")
                if "Resource busy" in str(e).lower() or "USBError" in str(e):
                    logger.info("Detected USB conflict, resolving...")
                    resolve_usb_conflicts()
                    time.sleep(2)
                else:
                    logger.error(f"Non-USB error (black on white), aborting: {str(e)}")
                    break
        else:
            logger.warning("Failed to print QR code (black on white) after 3 attempts, trying with --red")

        # Retry with --red (black/red on white)
        for attempt in range(3):
            try:
                print_cmd = base_print_cmd.copy()
                print_cmd.insert(-1, "--red")  # Add --red before img_path
                logger.debug(f"Executing QR print (black/red on white, attempt {attempt + 1}/3): {' '.join(print_cmd)}")
                result = subprocess.run(print_cmd, capture_output=True, text=True, check=True)
                logger.debug(f"Output: {result.stdout}")
                logger.debug(f"Error (if any): {result.stderr}")
                if "Printing was successful" in result.stderr:
                    logger.info(f"Successfully printed QR code (black/red on white) on attempt {attempt + 1}")
                    os.remove(img_path)
                    cleaned_output = [line for line in result.stderr.splitlines() if "deprecation warning" not in line.lower()]
                    return {'status': 'success', 'message': "\n".join(cleaned_output) or "Printing was successful."}
                else:
                    logger.warning(f"Print attempt {attempt + 1} (black/red on white) failed with output: {result.stderr}")
                    resolve_usb_conflicts()
                    time.sleep(2)
            except subprocess.CalledProcessError as e:
                logger.warning(f"Print attempt {attempt + 1} (black/red on white) failed with error: {e.stderr}")
                if "Resource busy" in e.stderr.lower() or "usberror" in e.stderr.lower():
                    logger.info("Detected USB conflict, resolving...")
                    resolve_usb_conflicts()
                    time.sleep(2)
                else:
                    logger.error(f"Unexpected subprocess error (black/red on white): {e.stderr}")
                    break
            except Exception as e:
                logger.error(f"Unexpected error during print attempt {attempt + 1} (black/red on white): {str(e)}")
                if "Resource busy" in str(e).lower() or "USBError" in str(e):
                    logger.info("Detected USB conflict, resolving...")
                    resolve_usb_conflicts()
                    time.sleep(2)
                else:
                    logger.error(f"Non-USB error (black/red on white), aborting: {str(e)}")
                    break
        else:
            logger.error("Failed to print QR code (black/red on white) after 3 attempts")
            os.remove(img_path)
            return {'status': 'error', 'message': 'Failed to print QR code after 3 attempts with black/red on white'}

    except Exception as e:
        logger.error(f"Error in print_qr_code: {str(e)}")
        if os.path.exists(img_path):
            os.remove(img_path)
        return {'status': 'error', 'message': f'Error in print_qr_code: {str(e)}'}

def print_file(file_path):
    """Print an image or PDF file with cropping, custom scaling, and optional grayscale/dithering."""
    output_path = "/tmp/print_file.png"  # Define early to avoid UnboundLocalError
    try:
        PAPER_WIDTH = 696  # Printer paper width in pixels (62mm at 300 DPI)

        # Clean the filename to handle Unicode issues
        filename = clean_filename(os.path.basename(file_path))
        logger.debug(f"Cleaned filename: {filename}")

        # Determine file type and dimensions
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            img = Image.open(file_path)
            width, height = img.size
        elif file_path.lower().endswith('.pdf'):
            pdf = PyPDF2.PdfReader(file_path)
            num_pages = len(pdf.pages)
            logger.debug(f"PDF has {num_pages} pages")

            # Convert all pages to PNGs at full resolution
            page_images = []
            for page_num in range(num_pages):
                output_prefix = f"/tmp/pdf_page_{page_num}"
                subprocess.run(['pdftoppm', '-png', '-f', str(page_num + 1), '-l', str(page_num + 1), file_path, output_prefix], check=True)
                page_img = Image.open(f"{output_prefix}-{page_num + 1}.png")
                page_images.append(page_img)
                os.remove(f"{output_prefix}-{page_num + 1}.png")

            # Combine pages vertically into a single image
            total_height = sum(img.height for img in page_images)
            max_width = max(img.width for img in page_images)
            combined_img = Image.new('RGB', (max_width, total_height), (255, 255, 255))
            y_offset = 0
            for img in page_images:
                combined_img.paste(img, (0, y_offset))
                y_offset += img.height
            img = combined_img
            width, height = img.size
        else:
            logger.debug(f"Skipping unsupported file: {file_path}")
            return None  # Caller will handle removal

        # Log original dimensions
        logger.debug(f"Original dimensions: {width}x{height}px")

        # Crop whitespace unless filename contains "+ws"
        if "+ws" not in filename.lower():
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img_array = img.point(lambda p: p < 240 and 255)  # Anything darker than 240 is content
            bbox = img_array.getbbox()
            if bbox:
                img = img.crop(bbox)
                width, height = img.size
                logger.debug(f"Cropped image to remove whitespace: {width}x{height}px")
            else:
                logger.debug("No content detected after cropping, using original image")

        # Save intermediate cropped image for debugging
        debug_path = "/home/odroid/cropped_debug.png"
        img.save(debug_path)
        logger.debug(f"Saved cropped image for debugging at {debug_path}, size: {width}x{height}px")

        # Parse filename for custom width or height
        custom_width = None
        custom_height = None
        width_match = re.search(r'\|w=(\d+)\|', filename)
        height_match = re.search(r'\|h=(\d+)\|', filename)
        if width_match:
            custom_width = int(width_match.group(1))
            logger.debug(f"Custom width specified: {custom_width}px")
        if height_match:
            custom_height = int(height_match.group(1))
            logger.debug(f"Custom height specified: {custom_height}px")

        # Final resize step
        aspect_ratio = width / height
        if custom_width and custom_height:
            # Both specified, stretch to exact dimensions
            new_width = custom_width
            new_height = custom_height
            rotate = new_width > PAPER_WIDTH and new_width > new_height
            img = img.resize((new_width, new_height), Image.LANCZOS)
            logger.debug(f"Stretched image to {new_width}x{new_height}px (ignoring aspect ratio), rotate: {rotate}")
        elif custom_width:
            # Only width specified, preserve aspect ratio
            new_width = custom_width
            new_height = int(new_width / aspect_ratio)
            rotate = new_width > PAPER_WIDTH and new_width > new_height
            img = img.resize((new_width, new_height), Image.LANCZOS)
            logger.debug(f"Resized to custom width {new_width}x{new_height}px (preserving aspect ratio), rotate: {rotate}")
        elif custom_height:
            # Only height specified, preserve aspect ratio
            new_height = custom_height
            new_width = int(new_height * aspect_ratio)
            rotate = new_width > PAPER_WIDTH and new_width > new_height
            img = img.resize((new_width, new_height), Image.LANCZOS)
            logger.debug(f"Resized to custom height {new_width}x{new_height}px (preserving aspect ratio), rotate: {rotate}")
        else:
            # No custom dimensions, use default scaling
            if width < height:  # Portrait
                new_width = PAPER_WIDTH
                new_height = int(PAPER_WIDTH / aspect_ratio)
                rotate = False
            else:  # Landscape
                new_width = int(PAPER_WIDTH * aspect_ratio)
                new_height = PAPER_WIDTH
                rotate = True
            img = img.resize((new_width, new_height), Image.LANCZOS)
            logger.debug(f"Scaled image to {new_width}x{new_height}px (still in color), rotate: {rotate}")

        # Rotate if wider than tall and exceeds paper width
        if rotate:
            img = img.rotate(90, expand=True)
            logger.debug(f"Rotated image to align short edge with paper width, new dimensions: {img.width}x{img.height}px")

        # Create a white canvas with tape width and image height
        canvas_width = PAPER_WIDTH
        canvas_height = img.height
        canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
        # Paste the image on the left side (x=0)
        canvas.paste(img, (0, 0))
        img = canvas
        logger.debug(f"Placed image on white canvas: {canvas_width}x{canvas_height}px")

        # Convert to grayscale and dither unless "-gs" is in filename
        if "-gs" not in filename:
            img = img.convert('L')  # Grayscale
            img = img.convert('1', dither=Image.FLOYDSTEINBERG)  # 1-bit with dithering
            logger.debug(f"Converted to grayscale and dithered to 1-bit")
        else:
            logger.debug(f"Keeping image in original color mode due to '-gs' in filename")

        # Prepare image for printing
        img.save(output_path)

        # Print with USB conflict resolution
        brother_ql_path = os.path.expanduser("~/.local/bin/brother_ql")
        print_cmd = [
            brother_ql_path, "--backend", "pyusb",
            "--model", "QL-810W", "--printer", "usb://0x04f9:0x209c",
            "print", "--label", "62", output_path
        ]
        for attempt in range(3):
            try:
                logger.debug(f"Executing print (attempt {attempt + 1}/3): {' '.join(print_cmd)}")
                result = subprocess.run(print_cmd, capture_output=True, text=True)
                logger.debug(f"Output: {result.stdout}")
                logger.debug(f"Error (if any): {result.stderr}")
                if "Printing was successful" in result.stderr:  # Check stderr for success
                    logger.info(f"Successfully printed {file_path} on attempt {attempt + 1}")
                    break
                elif "Resource busy" in result.stderr or result.returncode != 0:
                    logger.warning(f"Print attempt {attempt + 1} failed, resolving USB conflicts")
                    resolve_usb_conflicts()
                    time.sleep(2)
                else:
                    logger.error(f"Print failed with unexpected output: {result.stderr}")
                    break
            except subprocess.CalledProcessError as e:
                logger.warning(f"Print attempt {attempt + 1} failed with error: {e.stderr}")
                resolve_usb_conflicts()
                time.sleep(2)
            except Exception as e:
                logger.error(f"Unexpected error during print attempt {attempt + 1}: {str(e)}")
                resolve_usb_conflicts()
                time.sleep(2)
        else:
            logger.error(f"Failed to print {file_path} after 3 attempts")
            return None

        return result
    except Exception as e:
        logger.error(f"Error printing file {file_path}: {str(e)}")
        return None
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
