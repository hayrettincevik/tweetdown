# TweetDown

TweetDown is a local Windows desktop app for exporting X/Twitter liked posts to JSON.

It uses your own X session, walks the Likes GraphQL timeline with cursors, and writes
progress after each page so long exports can be resumed.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Optional username/password login support:

```powershell
python -m pip install -r requirements-login.txt
```

## Authentication

Recommended: click **"Log in to X"** in the app. It opens the real X login page inside
an embedded window (WebView2); you log in there normally — captcha and two-factor included —
and once the session is established the app reads `auth_token`, `ct0` and your user id
straight from that window. Your password never passes through the app.

This needs the Microsoft Edge WebView2 runtime, which ships with current Windows 10/11. If
it is missing, install the free "Evergreen" runtime from Microsoft.

Fallbacks (under the **"Advanced"** section): the app can also read cookies from an
installed browser, accept a pasted cookie header, or take `auth_token`/`ct0` manually
(see below).

The interface is in English by default; use the **TR / EN** switch in the top-right corner
to switch to Turkish.

The app needs:

- `auth_token`
- `ct0`
- your numeric X user id

If browser extraction can read the `twid` cookie, the numeric user id is filled
automatically.

If Chrome extraction does not find the session:

1. Make sure the x.com tab is open in the same Chrome profile shown in the app.
2. Try closing Chrome completely and pressing "Get session from browser" again.
3. If Chrome still only exposes guest cookies, copy the full request cookie header:
   - open `https://x.com/i/likes`
   - press `F12`
   - open the Network tab
   - refresh the page
   - click a request to `x.com/i/api/graphql/.../Likes`
   - Headers
   - Request Headers
   - copy the whole `Cookie:` value
   - paste it into the app's `Cookie header` field

You can also copy `auth_token` and `ct0` separately from DevTools > Application >
Cookies > `https://x.com`. The numeric user id can be left empty; TweetDown will try to
resolve it from the session.

## Output

The exported JSON contains:

- `metadata`
- `tweets`
- `raw_pages` when enabled
- `errors`

Progress is saved under `.tweetdown/state.json`. The packaged EXE keeps `.tweetdown/` and
the default export file next to `TweetDown.exe`, regardless of where it is launched from.

## Viewer

`tweetdown_viewer.html` is a standalone browser viewer for an exported JSON: tweet cards
with avatars, media, clickable links, search, sorting and a media-only filter. Open it and
pick a file, or drag one in. Inside the app, the **"Open last downloaded JSON in viewer"**
button opens it through a small loopback server and auto-loads the latest export; if none is
found it opens with the file picker. All processing happens in your browser — no data leaves
your machine.

## Package an EXE

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
pyinstaller --onefile --windowed --name TweetDown app.py
```
