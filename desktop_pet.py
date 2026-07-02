from __future__ import annotations

from datetime import datetime
from pathlib import Path
import random
import tkinter as tk
from dataclasses import dataclass
from typing import Dict, List

from PIL import ImageTk

from sprite_states import PetState, SpriteStateLibrary, build_default_library


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_DIALOGUE_PATH = ROOT_DIR / "assets" / "dialogues.txt"
TRANSPARENT_MASK = "#010101"
ANIMATION_INTERVAL_MS = 260
BEHAVIOR_TICK_MS = 50
WALK_STEP_PX = 4
GRAVITY_ACCELERATION_PX = 2
MAX_FALL_SPEED_PX = 16
FALL_IMPACT_MS = 60
FALL_SPLAT_MS = 300
CRAWL_FRAME_MS = 180
CRAWL_JUMP_PIXELS = 18
IDLE_TICK_RANGE = (28, 70)
WALK_TICK_RANGE = (26, 52)
PEEK_TICK_RANGE = (12, 24)
SPECIAL_IDLE_CHANCE = 0.12
WALK_CHANCE = 0.45
SPECIAL_WALK_CHANCE = 0.35
BUBBLE_BG = "#f3e5ab"
BUBBLE_FG = "#3a2f28"
BUBBLE_WRAP_PX = 280
BUBBLE_OFFSET_Y = 90
BUBBLE_DURATION_MS = 5200
BUBBLE_PAD_X = 14
BUBBLE_PAD_Y = 10
MOVE_EVERY_N_TICKS = 2
DRAG_SHAKE_THRESHOLD = 42


@dataclass
class DragContext:
    offset_x: int = 0
    offset_y: int = 0
    active: bool = False
    last_x_root: int = 0
    last_y_root: int = 0


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def compute_floor_y(screen_height: int, sprite_height: int) -> int:
    return max(0, screen_height - sprite_height)


def load_dialogues(dialogue_path: Path) -> Dict[str, str]:
    if not dialogue_path.exists():
        return {}

    lines = [line.rstrip() for line in dialogue_path.read_text(encoding="utf-8").splitlines()]
    dialogues: Dict[str, str] = {}
    index = 0

    while index < len(lines):
        title = lines[index].strip()
        index += 1

        if not title:
            continue

        while index < len(lines) and not lines[index].strip():
            index += 1

        if index >= len(lines):
            break

        body = lines[index].strip()
        index += 1
        dialogues[title] = body

    return dialogues


