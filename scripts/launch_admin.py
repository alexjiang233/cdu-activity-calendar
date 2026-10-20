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
URL = 'http://127.0.0.1:8790/'


def ready():
    try:
        with urllib.request.urlopen(URL + 'manage/version/', timeout=2) as response:
            data = json.load(response)
        return data.get('app') == 'campus-workbench-2'
    except (OSError, ValueError):
        return False


def launch(open_browser=True):
    if not ready():
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        runtime=ROOT/'.venv-backend'/('Scripts/pythonw.exe' if os.name=='nt' else 'bin/python')
        if not runtime.exists():raise RuntimeError('尚未安装后台运行环境，请先按 docs/backend/GETTING-STARTED.md 完成安装。')
        subprocess.Popen([str(runtime), str(ROOT / 'backend/manage.py'),'runserver','127.0.0.1:8790','--noreload'], cwd=ROOT/'backend',
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        for _ in range(40):
            time.sleep(.25)
            if ready():
                break
        else:
            raise RuntimeError('管理页暂时没能打开，请把这个情况告诉Sol。你的原始资料没有改变。')
    if open_browser:
        webbrowser.open(URL+'manage/')
    return URL+'manage/'


if __name__ == '__main__':
    try:
        launch()
    except Exception as exc:
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(exc), '校园活动管理', 0x10)
        else:
            raise
