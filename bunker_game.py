# Demon Bunker: a first-person shooter in the style of Doom and Wolfenstein 3D. Walk a bunker full of
# zombies, imps and demons, find the red key, reach the exit switch. Three levels.
# Controls: joystick walk and turn, B held + left/right strafe, A fire, X switch weapon, Y map.
# Saves: "level" (the level you're on, 1-3).
#
# Drawing: a raycaster. cast() (viper) sends one ray per 2-px column, walks the map grid to the first
# wall and draws the whole column straight into the 4-bit framebuffer: ceiling, textured wall, floor.
# Things (monsters, pickups, fireballs) are 16x16 billboards drawn by spr() (viper) against the
# column depths cast() left in ZB. All math is fixed point: positions are 1/256 of a cell, angles
# 1024 to a turn, directions 4096 = 1.0. Only the 3D view is pushed each frame; the status bar
# is pushed when it changes.
import time, random, gc
from lcd import LCD, Keys
import save
import ui
import bunker_draw as R
from bunker_art import *

lcd = LCD()
keys = Keys()

FRAME = 40                  # ms a frame: 25 fps

# ---- the levels ---------------------------------------------------------------------------------
# '#' stone  '%' brick  '=' tech  '|' metal  'D' door  'R' red-key door  'E' exit switch
# '@' you (facing east)  'z' zombie  'i' imp  'd' demon  'o' barrel
# '+' medkit  'a' bullets  's' shells  'g' shotgun  'k' red key

LEVELS = [
    ("Hangar", [
        "####################",
        "#@...#.....z.......#",
        "#....#.............#",
        "#..a.D....o...o....#",
        "#....#.............#",
        "##D###......z......#",
        "#....|||||D|||||||||",
        "#.z..|.........+...#",
        "#....|..g..........#",
        "#.+..D.......z.....#",
        "#....|.........a...#",
        "######%%%%D%%%%RR%%%",
        "#....%.........%...#",
        "#.k..D...i.....%.z.E",
        "#....%..o......%...#",
        "##################%#",
    ]),
    ("Toxin Labs", [
        "========================",
        "=@.....=.........=.....=",
        "=......D....z....D..i..=",
        "=..+...=.........=.....=",
        "=====D==.o.....o.===D===",
        "=.....=..........=.....=",
        "=..i..=....i.....=.....=",
        "=.....====D=======..s..=",
        "=.a...=.....=.....=....=",
        "=.....D..d..D..k..=..o.=",
        "=.....=.....=.....=....=",
        "===D=====D=========D====",
        "=.....z.......i........=",
        "=..o.......%%R%%.....+.=",
        "=..........%...%.......=",
        "=...i...d..%.E.%..z..a.=",
        "=..........%...%.......=",
        "========================",
    ]),
    ("Hell Gate", [
        "%%%%%%%%%%%%%%%%%%%%%%%%",
        "%@.....%...............%",
        "%......D....i....d.....%",
        "%..s...%...............%",
        "%%%%D%%%%%%%%D%%%%%%%%%%",
        "%.......%..........%...%",
        "%.d...i.%..o...o...D.+.%",
        "%.......%..........%...%",
        "%..+....D....i.....%%D%%",
        "%.......%..........%...%",
        "%%%%%%D%%%%%%%%%%%%%.k.%",
        "%..i......d......i.%...%",
        "%..................%%D%%",
        "%...o....###R###...%...%",
        "%........#.....#..i%.a.%",
        "%..d.....#..E..#...D...%",
        "%........#.....#...%...%",
        "%%%%%%%%%%%%%%%%%%%%%%%%",
    ]),
]

