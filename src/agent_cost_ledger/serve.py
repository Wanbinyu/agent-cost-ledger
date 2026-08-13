from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from .settings import default_data_dir
from .webapp import create_app


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    data_dir: Path | str | None = None,
) -> None:
    """Start the chat UI with bottom usage bar."""
    root = Path(data_dir) if data_dir else default_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    app = create_app(root)

    if open_browser:
        url = f"http://{host}:{port}/"

        def _open() -> None:
            # Wait briefly for server bind
            time.sleep(0.8)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")
