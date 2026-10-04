# Demon Bunker's look: the palette, shading, textures, sprites, the guns, the status bar digits, and
# the tables the renderer (bunker_draw) reads. Built once at start, under the boot bar (bunker.py).
import random, framebuf, struct
from lcd import color
import bunker_draw as R

VH = 184                    # 3D view height, px; the status bar is under it
NC = 120                    # view columns, 2 px each
B = 65536                   # bias: the ptr32 arrays only hold values >= 0

# The 16 colors (lcd.PALETTE): a grey ramp from black to white, then green, dark green, red,
# yellow, blue. RAMP[i] is the i-th grey.
RAMP = [color(v, v, v) for v in (0, 26, 60, 90, 120, 148, 169, 195, 216, 236, 254)]
K, W = RAMP[0], RAMP[10]
GR, GD = color(34, 196, 82), color(22, 140, 52)
RD, YL, BL = color(227, 49, 44), color(255, 220, 0), color(40, 100, 230)
CH = {"k": K, "w": W, "g": GR, "G": GD, "r": RD, "y": YL, "b": BL}
for _i in range(1, 10):
    CH[str(_i)] = RAMP[_i]
CLEAR = 16                  # a texel that isn't drawn

# Shading: SH[lvl * 16 + c] is color c seen from distance level lvl (0 near .. 5 far); level 6 is a
# white flash (a monster that was just hit).
SH = bytearray(7 * 16)


def _darker(c, n):
    if c in RAMP:
        return RAMP[max(1, RAMP.index(c) - n)] if c != K else K
    fade = {GR: (GR, GD, GD, RAMP[3], RAMP[2], RAMP[1]), GD: (GD, GD, RAMP[2], RAMP[2], RAMP[1], RAMP[1]),
            RD: (RD, RD, RD, RAMP[3], RAMP[2], RAMP[1]), YL: (YL, YL, RAMP[7], RAMP[5], RAMP[3], RAMP[2]),
            BL: (BL, BL, BL, RAMP[2], RAMP[2], RAMP[1])}
    return fade[c][min(n, 5)]


for _l in range(6):
    for _c in range(16):
        SH[_l * 16 + _c] = _darker(_c, _l)
for _c in range(16):
    SH[96 + _c] = W

