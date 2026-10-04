#!/bin/sh
# bunker_art.py and bunker_game.py -> .mpy (bytecode, mpy-cross 1.29.0 as wedgie.dev's firmware): an
# RP2040 can't compile this much Python at start. bunker.py (the tiny entry) and bunker_draw.py (viper,
# machine code) stay source. Run after every change and commit the .mpy files too.
cd "$(dirname "$0")" && uv run -q --with mpy-cross==1.29.0.post2 python3 -c "
import mpy_cross, subprocess
for m in ('bunker_art', 'bunker_game'):
    subprocess.run([mpy_cross.mpy_cross, '-s', m + '.py', '-o', m + '.mpy', m + '.py'], check=True)"