class ChibiHuTaoDesktopPet:
    def __init__(
        self,
        library: SpriteStateLibrary | None = None,
        dialogue_path: Path = DEFAULT_DIALOGUE_PATH,
    ) -> None:
        self.library = library or build_default_library()
        self.root = tk.Tk()
        self.root.title("Chibi Hu Tao Desktop Pet")

        self.drag = DragContext()
        self.behavior_enabled = True
        self.behavior_after_id: str | None = None
        self.animation_after_id: str | None = None
        self.pending_after_ids: List[str] = []
        self.animation_paused = False
        self.current_state = PetState.SIT_HAPPY
        self.frame_index = 0
        self.position_x = 120
        self.position_y = 120
        self.gravity_active = False
        self.vertical_velocity = 0
        self.facing_right = True
        self.state_ticks_remaining = random.randint(*IDLE_TICK_RANGE)
        self.peek_ticks_remaining = 0
        self.move_tick_counter = 0
        self.dialogues = load_dialogues(dialogue_path)
        self.dialogue_window: tk.Toplevel | None = None
        self.dialogue_after_id: str | None = None
        self.dialogue_label: tk.Label | None = None
        self.last_dialogue_key: str | None = None

        self.photo_cache = self._build_photo_cache()
        self.max_frame_width, self.max_frame_height = self._get_max_frame_size()

        self._configure_window()
        self.canvas = tk.Canvas(
            self.root,
            width=self.max_frame_width,
            height=self.max_frame_height,
            bg=TRANSPARENT_MASK,
            bd=0,
            highlightthickness=0,
        )
        self.canvas.pack()
        self.sprite_item = self.canvas.create_image(0, 0, anchor="nw")

        self._bind_events()
        self._move_window(self.position_x, self.position_y)
        self._render_current_frame()
        self._schedule_animation_tick()
        self._schedule_behavior_tick()

    def _build_photo_cache(self) -> Dict[PetState, Dict[bool, List[ImageTk.PhotoImage]]]:
        cache: Dict[PetState, Dict[bool, List[ImageTk.PhotoImage]]] = {}
        for state in PetState:
            config = self.library.get_state_config(state)
            normal = self.library.get_state_sprites(state, directional_mirror=False)
            mirrored = (
                self.library.get_state_sprites(state, directional_mirror=True)
                if config.directional_flip or config.mirror_x
                else normal
            )
            cache[state] = {False: normal, True: mirrored}
        return cache

    def _get_max_frame_size(self) -> tuple[int, int]:
        widths = []
        heights = []
        for state in PetState:
            for image in self.library.get_state_images(state):
                widths.append(image.width)
                heights.append(image.height)
        return max(widths), max(heights)

    def _configure_window(self) -> None:
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_MASK)
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT_MASK)
        except tk.TclError:
            pass

    def _bind_events(self) -> None:
        for widget in (self.root, self.canvas):
            widget.bind("<Button-1>", self.on_mouse_down)
            widget.bind("<B1-Motion>", self.on_mouse_drag)
            widget.bind("<ButtonRelease-1>", self.on_mouse_up)

    def _get_floor_y(self) -> int:
        return compute_floor_y(self.root.winfo_screenheight(), self.max_frame_height)

    def _get_max_x(self) -> int:
        return max(0, self.root.winfo_screenwidth() - self.max_frame_width)

    def _cancel_pending_sequences(self) -> None:
        for after_id in self.pending_after_ids:
            self.root.after_cancel(after_id)
        self.pending_after_ids.clear()
        self.animation_paused = False

    def _queue_after(self, delay_ms: int, callback) -> None:
        after_id = self.root.after(delay_ms, callback)
        self.pending_after_ids.append(after_id)

    def destroy_dialogue_bubble(self) -> None:
        if self.dialogue_after_id is not None:
            self.root.after_cancel(self.dialogue_after_id)
            self.dialogue_after_id = None
        if self.dialogue_window is not None:
            self.dialogue_window.destroy()
            self.dialogue_window = None
            self.dialogue_label = None

    def _position_dialogue_bubble(self) -> None:
        if self.dialogue_window is None:
            return
        bubble_x = clamp(
            self.position_x + max(0, (self.max_frame_width // 2) - 120),
            0,
            self.root.winfo_screenwidth(),
        )
        bubble_y = max(0, self.position_y - BUBBLE_OFFSET_Y)
        self.dialogue_window.geometry(f"+{bubble_x}+{bubble_y}")

    def show_dialogue_bubble(self, text: str, duration_ms: int = BUBBLE_DURATION_MS) -> None:
        self.destroy_dialogue_bubble()
        self.dialogue_window = tk.Toplevel(self.root)
        self.dialogue_window.overrideredirect(True)
        self.dialogue_window.wm_attributes("-topmost", True)
        self.dialogue_window.configure(bg=BUBBLE_BG, padx=2, pady=2)

        container = tk.Frame(
            self.dialogue_window,
            bg=BUBBLE_BG,
            highlightbackground=BUBBLE_FG,
            highlightthickness=2,
            bd=0,
        )
        container.pack()
        self.dialogue_label = tk.Label(
            container,
            text=text,
            bg=BUBBLE_BG,
            fg=BUBBLE_FG,
            font=("Segoe UI", 10, "bold"),
            justify="left",
            wraplength=BUBBLE_WRAP_PX,
            padx=BUBBLE_PAD_X,
            pady=BUBBLE_PAD_Y,
        )
        self.dialogue_label.pack()
        self._position_dialogue_bubble()
        self.dialogue_after_id = self.root.after(duration_ms, self.destroy_dialogue_bubble)

    def _pick_dialogue(self, keys: List[str]) -> str | None:
        available = [key for key in keys if key in self.dialogues]
        if not available:
            return None
        choices = [key for key in available if key != self.last_dialogue_key]
        selected_key = random.choice(choices or available)
        self.last_dialogue_key = selected_key
        return self.dialogues[selected_key]

    def _pick_contextual_idle_dialogue(self) -> str | None:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return self.dialogues.get("Good Morning")
        if 12 <= hour < 17:
            return self.dialogues.get("Good Afternoon")
        if 17 <= hour < 21:
            return self.dialogues.get("Good Evening")
        return self.dialogues.get("Good Night")

    def _show_celebration_dialogue(self) -> None:
        quote = self._pick_dialogue(
            [
                "Birthday",
                "About Us: Helper",
                "Hu Tao's Hobbies",
                "Favorite Food",
                "Hu Tao's Troubles",
            ]
        )
        if quote:
            self.show_dialogue_bubble(quote)

    def _should_mirror_current_state(self) -> bool:
        return self.facing_right and self.library.get_state_config(self.current_state).directional_flip

    def _reset_state_timer(self, state: PetState) -> None:
        if state in (PetState.WALK_NORMAL, PetState.WALK_SPECIAL):
            self.state_ticks_remaining = random.randint(*WALK_TICK_RANGE)
        elif state == PetState.EDGE_PEEK:
            self.peek_ticks_remaining = random.randint(*PEEK_TICK_RANGE)
            self.state_ticks_remaining = self.peek_ticks_remaining
        else:
            self.state_ticks_remaining = random.randint(*IDLE_TICK_RANGE)

    def _move_window(self, x: int, y: int) -> None:
        self.position_x = clamp(x, 0, self._get_max_x())
        self.position_y = clamp(y, 0, self._get_floor_y())
        self.root.geometry(
            f"{self.max_frame_width}x{self.max_frame_height}+{self.position_x}+{self.position_y}"
        )
        self._position_dialogue_bubble()

    def _render_current_frame(self) -> None:
        frames = self.photo_cache[self.current_state][self._should_mirror_current_state()]
        frame = frames[self.frame_index % len(frames)]
        self.canvas.itemconfigure(self.sprite_item, image=frame)
        self.canvas.image = frame

    def _set_state(self, state: PetState, keep_dialogue: bool = False) -> None:
        if self.current_state == state:
            return
        if not keep_dialogue:
            self.destroy_dialogue_bubble()
        self.current_state = state
        self.frame_index = 0
        if state == PetState.EDGE_PEEK:
            self.peek_ticks_remaining = random.randint(*PEEK_TICK_RANGE)
        self._render_current_frame()
        if state == PetState.CELEBRATION_BUTTERFLY:
            self._show_celebration_dialogue()

    def _schedule_animation_tick(self) -> None:
        if self.animation_after_id is not None:
            self.root.after_cancel(self.animation_after_id)
        self.animation_after_id = self.root.after(ANIMATION_INTERVAL_MS, self._animation_tick)

    def _animation_tick(self) -> None:
        if not self.animation_paused:
            frames = self.photo_cache[self.current_state][self._should_mirror_current_state()]
            self.frame_index = (self.frame_index + 1) % len(frames)
            self._render_current_frame()
        self._schedule_animation_tick()

    def _schedule_behavior_tick(self) -> None:
        if self.behavior_after_id is not None:
            self.root.after_cancel(self.behavior_after_id)
        self.behavior_after_id = self.root.after(BEHAVIOR_TICK_MS, self._behavior_tick)

    def _behavior_tick(self) -> None:
        if self.drag.active:
            self._schedule_behavior_tick()
            return
        if self.gravity_active:
            self._update_fall()
        elif self.behavior_enabled:
            self._update_autonomous_behavior()
        self._schedule_behavior_tick()

    def pause_behavior(self) -> None:
        self.behavior_enabled = False

    def resume_behavior(self) -> None:
        self.behavior_enabled = True
        if self.current_state not in (PetState.WALK_NORMAL, PetState.WALK_SPECIAL, PetState.EDGE_PEEK):
            self._reset_state_timer(PetState.SIT_HAPPY)

    def _update_fall(self) -> None:
        floor_y = self._get_floor_y()
        if self.position_y >= floor_y:
            self._handle_floor_impact()
            return

        self.vertical_velocity = min(
            self.vertical_velocity + GRAVITY_ACCELERATION_PX,
            MAX_FALL_SPEED_PX,
        )
        next_y = min(self.position_y + self.vertical_velocity, floor_y)
        self._move_window(self.position_x, next_y)

        if next_y >= floor_y:
            self._handle_floor_impact()

    def _handle_floor_impact(self) -> None:
        self.gravity_active = False
        self.vertical_velocity = 0
        self._move_window(self.position_x, self._get_floor_y())
        self._cancel_pending_sequences()
        self.animation_paused = True
        self._set_state(PetState.FALL_IMPACT)
        self._queue_after(FALL_IMPACT_MS, self._enter_fall_splat)

    def _enter_fall_splat(self) -> None:
        self.pending_after_ids.pop(0)
        self._set_state(PetState.FALL_SPLAT)
        self._queue_after(FALL_SPLAT_MS, self._start_crawl_recovery)

    def _start_crawl_recovery(self) -> None:
        self.pending_after_ids.pop(0)
        self._set_state(PetState.CRAWL_RECOVERY)
        self.frame_index = 0
        self._render_current_frame()
        self._queue_after(CRAWL_FRAME_MS, self._crawl_recovery_frame_one)

    def _crawl_recovery_frame_one(self) -> None:
        self.pending_after_ids.pop(0)
        self.frame_index = 1
        self._render_current_frame()
        self._queue_after(CRAWL_FRAME_MS, self._crawl_recovery_frame_two)

    def _crawl_recovery_frame_two(self) -> None:
        self.pending_after_ids.pop(0)
        self.frame_index = 2
        self._render_current_frame()
        self._move_window(self.position_x, max(0, self.position_y - CRAWL_JUMP_PIXELS))
        self._queue_after(80, self._complete_crawl_recovery)

    def _complete_crawl_recovery(self) -> None:
        self.pending_after_ids.pop(0)
        self._move_window(self.position_x, self._get_floor_y())
        self.animation_paused = False
        self.behavior_enabled = True
        self._enter_walk_state(special=False)

    def _choose_walk_style(self) -> PetState:
        if random.random() < SPECIAL_WALK_CHANCE:
            return PetState.WALK_SPECIAL
        return PetState.WALK_NORMAL

    def _enter_walk_state(self, special: bool | None = None) -> None:
        self.move_tick_counter = 0
        target_state = (
            self._choose_walk_style()
            if special is None
            else (PetState.WALK_SPECIAL if special else PetState.WALK_NORMAL)
        )
        self._set_state(target_state)
        self._reset_state_timer(target_state)

    def _set_facing_from_position(self) -> None:
        if self.position_x <= 0:
            self.facing_right = True
        elif self.position_x >= self._get_max_x():
            self.facing_right = False

    def _choose_next_idle_state(self) -> None:
        roll = random.random()
        if roll < SPECIAL_IDLE_CHANCE:
            self._set_state(PetState.CELEBRATION_BUTTERFLY)
            self._reset_state_timer(PetState.CELEBRATION_BUTTERFLY)
            return

        if roll < SPECIAL_IDLE_CHANCE + WALK_CHANCE:
            self._set_facing_from_position()
            if 0 < self.position_x < self._get_max_x():
                self.facing_right = random.choice((True, False))
            self._enter_walk_state()
            return

        idle_state = random.choice(
            (
                PetState.SIT_HAPPY,
                PetState.SIT_COZY_A,
                PetState.SIT_COZY_B,
                PetState.LOOK_UP_IDLE,
            )
        )
        self._set_state(idle_state)
        self._reset_state_timer(idle_state)
        if random.random() < 0.2:
            idle_quote = self._pick_contextual_idle_dialogue()
            if idle_quote:
                self.show_dialogue_bubble(idle_quote, duration_ms=4200)

    def _update_edge_peek(self) -> None:
        self.peek_ticks_remaining -= 1
        if self.peek_ticks_remaining > 0:
            return
        self.facing_right = self.position_x <= 0
        self._enter_walk_state(special=False)

    def _advance_walk(self) -> None:
        self.move_tick_counter = (self.move_tick_counter + 1) % MOVE_EVERY_N_TICKS
        self.state_ticks_remaining -= 1
        if self.move_tick_counter != 0:
            if self.state_ticks_remaining <= 0:
                self._choose_next_idle_state()
            return

        step = WALK_STEP_PX if self.facing_right else -WALK_STEP_PX
        target_x = self.position_x + step
        max_x = self._get_max_x()

        if target_x <= 0 or target_x >= max_x:
            self._move_window(clamp(target_x, 0, max_x), self.position_y)
            self.facing_right = self.position_x <= 0
            self._set_state(PetState.EDGE_PEEK)
            self._reset_state_timer(PetState.EDGE_PEEK)
            return

        self._move_window(target_x, self.position_y)
        if self.state_ticks_remaining <= 0:
            self._choose_next_idle_state()

    def _update_autonomous_behavior(self) -> None:
        if self.current_state == PetState.EDGE_PEEK:
            self._update_edge_peek()
            return

        if self.current_state in (PetState.WALK_NORMAL, PetState.WALK_SPECIAL):
            self._advance_walk()
            return

        self.state_ticks_remaining -= 1
        if self.state_ticks_remaining <= 0:
            self._choose_next_idle_state()

    def _begin_fall(self) -> None:
        self.gravity_active = True
        self.vertical_velocity = 0
        self.behavior_enabled = False
        self.animation_paused = False
        self._set_state(PetState.FALL_START)

    def on_mouse_down(self, event: tk.Event) -> None:
        self.drag.active = True
        self.drag.offset_x = event.x_root - self.root.winfo_x()
        self.drag.offset_y = event.y_root - self.root.winfo_y()
        self.drag.last_x_root = event.x_root
        self.drag.last_y_root = event.y_root
        self.gravity_active = False
        self.vertical_velocity = 0
        self._cancel_pending_sequences()
        self.pause_behavior()
        self._set_state(PetState.DRAG_HELD)

    def on_mouse_drag(self, event: tk.Event) -> None:
        if not self.drag.active:
            return

        delta_x = event.x_root - self.drag.last_x_root
        delta_y = event.y_root - self.drag.last_y_root
        self.drag.last_x_root = event.x_root
        self.drag.last_y_root = event.y_root

        new_x = event.x_root - self.drag.offset_x
        new_y = event.y_root - self.drag.offset_y
        self._move_window(new_x, new_y)
        self.facing_right = delta_x >= 0

        if abs(delta_x) + abs(delta_y) >= DRAG_SHAKE_THRESHOLD:
            self._set_state(PetState.DIZZY_SHAKING)
        else:
            self._set_state(PetState.DRAG_HELD)

    def on_mouse_up(self, _event: tk.Event) -> None:
        if not self.drag.active:
            return
        self.drag.active = False
        if self.position_y < self._get_floor_y():
            self._begin_fall()
            return
        self._set_state(PetState.SIT_HAPPY)
        self.resume_behavior()

    def trigger_birthday_dialogue(self) -> None:
        birthday_quote = self.dialogues.get("Birthday")
        self._set_state(PetState.CELEBRATION_BUTTERFLY, keep_dialogue=True)
        self._reset_state_timer(PetState.CELEBRATION_BUTTERFLY)
        if birthday_quote:
            self.show_dialogue_bubble(birthday_quote, duration_ms=6500)

    def shutdown(self) -> None:
        self._cancel_pending_sequences()
        self.destroy_dialogue_bubble()
        self.root.destroy()

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
        self.root.mainloop()


def main() -> None:
    app = ChibiHuTaoDesktopPet()
    app.run()


if __name__ == "__main__":
    main()