# Ceiling and floor: one byte (two pixels) per row, dithered between two greys for a gradient.
ROWC = bytearray(VH)
for _y in range(VH):
    if _y < VH // 2:
        _t = (_y * 6) // (VH // 2)                       # 0 at the top .. 5 at the horizon
        _a, _b = (RAMP[3], RAMP[3], RAMP[2], RAMP[2], RAMP[1], RAMP[1])[_t], (RAMP[3], RAMP[2], RAMP[2], RAMP[1], RAMP[1], K)[_t]
    else:
        _t = ((_y - VH // 2) * 6) // (VH // 2)            # 0 at the horizon .. 5 at the bottom
        _a, _b = (K, RAMP[1], RAMP[1], RAMP[2], RAMP[2], RAMP[3])[_t], (RAMP[1], RAMP[1], RAMP[2], RAMP[2], RAMP[3], RAMP[4])[_t]
    if _y & 1:
        _a, _b = _b, _a
    ROWC[_y] = (_a << 4) | _b

SIN = [0] * 1024
import math
for _i in range(1024):
    SIN[_i] = int(math.sin(_i * math.pi / 512) * 4096)
del math


def cos(a):
    return SIN[(a + 256) & 1023]


def sin(a):
    return SIN[a & 1023]


# The arrays viper reads as ptr32 are bytearrays (4 bytes a value, little-endian): the emulator's
# ptr32 works on bytes only. Python writes them with put().
CAMT = bytearray(4 * NC)                   # each column's camera x, -4096..4096, biased
for _x in range(NC):
    struct.pack_into("<i", CAMT, 4 * _x, ((2 * _x + 1 - NC) * 4096) // NC + B)
ZB = bytearray(4 * NC)                     # each column's wall depth, 1/256 cell
ST = bytearray(4 * 8)                      # what cast() reads: px, py, dir, plane, map width, VH
SA = bytearray(4 * 9)                      # what spr() reads


def put(a, i, v):
    struct.pack_into("<i", a, 4 * i, v)


R.ZB, R.SH, R.ROWC, R.CAMT = ZB, SH, ROWC, CAMT       # the tables the renderer reads

# ---- textures: 16x16, stored a column at a time (tex * 256 + x * 16 + y) ----------------------

NTEX = 7
TEX = bytearray(NTEX * 256)


def _tex(i, draw):
    fb = framebuf.FrameBuffer(bytearray(256), 16, 16, framebuf.GS8)
    draw(fb)
    for x in range(16):
        for y in range(16):
            TEX[i * 256 + x * 16 + y] = fb.pixel(x, y)


def _stone(fb):
    fb.fill(RAMP[5])
    for y in range(16):
        for x in range(16):
            r = random.getrandbits(3)
            if r == 0:
                fb.pixel(x, y, RAMP[4])
            elif r == 1:
                fb.pixel(x, y, RAMP[6])
    for y, x0 in ((0, 0), (5, 4), (10, 9), (15, 2)):
        fb.hline(0, y, 16, RAMP[3])
    for x, y0 in ((4, 0), (12, 0), (9, 5), (1, 5), (14, 10), (6, 10)):
        fb.vline(x, y0, 5, RAMP[3])


def _brick(fb):
    fb.fill(RD)
    for y in (3, 7, 11, 15):
        fb.hline(0, y, 16, RAMP[2])
    for y in range(4):
        x = 7 if y & 1 else 3
        fb.vline(x, y * 4, 3, RAMP[2])
        fb.vline(x + 8, y * 4, 3, RAMP[2])
    for _ in range(14):
        fb.pixel(random.getrandbits(4), random.getrandbits(4), RAMP[3])


def _tech(fb):
    fb.fill(RAMP[3])
    fb.rect(0, 0, 16, 16, RAMP[2])
    fb.fill_rect(2, 2, 12, 5, RAMP[2])
    fb.fill_rect(3, 3, 10, 3, GD)
    fb.hline(3, 4, 10, GR)
    fb.fill_rect(2, 9, 5, 5, RAMP[4])
    fb.fill_rect(9, 9, 5, 5, RAMP[4])
    fb.pixel(4, 11, YL)
    fb.pixel(11, 11, RD)


def _metal(fb):
    fb.fill(RAMP[4])
    for x in (0, 8):
        fb.vline(x, 0, 16, RAMP[2])
        fb.vline(x + 1, 0, 16, RAMP[6])
    for x in (3, 11):
        for y in (2, 13):
            fb.pixel(x, y, RAMP[7])
            fb.pixel(x + 1, y + 1, RAMP[2])


def _door(fb, band=None):
    fb.fill(RAMP[6])
    fb.rect(0, 0, 16, 16, RAMP[3])
    for y in range(2, 15, 3):
        fb.hline(2, y, 12, RAMP[4])
    fb.vline(8, 1, 14, RAMP[3])
    if band is not None:
        fb.fill_rect(1, 6, 14, 4, band)
        fb.hline(1, 6, 14, K)
        fb.hline(1, 9, 14, K)


def _exit(fb):
    fb.fill(RAMP[3])
    fb.rect(1, 1, 14, 14, RAMP[6])
    fb.fill_rect(5, 3, 6, 10, K)
    fb.fill_rect(6, 4, 4, 3, GR)
    fb.fill_rect(6, 9, 4, 3, RD)
    fb.pixel(2, 2, YL)
    fb.pixel(13, 2, YL)


random.seed(3)
for _i, _d in enumerate((_stone, _brick, _tech, _metal, _door, lambda fb: _door(fb, RD), _exit)):
    _tex(_i, _d)

# map cells: 0 floor, 1.. a wall with texture n-1
WALLS = {"#": 1, "%": 2, "=": 3, "|": 4, "D": 5, "R": 6, "E": 7}
DOOR, RDOOR, EXIT = 5, 6, 7

# ---- sprites: 16x16, column-major like the textures; '.' clear -----------------------------------

ART = {
    "imp": [
        "....k.....k.....",
        "....rk...kr.....",
        ".....rrrrr......",
        "....rr6r6rr.....",
        "....rryryrr.....",
        ".....rkkkr......",
        "..k.rrrrrrr.k...",
        "..rrr3rrr3rrr...",
        "...rr3rrr3rr....",
        "....rrrrrrr.....",
        "....r3rrr3r.....",
        ".....rr.rr......",
        ".....r3.3r......",
        ".....rr.rr......",
        "....krr.rrk.....",
        "....kk...kk.....",
    ],
    "imp_atk": [
        "y...k.....k...y.",
        "yy..rk...kr..yy.",
        ".yr..rrrrr..ry..",
        "..rrrr6r6rrrr...",
        "....rryryrr.....",
        ".....rwwwr......",
        "....rrkkkrr.....",
        "....r3rrr3r.....",
        "....rr3r3rr.....",
        "....rrrrrrr.....",
        "....r3rrr3r.....",
        ".....rr.rr......",
        ".....r3.3r......",
        ".....rr.rr......",
        "....krr.rrk.....",
        "....kk...kk.....",
    ],
    "imp_dead": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "......r.........",
        "...r.rrr..r.....",
        "..rrrr3rrrrr.r..",
        ".rrrkrrrr3rrrrr.",
        "rr3rrrrrrrrrr3rr",
    ],
    "demon": [
        "................",
        "................",
        "...rr.....rr....",
        "..r9rrrrrrr9r...",
        "..rrrr6r6rrrr...",
        ".rrrrrrrrrrrrr..",
        ".rr3wkwkwkw3rr..",
        ".rr3kwkwkwk3rr..",
        ".rrrrrrrrrrrrr..",
        "..rr3rrrrr3rr...",
        "..rrrrrrrrrrr...",
        "...rr3rrr3rr....",
        "...rr.....rr....",
        "..r3r.....r3r...",
        "..rrk.....krr...",
        "..kk.......kk...",
    ],
    "demon_atk": [
        "................",
        "...rr.....rr....",
        "..r9rrrrrrr9r...",
        "..rrrr6r6rrrr...",
        ".rrrrrrrrrrrrr..",
        ".rr3wkwkwkw3rr..",
        ".rr3kkkkkkk3rr..",
        ".rr3kkkrkkk3rr..",
        ".rr3wkwkwkw3rr..",
        "..rr3rrrrr3rr...",
        "..rrrrrrrrrrr...",
        "...rr3rrr3rr....",
        "...rr.....rr....",
        "..r3r.....r3r...",
        "..rrk.....krr...",
        "..kk.......kk...",
    ],
    "demon_dead": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "....rr..r.......",
        "..rrrrr3rrr.r...",
        ".rr3wkwrrrrrrrr.",
        "rrrrrr3rrrr3rrrr",
    ],
    "zombie": [
        "......666.......",
        ".....67776......",
        ".....7k7k7......",
        ".....67776......",
        "......4r4.......",
        "....GGGGGGG.....",
        "...GGGG4GGGG....",
        "...GG.GGG.GG....",
        "...GG.GGG.GG....",
        "...77.G4G.77....",
        "......3333......",
        ".....33..33.....",
        ".....33..33.....",
        ".....33..33.....",
        ".....22..22.....",
        "....222..222....",
    ],
    "zombie_atk": [
        "......666.......",
        ".....67776......",
        ".....7k7k7......",
        ".....67776......",
        "......4r4.......",
        "....GGGGGGG.....",
        "...GGGG4GGGG...y",
        "...GGGGGG77222yy",
        "...GG.GGG.......",
        "...77.G4G.......",
        "......3333......",
        ".....33..33.....",
        ".....33..33.....",
        ".....33..33.....",
        ".....22..22.....",
        "....222..222....",
    ],
    "zombie_dead": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "......rr........",
        "..666.rGGGG33...",
        ".67k7GGGrGGG3322",
        "..666GGGGGG33322",
    ],
    "med": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "....88888888....",
        "...8wwwwwwww8...",
        "...8wwwrrwww8...",
        "...8wwwrrwww8...",
        "...8wrrrrrrw8...",
        "...8wwwrrwww8...",
        "...8wwwrrwww8...",
        "...8wwwwwwww8...",
        "....88888888....",
    ],
    "clip": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "......yyy.......",
        "......y3y.......",
        ".....GGGGG......",
        ".....GyyyG......",
        ".....GGGGG......",
        ".....G333G......",
        ".....GGGGG......",
    ],
    "shells": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "...rrrrrrrrr....",
        "...ryyryyryr....",
        "...rrrrrrrrr....",
        "...r3rr3rr3r....",
        "...r3rr3rr3r....",
        "...rrrrrrrrr....",
        "................",
    ],
    "shotgun": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "...2222222222...",
        "..k5555555222...",
        "..2222222.333...",
        ".........3333...",
        "..........333...",
        "................",
    ],
    "key": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "......rrr.......",
        ".....r...r......",
        ".....r...r......",
        "......rrr.......",
        ".......r........",
        ".......rr.......",
        ".......rrr......",
    ],
    "ball": [
        "................",
        "................",
        "................",
        "................",
        "......yyy.......",
        ".....yywyy......",
        "....ryywwyr.....",
        "....rywwwyr.....",
        "....ryywyyr.....",
        ".....rryrr......",
        "......rrr.......",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
    "barrel": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "....GGGGGGG.....",
        "...g5555555g....",
        "...5g55555g5....",
        "...55555555g....",
        "...4444444444...",
        "...5555555555...",
        "...55gg5g5555...",
        "...4444444444...",
        "...5555555555...",
        "...5555555555...",
        "....4444444.....",
    ],
    "boom": [
        "................",
        "...y......y.....",
        ".....yyyyy...y..",
        "..yyyrrrrryy....",
        ".yyrrrwwwrrryy..",
        "..yrrwwwwwwrry..",
        ".yrrwwwyywwwrry.",
        ".yrwwyyyyyywwry.",
        ".yrwwyyyyyywwry.",
        ".yrrwwwyywwwrry.",
        "..yrrwwwwwwrry..",
        ".yyrrrwwwrrryy..",
        "..yyyrrrrryy....",
        ".....yyyyy...y..",
        "...y......y.....",
        "................",
    ],
}
FR = {}
SPR = bytearray(len(ART) * 256)
for _i, (_n, _rows) in enumerate(ART.items()):
    FR[_n] = _i * 256
    for _y, _r in enumerate(_rows):
        for _x, _ch in enumerate(_r):
            SPR[_i * 256 + _x * 16 + _y] = CLEAR if _ch == "." else CH[_ch]
