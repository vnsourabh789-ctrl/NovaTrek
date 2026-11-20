"""``python -m novatrek`` (or NovaTrek.exe) — start the server and open the browser."""

import socket
import threading
import webbrowser

import uvicorn

from novatrek.config import get_settings


def _free_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) != 0:  # nothing listening -> free
                return port
    return preferred


def main() -> None:
    from novatrek.main import app  # imported here so PyInstaller bundles it

    s = get_settings()
    port = _free_port(s.host, s.port)
    url = f"http://{s.host}:{port}"
    print(f"\n  NovaTrek online -> {url}\n  Close this window (or press Ctrl+C) to stop.\n")  # ASCII: cp1252 consoles
    if _opens_browser():
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=s.host, port=port, log_level="info")


def _opens_browser() -> bool:
    import os
    import sys
    return bool(getattr(sys, "frozen", False)) or os.getenv("OPEN_BROWSER", "").lower() in ("1", "true", "yes")


if __name__ == "__main__":
    main()
