from PIL import Image, ImageDraw, ImageFont
import io
import base64
import qrcode
from label_printer.fonts import get_font_path
from label_printer.config import logger

def generate_label_image(text1, text2, text3, length_mm, size1, size2, size3, face1, face2, face3, bold1, bold2, bold3, italic1, italic2, italic3, underline1, underline2, underline3, bg1, bg2, bg3, orientation, tape_type, justify1='left', justify2='left', justify3='left', spacing1=10, spacing2=10):
    width_px = 696  # 62mm at 300 DPI
    length_px = max(int(length_mm * 11.811) - 83, 1)  # Subtract ~7mm (~83px) padding

    if orientation == "rotated":
        img_width = length_px
        img_height = width_px
    else:
        img_width = width_px
        img_height = length_px

    image = Image.new("RGB", (img_width, img_height), "white")
    draw = ImageDraw.Draw(image)

    fonts = []
    for face, bold, italic, size in [(face1, bold1, italic1, size1), (face2, bold2, italic2, size2), (face3, bold3, italic3, size3)]:
        font_path = get_font_path(face, bold, italic)
        fonts.append(ImageFont.truetype(font_path, size))

    lines = [
        (text1.splitlines(), fonts[0], bg1, underline1, justify1),
        (text2.splitlines(), fonts[1], bg2, underline2, justify2),
        (text3.splitlines(), fonts[2], bg3, underline3, justify3)
    ]
    y_offset = 0
    spacings = [int(spacing1), int(spacing2)]  # Convert to integers

    start_y = 0
    section_index = 0

    for text_lines, font, bg_color, underline, justify in lines:
        if not text_lines:
            if section_index < 2:  # Only increment y_offset if not the last section
                y_offset += spacings[section_index]
                section_index += 1
            continue
        if bg_color != "white":
            draw.rectangle([0, start_y + y_offset, img_width, start_y + y_offset + len(text_lines) * (font.size + 10)], fill=bg_color)
        for line in text_lines:
            if not line:
                y_offset += font.size + 10  # Default line spacing within a section
                continue
            parts = []
            current_text = ""
            current_color = "black" if bg_color == "white" else "white"
            i = 0
            while i < len(line):
                if line[i:i+3] == "[[[":
                    if current_text:
                        parts.append((current_text, current_color))
                    current_text = ""
                    current_color = "white"
                    i += 3
                elif line[i:i+3] == "]]]":
                    if current_text:
                        parts.append((current_text, current_color))
                    current_text = ""
                    current_color = "black" if bg_color == "white" else "white"
                    i += 3
                elif line[i:i+2] == "[[":
                    if current_text:
                        parts.append((current_text, current_color))
                    current_text = ""
                    current_color = "red" if tape_type == "red_black" else "black"
                    i += 2
                elif line[i:i+2] == "]]":
                    if current_text:
                        parts.append((current_text, current_color))
                    current_text = ""
                    current_color = "black" if bg_color == "white" else "white"
                    i += 2
                else:
                    current_text += line[i]
                    i += 1
            if current_text:
                parts.append((current_text, current_color))

            line_width = sum(draw.textbbox((0, 0), part[0], font=font)[2] - draw.textbbox((0, 0), part[0], font=font)[0] for part in parts if part[0])
            if line_width > img_width:
                scale_factor = img_width / line_width
                scaled_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", int(font.size * scale_factor))
            else:
                scaled_font = font

            if justify == "center":
                x = (img_width - line_width) // 2
            elif justify == "right":
                x = img_width - line_width
            else:  # left
                x = 0

            for part_text, part_color in parts:
                if part_text:
                    text_bbox = draw.textbbox((0, 0), part_text, font=scaled_font)
                    text_width = text_bbox[2] - text_bbox[0]
                    draw.text((x, start_y + y_offset), part_text, font=scaled_font, fill=part_color)
                    if underline:
                        draw.line([x, start_y + y_offset + scaled_font.size, x + text_width, start_y + y_offset + scaled_font.size], fill=part_color, width=2)
                    x += text_width
            y_offset += scaled_font.size + 10  # Spacing within a section

        # Add spacing between sections
        if section_index < 2:  # Only increment y_offset if not the last section
            y_offset += spacings[section_index]
            section_index += 1

    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    else:
        image = Image.new("RGB", (1, 1), "white")

    if orientation == "rotated":
        image = image.rotate(90, expand=True)

    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return img_str

def generate_qr_code_image(url, box_size=10):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=0,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    return qr_img