del ART

# ---- the guns: 24x20 art drawn 3x into 4-bit framebufs (72x72, the top 12 rows for the flash),
# blitted with GKEY clear --------------------------------------------------------------------------

GKEY = BL

GUNS = {
    "pistol": [
        "..........4444..........",
        ".........456654.........",
        ".........456654.........",
        ".........356653.........",
        ".........356653.........",
        ".........355553.........",
        "........23555532........",
        "........23533532........",
        "........22222222........",
        ".......7722222277.......",
        "......778822228877......",
        ".....77888822888877.....",
        "....7788888888888877....",
        "....7888888888888887....",
        "...778888888888888877...",
        "...788888888888888887...",
        "..77888888888888888877..",
        "..78888888888888888887..",
        ".7788888888888888888877.",
        ".7888888888888888888887.",
    ],
    "shotgun": [
        "..........4444..........",
        ".........466664.........",
        ".........466664.........",
        ".........455554.........",
        ".........455554.........",
        ".........455554.........",
        "........34555543........",
        "........33333333........",
        ".......3666666663.......",
        ".......3555555553.......",
        ".......3666666663.......",
        ".......3444444443.......",
        "......773333333377......",
        ".....77883333338877.....",
        "....7788883333888877....",
        "....7888888338888887....",
        "...778888888888888877...",
        "...788888888888888887...",
        "..77888888888888888877..",
        "..78888888888888888887..",
    ],
}


