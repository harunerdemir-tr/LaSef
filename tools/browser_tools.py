import os
import sys
import time
import threading
import http.server
import socketserver
from typing import Dict, Any, List, Optional
from PIL import ImageGrab

_playwright_available = False
try:
    from playwright.sync_api import sync_playwright
    _playwright_available = True
except ImportError:
    _playwright_available = False

class LocalHttpServerManager:
    """Üretilen web projelerini tarayıcı testi için yerel HTTP sunucusunda başlatır."""
    def __init__(self):
        self._server = None
        self._thread = None
        self._current_dir = ""
        self._current_port = 8099
        self._lock = threading.Lock()

    def start_server(self, directory: str, port: int = 8099) -> str:
        with self._lock:
            if self._server:
                if self._current_dir == os.path.abspath(directory):
                    return f"http://127.0.0.1:{self._current_port}"
                self.stop_server()

            self._current_dir = os.path.abspath(directory)
            self._current_port = port

            class QuietHandler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=directory, **kwargs)
                def log_message(self, format, *args):
                    pass

            for p in range(port, port + 20):
                try:
                    self._server = socketserver.TCPServer(("127.0.0.1", p), QuietHandler)
                    self._current_port = p
                    break
                except OSError:
                    continue

            if not self._server:
                return ""

            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            return f"http://127.0.0.1:{self._current_port}"

    def stop_server(self):
        with self._lock:
            if self._server:
                try:
                    self._server.shutdown()
                    self._server.server_close()
                except Exception:
                    pass
                self._server = None
                self._thread = None

class BrowserAutomationEngine:
    """
    🌐 Playwright Destekli Canlı Tarayıcı Otomasyonu (Browser Automation Engine)
    - Sayfayı açar, yükler ve JavaScript render'ını bekler
    - Konsol loglarını (console.error, console.warn) canlı yakalar
    - DOM elementlerine tıklar, metin yazar, etkileşimde bulunur
    - Ekran görüntüsü çekip Vision modeline analiz için hazırlar
    """
    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None
        self._console_logs = []
        self._page_errors = []
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return _playwright_available

    def open_page(self, url: str, headless: bool = True, timeout_ms: int = 20000) -> Dict[str, Any]:
        if not _playwright_available:
            return {"success": False, "error": "Playwright kütüphanesi kurulu değil."}

        with self._lock:
            try:
                self.close()
                self._console_logs.clear()
                self._page_errors.clear()

                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch(
                    headless=headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--autoplay-policy=no-user-gesture-required"]
                )
                context = self._browser.new_context(viewport={"width": 1280, "height": 720})
                self._page = context.new_page()

                self._page.on("console", lambda msg: self._console_logs.append({
                    "type": msg.type,
                    "text": msg.text,
                    "location": msg.location
                }))
                self._page.on("pageerror", lambda err: self._page_errors.append(str(err)))

                response = self._page.goto(url, timeout=timeout_ms, wait_until="load")
                time.sleep(1.0)

                title = self._page.title()
                return {
                    "success": True,
                    "title": title,
                    "url": self._page.url,
                    "status": response.status if response else 200
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    def capture_screenshot(self, output_path: str) -> Dict[str, Any]:
        with self._lock:
            if not self._page:
                return {"success": False, "error": "Aktif bir tarayıcı sayfası yok."}
            try:
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                self._page.screenshot(path=output_path, full_page=False)
                size_kb = os.path.getsize(output_path) / 1024
                return {"success": True, "path": output_path, "size_kb": size_kb}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def click(self, selector: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        with self._lock:
            if not self._page:
                return {"success": False, "error": "Aktif sayfa yok."}
            try:
                self._page.click(selector, timeout=timeout_ms)
                time.sleep(0.5)
                return {"success": True, "selector": selector}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def type_text(self, selector: str, text: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        with self._lock:
            if not self._page:
                return {"success": False, "error": "Aktif sayfa yok."}
            try:
                self._page.fill(selector, text, timeout=timeout_ms)
                return {"success": True, "selector": selector}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def press_key(self, key: str) -> Dict[str, Any]:
        """Klavye tuşuna basar (örn. 'Space', 'ArrowUp', 'Enter', 'KeyW')."""
        with self._lock:
            if not self._page:
                return {"success": False, "error": "Aktif sayfa yok."}
            try:
                self._page.keyboard.press(key)
                return {"success": True, "key": key}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def get_logs_and_errors(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "console_logs": list(self._console_logs),
                "page_errors": list(self._page_errors),
                "has_errors": bool(self._page_errors or any(l["type"] == "error" for l in self._console_logs))
            }

    def inspect_dom(self) -> Dict[str, Any]:
        with self._lock:
            if not self._page:
                return {"success": False, "error": "Aktif sayfa yok."}
            try:
                info = self._page.evaluate("""() => {
                    const canvas = document.querySelector('canvas');
                    const buttons = Array.from(document.querySelectorAll('button')).map(b => b.innerText || b.id || b.className);
                    const allIds = Array.from(document.querySelectorAll('[id]')).map(el => el.id);
                    return {
                        has_canvas: !!canvas,
                        canvas_size: canvas ? { width: canvas.width, height: canvas.height } : null,
                        buttons: buttons.slice(0, 10),
                        ids: allIds.slice(0, 20),
                        title: document.title
                    };
                }""")
                return {"success": True, "dom_info": info}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def close(self):
        try:
            if self._page:
                self._page.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        finally:
            self._page = None
            self._browser = None
            self._pw = None

def capture_desktop_screenshot(output_path: str) -> Dict[str, Any]:
    """OS Masaüstü / Ekran görüntüsünü Pillow ile doğrudan yakalar (Computer Use)."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img = ImageGrab.grab()
        img.save(output_path, "PNG")
        return {"success": True, "path": output_path, "size_kb": os.path.getsize(output_path) / 1024}
    except Exception as e:
        return {"success": False, "error": str(e)}

local_server_manager = LocalHttpServerManager()
browser_engine = BrowserAutomationEngine()
