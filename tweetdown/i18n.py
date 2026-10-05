"""Tiny translation layer shared by the GUI and the backend.

English is the default. The GUI flips the language at runtime with
``set_language``; strings created afterwards (logs, dialogs, exceptions) reflect
the current language. The login subprocess picks up the language from the
``TWEETDOWN_LANG`` environment variable.
"""

from __future__ import annotations

import os

LANGUAGES = ("en", "tr")
_lang = os.environ.get("TWEETDOWN_LANG", "en")
if _lang not in LANGUAGES:
    _lang = "en"


def set_language(lang: str) -> None:
    global _lang
    if lang in LANGUAGES:
        _lang = lang


def get_language() -> str:
    return _lang


def t(key: str, **kwargs: object) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_lang) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


STRINGS: dict[str, dict[str, str]] = {
    # ---- GUI: window / headings / frames ----
    "app_title": {"en": "TweetDown — X Likes JSON Exporter", "tr": "TweetDown — X Beğeni JSON İndirici"},
    "heading": {"en": "Export your X likes as JSON", "tr": "X beğenilerini JSON olarak indir"},
    "frame_session": {"en": "Session", "tr": "Oturum"},
    "frame_export": {"en": "Export", "tr": "Dışa aktar"},
    "frame_status": {"en": "Status", "tr": "Durum"},
    # ---- GUI: session controls ----
    "btn_webview_login": {"en": "Log in to X (recommended)", "tr": "X'te Oturum Aç (önerilen)"},
    "hint_webview": {
        "en": "Log in to X in the window that opens; the rest is automatic.",
        "tr": "Açılan pencerede X'e giriş yapın; gerisi otomatik.",
    },
    "btn_use_saved": {"en": "Use saved session", "tr": "Kayıtlı Oturumu Kullan"},
    "adv_collapsed": {"en": "▸ Advanced (manual / cookie / browser)", "tr": "▸ Gelişmiş (manuel / cookie / tarayıcı)"},
    "adv_expanded": {"en": "▾ Advanced (manual / cookie / browser)", "tr": "▾ Gelişmiş (manuel / cookie / tarayıcı)"},
    "lbl_browser": {"en": "Browser", "tr": "Tarayıcı"},
    "btn_browser_get": {"en": "Get session from browser", "tr": "Tarayıcıdan Oturumu Al"},
    "lbl_user_id": {"en": "Numeric user id", "tr": "Numeric user id"},
    "btn_manual_save": {"en": "Save manual session", "tr": "Manuel Oturumu Kaydet"},
    "lbl_cookie_header": {"en": "Cookie header", "tr": "Cookie header"},
    "btn_cookie_get": {"en": "Load from cookie header", "tr": "Cookie Header'dan Al"},
    # ---- GUI: export controls ----
    "lbl_json_file": {"en": "JSON file", "tr": "JSON dosyası"},
    "btn_choose": {"en": "Choose", "tr": "Seç"},
    "chk_resume": {"en": "Resume where it left off", "tr": "Kaldığı yerden devam et"},
    "chk_raw": {"en": "Also keep raw X responses", "tr": "Ham X cevaplarını da sakla"},
    "lbl_page_delay": {"en": "Page delay", "tr": "Sayfa gecikmesi"},
    "lbl_max_pages": {"en": "Max pages", "tr": "Max sayfa"},
    "btn_open_viewer": {
        "en": "📂 Open last downloaded JSON in viewer",
        "tr": "📂 Son indirilen JSON'u görüntüleyicide aç",
    },
    # ---- GUI: actions ----
    "btn_start": {"en": "Download likes as JSON", "tr": "Beğenileri JSON İndir"},
    "btn_stop": {"en": "Stop", "tr": "Durdur"},
    "lang_switch_to": {"en": "Türkçe", "tr": "English"},
    # ---- GUI: status / logs ----
    "status_waiting": {"en": "Waiting for session", "tr": "Oturum bekleniyor"},
    "status_saved_found": {"en": "Saved session found: {source}", "tr": "Kayıtlı oturum bulundu: {source}"},
    "status_ready": {"en": "✓ Session ready: {source}", "tr": "✓ Oturum hazır: {source}"},
    "log_login_ok": {
        "en": "✓ Login successful. Source: {source}, user id: {user_id}",
        "tr": "✓ Giriş başarılı. Kaynak: {source}, user id: {user_id}",
    },
    "log_webview_opening": {
        "en": "Opening the X login window; waiting for you to sign in...",
        "tr": "X oturum açma penceresi açılıyor; giriş yapmanız bekleniyor...",
    },
    "log_browser_reading": {"en": "Reading browser cookies...", "tr": "Tarayıcı cookie değerleri okunuyor..."},
    "log_download_start": {"en": "Starting download...", "tr": "İndirme başlıyor..."},
    "log_stop_requested": {
        "en": "Stop requested; it will stop after the current page.",
        "tr": "Durdurma istendi; mevcut sayfa tamamlanınca duracak.",
    },
    "log_done": {"en": "Done. {count} likes saved.", "tr": "Tamamlandı. {count} beğeni kaydedildi."},
    "log_error_prefix": {"en": "Error: {msg}", "tr": "Hata: {msg}"},
    "log_unexpected_prefix": {"en": "Unexpected error: {msg}", "tr": "Beklenmeyen hata: {msg}"},
    "log_viewer_opened": {"en": "Viewer opened: {name}", "tr": "Görüntüleyici açıldı: {name}"},
    "log_viewer_opened_nojson": {
        "en": "Viewer opened. No downloaded JSON found; you can pick a file yourself.",
        "tr": "Görüntüleyici açıldı. İndirilmiş JSON bulunamadı; dosyayı kendiniz seçebilirsiniz.",
    },
    # ---- GUI: dialogs ----
    "dlg_login_ok_title": {"en": "Login successful", "tr": "Giriş başarılı"},
    "dlg_login_ok_msg": {
        "en": "Session ready.\n\nUser id: {user_id}\nSource: {source}\n\n"
              "You can now start downloading with 'Download likes as JSON'.",
        "tr": "Oturum hazır.\n\nUser id: {user_id}\nKaynak: {source}\n\n"
              "Artık 'Beğenileri JSON İndir' ile indirmeye başlayabilirsiniz.",
    },
    "dlg_busy_title": {"en": "Working", "tr": "Çalışıyor"},
    "dlg_busy_running": {
        "en": "A running task must finish before starting another.",
        "tr": "Devam eden işlem bitmeden yenisi başlatılamaz.",
    },
    "dlg_busy_already": {"en": "A task is already running.", "tr": "Zaten çalışan bir işlem var."},
    "dlg_no_saved_title": {"en": "No session", "tr": "Oturum yok"},
    "dlg_no_saved_msg": {"en": "No saved session found.", "tr": "Kayıtlı oturum bulunamadı."},
    "dlg_auth_error_title": {"en": "Session error", "tr": "Oturum hatası"},
    "dlg_error_title": {"en": "Error", "tr": "Hata"},
    "err_viewer_open": {"en": "Could not open the viewer: {exc}", "tr": "Görüntüleyici açılamadı: {exc}"},
    "dlg_save_json_title": {"en": "Save JSON file", "tr": "JSON dosyasını kaydet"},
    "filetype_all": {"en": "All files", "tr": "Tüm dosyalar"},
    "dlg_session_needed_title": {"en": "Session required", "tr": "Oturum gerekli"},
    "dlg_session_needed_msg": {
        "en": "Get or enter your session details first.",
        "tr": "Önce oturum bilgilerini alın veya girin.",
    },
    "dlg_invalid_title": {"en": "Invalid value", "tr": "Geçersiz değer"},
    "dlg_invalid_maxpages": {"en": "Max pages must be a positive number.", "tr": "Max sayfa pozitif bir sayı olmalı."},
    "dlg_done_title": {"en": "Done", "tr": "Tamamlandı"},
    "dlg_done_msg": {"en": "{count} likes saved to the JSON file.", "tr": "{count} beğeni JSON dosyasına kaydedildi."},
    "dlg_partial_title": {"en": "Partial export", "tr": "Kısmi dışa aktarım"},
    "msg_partial": {
        "en": "Stopped at the max-pages limit. {count} likes saved so far; to continue, "
              "start again with 'Resume where it left off' enabled.",
        "tr": "Max sayfa sınırında duruldu. Şimdiye kadar {count} beğeni kaydedildi; "
              "devam etmek için 'Kaldığı yerden devam et' açıkken tekrar başlatın.",
    },
    "dlg_stopped_title": {"en": "Stopped", "tr": "Durduruldu"},
    "dlg_unexpected_title": {"en": "Unexpected error", "tr": "Beklenmeyen hata"},
    "no_viewer_file_warn": {
        "en": "No JSON found to view. Download your likes first, or choose a valid file in 'JSON file'.",
        "tr": "Görüntülenecek bir JSON bulunamadı. Önce beğenileri indirin ya da 'JSON dosyası' alanında geçerli bir dosya seçin.",
    },
    # ---- webview login window ----
    "webview_window_title": {"en": "TweetDown — Log in to X", "tr": "TweetDown — X'te Oturum Aç"},
    # ---- backend: client.py ----
    "cl_discover_qid": {"en": "Discovering X query id...", "tr": "X query id keşfediliyor..."},
    "cl_resuming": {"en": "Resuming where it left off...", "tr": "Kaldığı yerden devam ediliyor..."},
    "cl_reading_fresh": {"en": "Reading likes from the start...", "tr": "Beğeniler baştan okunuyor..."},
    "cl_stopped": {"en": "Download stopped. You can resume later.", "tr": "İndirme durduruldu. Daha sonra devam edebilirsiniz."},
    "cl_extra_var": {"en": "X requested extra variable(s), adding: {names}", "tr": "X ek değişken istedi, ekleniyor: {names}"},
    "cl_qid_refresh": {"en": "Refreshing query id...", "tr": "Query id yenileniyor..."},
    "cl_failed_auto": {
        "en": "The request failed despite automatic fixes. The X API may be returning an unexpected response.",
        "tr": "İstek, otomatik düzeltmelere rağmen başarısız oldu. X API'si beklenmedik bir yanıt veriyor olabilir.",
    },
    "cl_page_progress": {"en": "Page {page}: {fresh} new likes, {total} total", "tr": "Sayfa {page}: {fresh} yeni beğeni, toplam {total}"},
    "cl_json_saved": {"en": "JSON saved: {path}", "tr": "JSON kaydedildi: {path}"},
    "cl_maxpages_saved": {
        "en": "Reached the max-pages limit; progress saved, you can resume.",
        "tr": "Max sayfa sınırına ulaşıldı; ilerleme saklandı, kaldığı yerden devam edebilirsiniz.",
    },
    "cl_missing_vars": {"en": "Missing GraphQL variables: {names}", "tr": "Eksik GraphQL değişkenleri: {names}"},
    "cl_err_rejected": {
        "en": "X rejected the session. The cookie/login details are invalid or expired.",
        "tr": "X oturumu reddetti. Cookie/login bilgileri geçersiz veya süresi dolmuş.",
    },
    "cl_err_ratelimit": {
        "en": "X returned a rate limit. Resume later from where you left off.",
        "tr": "X rate limit verdi. Bir süre sonra kaldığınız yerden devam edin.",
    },
    "cl_err_ratelimit_reset": {"en": " Rate limit reset: {reset}", "tr": " Rate limit reset: {reset}"},
    "cl_err_qid_stale": {"en": "The Likes GraphQL query id looks outdated.", "tr": "Likes GraphQL query id eskimiş görünüyor."},
    "cl_err_graphql": {"en": "X GraphQL error: {message}", "tr": "X GraphQL hatası: {message}"},
    "cl_err_http": {"en": "X HTTP {status}: {text}", "tr": "X HTTP {status}: {text}"},
    "cl_err_httpx": {
        "en": "httpx is not installed. Run `python -m pip install -r requirements.txt` first.",
        "tr": "httpx kurulu değil. Önce `python -m pip install -r requirements.txt` çalıştırın.",
    },
    # ---- backend: auth.py ----
    "au_user_id_needed": {
        "en": "A numeric user id is required. It could not be resolved from the session automatically.",
        "tr": "Numeric user id gerekli. Oturumdan otomatik çözülemedi.",
    },
    "au_user_id_numeric": {"en": "User id must be numeric.", "tr": "User id numeric olmalı."},
    "au_login_start_fail": {"en": "Could not start the login window.", "tr": "Oturum açma penceresi başlatılamadı."},
    "au_login_timeout": {"en": "Login timed out. Please try again.", "tr": "Oturum açma zaman aşımına uğradı. Lütfen tekrar deneyin."},
    "au_login_incomplete": {
        "en": "Login was not completed. Sign in to X in the window that opens; "
              "it closes automatically once login succeeds.",
        "tr": "Giriş tamamlanmadı. Açılan pencerede X'e giriş yapın; "
              "giriş başarılı olunca pencere kendiliğinden kapanır.",
    },
    "au_login_no_userid": {
        "en": "Login succeeded but the numeric user id could not be resolved. Enter the user id manually.",
        "tr": "Giriş başarılı ama numeric user id çözülemedi. User id alanını elle girin.",
    },
    "au_browser_no_twid": {
        "en": "auth_token and ct0 were read but twid (for the numeric user id) was not found. "
              "Enter the user id manually and save auth_token/ct0 by hand.",
        "tr": "auth_token ve ct0 okundu ama numeric user id için twid bulunamadı. "
              "User id alanını manuel girip auth_token/ct0 değerlerini manuel kaydedin.",
    },
    "au_browser_not_found_profile": {
        "en": "auth_token, ct0 and twid were not found in the browser. "
              "Make sure the x.com tab is open in the selected Chrome profile.",
        "tr": "Tarayıcıdan auth_token, ct0 ve twid bulunamadı. "
              "x.com sekmesinin seçili Chrome profilinde açık olduğundan emin olun.",
    },
    "au_bc3_missing": {
        "en": "browser-cookie3 is not installed. Install the requirements.txt dependencies.",
        "tr": "browser-cookie3 kurulu değil. requirements.txt kurulumunu yapın.",
    },
    "au_browser_not_found_hint": {
        "en": "auth_token, ct0 and twid were not found in the browser. Make sure you are logged in at x.com. "
              "If that fails, copy the full Cookie header from DevTools > Network and paste it into the "
              "app's Cookie header field.",
        "tr": "Tarayıcıdan auth_token, ct0 ve twid bulunamadı. x.com'da giriş yaptığınızdan emin olun. "
              "Olmazsa DevTools > Network içinden tam Cookie header'ını kopyalayıp uygulamadaki "
              "Cookie Header alanına yapıştırın.",
    },
    "au_detail_suffix": {"en": " Detail: {detail}", "tr": " Detay: {detail}"},
    "au_last_errors": {"en": " Last errors: {detail}", "tr": " Son hatalar: {detail}"},
    "au_chromium_reader": {"en": " Chromium reader: {detail}", "tr": " Chromium okuyucu: {detail}"},
    "au_twikit_missing": {
        "en": "twikit is not installed. Install the requirements.txt dependencies.",
        "tr": "twikit kurulu değil. requirements.txt kurulumunu yapın.",
    },
    "au_login_cookies_missing": {
        "en": "Login appeared to succeed but the required cookie values were not obtained.",
        "tr": "Giriş başarılı görünse de gerekli cookie değerleri alınamadı.",
    },
    "au_user_pass_needed": {"en": "Username and password are required.", "tr": "Kullanıcı adı ve şifre gerekli."},
    "au_login_failed": {
        "en": "X login failed. A captcha, 2FA or security check may have appeared. "
              "Try the browser-cookie method instead.",
        "tr": "X login başarısız oldu. Captcha, 2FA veya güvenlik kontrolü çıkmış olabilir. "
              "Tarayıcı cookie yöntemiyle devam etmeyi deneyin.",
    },
    "au_token_required": {"en": "auth_token and ct0 are required.", "tr": "auth_token ve ct0 gerekli."},
    # ---- backend: chromium_cookies.py ----
    "cc_no_localappdata": {"en": "LOCALAPPDATA not found.", "tr": "LOCALAPPDATA bulunamadı."},
    "cc_pywin32_missing": {
        "en": "pywin32 is not installed; the requirements.txt install is required.",
        "tr": "pywin32 kurulu değil; requirements.txt kurulumu gerekli.",
    },
    "cc_no_cookies_profile": {
        "en": "Chromium profiles were read but no x.com login cookies were found. "
              "Make sure the open x.com tab is in the correct Chrome profile.",
        "tr": "Chromium profilleri okundu ama x.com giriş cookie'leri bulunamadı. "
              "Açık x.com sekmesinin doğru Chrome profilinde olduğundan emin olun.",
    },
    "cc_no_cookies": {"en": "Could not read Chromium cookies.", "tr": "Chromium cookie okunamadı."},
    # ---- backend: query_ids.py ----
    "qi_httpx_missing": {
        "en": "httpx is not installed. Run `python -m pip install -r requirements.txt` first.",
        "tr": "httpx kurulu değil. Önce `python -m pip install -r requirements.txt` çalıştırın.",
    },
    "qi_not_found": {"en": "Query id not found: {names}", "tr": "Query id bulunamadı: {names}"},
}
