"""In-app X login via an embedded WebView2 window.

This module runs in its own process (so its GUI loop does not clash with the
Tkinter main loop). It opens the real X login page, lets the user authenticate
normally — including captcha / two-factor — and once the session cookies appear
it reads ``auth_token``, ``ct0`` and ``twid`` straight from the embedded
browser's own cookie jar, then writes them to the file given on the command line.

The user's password never passes through our code: authentication happens
entirely inside X's own page.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any


LOGIN_URL = "https://x.com/login"
REQUIRED_COOKIES = ("auth_token", "ct0")
POLL_SECONDS = 1.0
MAX_WAIT_SECONDS = 600  # Give up after 10 minutes of no completed login.


def _flatten_cookies(cookies: Any) -> dict[str, str]:
    """Normalise pywebview's cookie list into a simple name -> value dict.

    Different backends return either ``http.cookiejar.Cookie`` objects or
    ``SimpleCookie`` instances, so handle both shapes.
    """
    values: dict[str, str] = {}
    for cookie in cookies or []:
        name = getattr(cookie, "name", None)
        value = getattr(cookie, "value", None)
        if name is not None and value is not None:
            values[name] = value
            continue
        items = getattr(cookie, "items", None)
        if callable(items):
            try:
                for key, morsel in cookie.items():
                    values[key] = getattr(morsel, "value", morsel)
            except Exception:
                pass
    return values


def run(outfile: str) -> None:
    import webview

    result: dict[str, str] = {}
    closed = threading.Event()

    window = webview.create_window(
        "TweetDown - X'te Oturum Aç",
        LOGIN_URL,
        width=520,
        height=760,
    )
    window.events.closed += closed.set

    def poll() -> None:
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while not closed.is_set() and time.monotonic() < deadline:
            try:
                values = _flatten_cookies(window.get_cookies())
            except Exception:
                values = {}
            if all(values.get(name) for name in REQUIRED_COOKIES):
                result["auth_token"] = values["auth_token"]
                result["ct0"] = values["ct0"]
                if values.get("twid"):
                    result["twid"] = values["twid"]
                break
            time.sleep(POLL_SECONDS)
        if not closed.is_set():
            try:
                window.destroy()
            except Exception:
                pass

    webview.start(poll)

    with open(outfile, "w", encoding="utf-8") as handle:
        json.dump(result, handle)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m tweetdown.webview_login <outfile>")
    run(sys.argv[1])
