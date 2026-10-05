from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from . import i18n
from .i18n import t
from .auth import (
    LOGIN_FLAG,
    AuthError,
    from_browser,
    from_cookie_header,
    from_manual,
    from_webview_login,
    load_session,
)
from .client import ExportStopped, XRequestError, default_output_path, export_likes
from .models import AuthBundle


class TweetDownApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.lang = i18n.get_language()
        os.environ["TWEETDOWN_LANG"] = self.lang

        self.auth: AuthBundle | None = load_session()
        self.worker: threading.Thread | None = None
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.stop_requested = False
        self.last_output: Path | None = None

        # (widget, key) pairs whose text is re-applied when the language changes.
        self._i18n_widgets: list[tuple[tk.Widget, str]] = []
        self._status_key: str | None = None
        self._status_kw: dict[str, Any] = {}

        self.auth_token_var = tk.StringVar()
        self.ct0_var = tk.StringVar()
        self.user_id_var = tk.StringVar(value=self.auth.user_id if self.auth else "")
        self.browser_var = tk.StringVar(value="auto")
        self.cookie_header_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(default_output_path()))
        self.include_raw_var = tk.BooleanVar(value=False)
        self.resume_var = tk.BooleanVar(value=True)
        self.page_delay_var = tk.DoubleVar(value=1.0)
        self.max_pages_var = tk.StringVar()
        self.status_var = tk.StringVar()

        self.title(t("app_title"))
        self.geometry("780x660")
        self.minsize(720, 580)

        self._build_ui()
        if self.auth:
            self._set_status_key("status_saved_found", source=self.auth.source)
        else:
            self._set_status_key("status_waiting")
        self.after(150, self._drain_events)

    # ---- i18n helpers ----
    def _reg(self, widget: tk.Widget, key: str) -> tk.Widget:
        widget.configure(text=t(key))
        self._i18n_widgets.append((widget, key))
        return widget

    def _set_status_key(self, key: str, **kwargs: Any) -> None:
        self._status_key = key
        self._status_kw = kwargs
        self.status_var.set(t(key, **kwargs))

    def _toggle_language(self) -> None:
        self.lang = "tr" if self.lang == "en" else "en"
        i18n.set_language(self.lang)
        os.environ["TWEETDOWN_LANG"] = self.lang
        self._apply_language()

    def _apply_language(self) -> None:
        self.title(t("app_title"))
        for widget, key in self._i18n_widgets:
            try:
                widget.configure(text=t(key))
            except tk.TclError:
                pass
        self.lang_button.configure(text=t("lang_switch_to"))
        self._update_adv_toggle()
        if self._status_key:
            self.status_var.set(t(self._status_key, **self._status_kw))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self._reg(ttk.Label(header, font=("Segoe UI", 16, "bold")), "heading").grid(
            row=0, column=0, sticky="w"
        )
        self.lang_button = ttk.Button(header, text=t("lang_switch_to"), width=9, command=self._toggle_language)
        self.lang_button.grid(row=0, column=1, sticky="e")

        auth_frame = self._reg(ttk.LabelFrame(root, padding=12), "frame_session")
        auth_frame.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        auth_frame.columnconfigure(0, weight=1)

        self.webview_button = self._reg(
            ttk.Button(auth_frame, command=self._load_webview_auth), "btn_webview_login"
        )
        self.webview_button.grid(row=0, column=0, sticky="w")
        self._reg(ttk.Label(auth_frame, foreground="#777777"), "hint_webview").grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

        self._reg(ttk.Button(auth_frame, command=self._load_saved_auth), "btn_use_saved").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

        self.advanced_visible = False
        self.adv_toggle = ttk.Button(auth_frame, text=t("adv_collapsed"), command=self._toggle_advanced)
        self.adv_toggle.grid(row=2, column=0, sticky="w", pady=(10, 0))

        adv = ttk.Frame(auth_frame)
        adv.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        adv.columnconfigure(1, weight=1)
        adv.columnconfigure(3, weight=1)
        adv.grid_remove()
        self.advanced_frame = adv

        self._reg(ttk.Label(adv), "lbl_browser").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            adv,
            textvariable=self.browser_var,
            values=("auto", "chrome", "edge", "firefox", "brave", "opera", "vivaldi"),
            state="readonly",
            width=14,
        ).grid(row=0, column=1, sticky="w", padx=(8, 8))
        self._reg(ttk.Button(adv, command=self._load_browser_auth), "btn_browser_get").grid(
            row=0, column=2, columnspan=2, sticky="w"
        )

        ttk.Label(adv, text="auth_token").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(adv, textvariable=self.auth_token_var, show="*", width=32).grid(
            row=1, column=1, sticky="ew", padx=(8, 8), pady=(10, 0)
        )
        ttk.Label(adv, text="ct0").grid(row=1, column=2, sticky="w", pady=(10, 0))
        ttk.Entry(adv, textvariable=self.ct0_var, show="*", width=32).grid(
            row=1, column=3, sticky="ew", padx=(8, 0), pady=(10, 0)
        )

        self._reg(ttk.Label(adv), "lbl_user_id").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(adv, textvariable=self.user_id_var).grid(
            row=2, column=1, sticky="ew", padx=(8, 8), pady=(8, 0)
        )
        self._reg(ttk.Button(adv, command=self._load_manual_auth), "btn_manual_save").grid(
            row=2, column=2, columnspan=2, sticky="w", pady=(8, 0)
        )
        self._reg(ttk.Label(adv), "lbl_cookie_header").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(adv, textvariable=self.cookie_header_var, show="*").grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(8, 8), pady=(8, 0)
        )
        self._reg(ttk.Button(adv, command=self._load_cookie_header_auth), "btn_cookie_get").grid(
            row=3, column=3, sticky="w", pady=(8, 0)
        )

        export_frame = self._reg(ttk.LabelFrame(root, padding=12), "frame_export")
        export_frame.grid(row=2, column=0, sticky="ew", pady=8)
        export_frame.columnconfigure(1, weight=1)

        self._reg(ttk.Label(export_frame), "lbl_json_file").grid(row=0, column=0, sticky="w")
        ttk.Entry(export_frame, textvariable=self.output_var).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self._reg(ttk.Button(export_frame, command=self._choose_output), "btn_choose").grid(
            row=0, column=2, sticky="w"
        )

        self._reg(ttk.Checkbutton(export_frame, variable=self.resume_var), "chk_resume").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self._reg(ttk.Checkbutton(export_frame, variable=self.include_raw_var), "chk_raw").grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        self._reg(ttk.Label(export_frame), "lbl_page_delay").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(export_frame, from_=0.5, to=10.0, increment=0.5, textvariable=self.page_delay_var, width=8).grid(
            row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0)
        )
        self._reg(ttk.Label(export_frame), "lbl_max_pages").grid(row=2, column=1, sticky="w", padx=(110, 0), pady=(8, 0))
        ttk.Entry(export_frame, textvariable=self.max_pages_var, width=10).grid(
            row=2, column=1, sticky="w", padx=(200, 0), pady=(8, 0)
        )

        self._reg(ttk.Button(export_frame, command=self._open_viewer), "btn_open_viewer").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(12, 0)
        )

        log_frame = self._reg(ttk.LabelFrame(root, padding=12), "frame_status")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=8)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

        action_frame = ttk.Frame(root)
        action_frame.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        action_frame.columnconfigure(0, weight=1)
        ttk.Label(action_frame, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.start_button = self._reg(ttk.Button(action_frame, command=self._start_export), "btn_start")
        self.start_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.stop_button = self._reg(ttk.Button(action_frame, command=self._stop_export, state=tk.DISABLED), "btn_stop")
        self.stop_button.grid(row=0, column=2, sticky="e", padx=(8, 0))

    def _update_adv_toggle(self) -> None:
        self.adv_toggle.configure(text=t("adv_expanded") if self.advanced_visible else t("adv_collapsed"))

    def _append_log(self, message: str) -> None:
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.status_var.set(message)
        self._status_key = None  # a raw log line is showing now, not a keyed status

    def _set_auth(self, bundle: AuthBundle, *, announce: bool = True) -> None:
        self.auth = bundle
        self.user_id_var.set(bundle.user_id)
        self._append_log(t("log_login_ok", source=bundle.source, user_id=bundle.user_id))
        self._set_status_key("status_ready", source=bundle.source)
        if announce:
            messagebox.showinfo(
                t("dlg_login_ok_title"),
                t("dlg_login_ok_msg", user_id=bundle.user_id, source=bundle.source),
            )

    def _run_auth_job(self, fn: Any) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(t("dlg_busy_title"), t("dlg_busy_running"))
            return

        def job() -> None:
            try:
                self.events.put(("auth", fn()))
            except Exception as exc:
                self.events.put(("error", exc))

        self.worker = threading.Thread(target=job, daemon=True)
        self.worker.start()

    def _load_saved_auth(self) -> None:
        bundle = load_session()
        if not bundle:
            messagebox.showwarning(t("dlg_no_saved_title"), t("dlg_no_saved_msg"))
            return
        self._set_auth(bundle)

    def _toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_frame.grid()
        else:
            self.advanced_frame.grid_remove()
        self._update_adv_toggle()

    def _load_webview_auth(self) -> None:
        self._append_log(t("log_webview_opening"))
        self._run_auth_job(from_webview_login)

    def _load_browser_auth(self) -> None:
        self._append_log(t("log_browser_reading"))
        self._run_auth_job(lambda: from_browser(self.browser_var.get()))

    def _load_manual_auth(self) -> None:
        try:
            self._set_auth(
                from_manual(
                    self.auth_token_var.get(),
                    self.ct0_var.get(),
                    self.user_id_var.get(),
                )
            )
        except AuthError as exc:
            messagebox.showerror(t("dlg_auth_error_title"), str(exc))

    def _load_cookie_header_auth(self) -> None:
        try:
            self._set_auth(from_cookie_header(self.cookie_header_var.get(), self.user_id_var.get()))
        except AuthError as exc:
            messagebox.showerror(t("dlg_auth_error_title"), str(exc))

    def _find_last_json(self) -> Path | None:
        if self.last_output and self.last_output.exists():
            return self.last_output
        from .state import BASE_DIR

        candidates: list[Path] = []
        current = Path(self.output_var.get())
        if current.exists():
            candidates.append(current)
        base = BASE_DIR.resolve()
        # Look in the output folder, the app folder, the working directory, and
        # (when running from dist/) the project folder next to it.
        search_dirs = {current.parent, base, base.parent, Path.cwd()}
        for directory in search_dirs:
            try:
                candidates.extend(Path(directory).glob("x_likes_*.json"))
            except OSError:
                pass
        candidates = [c for c in candidates if c.exists()]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _open_viewer(self) -> None:
        path = self._find_last_json()
        try:
            from .viewer import open_in_viewer

            open_in_viewer(path)  # path may be None -> viewer shows file picker
        except Exception as exc:  # noqa: BLE001 - surface any failure to the user
            messagebox.showerror(t("dlg_error_title"), t("err_viewer_open", exc=exc))
            return
        if path:
            self._append_log(t("log_viewer_opened", name=path.name))
        else:
            self._append_log(t("log_viewer_opened_nojson"))

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title=t("dlg_save_json_title"),
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), (t("filetype_all"), "*.*")),
            initialfile=Path(self.output_var.get()).name,
        )
        if path:
            self.output_var.set(path)

    def _start_export(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(t("dlg_busy_title"), t("dlg_busy_already"))
            return
        if not self.auth:
            try:
                self.auth = from_manual(
                    self.auth_token_var.get(),
                    self.ct0_var.get(),
                    self.user_id_var.get(),
                )
            except AuthError:
                messagebox.showwarning(t("dlg_session_needed_title"), t("dlg_session_needed_msg"))
                return
        try:
            max_pages = int(self.max_pages_var.get()) if self.max_pages_var.get().strip() else None
        except ValueError:
            max_pages = 0
        if max_pages is not None and max_pages < 1:
            messagebox.showerror(t("dlg_invalid_title"), t("dlg_invalid_maxpages"))
            return

        self.stop_requested = False
        self.last_output = Path(self.output_var.get())
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._append_log(t("log_download_start"))

        output_path = Path(self.output_var.get())

        def progress(message: str) -> None:
            self.events.put(("log", message))

        def should_stop() -> bool:
            return self.stop_requested

        def job() -> None:
            try:
                result = export_likes(
                    auth=self.auth,
                    output_path=output_path,
                    include_raw=self.include_raw_var.get(),
                    resume=self.resume_var.get(),
                    max_pages=max_pages,
                    page_delay=float(self.page_delay_var.get()),
                    progress=progress,
                    should_stop=should_stop,
                )
                self.events.put(("done", result))
            except Exception as exc:
                self.events.put(("error", exc))

        self.worker = threading.Thread(target=job, daemon=True)
        self.worker.start()

    def _stop_export(self) -> None:
        self.stop_requested = True
        self._append_log(t("log_stop_requested"))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "auth":
                self._set_auth(payload)
            elif kind == "done":
                self.start_button.configure(state=tk.NORMAL)
                self.stop_button.configure(state=tk.DISABLED)
                metadata = payload.get("metadata", {})
                count = metadata.get("tweet_count", 0)
                if metadata.get("complete", True):
                    self._append_log(t("log_done", count=count))
                    messagebox.showinfo(t("dlg_done_title"), t("dlg_done_msg", count=count))
                else:
                    message = t("msg_partial", count=count)
                    self._append_log(message)
                    messagebox.showinfo(t("dlg_partial_title"), message)
            elif kind == "error":
                self.start_button.configure(state=tk.NORMAL)
                self.stop_button.configure(state=tk.DISABLED)
                message = str(payload)
                if isinstance(payload, ExportStopped):
                    self._append_log(message)
                    messagebox.showinfo(t("dlg_stopped_title"), message)
                elif isinstance(payload, (AuthError, XRequestError)):
                    self._append_log(t("log_error_prefix", msg=message))
                    messagebox.showerror(t("dlg_error_title"), message)
                else:
                    self._append_log(t("log_unexpected_prefix", msg=message))
                    messagebox.showerror(t("dlg_unexpected_title"), message)
        self.after(150, self._drain_events)


def main() -> None:
    # A frozen EXE re-launches itself with this flag to show the login window.
    if len(sys.argv) >= 3 and sys.argv[1] == LOGIN_FLAG:
        from .webview_login import run

        run(sys.argv[2])
        return
    app = TweetDownApp()
    app.mainloop()
