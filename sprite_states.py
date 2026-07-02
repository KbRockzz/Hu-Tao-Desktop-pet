from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Dict, Iterable, List, Tuple

from PIL import Image, ImageOps, ImageTk

from asset_manager import ASSETS_DIR, AssetManager, find_default_asset


SpriteCell = Tuple[int, int]


class PetState(StrEnum):
    WALK_NORMAL = "WALK_NORMAL"
    WALK_SPECIAL = "WALK_SPECIAL"
    CRAWL_RECOVERY = "CRAWL_RECOVERY"
    WALL_CLIMB = "WALL_CLIMB"
    DRAG_HELD = "DRAG_HELD"
    DIZZY_SHAKING = "DIZZY_SHAKING"
    FALL_START = "FALL_START"
    FALL_IMPACT = "FALL_IMPACT"
    FALL_SPLAT = "FALL_SPLAT"
    SIT_HAPPY = "SIT_HAPPY"
    SIT_COZY_A = "SIT_COZY_A"
    SIT_COZY_B = "SIT_COZY_B"
    CELEBRATION_BUTTERFLY = "CELEBRATION_BUTTERFLY"
    EDGE_PEEK = "EDGE_PEEK"
    LOOK_UP_IDLE = "LOOK_UP_IDLE"


@dataclass(frozen=True)
class StateConfig:
    state: PetState
    cells: Tuple[SpriteCell, ...]
    behavioral_context: str
    mirror_x: bool = False
    directional_flip: bool = False


def _range_cells(row: int, start_col: int, end_col: int) -> Tuple[SpriteCell, ...]:
    return tuple((row, col) for col in range(start_col, end_col + 1))


def _cells(*positions: SpriteCell) -> Tuple[SpriteCell, ...]:
    return tuple(positions)


STATE_CONFIGS: Dict[PetState, StateConfig] = {
    PetState.WALK_NORMAL: StateConfig(
        state=PetState.WALK_NORMAL,
        cells=_range_cells(0, 0, 2),
        behavioral_context="Standard horizontal pacing along the taskbar or window tops.",
        directional_flip=True,
    ),
    PetState.WALK_SPECIAL: StateConfig(
        state=PetState.WALK_SPECIAL,
        cells=_cells((1, 5), (2, 0), (2, 1)),
        behavioral_context="Sneaky tiptoe march variation.",
        directional_flip=True,
    ),
    PetState.CRAWL_RECOVERY: StateConfig(
        state=PetState.CRAWL_RECOVERY,
        cells=_cells((3, 1), (3, 2), (3, 3)),
        behavioral_context="Crawl recovery that ends with a push-off jump back to standing.",
        directional_flip=True,
    ),
    PetState.WALL_CLIMB: StateConfig(
        state=PetState.WALL_CLIMB,
        cells=_cells((3, 4), (3, 5), (4, 0)),
        behavioral_context="Vertical climbing loop for active application borders.",
    ),
    PetState.DRAG_HELD: StateConfig(
        state=PetState.DRAG_HELD,
        cells=_cells((0, 4), (1, 0)),
        behavioral_context="Flailing loop played while the user actively drags her.",
    ),
    PetState.DIZZY_SHAKING: StateConfig(
        state=PetState.DIZZY_SHAKING,
        cells=_cells((1, 1), (1, 2), (1, 3)),
        behavioral_context="Triggered if the cursor shakes the widget violently.",
    ),
    PetState.FALL_START: StateConfig(
        state=PetState.FALL_START,
        cells=_cells((0, 3)),
        behavioral_context="Single-frame pose triggered the instant she is released mid-air.",
    ),
    PetState.FALL_IMPACT: StateConfig(
        state=PetState.FALL_IMPACT,
        cells=_cells((2, 5)),
        behavioral_context="High-velocity impact frame flashed on collision.",
    ),
    PetState.FALL_SPLAT: StateConfig(
        state=PetState.FALL_SPLAT,
        cells=_cells((3, 0)),
        behavioral_context="Flat face-plant frame after impact.",
        directional_flip=True,
    ),
    PetState.SIT_HAPPY: StateConfig(
        state=PetState.SIT_HAPPY,
        cells=_cells((4, 1), (4, 2), (4, 3), (4, 4)),
        behavioral_context="Plops down, sits upright, blinks, and smiles.",
    ),
    PetState.SIT_COZY_A: StateConfig(
        state=PetState.SIT_COZY_A,
        cells=_cells((1, 4)),
        behavioral_context="Single-frame look-away resting pose.",
    ),
    PetState.SIT_COZY_B: StateConfig(
        state=PetState.SIT_COZY_B,
        cells=_cells((4, 5)),
        behavioral_context="Single-frame alternate resting pose.",
    ),
    PetState.CELEBRATION_BUTTERFLY: StateConfig(
        state=PetState.CELEBRATION_BUTTERFLY,
        cells=_range_cells(5, 0, 2),
        behavioral_context="Birthday or click celebration with floating butterflies.",
    ),
    PetState.EDGE_PEEK: StateConfig(
        state=PetState.EDGE_PEEK,
        cells=_range_cells(5, 3, 5),
        behavioral_context="Peeking interaction while tucked against a monitor edge.",
        directional_flip=True,
    ),
    PetState.LOOK_UP_IDLE: StateConfig(
        state=PetState.LOOK_UP_IDLE,
        cells=_cells((2, 2), (2, 3), (2, 4)),
        behavioral_context="Supplementary upward-looking idle transition.",
    ),
}


class SpriteStateLibrary:
    def __init__(self, asset_manager: AssetManager) -> None:
        self.asset_manager = asset_manager

    def get_state_config(self, state: PetState | str) -> StateConfig:
        normalized_state = PetState(state)
        return STATE_CONFIGS[normalized_state]

    def get_state_cells(self, state: PetState | str) -> Tuple[SpriteCell, ...]:
        return self.get_state_config(state).cells

    def get_state_images(
        self,
        state: PetState | str,
        directional_mirror: bool = False,
    ) -> List[Image.Image]:
        config = self.get_state_config(state)
        images = [
            self.asset_manager.get_cell_image(row, col)
            for row, col in config.cells
        ]
        if config.mirror_x or (config.directional_flip and directional_mirror):
            return [ImageOps.mirror(image) for image in images]
        return images

    def get_state_sprites(
        self,
        state: PetState | str,
        directional_mirror: bool = False,
    ) -> List[ImageTk.PhotoImage]:
        return [
            ImageTk.PhotoImage(image)
            for image in self.get_state_images(state, directional_mirror=directional_mirror)
        ]

    def iter_state_summary(self) -> Iterable[str]:
        for state, config in STATE_CONFIGS.items():
            cell_summary = ", ".join(f"({row},{col})" for row, col in config.cells)
            mirror_note = " mirrored" if config.mirror_x else ""
            yield (
                f"{state}: [{cell_summary}] | frames={len(config.cells)}"
                f"{mirror_note} | {config.behavioral_context}"
            )


def build_default_library() -> SpriteStateLibrary:
    asset_manager = AssetManager(find_default_asset(ASSETS_DIR))
    return SpriteStateLibrary(asset_manager)


def main() -> None:
    library = build_default_library()

    print("Phase 2 sprite mapping summary")
    for line in library.iter_state_summary():
        print(line)

    sample_state = PetState.SIT_HAPPY
    sample_boxes = [
        library.asset_manager.get_cell_box(row, col)
        for row, col in library.get_state_cells(sample_state)
    ]
    print(f"{sample_state} boxes: {sample_boxes}")


if __name__ == "__main__":
    main()
