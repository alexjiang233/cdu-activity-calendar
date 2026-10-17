"""Double-click launcher: reuse local desk, otherwise start it without a console."""
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8768/'


def ready():
    try:
        with urllib.request.urlopen(URL + 'api/status', timeout=2) as response:
            data = json.load(response)
        return data.get('app') == 'cdu-content-desk-1' and isinstance(data.get('activities'), int)
    except (OSError, ValueError):
        return False


def launch(open_browser=True):
    if not ready():
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.Popen([sys.executable, str(ROOT / 'scripts/admin_server.py')], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        for _ in range(40):
            time.sleep(.25)
            if ready():
                break
        else:
            raise RuntimeError('管理页暂时没能打开，请把这个情况告诉Sol。你的原始资料没有改变。')
    if open_browser:
        webbrowser.open(URL)
    return URL


if __name__ == '__main__':
    try:
        launch()
    except Exception as exc:
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(exc), '校园活动管理', 0x10)
        else:
            raise