# Things: kind, look, hp, speed (1/256 cell a frame), size (1/256 cell: how big it's drawn)
KINDS = {
    "z": ("zombie", 2, 9, 230), "i": ("imp", 3, 10, 230), "d": ("demon", 6, 20, 210),
    "o": ("barrel", 1, 0, 170), "+": ("med", 0, 0, 200), "a": ("clip", 0, 0, 200),
    "s": ("shells", 0, 0, 200), "g": ("shotgun", 0, 0, 220), "k": ("key", 0, 0, 200),
}
MONSTERS = "zid"


class Thing:
    def __init__(self, k, x, y):
        self.k = k                          # the map letter (KINDS), or "b" for a fireball, "x" a blast
        self.x, self.y = x, y
        if k in KINDS:
            self.look, self.hp, self.spd, self.size = KINDS[k]
        self.awake = False
        self.cd = 30 + random.getrandbits(5)     # frames until it may attack
        self.atk = 0                        # frames left showing its attack look
        self.pain = 0                       # frames left flashing white
        self.dead = False
        self.gone = False                   # picked up, or a fireball that hit
        self.d = 0                          # depth on screen last frame (0 = not on screen)
        self.col = 0
        self.w = 0
        self.vx = self.vy = 0               # fireballs


# ---- the game ------------------------------------------------------------------------------------

class G:
    pass


g = G()
MAP = bytearray(24 * 24)


def load(n):
    name, rows = LEVELS[n]
    g.level, g.name = n, name
    g.mw, g.mh = len(rows[0]), len(rows)
    for i in range(len(MAP)):
        MAP[i] = 0
    g.things = []
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            MAP[y * g.mw + x] = WALLS.get(ch, 0)
            cx, cy = x * 256 + 128, y * 256 + 128
            if ch == "@":
                g.px, g.py, g.ang = cx, cy, 0
            elif ch in KINDS:
                g.things.append(Thing(ch, cx, cy))
    g.total = sum(1 for t in g.things if t.k in MONSTERS)
    g.kills = 0
    g.key = False
    g.frames = 0
    g.msg, g.msgt = "", 0
    g.hurt = g.glow = 0
    g.fire = 0
    g.cool = 12                           # the A that started the level isn't a shot
    g.bob = 0
    g.map = False
    g.done = False
    g.hud = True
    g.ms = getattr(g, "ms", 0)
    g.seen = bytearray(g.mw * g.mh)       # what the map shows: cells you've been near


def fresh():
    g.hp, g.ammo, g.shells, g.sg, g.wpn = 100, 50, 0, False, 0


def say(s):
    g.msg, g.msgt = s, 60


def cell(x, y):
    """The map cell at a point (1/256 cell units); outside the map counts as a wall."""
    cx, cy = x >> 8, y >> 8
    if cx < 0 or cy < 0 or cx >= g.mw or cy >= g.mh:
        return 1
    return MAP[cy * g.mw + cx]


def free(x, y, r):
    return not (cell(x - r, y - r) or cell(x + r, y - r) or cell(x - r, y + r) or cell(x + r, y + r))


def bump(x, y):
    """You walked into the wall at x, y: open a door, try the red door, flip the exit."""
    c = cell(x, y)
    i = (y >> 8) * g.mw + (x >> 8)
    if c == DOOR:
        MAP[i] = 0
    elif c == RDOOR:
        if g.key:
            MAP[i] = 0
            say("Red door open")
        elif g.msgt < 30:
            say("You need the red key")
    elif c == EXIT:
        g.done = True


def walk(dx, dy):
    r = 64
    nx, ny = g.px + dx, g.py + dy
    ex = nx + (r if dx > 0 else -r)
    ey = ny + (r if dy > 0 else -r)
    if free(nx, g.py, r):
        g.px = nx
    elif dx:
        bump(ex, g.py)
    if free(g.px, ny, r):
        g.py = ny
    elif dy:
        bump(g.px, ey)


def dist(t):
    ax, ay = abs(t.x - g.px), abs(t.y - g.py)
    return max(ax, ay) + (min(ax, ay) >> 1)         # close enough to sqrt for game logic


