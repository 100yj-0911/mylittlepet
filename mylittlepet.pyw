"""A tiny pixel pet that wanders across the Windows desktop."""

from __future__ import annotations

import json
import math
import os
import random
import time
from pathlib import Path
import tkinter as tk


APP_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = APP_DIR / "pet_settings.json"
TRANSPARENT = "#ff00ff"
CANVAS_W, CANVAS_H = 176, 164
SCALE = 7

PALETTES = {
    "dog": {
        "K": "#403747", "O": "#ed9f49", "L": "#ffc16b", "W": "#fff0d5",
        "D": "#56475a", "E": "#302832", "P": "#f06b83", "N": "#342b34",
    },
    "cat": {
        "K": "#17191b", "G": "#85848a", "L": "#aaa9b0",
        "E": "#202124", "P": "#f29ba6", "N": "#28242c",
    },
}

# Both characters face forward, following the user's new reference images.
SPRITES = {
    "dog": [
        "........KKKK........",
        "....KKKOOOOOOOKKK....",
        "..KKOOOOOOOOOOOOOKK..",
        ".KOOOOOOOOOOOOOOOOOK.",
        "KOOLOOOOOOOOOOOOOLOOK",
        "KOOLOOOOOOOOOOOOOLOOOK",
        "KOLOOOOEOOOOOOEOOOLOOK",
        "KOOOOOOEOOOOOOEOOOOOOK",
        ".KOOOOOOOOOOOOOOOOOOOK.",
        "..KOOOOOOOWWWOOOOOOOK..",
        "...KOOOOOOWWWWWOOOOK...",
        "...KOOOOOOWWNWWOOOOK...",
        "....KOOOOOOWWWWOOOOK....",
        ".....KKKDDDDDDKKK......",
        "....KOOOOOOWWWOOOOOK....",
        "...KOOOOOOWWWWWOOOOOK...",
        "...KOOOOK....KOOOOK...",
        "....KKKK......KKKK....",
    ],
    "cat": [
        "........KK..KK........",
        ".......KGLKKLGK.......",
        "......KGGGKKGGGK......",
        ".....KGGGGGGGGGGK.....",
        "....KGGGGGGGGGGGGK....",
        "...KGGGGGGGGGGGGGGK...",
        "..KGGGGGEGGGEGGGGGK..",
        "..KGGGGGEGGGEGGGGGK..",
        "..KGGGGGGGGGGGGGGGK..",
        "...KGGPPNGNGNPPGGK...",
        "....KGGGGNGNGGGGK....",
        ".....KGGGGGGGGGK.....",
        "....KKKKKKKKKKKKK....",
        "...KGGGGGGGGGGGGGK...",
        "..KGGGGGGGGGGGGGGGK..",
        ".KGGGGGGGGGGGGGGGGGK.",
        ".KGGGKKGGGGGGKKGGGK.",
        "..KKKKK....KKKKK..",
    ],
}

NAMES = {"dog": "강아지", "cat": "고양이"}


def load_settings() -> dict:
    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return settings if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def load_pet() -> str | None:
    value = load_settings().get("pet")
    return value if value in SPRITES else None


def save_pet(pet: str) -> None:
    settings = load_settings()
    settings["pet"] = pet
    save_settings(settings)


def load_follow_mouse() -> bool:
    value = load_settings().get("follow_mouse", True)
    return value if isinstance(value, bool) else True


def save_follow_mouse(enabled: bool) -> None:
    settings = load_settings()
    settings["follow_mouse"] = enabled
    save_settings(settings)


