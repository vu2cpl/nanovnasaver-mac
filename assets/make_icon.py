#!/usr/bin/env python3
"""Generate a polished 1024x1024 macOS-style app icon from the NanoVNASaver
Smith-chart logo: rounded-square (Apple icon-grid proportions) with a subtle
vertical gradient background and the logo centered with safe-area padding.
"""
import sys
from PIL import Image, ImageDraw

SRC = sys.argv[1]
OUT = sys.argv[2]

SIZE = 1024
# Apple macOS icon grid: the rounded-square shape is 824x824 within 1024,
# centered (100px margin), with a corner radius of ~185.
SHAPE = 824
MARGIN = (SIZE - SHAPE) // 2
RADIUS = 185
# Supersample for smooth edges/gradient, then downscale.
SS = 4

W = SIZE * SS

# 1. Subtle vertical gradient (white -> light blue) for the square fill.
grad = Image.new("RGB", (1, SHAPE * SS))
top = (255, 255, 255)
bot = (228, 239, 251)  # #e4effb
for y in range(SHAPE * SS):
    t = y / (SHAPE * SS - 1)
    grad.putpixel(
        (0, y),
        tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3)),
    )
grad = grad.resize((SHAPE * SS, SHAPE * SS))

# 2. Rounded-square mask.
mask = Image.new("L", (SHAPE * SS, SHAPE * SS), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle(
    [0, 0, SHAPE * SS - 1, SHAPE * SS - 1],
    radius=RADIUS * SS,
    fill=255,
)

# 3. Compose the square onto the full transparent canvas.
canvas = Image.new("RGBA", (W, W), (0, 0, 0, 0))
square = Image.new("RGBA", (SHAPE * SS, SHAPE * SS), (0, 0, 0, 0))
square.paste(grad, (0, 0), mask)
canvas.paste(square, (MARGIN * SS, MARGIN * SS), square)

# 4. Place the logo centered, scaled to leave breathing room inside the square.
logo = Image.open(SRC).convert("RGBA")
# Flatten any transparency in the logo onto white so the curves read cleanly.
logo_bg = Image.new("RGBA", logo.size, (255, 255, 255, 0))
logo = Image.alpha_composite(logo_bg, logo)

target = int(SHAPE * SS * 0.66)  # ~66% of the square
lw, lh = logo.size
scale = target / max(lw, lh)
logo = logo.resize((round(lw * scale), round(lh * scale)), Image.LANCZOS)
lx = (W - logo.width) // 2
ly = (W - logo.height) // 2
canvas.paste(logo, (lx, ly), logo)

# 5. Downscale to final size with high-quality resampling.
icon = canvas.resize((SIZE, SIZE), Image.LANCZOS)
icon.save(OUT)
print(f"wrote {OUT} ({icon.size[0]}x{icon.size[1]})")
