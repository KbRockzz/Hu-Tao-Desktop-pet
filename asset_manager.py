from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(
        "Pillow is required to run asset_manager.py. Install it with: pip install pillow"
    ) from exc


ROOT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "assets"
DEFAULT_PATTERN = "Hu Tao mascot*"
OUTPUT_DIR = ASSETS_DIR / "debug_output"
TRANSPARENT_SHEET_NAME = "hu_tao_rgba.png"
DEBUG_GRID_NAME = "hu_tao_debug_grid.png"
SPRITE_SIZE = 100

# The original sheet is 600x600 and contains 36 sprites arranged as a 6x6 grid
# of exact 100x100 cells.
GRID_COLS = 6
GRID_ROWS = 6


class AssetManager:
    def __init__(
        self,
        asset_path: Path,
        output_dir: Path = OUTPUT_DIR,
        cols: int = GRID_COLS,
        rows: int = GRID_ROWS,
        white_threshold: int = 240,
    ) -> None:
        self.asset_path = asset_path
        self.output_dir = output_dir
        self.cols = cols
        self.rows = rows
        self.white_threshold = white_threshold

        self.source_image = Image.open(self.asset_path).convert("RGBA")
        self.rgba_image = self._apply_white_to_alpha(self.source_image)
        self._sprite_cache: Dict[Tuple[int, int], Image.Image] = {}
        self._validate_sheet_dimensions()

    def _validate_sheet_dimensions(self) -> None:
        width, height = self.source_image.size
        expected_width = self.cols * SPRITE_SIZE
        expected_height = self.rows * SPRITE_SIZE
        if width != expected_width or height != expected_height:
            raise ValueError(
                "Unexpected sprite sheet dimensions: "
                f"got {width}x{height}, expected {expected_width}x{expected_height}"
            )

    def _apply_white_to_alpha(self, image: Image.Image) -> Image.Image:
        processed = image.copy()
        pixels = []

        for red, green, blue, alpha in processed.getdata():
            if red > self.white_threshold and green > self.white_threshold and blue > self.white_threshold:
                pixels.append((red, green, blue, 0))
            else:
                pixels.append((red, green, blue, alpha))

        processed.putdata(pixels)
        return processed

    def get_cell_box(self, row: int, col: int) -> Tuple[int, int, int, int]:
        if not 0 <= row < self.rows:
            raise IndexError(f"row {row} out of range 0-{self.rows - 1}")
        if not 0 <= col < self.cols:
            raise IndexError(f"col {col} out of range 0-{self.cols - 1}")

        left = col * SPRITE_SIZE
        upper = row * SPRITE_SIZE
        right = left + SPRITE_SIZE
        lower = upper + SPRITE_SIZE
        return left, upper, right, lower

    def get_cell_image(self, row: int, col: int) -> Image.Image:
        key = (row, col)
        if key not in self._sprite_cache:
            self._sprite_cache[key] = self.rgba_image.crop(self.get_cell_box(row, col))
        return self._sprite_cache[key]

    def get_sprite(self, row: int, col: int) -> ImageTk.PhotoImage:
        return ImageTk.PhotoImage(self.get_cell_image(row, col))

    def save_processed_sheet(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / TRANSPARENT_SHEET_NAME
        self.rgba_image.save(destination)
        return destination

    def export_slices(self) -> list[Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        exported_paths: list[Path] = []

        for existing_slice in self.output_dir.glob("sprite_r*_c*.png"):
            existing_slice.unlink()

        for row in range(self.rows):
            for col in range(self.cols):
                slice_path = self.output_dir / f"sprite_r{row}_c{col}.png"
                self.get_cell_image(row, col).save(slice_path)
                exported_paths.append(slice_path)

        return exported_paths

    def export_debug_grid(self, margin: int = 12, label_height: int = 18) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        cell_widths = []
        cell_heights = []
        for col in range(self.cols):
            left, _, right, _ = self.get_cell_box(0, col)
            cell_widths.append(right - left)
        for row in range(self.rows):
            _, upper, _, lower = self.get_cell_box(row, 0)
            cell_heights.append(lower - upper)

        max_cell_width = max(cell_widths)
        max_cell_height = max(cell_heights)
        canvas_width = margin + self.cols * (max_cell_width + margin)
        canvas_height = margin + self.rows * (max_cell_height + label_height + margin)

        debug_image = Image.new("RGBA", (canvas_width, canvas_height), (32, 24, 24, 255))
        draw = ImageDraw.Draw(debug_image)

        for row in range(self.rows):
            for col in range(self.cols):
                sprite = self.get_cell_image(row, col)
                x = margin + col * (max_cell_width + margin)
                y = margin + row * (max_cell_height + label_height + margin)
                debug_image.alpha_composite(sprite, (x, y))
                draw.rectangle(
                    (x - 1, y - 1, x + sprite.width, y + sprite.height),
                    outline=(243, 229, 171, 255),
                    width=1,
                )
                draw.text((x, y + max_cell_height + 2), f"r{row} c{col}", fill=(243, 229, 171, 255))

        debug_path = self.output_dir / DEBUG_GRID_NAME
        debug_image.save(debug_path)
        return debug_path


def find_default_asset(assets_dir: Path) -> Path:
    candidates = sorted(path for path in assets_dir.glob(DEFAULT_PATTERN) if path.is_file())
    if not candidates:
        raise FileNotFoundError(
            f"No asset matching '{DEFAULT_PATTERN}' was found in {assets_dir}"
        )
    return candidates[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Hu Tao sprite-sheet assets and export debug slices."
    )
    parser.add_argument(
        "--asset",
        type=Path,
        default=find_default_asset(ASSETS_DIR),
        help="Path to the source sprite-sheet image.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory where processed outputs are written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manager = AssetManager(asset_path=args.asset, output_dir=args.output_dir)

    processed_path = manager.save_processed_sheet()
    slice_paths = manager.export_slices()
    debug_grid_path = manager.export_debug_grid()

    print(f"Loaded asset: {args.asset}")
    print(f"Grid layout: {manager.cols} columns x {manager.rows} rows")
    print(f"Source size: {manager.rgba_image.size[0]}x{manager.rgba_image.size[1]}")
    print(f"Processed sheet: {processed_path}")
    print(f"Exported slices: {len(slice_paths)}")
    print(f"Debug grid: {debug_grid_path}")

    sample_box = manager.get_cell_box(0, 0)
    print(f"Sample cell box row=0 col=0: {sample_box}")


if __name__ == "__main__":
    main()
