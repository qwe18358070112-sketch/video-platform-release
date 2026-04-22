from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from PIL import ImageGrab

from admin_utils import current_integrity_level
from common import load_config
from controller import Controller
from grid_mapper import GridMapper
from logger_setup import setup_logger
from native_runtime_client import NativeRuntimeClient
from window_manager import WindowManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Single-cell elevated smoke probe for the Infovision client.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--mode", choices=["auto", "windowed", "fullscreen"], default="auto")
    parser.add_argument("--layout", type=int, choices=[4, 6, 9, 12], help="Override grid.layout for this probe only.")
    parser.add_argument("--cell-index", type=int, default=1, help="Zero-based cell index to exercise.")
    parser.add_argument("--dwell-seconds", type=float, default=1.5, help="Probe dwell time between zoom in and zoom out.")
    parser.add_argument("--output-dir", default="tmp/elevated_probe", help="Directory for screenshots and metadata.")
    return parser.parse_args()


def save_client_capture(path: Path, bbox: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=bbox).save(path)


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    logger = setup_logger(config.logging, config.path.parent)
    native_client = NativeRuntimeClient(config.path.parent, config.window, logger) if config.window.native_runtime_enabled else None
    window_manager = WindowManager(config.window, logger, native_client=native_client)
    controller = Controller(
        config.timing,
        logger,
        backend=config.window.control_backend,
        autohotkey_path=config.window.autohotkey_path,
        native_client=native_client,
    )
    grid_mapper = GridMapper(config.grid)

    try:
        window_info = window_manager.find_target_window()
        current_integrity = current_integrity_level()
        if current_integrity.rid < window_info.integrity_rid:
            raise SystemExit(
                f"Probe integrity {current_integrity.label} is lower than target {window_info.integrity_label}. Run elevated."
            )

        requested_mode = args.mode if args.mode != "auto" else config.profiles.active_mode
        active_mode = window_manager.detect_mode(window_info, requested_mode)
        preview_rect = getattr(config.profiles, active_mode).to_rect(window_info.client_rect)
        active_layout = int(args.layout or config.grid.layout)
        cells = grid_mapper.build_cells(preview_rect, active_layout)
        if not cells:
            raise SystemExit("No cells were generated from the current calibration profile.")

        target_cell = cells[args.cell_index % len(cells)]
        output_dir = (config.path.parent / args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        zoom_out_point = preview_rect.center
        metadata = {
            "integrity": current_integrity.label,
            "target_integrity": window_info.integrity_label,
            "hwnd": window_info.hwnd,
            "process_id": window_info.process_id,
            "mode": active_mode,
            "layout": active_layout,
            "preview_rect": preview_rect.to_bbox(),
            "cell_index": target_cell.index,
            "select_point": target_cell.select_point,
            "zoom_point": target_cell.zoom_point,
            "zoom_out_point": zoom_out_point,
        }

        window_manager.focus_window(window_info.hwnd)
        time.sleep(config.timing.focus_delay_ms / 1000.0)

        save_client_capture(output_dir / "00_before.png", window_info.client_rect.to_bbox())
        controller.click_once(
            target_cell.select_point,
            hwnd=window_info.hwnd,
            client_origin=(window_info.client_rect.left, window_info.client_rect.top),
            action_type="smoke_select",
        )
        time.sleep(config.timing.select_settle_ms / 1000.0)
        save_client_capture(output_dir / "01_after_single_click.png", window_info.client_rect.to_bbox())

        # 放大要打在当前格子的放大点，避免把“选中点”和“放大点”混为一谈。
        controller.double_click(
            target_cell.zoom_point,
            hwnd=window_info.hwnd,
            client_origin=(window_info.client_rect.left, window_info.client_rect.top),
            action_type="smoke_zoom_in",
        )
        time.sleep(args.dwell_seconds)
        save_client_capture(output_dir / "02_after_double_click.png", window_info.client_rect.to_bbox())

        # 返回宫格优先打预览中心，和主调度保持一致，避免在已放大界面误打回原小格位置。
        controller.double_click(
            zoom_out_point,
            hwnd=window_info.hwnd,
            client_origin=(window_info.client_rect.left, window_info.client_rect.top),
            action_type="smoke_zoom_out",
        )
        time.sleep(config.timing.post_restore_dwell_seconds)
        save_client_capture(output_dir / "03_after_restore.png", window_info.client_rect.to_bbox())

        (output_dir / "probe_result.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Elevated smoke probe finished: %s", output_dir)
        print(output_dir)
        return 0
    finally:
        if native_client is not None:
            native_client.close()


if __name__ == "__main__":
    raise SystemExit(main())
