import json
import threading
import time
import webbrowser
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from app.setup import initialize_database
from database import DATA_DIR, DEMO_MODE, SessionLocal
from manage import seed_catalog

HOST = "127.0.0.1"
PORT = 8020 if DEMO_MODE else 8018
URL = f"http://{HOST}:{PORT}/"


def site_is_ready():
    try:
        with urlopen(f"{URL}openapi.json", timeout=0.5) as response:
            schema = json.load(response)
            paths = schema.get("paths", {})
            has_demo = "/api/auth/demo/{role}" in paths
            return "/api/applications/{app_id}/attachments" in paths and has_demo == DEMO_MODE
    except (OSError, URLError, ValueError):
        return False


def open_browser_when_ready():
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if site_is_ready():
            webbrowser.open(URL)
            return
        time.sleep(0.25)


def main():
    if site_is_ready():
        webbrowser.open(URL)
        return

    if not DEMO_MODE and not (DATA_DIR / "mektep.sqlite3").exists():
        initialize_database()
        with SessionLocal() as db:
            seed_catalog(db)

    print(f"Open {URL}. Keep this window open while using the site.", flush=True)
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    uvicorn.run("main:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
