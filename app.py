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


def build_image(photo_url, beds, baths, price, neighborhood, description):
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

    photo_el = (
        f'\n  <image x="0" y="0" width="1084.35" height="847" '
        f'preserveAspectRatio="xMidYMid slice" '
        f'xlink:href="data:image/jpeg;base64,{img_b64}"/>'
    )
    svg = svg.replace('<rect x="3.45" y="1117.39"', photo_el + '\n  <rect x="3.45" y="1117.39"')

    svg = re.sub(r'(<tspan x="0" y="0">)9 BED(</tspan>)', rf'\g<1>{beds} BED\2', svg)
    svg = re.sub(r'(<tspan x="0" y="0">)11 BATH(</tspan>)', rf'\g<1>{baths} BATH\2', svg)
    svg = re.sub(
        r'(<tspan x="0" y="0">\$)5,500,000(</tspan>)',
        rf'\g<1>{price.replace("$", "")}\2',
        svg,
    )
    svg = re.sub(r'(<tspan x="0" y="0">)WOODLAND HILLS(</tspan>)', rf'\g<1>{neighborhood}\2', svg)

    lines = textwrap.wrap(description, width=44)[:10]
    tspans = "".join(f'<tspan x="0" y="{i * 49.2:.1f}">{line}</tspan>' for i, line in enumerate(lines))
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

    try:
        filename = build_image(
            data["photo_url"],
            str(data["beds"]),
            str(data["baths"]),
            str(data["price"]),
            str(data["neighborhood"]).upper(),
            str(data["description"])[:300],
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
