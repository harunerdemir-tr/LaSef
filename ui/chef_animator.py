import math
import time
import tkinter as tk
from typing import Callable, List, Optional, Tuple


class ChefState:
    """Animated companion visual states for LaSef Chef."""
    IDLE = "idle"
    GREETING = "greeting"
    TYPING = "typing"
    THINKING = "thinking"
    ORCHESTRATING = "orchestrating"
    AUDITING = "auditing"
    SUCCESS = "success"
    ERROR = "error"


_STATE_ACCENTS = {
    ChefState.IDLE: ("#3B82F6", "#1E293B", "Hazır"),
    ChefState.GREETING: ("#38BDF8", "#164E63", "Selam!"),
    ChefState.TYPING: ("#60A5FA", "#1E3A8A", "Dinliyor"),
    ChefState.THINKING: ("#F59E0B", "#451A03", "Planlıyor"),
    ChefState.ORCHESTRATING: ("#06B6D4", "#083344", "Yönetiyor"),
    ChefState.AUDITING: ("#A78BFA", "#2E1065", "Denetliyor"),
    ChefState.SUCCESS: ("#10B981", "#064E3B", "Tamamlandı"),
    ChefState.ERROR: ("#F87171", "#450A0A", "Müdahale"),
}

_WORKER_PALETTE = [
    "#38BDF8",
    "#10B981",
    "#F59E0B",
    "#A78BFA",
    "#F472B6",
    "#22D3EE",
]

_GREETING_TOKENS = (
    "selam", "merhaba", "mrb", "slm", "hey", "hello", "hi",
    "günaydın", "gunaydin", "iyi akşamlar", "naber", "selamlar"
)


def _rotate_point(px: float, py: float, cx: float, cy: float, angle: float) -> Tuple[float, float]:
    """Rotates (px, py) around (cx, cy) by radians."""
    ca = math.cos(angle)
    sa = math.sin(angle)
    dx = px - cx
    dy = py - cy
    return cx + dx * ca - dy * sa, cy + dx * sa + dy * ca


