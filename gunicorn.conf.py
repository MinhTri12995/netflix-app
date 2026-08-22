import sys
import os

base_dir = os.path.abspath(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

bind = "0.0.0.0:" + os.environ.get("PORT", "10000")
workers = 1
timeout = 120