def _gun(rows, flash):
    fb = framebuf.FrameBuffer(bytearray(72 * 72 // 2), 72, 72, framebuf.GS4_HMSB)
    fb.fill(GKEY)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch != ".":
                fb.fill_rect(x * 3, y * 3 + 12, 3, 3, CH[ch])
    if flash:
        fb.ellipse(36, 10, 14, 10, YL, True)
        fb.ellipse(36, 11, 7, 6, W, True)
        for dx, dy in ((-16, -2), (15, 1), (-7, -9), (8, -9)):
            fb.fill_rect(36 + dx, 10 + dy, 3, 3, RD)
    return fb


GUNFB = [[_gun(GUNS[n], f) for f in (0, 1)] for n in ("pistol", "shotgun")]
del GUNS

# ---- status bar digits: the 8x8 font at 2x, red with a black shadow, made once --------------------

DIG = []
for _d in "0123456789%":
    _m = framebuf.FrameBuffer(bytearray(8), 8, 8, framebuf.MONO_HLSB)
    _m.text(_d, 0, 0, 1)
    _f = framebuf.FrameBuffer(bytearray(18 * 18 // 2), 18, 18, framebuf.GS4_HMSB)
    _f.fill(GKEY)
    for _pass, _c in ((2, K), (0, RD)):
        for _y in range(8):
            for _x in range(8):
                if _m.pixel(_x, _y):
                    _f.fill_rect(_x * 2 + _pass, _y * 2 + _pass, 2, 2, _c)
    DIG.append(_f)

