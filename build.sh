#!/bin/sh
# bunker.py -> bunker.mpy (bytecode, mpy-cross 1.29.0 as wedgie.dev's firmware): an RP2040 can't
# compile 40 KB of Python at start. Run after every change to bunker.py and commit both.
cd "$(dirname "$0")" && uv run -q --with mpy-cross==1.29.0.post2 python3 -c "
import mpy_cross, subprocess
subprocess.run([mpy_cross.mpy_cross, '-s', 'bunker.py', '-o', 'bunker.mpy', 'bunker.py'], check=True)"