def _smoothstep(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


class ChefAnimatorCanvas(tk.Canvas):
    """
    Hafif, bağımlılıksız, ~25 FPS vektörel LaSef Şef & Kum Saati / Ajan Orbit animasyon bileşeni.
    Yazı yazarken selam verir, düşünürken kum saatini çevirir, çalışırken alt ajanları yönetir.
    """

    def __init__(
        self,
        master,
        width: int = 216,
        height: int = 76,
        bg_color: str = "#111622",
        on_click: Optional[Callable[[], None]] = None,
        **kwargs
    ):
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg_color,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            **kwargs
        )
        self._base_state: str = ChefState.IDLE
        self._transient_state: Optional[str] = None
        self._transient_until: float = 0.0
        self._worker_count: int = 3
        self._custom_caption: str = ""
        self._bg_color: str = bg_color
        self._start_ts: float = time.monotonic()
        self._state_ts: float = self._start_ts
        self._after_id: Optional[str] = None
        self._destroyed: bool = False
        self._on_click = on_click
        self._frame_ms: int = 40

        self.bind("<Button-1>", self._handle_click)
        self.bind("<Destroy>", self._handle_destroy)
        self._tick()

    @property
    def current_state(self) -> str:
        """Aktif görünen animasyon durumunu döndürür (geçici selam/yazma dahil)."""
        if self._transient_state and time.monotonic() < self._transient_until:
            return self._transient_state
        return self._base_state

    def set_bg(self, bg_color: str) -> None:
        self._bg_color = bg_color
        try:
            self.configure(bg=bg_color)
        except Exception:
            pass

    def set_state(self, state: str, worker_count: Optional[int] = None, label: str = "") -> None:
        """Kalıcı animasyon durumunu değiştirir."""
        if state not in _STATE_ACCENTS:
            state = ChefState.IDLE
        if state != self._base_state:
            self._base_state = state
            self._state_ts = time.monotonic()
        if state in (ChefState.THINKING, ChefState.ORCHESTRATING, ChefState.AUDITING):
            self._transient_state = None
        if worker_count is not None:
            self._worker_count = max(1, min(12, int(worker_count)))
        if label:
            self._custom_caption = label
        elif state == ChefState.IDLE:
            self._custom_caption = ""

    def set_worker_count(self, count: int) -> None:
        self._worker_count = max(1, min(12, int(count)))

    def trigger_wave(self, greeting_mode: bool = True, duration: float = 2.2) -> None:
        """Şefin el sallayıp şapkasını kaldırmasını sağlar (boştayken/sonuçtayken)."""
        if self._base_state in (ChefState.THINKING, ChefState.ORCHESTRATING, ChefState.AUDITING):
            return
        self._transient_state = ChefState.GREETING if greeting_mode else ChefState.TYPING
        self._transient_until = time.monotonic() + max(0.6, duration)

    def trigger_typing_reaction(self, text_value: str = "") -> None:
        """Kullanıcı klavyeden yazarken selam/dinleme tepkisi verir."""
        if self._base_state in (ChefState.THINKING, ChefState.ORCHESTRATING, ChefState.AUDITING):
            return
        lowered = (text_value or "").strip().lower()
        tail = lowered[-28:] if len(lowered) > 28 else lowered
        is_greeting = any(tok in tail.split() or tail.startswith(tok) for tok in _GREETING_TOKENS)
        if is_greeting or len(lowered) <= 1:
            self.trigger_wave(greeting_mode=True, duration=2.3)
        else:
            self.trigger_wave(greeting_mode=False, duration=1.25)

    def _handle_click(self, _event=None) -> None:
        self.trigger_wave(greeting_mode=True, duration=2.2)
        if callable(self._on_click):
            try:
                self._on_click()
            except Exception:
                pass

    def _handle_destroy(self, event=None) -> None:
        if event is None or event.widget is self:
            self.stop()

    def stop(self) -> None:
        self._destroyed = True
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _tick(self) -> None:
        if self._destroyed:
            return
        try:
            if not self.winfo_exists():
                return
            self._draw_frame()
            self._after_id = self.after(self._frame_ms, self._tick)
        except tk.TclError:
            self._destroyed = True
        except Exception:
            if not self._destroyed:
                self._after_id = self.after(120, self._tick)

    def _rounded_pill(self, x1: float, y1: float, x2: float, y2: float, r: float = 10, **kwargs):
        r = min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0)
        pts = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.create_polygon(pts, smooth=True, **kwargs)

    def _draw_frame(self) -> None:
        now = time.monotonic()
        t = now - self._start_ts
        state = self.current_state
        if self._transient_state and now >= self._transient_until:
            self._transient_state = None
            state = self._base_state

        accent, halo_bg, default_label = _STATE_ACCENTS.get(state, _STATE_ACCENTS[ChefState.IDLE])

        w = max(180, int(self.winfo_width() or self["width"]))
        h = max(64, int(self.winfo_height() or self["height"]))

        self.delete("anim")

        cx = 44.0
        base_cy = h * 0.56
        self._draw_chef_character(cx, base_cy, t, state, accent, halo_bg)

        prop_x = min(w - 58.0, max(124.0, w * 0.66))
        prop_y = h * 0.49
        self._draw_companion_prop(prop_x, prop_y, w, h, t, state, accent, default_label)

    def _draw_chef_character(
        self,
        cx: float,
        cy: float,
        t: float,
        state: str,
        accent: str,
        halo_bg: str,
    ) -> None:
        if state == ChefState.SUCCESS:
            bob = -abs(math.sin(t * 6.5)) * 4.5
        elif state == ChefState.GREETING:
            bob = -abs(math.sin(t * 4.2)) * 2.2
        elif state == ChefState.ORCHESTRATING:
            bob = math.sin(t * 5.0) * 1.6
        else:
            bob = math.sin(t * 2.2) * 1.2

        y = cy + bob

        pulse = 1.0 + 0.06 * math.sin(t * 3.5)
        r_outer = 27.0 * pulse
        self.create_oval(
            cx - r_outer, cy - r_outer - 4, cx + r_outer, cy + r_outer - 4,
            fill=halo_bg, outline=accent, width=1.4, tags="anim"
        )

        self.create_arc(
            cx - 19, y + 7, cx + 19, y + 36,
            start=0, extent=180, style=tk.CHORD,
            fill="#F8FAFC", outline="#CBD5E1", width=1.2, tags="anim"
        )
        self.create_polygon(
            cx - 7, y + 10, cx + 7, y + 10, cx, y + 20,
            fill="#1E293B", outline="", tags="anim"
        )
        self.create_polygon(
            cx - 4, y + 11, cx + 4, y + 11, cx, y + 16,
            fill=accent, outline="", tags="anim"
        )

        head_y = y - 2.0
        tilt_x = 0.0
        if state == ChefState.GREETING:
            tilt_x = math.sin(t * 5.5) * 1.4
        elif state == ChefState.THINKING:
            tilt_x = -1.2

        hx = cx + tilt_x
        self.create_oval(
            hx - 12.5, head_y - 12.0, hx + 12.5, head_y + 12.0,
            fill="#FCD9B6", outline="#E0AC82", width=1.2, tags="anim"
        )

        blink = (t % 3.8) < 0.14
        look_dx = 0.0
        look_dy = 0.0
        if state == ChefState.THINKING:
            look_dx = 1.5
            look_dy = -1.1
        elif state == ChefState.TYPING:
            look_dx = 1.3
            look_dy = 0.5

        for side in (-1, 1):
            ex = hx + side * 4.5
            ey = head_y - 1.5
            if state in (ChefState.GREETING, ChefState.SUCCESS):
                self.create_arc(
                    ex - 2.8, ey - 1.5, ex + 2.8, ey + 3.5,
                    start=15, extent=150, style=tk.ARC,
                    outline="#1E293B", width=1.8, tags="anim"
                )
            elif blink:
                self.create_line(
                    ex - 2.4, ey + 0.5, ex + 2.4, ey + 0.5,
                    fill="#1E293B", width=1.6, tags="anim"
                )
            else:
                self.create_oval(
                    ex - 1.8 + look_dx * 0.4, ey - 2.0 + look_dy * 0.4,
                    ex + 1.8 + look_dx * 0.4, ey + 2.0 + look_dy * 0.4,
                    fill="#0F172A", outline="", tags="anim"
                )
                self.create_oval(
                    ex - 0.8 + look_dx * 0.4, ey - 1.4 + look_dy * 0.4,
                    ex + 0.4 + look_dx * 0.4, ey - 0.2 + look_dy * 0.4,
                    fill="#FFFFFF", outline="", tags="anim"
                )

        self.create_arc(
            hx - 6.0, head_y + 1.2, hx + 0.2, head_y + 5.8,
            start=15, extent=155, style=tk.ARC, outline="#334155", width=1.9, tags="anim"
        )
        self.create_arc(
            hx - 0.2, head_y + 1.2, hx + 6.0, head_y + 5.8,
            start=10, extent=155, style=tk.ARC, outline="#334155", width=1.9, tags="anim"
        )
        if state in (ChefState.GREETING, ChefState.SUCCESS):
            self.create_arc(
                hx - 4.0, head_y + 3.0, hx + 4.0, head_y + 8.5,
                start=200, extent=140, style=tk.ARC, outline="#9F1239", width=1.6, tags="anim"
            )
        elif state == ChefState.ERROR:
            self.create_arc(
                hx - 3.5, head_y + 6.0, hx + 3.5, head_y + 10.0,
                start=20, extent=140, style=tk.ARC, outline="#475569", width=1.5, tags="anim"
            )
        else:
            self.create_arc(
                hx - 3.2, head_y + 3.6, hx + 3.2, head_y + 7.2,
                start=200, extent=140, style=tk.ARC, outline="#475569", width=1.4, tags="anim"
            )

        hat_lift = 0.0
        hat_tilt = 0.0
        if state == ChefState.GREETING:
            lift_wave = 0.5 + 0.5 * math.sin(t * 6.0)
            hat_lift = 3.5 + lift_wave * 2.5
            hat_tilt = -3.0 - lift_wave * 1.5
        elif state == ChefState.SUCCESS:
            hat_lift = abs(math.sin(t * 7.0)) * 3.0

        hat_x = hx + hat_tilt * 0.55
        hat_y = head_y - 12.5 - hat_lift

        self.create_oval(hat_x - 13.5, hat_y - 14.0, hat_x - 1.5, hat_y - 1.0, fill="#FFFFFF", outline="#CBD5E1", width=1.0, tags="anim")
        self.create_oval(hat_x + 1.5, hat_y - 14.0, hat_x + 13.5, hat_y - 1.0, fill="#FFFFFF", outline="#CBD5E1", width=1.0, tags="anim")
        self.create_oval(hat_x - 8.5, hat_y - 17.5, hat_x + 8.5, hat_y - 2.0, fill="#FFFFFF", outline="#CBD5E1", width=1.0, tags="anim")
        self.create_rectangle(hat_x - 10.5, hat_y - 6.0, hat_x + 10.5, hat_y + 1.5, fill="#F8FAFC", outline="#CBD5E1", width=1.0, tags="anim")
        self.create_rectangle(hat_x - 10.5, hat_y - 1.2, hat_x + 10.5, hat_y + 1.5, fill=accent, outline="", tags="anim")

        arm_ox = cx + 12.0
        arm_oy = y + 11.0

        if state == ChefState.GREETING:
            ang = -0.95 + 0.55 * math.sin(t * 10.5)
            hx_hand = arm_ox + 15.0 * math.cos(ang)
            hy_hand = arm_oy + 15.0 * math.sin(ang)
            self.create_line(arm_ox, arm_oy, hx_hand, hy_hand, fill="#F8FAFC", width=4.2, capstyle=tk.ROUND, tags="anim")
            self.create_oval(hx_hand - 3.6, hy_hand - 3.6, hx_hand + 3.6, hy_hand + 3.6, fill="#FCD9B6", outline="#E0AC82", width=1.0, tags="anim")
            for k in (1, 2):
                r_arc = 5.5 + k * 3.5
                self.create_arc(
                    hx_hand - r_arc, hy_hand - r_arc, hx_hand + r_arc, hy_hand + r_arc,
                    start=-30, extent=85, style=tk.ARC, outline=accent, width=1.3, tags="anim"
                )
        elif state == ChefState.TYPING:
            ang = -0.55 + 0.25 * math.sin(t * 7.0)
            hx_hand = arm_ox + 13.0 * math.cos(ang)
            hy_hand = arm_oy + 13.0 * math.sin(ang)
            self.create_line(arm_ox, arm_oy, hx_hand, hy_hand, fill="#F8FAFC", width=4.0, capstyle=tk.ROUND, tags="anim")
            self.create_oval(hx_hand - 3.3, hy_hand - 3.3, hx_hand + 3.3, hy_hand + 3.3, fill="#FCD9B6", outline="#E0AC82", width=1.0, tags="anim")
        elif state == ChefState.THINKING:
            chin_x = hx + 7.5
            chin_y = head_y + 8.5
            self.create_line(arm_ox, arm_oy, chin_x + 4, chin_y + 3, chin_x, chin_y, fill="#F8FAFC", width=3.8, capstyle=tk.ROUND, smooth=True, tags="anim")
            self.create_oval(chin_x - 3.0, chin_y - 3.0, chin_x + 3.0, chin_y + 3.0, fill="#FCD9B6", outline="#E0AC82", width=1.0, tags="anim")
        elif state == ChefState.ORCHESTRATING:
            ang = -0.65 + 0.65 * math.sin(t * 7.2)
            hx_hand = arm_ox + 10.5 * math.cos(ang)
            hy_hand = arm_oy + 10.5 * math.sin(ang)
            baton_ang = ang - 0.35 + 0.3 * math.cos(t * 14.4)
            bx = hx_hand + 14.0 * math.cos(baton_ang)
            by = hy_hand + 14.0 * math.sin(baton_ang)
            self.create_line(arm_ox, arm_oy, hx_hand, hy_hand, fill="#F8FAFC", width=4.0, capstyle=tk.ROUND, tags="anim")
            self.create_oval(hx_hand - 3.1, hy_hand - 3.1, hx_hand + 3.1, hy_hand + 3.1, fill="#FCD9B6", outline="", tags="anim")
            self.create_line(hx_hand, hy_hand, bx, by, fill="#E2E8F0", width=2.0, capstyle=tk.ROUND, tags="anim")
            self.create_oval(bx - 2.6, by - 2.6, bx + 2.6, by + 2.6, fill="#22D3EE", outline="#FFFFFF", width=0.8, tags="anim")
        elif state == ChefState.AUDITING:
            lx = arm_ox + 9.0 + 3.0 * math.sin(t * 4.5)
            ly = arm_oy - 8.0 + 2.0 * math.cos(t * 4.5)
            self.create_line(arm_ox, arm_oy, lx - 3, ly + 4, fill="#F8FAFC", width=3.8, capstyle=tk.ROUND, tags="anim")
            self.create_oval(lx - 5.5, ly - 5.5, lx + 5.5, ly + 5.5, fill="#1E1B4B", outline=accent, width=2.0, tags="anim")
            self.create_line(lx - 2.5, ly - 2.0, lx - 0.5, ly - 3.5, fill="#DDD6FE", width=1.4, tags="anim")
        elif state == ChefState.SUCCESS:
            ang = -1.1 + 0.22 * math.sin(t * 8.0)
            hx_hand = arm_ox + 15.0 * math.cos(ang)
            hy_hand = arm_oy + 15.0 * math.sin(ang)
            self.create_line(arm_ox, arm_oy, hx_hand, hy_hand, fill="#F8FAFC", width=4.0, capstyle=tk.ROUND, tags="anim")
            self.create_oval(hx_hand - 3.4, hy_hand - 3.4, hx_hand + 3.4, hy_hand + 3.4, fill="#FCD9B6", outline="", tags="anim")

    def _draw_companion_prop(
        self,
        px: float,
        py: float,
        w: float,
        h: float,
        t: float,
        state: str,
        accent: str,
        default_label: str,
    ) -> None:
        if state == ChefState.IDLE:
            r = 16.0
            self.create_oval(px - r, py - r, px + r, py + r, outline="#263248", width=1.4, dash=(3, 4), tags="anim")
            ang = t * 1.4
            dx, dy = px + r * math.cos(ang), py + r * math.sin(ang)
            self.create_oval(dx - 2.8, dy - 2.8, dx + 2.8, dy + 2.8, fill=accent, outline="", tags="anim")
            self.create_text(px + 26, py, text="Hazır", anchor="w", fill="#64748B", font=("Segoe UI", 9, "bold"), tags="anim")

        elif state == ChefState.GREETING:
            bx1, by1, bx2, by2 = px - 24, py - 14, px + 44, py + 13
            self._rounded_pill(bx1, by1, bx2, by2, r=10, fill="#164E63", outline="#38BDF8", width=1.4, tags="anim")
            self.create_polygon(bx1 + 6, by2 - 4, bx1 - 4, by2 + 3, bx1 + 12, by2, fill="#164E63", outline="", tags="anim")
            self.create_text((bx1 + bx2) / 2, (by1 + by2) / 2, text="Selam!", fill="#E0F2FE", font=("Segoe UI", 9, "bold"), tags="anim")
            for idx in range(3):
                sa = t * 3.0 + idx * 2.1
                sx = px + 54 + 5 * math.cos(sa)
                sy = py - 12 + idx * 10 + 3 * math.sin(sa * 1.4)
                sz = 2.0 + 1.2 * abs(math.sin(t * 5.0 + idx))
                self.create_oval(sx - sz, sy - sz, sx + sz, sy + sz, fill="#FBBF24", outline="", tags="anim")

        elif state == ChefState.TYPING:
            bx1, by1, bx2, by2 = px - 24, py - 13, px + 26, py + 12
            self._rounded_pill(bx1, by1, bx2, by2, r=10, fill="#172554", outline="#60A5FA", width=1.3, tags="anim")
            for i in range(3):
                dot_x = (bx1 + bx2) / 2 - 11 + i * 11
                dot_y = (by1 + by2) / 2 + math.sin(t * 8.0 - i * 1.1) * 2.8
                self.create_oval(dot_x - 2.3, dot_y - 2.3, dot_x + 2.3, dot_y + 2.3, fill="#93C5FD", outline="", tags="anim")
            self.create_text(bx2 + 8, py, text="Dinliyor", anchor="w", fill="#93C5FD", font=("Segoe UI", 8, "bold"), tags="anim")

        elif state == ChefState.THINKING:
            hg_x = px + 6
            hg_y = py
            self._draw_rotating_hourglass(hg_x, hg_y, scale=1.0, t=t, accent="#F59E0B", cycle_sec=3.0)
            for i in range(3):
                dx = px - 34 + i * 9
                dy = py - 8 + math.sin(t * 5.0 - i * 0.9) * 2.8
                self.create_oval(dx - 2.2, dy - 2.2, dx + 2.2, dy + 2.2, fill="#FCD34D", outline="", tags="anim")
            self.create_text(hg_x + 26, py, text="Planlıyor", anchor="w", fill="#FBBF24", font=("Segoe UI", 9, "bold"), tags="anim")

        elif state == ChefState.ORCHESTRATING:
            ocx = px - 4
            ocy = py
            n = max(2, min(self._worker_count, 6))
            self.create_oval(ocx - 25, ocy - 17, ocx + 25, ocy + 17, outline="#164E63", width=1.2, dash=(2, 3), tags="anim")
            self.create_oval(ocx - 5.5, ocy - 5.5, ocx + 5.5, ocy + 5.5, fill="#0891B2", outline="#22D3EE", width=1.5, tags="anim")

            for i in range(n):
                ang = t * 1.85 + (2.0 * math.pi * i / n)
                nx = ocx + 25.0 * math.cos(ang)
                ny = ocy + 17.0 * math.sin(ang)
                col = _WORKER_PALETTE[i % len(_WORKER_PALETTE)]
                self.create_line(ocx, ocy, nx, ny, fill="#1E3A5F", width=1.1, tags="anim")
                pkt = (t * 1.8 + i * 0.37) % 1.0
                px_pkt = ocx + (nx - ocx) * pkt
                py_pkt = ocy + (ny - ocy) * pkt
                self.create_oval(px_pkt - 1.6, py_pkt - 1.6, px_pkt + 1.6, py_pkt + 1.6, fill="#FFFFFF", outline="", tags="anim")
                nr = 4.2 + 0.8 * math.sin(t * 4.5 + i)
                self.create_oval(nx - nr, ny - nr, nx + nr, ny + nr, fill=col, outline="#0F172A", width=1.0, tags="anim")

            self._draw_rotating_hourglass(ocx + 48, py, scale=0.68, t=t, accent="#22D3EE", cycle_sec=2.6)

        elif state == ChefState.AUDITING:
            rx1, ry1, rx2, ry2 = px - 24, py - 15, px + 36, py + 15
            self._rounded_pill(rx1, ry1, rx2, ry2, r=8, fill="#1E1B4B", outline="#6D28D9", width=1.2, tags="anim")
            for r_i in range(3):
                ly = ry1 + 7 + r_i * 7.5
                self.create_line(rx1 + 7, ly, rx2 - 9 - r_i * 5, ly, fill="#4C1D95", width=2.5, capstyle=tk.ROUND, tags="anim")
            scan_x = rx1 + 7 + (rx2 - rx1 - 14) * (0.5 + 0.5 * math.sin(t * 4.5))
            self.create_line(scan_x, ry1 + 3, scan_x, ry2 - 3, fill="#C4B5FD", width=2.0, tags="anim")
            self.create_text(rx2 + 8, py, text="Denetim", anchor="w", fill="#C4B5FD", font=("Segoe UI", 9, "bold"), tags="anim")

        elif state == ChefState.SUCCESS:
            self.create_oval(px - 15, py - 15, px + 15, py + 15, fill="#064E3B", outline="#10B981", width=2.0, tags="anim")
            self.create_line(px - 7, py + 1, px - 1.5, py + 6.5, px + 8, py - 5.5, fill="#FFFFFF", width=2.6, capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="anim")
            for idx in range(6):
                a = idx * (math.pi / 3.0) + t * 1.2
                dist = 19.0 + 4.0 * math.sin(t * 5.0 + idx)
                sx = px + dist * math.cos(a)
                sy = py + dist * math.sin(a)
                col = _WORKER_PALETTE[idx % len(_WORKER_PALETTE)]
                self.create_oval(sx - 2.0, sy - 2.0, sx + 2.0, sy + 2.0, fill=col, outline="", tags="anim")
            self.create_text(px + 24, py, text="Hazır!", anchor="w", fill="#34D399", font=("Segoe UI", 9, "bold"), tags="anim")

        elif state == ChefState.ERROR:
            gx, gy = px - 2, py
            teeth = 6
            pts = []
            base_a = t * 1.8
            for k in range(teeth * 2):
                a = base_a + k * (math.pi / teeth)
                rad = 13.0 if k % 2 == 0 else 8.5
                pts.extend([gx + rad * math.cos(a), gy + rad * math.sin(a)])
            self.create_polygon(pts, fill="#451A03", outline="#F59E0B", width=1.6, tags="anim")
            self.create_oval(gx - 4.0, gy - 4.0, gx + 4.0, gy + 4.0, fill=self._bg_color, outline="#F87171", width=1.4, tags="anim")
            self.create_text(gx + 20, py, text="Onarım", anchor="w", fill="#FCA5A5", font=("Segoe UI", 9, "bold"), tags="anim")

    def _draw_rotating_hourglass(
        self,
        cx: float,
        cy: float,
        scale: float,
        t: float,
        accent: str,
        cycle_sec: float = 3.0,
    ) -> None:
        """
        Gerçek 2D rotasyon matrisi ile dönen ve altın kum akıtan vektörel Kum Saati.
        %72 süre boyunca kum yukarıdan aşağı akar, %28 sürede 180 derece zarifçe döner.
        """
        phase = (t % cycle_sec) / cycle_sec
        pour_end = 0.72
        if phase < pour_end:
            angle = 0.0
            sand_p = phase / pour_end
            is_pouring = True
        else:
            rot_u = (phase - pour_end) / (1.0 - pour_end)
            angle = math.pi * _smoothstep(rot_u)
            sand_p = 1.0
            is_pouring = False

        hw = 10.5 * scale
        hh = 14.5 * scale

        def rot(pts: List[Tuple[float, float]]) -> List[float]:
            out: List[float] = []
            for x0, y0 in pts:
                rx, ry = _rotate_point(cx + x0, cy + y0, cx, cy, angle)
                out.extend([rx, ry])
            return out

        if not is_pouring:
            top_pts = [(-hw * 0.45, -hh * 0.42), (hw * 0.45, -hh * 0.42), (0, -1.5 * scale)]
            bot_pts = [(-hw * 0.65, hh * 0.78), (hw * 0.65, hh * 0.78), (0, hh * 0.25)]
            self.create_polygon(rot(top_pts), fill="#FBBF24", outline="", tags="anim")
            self.create_polygon(rot(bot_pts), fill="#F59E0B", outline="", tags="anim")
        else:
            top_ratio = max(0.08, 1.0 - sand_p)
            bot_ratio = min(0.95, 0.12 + sand_p * 0.85)
            ty = -hh * 0.82 * top_ratio
            tx = hw * 0.72 * top_ratio
            top_pts = [(-tx, ty), (tx, ty), (0, -1.2 * scale)]
            by = hh * 0.82
            bh = by - (hh * 0.72 * (1.0 - bot_ratio) + 2.0 * scale)
            bx = hw * 0.78
            bot_pts = [(-bx, by), (bx, by), (0, max(2.0 * scale, by - bh))]
            self.create_polygon(rot(top_pts), fill="#FBBF24", outline="", tags="anim")
            self.create_polygon(rot(bot_pts), fill="#F59E0B", outline="", tags="anim")
            self.create_line(cx, cy - 1.5 * scale, cx, cy + hh * 0.68, fill="#FDE68A", width=1.4, tags="anim")
            for d in range(2):
                dy = cy + ((t * 28.0 + d * 6.0) % (hh * 0.65))
                self.create_oval(cx - 1.2, dy - 1.2, cx + 1.2, dy + 1.2, fill="#FEF08A", outline="", tags="anim")

        glass_top = rot([(-hw * 0.82, -hh * 0.84), (hw * 0.82, -hh * 0.84), (0, 0)])
        glass_bot = rot([(-hw * 0.82, hh * 0.84), (hw * 0.82, hh * 0.84), (0, 0)])
        self.create_polygon(glass_top, fill="", outline="#CBD5E1", width=1.4, joinstyle=tk.ROUND, tags="anim")
        self.create_polygon(glass_bot, fill="", outline="#CBD5E1", width=1.4, joinstyle=tk.ROUND, tags="anim")

        cap_top = rot([(-hw, -hh * 0.88), (hw, -hh * 0.88)])
        cap_bot = rot([(-hw, hh * 0.88), (hw, hh * 0.88)])
        self.create_line(*cap_top, fill=accent, width=max(2, int(2.6 * scale)), capstyle=tk.ROUND, tags="anim")
        self.create_line(*cap_bot, fill=accent, width=max(2, int(2.6 * scale)), capstyle=tk.ROUND, tags="anim")
