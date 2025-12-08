from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
src_logo = BASE_DIR / "static" / "images" / "logo_header.png"
src_hero = BASE_DIR / "static" / "images" / "mainheader.png"
fav_dir = BASE_DIR / "static" / "images" / "favicon"
fav_dir.mkdir(parents=True, exist_ok=True)

# --- FAVICONS из логотипа ---
if not src_logo.exists():
    raise FileNotFoundError(f"Logo not found: {src_logo}")

img = Image.open(src_logo).convert("RGBA")

sizes = [
    ("favicon-16x16.png", (16, 16)),
    ("favicon-32x32.png", (32, 32)),
    ("favicon-192.png", (192, 192)),
    ("favicon-512.png", (512, 512)),
]

for name, size in sizes:
    resized = img.resize(size, Image.LANCZOS)
    resized.save(fav_dir / name, format="PNG")

# Apple Touch Icon (180x180)
apple = img.resize((180, 180), Image.LANCZOS)
apple.save(fav_dir / "apple-touch-icon.png", format="PNG")

# favicon.ico (16,32,48 в одном ICO)
ico_sizes = [(16, 16), (32, 32), (48, 48)]
ico_images = [img.resize(s, Image.LANCZOS) for s in ico_sizes]
ico_path = fav_dir / "favicon.ico"
ico_images[0].save(ico_path, format="ICO", sizes=ico_sizes)

print("Favicons generated in", fav_dir)

# --- OG IMAGE из mainheader ---
if src_hero.exists():
    hero = Image.open(src_hero).convert("RGB")
    og_size = (1200, 630)
    hero = hero.resize(og_size, Image.LANCZOS)
    og_path = BASE_DIR / "static" / "images" / "og-image.jpg"
    hero.save(og_path, format="JPEG", quality=90)
    print("OG image saved to", og_path)
else:
    print("mainheader.png not found, skip og-image generation")