class DesktopPet:
    def __init__(self, root: tk.Tk, pet: str):
        self.root = root
        self.pet = pet
        self.canvas: tk.Canvas | None = None
        self.sprite_items: list[int] = []
        self.x = 100.0
        self.y = 100.0
        self.dragging = False
        self.drag_offset_x = 0.0
        self.drag_offset_y = 0.0
        self.follow_offset_x = CANVAS_W / 2
        self.follow_offset_y = CANVAS_H / 2
        self.follow_mouse = load_follow_mouse()
        self.follow_var = tk.BooleanVar(root, value=self.follow_mouse)
        self.roam_dx = random.choice((-0.9, 0.9))
        self.roam_dy = random.choice((-0.45, 0.45))
        self.next_turn = time.monotonic() + random.uniform(2.0, 5.0)
        self.frame = 0
        self.action: str | None = None
        self.action_until = 0.0
        self.bubble = ""
        self.bubble_until = 0.0
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            self.root.configure(bg="#28354d")
        self.root.geometry(f"{CANVAS_W}x{CANVAS_H}+{int(self.x)}+{int(self.y)}")
        self.canvas = tk.Canvas(root, width=CANVAS_W, height=CANVAS_H, bg=TRANSPARENT,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.root.bind("<Button-3>", self.show_menu)
        self.root.bind("<Button-2>", self.show_menu)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.bind("<Control-Shift-Q>", lambda _event: self.root.destroy())
        self.menu = tk.Menu(self.root, tearoff=False, font=("Segoe UI", 10),
                            bg="#fffaf0", fg="#34323d", activebackground="#f4c6a2",
                            activeforeground="#34323d", borderwidth=0)
        self.menu.add_checkbutton(label="마우스 따라다니기", variable=self.follow_var,
                                  command=self.toggle_follow)
        self.menu.add_separator()
        self.menu.add_command(label="♡  쓰다듬기", command=lambda: self.interact("pet"))
        self.menu.add_command(label="✦  간식 주기", command=lambda: self.interact("treat"))
        self.menu.add_separator()
        self.menu.add_command(label="반려동물 바꾸기", command=self.choose_pet)
        self.menu.add_command(label="종료", command=self.root.destroy)
        self.canvas.bind("<Button-3>", self.show_menu)
        self.canvas.bind("<Button-2>", self.show_menu)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag_pet)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.draw()
        self.root.deiconify()
        self.root.after(500, self.tick)

    def show_menu(self, event: tk.Event) -> str:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()
        return "break"

    def toggle_follow(self) -> None:
        self.follow_mouse = bool(self.follow_var.get())
        save_follow_mouse(self.follow_mouse)
        self.bubble = "따라갈게!" if self.follow_mouse else "자유롭게 돌아다닐게!"
        self.bubble_until = time.monotonic() + 2.0

    def start_drag(self, event: tk.Event) -> str:
        self.dragging = True
        self.drag_offset_x = event.x_root - self.x
        self.drag_offset_y = event.y_root - self.y
        return "break"

    def drag_pet(self, event: tk.Event) -> str:
        if not self.dragging:
            return "break"
        max_x = max(0, self.root.winfo_screenwidth() - CANVAS_W)
        max_y = max(0, self.root.winfo_screenheight() - CANVAS_H)
        self.x = min(max(event.x_root - self.drag_offset_x, 0), max_x)
        self.y = min(max(event.y_root - self.drag_offset_y, 0), max_y)
        self.root.geometry(f"{CANVAS_W}x{CANVAS_H}+{int(self.x)}+{int(self.y)}")
        return "break"

    def stop_drag(self, event: tk.Event) -> str:
        if self.dragging:
            self.dragging = False
            if self.follow_mouse:
                # Keep the grabbed point under the pointer after the drop.
                self.follow_offset_x = event.x_root - self.x
                self.follow_offset_y = event.y_root - self.y
        return "break"

    def choose_pet(self) -> None:
        self.root.withdraw()
        selector = tk.Toplevel(self.root)
        selector.title("나의 작은 친구")
        selector.resizable(False, False)
        selector.configure(bg="#fffaf0")
        selector.attributes("-topmost", True)
        selector.protocol("WM_DELETE_WINDOW", lambda: self.close_selector(selector))
        body = tk.Frame(selector, bg="#fffaf0", padx=26, pady=22)
        body.pack()
        tk.Label(body, text="새 친구를 골라 주세요", bg="#fffaf0", fg="#383443",
                 font=("Malgun Gothic", 17, "bold")).pack(pady=(0, 5))
        tk.Label(body, text="언제든 우클릭 메뉴에서 바꿀 수 있어요.", bg="#fffaf0", fg="#77727e",
                 font=("Malgun Gothic", 9)).pack(pady=(0, 16))
        buttons = tk.Frame(body, bg="#fffaf0")
        buttons.pack()
        for kind, emoji, title, desc in (("dog", "🐶", "강아지", "꼬리를 흔들어요"),
                                         ("cat", "🐱", "고양이", "살금살금 움직여요")):
            card = tk.Button(buttons, text=f"{emoji}\n{title}\n{desc}", width=16, height=5,
                             bg="#f8eadc" if kind == "dog" else "#e8e9f3",
                             fg="#403b45", activebackground="#f5d4b6",
                             font=("Malgun Gothic", 11), relief="flat", bd=0,
                             command=lambda k=kind: self.set_pet(k, selector))
            card.pack(side="left", padx=6)
        selector.update_idletasks()
        selector.geometry(f"+{(selector.winfo_screenwidth()-selector.winfo_width())//2}+"
                          f"{(selector.winfo_screenheight()-selector.winfo_height())//2}")
        selector.grab_set()

    def close_selector(self, selector: tk.Toplevel) -> None:
        selector.destroy()
        if load_pet() is None:
            self.root.destroy()
        else:
            self.root.deiconify()

    def set_pet(self, pet: str, selector: tk.Toplevel | None = None) -> None:
        self.pet = pet
        save_pet(pet)
        if selector is not None:
            selector.destroy()
        self.action = None
        self.bubble = "새 친구가 왔어요!"
        self.bubble_until = time.monotonic() + 2.5
        self.draw()
        self.root.deiconify()

    def interact(self, action: str) -> None:
        self.action = action
        self.action_until = time.monotonic() + (2.3 if action == "pet" else 2.8)
        self.bubble = random.choice(("기분 좋아!", "고마워!", "좋아요!")) if action == "pet" else random.choice(("냠냠!", "맛있다!", "간식이다!") )
        self.bubble_until = self.action_until
        self.draw()

    def draw_sprite(self) -> None:
        assert self.canvas is not None
        palette = PALETTES[self.pet]
        width = max(25, max(map(len, SPRITES[self.pet])))
        rows = [list(row.center(width, ".")) for row in SPRITES[self.pet]]
        if self.pet == "cat":
            # Blink, knead the front paws, and curl the tail behind the body.
            if self.frame % 36 in (0, 1):
                for row in rows[6:8]:
                    row[:] = ["K" if pixel == "E" else pixel for pixel in row]
            if self.frame % 8 in (3, 4, 5):
                rows[17] = list(".KKKKK....KKKKK.".center(width, "."))
        else:
            # Blink, perk the floppy ears, step with the front paws, and peek out its tongue.
            if self.frame % 40 in (0, 1):
                for row in rows[6:8]:
                    row[:] = ["K" if pixel == "E" else pixel for pixel in row]
            if self.frame % 8 in (2, 3, 4):
                rows[0] = list(".......KKKKKK.......".center(width, "."))
            if self.frame % 6 in (3, 4, 5):
                rows[17] = list("..KKKKK......KKKKK..".center(width, "."))
            if self.action in ("pet", "treat") or self.frame % 8 in (0, 1, 2):
                rows[12][width // 2] = "P"
        sx = (CANVAS_W - width * SCALE) // 2
        bob = 2 if self.frame % 4 in (1, 2) else 0
        if self.action == "pet":
            bob -= 3 if self.frame % 2 else 0
        sy = 35 + bob
        tail_phase = (self.frame // 2) % 4
        if self.action in ("pet", "treat"):
            tail_phase = self.frame % 4
        tail_sway = (0, -1, 0, 1)[tail_phase]
        if self.pet == "cat":
            tail_outline = ((19, 13), (20, 13), (21, 12), (22, 11), (23, 11),
                            (24, 12), (24, 13), (23, 14), (22, 14), (21, 14))
            tail_fill = ((20, 13), (21, 13), (22, 12), (23, 12), (23, 13), (22, 13))
        else:
            tail_outline = ((20, 14), (21, 13), (22, 12), (23, 11), (24, 11),
                            (24, 12), (23, 13), (22, 14), (21, 15), (20, 15))
            tail_fill = ((21, 14), (22, 13), (23, 12), (23, 11))
        # Paint the curled tails first so their roots tuck behind each front-facing body.
        for gx, gy in tail_outline:
            y1 = sy + (gy + tail_sway) * SCALE
            x1 = sx + gx * SCALE
            self.canvas.create_rectangle(x1, y1, x1 + SCALE, y1 + SCALE,
                                         fill=palette["K"], outline=palette["K"])
        tail_color = palette["G"] if self.pet == "cat" else palette["O"]
        for gx, gy in tail_fill:
            y1 = sy + (gy + tail_sway) * SCALE
            x1 = sx + gx * SCALE
            self.canvas.create_rectangle(x1, y1, x1 + SCALE, y1 + SCALE,
                                         fill=tail_color, outline=tail_color)
        for j, row in enumerate(rows):
            for i, pixel in enumerate(row):
                color = palette.get(pixel)
                if color:
                    x1, y1 = sx + i * SCALE, sy + j * SCALE
                    self.canvas.create_rectangle(x1, y1, x1 + SCALE, y1 + SCALE,
                                                 fill=color, outline=color)

    def draw(self) -> None:
        assert self.canvas is not None
        self.canvas.delete("all")
        now = time.monotonic()
        if self.bubble and now < self.bubble_until:
            self.canvas.create_rectangle(38, 8, 138, 33, fill="#fffaf0", outline="#ead9c5", width=1)
            self.canvas.create_polygon(79, 32, 86, 32, 81, 38, fill="#fffaf0", outline="#ead9c5")
            self.canvas.create_text(88, 20, text=self.bubble, fill="#51424a",
                                    font=("Malgun Gothic", 9, "bold"))
        self.draw_sprite()
        if self.action == "pet" and now < self.action_until:
            for cx, cy in ((40, 67), (137, 74), (47, 122)):
                bob = int((self.frame % 5) * 2)
                self.canvas.create_text(cx, cy - bob, text="♥", fill="#ef8297",
                                        font=("Segoe UI", 15, "bold"))
        elif self.action == "treat" and now < self.action_until:
            self.canvas.create_oval(76, 132, 102, 144, fill="#e9bb79", outline="#8b6449", width=2)
            self.canvas.create_rectangle(84, 130, 94, 137, fill="#f4d69f", outline="#8b6449")
            self.canvas.create_oval(80, 127, 86, 133, fill="#f4d69f", outline="#8b6449")
            self.canvas.create_oval(92, 127, 98, 133, fill="#f4d69f", outline="#8b6449")
        if self.action == "pet" and now < self.action_until:
            # A blocky hand icon above the head is the dedicated stroking animation.
            self.canvas.create_text(115, 47, text="✋", fill="#eab28e", font=("Segoe UI Emoji", 15))

    def tick(self) -> None:
        if not self.root.winfo_exists():
            return
        now = time.monotonic()
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if self.action and now >= self.action_until:
            self.action = None
        # Follow the pointer or wander freely, keeping the pet fully on-screen.
        max_x = max(0, screen_w - CANVAS_W)
        max_y = max(0, screen_h - CANVAS_H)
        if not self.dragging and not self.menu.winfo_ismapped():
            if self.follow_mouse:
                target_x = min(max(self.root.winfo_pointerx() - self.follow_offset_x, 0), max_x)
                target_y = min(max(self.root.winfo_pointery() - self.follow_offset_y, 0), max_y)
                offset_x, offset_y = target_x - self.x, target_y - self.y
                distance = math.hypot(offset_x, offset_y)
                if distance > 1:
                    step = min(2.8, distance)
                    self.x += offset_x / distance * step
                    self.y += offset_y / distance * step
            else:
                if now >= self.next_turn:
                    self.roam_dx = random.choice((-1.1, -0.8, 0.8, 1.1))
                    self.roam_dy = random.choice((-0.6, -0.35, 0.35, 0.6))
                    self.next_turn = now + random.uniform(2.0, 5.0)
                self.x += self.roam_dx
                self.y += self.roam_dy
                if self.x < 0 or self.x > max_x:
                    self.roam_dx *= -1
                    self.x = min(max(self.x, 0), max_x)
                if self.y < 0 or self.y > max_y:
                    self.roam_dy *= -1
                    self.y = min(max(self.y, 0), max_y)
        self.root.geometry(f"{CANVAS_W}x{CANVAS_H}+{int(self.x)}+{int(self.y)}")
        self.frame += 1
        self.draw()
        self.root.after(90, self.tick)


def main() -> None:
    root = tk.Tk()
    root.title("나의 작은 친구")
    pet = load_pet()
    if pet is None:
        # Keep the root available while the first choice window is open.
        pet = "dog"
    app = DesktopPet(root, pet)
    if load_pet() is None:
        app.choose_pet()
    root.mainloop()


if __name__ == "__main__":
    main()
