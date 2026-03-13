import os
from importlib.metadata import version

BASE_URL = os.getenv("SMOOTH_BASE_URL", "https://api.smooth.sh/api/")
SDK_VERSION = version("smooth-py")
