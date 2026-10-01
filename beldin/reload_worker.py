"""Detached, fixed Beldin reload helper."""
import re
import sys
from .control_center import PRODUCTION_ROOT, run_reload

if __name__ == '__main__':
    if len(sys.argv) == 2 and re.fullmatch('[a-f0-9]{32}', sys.argv[1]):
        run_reload(PRODUCTION_ROOT, sys.argv[1])
