import os
import re
import uuid
import base64
import textwrap
from io import BytesIO

import requests
from flask import Flask, request, jsonify, send_from_directory
from PIL import Image
import cairosvg

app = Flask(__name__)

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "off-market-template.svg")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Neighborhood values that should never appear in the white box
BLOCK_PHRASES = [
    'CONTACT AGENT', 'CONTACT LISTING', 'ADDRESS WITHHELD',
    'BY APPOINTMENT', 'UPON REQUEST', 'PRIVATE ADDRESS',
    'UNDISCLOSED', 'NOT DISCLOSED',
]
GENERIC_CITIES = {'LOS ANGELES', 'LA', 'CALIFORNIA', 'CA', 'SOUTHERN CALIFORNIA'}


def clean_photo_url(url):
    """Strip HTML entities and TAN overlay watermark parameter."""
    url = url.replace('&amp;', '&')
    url = re.sub(r'&overlay=[^&"]*', '', url)
    return url


def is_address(text):
    """Return True if text looks like a street address rather than a neighborhood."""
    if not text:
        return False
    if text[0].isdigit():
        return True
    if re.search(r'\b(ST|AVE|BLVD|DR|RD|WAY|LN|LANE|CT|PL|TER|CIR|HWY|PKWY)\b', text.upper()):
        return True
    return False


def clean_neighborhood(text):
    """
    Strip state/zip suffix, reject street addresses, block placeholder
    phrases, and reject generic city names. Returns empty string if the
    value is unusable (caller should skip the post).
    """
    if not text:
        return ""
    if is_address(text):
        return ""
    # Block TAN placeholder phrases like "Contact Agent for Address"
    upper = text.upper()
    if any(phrase in upper for phrase in BLOCK_PHRASES):
        return ""
    # Strip trailing ", CA 90265" or "CA 90265"
    text = re.sub(r',?\s*[A-Z]{2}\s+\d{5}(-\d{4})?$', '', text).strip()
    if text.upper() in GENERIC_CITIES:
        return ""
    return text


def clean_description(text):
    """Strip availability/contact boilerplate from listing descriptions."""
    stop_phrases = [
        'available now', 'available soon', 'available immediately',
        'please contact', 'contact listing', 'contact the listing',
        'contact the agent', 'contact agent', 'to schedule a',
        'call for details', 'call today', 'call for a',
        'reach out', 'for a private showing', 'for private showing',
        'for more information', 'for additional information',
        'for a showing', 'for showings', 'email for', 'dm for',
        'link in bio', 'inquire within', 'inquire today',
    ]
    text_lower = text.lower()
    earliest = len(text)
    for phrase in stop_phrases:
        idx = text_lower.find(phrase)
        if 0 < idx < earliest:
            earliest = idx
    return text[:earliest].strip().rstrip('.,; ')


