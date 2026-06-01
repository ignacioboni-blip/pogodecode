#!/usr/bin/env python3
"""Generate labelled UI mockups for the README (not real screenshots)."""
import os
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
BOLD = "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def f(path, size):
    return ImageFont.truetype(path, size)


# palette
BG = (240, 240, 240)
PANE = (255, 255, 255)
BORDER = (200, 200, 200)
TXT = (30, 30, 30)
DIM = (110, 110, 110)
ACCENT = (45, 110, 210)
SEL = (210, 228, 250)
TITLEBAR = (225, 225, 228)
BTN = (250, 250, 250)


def chrome(d, w, title):
    """Draw a neutral OS-style title bar; returns the y where content starts."""
    d.rectangle([0, 0, w, 34], fill=TITLEBAR)
    d.line([0, 34, w, 34], fill=BORDER)
    d.ellipse([12, 12, 22, 22], outline=(150, 150, 150))
    d.text((34, 9), title, font=f(BOLD, 13), fill=(60, 60, 60))
    for i, gx in enumerate((w - 66, w - 44, w - 22)):
        d.text((gx, 8), ("—", "□", "✕")[i], font=f(FONT, 13), fill=(90, 90, 90))
    return 35


def button(d, x, y, label, pad=10, h=26, fill=BTN, fg=TXT, fnt=None):
    fnt = fnt or f(FONT, 13)
    tw = d.textlength(label, font=fnt)
    d.rounded_rectangle([x, y, x + tw + pad * 2, y + h], radius=5, fill=fill, outline=BORDER)
    d.text((x + pad, y + (h - 15) // 2), label, font=fnt, fill=fg)
    return x + tw + pad * 2


def field(d, x, y, w, text, h=26):
    d.rounded_rectangle([x, y, x + w, y + h], radius=4, fill=PANE, outline=BORDER)
    d.text((x + 8, y + (h - 15) // 2), text, font=f(FONT, 13), fill=TXT)


# ---------------------------------------------------------------- VIEWER
def viewer():
    W, H = 1000, 700
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y0 = chrome(d, W, "PoGo Pokédex Viewer v1.0.0")

    # menu bar
    d.rectangle([0, y0, W, y0 + 24], fill=BG)
    mx = 10
    for m in ("File", "Help"):
        d.text((mx, y0 + 4), m, font=f(FONT, 13), fill=TXT)
        mx += int(d.textlength(m, font=f(FONT, 13))) + 18
    y0 += 25

    # toolbar
    button(d, 12, y0 + 8, "Open GAME_MASTER / JSON…")
    d.text((230, y0 + 13), "GAME_MASTER  (18,707 templates)", font=f(FONT, 13), fill=DIM)
    bx = W - 12 - (d.textlength("Export sheets → JSON", font=f(FONT, 13)) + 20)
    button(d, bx, y0 + 8, "Export sheets → JSON")
    y0 += 44

    # tabs
    tabs = ["Pokédex", "Compare", "Moves", "Type Chart", "Weather",
            "Items", "Leagues", "Templates", "Validation", "Diff"]
    tx = 12
    for i, t in enumerate(tabs):
        tw = d.textlength(t, font=f(FONT, 12)) + 18
        active = i == 0
        d.rounded_rectangle([tx, y0, tx + tw, y0 + 26], radius=4,
                            fill=PANE if active else BG, outline=BORDER)
        d.text((tx + 9, y0 + 6), t, font=f(BOLD if active else FONT, 12),
               fill=ACCENT if active else TXT)
        tx += tw + 3
    y0 += 26
    d.rectangle([12, y0, W - 12, H - 26], fill=PANE, outline=BORDER)

    # filter bar
    fy = y0 + 10
    d.text((24, fy + 4), "Search:", font=f(FONT, 12), fill=TXT)
    field(d, 78, fy, 120, "char", h=22)
    d.text((212, fy + 4), "Type:", font=f(FONT, 12), fill=TXT)
    field(d, 252, fy, 90, "All  ▾", h=22)
    d.text((356, fy + 4), "Sort:", font=f(FONT, 12), fill=TXT)
    field(d, 396, fy, 100, "Max CP  ▾", h=22)
    button(d, W - 165, fy - 1, "📌 Add to Compare", pad=8, h=23, fnt=f(FONT, 12))
    y0 = fy + 34

    # left list
    lx, lw = 24, 210
    d.rectangle([lx, y0, lx + lw, H - 40], fill=PANE, outline=BORDER)
    names = ["#0003  Venusaur", "#0006  Charizard", "#0006  Mega X Charizard",
             "#0006  Mega Y Charizard", "#0009  Blastoise", "#0065  Alakazam",
             "#0094  Gengar", "#0130  Gyarados", "#0149  Dragonite",
             "#0150  Mewtwo", "#0248  Tyranitar", "#0282  Gardevoir",
             "#0376  Metagross", "#0445  Garchomp", "#0448  Lucario"]
    ly = y0 + 4
    for i, n in enumerate(names):
        if i == 1:
            d.rectangle([lx + 2, ly - 1, lx + lw - 2, ly + 17], fill=SEL)
        d.text((lx + 8, ly), n, font=f(FONT, 12), fill=TXT)
        ly += 19

    # detail pane
    dx = lx + lw + 14
    d.text((dx, y0), "Charizard", font=f(BOLD, 20), fill=TXT)
    d.text((dx + 130, y0 + 6), "[V0006_POKEMON_CHARIZARD]", font=f(MONO, 11), fill=DIM)
    sy = y0 + 36
    rows = [
        ("Type", "Fire / Flying"),
        ("Stats", "Atk 223   Def 173   Sta 186"),
        ("Max CP", "L40 2889   /   L50 3266   /   L51 best-buddy 3305"),
        ("Size", "1.7 m  /  90.5 kg"),
        ("Capture", "5.0%"),
    ]
    for k, v in rows:
        d.text((dx, sy), k, font=f(BOLD, 13), fill=DIM)
        d.text((dx + 90, sy), v, font=f(MONO, 13), fill=TXT)
        sy += 24
    sy += 6
    d.text((dx, sy), "Fast moves", font=f(BOLD, 13), fill=ACCENT); sy += 22
    for m in ["Fire Spin (Fire)   power 13, energy 9, 1.0s   13.0 DPS / 9.0 EPS",
              "Air Slash (Flying)  power 12, energy 8, 1.0s   12.0 DPS / 8.0 EPS"]:
        d.text((dx + 14, sy), m, font=f(MONO, 12), fill=TXT); sy += 20
    sy += 6
    d.text((dx, sy), "Charge moves", font=f(BOLD, 13), fill=ACCENT); sy += 22
    for m in ["Fire Blast (Fire)    power 140, energy 100, 4.0s   35.0 DPS",
              "Dragon Claw (Dragon) power  45, energy  33, 1.5s   30.0 DPS",
              "Overheat (Fire)      power 160, energy 100, 4.0s   40.0 DPS",
              "Air Cutter (Flying)  power  55, energy  50, 2.5s   22.0 DPS"]:
        d.text((dx + 14, sy), m, font=f(MONO, 12), fill=TXT); sy += 20
    sy += 6
    d.text((dx, sy), "Weaknesses", font=f(BOLD, 13), fill=(200, 60, 60)); sy += 20
    d.text((dx + 14, sy), "Rock ×2.56   Water ×1.6   Electric ×1.6", font=f(MONO, 12), fill=TXT)

    # status bar
    d.rectangle([0, H - 22, W, H], fill=TITLEBAR)
    d.line([0, H - 22, W, H - 22], fill=BORDER)
    d.text((10, H - 19), "Loaded 18,707 templates  ·  2,577 Pokémon forms  ·  ready",
           font=f(FONT, 12), fill=DIM)

    img.save("docs/screenshots/viewer.png")
    print("wrote docs/screenshots/viewer.png")


# --------------------------------------------------------------- DECODER
def decoder():
    W, H = 700, 500
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y0 = chrome(d, W, "PoGo GAME_MASTER Decoder v1.0.0") + 16

    d.text((20, y0), "Input GAME_MASTER file", font=f(BOLD, 13), fill=TXT)
    y0 += 22
    field(d, 20, y0, W - 140, "C:\\Users\\me\\Downloads\\GAME_MASTER")
    button(d, W - 110, y0, "Browse…", pad=12)
    y0 += 44

    d.text((20, y0), "Output JSON file", font=f(BOLD, 13), fill=TXT)
    y0 += 22
    field(d, 20, y0, W - 140, "C:\\Users\\me\\Downloads\\game_master.json")
    button(d, W - 110, y0, "Browse…", pad=12)
    y0 += 46

    button(d, 20, y0, "Decode → JSON", pad=16, h=30, fill=(45, 110, 210),
           fg=(255, 255, 255), fnt=f(BOLD, 14))
    cb_x = 200
    d.rectangle([cb_x, y0 + 6, cb_x + 16, y0 + 22], fill=PANE, outline=BORDER)
    d.line([cb_x + 3, y0 + 14, cb_x + 7, y0 + 18], fill=ACCENT, width=2)
    d.line([cb_x + 7, y0 + 18, cb_x + 13, y0 + 9], fill=ACCENT, width=2)
    d.text((cb_x + 24, y0 + 7), "Pretty-print JSON", font=f(FONT, 13), fill=TXT)
    y0 += 46

    # log
    d.rectangle([20, y0, W - 20, H - 30], fill=(28, 30, 34), outline=BORDER)
    log = [
        "Reading GAME_MASTER (2.92 MB)…",
        "Decoding protobuf wire format (schema-free)…",
        "  parsed 18,707 templates",
        "  templatesById: 18,707 keys",
        "  categories: 1,598",
        "Writing JSON → game_master.json",
        "Done in 4.1s  ·  18.9 MB written",
        "✓ Success",
    ]
    ly = y0 + 10
    for line in log:
        col = (120, 230, 140) if line.startswith("✓") else (210, 210, 210)
        d.text((30, ly), line, font=f(MONO, 12), fill=col)
        ly += 19

    d.rectangle([0, H - 22, W, H], fill=TITLEBAR)
    d.line([0, H - 22, W, H - 22], fill=BORDER)
    d.text((10, H - 19), "Done  ·  game_master.json", font=f(FONT, 12), fill=DIM)

    img.save("docs/screenshots/decoder.png")
    print("wrote docs/screenshots/decoder.png")


if __name__ == "__main__":
    os.makedirs("docs/screenshots", exist_ok=True)
    viewer()
    decoder()
