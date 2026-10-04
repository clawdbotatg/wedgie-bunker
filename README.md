# Demon Bunker

A first-person shooter for the [wedgie](https://wedgie.dev), in the style of Doom and Wolfenstein 3D.
Zombies, imps and demons in a bunker. Find the red key, hit the exit switch. Three levels.

## Controls

| | |
|---|---|
| joystick up / down | walk |
| joystick left / right | turn |
| B held + left / right | strafe |
| A | fire (hold to keep firing) |
| X | switch pistol / shotgun |
| Y | map |

Walk into a door to open it. The red door needs the red key. Barrels explode when shot.

## Monsters

- **Zombie** (green): shoots you from a distance, drops bullets when it dies.
- **Imp** (red, horns): throws fireballs.
- **Demon** (big red mouth): fast, bites up close.

## Saves

- `level`: the level you're on (1-3). Set it to 3 to start at Hell Gate.

## How it draws

A raycaster in viper: one ray per 2-px column, the column drawn straight into the 4-bit framebuffer
(ceiling, textured wall, floor). Monsters and pickups are 16x16 billboards checked against each
column's wall depth. Only the 3D view is pushed each frame; the status bar only when it changes.

## Files

- `bunker.py`: the game. **Run `./build.sh` after changing it** and commit `bunker.mpy` too: the wedgie
  runs the compiled `bunker.mpy` (an RP2040 can't compile this much Python at start).
- `bunker_draw.py`: the renderer in viper. Viper is machine code, so it stays `.py` and compiles on the wedgie.

## License

MIT.
