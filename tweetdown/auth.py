from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .models import AuthBundle
from .state import APP_DIR, SESSION_PATH, ensure_app_dir, load_json, save_json

PUBLIC_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16c"
    "HjhLTvJu4FA33AGWWjCpTnA"
)

# Argument the frozen EXE re-launches itself with to open the login window.
LOGIN_FLAG = "--tweetdown-login"


class AuthError(RuntimeError):
    pass


def _extract_user_id_from_twid(twid: str | None) -> str | None:
    if not twid:
        return None
    match = re.search(r"u%3D(\d+)|u=(\d+)|(\d+)", twid)
    if not match:
        return None
    return next(group for group in match.groups() if group)


def save_session(bundle: AuthBundle) -> None:
    save_json(
        SESSION_PATH,
        {
            "auth_token": bundle.auth_token,
            "ct0": bundle.ct0,
            "user_id": bundle.user_id,
            "source": bundle.source,
        },
    )


def load_session() -> AuthBundle | None:
    data: dict[str, Any] = load_json(SESSION_PATH, {})
    if data.get("auth_token") and data.get("ct0") and data.get("user_id"):
        return AuthBundle(
            auth_token=data["auth_token"],
            ct0=data["ct0"],
            user_id=str(data["user_id"]),
            source=data.get("source", "saved"),
        )
    return None


async def _resolve_user_id_from_session(auth_token: str, ct0: str) -> str | None:
    try:
        import httpx
    except ImportError:
        return None
    headers = {
        "authorization": f"Bearer {PUBLIC_BEARER_TOKEN}",
        "cookie": f"auth_token={auth_token}; ct0={ct0};",
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "accept": "*/*",
        "user-agent": "Mozilla/5.0",
        "referer": "https://x.com/",
    }
    urls = (
        "https://x.com/i/api/1.1/account/settings.json",
        "https://api.twitter.com/1.1/account/settings.json",
    )
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        for url in urls:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                continue
            data = response.json()
            for key in ("user_id", "id", "id_str"):
                value = data.get(key)
                if value and str(value).isdigit():
                    return str(value)
    return None


def resolve_user_id_from_session(auth_token: str, ct0: str) -> str | None:
    try:
        return asyncio.run(_resolve_user_id_from_session(auth_token, ct0))
    except Exception:
        return None


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in cookie_header.replace("\n", ";").split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            values[name] = value
    return values


def from_cookie_header(cookie_header: str, user_id: str = "") -> AuthBundle:
    values = parse_cookie_header(cookie_header)
    auth_token = values.get("auth_token", "")
    ct0 = values.get("ct0", "")
    resolved_user_id = user_id.strip() or _extract_user_id_from_twid(values.get("twid"))
    return from_manual(auth_token, ct0, resolved_user_id or "")


def from_manual(auth_token: str, ct0: str, user_id: str) -> AuthBundle:
    auth_token = auth_token.strip()
    ct0 = ct0.strip()
    user_id = user_id.strip()
    if not auth_token or not ct0:
        raise AuthError("auth_token ve ct0 gerekli.")
    if not user_id:
        user_id = resolve_user_id_from_session(auth_token, ct0) or ""
    if not user_id:
        raise AuthError("Numeric user id gerekli. Oturumdan otomatik çözülemedi.")
    if not user_id.isdigit():
        raise AuthError("User id numeric olmalı.")
    bundle = AuthBundle(auth_token, ct0, user_id, "manual")
    save_session(bundle)
    return bundle


def _login_child_command(outfile: str) -> list[str]:
    # The login window runs in a separate process so its WebView2 GUI loop does
    # not fight the Tkinter main loop. A frozen EXE re-launches itself with a
    # flag; in a plain checkout we run the module directly.
    if getattr(sys, "frozen", False):
        return [sys.executable, LOGIN_FLAG, outfile]
    return [sys.executable, "-m", "tweetdown.webview_login", outfile]