def sight(t):
    """True if nothing stands between t and you (steps of 1/4 cell along the line)."""
    x, y = t.x, t.y
    dx, dy = g.px - x, g.py - y
    n = max(abs(dx), abs(dy)) >> 6
    if n == 0:
        return True
    sx, sy = dx // n, dy // n
    for _ in range(n):
        x += sx
        y += sy
        if cell(x, y):
            return False
    return True


def hurt(n):
    if g.hp <= 0:
        return
    g.hp = max(0, g.hp - n)
    g.hurt = 8
    g.hud = True


def blast(t):
    """A barrel goes off: hurts everything within 1.5 cells, you too."""
    t.dead = True
    t.k = "x"
    t.atk = 14
    for o in g.things:
        if o is not t and not o.dead and (o.k in MONSTERS or o.k == "o"):
            dd = max(abs(o.x - t.x), abs(o.y - t.y))
            if dd < 400:
                damage(o, 6 if dd < 200 else 3)
    dd = dist(t)
    if dd < 400:
        hurt(40 if dd < 200 else 20)


def damage(t, n):
    t.hp -= n
    t.pain = 4
    t.awake = True
    if t.hp <= 0 and not t.dead:
        if t.k == "o":
            blast(t)
            return
        t.dead = True
        g.kills += 1
        g.hud = True
        if t.k == "z":                          # a zombie drops its clip
            c = Thing("a", t.x + 40, t.y + 40)
            g.things.append(c)


