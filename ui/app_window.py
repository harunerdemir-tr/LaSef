import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from customtkinter import filedialog

from core.branch_memory_manager import (
    branch_memory,
    format_relative_time,
    generate_smart_title,
)
from core.config_manager import load_config
from core.event_bus import EVENT_SCAN_PROGRESS, EVENT_TIMELINE_STAGE, event_bus
from orchestrator import orkestrayi_yonet
from ui.chef_animator import ChefAnimatorCanvas, ChefState

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG_APP = "#0B0F17"
BG_SIDEBAR = "#0E131D"
BG_SURFACE = "#121824"
BG_CARD = "#171F2E"
BG_ELEVATED = "#1C2536"
BG_HOVER = "#212C40"
BORDER_SUBTLE = "#232E42"
BORDER_ACCENT = "#3B82F6"

ACCENT_BLUE = "#3B82F6"
ACCENT_BLUE_HOVER = "#2563EB"
ACCENT_CYAN = "#06B6D4"
ACCENT_GREEN = "#10B981"
ACCENT_AMBER = "#F59E0B"
ACCENT_PURPLE = "#8B5CF6"
ACCENT_RED = "#EF4444"

TEXT_PRIMARY = "#F1F5F9"
TEXT_MUTED = "#94A3B8"
TEXT_DIM = "#64748B"

FONT_UI = "Segoe UI"
FONT_MONO = "Consolas"

SABLONLAR = {
    "Unity 3D": (
        "🎮 Unity 3D TPS",
        "Unity 3D (URP) için modüler Third-Person karakter kontrolcüsü, kamera takibi "
        "(Cinemachine / Smooth Follow), zemin algılama ve Input System uyumlu C# sınıflarını oluştur."
    ),
    "Blender 3D": (
        "🎨 Blender 3D Sahne",
        "Blender MCP ile stilize bir çalışma masası dioraması (monitör, masa lambası, kupa, "
        "PBR materyaller ve 3 nokta stüdyo ışıklandırma) sahneleyip EEVEE/Cycles ile önizleme renderı al."
    ),
    "Web UI": (
        "🌐 Web Uygulama",
        "Modern karanlık temalı, responsive ve sıfır harici bağımlılıklı interaktif bir Web "
        "kontrol paneli / mini oyun (index.html, style.css, app.js) geliştir."
    ),
    "Teknik Rapor": (
        "📊 Teknik Rapor",
        "Bağlı kaynak dosya ve klasörleri analiz et; mimari yapı, tespit edilen hatalar ve "
        "optimizasyon önerilerini içeren yapılandırılmış Türkçe teknik rapor hazırla."
    ),
}

EMPTY_STARTERS = [
    ("🎮 Unity 3D Kontrolcü", "Unity URP TPS hareket, kamera & zıplama sistemi", SABLONLAR["Unity 3D"][1]),
    ("🎨 Blender 3D Sahne", "Otomatik 3D sahne kurulumu, ışık & materyal", SABLONLAR["Blender 3D"][1]),
    ("🌐 Modern Web Arayüzü", "HTML/CSS/JS tam kapsamlı interaktif ürün", SABLONLAR["Web UI"][1]),
    ("📊 Kod & Dosya Analizi", "Eklediğin dosya veya klasörü derinlemesine incele", SABLONLAR["Teknik Rapor"][1]),
]


class ModernTextRedirector:
    """Stdout/Stderr akışını renkli terminale yönlendirir ve animasyon/ajan kartlarını tetikler."""

    def __init__(self, textbox, app_instance, original_stream=None):
        self.textbox = textbox
        self.app = app_instance
        self.original_stream = original_stream
        self._buffer: List[str] = []
        self._buf_lock = threading.Lock()
        self._step_to_aid: Dict[str, str] = {}
        self._file_to_aids: Dict[str, List[str]] = {}
        self._aid_meta: Dict[str, tuple] = {}
        self._tagleri_tanimla()

    @property
    def encoding(self):
        return getattr(self.original_stream, "encoding", "utf-8")

    def clear_buffer(self):
        with self._buf_lock:
            self._buffer.clear()
        self._step_to_aid.clear()
        self._file_to_aids.clear()
        self._aid_meta.clear()

    def get_full_log(self) -> str:
        """Thread-safe log okuma (arka plan thread'lerinden Tkinter widget erişimi yapmaz)."""
        with self._buf_lock:
            return "".join(self._buffer)

    def _tagleri_tanimla(self):
        try:
            self.textbox.tag_config("info", foreground="#94A3B8")
            self.textbox.tag_config("sef", foreground="#FBBF24")
            self.textbox.tag_config("ajan", foreground="#38BDF8")
            self.textbox.tag_config("konsey", foreground="#C4B5FD")
            self.textbox.tag_config("basari", foreground="#34D399")
            self.textbox.tag_config("hata", foreground="#F87171")
            self.textbox.tag_config("mcp", foreground="#22D3EE")
        except Exception:
            pass

    def write(self, string):
        if not string:
            return
        with self._buf_lock:
            self._buffer.append(string)
        if self.original_stream:
            try:
                self.original_stream.write(string)
                self.original_stream.flush()
            except Exception:
                pass
        try:
            if self.app and self.app.winfo_exists():
                self.app.after(0, self._gui_guncelle, string)
        except Exception:
            pass

    def _gui_guncelle(self, string: str):
        try:
            if not self.app.winfo_exists():
                return
        except Exception:
            return

        try:
            self.textbox.configure(state="normal")
            for line in string.splitlines(keepends=True):
                tag = "info"
                if any(k in line for k in ("❌", "HATA", "FATAL", "Traceback", "İPTAL", "BAĞLANTI HATASI")):
                    tag = "hata"
                elif any(k in line for k in ("PROJE BAŞARIYLA TAMAMLANDI", "ŞEF ONAYI", "mühürlendi", "TAMİRİ BAŞARILI")):
                    tag = "basari"
                elif any(k in line for k in ("Hakem Konseyi", "KONSEY", "DENETİM", "VISION")):
                    tag = "konsey"
                elif any(k in line for k in ("UNITY", "BLENDER", "MCP", "WEB OTONOM")):
                    tag = "mcp"
                elif any(k in line for k in ("ŞEF", "MİMAR", "PLAN", "REVİZYON", "MÜDAHALE")):
                    tag = "sef"
                elif "[amele_" in line or "[Adım" in line or "Ajan" in line:
                    tag = "ajan"

                self.textbox.insert("end", line, tag)
                self._parse_live_telemetry(line)

            self.textbox.see("end")
            self.textbox.configure(state="disabled")
        except Exception:
            pass

    def _resolve_unique_aid_by_file(self, line: str) -> Optional[str]:
        m_file = re.search(r"'([^']+)'", line)
        if not m_file:
            return None
        fname = m_file.group(1).strip()
        aids = self._file_to_aids.get(fname) or []
        if len(aids) == 1:
            return aids[0]
        return None

    def _parse_live_telemetry(self, line: str):
        try:
            m_plan = re.search(r"\[Adım\s+(\d+)\]\s+([^\s\[]+)\s+\[([^\]]+)\].*?->\s*(.+)", line)
            if m_plan:
                step_idx, fname, cap, title = m_plan.groups()
                step_clean = step_idx.strip()
                fname_clean = fname.strip()
                cap_clean = cap.strip()
                title_clean = title.strip()
                aid = f"amele_{cap_clean}_{step_clean}"
                display_name = f"{fname_clean} · {cap_clean.upper()}"
                self._step_to_aid[step_clean] = aid
                self._file_to_aids.setdefault(fname_clean, [])
                if aid not in self._file_to_aids[fname_clean]:
                    self._file_to_aids[fname_clean].append(aid)
                self._aid_meta[aid] = (display_name, title_clean)
                self.app.create_or_update_agent_card(
                    aid, display_name, title_clean, "Bekleniyor", "Sırada", "Sırada"
                )
                self.app.set_chef_animation(ChefState.THINKING, hint="Görev planı çıkarılıyor...")
                return

            m_start = re.search(
                r"\[(amele_[^|\]]+)\|\s*([^\]]+)\]\s+'([^']+)'(?:\s+\(([^)]+)\))?\s+görevine başladı(?:\.\.\.)?\s*\(([^)]+)\)",
                line,
            )
            if m_start:
                aid, cap, title, target_file, model = m_start.groups()
                aid_clean = aid.strip()
                cap_clean = cap.strip()
                title_clean = title.strip()
                if target_file and target_file.strip():
                    display_name = f"{target_file.strip()} · {cap_clean.upper()}"
                elif aid_clean in self._aid_meta:
                    display_name = self._aid_meta[aid_clean][0]
                else:
                    display_name = f"{aid_clean} · {cap_clean.upper()}"
                self._aid_meta[aid_clean] = (display_name, title_clean)
                self.app.create_or_update_agent_card(
                    aid_clean, display_name, title_clean, model.strip(), "Çalışıyor", "Aktif"
                )
                self.app.set_chef_animation(
                    ChefState.ORCHESTRATING,
                    hint=f"{cap_clean.upper()} alt ajanı çalıştırılıyor..."
                )
                return

            if "WAITING_SYNC" in line or "Akran Ajan" in line:
                m_peer = re.search(r"\[(amele_[^|\]]+)", line)
                if m_peer:
                    status_label = "Onay Bekliyor" if "WAITING_SYNC" in line else "Senkron"
                    self.app.create_or_update_agent_card(m_peer.group(1).strip(), status=status_label)
                return

            if "kritik hata" in line.lower() or "Revizyon üretim hatası" in line:
                m_err = re.search(r"\[(amele_[^|\]]+)", line)
                if m_err:
                    self.app.create_or_update_agent_card(m_err.group(1).strip(), status="Hata")
                return

            if any(k in line for k in ("ŞEF REVİZYONU", "ŞEF MÜDAHALESİ", "Şef revizyon istedi")):
                m_rev = re.search(r"\[(amele_[^|\]]+)", line)
                aid_rev = m_rev.group(1).strip() if m_rev else self._resolve_unique_aid_by_file(line)
                if aid_rev:
                    self.app.create_or_update_agent_card(aid_rev, status="Revizyon")
                self.app.set_chef_animation(ChefState.AUDITING, hint="Baş Şef revizyon uyguluyor...")
                return

            if any(k in line for k in ("Hakem Konseyi", "BLENDER MCP", "WEB OTONOM TESTİ", "UNITY DERLEME")):
                self.app.set_chef_animation(ChefState.AUDITING, hint="Kalite & doğrulama denetimi...")
                return

            if any(k in line for k in ("Şef onayı alındı", "ŞEF ONAYI", "TAMİRİ BAŞARILI", "KURTARMASI BAŞARILI", "mühürlendi")):
                m_ok = re.search(r"\[(amele_[^|\]]+)", line)
                aid_ok = m_ok.group(1).strip() if m_ok else self._resolve_unique_aid_by_file(line)
                if aid_ok:
                    self.app.create_or_update_agent_card(aid_ok, status="Tamamlandı")
                return

            if "PROJE BAŞARIYLA TAMAMLANDI" in line:
                self.app.set_chef_animation(ChefState.SUCCESS, hint="Proje başarıyla tamamlandı!")
        except Exception:
            pass

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass


SASH_IDLE_BG = "#1A2436"
DEFAULT_SIDEBAR_WIDTH = 250
DEFAULT_INSPECTOR_WIDTH = 390
DEFAULT_COMPOSER_HEIGHT = 64
UI_PREFS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".lasef_ui_prefs.json",
)


