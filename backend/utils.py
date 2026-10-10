import os
import io
import math
import zipfile
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import qrcode


def _get_font(font_names: List[str], size: int) -> ImageFont.ImageFont:
    """
    Attempt to load one of the specified TrueType fonts from system or local paths,
    falling back to PIL's default bitmap font if none are available.
    """
    windir = os.environ.get("WINDIR", "C:\\Windows")
    system_font_dir = os.path.join(windir, "Fonts")

    for name in font_names:
        # Check standard system path
        full_path = os.path.join(system_font_dir, name)
        if os.path.exists(full_path):
            try:
                return ImageFont.truetype(full_path, size)
            except Exception:
                pass
        # Check direct font name (if in current dir or registered in PIL)
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass

    return ImageFont.load_default()


def _draw_ornamental_corners(draw: ImageDraw.ImageDraw, rect: Tuple[int, int, int, int], size: int = 40, color: Tuple[int, int, int] = (197, 155, 39)):
    """Draw ornate corner brackets and flourishes around the inner certificate border."""
    x1, y1, x2, y2 = rect
    c_len = size

    # Top-Left
    draw.line([(x1 - 10, y1), (x1 + c_len, y1)], fill=color, width=3)
    draw.line([(x1, y1 - 10), (x1, y1 + c_len)], fill=color, width=3)
    draw.rectangle([x1 + 6, y1 + 6, x1 + 12, y1 + 12], fill=color)

    # Top-Right
    draw.line([(x2 + 10, y1), (x2 - c_len, y1)], fill=color, width=3)
    draw.line([(x2, y1 - 10), (x2, y1 + c_len)], fill=color, width=3)
    draw.rectangle([x2 - 12, y1 + 6, x2 - 6, y1 + 12], fill=color)

    # Bottom-Left
    draw.line([(x1 - 10, y2), (x1 + c_len, y2)], fill=color, width=3)
    draw.line([(x1, y2 + 10), (x1, y2 - c_len)], fill=color, width=3)
    draw.rectangle([x1 + 6, y2 - 12, x1 + 12, y2 - 6], fill=color)

    # Bottom-Right
    draw.line([(x2 + 10, y2), (x2 - c_len, y2)], fill=color, width=3)
    draw.line([(x2, y2 + 10), (x2, y2 - c_len)], fill=color, width=3)
    draw.rectangle([x2 - 12, y2 - 12, x2 - 6, y2 - 6], fill=color)


def _draw_gold_seal(img: Image.Image, cx: int, cy: int, radius: int = 70):
    """Draw an elegant circular gold achievement seal with notched edge and ribbon tails."""
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    d = ImageDraw.Draw(overlay)

    # Ribbon tails
    ribbon_color = (168, 128, 25, 240)
    d.polygon([(cx - 35, cy + 20), (cx - 55, cy + 120), (cx - 25, cy + 105), (cx - 10, cy + 120), (cx - 5, cy + 20)], fill=ribbon_color)
    d.polygon([(cx + 5, cy + 20), (cx + 10, cy + 120), (cx + 25, cy + 105), (cx + 55, cy + 120), (cx + 35, cy + 20)], fill=ribbon_color)

    # Serrated seal outer rim (rosette notches)
    num_teeth = 48
    points = []
    for i in range(num_teeth * 2):
        angle = i * (math.pi / num_teeth)
        r = radius if (i % 2 == 0) else (radius - 7)
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        points.append((px, py))
    d.polygon(points, fill=(212, 175, 55, 255), outline=(155, 120, 20, 255))

    # Inner concentric rings
    d.ellipse([cx - radius + 10, cy - radius + 10, cx + radius - 10, cy + radius - 10], outline=(245, 222, 120, 255), width=3)
    d.ellipse([cx - radius + 16, cy - radius + 16, cx + radius - 16, cy + radius - 16], fill=(185, 142, 30, 255), outline=(130, 95, 10, 255), width=2)

    # Seal text / star motif
    star_font = _get_font(["arial.ttf"], 28)
    d.text((cx, cy - 15), "★ ★ ★", fill=(255, 245, 200, 255), font=star_font, anchor="mm")
    text_font = _get_font(["georgia.ttf", "arial.ttf"], 13)
    d.text((cx, cy + 12), "EXCELLENCE", fill=(255, 255, 240, 255), font=text_font, anchor="mm")
    d.text((cx, cy + 28), "VERIFIED", fill=(245, 225, 160, 255), font=text_font, anchor="mm")

    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def _draw_signature(draw: ImageDraw.ImageDraw, x: int, y: int, name: str, title: str):
    """Draw a professional signature block with simulated cursive stroke and title."""
    # Simulated signature curve
    sig_color = (25, 39, 70)
    draw.line([(x - 90, y), (x + 90, y)], fill=(160, 165, 180), width=1)
    
    # Artistic cursive flourish line
    flourish_points = [
        (x - 65, y - 18), (x - 45, y - 35), (x - 20, y - 12),
        (x + 5, y - 42), (x + 35, y - 16), (x + 75, y - 28)
    ]
    for i in range(len(flourish_points) - 1):
        draw.line([flourish_points[i], flourish_points[i + 1]], fill=sig_color, width=2)
    
    name_font = _get_font(["georgia.ttf", "times.ttf", "arial.ttf"], 18)
    title_font = _get_font(["calibri.ttf", "arial.ttf"], 14)
    draw.text((x, y + 12), name, fill=(30, 41, 59), font=name_font, anchor="mm")
    draw.text((x, y + 32), title, fill=(100, 116, 139), font=title_font, anchor="mm")


