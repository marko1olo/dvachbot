import os
import sys
import subprocess

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

cmd = [
    sys.executable, "-m", "pytest", "-p", "pytest_asyncio.plugin",
    "tests/test_media_resiliency.py",
    "tests/test_files_endpoint.py",
    "tests/test_select_mirror_strategically.py",
    "tests/test_html_anchors.py"
]

print("Running command:", " ".join(cmd))
result = subprocess.run(cmd, capture_output=False)
sys.exit(result.returncode)