def from_webview_login(timeout: float = 660.0) -> AuthBundle:
    ensure_app_dir()
    handle, tmp_name = tempfile.mkstemp(prefix="tdlogin_", suffix=".json", dir=str(APP_DIR))
    os.close(handle)
    tmp_path = Path(tmp_name)
    data: dict[str, Any] = {}
    try:
        try:
            subprocess.run(_login_child_command(str(tmp_path)), timeout=timeout)
        except FileNotFoundError as exc:
            raise AuthError("Oturum açma penceresi başlatılamadı.") from exc
        except subprocess.TimeoutExpired as exc:
            raise AuthError("Oturum açma zaman aşımına uğradı. Lütfen tekrar deneyin.") from exc
        try:
            data = json.loads(tmp_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass

    auth_token = data.get("auth_token")
    ct0 = data.get("ct0")
    if not auth_token or not ct0:
        raise AuthError(
            "Giriş tamamlanmadı. Açılan pencerede X'e giriş yapın; "
            "giriş başarılı olunca pencere kendiliğinden kapanır."
        )
    user_id = _extract_user_id_from_twid(data.get("twid")) or resolve_user_id_from_session(auth_token, ct0)
    if not user_id:
        raise AuthError("Giriş başarılı ama numeric user id çözülemedi. User id alanını elle girin.")
    bundle = AuthBundle(auth_token, ct0, str(user_id), "webview-login")
    save_session(bundle)
    return bundle


def from_browser(browser_name: str | None = None) -> AuthBundle:
    browser_name = (browser_name or "auto").lower()
    chromium_error: Exception | None = None
    if browser_name in {"auto", "chrome", "edge", "brave", "vivaldi", "opera"}:
        try:
            from .chromium_cookies import extract_x_cookies

            values, profile = extract_x_cookies(browser_name)
            auth_token = values.get("auth_token")
            ct0 = values.get("ct0")
            user_id = _extract_user_id_from_twid(values.get("twid"))
            if auth_token and ct0 and not user_id:
                user_id = resolve_user_id_from_session(auth_token, ct0)
            if auth_token and ct0 and user_id:
                bundle = AuthBundle(
                    auth_token,
                    ct0,
                    user_id,
                    f"{profile.browser_name}:{profile.profile_dir.name}",
                )
                save_session(bundle)
                return bundle
            if auth_token and ct0:
                raise AuthError(
                    "auth_token ve ct0 okundu ama numeric user id için twid bulunamadı. "
                    "User id alanını manuel girip auth_token/ct0 değerlerini manuel kaydedin."
                )
        except AuthError:
            raise
        except Exception as exc:
            chromium_error = exc
            if browser_name != "auto":
                raise AuthError(
                    "Tarayıcıdan auth_token, ct0 ve twid bulunamadı. "
                    "x.com sekmesinin seçili Chrome profilinde açık olduğundan emin olun. "
                    f"Detay: {exc}"
                ) from exc
            # In auto mode fall through to browser_cookie3, which also covers Firefox.

    try:
        import browser_cookie3
    except ImportError as exc:
        raise AuthError("browser-cookie3 kurulu değil. requirements.txt kurulumunu yapın.") from exc

    loaders = []
    if browser_name in ("auto", "chrome"):
        loaders.append(("chrome", browser_cookie3.chrome))
    if browser_name in ("auto", "edge"):
        loaders.append(("edge", browser_cookie3.edge))
    if browser_name in ("auto", "firefox"):
        loaders.append(("firefox", browser_cookie3.firefox))
    if browser_name in ("auto", "brave"):
        loaders.append(("brave", browser_cookie3.brave))
    if browser_name in ("auto", "opera"):
        loaders.append(("opera", browser_cookie3.opera))
    if browser_name in ("auto", "vivaldi"):
        loaders.append(("vivaldi", browser_cookie3.vivaldi))

    errors: list[str] = []
    for name, loader in loaders:
        try:
            jar = loader(domain_name=".x.com")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        values = {cookie.name: cookie.value for cookie in jar}
        auth_token = values.get("auth_token")
        ct0 = values.get("ct0")
        user_id = _extract_user_id_from_twid(values.get("twid"))
        if auth_token and ct0 and not user_id:
            user_id = resolve_user_id_from_session(auth_token, ct0)
        if auth_token and ct0 and user_id:
            bundle = AuthBundle(auth_token, ct0, user_id, f"browser:{name}")
            save_session(bundle)
            return bundle

    detail = "; ".join(errors[-3:])
    chromium_detail = f" Chromium okuyucu: {chromium_error}" if chromium_error else ""
    raise AuthError(
        "Tarayıcıdan auth_token, ct0 ve twid bulunamadı. x.com'da giriş yaptığınızdan emin olun. "
        "Olmazsa DevTools > Network içinden tam Cookie header'ını kopyalayıp uygulamadaki "
        "Cookie Header alanına yapıştırın."
        + chromium_detail
        + (f" Son hatalar: {detail}" if detail else "")
    )


async def _login_with_twikit(username: str, password: str, email: str | None) -> AuthBundle:
    try:
        from twikit import Client
    except ImportError as exc:
        raise AuthError("twikit kurulu değil. requirements.txt kurulumunu yapın.") from exc

    client = Client("en-US")
    ensure_app_dir()
    cookie_path = APP_DIR / "twikit_cookies.json"
    await client.login(
        auth_info_1=username,
        auth_info_2=email or username,
        password=password,
        cookies_file=str(cookie_path),
    )
    cookies = client.get_cookies()
    auth_token = cookies.get("auth_token")
    ct0 = cookies.get("ct0")
    user_id = _extract_user_id_from_twid(cookies.get("twid"))
    if not auth_token or not ct0 or not user_id:
        raise AuthError("Giriş başarılı görünse de gerekli cookie değerleri alınamadı.")
    return AuthBundle(auth_token, ct0, user_id, "twikit-login")


def from_username_password(username: str, password: str, email: str | None = None) -> AuthBundle:
    if not username.strip() or not password:
        raise AuthError("Kullanıcı adı ve şifre gerekli.")
    try:
        bundle = asyncio.run(_login_with_twikit(username.strip(), password, email.strip() if email else None))
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(
            "X login başarısız oldu. Captcha, 2FA veya güvenlik kontrolü çıkmış olabilir. "
            "Tarayıcı cookie yöntemiyle devam etmeyi deneyin."
        ) from exc
    save_session(bundle)
    return bundle
