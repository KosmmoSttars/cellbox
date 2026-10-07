import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cellbox import jitcache  # noqa: E402

jitcache.install()
