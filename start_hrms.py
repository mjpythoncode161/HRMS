import os
import subprocess
import time
import webbrowser
import sys
import socket

# Get folder where the exe/script is located
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

url = "http://127.0.0.1:8000"

# If server already running, just open browser
if is_port_in_use(8000):
    webbrowser.open(url)
else:
    # Start Django server without console
    subprocess.Popen(
        ["pythonw", "manage.py", "runserver", "127.0.0.1:8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    time.sleep(6)
    webbrowser.open(url)