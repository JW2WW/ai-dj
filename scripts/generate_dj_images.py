"""Generate default DJ profile images (placeholder avatars).

Creates simple gradient-background images with DJ initials
for the 4 default personas. Run once to populate assets/dj_images/.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageColor

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "dj_images"

DJ_IMAGES = {
    "morning_mike": {"initials": "MM", "bg": "#4A90E2", "fg": "white"},
    "night_nina": {"initials": "NN", "bg": "#E24A90", "fg": "white"},
    "sunny_sam": {"initials": "SS", "bg": "#F5A623", "fg": "white"},
    "late_night_leo": {"initials": "LL", "bg": "#7B68EE", "fg": "white"},
}

SIZE = (220, 260)


def generate_default_images():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Try to get a nice bold font
        font = ImageFont.truetype("arial.ttf", 72)
    except (OSError, IOError):
        font = ImageFont.load_default()

    for dj_id, info in DJ_IMAGES.items():
        bg_rgb = ImageColor.getrgb(info["bg"])
        img = Image.new("RGB", SIZE, color=info["bg"])
        draw = ImageDraw.Draw(img)

        # Draw a slightly darker bottom gradient effect
        for y in range(SIZE[1] - 60, SIZE[1]):
            shade = 0.7 + 0.3 * (1 - (SIZE[1] - y) / 60)
            r, g, b = int(bg_rgb[0] * shade), int(bg_rgb[1] * shade), int(bg_rgb[2] * shade)
            draw.line([(0, y), (SIZE[0], y)], fill=(r, g, b))

        # Draw initials centered
        bbox = draw.textbbox((0, 0), info["initials"][0], font=font)
        tw = bbox[2] - bbox[0]
        x = (SIZE[0] - tw) // 2
        y = SIZE[1] // 2 - 40
        draw.text((x, y), info["initials"][0], fill=info["fg"], font=font)

        # Save as JPEG
        out_path = OUTPUT_DIR / f"{dj_id}.jpg"
        img.save(out_path, "JPEG", quality=85)
        print(f"Created {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    generate_default_images()