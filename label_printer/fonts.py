import glob
import os
from PIL import ImageFont
from label_printer.config import FONT_DIR, logger

def scan_fonts():
    logger.debug(f"Scanning fonts in directory: {FONT_DIR}")
    font_files = glob.glob(os.path.join(FONT_DIR, "**/*.ttf"), recursive=True)
    font_families = {}
    for font_path in font_files:
        logger.debug(f"Found font file: {font_path}")
        try:
            ImageFont.truetype(font_path, size=10)
            font_name = os.path.basename(font_path).replace('.ttf', '')
            family = font_name.split('-')[0] if '-' in font_name else font_name
            if family not in font_families:
                font_families[family] = []
            font_families[family].append(font_path)
            logger.debug(f"Added font: {font_name} (family: {family})")
        except Exception as e:
            logger.warning(f"Skipping font {font_path}: {str(e)}")
            continue
    logger.debug(f"Usable font families: {sorted(font_families.keys())}")
    return font_families

font_families = scan_fonts()

def get_font_path(family, bold, italic):
    if family not in font_families:
        logger.debug(f"Font family {family} not found, using DejaVuSans.ttf")
        return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    styles = []
    if bold:
        styles.append("Bold")
    if italic:
        styles.append("Oblique" if "Oblique" in "".join(font_families[family]) else "Italic")
    style_suffix = "".join(styles)
    font_name = f"{family}{'-' + style_suffix if style_suffix else ''}.ttf"

    for path in font_families[family]:
        if font_name in path:
            return path
    plain_font = f"{family}.ttf"
    for path in font_families[family]:
        if plain_font in path:
            logger.debug(f"Style {style_suffix} not found for {family}, using {plain_font}")
            return path

    logger.debug(f"No matching style for {family}, using first available font")
    return font_families[family][0]