def build_image(photo_url, beds, baths, price, neighborhood, description):
    photo_url = clean_photo_url(photo_url)
    resp = requests.get(photo_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content)).convert("RGB")

    target_w, target_h = 1084, 847
    ratio = img.width / img.height
    target_ratio = target_w / target_h
    if ratio > target_ratio:
        new_h = target_h
        new_w = int(ratio * new_h)
    else:
        new_w = target_w
        new_h = int(new_w / ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    img = img.crop((
        (new_w - target_w) // 2,
        (new_h - target_h) // 2,
        (new_w + target_w) // 2,
        (new_h + target_h) // 2,
    ))

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    with open(TEMPLATE_PATH) as f:
        svg = f.read()

    # Insert property photo behind the overlay frame
    photo_el = (
        f'\n  <image x="0" y="0" width="1084.35" height="847" '
        f'preserveAspectRatio="xMidYMid slice" '
        f'xlink:href="data:image/jpeg;base64,{img_b64}"/>'
    )
    svg = svg.replace('<rect x="3.45" y="1117.39"', photo_el + '\n  <rect x="3.45" y="1117.39"')

    # Fix white vertical line: extend dark description rect full width, remove stroke
    svg = svg.replace(
        '<rect x="3.45" y="1117.39" width="1079.97" height="799.37" fill="#080808" stroke="#010101" stroke-miterlimit="10"/>',
        '<rect x="0" y="1117.39" width="1084.35" height="799.37" fill="#080808"/>'
    )

    # Bed / bath / price labels
    svg = re.sub(r'(<tspan x="0" y="0">)9 BED(</tspan>)', rf'\g<1>{beds} BED\2', svg)
    svg = re.sub(r'(<tspan x="0" y="0">)11 BATH(</tspan>)', rf'\g<1>{baths} BATH\2', svg)
    svg = re.sub(
        r'(<tspan x="0" y="0">\$)5,500,000(</tspan>)',
        rf'\g<1>{price.replace("$", "")}\2',
        svg,
    )

    # Dollar sign icon: expand clipPath rect so the icon isn't cut off when
    # shifted, then nudge image slightly right and down to center in circle.
    svg = svg.replace(
        '<clipPath id="clippath-1">\n      <rect x="516.35" y="540.97" width="49.92" height="79.16" fill="#fff"/>',
        '<clipPath id="clippath-1">\n      <rect x="513.35" y="537.97" width="56" height="85" fill="#fff"/>'
    )
    svg = re.sub(
        r'(<image width="379" height="601" transform=")translate\(516\.35 540\.97\) scale\(\.13\)',
        r'\1translate(518.35 542.97) scale(.13)',
        svg
    )

    # "OFF-MARKET LOS ANGELES": replace full element — centered, smaller font
    svg = re.sub(
        r'<text transform="translate\(203\.16 380\.07\)" fill="#fff" '
        r'filter="url\(#drop-shadow-9\)" font-family="Cosmata-ExtraBold, Cosmata" '
        r'font-size="50" font-weight="700"><tspan x="0" y="0">OFF-MARKET LOS ANGELES</tspan></text>',
        '<text x="541.48" y="380.07" text-anchor="middle" fill="#fff" '
        'filter="url(#drop-shadow-9)" font-family="Cosmata-ExtraBold, Cosmata" '
        'font-size="40" font-weight="700">OFF-MARKET LOS ANGELES</text>',
        svg
    )

    # Neighborhood: replace full element — centered, dynamic font size
    neigh_len = len(neighborhood)
    if neigh_len <= 12:
        neigh_fontsize = "58"
    elif neigh_len <= 16:
        neigh_fontsize = "50"
    elif neigh_len <= 20:
        neigh_fontsize = "42"
    else:
        neigh_fontsize = "36"

    svg = re.sub(
        r'<text transform="translate\(277\.59 950\.23\)" fill="#231f20" '
        r'filter="url\(#drop-shadow-7\)" font-family="Cosmata-ExtraBold, Cosmata" '
        r'font-size="58" font-weight="700"><tspan x="0" y="0">WOODLAND HILLS</tspan></text>',
        f'<text x="545.91" y="950.23" text-anchor="middle" fill="#231f20" '
        f'filter="url(#drop-shadow-7)" font-family="Cosmata-ExtraBold, Cosmata" '
        f'font-size="{neigh_fontsize}" font-weight="700">{neighborhood}</text>',
        svg
    )

    # Description: clean boilerplate, cap at 8 lines.
    # "EMAIL US FOR DETAILS / LINK IN BIO" is already built into the SVG
    # template as vector art at y≈1694 and y≈1768 (bottom of the 9:16 image).
    description = clean_description(description)
    lines = textwrap.wrap(description, width=44)[:8]
    tspans = "".join(
        f'<tspan x="0" y="{i * 49.2:.1f}">{line}</tspan>'
        for i, line in enumerate(lines)
    )
    desc_start = svg.find('<text transform="translate(104.5233 1092.315)"')
    desc_end = svg.find("</text>", desc_start) + 7
    new_desc = (
        f'<text transform="translate(104.5233 1092.315)" fill="#fff" '
        f'font-family="Cosmata-Regular, Cosmata" font-size="41">{tspans}</text>'
    )
    svg = svg[:desc_start] + new_desc + svg[desc_end:]

    filename = f"{uuid.uuid4().hex}.png"
    out_path = os.path.join(OUTPUT_DIR, filename)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=out_path, output_width=1080, output_height=1920)
    return filename


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True)
    required = ["photo_url", "beds", "baths", "price", "neighborhood", "description"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    neighborhood = clean_neighborhood(str(data["neighborhood"]).strip()).upper()

    # Skip post if no valid neighborhood found — Make.com HTTP module will
    # stop the scenario on a 4xx response (shows as incomplete execution).
    if not neighborhood:
        return jsonify({"error": "No valid neighborhood — skipping post"}), 422

    try:
        filename = build_image(
            data["photo_url"],
            str(data["beds"]),
            str(data["baths"]),
            str(data["price"]),
            neighborhood,
            str(data["description"])[:600],
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    base_url = request.url_root.rstrip("/")
    return jsonify({"image_url": f"{base_url}/images/{filename}"})


@app.route("/images/<filename>")
def serve_image(filename):
    return send_from_directory(OUTPUT_DIR, filename, mimetype="image/png")


@app.route("/")
def health():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