def generate_certificate(
    cert_id: str,
    recipient_name: str,
    course_name: str,
    issue_date: str,
    output_path: str,
    simulate_failure: bool = False
) -> str:
    """
    Programmatically renders a high-resolution, production-grade certificate using Pillow.
    
    Features:
    - 1920x1280 crisp landscape layout.
    - Double ornamental gold & midnight borders with intricate corner brackets.
    - Guilloché background watermark motif.
    - Dynamically auto-scaled typography for recipient name.
    - Cryptographic verification QR code.
    - Gold rosette seal of excellence.
    - Official dual executive signatures.
    
    Fault Isolation Support:
    If `simulate_failure` is True or invalid inputs are encountered, raises an exception
    that must be captured by the calling background worker without halting sibling certificates.
    """
    if simulate_failure:
        raise RuntimeError(f"Simulated processing error for recipient: '{recipient_name}' (ID: {cert_id})")

    if not recipient_name or not recipient_name.strip():
        raise ValueError("Recipient name is missing or invalid.")
    if not course_name or not course_name.strip():
        raise ValueError("Course name is missing or invalid.")

    width, height = 1920, 1280
    bg_color = (252, 251, 247)  # Warm ivory parchment

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # 1. Subtle Guilloché / Rosette watermark in center background
    watermark_layer = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    wd = ImageDraw.Draw(watermark_layer)
    cx, cy = width // 2, height // 2 - 20
    for r in range(120, 380, 24):
        wd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(212, 175, 55, 14), width=2)
    img.paste(Image.alpha_composite(img.convert("RGBA"), watermark_layer).convert("RGB"))
    draw = ImageDraw.Draw(img)

    # 2. Outer Deep Midnight Border
    navy = (15, 23, 42)
    gold = (197, 155, 39)
    gold_light = (225, 190, 80)
    
    draw.rectangle([25, 25, width - 25, height - 25], outline=navy, width=12)
    draw.rectangle([45, 45, width - 45, height - 45], outline=gold_light, width=2)
    draw.rectangle([55, 55, width - 55, height - 55], outline=gold, width=4)
    draw.rectangle([65, 65, width - 65, height - 65], outline=gold_light, width=1)

    # Ornamental Corners
    _draw_ornamental_corners(draw, (55, 55, width - 55, height - 55), size=50, color=gold)

    # 3. Top Header Badges & Academy Title
    font_academy = _get_font(["calibri.ttf", "arial.ttf"], 18)
    draw.text((width // 2, 130), "• GLOBAL INSTITUTE OF PROFESSIONAL EXCELLENCE •", fill=gold, font=font_academy, anchor="mm")

    font_title = _get_font(["georgia.ttf", "times.ttf", "arial.ttf"], 62)
    draw.text((width // 2, 210), "CERTIFICATE OF ACHIEVEMENT", fill=navy, font=font_title, anchor="mm")

    # Fine divider accent line under title
    div_y = 260
    draw.line([(width // 2 - 180, div_y), (width // 2 + 180, div_y)], fill=gold, width=2)
    draw.polygon([(width // 2 - 6, div_y - 6), (width // 2 + 6, div_y - 6), (width // 2, div_y + 8)], fill=gold)

    # 4. Presentation Prompt
    font_sub = _get_font(["georgia.ttf", "calibri.ttf", "arial.ttf"], 24)
    draw.text((width // 2, 330), "THIS IS PROUDLY PRESENTED TO", fill=(100, 116, 139), font=font_sub, anchor="mm")

    # 5. Recipient Name (with auto-scaling to avoid overflow)
    name_size = 72
    if len(recipient_name) > 28:
        name_size = 54
    elif len(recipient_name) > 36:
        name_size = 44
    font_name = _get_font(["georgia.ttf", "times.ttf", "arial.ttf"], name_size)
    draw.text((width // 2, 430), recipient_name, fill=navy, font=font_name, anchor="mm")

    # Name underline bar
    name_line_y = 485
    draw.line([(width // 2 - 280, name_line_y), (width // 2 + 280, name_line_y)], fill=gold, width=3)

    # 6. Course & Completion Statement
    font_desc = _get_font(["georgia.ttf", "calibri.ttf", "arial.ttf"], 22)
    draw.text(
        (width // 2, 550),
        "for successfully fulfilling all rigorous curriculum requirements and demonstrating mastery in",
        fill=(71, 85, 105),
        font=font_desc,
        anchor="mm"
    )

    # Course Name in prominent styled font
    course_size = 46
    if len(course_name) > 40:
        course_size = 36
    font_course = _get_font(["georgia.ttf", "times.ttf", "arial.ttf"], course_size)
    draw.text((width // 2, 630), course_name, fill=(18, 55, 100), font=font_course, anchor="mm")

    # 7. Verification QR Code
    qr_url = f"https://verify.certifyforge.org/certificates/{cert_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0F172A", back_color="#FCFBF7").convert("RGB")
    qr_w, qr_h = qr_img.size
    
    qr_x, qr_y = 170, height - 320
    # Paste QR code
    img.paste(qr_img, (qr_x, qr_y))
    # Border around QR code
    draw.rectangle([qr_x - 4, qr_y - 4, qr_x + qr_w + 4, qr_y + qr_h + 4], outline=gold, width=2)
    
    font_qr_label = _get_font(["calibri.ttf", "arial.ttf"], 13)
    draw.text((qr_x + qr_w // 2, qr_y + qr_h + 16), "SCAN TO VERIFY", fill=(100, 116, 139), font=font_qr_label, anchor="mm")
    draw.text((qr_x + qr_w // 2, qr_y + qr_h + 34), f"ID: {cert_id[:16]}...", fill=(100, 116, 139), font=font_qr_label, anchor="mm")

    # 8. Gold Rosette Seal in center footer
    _draw_gold_seal(img, width // 2, height - 230, radius=72)
    draw = ImageDraw.Draw(img)

    # 9. Dual Signatures
    sig_y = height - 240
    _draw_signature(draw, width - 380, sig_y, "Dr. Arthur Pendelton", "Academic Dean")
    _draw_signature(draw, width // 2 + 180, sig_y, "Morgan Reed, M.Sc.", "Program Director")

    # 10. Date of Issue & Footer Metadata
    font_meta = _get_font(["calibri.ttf", "arial.ttf"], 16)
    draw.text((width // 2, height - 100), f"Date of Issue: {issue_date}   |   Certificate ID: {cert_id}", fill=(100, 116, 139), font=font_meta, anchor="mm")

    # Ensure target directory exists and save
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG", quality=95, optimize=True)

    return output_path


def create_job_zip(job_id: str, file_mappings: List[Tuple[str, str]], zip_output_path: str) -> str:
    """
    Assembles all successful certificate images for a job into a downloadable ZIP archive.
    `file_mappings` is a list of tuples: (source_file_path, archive_entry_name).
    """
    os.makedirs(os.path.dirname(os.path.abspath(zip_output_path)), exist_ok=True)
    with zipfile.ZipFile(zip_output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for src_path, arc_name in file_mappings:
            if os.path.exists(src_path):
                zipf.write(src_path, arcname=arc_name)

    return zip_output_path

