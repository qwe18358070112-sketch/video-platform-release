from __future__ import annotations

import time
from pathlib import Path

import keyboard
import win32api
import yaml
from PIL import ImageDraw, ImageGrab

from common import Rect
from grid_mapper import GridMapper
from window_manager import WindowManager


class CalibrationManager:
    def __init__(self, config, window_manager: WindowManager, logger, status_publisher=None):
        self._config = config
        self._window_manager = window_manager
        self._logger = logger
        self._status = status_publisher

    def run(self, mode: str) -> None:
        if mode not in {"windowed", "fullscreen"}:
            raise ValueError("Calibration mode must be windowed or fullscreen")

        window_info = self._window_manager.find_target_window()
        self._window_manager.focus_window(window_info.hwnd)
        time.sleep(self._config.timing.focus_delay_ms / 1000.0)

        print("")
        print(f"Calibration mode: {mode}")
        print(f"Target window: {window_info.title or window_info.process_name}")
        print(f"Client rect: {window_info.client_rect}")
        print("")
        print("Step 1: Move the mouse to the TOP-LEFT corner of the preview area.")
        print(f"Then press {self._config.hotkeys.calibration_capture}.")
        self._publish_instruction(
            title=f"{mode} 标定",
            message="第 1 步：把鼠标移到预览区左上角",
            details=f"移动好以后按 {self._config.hotkeys.calibration_capture}",
            level="info",
        )
        top_left = self._capture_point(window_info.client_rect)
        print(f"Captured top-left: {top_left}")

        print("")
        print("Step 2: Move the mouse to the BOTTOM-RIGHT corner of the preview area.")
        print(f"Then press {self._config.hotkeys.calibration_capture} again.")
        self._publish_instruction(
            title=f"{mode} 标定",
            message="第 2 步：把鼠标移到预览区右下角",
            details=f"移动好以后再按一次 {self._config.hotkeys.calibration_capture}",
            level="info",
        )
        bottom_right = self._capture_point(window_info.client_rect)
        print(f"Captured bottom-right: {bottom_right}")

        if bottom_right[0] <= top_left[0] or bottom_right[1] <= top_left[1]:
            raise RuntimeError("Invalid calibration points: bottom-right must be below and to the right of top-left")

        profile = self._to_ratio_profile(window_info.client_rect, top_left, bottom_right)
        self._persist_profile(mode, profile)
        preview_path = self._save_capture_preview(mode, window_info.client_rect, top_left, bottom_right)
        self._logger.info("Saved %s calibration profile: %s", mode, profile)

        print("")
        print("Calibration saved.")
        print(profile)
        print(f"Calibration preview image: {preview_path}")
        self._publish_instruction(
            title=f"{mode} 标定完成",
            message="标定结果已保存",
            details=f"预览图: {preview_path.name}",
            level="success",
        )
        if self._status:
            self._status.stop(message=f"{mode} 标定完成")

    def inspect(self, mode: str) -> Path:
        if mode not in {"windowed", "fullscreen"}:
            raise ValueError("Calibration mode must be windowed or fullscreen")

        window_info = self._window_manager.find_target_window()
        self._window_manager.focus_window(window_info.hwnd)
        time.sleep(self._config.timing.focus_delay_ms / 1000.0)

        output_path = self._save_profile_preview(mode, window_info.client_rect)
        self._logger.info("Saved %s calibration inspection preview: %s", mode, output_path)
        print(f"Calibration inspection image: {output_path}")
        self._publish_instruction(
            title=f"{mode} 标定检查",
            message="已生成当前标定检查图",
            details=f"文件: {output_path.name}",
            level="success",
        )
        if self._status:
            self._status.stop(message=f"{mode} 标定检查完成")
        return output_path

    def _capture_point(self, client_rect: Rect) -> tuple[int, int]:
        keyboard.wait(self._config.hotkeys.calibration_capture, suppress=False, trigger_on_release=False)
        point = win32api.GetCursorPos()
        if not client_rect.contains_point(point):
            raise RuntimeError(f"Captured point {point} is outside the client area {client_rect}")
        return point

    def _to_ratio_profile(self, client_rect: Rect, top_left: tuple[int, int], bottom_right: tuple[int, int]) -> dict[str, float]:
        width = max(1, client_rect.width)
        height = max(1, client_rect.height)
        return {
            "left_ratio": round((top_left[0] - client_rect.left) / width, 6),
            "top_ratio": round((top_left[1] - client_rect.top) / height, 6),
            "right_ratio": round((bottom_right[0] - client_rect.left) / width, 6),
            "bottom_ratio": round((bottom_right[1] - client_rect.top) / height, 6),
        }

    def _persist_profile(self, mode: str, profile: dict[str, float]) -> None:
        config_path = Path(self._config.path)
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        raw.setdefault("profiles", {})
        raw["profiles"][mode] = profile
        config_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=False), encoding="utf-8")

    def _save_capture_preview(
        self,
        mode: str,
        client_rect: Rect,
        top_left: tuple[int, int],
        bottom_right: tuple[int, int],
    ) -> Path:
        output_dir = self._config.path.parent / "tmp"
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"calibration_{mode}_preview.png"
        image = ImageGrab.grab(bbox=client_rect.to_bbox()).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (
                top_left[0] - client_rect.left,
                top_left[1] - client_rect.top,
                bottom_right[0] - client_rect.left,
                bottom_right[1] - client_rect.top,
            ),
            outline=(37, 99, 235),
            width=4,
        )
        draw.ellipse(
            (
                top_left[0] - client_rect.left - 5,
                top_left[1] - client_rect.top - 5,
                top_left[0] - client_rect.left + 5,
                top_left[1] - client_rect.top + 5,
            ),
            fill=(16, 185, 129),
        )
        draw.ellipse(
            (
                bottom_right[0] - client_rect.left - 5,
                bottom_right[1] - client_rect.top - 5,
                bottom_right[0] - client_rect.left + 5,
                bottom_right[1] - client_rect.top + 5,
            ),
            fill=(239, 68, 68),
        )
        image.save(destination)
        return destination

    def _save_profile_preview(self, mode: str, client_rect: Rect) -> Path:
        output_dir = self._config.path.parent / "tmp"
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"calibration_{mode}_inspect.png"
        profile = getattr(self._config.profiles, mode)
        preview_rect = profile.to_rect(client_rect)
        cells = GridMapper(self._config.grid).build_cells(preview_rect, self._config.grid.layout)

        image = ImageGrab.grab(bbox=client_rect.to_bbox()).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (
                preview_rect.left - client_rect.left,
                preview_rect.top - client_rect.top,
                preview_rect.right - client_rect.left,
                preview_rect.bottom - client_rect.top,
            ),
            outline=(37, 99, 235),
            width=4,
        )

        for cell in cells:
            draw.rectangle(
                (
                    cell.rect.left - client_rect.left,
                    cell.rect.top - client_rect.top,
                    cell.rect.right - client_rect.left,
                    cell.rect.bottom - client_rect.top,
                ),
                outline=(148, 163, 184),
                width=2,
            )
            cx = cell.click_point[0] - client_rect.left
            cy = cell.click_point[1] - client_rect.top
            draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(239, 68, 68))
            draw.text((cx + 8, cy - 8), str(cell.index + 1), fill=(255, 255, 255))

        image.save(destination)
        return destination

    def _publish_instruction(self, title: str, message: str, details: str, level: str) -> None:
        if self._status:
            self._status.publish(title=title, message=message, details=details, level=level)
