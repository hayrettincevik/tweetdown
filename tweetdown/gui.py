from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

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
        self.title("TweetDown - X Beğeni JSON İndirici")
        self.geometry("780x640")
        self.minsize(720, 560)

        self.auth: AuthBundle | None = load_session()
        self.worker: threading.Thread | None = None
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.stop_requested = False
        self.last_output: Path | None = None

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
        self.status_var = tk.StringVar(
            value=f"Kayıtlı oturum bulundu: {self.auth.source}" if self.auth else "Oturum bekleniyor"
        )

        self._build_ui()
        self.after(150, self._drain_events)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        title = ttk.Label(root, text="X beğenilerini JSON olarak indir", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")

        auth_frame = ttk.LabelFrame(root, text="Oturum", padding=12)
        auth_frame.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        auth_frame.columnconfigure(0, weight=1)

        self.webview_button = ttk.Button(
            auth_frame, text="X'te Oturum Aç (önerilen)", command=self._load_webview_auth
        )
        self.webview_button.grid(row=0, column=0, sticky="w")
        ttk.Label(
            auth_frame,
            text="Açılan pencerede X'e giriş yapın; gerisi otomatik.",
            foreground="#777777",
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        ttk.Button(auth_frame, text="Kayıtlı Oturumu Kullan", command=self._load_saved_auth).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

        self.advanced_visible = False
        self.adv_toggle = ttk.Button(
            auth_frame, text="▸ Gelişmiş (manuel / cookie / tarayıcı)", command=self._toggle_advanced
        )
        self.adv_toggle.grid(row=2, column=0, sticky="w", pady=(10, 0))

        # --- collapsible advanced section (hidden by default) ---
        adv = ttk.Frame(auth_frame)
        adv.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        adv.columnconfigure(1, weight=1)
        adv.columnconfigure(3, weight=1)
        adv.grid_remove()
        self.advanced_frame = adv

        ttk.Label(adv, text="Tarayıcı").grid(row=0, column=0, sticky="w")
        browser = ttk.Combobox(
            adv,
            textvariable=self.browser_var,
            values=("auto", "chrome", "edge", "firefox", "brave", "opera", "vivaldi"),
            state="readonly",
            width=14,
        )
        browser.grid(row=0, column=1, sticky="w", padx=(8, 8))
        ttk.Button(adv, text="Tarayıcıdan Oturumu Al", command=self._load_browser_auth).grid(
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

        ttk.Label(adv, text="Numeric user id").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(adv, textvariable=self.user_id_var).grid(
            row=2, column=1, sticky="ew", padx=(8, 8), pady=(8, 0)
        )
        ttk.Button(adv, text="Manuel Oturumu Kaydet", command=self._load_manual_auth).grid(
            row=2, column=2, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Label(adv, text="Cookie header").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(adv, textvariable=self.cookie_header_var, show="*").grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(8, 8), pady=(8, 0)
        )
        ttk.Button(adv, text="Cookie Header'dan Al", command=self._load_cookie_header_auth).grid(
            row=3, column=3, sticky="w", pady=(8, 0)
        )

        export_frame = ttk.LabelFrame(root, text="Dışa aktar", padding=12)
        export_frame.grid(row=2, column=0, sticky="ew", pady=8)
        export_frame.columnconfigure(1, weight=1)

        ttk.Label(export_frame, text="JSON dosyası").grid(row=0, column=0, sticky="w")
        ttk.Entry(export_frame, textvariable=self.output_var).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(export_frame, text="Seç", command=self._choose_output).grid(row=0, column=2, sticky="w")

        ttk.Checkbutton(export_frame, text="Kaldığı yerden devam et", variable=self.resume_var).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(export_frame, text="Ham X cevaplarını da sakla", variable=self.include_raw_var).grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Label(export_frame, text="Sayfa gecikmesi").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(export_frame, from_=0.5, to=10.0, increment=0.5, textvariable=self.page_delay_var, width=8).grid(
            row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0)
        )
        ttk.Label(export_frame, text="Max sayfa").grid(row=2, column=1, sticky="w", padx=(110, 0), pady=(8, 0))
        ttk.Entry(export_frame, textvariable=self.max_pages_var, width=10).grid(
            row=2, column=1, sticky="w", padx=(180, 0), pady=(8, 0)
        )

        ttk.Button(
            export_frame,
            text="📂 Son indirilen JSON'u görüntüleyicide aç",
            command=self._open_viewer,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))

        log_frame = ttk.LabelFrame(root, text="Durum", padding=12)
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
        self.start_button = ttk.Button(action_frame, text="Beğenileri JSON İndir", command=self._start_export)
        self.start_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.stop_button = ttk.Button(action_frame, text="Durdur", command=self._stop_export, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=2, sticky="e", padx=(8, 0))

    def _append_log(self, message: str) -> None:
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.status_var.set(message)

    def _set_auth(self, bundle: AuthBundle, *, announce: bool = True) -> None:
        self.auth = bundle
        self.user_id_var.set(bundle.user_id)
        self.status_var.set(f"✓ Oturum hazır: {bundle.source}")
        self._append_log(f"✓ Giriş başarılı. Kaynak: {bundle.source}, user id: {bundle.user_id}")
        if announce:
            messagebox.showinfo(
                "Giriş başarılı",
                f"Oturum hazır.\n\nUser id: {bundle.user_id}\nKaynak: {bundle.source}\n\n"
                "Artık 'Beğenileri JSON İndir' ile indirmeye başlayabilirsiniz.",
            )

    def _run_auth_job(self, fn: Any) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Çalışıyor", "Devam eden işlem bitmeden yenisi başlatılamaz.")
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
            messagebox.showwarning("Oturum yok", "Kayıtlı oturum bulunamadı.")
            return
        self._set_auth(bundle)

    def _toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_frame.grid()
            self.adv_toggle.configure(text="▾ Gelişmiş (manuel / cookie / tarayıcı)")
        else:
            self.advanced_frame.grid_remove()
            self.adv_toggle.configure(text="▸ Gelişmiş (manuel / cookie / tarayıcı)")

    def _load_webview_auth(self) -> None:
        self._append_log("X oturum açma penceresi açılıyor; giriş yapmanız bekleniyor...")
        self._run_auth_job(from_webview_login)

    def _load_browser_auth(self) -> None:
        self._append_log("Tarayıcı cookie değerleri okunuyor...")
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
            messagebox.showerror("Oturum hatası", str(exc))

    def _load_cookie_header_auth(self) -> None:
        try:
            self._set_auth(from_cookie_header(self.cookie_header_var.get(), self.user_id_var.get()))
        except AuthError as exc:
            messagebox.showerror("Oturum hatası", str(exc))

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
            messagebox.showerror("Hata", f"Görüntüleyici açılamadı: {exc}")
            return
        if path:
            self._append_log(f"Görüntüleyici açıldı: {path.name}")
        else:
            self._append_log("Görüntüleyici açıldı. İndirilmiş JSON bulunamadı; dosyayı kendiniz seçebilirsiniz.")

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="JSON dosyasını kaydet",
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("Tüm dosyalar", "*.*")),
            initialfile=Path(self.output_var.get()).name,
        )
        if path:
            self.output_var.set(path)

    def _start_export(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Çalışıyor", "Zaten çalışan bir işlem var.")
            return
        if not self.auth:
            try:
                self.auth = from_manual(
                    self.auth_token_var.get(),
                    self.ct0_var.get(),
                    self.user_id_var.get(),
                )
            except AuthError:
                messagebox.showwarning("Oturum gerekli", "Önce oturum bilgilerini alın veya girin.")
                return
        try:
            max_pages = int(self.max_pages_var.get()) if self.max_pages_var.get().strip() else None
        except ValueError:
            max_pages = 0
        if max_pages is not None and max_pages < 1:
            messagebox.showerror("Geçersiz değer", "Max sayfa pozitif bir sayı olmalı.")
            return

        self.stop_requested = False
        self.last_output = Path(self.output_var.get())
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._append_log("İndirme başlıyor...")

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
        self._append_log("Durdurma istendi; mevcut sayfa tamamlanınca duracak.")

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
                    self._append_log(f"Tamamlandı. {count} beğeni kaydedildi.")
                    messagebox.showinfo("Tamamlandı", f"{count} beğeni JSON dosyasına kaydedildi.")
                else:
                    message = (
                        f"Max sayfa sınırında duruldu. Şimdiye kadar {count} beğeni kaydedildi; "
                        "devam etmek için 'Kaldığı yerden devam et' açıkken tekrar başlatın."
                    )
                    self._append_log(message)
                    messagebox.showinfo("Kısmi dışa aktarım", message)
            elif kind == "error":
                self.start_button.configure(state=tk.NORMAL)
                self.stop_button.configure(state=tk.DISABLED)
                message = str(payload)
                if isinstance(payload, ExportStopped):
                    self._append_log(message)
                    messagebox.showinfo("Durduruldu", message)
                elif isinstance(payload, (AuthError, XRequestError)):
                    self._append_log("Hata: " + message)
                    messagebox.showerror("Hata", message)
                else:
                    self._append_log("Beklenmeyen hata: " + message)
                    messagebox.showerror("Beklenmeyen hata", message)
        self.after(150, self._drain_events)


def main() -> None:
    # A frozen EXE re-launches itself with this flag to show the login window.
    if len(sys.argv) >= 3 and sys.argv[1] == LOGIN_FLAG:
        from .webview_login import run

        run(sys.argv[2])
        return
    app = TweetDownApp()
    app.mainloop()