class LaSefUI(ctk.CTk):
    """LaSef Studio — Sade, şık, animasyonlu orkestrasyon arayüzü."""

    def __init__(self):
        super().__init__()
        self.title("LaSef Studio — AI Orkestrasyon Şefi")
        self.geometry("1320x840")
        self.minsize(960, 650)
        self.configure(fg_color=BG_APP)

        self.sidebar_width: int = DEFAULT_SIDEBAR_WIDTH
        self.inspector_width: int = DEFAULT_INSPECTOR_WIDTH
        self.composer_height: int = DEFAULT_COMPOSER_HEIGHT
        self._load_ui_prefs()

        self.is_running: bool = False
        self.sidebar_visible: bool = True
        self.inspector_visible: bool = False
        self.search_visible: bool = False
        self.active_inspector_tab: str = "agents"
        self.search_query: str = ""

        self.secilen_klasor: str = ""
        self.secilen_kaynak_klasorler: List[str] = []
        self.secilen_kaynak_tekil_dosyalar: List[str] = []
        self.secilen_kaynak_dosyalar: List[str] = []
        self.agent_cards_data: Dict[str, Dict[str, Any]] = {}
        self._cards_lock = threading.Lock()

        self.active_project_id: Optional[str] = None
        self.active_conversation_id: Optional[str] = None
        self.active_node_id: Optional[str] = None
        self.active_fork_parent_id: Optional[str] = None
        self.nav_history: List[str] = []
        self.nav_index: int = -1

        self._plus_menu_frame: Optional[ctk.CTkFrame] = None
        self._template_subframe: Optional[ctk.CTkFrame] = None
        self._row_menu_frame: Optional[ctk.CTkFrame] = None
        self._placeholder_active: bool = False
        self._placeholder_text: str = (
            "Ne üretmek istediğini yaz... (Gönder: Enter • Alt satır: Shift+Enter)"
        )

        self._timeline_state = {
            "prev": "Hazır",
            "curr": "Fikir Bekleniyor",
            "next": "Planlama",
            "ratio": 0.0,
        }

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self.redirector: Optional[ModernTextRedirector] = None

        self._build_layout()
        self._setup_stdout_redirect()
        self._bind_global_events()

        try:
            event_bus.subscribe(EVENT_TIMELINE_STAGE, self._on_timeline_event)
            event_bus.subscribe(EVENT_SCAN_PROGRESS, self._on_scan_progress_event)
        except Exception:
            pass

        self._load_initial_state()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _load_ui_prefs(self):
        try:
            if os.path.isfile(UI_PREFS_PATH):
                with open(UI_PREFS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                self.sidebar_width = max(190, min(420, int(data.get("sidebar_width", DEFAULT_SIDEBAR_WIDTH))))
                self.inspector_width = max(290, min(620, int(data.get("inspector_width", DEFAULT_INSPECTOR_WIDTH))))
                self.composer_height = max(52, min(220, int(data.get("composer_height", DEFAULT_COMPOSER_HEIGHT))))
        except Exception:
            pass

    def _save_ui_prefs(self):
        try:
            payload = {
                "sidebar_width": int(self.sidebar_width),
                "inspector_width": int(self.inspector_width),
                "composer_height": int(self.composer_height),
            }
            with open(UI_PREFS_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _get_scale_factor(self) -> float:
        try:
            return max(0.5, float(self._get_widget_scaling()))
        except Exception:
            return 1.0

    def _set_sidebar_width(self, new_width: float):
        clamped = max(190, min(420, int(round(new_width))))
        if clamped == self.sidebar_width:
            return
        self.sidebar_width = clamped
        if hasattr(self, "sidebar_frame"):
            self.sidebar_frame.configure(width=clamped)

    def _set_inspector_width(self, new_width: float):
        clamped = max(290, min(620, int(round(new_width))))
        if clamped == self.inspector_width:
            return
        self.inspector_width = clamped
        if hasattr(self, "inspector_frame"):
            self.inspector_frame.configure(width=clamped)

    def _set_composer_height(self, new_height: float):
        clamped = max(52, min(220, int(round(new_height))))
        if clamped == self.composer_height:
            return
        self.composer_height = clamped
        if hasattr(self, "gorev_girisi"):
            self.gorev_girisi.configure(height=clamped)

    def _refresh_agent_card_wraplengths(self):
        target_wrap = max(180, int(self.inspector_width) - 70)
        with self._cards_lock:
            entries = list(self.agent_cards_data.values())
        for entry in entries:
            try:
                lbl = entry.get("lbl_task")
                if lbl is not None:
                    lbl.configure(wraplength=target_wrap)
            except Exception:
                pass

    def _bind_sash_drag(self, sash, orientation: str, get_initial, apply_value, on_reset, sign: int = 1, on_finish=None):
        drag_state = {"active": False, "start_coord": 0, "start_val": 0}

        def _on_enter(_e):
            if not drag_state["active"]:
                sash.configure(bg=ACCENT_BLUE)

        def _on_leave(_e):
            if not drag_state["active"]:
                sash.configure(bg=SASH_IDLE_BG)

        def _on_press(e):
            drag_state["active"] = True
            drag_state["start_coord"] = e.x_root if orientation == "h" else e.y_root
            drag_state["start_val"] = get_initial()
            sash.configure(bg=ACCENT_CYAN)

        def _on_motion(e):
            if not drag_state["active"]:
                return
            scale = self._get_scale_factor()
            coord = e.x_root if orientation == "h" else e.y_root
            delta = sign * (coord - drag_state["start_coord"]) / scale
            apply_value(drag_state["start_val"] + delta)

        def _on_release(_e):
            drag_state["active"] = False
            sash.configure(bg=SASH_IDLE_BG)
            if on_finish:
                on_finish()
            self._save_ui_prefs()

        def _on_double(_e):
            on_reset()
            if on_finish:
                on_finish()
            self._save_ui_prefs()

        sash.bind("<Enter>", _on_enter)
        sash.bind("<Leave>", _on_leave)
        sash.bind("<Button-1>", _on_press)
        sash.bind("<B1-Motion>", _on_motion)
        sash.bind("<ButtonRelease-1>", _on_release)
        sash.bind("<Double-Button-1>", _on_double)

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(3, weight=0)
        self.grid_columnconfigure(4, weight=0)

        self.sidebar_frame = ctk.CTkFrame(
            self, width=self.sidebar_width, corner_radius=0, fg_color=BG_SIDEBAR,
            border_width=0
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)
        self._build_sidebar()

        self.sidebar_sash = tk.Frame(
            self, width=5, bg=SASH_IDLE_BG, cursor="sb_h_double_arrow", highlightthickness=0, bd=0
        )
        self.sidebar_sash.grid(row=0, column=1, sticky="ns")
        self._bind_sash_drag(
            self.sidebar_sash,
            "h",
            lambda: self.sidebar_width,
            self._set_sidebar_width,
            lambda: self._set_sidebar_width(DEFAULT_SIDEBAR_WIDTH),
            sign=1,
        )

        self.center_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=BG_APP)
        self.center_frame.grid(row=0, column=2, sticky="nsew")
        self.center_frame.grid_rowconfigure(0, weight=0)
        self.center_frame.grid_rowconfigure(1, weight=0)
        self.center_frame.grid_rowconfigure(2, weight=1)
        self.center_frame.grid_rowconfigure(3, weight=0)
        self.center_frame.grid_rowconfigure(4, weight=0)
        self.center_frame.grid_rowconfigure(5, weight=0)
        self.center_frame.grid_columnconfigure(0, weight=1)

        self._build_top_header()
        self._build_chef_companion_banner()
        self._build_messages_feed()
        self._build_attachment_strip()
        self._build_composer()

        self.inspector_sash = tk.Frame(
            self, width=5, bg=SASH_IDLE_BG, cursor="sb_h_double_arrow", highlightthickness=0, bd=0
        )
        self._bind_sash_drag(
            self.inspector_sash,
            "h",
            lambda: self.inspector_width,
            self._set_inspector_width,
            lambda: self._set_inspector_width(DEFAULT_INSPECTOR_WIDTH),
            sign=-1,
            on_finish=self._refresh_agent_card_wraplengths,
        )

        self.inspector_frame = ctk.CTkFrame(
            self, width=self.inspector_width, corner_radius=0, fg_color=BG_SIDEBAR,
            border_width=1, border_color=BORDER_SUBTLE
        )
        self._build_inspector_panel()

    def _build_sidebar(self):
        self.sidebar_frame.grid_rowconfigure(0, weight=0)
        self.sidebar_frame.grid_rowconfigure(1, weight=0)
        self.sidebar_frame.grid_rowconfigure(2, weight=0)
        self.sidebar_frame.grid_rowconfigure(3, weight=1)
        self.sidebar_frame.grid_rowconfigure(4, weight=0)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        top.grid_columnconfigure(0, weight=1)

        brand_row = ctk.CTkFrame(top, fg_color="transparent")
        brand_row.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            brand_row, text="✦", font=(FONT_UI, 15, "bold"), text_color=ACCENT_CYAN
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            brand_row, text="LaSef", font=(FONT_UI, 15, "bold"), text_color=TEXT_PRIMARY
        ).pack(side="left")

        nav_btns = ctk.CTkFrame(top, fg_color="transparent")
        nav_btns.grid(row=0, column=1, sticky="e")

        self.btn_nav_back = ctk.CTkButton(
            nav_btns, text="‹", width=26, height=26, corner_radius=8,
            fg_color="transparent", hover_color=BG_ELEVATED, text_color=TEXT_MUTED,
            font=(FONT_UI, 15), command=self.navigate_back
        )
        self.btn_nav_back.pack(side="left", padx=1)

        self.btn_nav_fwd = ctk.CTkButton(
            nav_btns, text="›", width=26, height=26, corner_radius=8,
            fg_color="transparent", hover_color=BG_ELEVATED, text_color=TEXT_MUTED,
            font=(FONT_UI, 15), command=self.navigate_forward
        )
        self.btn_nav_fwd.pack(side="left", padx=1)

        self.btn_search_toggle = ctk.CTkButton(
            nav_btns, text="🔍", width=28, height=26, corner_radius=8,
            fg_color="transparent", hover_color=BG_ELEVATED, text_color=TEXT_MUTED,
            font=(FONT_UI, 12), command=self._toggle_search_bar
        )
        self.btn_search_toggle.pack(side="left", padx=(3, 0))

        ctk.CTkButton(
            self.sidebar_frame,
            text="＋  Yeni Görev",
            height=38,
            corner_radius=10,
            fg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            text_color="#FFFFFF",
            font=(FONT_UI, 12, "bold"),
            command=self.start_new_conversation_ui,
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 8))

        self.search_container = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.search_entry = ctk.CTkEntry(
            self.search_container,
            placeholder_text="Görevlerde ara...",
            height=32,
            corner_radius=8,
            fg_color=BG_CARD,
            border_color=BORDER_SUBTLE,
            border_width=1,
            text_color=TEXT_PRIMARY,
            font=(FONT_UI, 11),
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        self.sidebar_scroll = ctk.CTkScrollableFrame(
            self.sidebar_frame,
            fg_color="transparent",
            scrollbar_button_color="#1F2937",
            scrollbar_button_hover_color="#334155",
        )
        self.sidebar_scroll.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        self.sidebar_scroll.grid_columnconfigure(0, weight=1)

        bottom = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        bottom.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 12))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            bottom, text="📂 Klasör Ekle", height=30, corner_radius=8,
            fg_color=BG_SURFACE, hover_color=BG_ELEVATED, text_color=TEXT_MUTED,
            font=(FONT_UI, 11), command=self._add_new_project_folder_dialog
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            bottom, text="⚙️ Ayarlar", height=30, corner_radius=8,
            fg_color=BG_SURFACE, hover_color=BG_ELEVATED, text_color=TEXT_MUTED,
            font=(FONT_UI, 11), command=self._open_settings_modal
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def toggle_sidebar(self):
        if self.sidebar_visible:
            self.sidebar_frame.grid_forget()
            self.sidebar_sash.grid_forget()
            self.sidebar_visible = False
        else:
            self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
            self.sidebar_sash.grid(row=0, column=1, sticky="ns")
            self.sidebar_visible = True

    def _toggle_search_bar(self):
        self.search_visible = not self.search_visible
        if self.search_visible:
            self.search_container.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))
            self.search_entry.focus_set()
        else:
            self.search_container.grid_forget()
            self.search_query = ""
            try:
                self.search_entry.delete(0, "end")
            except Exception:
                pass
            self.refresh_sidebar()

    def _on_search_changed(self, _event=None):
        self.search_query = self.search_entry.get().strip().lower()
        self.refresh_sidebar()

    def refresh_sidebar(self):
        self._close_popovers()
        for w in self.sidebar_scroll.winfo_children():
            w.destroy()

        projects = branch_memory.get_projects()
        if not projects:
            ctk.CTkLabel(
                self.sidebar_scroll,
                text="Henüz görev yok.\nYukarıdan yeni görev başlat.",
                text_color=TEXT_DIM,
                font=(FONT_UI, 11),
                justify="center",
            ).pack(pady=30)
            return

        for proj in projects:
            pid = proj["project_id"]
            pname = proj.get("name", "Proje")
            expanded = bool(proj.get("expanded", True))
            convs = branch_memory.get_conversations_for_project(pid, search_query=self.search_query)

            if self.search_query and not convs and self.search_query not in pname.lower():
                continue

            p_row = ctk.CTkFrame(self.sidebar_scroll, fg_color="transparent", height=30)
            p_row.pack(fill="x", pady=(6, 2))
            p_row.grid_columnconfigure(0, weight=1)

            arrow = "▾" if expanded else "▸"
            is_active_proj = (pid == self.active_project_id)
            ctk.CTkButton(
                p_row,
                text=f"{arrow}  📁 {pname[:22]}",
                anchor="w",
                height=28,
                corner_radius=8,
                fg_color=BG_SURFACE if is_active_proj else "transparent",
                hover_color=BG_ELEVATED,
                text_color=TEXT_PRIMARY if is_active_proj else TEXT_MUTED,
                font=(FONT_UI, 11, "bold"),
                command=lambda p=pid: self._on_project_folder_click(p),
            ).grid(row=0, column=0, sticky="ew")

            ctk.CTkButton(
                p_row,
                text="⋯",
                width=26,
                height=26,
                corner_radius=7,
                fg_color="transparent",
                hover_color=BG_ELEVATED,
                text_color=TEXT_DIM,
                font=(FONT_UI, 12),
                command=lambda p=proj, btn_parent=p_row: self._open_project_row_menu(p, btn_parent),
            ).grid(row=0, column=1, padx=(2, 0))

            if expanded or self.search_query:
                for conv in convs:
                    cid = conv["conversation_id"]
                    ctitle = conv.get("title", "Yeni Görev")
                    rel_t = format_relative_time(conv.get("updated_at"))
                    is_curr = (cid == self.active_conversation_id)

                    c_row = ctk.CTkFrame(
                        self.sidebar_scroll,
                        fg_color=BG_CARD if is_curr else "transparent",
                        corner_radius=8,
                        border_width=1 if is_curr else 0,
                        border_color=BORDER_ACCENT if is_curr else BORDER_SUBTLE,
                    )
                    c_row.pack(fill="x", padx=(10, 2), pady=1)
                    c_row.grid_columnconfigure(0, weight=1)

                    label_txt = f"{ctitle[:21]}{'…' if len(ctitle) > 21 else ''}"
                    ctk.CTkButton(
                        c_row,
                        text=f"💬  {label_txt}",
                        anchor="w",
                        height=30,
                        corner_radius=7,
                        fg_color="transparent",
                        hover_color=BG_HOVER if not is_curr else BG_CARD,
                        text_color=TEXT_PRIMARY if is_curr else TEXT_MUTED,
                        font=(FONT_UI, 11, "bold" if is_curr else "normal"),
                        command=lambda c=cid: self.load_conversation_view(c),
                    ).grid(row=0, column=0, sticky="ew")

                    ctk.CTkLabel(
                        c_row, text=rel_t, font=(FONT_UI, 9), text_color=TEXT_DIM
                    ).grid(row=0, column=1, padx=(2, 2))

                    ctk.CTkButton(
                        c_row,
                        text="⋯",
                        width=24,
                        height=24,
                        corner_radius=6,
                        fg_color="transparent",
                        hover_color=BG_HOVER,
                        text_color=TEXT_DIM,
                        font=(FONT_UI, 11),
                        command=lambda c=conv, holder=c_row: self._open_conv_row_menu(c, holder),
                    ).grid(row=0, column=2, padx=(0, 3))

    def _on_project_folder_click(self, project_id: str):
        branch_memory.toggle_project_expanded(project_id)
        self.refresh_sidebar()

    def _add_new_project_folder_dialog(self):
        folder = filedialog.askdirectory(title="Projeye Klasör Bağla")
        if not folder:
            return
        proj = branch_memory.get_or_create_project_for_folder(folder)
        self.active_project_id = proj["project_id"]
        self.secilen_klasor = folder
        self._guncelle_kaynak_gorunumu()
        self.refresh_sidebar()

    def _open_project_row_menu(self, proj: Dict[str, Any], anchor_widget):
        pid = proj["project_id"]
        pname = proj.get("name", "Proje")
        items = [
            ("＋  Bu Projede Yeni Görev", lambda: self._new_conv_in_project(pid)),
            ("✏️  Adını Değiştir", lambda: self._rename_project_ui(pid, pname)),
            ("🗑️  Projeyi Sil", lambda: self._delete_project_ui(pid, pname)),
        ]
        self._show_floating_menu(anchor_widget, items, align_right=True)

    def _open_conv_row_menu(self, conv: Dict[str, Any], anchor_widget):
        cid = conv["conversation_id"]
        ctitle = conv.get("title", "Görev")
        items = [
            ("🌿  Dal Haritası", lambda: (self.load_conversation_view(cid), self._open_branch_tree_modal())),
            ("✏️  Yeniden Adlandır", lambda: self._rename_conversation_ui(cid, ctitle)),
            ("🗑️  Görevi Sil", lambda: self._delete_conversation_by_id(cid)),
        ]
        self._show_floating_menu(anchor_widget, items, align_right=True)

    def _new_conv_in_project(self, project_id: str):
        self.active_project_id = project_id
        self.start_new_conversation_ui()

    def _rename_project_ui(self, project_id: str, current_name: str):
        def _save(new_val: str):
            if new_val.strip():
                branch_memory.rename_project(project_id, new_val.strip())
                self.refresh_sidebar()
        self._open_simple_edit_modal("Proje Adını Değiştir", "Proje adı:", current_name, _save)

    def _delete_project_ui(self, project_id: str, project_name: str):
        def _confirm():
            branch_memory.delete_project(project_id, delete_conversations=True)
            if self.active_project_id == project_id:
                self.active_project_id = None
                self.active_conversation_id = None
                self.active_node_id = None
                self.start_new_conversation_ui()
            self.refresh_sidebar()
        self._open_confirm_modal(
            "Projeyi Sil",
            f"'{project_name}' projesi ve içindeki görevler silinecek. Onaylıyor musunuz?",
            _confirm
        )

    def _rename_conversation_ui(self, conversation_id: str, current_title: str):
        def _save(new_val: str):
            if new_val.strip():
                branch_memory.rename_conversation(conversation_id, new_val.strip())
                self.refresh_sidebar()
                if self.active_conversation_id == conversation_id:
                    self._update_header_title()
        self._open_simple_edit_modal("Görevi Yeniden Adlandır", "Görev başlığı:", current_title, _save)

    def _delete_conversation_by_id(self, conversation_id: str):
        branch_memory.delete_conversation(conversation_id)
        if self.active_conversation_id == conversation_id:
            self.active_conversation_id = None
            self.active_node_id = None
            self.start_new_conversation_ui()
        else:
            self.refresh_sidebar()

    def _build_top_header(self):
        header = ctk.CTkFrame(
            self.center_frame, height=52, corner_radius=0, fg_color=BG_APP,
            border_width=0
        )
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(8, 4))
        header.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            left, text="◧", width=32, height=32, corner_radius=9,
            fg_color=BG_SURFACE, hover_color=BG_ELEVATED, text_color=TEXT_MUTED,
            border_width=1, border_color=BORDER_SUBTLE, font=(FONT_UI, 14),
            command=self.toggle_sidebar
        ).pack(side="left", padx=(0, 10))

        self.btn_header_branch = ctk.CTkButton(
            left,
            text="🌿 Ana Dal · Yeni Görev",
            height=32,
            corner_radius=16,
            fg_color=BG_SURFACE,
            hover_color=BG_ELEVATED,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=BORDER_SUBTLE,
            font=(FONT_UI, 12, "bold"),
            command=self._open_branch_tree_modal,
        )
        self.btn_header_branch.pack(side="left")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e")

        self.btn_status_pill = ctk.CTkButton(
            right,
            text="● Hazır",
            height=30,
            corner_radius=15,
            fg_color=BG_SURFACE,
            hover_color=BG_ELEVATED,
            text_color=ACCENT_GREEN,
            border_width=1,
            border_color=BORDER_SUBTLE,
            font=(FONT_UI, 11, "bold"),
            command=self._open_bridges_status_modal,
        )
        self.btn_status_pill.pack(side="left", padx=(0, 8))

        self.btn_inspector_toggle = ctk.CTkButton(
            right,
            text="📊 Takip Paneli",
            height=30,
            corner_radius=15,
            fg_color=BG_SURFACE,
            hover_color=BG_ELEVATED,
            text_color=TEXT_MUTED,
            border_width=1,
            border_color=BORDER_SUBTLE,
            font=(FONT_UI, 11, "bold"),
            command=self.toggle_inspector,
        )
        self.btn_inspector_toggle.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            right,
            text="📁",
            width=32,
            height=30,
            corner_radius=15,
            fg_color=BG_SURFACE,
            hover_color=BG_ELEVATED,
            text_color=TEXT_MUTED,
            border_width=1,
            border_color=BORDER_SUBTLE,
            font=(FONT_UI, 13),
            command=self._open_active_folder_in_explorer,
        ).pack(side="left")

    def toggle_inspector(self, force_open: Optional[bool] = None):
        target = (not self.inspector_visible) if force_open is None else bool(force_open)
        if target == self.inspector_visible:
            return
        self.inspector_visible = target
        if self.inspector_visible:
            self.inspector_sash.grid(row=0, column=3, sticky="ns")
            self.inspector_frame.grid(row=0, column=4, sticky="nsew")
            self.inspector_frame.grid_propagate(False)
            self.btn_inspector_toggle.configure(
                fg_color="#172554", text_color="#93C5FD", border_color=ACCENT_BLUE
            )
        else:
            self.inspector_sash.grid_forget()
            self.inspector_frame.grid_forget()
            self.btn_inspector_toggle.configure(
                fg_color=BG_SURFACE, text_color=TEXT_MUTED, border_color=BORDER_SUBTLE
            )

    def _open_active_folder_in_explorer(self):
        path = self.secilen_klasor
        if not path and self.active_conversation_id:
            conv = branch_memory.get_conversation(self.active_conversation_id)
            if conv:
                path = conv.get("target_folder", "")
        if not path or not os.path.isdir(path):
            self.klasor_sec()
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _build_chef_companion_banner(self):
        banner = ctk.CTkFrame(
            self.center_frame,
            fg_color=BG_SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        banner.grid(row=1, column=0, sticky="ew", padx=22, pady=(2, 8))
        banner.grid_rowconfigure(0, weight=1)
        banner.grid_columnconfigure(1, weight=1)

        self.chef_animator = ChefAnimatorCanvas(
            banner,
            width=222,
            height=74,
            bg_color=BG_SURFACE,
            on_click=self._on_chef_clicked,
        )
        self.chef_animator.grid(row=0, column=0, padx=(12, 8), pady=5, sticky="w")

        info = ctk.CTkFrame(banner, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=(4, 14), pady=8)
        info.grid_columnconfigure(0, weight=1)

        top_line = ctk.CTkFrame(info, fg_color="transparent")
        top_line.grid(row=0, column=0, sticky="ew")
        top_line.grid_columnconfigure(0, weight=1)

        self.lbl_chef_headline = ctk.CTkLabel(
            top_line,
            text="Baş Şef Hazır — fikrini yaz veya '+' ile dosya bağla",
            anchor="w",
            font=(FONT_UI, 12, "bold"),
            text_color=TEXT_PRIMARY,
        )
        self.lbl_chef_headline.grid(row=0, column=0, sticky="w")

        self.lbl_chef_sub = ctk.CTkLabel(
            top_line,
            text="NVIDIA NIM · Gemini · MCP Köprüleri",
            anchor="e",
            font=(FONT_UI, 10),
            text_color=TEXT_DIM,
        )
        self.lbl_chef_sub.grid(row=0, column=1, sticky="e", padx=(10, 0))

        self.stage_progress = ctk.CTkProgressBar(
            info, height=6, corner_radius=3,
            fg_color="#1E293B", progress_color=ACCENT_BLUE
        )
        self.stage_progress.grid(row=1, column=0, sticky="ew", pady=(8, 3))
        self.stage_progress.set(0.0)

        self.lbl_stage_note = ctk.CTkLabel(
            info,
            text="Beklemede · Tıklarsan Şef selam verir 👋",
            anchor="w",
            font=(FONT_UI, 10),
            text_color=TEXT_MUTED,
        )
        self.lbl_stage_note.grid(row=2, column=0, sticky="w")

        self.fork_pill_frame = ctk.CTkFrame(banner, fg_color="transparent", width=1, height=1)

    def _on_chef_clicked(self):
        if not self.is_running:
            self.lbl_chef_headline.configure(text="Merhaba! Bugün hangi fikri hayata geçiriyoruz?")
            self.lbl_stage_note.configure(text="Şef göreve hazır — mesaj yazabilir veya şablon seçebilirsin")

    def set_chef_animation(self, state: str, hint: str = "", worker_count: Optional[int] = None):
        if not hasattr(self, "chef_animator"):
            return
        active_cnt = worker_count
        if active_cnt is None and self.agent_cards_data:
            active_cnt = max(2, len(self.agent_cards_data))
        self.chef_animator.set_state(state, worker_count=active_cnt)
        if hint:
            self.lbl_stage_note.configure(text=hint)

    def _on_timeline_event(self, event):
        data = getattr(event, "data", None) or {}
        try:
            if self.winfo_exists():
                self.after(0, self.update_timeline_display, data)
        except Exception:
            pass

    def update_timeline_display(self, data: dict):
        curr_title = str(data.get("current_title", "") or "")
        curr_note = str(data.get("current_note", "") or "")
        next_title = str(data.get("next_title", "") or "")
        prev_title = str(data.get("prev_title", "") or "")
        ratio = float(data.get("progress_ratio", 0.0) or 0.0)

        self._timeline_state = {
            "prev": prev_title or "Önceki",
            "curr": curr_title or "Çalışıyor",
            "next": next_title or "Sonraki",
            "ratio": max(0.0, min(1.0, ratio)),
        }

        try:
            self.stage_progress.set(self._timeline_state["ratio"])
            if curr_title:
                self.lbl_chef_headline.configure(text=curr_title)
            if curr_note:
                self.lbl_stage_note.configure(text=curr_note)
            if next_title:
                self.lbl_chef_sub.configure(text=f"Sıradaki: {next_title}")

            low = curr_title.lower()
            if any(k in low for k in ("tamam", "mühür", "sonuç")):
                self.set_chef_animation(ChefState.SUCCESS)
                self.stage_progress.configure(progress_color=ACCENT_GREEN)
            elif any(k in low for k in ("konsey", "denet", "test", "onay", "vision")):
                self.set_chef_animation(ChefState.AUDITING)
                self.stage_progress.configure(progress_color=ACCENT_PURPLE)
            elif any(k in low for k in ("ajan", "paralel", "üretim", "kod", "blender", "unity")):
                self.set_chef_animation(ChefState.ORCHESTRATING)
                self.stage_progress.configure(progress_color=ACCENT_CYAN)
            elif any(k in low for k in ("plan", "analiz", "mimari")):
                self.set_chef_animation(ChefState.THINKING)
                self.stage_progress.configure(progress_color=ACCENT_AMBER)

            self._refresh_timeline_summary_labels()
        except Exception:
            pass

    def _build_messages_feed(self):
        self.messages_scroll = ctk.CTkScrollableFrame(
            self.center_frame,
            fg_color="transparent",
            scrollbar_button_color="#1F2937",
            scrollbar_button_hover_color="#334155",
        )
        self.messages_scroll.grid(row=2, column=0, sticky="nsew", padx=22, pady=2)
        self.messages_scroll.grid_columnconfigure(0, weight=1)

    def _render_empty_welcome(self):
        for w in self.messages_scroll.winfo_children():
            w.destroy()

        hero = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        hero.pack(fill="both", expand=True, pady=(34, 16), padx=24)

        ctk.CTkLabel(
            hero,
            text="Bugün ne inşa edelim?",
            font=(FONT_UI, 24, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(8, 6))

        ctk.CTkLabel(
            hero,
            text=(
                "Görevini yaz; Baş Şef planlasın, NVIDIA NIM alt ajanları paralel üretsin.\n"
                "Görsel, belge veya klasör eklemek için alttaki  ＋  butonunu kullan."
            ),
            font=(FONT_UI, 12),
            text_color=TEXT_MUTED,
            justify="center",
        ).pack(pady=(0, 22))

        grid_box = ctk.CTkFrame(hero, fg_color="transparent")
        grid_box.pack(fill="x", padx=20)
        grid_box.grid_columnconfigure(0, weight=1)
        grid_columnconfigure_set = (0, 1)
        for col in grid_columnconfigure_set:
            grid_box.grid_columnconfigure(col, weight=1)

        for idx, (title, desc, prompt_txt) in enumerate(EMPTY_STARTERS):
            r = idx // 2
            c = idx % 2
            card = ctk.CTkFrame(
                grid_box,
                fg_color=BG_CARD,
                corner_radius=12,
                border_width=1,
                border_color=BORDER_SUBTLE,
            )
            card.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkButton(
                card,
                text=f"{title}\n{desc}",
                anchor="w",
                height=62,
                corner_radius=11,
                fg_color="transparent",
                hover_color=BG_HOVER,
                text_color=TEXT_PRIMARY,
                font=(FONT_UI, 11),
                command=lambda p=prompt_txt: self._sablon_doldur(p),
            ).pack(fill="both", expand=True, padx=4, pady=4)

    def _render_conversation_messages(self, conversation_id: str, active_node_id: Optional[str]):
        for w in self.messages_scroll.winfo_children():
            w.destroy()

        nodes = branch_memory.get_all_nodes_sorted(conversation_id)
        if not nodes:
            self._render_empty_welcome()
            return

        for node in nodes:
            self._create_message_turn_card(conversation_id, node, is_active=(node.get("node_id") == active_node_id))

    def _create_message_turn_card(self, conversation_id: str, node: Dict[str, Any], is_active: bool = False):
        nid = node["node_id"]
        turn_no = node.get("turn_number", 1)
        b_name = node.get("branch_name", "Ana Dal")
        status = node.get("status", "success")
        prompt_text = node.get("prompt", "")
        chef_summary = node.get("chef_summary", "")
        source_files = node.get("source_files", []) or []
        files_produced = node.get("files_produced", []) or []
        created_rel = format_relative_time(node.get("created_at"))

        border_col = ACCENT_BLUE if is_active else BORDER_SUBTLE
        card = ctk.CTkFrame(
            self.messages_scroll,
            fg_color=BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=border_col,
        )
        card.pack(fill="x", pady=7, padx=4)
        card.grid_columnconfigure(0, weight=1)

        meta = ctk.CTkFrame(card, fg_color="transparent")
        meta.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        meta.grid_columnconfigure(1, weight=1)

        status_icon = "✅" if status == "success" else ("⏳" if status == "running" else "⚠️")
        badge_txt = f"{status_icon}  Tur #{turn_no}  ·  {b_name}  ·  {created_rel}"
        ctk.CTkLabel(
            meta, text=badge_txt, font=(FONT_UI, 10, "bold"),
            text_color=ACCENT_CYAN if is_active else TEXT_DIM
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            meta,
            text="⋯",
            width=28,
            height=24,
            corner_radius=7,
            fg_color="transparent",
            hover_color=BG_HOVER,
            text_color=TEXT_MUTED,
            font=(FONT_UI, 13),
            command=lambda n=node, h=meta: self._open_node_action_menu(conversation_id, n, h),
        ).grid(row=0, column=2, sticky="e")

        prompt_box = ctk.CTkFrame(card, fg_color=BG_SURFACE, corner_radius=10)
        prompt_box.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 8))
        ctk.CTkLabel(
            prompt_box,
            text=prompt_text,
            anchor="w",
            justify="left",
            wraplength=680,
            font=(FONT_UI, 12),
            text_color=TEXT_PRIMARY,
        ).pack(fill="x", padx=12, pady=(9, 6 if source_files else 9))

        if source_files:
            src_row = ctk.CTkFrame(prompt_box, fg_color="transparent")
            src_row.pack(fill="x", padx=12, pady=(0, 8))
            for sp in source_files[:5]:
                bn = os.path.basename(sp) or sp
                ctk.CTkLabel(
                    src_row,
                    text=f"📎 {bn}",
                    corner_radius=8,
                    fg_color=BG_ELEVATED,
                    text_color="#93C5FD",
                    font=(FONT_UI, 9, "bold"),
                    padx=7,
                    pady=2,
                ).pack(side="left", padx=(0, 4))
            if len(source_files) > 5:
                ctk.CTkLabel(
                    src_row,
                    text=f"+{len(source_files) - 5} ek",
                    font=(FONT_UI, 9),
                    text_color=TEXT_DIM,
                ).pack(side="left", padx=4)

        if chef_summary:
            preview = chef_summary.strip()
            max_len = 520
            truncated = len(preview) > max_len
            shown_txt = (preview[:max_len] + "…") if truncated else preview

            sum_lbl = ctk.CTkLabel(
                card,
                text=shown_txt,
                anchor="w",
                justify="left",
                wraplength=680,
                font=(FONT_UI, 11),
                text_color=TEXT_MUTED,
            )
            sum_lbl.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 6))

            if truncated:
                def _toggle_full(lbl=sum_lbl, full=preview, short=shown_txt, btn_ref=None):
                    curr = lbl.cget("text")
                    lbl.configure(text=full if curr == short else short)

                ctk.CTkButton(
                    card,
                    text="Tam Raporu Gör / Daralt",
                    width=130,
                    height=22,
                    corner_radius=6,
                    fg_color="transparent",
                    hover_color=BG_HOVER,
                    text_color=ACCENT_BLUE,
                    font=(FONT_UI, 10, "bold"),
                    command=_toggle_full,
                ).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 6))

        if files_produced:
            files_row = ctk.CTkFrame(card, fg_color="transparent")
            files_row.grid(row=4, column=0, sticky="ew", padx=14, pady=(2, 10))
            for f_info in files_produced[:6]:
                fname = os.path.basename(f_info.get("path") or f_info.get("name") or "dosya")
                ctk.CTkButton(
                    files_row,
                    text=f"📄 {fname}",
                    height=24,
                    corner_radius=12,
                    fg_color=BG_ELEVATED,
                    hover_color=BG_HOVER,
                    text_color="#CBD5E1",
                    font=(FONT_UI, 10),
                    command=lambda fi=f_info, n=node: self._open_single_file_preview(fi, n),
                ).pack(side="left", padx=(0, 5), pady=2)
            if len(files_produced) > 6:
                ctk.CTkButton(
                    files_row,
                    text=f"+{len(files_produced) - 6} daha",
                    height=24,
                    corner_radius=12,
                    fg_color="transparent",
                    hover_color=BG_HOVER,
                    text_color=ACCENT_CYAN,
                    font=(FONT_UI, 10, "bold"),
                    command=self._open_files_inspector_modal,
                ).pack(side="left", padx=2)

    def _open_node_action_menu(self, conversation_id: str, node: Dict[str, Any], anchor_widget):
        nid = node["node_id"]
        items = [
            ("👁️  Bu Turun Log & Ajanlarını Gör", lambda: self._select_node_view(conversation_id, nid)),
            ("↩️  Buradan Dallan (Fork)", lambda: self._set_branch_fork_point(conversation_id, nid)),
            ("✏️  İstemi Düzenle", lambda: self._edit_node_modal(conversation_id, node)),
            ("🗑️  Bu Turu Sil", lambda: self._delete_node_ui(conversation_id, nid)),
        ]
        self._show_floating_menu(anchor_widget, items, align_right=True)

    def _select_node_view(self, conversation_id: str, node_id: str):
        branch_memory.set_active_selection(conversation_id, node_id)
        self.load_conversation_view(conversation_id, target_node_id=node_id)

    def _build_attachment_strip(self):
        self.attachment_strip = ctk.CTkFrame(self.center_frame, fg_color="transparent")

    def _guncelle_kaynak_gorunumu(self):
        for w in self.attachment_strip.winfo_children():
            w.destroy()

        chips: List[tuple] = []
        if self.secilen_klasor:
            chips.append((
                f"📁 Çıktı: {os.path.basename(self.secilen_klasor) or self.secilen_klasor}",
                "#064E3B", "#34D399", self._clear_target_folder
            ))
        for kf in self.secilen_kaynak_klasorler:
            chips.append((
                f"📂 {os.path.basename(kf) or kf}",
                "#1E293B", "#93C5FD", lambda p=kf: self._remove_source_folder(p)
            ))
        for df in self.secilen_kaynak_tekil_dosyalar:
            ext = os.path.splitext(df)[1].lower()
            icon = "🖼️" if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif") else "📄"
            chips.append((
                f"{icon} {os.path.basename(df)}",
                "#1E293B", "#CBD5E1", lambda p=df: self._remove_source_file(p)
            ))

        if not chips:
            self.attachment_strip.grid_forget()
            return

        self.attachment_strip.grid(row=3, column=0, sticky="ew", padx=24, pady=(2, 4))
        for label, bg_c, fg_c, remove_fn in chips:
            pill = ctk.CTkFrame(
                self.attachment_strip, fg_color=bg_c, corner_radius=12,
                border_width=1, border_color=BORDER_SUBTLE
            )
            pill.pack(side="left", padx=(0, 6), pady=2)
            ctk.CTkLabel(
                pill, text=label, font=(FONT_UI, 10, "bold"), text_color=fg_c
            ).pack(side="left", padx=(9, 4), pady=3)
            ctk.CTkButton(
                pill, text="✕", width=18, height=18, corner_radius=9,
                fg_color="transparent", hover_color="#334155", text_color=TEXT_MUTED,
                font=(FONT_UI, 9, "bold"), command=remove_fn
            ).pack(side="left", padx=(0, 4), pady=2)

    def _clear_target_folder(self):
        self.secilen_klasor = ""
        self._guncelle_kaynak_gorunumu()

    def _remove_source_folder(self, folder_path: str):
        self.secilen_kaynak_klasorler = [p for p in self.secilen_kaynak_klasorler if p != folder_path]
        self._rebuild_source_files_list()
        self._guncelle_kaynak_gorunumu()

    def _remove_source_file(self, file_path: str):
        self.secilen_kaynak_tekil_dosyalar = [p for p in self.secilen_kaynak_tekil_dosyalar if p != file_path]
        self._rebuild_source_files_list()
        self._guncelle_kaynak_gorunumu()

    def _rebuild_source_files_list(self):
        collected: List[str] = []
        for kf in self.secilen_kaynak_klasorler:
            if kf and os.path.isdir(kf):
                collected.append(kf)
        for sf in self.secilen_kaynak_tekil_dosyalar:
            if sf and os.path.isfile(sf):
                collected.append(sf)

        seen = set()
        deduped = []
        for p in collected:
            norm = os.path.normpath(p)
            if norm not in seen:
                seen.add(norm)
                deduped.append(p)
        self.secilen_kaynak_dosyalar = deduped

    def _build_composer(self):
        self.composer_sash = tk.Frame(
            self.center_frame, height=5, bg=SASH_IDLE_BG,
            cursor="sb_v_double_arrow", highlightthickness=0, bd=0,
        )
        self.composer_sash.grid(row=4, column=0, sticky="ew", padx=36, pady=(2, 0))
        self._bind_sash_drag(
            self.composer_sash,
            "v",
            lambda: self.composer_height,
            self._set_composer_height,
            lambda: self._set_composer_height(DEFAULT_COMPOSER_HEIGHT),
            sign=-1,
        )

        wrapper = ctk.CTkFrame(
            self.center_frame,
            fg_color=BG_SURFACE,
            corner_radius=18,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        wrapper.grid(row=5, column=0, sticky="ew", padx=22, pady=(2, 16))
        wrapper.grid_columnconfigure(1, weight=1)
        self.composer_wrapper = wrapper

        self.btn_plus_menu = ctk.CTkButton(
            wrapper,
            text="＋",
            width=38,
            height=38,
            corner_radius=19,
            fg_color=BG_ELEVATED,
            hover_color=BG_HOVER,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=BORDER_SUBTLE,
            font=(FONT_UI, 17, "bold"),
            command=self._toggle_plus_menu,
        )
        self.btn_plus_menu.grid(row=0, column=0, padx=(10, 6), pady=10, sticky="s")

        self.gorev_girisi = ctk.CTkTextbox(
            wrapper,
            height=self.composer_height,
            corner_radius=10,
            fg_color="transparent",
            border_width=0,
            text_color=TEXT_PRIMARY,
            font=(FONT_UI, 13),
            wrap="word",
        )
        self.gorev_girisi.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self._apply_placeholder()

        self.gorev_girisi.bind("<FocusIn>", self._on_input_focus_in)
        self.gorev_girisi.bind("<FocusOut>", self._on_input_focus_out)
        self.gorev_girisi.bind("<KeyRelease>", self._on_input_key_release)
        self.gorev_girisi.bind("<Return>", self._on_input_return)

        self.btn_baslat = ctk.CTkButton(
            wrapper,
            text="➤ Başlat",
            width=102,
            height=38,
            corner_radius=19,
            fg_color=ACCENT_BLUE,
            hover_color=ACCENT_BLUE_HOVER,
            text_color="#FFFFFF",
            font=(FONT_UI, 12, "bold"),
            command=self.baslat_thread,
        )
        self.btn_baslat.grid(row=0, column=2, padx=(6, 10), pady=10, sticky="s")

    def _apply_placeholder(self):
        self.gorev_girisi.delete("1.0", "end")
        self.gorev_girisi.insert("1.0", self._placeholder_text)
        self.gorev_girisi.configure(text_color=TEXT_DIM)
        self._placeholder_active = True

    def _placeholder_temizle(self, _e=None):
        if self._placeholder_active:
            self.gorev_girisi.delete("1.0", "end")
            self.gorev_girisi.configure(text_color=TEXT_PRIMARY)
            self._placeholder_active = False

    def _on_input_focus_in(self, _event=None):
        self._placeholder_temizle()
        if not self.is_running:
            self.chef_animator.trigger_wave(greeting_mode=True, duration=1.8)

    def _on_input_focus_out(self, _event=None):
        txt = self.gorev_girisi.get("1.0", "end-1c").strip()
        if not txt:
            self._apply_placeholder()

    def _on_input_key_release(self, event=None):
        if self._placeholder_active:
            return
        txt = self.gorev_girisi.get("1.0", "end-1c")
        if hasattr(self, "chef_animator") and not self.is_running:
            self.chef_animator.trigger_typing_reaction(txt)

    def _on_input_return(self, event=None):
        if event and (event.state & 0x0001):
            return None
        if not self.is_running:
            self.baslat_thread()
        return "break"

    def _sablon_doldur(self, prompt_text: str):
        self._close_popovers()
        self._placeholder_temizle()
        self.gorev_girisi.delete("1.0", "end")
        self.gorev_girisi.insert("1.0", prompt_text)
        self.gorev_girisi.configure(text_color=TEXT_PRIMARY)
        self._placeholder_active = False
        self.gorev_girisi.focus_set()
        if hasattr(self, "chef_animator") and not self.is_running:
            self.chef_animator.trigger_wave(greeting_mode=True, duration=2.2)

    def _toggle_plus_menu(self):
        if self._plus_menu_frame is not None:
            self._close_popovers()
            return

        has_attachments = bool(
            self.secilen_klasor
            or self.secilen_kaynak_klasorler
            or self.secilen_kaynak_tekil_dosyalar
        )

        items = [
            ("🖼️  Görsel / Belge Ekle", lambda: (self._close_popovers(), self.kaynak_dosya_sec())),
            ("📂  Kaynak Klasör Bağla", lambda: (self._close_popovers(), self.kaynak_klasor_sec())),
            ("📁  Hedef Çıktı Klasörü Seç", lambda: (self._close_popovers(), self.klasor_sec())),
            ("✨  Hızlı Şablon Seç  ▸", self._open_template_picker_popover),
        ]
        if has_attachments:
            items.append(("🧹  Tüm Ekleri Temizle", lambda: (self._close_popovers(), self.kaynak_temizle())))

        self._plus_menu_frame = self._create_popover_at_widget(
            self.btn_plus_menu, items, above=True, align_right=False, width=230
        )

    def _open_template_picker_popover(self):
        if self._template_subframe is not None:
            try:
                self._template_subframe.destroy()
            except Exception:
                pass
            self._template_subframe = None
            return

        anchor = self._plus_menu_frame or self.btn_plus_menu
        t_items = [
            (label, lambda p=prompt_txt: self._sablon_doldur(p))
            for _, (label, prompt_txt) in SABLONLAR.items()
        ]
        self._template_subframe = self._create_popover_at_widget(
            anchor, t_items, above=True, align_right=False, width=220,
            keep_existing=True, side_right=(self._plus_menu_frame is not None)
        )

    def _show_floating_menu(self, anchor_widget, items: List[tuple], align_right: bool = True):
        self._close_popovers()
        self._row_menu_frame = self._create_popover_at_widget(
            anchor_widget, items, above=False, align_right=align_right, width=220
        )

    def _create_popover_at_widget(
        self,
        anchor_widget,
        items: List[tuple],
        above: bool = True,
        align_right: bool = False,
        width: int = 225,
        keep_existing: bool = False,
        side_right: bool = False,
    ) -> ctk.CTkFrame:
        if not keep_existing:
            self._close_popovers()

        menu = ctk.CTkFrame(
            self,
            width=width,
            fg_color=BG_ELEVATED,
            corner_radius=12,
            border_width=1,
            border_color="#334155",
        )
        for text, cmd in items:
            btn = ctk.CTkButton(
                menu,
                text=text,
                anchor="w",
                height=32,
                corner_radius=8,
                fg_color="transparent",
                hover_color=BG_HOVER,
                text_color=TEXT_PRIMARY,
                font=(FONT_UI, 11),
                command=cmd,
            )
            btn.pack(fill="x", padx=6, pady=3)

        self.update_idletasks()
        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        ax = anchor_widget.winfo_rootx() - root_x
        ay = anchor_widget.winfo_rooty() - root_y
        aw = max(32, anchor_widget.winfo_width())
        ah = max(28, anchor_widget.winfo_height())

        est_h = len(items) * 38 + 10
        if side_right:
            x = min(ax + aw + 6, max(8, self.winfo_width() - width - 10))
            y = max(8, min(ay + ah - est_h, self.winfo_height() - est_h - 10))
        else:
            x = (ax + aw - width) if align_right else ax
            x = max(8, min(x, max(8, self.winfo_width() - width - 10)))
            if above:
                y = max(8, ay - est_h - 6)
            else:
                y = min(ay + ah + 4, max(8, self.winfo_height() - est_h - 10))

        menu.place(x=x, y=y)
        menu.lift()
        return menu

    def _close_popovers(self):
        for attr in ("_template_subframe", "_plus_menu_frame", "_row_menu_frame"):
            frame = getattr(self, attr, None)
            if frame is not None:
                try:
                    frame.destroy()
                except Exception:
                    pass
                setattr(self, attr, None)

    def _bind_global_events(self):
        self.bind("<Escape>", lambda _e: self._close_popovers())
        self.bind("<Button-1>", self._on_global_click, add="+")

    def _on_global_click(self, event):
        w = event.widget
        for ref in (self._plus_menu_frame, self._template_subframe, self._row_menu_frame, self.btn_plus_menu):
            if ref is None:
                continue
            try:
                cur = w
                while cur is not None:
                    if cur is ref:
                        return
                    cur = getattr(cur, "master", None)
            except Exception:
                pass
        self._close_popovers()

    def _build_inspector_panel(self):
        self.inspector_frame.grid_rowconfigure(0, weight=0)
        self.inspector_frame.grid_rowconfigure(1, weight=0)
        self.inspector_frame.grid_rowconfigure(2, weight=1)
        self.inspector_frame.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self.inspector_frame, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        top.grid_columnconfigure(0, weight=1)

        self.inspector_seg = ctk.CTkSegmentedButton(
            top,
            values=["🤖 Ajanlar", "💻 Konsol"],
            height=30,
            corner_radius=9,
            fg_color=BG_SURFACE,
            selected_color=ACCENT_BLUE,
            selected_hover_color=ACCENT_BLUE_HOVER,
            unselected_color=BG_SURFACE,
            unselected_hover_color=BG_ELEVATED,
            font=(FONT_UI, 11, "bold"),
            command=self._on_inspector_tab_change,
        )
        self.inspector_seg.set("🤖 Ajanlar")
        self.inspector_seg.grid(row=0, column=0, sticky="w")

        tools = ctk.CTkFrame(top, fg_color="transparent")
        tools.grid(row=0, column=1, sticky="e")
        for lbl, cmd in (
            ("📦", self._open_files_inspector_modal),
            ("💾", self._konsolu_txt_kaydet),
            ("📋", self._konsolu_kopyala),
            ("✕", lambda: self.toggle_inspector(force_open=False)),
        ):
            ctk.CTkButton(
                tools, text=lbl, width=26, height=26, corner_radius=7,
                fg_color="transparent", hover_color=BG_ELEVATED,
                text_color=TEXT_MUTED, font=(FONT_UI, 11), command=cmd
            ).pack(side="left", padx=1)

        self.inspector_stats_bar = ctk.CTkFrame(
            self.inspector_frame, fg_color=BG_SURFACE, corner_radius=10,
            border_width=1, border_color=BORDER_SUBTLE
        )
        self.inspector_stats_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.lbl_inspector_stats = ctk.CTkLabel(
            self.inspector_stats_bar,
            text="🤖 0 Ajan  ·  ✅ 0 Biten  ·  ⚡ Hazır",
            anchor="w",
            font=(FONT_UI, 10, "bold"),
            text_color=TEXT_MUTED,
        )
        self.lbl_inspector_stats.pack(fill="x", padx=10, pady=6)

        self.agents_tab_frame = ctk.CTkScrollableFrame(
            self.inspector_frame, fg_color="transparent",
            scrollbar_button_color="#1F2937", scrollbar_button_hover_color="#334155"
        )
        self.agents_tab_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.agents_tab_frame.grid_columnconfigure(0, weight=1)

        self.console_tab_frame = ctk.CTkFrame(self.inspector_frame, fg_color="transparent")
        self.console_tab_frame.grid_rowconfigure(0, weight=1)
        self.console_tab_frame.grid_columnconfigure(0, weight=1)

        self.terminal_kutusu = ctk.CTkTextbox(
            self.console_tab_frame,
            fg_color="#090D14",
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=10,
            font=(FONT_MONO, 10),
            text_color="#CBD5E1",
            wrap="word",
            state="disabled",
        )
        self.terminal_kutusu.grid(row=0, column=0, sticky="nsew", padx=4, pady=(0, 8))

        self._show_inspector_tab("agents")

    def _on_inspector_tab_change(self, val: str):
        self._show_inspector_tab("console" if "Konsol" in val else "agents")

    def _show_inspector_tab(self, tab_name: str):
        self.active_inspector_tab = tab_name
        if tab_name == "console":
            self.agents_tab_frame.grid_forget()
            self.console_tab_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 10))
            self.inspector_seg.set("💻 Konsol")
        else:
            self.console_tab_frame.grid_forget()
            self.agents_tab_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 10))
            self.inspector_seg.set("🤖 Ajanlar")

    def _refresh_timeline_summary_labels(self):
        self._update_stat_pills()

    def _update_stat_pills(self):
        total = len(self.agent_cards_data)
        done = sum(1 for d in self.agent_cards_data.values() if d.get("status") in ("Tamamlandı", "APPROVED", "Onaylandı"))
        active = sum(
            1 for d in self.agent_cards_data.values()
            if d.get("status") in ("Çalışıyor", "RUNNING", "Revizyon", "Senkron", "Onay Bekliyor")
        )
        stage = self._timeline_state.get("curr", "Hazır")
        try:
            self.lbl_inspector_stats.configure(
                text=f"🤖 {total} Ajan  ·  ⚙️ {active} Aktif  ·  ✅ {done} Biten  ·  {stage}"
            )
            badge = f"📊 Takip ({total})" if total > 0 else "📊 Takip Paneli"
            self.btn_inspector_toggle.configure(text=badge)
            if hasattr(self, "chef_animator") and active > 0:
                self.chef_animator.set_worker_count(active)
        except Exception:
            pass

    def _clear_agent_cards_display(self):
        for w in self.agents_tab_frame.winfo_children():
            w.destroy()
        with self._cards_lock:
            self.agent_cards_data.clear()
        self._update_stat_pills()

    def create_or_update_agent_card(
        self,
        agent_id: str,
        name: str = "",
        task: str = "",
        model: str = "",
        status: str = "Sırada",
        stage_note: str = "",
    ):
        status_norm = {
            "QUEUE": "Sırada",
            "RUNNING": "Çalışıyor",
            "WAITING": "Onay Bekliyor",
            "WAITING_SYNC": "Onay Bekliyor",
            "REVISION": "Revizyon",
            "APPROVED": "Tamamlandı",
            "ERROR": "Hata",
        }.get(status, status)

        badge_palette = {
            "Sırada": ("#1E293B", "#94A3B8"),
            "Çalışıyor": ("#083344", "#22D3EE"),
            "Senkron": ("#451A03", "#FBBF24"),
            "Onay Bekliyor": ("#451A03", "#FBBF24"),
            "Revizyon": ("#4C0519", "#FB7185"),
            "Tamamlandı": ("#064E3B", "#34D399"),
            "Hata": ("#450A0A", "#F87171"),
        }.get(status_norm, ("#1E293B", "#94A3B8"))

        entry = self.agent_cards_data.get(agent_id)
        if entry is None:
            card = ctk.CTkFrame(
                self.agents_tab_frame,
                fg_color=BG_CARD,
                corner_radius=10,
                border_width=1,
                border_color=BORDER_SUBTLE,
            )
            card.pack(fill="x", padx=4, pady=4)
            card.grid_columnconfigure(0, weight=1)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
            top.grid_columnconfigure(0, weight=1)

            lbl_name = ctk.CTkLabel(
                top, text=name or agent_id, anchor="w",
                font=(FONT_UI, 11, "bold"), text_color=TEXT_PRIMARY
            )
            lbl_name.grid(row=0, column=0, sticky="w")

            lbl_badge = ctk.CTkLabel(
                top, text=status_norm, corner_radius=8,
                fg_color=badge_palette[0], text_color=badge_palette[1],
                font=(FONT_UI, 9, "bold"), padx=8, pady=2
            )
            lbl_badge.grid(row=0, column=1, sticky="e")

            wrap_w = max(180, int(self.inspector_width) - 70)
            lbl_task = ctk.CTkLabel(
                card, text=task or "-", anchor="w", justify="left", wraplength=wrap_w,
                font=(FONT_UI, 10), text_color=TEXT_MUTED
            )
            lbl_task.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 3))

            lbl_model = ctk.CTkLabel(
                card, text=f"🧠 {model or 'Bekliyor'}", anchor="w",
                font=(FONT_UI, 9), text_color=TEXT_DIM
            )
            lbl_model.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))

            with self._cards_lock:
                self.agent_cards_data[agent_id] = {
                    "card": card,
                    "lbl_name": lbl_name,
                    "lbl_badge": lbl_badge,
                    "lbl_task": lbl_task,
                    "lbl_model": lbl_model,
                    "name": name or agent_id,
                    "task": task,
                    "model": model,
                    "status": status_norm,
                }
        else:
            with self._cards_lock:
                if name:
                    entry["name"] = name
                    entry["lbl_name"].configure(text=name)
                if task:
                    entry["task"] = task
                    entry["lbl_task"].configure(text=task)
                if model:
                    entry["model"] = model
                    entry["lbl_model"].configure(text=f"🧠 {model}")
                entry["status"] = status_norm
            entry["lbl_badge"].configure(
                text=status_norm, fg_color=badge_palette[0], text_color=badge_palette[1]
            )
            entry["card"].configure(
                border_color=ACCENT_CYAN if status_norm == "Çalışıyor" else BORDER_SUBTLE
            )

        self._update_stat_pills()

    def _restore_node_telemetry_to_right_panel(self, node: Dict[str, Any]):
        self._clear_agent_cards_display()
        for idx, t in enumerate(node.get("agent_tasks") or [], 1):
            aid = t.get("agent_id") or f"restored_{idx}"
            self.create_or_update_agent_card(
                aid,
                name=t.get("name", aid),
                task=t.get("task", ""),
                model=t.get("model", ""),
                status=t.get("status", "Tamamlandı"),
            )

        log_txt = node.get("terminal_log", "")
        if log_txt:
            try:
                self.terminal_kutusu.configure(state="normal")
                self.terminal_kutusu.delete("1.0", "end")
                self.terminal_kutusu.insert("1.0", log_txt)
                self.terminal_kutusu.see("end")
                self.terminal_kutusu.configure(state="disabled")
            except Exception:
                pass

    def _load_initial_state(self):
        act_proj, act_conv, act_node = branch_memory.get_active_state()
        self.active_project_id = act_proj
        self.active_conversation_id = act_conv
        self.active_node_id = act_node
        self.refresh_sidebar()

        if act_conv and branch_memory.get_conversation(act_conv):
            self.load_conversation_view(act_conv, target_node_id=act_node, record_nav=True)
        else:
            self._render_empty_welcome()
            self._update_header_title()

    def start_new_conversation_ui(self):
        self._close_popovers()
        self.secilen_klasor = ""
        self.secilen_kaynak_klasorler = []
        self.secilen_kaynak_tekil_dosyalar = []
        self.secilen_kaynak_dosyalar = []
        self.active_fork_parent_id = None
        self._guncelle_kaynak_gorunumu()

        conv = branch_memory.create_new_conversation(
            project_id=self.active_project_id,
            title="Yeni Görev",
            target_folder="",
        )
        self.active_conversation_id = conv["conversation_id"]
        self.active_node_id = None
        self._clear_agent_cards_display()
        self._konsolu_temizle()
        self._render_fork_banner_pill()
        self._render_empty_welcome()
        self._update_header_title()
        self.refresh_sidebar()
        self.set_chef_animation(ChefState.IDLE, hint="Yeni görev hazır — fikrini bekliyorum")
        if hasattr(self, "chef_animator"):
            self.chef_animator.trigger_wave(greeting_mode=True, duration=1.8)

    def load_conversation_view(self, conversation_id: str, target_node_id: Optional[str] = None, record_nav: bool = True):
        conv = branch_memory.get_conversation(conversation_id)
        if not conv:
            self.start_new_conversation_ui()
            return

        prev_conv = self.active_conversation_id
        self.active_conversation_id = conversation_id
        self.active_project_id = conv.get("project_id") or self.active_project_id
        if prev_conv != conversation_id:
            self.secilen_kaynak_klasorler = []
            self.secilen_kaynak_tekil_dosyalar = []
            self.secilen_kaynak_dosyalar = []
            self.active_fork_parent_id = None
        nodes = branch_memory.get_all_nodes_sorted(conversation_id)

        if target_node_id and branch_memory.get_node(conversation_id, target_node_id):
            self.active_node_id = target_node_id
        elif conv.get("active_node_id") and branch_memory.get_node(conversation_id, conv["active_node_id"]):
            self.active_node_id = conv["active_node_id"]
        elif nodes:
            self.active_node_id = nodes[-1]["node_id"]
        else:
            self.active_node_id = None

        branch_memory.set_active_selection(conversation_id, self.active_node_id)

        if record_nav:
            if not self.nav_history or self.nav_history[self.nav_index] != conversation_id:
                self.nav_history = self.nav_history[: self.nav_index + 1]
                self.nav_history.append(conversation_id)
                self.nav_index = len(self.nav_history) - 1

        self.secilen_klasor = conv.get("target_folder") or ""
        self._guncelle_kaynak_gorunumu()
        self._render_fork_banner_pill()
        self._render_conversation_messages(conversation_id, self.active_node_id)
        self._update_header_title()
        self.refresh_sidebar()

        if self.active_node_id:
            node = branch_memory.get_node(conversation_id, self.active_node_id)
            if node:
                self._restore_node_telemetry_to_right_panel(node)
                st = node.get("status", "success")
                self.set_chef_animation(
                    ChefState.SUCCESS if st == "success" else ChefState.IDLE,
                    hint=f"Yüklenen tur: #{node.get('turn_number', 1)} ({node.get('branch_name', 'Ana Dal')})"
                )

    def navigate_back(self):
        if self.nav_index > 0:
            self.nav_index -= 1
            self.load_conversation_view(self.nav_history[self.nav_index], record_nav=False)

    def navigate_forward(self):
        if self.nav_index + 1 < len(self.nav_history):
            self.nav_index += 1
            self.load_conversation_view(self.nav_history[self.nav_index], record_nav=False)

    def _update_header_title(self):
        conv = branch_memory.get_conversation(self.active_conversation_id) if self.active_conversation_id else None
        title = conv.get("title", "Yeni Görev") if conv else "Yeni Görev"
        branch = "Ana Dal"
        if self.active_conversation_id and self.active_node_id:
            node = branch_memory.get_node(self.active_conversation_id, self.active_node_id)
            if node:
                branch = node.get("branch_name", "Ana Dal")
        short = f"{title[:26]}{'…' if len(title) > 26 else ''}"
        self.btn_header_branch.configure(text=f"🌿 {branch} · {short}")

    def _set_branch_fork_point(self, conversation_id: str, node_id: str):
        self.active_fork_parent_id = node_id
        branch_memory.set_fork_point(conversation_id, node_id)
        self._render_fork_banner_pill()
        self.gorev_girisi.focus_set()

    def _clear_fork_point(self):
        self.active_fork_parent_id = None
        self._render_fork_banner_pill()

    def _render_fork_banner_pill(self):
        for w in self.fork_pill_frame.winfo_children():
            w.destroy()
        if not self.active_fork_parent_id or not self.active_conversation_id:
            self.fork_pill_frame.grid_forget()
            return
        node = branch_memory.get_node(self.active_conversation_id, self.active_fork_parent_id)
        if not node:
            self.fork_pill_frame.grid_forget()
            return
        self.fork_pill_frame.grid(row=0, column=2, padx=(0, 12))
        ctk.CTkButton(
            self.fork_pill_frame,
            text=f"↩️ Tur #{node.get('turn_number', 1)} dalından ✕",
            height=26,
            corner_radius=13,
            fg_color="#2E1065",
            hover_color="#4C1D95",
            text_color="#DDD6FE",
            font=(FONT_UI, 10, "bold"),
            command=self._clear_fork_point,
        ).pack()

    def _center_modal(self, modal: ctk.CTkToplevel, width: int, height: int):
        """Modal pencereyi ana pencerenin tam ortasına konumlandırır ve ekran dışına taşmasını engeller."""
        try:
            self.update_idletasks()
            scale = self._get_scale_factor()
            phys_w = int(round(width * scale))
            phys_h = int(round(height * scale))
            scr_w = max(phys_w + 32, int(self.winfo_screenwidth()))
            scr_h = max(phys_h + 64, int(self.winfo_screenheight()))
            if self.winfo_viewable() and self.winfo_width() > 100 and self.winfo_height() > 100:
                px = int(self.winfo_rootx()) + (int(self.winfo_width()) - phys_w) // 2
                py = int(self.winfo_rooty()) + (int(self.winfo_height()) - phys_h) // 2
            else:
                px = (scr_w - phys_w) // 2
                py = (scr_h - phys_h) // 2
            x = max(12, min(px, scr_w - phys_w - 16))
            y = max(12, min(py, scr_h - phys_h - 48))
            modal.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            modal.geometry(f"{width}x{height}")

    def _edit_node_modal(self, conversation_id: str, node: Dict[str, Any]):
        nid = node["node_id"]
        modal = ctk.CTkToplevel(self)
        modal.title("Turu Düzenle")
        self._center_modal(modal, 560, 380)
        modal.configure(fg_color=BG_APP)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text="Kullanıcı İstemi:", font=(FONT_UI, 12, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=18, pady=(14, 4))
        p_box = ctk.CTkTextbox(modal, height=110, fg_color=BG_SURFACE, border_color=BORDER_SUBTLE, border_width=1)
        p_box.pack(fill="x", padx=18)
        p_box.insert("1.0", node.get("prompt", ""))

        ctk.CTkLabel(modal, text="Şef Özeti:", font=(FONT_UI, 12, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=18, pady=(12, 4))
        s_box = ctk.CTkTextbox(modal, height=120, fg_color=BG_SURFACE, border_color=BORDER_SUBTLE, border_width=1)
        s_box.pack(fill="both", expand=True, padx=18)
        s_box.insert("1.0", node.get("chef_summary", ""))

        def _save():
            branch_memory.update_node_prompt(
                conversation_id, nid, p_box.get("1.0", "end-1c").strip(), s_box.get("1.0", "end-1c").strip()
            )
            modal.destroy()
            self.load_conversation_view(conversation_id, target_node_id=nid, record_nav=False)

        ctk.CTkButton(
            modal, text="Kaydet", height=34, fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER, command=_save
        ).pack(pady=14)

    def _delete_node_ui(self, conversation_id: str, node_id: str):
        branch_memory.delete_node(conversation_id, node_id)
        if self.active_node_id == node_id:
            self.active_node_id = None
        self.load_conversation_view(conversation_id, record_nav=False)

    def kaynak_dosya_sec(self):
        files = filedialog.askopenfilenames(
            title="Görsel veya Belge Ekle",
            filetypes=[
                (
                    "Desteklenen Dosyalar",
                    "*.png *.jpg *.jpeg *.webp *.gif *.pdf *.txt *.md *.py *.cs *.json *.html *.css *.js *.yaml *.yml"
                ),
                ("Görseller", "*.png *.jpg *.jpeg *.webp *.gif"),
                ("Belgeler & Kod", "*.pdf *.txt *.md *.py *.cs *.json *.html *.css *.js *.yaml *.yml"),
                ("Tüm Dosyalar", "*.*"),
            ],
        )
        if not files:
            return
        for f in files:
            if f not in self.secilen_kaynak_tekil_dosyalar:
                self.secilen_kaynak_tekil_dosyalar.append(f)
        self._rebuild_source_files_list()
        self._guncelle_kaynak_gorunumu()

    def kaynak_klasor_sec(self):
        folder = filedialog.askdirectory(title="Kaynak Klasör Bağla")
        if not folder:
            return
        if folder not in self.secilen_kaynak_klasorler:
            self.secilen_kaynak_klasorler.append(folder)
        self._rebuild_source_files_list()
        self._guncelle_kaynak_gorunumu()

    def kaynak_temizle(self):
        self.secilen_klasor = ""
        self.secilen_kaynak_klasorler = []
        self.secilen_kaynak_tekil_dosyalar = []
        self.secilen_kaynak_dosyalar = []
        self._guncelle_kaynak_gorunumu()

    def klasor_sec(self):
        folder = filedialog.askdirectory(title="Çıktı / Hedef Klasör Seç")
        if folder:
            self.secilen_klasor = folder
            self._guncelle_kaynak_gorunumu()

    def _open_bridges_status_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Sistem & Köprü Sağlığı")
        self._center_modal(modal, 500, 360)
        modal.configure(fg_color=BG_APP)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(
            modal, text="🔌 Model & Uygulama Köprü Durumu",
            font=(FONT_UI, 15, "bold"), text_color=TEXT_PRIMARY
        ).pack(anchor="w", padx=20, pady=(16, 10))

        card = ctk.CTkFrame(modal, fg_color=BG_SURFACE, corner_radius=12, border_width=1, border_color=BORDER_SUBTLE)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        cfg = load_config() or {}
        sef_cfg = cfg.get("sef", {})
        ctk.CTkLabel(
            card,
            text=f"👑 Şef Modeli:  {sef_cfg.get('varsayilan_saglayici', 'gemini').upper()} · {sef_cfg.get('model', '-')}",
            anchor="w", font=(FONT_UI, 12), text_color=TEXT_PRIMARY
        ).pack(fill="x", padx=16, pady=(14, 6))

        lbl_unity = ctk.CTkLabel(card, text="🎮 Unity MCP (:8088): Kontrol ediliyor...", anchor="w", font=(FONT_UI, 12), text_color=TEXT_MUTED)
        lbl_unity.pack(fill="x", padx=16, pady=6)

        lbl_blender = ctk.CTkLabel(card, text="🎨 Blender MCP (:9876): Kontrol ediliyor...", anchor="w", font=(FONT_UI, 12), text_color=TEXT_MUTED)
        lbl_blender.pack(fill="x", padx=16, pady=6)

        def _probe():
            u_text = "🎮 Unity MCP (:8088): Çevrimdışı (Editor kapalı olabilir)"
            u_col = TEXT_MUTED
            try:
                from tools.unity_bridge_client import UnityBridgeClient
                uc = UnityBridgeClient()
                if uc.is_connected():
                    st = uc.get_status()
                    u_text = f"🎮 Unity MCP (:8088): Çevrimiçi · Sahne: {st.get('scene_name', 'Aktif')}"
                    u_col = ACCENT_GREEN
            except Exception:
                pass

            b_text = "🎨 Blender MCP (:9876): Çevrimdışı"
            b_col = TEXT_MUTED
            try:
                from tools.blender_bridge_client import BlenderBridgeClient, find_blender_executable
                bc = BlenderBridgeClient(timeout=1.5)
                exe = find_blender_executable()
                if bc.is_alive():
                    b_text = "🎨 Blender MCP (:9876): Canlı Köprü Bağlı"
                    b_col = ACCENT_GREEN
                elif exe:
                    b_text = f"🎨 Blender Headless Hazır ({os.path.basename(os.path.dirname(exe))})"
                    b_col = ACCENT_AMBER
            except Exception:
                pass

            def _update_ui():
                if modal.winfo_exists():
                    lbl_unity.configure(text=u_text, text_color=u_col)
                    lbl_blender.configure(text=b_text, text_color=b_col)

            self.after(0, _update_ui)

        threading.Thread(target=_probe, daemon=True).start()

        ctk.CTkButton(
            modal, text="Kapat", width=110, height=32, fg_color=BG_ELEVATED, hover_color=BG_HOVER, command=modal.destroy
        ).pack(pady=(0, 14))

    def _open_branch_tree_modal(self):
        if not self.active_conversation_id:
            return
        nodes = branch_memory.get_all_nodes_sorted(self.active_conversation_id)
        modal = ctk.CTkToplevel(self)
        modal.title("Dal & Zaman Haritası")
        self._center_modal(modal, 560, 440)
        modal.configure(fg_color=BG_APP)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text="🌿 Konuşma Dalları", font=(FONT_UI, 15, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=18, pady=(14, 8))
        scroll = ctk.CTkScrollableFrame(modal, fg_color=BG_SURFACE, corner_radius=12)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        if not nodes:
            ctk.CTkLabel(scroll, text="Bu görevde henüz tur yok.", text_color=TEXT_DIM).pack(pady=30)
            return

        for n in nodes:
            nid = n["node_id"]
            is_cur = (nid == self.active_node_id)
            row = ctk.CTkFrame(scroll, fg_color=BG_CARD if is_cur else "transparent", corner_radius=8)
            row.pack(fill="x", padx=6, pady=3)
            ctk.CTkButton(
                row,
                text=f"Tur #{n.get('turn_number', 1)} · {n.get('branch_name', 'Ana Dal')} — {n.get('prompt', '')[:45]}",
                anchor="w",
                fg_color="transparent",
                hover_color=BG_HOVER,
                text_color=ACCENT_CYAN if is_cur else TEXT_PRIMARY,
                command=lambda target=nid: (modal.destroy(), self._select_node_view(self.active_conversation_id, target)),
            ).pack(side="left", fill="x", expand=True, padx=4, pady=4)

    def _open_settings_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("LaSef Hafıza & Ayarlar")
        self._center_modal(modal, 460, 260)
        modal.configure(fg_color=BG_APP)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text="⚙️ Hafıza & Depolama", font=(FONT_UI, 15, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkLabel(
            modal, text=f"Kayıt Dosyası:\n{branch_memory.storage_file}",
            anchor="w", justify="left", wraplength=410, font=(FONT_UI, 11), text_color=TEXT_MUTED
        ).pack(fill="x", padx=20, pady=(0, 16))

        def _clear_all():
            branch_memory.clear_all_history()
            modal.destroy()
            self.start_new_conversation_ui()

        ctk.CTkButton(
            modal, text="🗑️ Tüm Sohbet Geçmişini Temizle", height=34,
            fg_color="#7F1D1D", hover_color="#991B1B", command=_clear_all
        ).pack(pady=6)

        ctk.CTkButton(
            modal, text="Kapat", width=100, height=30,
            fg_color=BG_ELEVATED, hover_color=BG_HOVER, command=modal.destroy
        ).pack(pady=8)

    def _open_single_file_preview(self, file_info: Dict[str, Any], node: Dict[str, Any]):
        fpath = file_info.get("path") or ""
        fname = os.path.basename(fpath) if fpath else file_info.get("name", "Dosya")
        modal = ctk.CTkToplevel(self)
        modal.title(f"Dosya Önizleme · {fname}")
        self._center_modal(modal, 760, 540)
        modal.configure(fg_color=BG_APP)
        modal.transient(self)

        ctk.CTkLabel(
            modal, text=f"📄 {fname}  ({fpath or 'Bellek'})",
            anchor="w", font=(FONT_UI, 12, "bold"), text_color=TEXT_PRIMARY
        ).pack(fill="x", padx=16, pady=(12, 6))

        box = ctk.CTkTextbox(modal, fg_color="#090D14", font=(FONT_MONO, 11), text_color="#E2E8F0", wrap="none")
        box.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        content = file_info.get("content", "")
        if not content and fpath and os.path.isfile(fpath):
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as exc:
                content = f"Dosya okunamadı: {exc}"
        box.insert("1.0", content or "(İçerik önizlemesi yok)")
        box.configure(state="disabled")

    def _open_files_inspector_modal(self):
        if not self.active_conversation_id or not self.active_node_id:
            return
        node = branch_memory.get_node(self.active_conversation_id, self.active_node_id)
        if not node:
            return
        files = node.get("files_produced") or []
        modal = ctk.CTkToplevel(self)
        modal.title("Üretilen Dosyalar")
        self._center_modal(modal, 540, 400)
        modal.configure(fg_color=BG_APP)
        modal.transient(self)

        scroll = ctk.CTkScrollableFrame(modal, fg_color=BG_SURFACE, corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=16, pady=16)
        if not files:
            ctk.CTkLabel(scroll, text="Bu turda üretilmiş dosya kaydı yok.", text_color=TEXT_DIM).pack(pady=30)
            return
        for f_info in files:
            fpath = f_info.get("path") or f_info.get("name", "Dosya")
            ctk.CTkButton(
                scroll, text=f"📄 {fpath}", anchor="w", fg_color="transparent", hover_color=BG_HOVER,
                command=lambda fi=f_info: self._open_single_file_preview(fi, node)
            ).pack(fill="x", pady=2)

    def _open_simple_edit_modal(self, title: str, label_text: str, initial_value: str, on_save):
        modal = ctk.CTkToplevel(self)
        modal.title(title)
        self._center_modal(modal, 420, 180)
        modal.configure(fg_color=BG_APP)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text=label_text, font=(FONT_UI, 12, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=18, pady=(16, 6))
        entry = ctk.CTkEntry(modal, fg_color=BG_SURFACE, border_color=BORDER_SUBTLE, border_width=1)
        entry.pack(fill="x", padx=18)
        entry.insert(0, initial_value)
        entry.focus_set()

        def _submit(_e=None):
            val = entry.get()
            modal.destroy()
            on_save(val)

        entry.bind("<Return>", _submit)
        ctk.CTkButton(modal, text="Kaydet", width=110, fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER, command=_submit).pack(pady=16)

    def _open_confirm_modal(self, title: str, msg: str, on_yes):
        modal = ctk.CTkToplevel(self)
        modal.title(title)
        self._center_modal(modal, 420, 170)
        modal.configure(fg_color=BG_APP)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text=msg, wraplength=380, font=(FONT_UI, 12), text_color=TEXT_PRIMARY).pack(padx=20, pady=(22, 16))
        row = ctk.CTkFrame(modal, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Vazgeç", width=100, fg_color=BG_ELEVATED, hover_color=BG_HOVER, command=modal.destroy).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Sil", width=100, fg_color="#991B1B", hover_color="#B91C1C", command=lambda: (modal.destroy(), on_yes())).pack(side="left", padx=6)

    def _setup_stdout_redirect(self):
        self.redirector = ModernTextRedirector(self.terminal_kutusu, self, original_stream=self._orig_stdout)
        sys.stdout = self.redirector
        sys.stderr = self.redirector

    def _konsolu_temizle(self):
        if self.redirector:
            self.redirector.clear_buffer()
        try:
            self.terminal_kutusu.configure(state="normal")
            self.terminal_kutusu.delete("1.0", "end")
            self.terminal_kutusu.configure(state="disabled")
        except Exception:
            pass

    def _konsolu_kopyala(self):
        try:
            txt = self.terminal_kutusu.get("1.0", "end-1c")
            self.clipboard_clear()
            self.clipboard_append(txt)
            self.set_system_status("● Log Kopyalandı", ACCENT_CYAN)
        except Exception:
            pass

    def _konsolu_txt_kaydet(self):
        txt = self.terminal_kutusu.get("1.0", "end-1c")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Metin Dosyası", "*.txt")], title="Konsolu Kaydet"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)

    def set_system_status(self, text: str, color: str):
        try:
            self.btn_status_pill.configure(text=text, text_color=color)
        except Exception:
            pass

    def baslat_thread(self):
        if self.is_running:
            return
        self._close_popovers()

        gorev = "" if self._placeholder_active else self.gorev_girisi.get("1.0", "end-1c").strip()
        if not gorev:
            self.set_chef_animation(ChefState.GREETING, hint="Önce küçük bir görev açıklaması yazmalısın!")
            self.gorev_girisi.focus_set()
            return

        klasor = self.secilen_klasor
        kaynak = list(self.secilen_kaynak_dosyalar)

        self.is_running = True
        self.btn_baslat.configure(state="disabled", text="⏳ Çalışıyor")
        self.set_system_status("● Orkestra Çalışıyor", ACCENT_AMBER)
        self.stage_progress.configure(progress_color=ACCENT_AMBER)
        self.stage_progress.set(0.08)
        self.set_chef_animation(ChefState.THINKING, hint="Baş Şef görevi analiz ediyor ve kum saatini başlattı...")
        self.lbl_chef_headline.configure(text="Baş Şef Planlıyor...")

        self._clear_agent_cards_display()
        self._konsolu_temizle()
        self.toggle_inspector(force_open=True)

        conv_id = self.active_conversation_id
        parent_for_run = self.active_fork_parent_id or self.active_node_id

        if not self.active_project_id and klasor:
            proj = branch_memory.get_or_create_project_for_folder(klasor)
            self.active_project_id = proj["project_id"]

        if not conv_id or not branch_memory.get_conversation(conv_id):
            conv = branch_memory.create_new_conversation(
                project_id=self.active_project_id,
                title=generate_smart_title(gorev),
                target_folder=klasor,
            )
            conv_id = conv["conversation_id"]
            self.active_conversation_id = conv_id
            parent_for_run = None

        branch_context_str = branch_memory.build_branch_prompt_context(conv_id, parent_for_run)
        conv_id, node_id = branch_memory.start_prompt_node(
            prompt=gorev,
            target_folder=klasor,
            source_files=kaynak,
            conversation_id=conv_id,
            parent_node_id=parent_for_run,
        )
        self.active_conversation_id = conv_id
        self.active_node_id = node_id
        self.active_fork_parent_id = None

        self.secilen_kaynak_klasorler = []
        self.secilen_kaynak_tekil_dosyalar = []
        self.secilen_kaynak_dosyalar = []
        self._guncelle_kaynak_gorunumu()

        self._render_fork_banner_pill()
        self.refresh_sidebar()
        self._render_conversation_messages(conv_id, node_id)

        self._apply_placeholder()

        t = threading.Thread(
            target=self._orkestra_calistir_arkaplan,
            args=(gorev, klasor, kaynak, conv_id, node_id, branch_context_str),
            daemon=True,
        )
        t.start()

    def _orkestra_calistir_arkaplan(
        self,
        gorev: str,
        klasor: str,
        kaynak: List[str],
        conv_id: str,
        node_id: str,
        branch_context_str: str,
    ):
        meta_out: Dict[str, Any] = {}
        sonuc_raporu = ""
        run_status = "success"
        try:
            sonuc_raporu = orkestrayi_yonet(
                kullanici_istegi=gorev,
                hedef_klasor=klasor,
                kaynak_dosyalar=kaynak,
                branch_context=branch_context_str,
                meta_out=meta_out,
            )
            if meta_out.get("verification_failed"):
                run_status = "warning"
        except Exception as exc:
            run_status = "error"
            sonuc_raporu = f"Orkestrasyon sırasında beklenmedik hata: {exc}"
            print(f"\n❌ FATAL UI THREAD ERROR: {exc}")

        saved_log = ""
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "terminal_outputs")
            os.makedirs(log_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            log_path = os.path.join(log_dir, f"terminal_{ts}.txt")
            saved_log = self.redirector.get_full_log() if self.redirector else ""
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(saved_log)
        except Exception:
            pass

        with self._cards_lock:
            agent_tasks_snapshot = [
                {
                    "agent_id": aid,
                    "name": info.get("name", aid),
                    "task": info.get("task", ""),
                    "model": info.get("model", ""),
                    "status": info.get("status", "Tamamlandı"),
                }
                for aid, info in self.agent_cards_data.items()
            ]

        try:
            branch_memory.complete_prompt_node(
                conversation_id=conv_id,
                node_id=node_id,
                chef_summary=str(sonuc_raporu or ""),
                terminal_log=saved_log,
                agent_tasks=agent_tasks_snapshot,
                files_produced=meta_out.get("files_produced", []),
                architecture_contract=meta_out.get("architecture_contract", ""),
                target_folder=meta_out.get("target_folder") or klasor,
                token_stats=meta_out.get("token_stats", {}),
                app_key=meta_out.get("app_key", ""),
                status=run_status,
            )
        except Exception as exc:
            print(f"⚠️ Hafıza kayıt hatası: {exc}")

        def _finish_ui():
            if not self.winfo_exists():
                return
            self.is_running = False
            self.btn_baslat.configure(state="normal", text="➤ Başlat")
            if run_status == "success":
                self.set_system_status("● Tamamlandı", ACCENT_GREEN)
                self.stage_progress.configure(progress_color=ACCENT_GREEN)
                self.stage_progress.set(1.0)
                self.set_chef_animation(ChefState.SUCCESS, hint="Tüm adımlar tamamlandı!")
                self.lbl_chef_headline.configure(text="Görev Tamamlandı")
            elif run_status == "warning":
                self.set_system_status("● Doğrulama Uyarısı", ACCENT_AMBER)
                self.stage_progress.configure(progress_color=ACCENT_AMBER)
                self.stage_progress.set(1.0)
                self.set_chef_animation(ChefState.ERROR, hint="Derleme veya sahne doğrulamasında uyarı var — konsolu kontrol et.")
                self.lbl_chef_headline.configure(text="Doğrulama Uyarısı")
            else:
                self.set_system_status("● Hata / Müdahale", ACCENT_RED)
                self.stage_progress.configure(progress_color=ACCENT_RED)
                self.set_chef_animation(ChefState.ERROR, hint="Bir sorun oluştu — konsolu kontrol et.")
                self.lbl_chef_headline.configure(text="Müdahale Gerekli")

            self.load_conversation_view(conv_id, target_node_id=node_id, record_nav=False)

        self.after(0, _finish_ui)

    def _on_scan_progress_event(self, event):
        try:
            data = getattr(event, "data", None)
            if isinstance(data, dict):
                self.after(0, self._update_scan_progress_ui, data)
        except Exception:
            pass

    def _update_scan_progress_ui(self, data: dict):
        try:
            if not self.winfo_exists():
                return
            ratio = float(data.get("ratio", 0.0))
            percent = float(data.get("percent", 0.0))
            done_items = int(data.get("done_items", 0))
            total_items = int(data.get("total_items", 0))
            eta_text = str(data.get("eta_text", ""))
            avg_s = float(data.get("avg_per_item_s", 0.0))
            stage_text = str(data.get("stage_text", ""))

            if hasattr(self, "stage_progress"):
                bar_val = 0.18 if percent >= 100.0 else max(0.02, min(0.99, ratio))
                self.stage_progress.set(bar_val)

            if hasattr(self, "lbl_chef_headline"):
                if percent >= 100.0:
                    self.lbl_chef_headline.configure(text="Kaynaklar Hazır · Baş Şef Planlıyor...")
                else:
                    self.lbl_chef_headline.configure(
                        text=f"Kaynaklar Taranıyor · %{percent:.0f} ({eta_text})"
                    )

            if hasattr(self, "lbl_chef_sub") and total_items > 0:
                if percent < 100.0:
                    self.lbl_chef_sub.configure(
                        text=f"{done_items}/{total_items} dosya · Ort: {avg_s:.2f}sn/dosya"
                    )

            if hasattr(self, "lbl_stage_note") and stage_text:
                self.lbl_stage_note.configure(text=stage_text)
        except Exception:
            pass

    def on_closing(self):
        self._save_ui_prefs()
        try:
            event_bus.unsubscribe(EVENT_TIMELINE_STAGE, self._on_timeline_event)
            event_bus.unsubscribe(EVENT_SCAN_PROGRESS, self._on_scan_progress_event)
        except Exception:
            pass
        try:
            if hasattr(self, "chef_animator"):
                self.chef_animator.stop()
        except Exception:
            pass
        try:
            sys.stdout = self._orig_stdout
            sys.stderr = self._orig_stderr
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
