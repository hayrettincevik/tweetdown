from __future__ import annotations

import base64
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .i18n import t


@dataclass(slots=True)
class ChromiumProfile:
    browser_id: str
    browser_name: str
    user_data_dir: Path
    profile_dir: Path


def _local_app_data() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    if not raw:
        raise RuntimeError(t("cc_no_localappdata"))
    return Path(raw)


def chromium_roots() -> dict[str, tuple[str, Path]]:
    local = _local_app_data()
    return {
        "chrome": ("Chrome", local / "Google" / "Chrome" / "User Data"),
        "edge": ("Edge", local / "Microsoft" / "Edge" / "User Data"),
        "brave": ("Brave", local / "BraveSoftware" / "Brave-Browser" / "User Data"),
        "vivaldi": ("Vivaldi", local / "Vivaldi" / "User Data"),
        "opera": ("Opera", local / "Opera Software" / "Opera Stable"),
    }


def list_profiles(browser_id: str | None = None) -> list[ChromiumProfile]:
    roots = chromium_roots()
    ids = [browser_id] if browser_id and browser_id != "auto" else list(roots)
    profiles: list[ChromiumProfile] = []
    for candidate_id in ids:
        item = roots.get(candidate_id)
        if not item:
            continue
        name, root = item
        local_state = root / "Local State"
        if not local_state.exists():
            continue
        if candidate_id == "opera":
            cookie_db = root / "Network" / "Cookies"
            if cookie_db.exists():
                profiles.append(ChromiumProfile(candidate_id, name, root, root))
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if child.name == "Default" or child.name.startswith("Profile "):
                cookie_db = child / "Network" / "Cookies"
                if cookie_db.exists():
                    profiles.append(ChromiumProfile(candidate_id, name, root, child))
    return profiles


def _master_key(user_data_dir: Path) -> bytes:
    try:
        import win32crypt
    except ImportError as exc:
        raise RuntimeError(t("cc_pywin32_missing")) from exc

    local_state = json.loads((user_data_dir / "Local State").read_text(encoding="utf-8"))
    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]


def _decrypt_value(encrypted: bytes, key: bytes) -> str:
    try:
        import win32crypt
    except ImportError as exc:
        raise RuntimeError(t("cc_pywin32_missing")) from exc

    if not encrypted:
        return ""
    if encrypted.startswith((b"v10", b"v11", b"v20")):
        from Cryptodome.Cipher import AES

        nonce = encrypted[3:15]
        ciphertext = encrypted[15:-16]
        tag = encrypted[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    return win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1].decode("utf-8")


def _read_cookie_rows(cookies_path: Path) -> list[tuple[str, str, bytes]]:
    query = """
        select host_key, name, encrypted_value
        from cookies
        where name in ('auth_token', 'ct0', 'twid')
          and (host_key like '%x.com' or host_key like '%twitter.com')
    """
    try:
        con = sqlite3.connect(f"file:{cookies_path}?mode=ro", uri=True)
        try:
            return con.execute(query).fetchall()
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
            tmp_path = Path(tmp.name)
        try:
            try:
                tmp_path.write_bytes(cookies_path.read_bytes())
            except PermissionError:
                return []
            con = sqlite3.connect(tmp_path)
            try:
                return con.execute(query).fetchall()
            finally:
                con.close()
        finally:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass


def extract_x_cookies(browser_id: str | None = None) -> tuple[dict[str, str], ChromiumProfile]:
    errors: list[str] = []
    checked_profiles = 0
    for profile in list_profiles(browser_id):
        try:
            cookies_path = profile.profile_dir / "Network" / "Cookies"
            key = _master_key(profile.user_data_dir)
            rows = _read_cookie_rows(cookies_path)
            checked_profiles += 1
            values: dict[str, str] = {}
            for _host, name, encrypted in rows:
                value = _decrypt_value(encrypted, key)
                if value:
                    values[name] = value
            if values.get("auth_token") and values.get("ct0"):
                return values, profile
        except Exception as exc:
            errors.append(f"{profile.browser_name}/{profile.profile_dir.name}: {exc}")
    detail = "; ".join(errors[-4:])
    if checked_profiles:
        raise RuntimeError(
            t("cc_no_cookies_profile")
            + (t("au_last_errors", detail=detail) if detail else "")
        )
    raise RuntimeError(t("cc_no_cookies") + (t("au_last_errors", detail=detail) if detail else ""))
