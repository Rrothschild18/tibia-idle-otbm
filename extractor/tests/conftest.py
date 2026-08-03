import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# build_phaser_map.py resolves its output/asset paths from sys.argv[1] at
# import time. Point it at an existing fixture map so importing the module
# in tests works the same as running it from the CLI. The argument is the
# map's pasta name (leaf folder under maps/<CIDADE>/) — the tool resolves
# which city it lives under itself (see map_dirs.py).
sys.argv = ["build_phaser_map.py", "ROOK-HUNT-0013_rats-rookguard"]