def shoot():
    pistol = g.wpn == 0
    if pistol:
        if g.ammo <= 0:
            say("No bullets")
            g.cool = 10
            return
        g.ammo -= 1
        g.cool = 9
    else:
        if g.shells <= 0:
            say("No shells")
            g.cool = 10
            return
        g.shells -= 1
        g.cool = 24
    g.fire = 4
    g.hud = True
    zc = struct.unpack_from("<i", ZB, 240)[0]
    best = None
    for t in g.things:
        if t.d and not t.dead and t.d < zc and (t.k in MONSTERS or t.k == "o"):
            reach = max(2, (t.w * 2) // 5) if pistol else (t.w >> 1) + 8
            if abs(t.col - 60) <= reach and (best is None or t.d < best.d):
                best = t
    if best:
        if pistol:
            damage(best, 1)
        else:
            damage(best, 4 if best.d < 768 else 2)
    for t in g.things:                          # the noise wakes everything near
        if t.k in MONSTERS and dist(t) < 2500:
            t.awake = True


def pickup(t):
    k = t.k
    if k == "+":
        if g.hp >= 100:
            return
        g.hp = min(100, g.hp + 25)
        say("Medkit")
    elif k == "a":
        g.ammo = min(200, g.ammo + 10)
        say("Bullets")
    elif k == "s":
        g.shells = min(50, g.shells + 8)
        say("Shells")
    elif k == "g":
        g.shells = min(50, g.shells + 8)
        if not g.sg:
            g.sg, g.wpn = True, 1
            say("A shotgun!")
        else:
            say("Shells")
    elif k == "k":
        g.key = True
        say("Red key")
    t.gone = True
    g.glow = 6
    g.hud = True


def think(t, i):
    if t.gone:
        return
    if t.k == "b":                               # a fireball
        t.x += t.vx
        t.y += t.vy
        if cell(t.x, t.y):
            t.gone = True
        elif dist(t) < 110:
            hurt(8 + random.getrandbits(3))
            t.gone = True
        return
    if t.k == "x":
        t.atk -= 1
        if t.atk <= 0:
            t.gone = True
        return
    if t.dead:
        return
    if t.k not in MONSTERS:
        if dist(t) < 120 and t.k != "o":
            pickup(t)
        return
    if t.pain:
        t.pain -= 1
    if t.atk:
        t.atk -= 1
    d = dist(t)
    if not t.awake:
        if (g.frames + i) & 7 == 0 and d < 2800 and sight(t):
            t.awake = True
        return
    if t.cd:
        t.cd -= 1
    near = 150 if t.k == "d" else 220
    if d > near and not t.atk:
        ux, uy = g.px - t.x, g.py - t.y
        m = max(abs(ux), abs(uy))
        sx, sy = ux * t.spd // m, uy * t.spd // m
        if free(t.x + sx, t.y, 60):
            t.x += sx
        if free(t.x, t.y + sy, 60):
            t.y += sy
    if t.cd == 0 and not t.pain:
        if t.k == "d":
            if d < 230:
                t.atk = 8
                t.cd = 22
                hurt(6 + random.getrandbits(4))
        elif d < 3000 and sight(t):
            t.atk = 10
            t.cd = 45 + random.getrandbits(6)
            if t.k == "i":
                ux, uy = g.px - t.x, g.py - t.y
                m = max(1, abs(ux), abs(uy))
                b = Thing("b", t.x, t.y)
                b.vx, b.vy = ux * 40 // m, uy * 40 // m
                g.things.append(b)
            elif random.getrandbits(8) < 200 - d // 16:
                hurt(3 + random.getrandbits(3))


def look(t):
    """The sprite frame for a thing right now, and whether it's mirrored."""
    k = t.k
    if k == "b":
        return FR["ball"], (g.frames >> 2) & 1
    if k == "x":
        return FR["boom"], (g.frames >> 1) & 1
    if k in MONSTERS:
        n = t.look
        if t.dead:
            return FR[n + "_dead"], 0
        if t.atk:
            return FR[n + "_atk"], 0
        return FR[n], ((g.frames + t.x) >> 3) & 1 if t.awake else 0
    return FR[t.look], 0


DRAW = []


def draw_things(dx, dy):
    """Project every thing, then draw them far to near."""
    DRAW.clear()
    px, py = g.px, g.py
    for t in g.things:
        t.d = 0
        if t.gone:
            continue
        rx, ry = t.x - px, t.y - py
        depth = (rx * dx + ry * dy) >> 12
        if depth < 40:
            continue
        lat = (ry * dx - rx * dy) >> 12
        col = 60 + (lat * 91) // depth
        hh = (VH << 8) // depth                    # a whole cell tall at this depth
        size = 150 if t.k == "b" else (230 if t.k == "x" else t.size)
        h = hh * size >> 8
        w = h >> 1
        if w < 1 or col + w < 0 or col - w > 120:
            continue
        t.d, t.col, t.w = depth, col, w
        DRAW.append(t)
    DRAW.sort(key=lambda t: -t.d)
    for t in DRAW:
        h = t.w * 2
        f, fl = look(t)
        put(SA, 0, t.col + B)
        put(SA, 1, t.w)
        if t.k == "b":
            put(SA, 2, (VH >> 1) - (h >> 1) + B)          # fireballs fly at eye level
        else:
            put(SA, 2, (VH >> 1) + (((VH << 8) // t.d) >> 1) - h + B)
        put(SA, 3, h)
        put(SA, 4, t.d)
        put(SA, 5, f)
        put(SA, 6, 6 if t.pain else (0 if t.k in "bx" else min(5, t.d >> 9)))
        put(SA, 7, VH)
        put(SA, 8, fl)
        R.spr(lcd.buffer, SPR, SA)


def draw_gun():
    fb = GUNFB[g.wpn][1 if g.fire > 1 else 0]
    bx = (SIN[(g.bob * 8) & 1023] * 6) >> 12
    by = abs(SIN[(g.bob * 8) & 1023] * 4) >> 12
    lcd.blit(fb, 84 + bx, VH - 66 + by + (4 if g.fire else 0), GKEY)


def draw_map():
    s = 7 if g.mw <= 20 else 6
    ox, oy = (240 - g.mw * s) // 2, (VH - g.mh * s) // 2
    lcd.fill_rect(ox - 4, oy - 4, g.mw * s + 8, g.mh * s + 8, K)
    for y in range(g.mh):
        for x in range(g.mw):
            i = y * g.mw + x
            c = MAP[i]
            if c and g.seen[i]:
                lcd.fill_rect(ox + x * s, oy + y * s, s - 1, s - 1, RD if c == RDOOR else (YL if c == DOOR else (GR if c == EXIT else RAMP[5])))
    px, py = ox + g.px * s // 256, oy + g.py * s // 256
    lcd.line(px, py, px + cos(g.ang) * 8 // 4096, py + sin(g.ang) * 8 // 4096, YL)
    lcd.fill_rect(px - 1, py - 1, 3, 3, W)
    lcd.text("%d ms a frame" % g.ms if g.ms else "ms a frame: soon", 4, VH - 10, RAMP[7])


def look_around():
    """Mark the cells near you as seen, for the map."""
    cx, cy = g.px >> 8, g.py >> 8
    for y in range(max(0, cy - 3), min(g.mh, cy + 4)):
        for x in range(max(0, cx - 3), min(g.mw, cx + 4)):
            g.seen[y * g.mw + x] = 1


def num(v, x, y):
    s = str(v)
    for i, ch in enumerate(s):
        lcd.blit(DIG[ord(ch) - 48], x + i * 16, y, GKEY)


def draw_hud():
    y = VH
    lcd.fill_rect(0, y, 240, 240 - y, RAMP[3])
    lcd.hline(0, y, 240, RAMP[5])
    lcd.hline(0, y + 1, 240, RAMP[4])
    for x in (62, 140, 196):
        lcd.vline(x, y + 2, 240 - y - 2, RAMP[2])
        lcd.vline(x + 1, y + 2, 240 - y - 2, RAMP[4])
    a = g.ammo if g.wpn == 0 else g.shells
    num(a, 6, y + 10)
    lcd.text("AMMO", 14, y + 36, RAMP[8])
    num(g.hp, 70, y + 10)
    lcd.blit(DIG[10], 70 + 16 * len(str(g.hp)), y + 10, GKEY)
    lcd.text("HEALTH", 78, y + 36, RAMP[8])
    lcd.text("KILLS", 150, y + 8, RAMP[8])
    lcd.text("%d/%d" % (g.kills, g.total), 150, y + 22, W)
    lcd.text("PISTOL" if g.wpn == 0 else "SHOTGN", 145, y + 40, YL if g.wpn else RAMP[7])
    lcd.text("KEY", 206, y + 8, RAMP[8])
    if g.key:
        lcd.fill_rect(210, y + 22, 16, 10, RD)
        lcd.rect(210, y + 22, 16, 10, K)
    lcd.text("L%d" % (g.level + 1), 208, y + 40, RAMP[7])


def frame():
    a = g.ang
    dx, dy = cos(a), sin(a)
    put(ST, 0, g.px)
    put(ST, 1, g.py)
    put(ST, 2, dx + B)
    put(ST, 3, dy + B)
    put(ST, 4, (-dy * 66) // 100 + B)
    put(ST, 5, (dx * 66) // 100 + B)
    put(ST, 6, g.mw)
    put(ST, 7, VH)
    R.cast(lcd.buffer, MAP, TEX, ST)
    draw_things(dx, dy)
    if g.map:
        draw_map()
    else:
        draw_gun()
    if g.hurt or g.glow:
        c = RD if g.hurt else YL
        for i in range(3):
            lcd.rect(i, i, 240 - 2 * i, VH - 2 * i, c)
    if g.msgt:
        lcd.text(g.msg, 4, 4, YL)
    lcd.show(0, VH)
    if g.hud:
        g.hud = False
        draw_hud()
        lcd.show(VH, 240)


def step():
    g.frames += 1
    for k in keys.pressed():
        if k == "A" and g.cool == 0:
            shoot()
        elif k == "X" and g.sg:
            g.wpn ^= 1
            g.hud = True
        elif k == "Y":
            g.map = not g.map
    if keys.held("A") and g.cool == 0:              # hold to keep firing
        shoot()
    a = g.ang
    dx, dy = cos(a), sin(a)
    moving = False
    spd = 24
    if keys.held("up"):
        walk(dx * spd >> 12, dy * spd >> 12)
        moving = True
    if keys.held("down"):
        walk(-dx * spd >> 12, -dy * spd >> 12)
        moving = True
    strafe = keys.held("B")
    if keys.held("left"):
        if strafe:
            walk(dy * spd >> 12, -dx * spd >> 12)
            moving = True
        else:
            g.ang = (g.ang - 20) & 1023
    if keys.held("right"):
        if strafe:
            walk(-dy * spd >> 12, dx * spd >> 12)
            moving = True
        else:
            g.ang = (g.ang + 20) & 1023
    if moving:
        g.bob += 1
    if g.cool:
        g.cool -= 1
    if g.fire:
        g.fire -= 1
    if g.hurt:
        g.hurt -= 1
    if g.glow:
        g.glow -= 1
    if g.msgt:
        g.msgt -= 1
    for i, t in enumerate(g.things):
        think(t, i)
    if g.frames & 31 == 0:
        g.things = [t for t in g.things if not t.gone]
    if g.frames & 7 == 0:
        look_around()


def wait_a():
    keys.pressed()
    while True:
        for k in keys.pressed():
            if k == "A":
                return
        time.sleep_ms(30)


def play(n):
    """One level. True if you reached the exit, False if you died."""
    load(n)
    look_around()
    gc.collect()
    busy = 0
    while True:
        t = time.ticks_ms()
        step()
        frame()
        busy += time.ticks_diff(time.ticks_ms(), t)
        if g.frames & 127 == 0:                   # the real frame time: on the map (Y), and over USB
            g.ms = busy >> 7
            print("bunker: %d ms a frame (budget %d)" % (g.ms, FRAME))
            busy = 0
        if g.done:
            return True
        if g.hp <= 0:
            return False
        left = FRAME - time.ticks_diff(time.ticks_ms(), t)
        time.sleep_ms(left if left > 4 else 4)    # USB runs in here: a slow frame still leaves it 4 ms


def run():
    level = save.load("level", 1) - 1
    if not 0 <= level < len(LEVELS):
        level = 0
    ui.page(lcd, "Demon Bunker", [("Level %d: %s" % (level + 1, LEVELS[level][0]), ui.INK),
                                  ("stick  walk and turn", ui.MUTED), ("B + stick  strafe", ui.MUTED),
                                  ("A  fire   X  weapon", ui.GREEN_D), ("Y  map", ui.MUTED)], "A  start")
    wait_a()
    fresh()
    while True:
        t0 = time.ticks_ms()
        if play(level):
            secs = time.ticks_diff(time.ticks_ms(), t0) // 1000
            kills = "Kills %d/%d" % (g.kills, g.total)
            level += 1
            if level >= len(LEVELS):
                save.store("level", 1)
                ui.page(lcd, "You won", [("The bunker is clear.", ui.INK), (kills, ui.MUTED)], "A  play again")
                level = 0
                wait_a()
                fresh()
                continue
            save.store("level", level + 1)
            ui.page(lcd, "Level done", [(kills, ui.INK), ("Time %d:%02d" % (secs // 60, secs % 60), ui.MUTED),
                                        ("Next: " + LEVELS[level][0], ui.GREEN_D)], "A  next level")
            wait_a()
        else:
            ui.page(lcd, "You died", [("Level %d: %s" % (level + 1, g.name), ui.INK),
                                      ("Kills %d/%d" % (g.kills, g.total), ui.MUTED)], "A  try again")
            wait_a()
            fresh()
