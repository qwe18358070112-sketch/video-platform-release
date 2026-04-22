from __future__ import annotations

"""收藏夹名称读取器。

设计目标：
1. 在 Windows 目标机上，尽量通过 UI Automation 读取左侧收藏夹树/列表的可见名称顺序。
2. 读取失败时不让主流程崩掉，而是退回缓存文件。
3. 当前容器不是 Windows，无法实机读取 UIA；因此实现必须是“可编译、可部署、失败可降级”。
"""

import json
import platform
from dataclasses import asdict
from pathlib import Path
from typing import Any

from common import FavoritesConfig, Rect, WindowInfo, resolve_output_path


class FavoritesReader:
    def __init__(self, config: FavoritesConfig, config_path: Path, logger):
        self._config = config
        self._logger = logger
        self._cache_path = resolve_output_path(config_path, config.cache_file)

    def read_visible_names(self, window_info: WindowInfo) -> list[str]:
        if not self._config.enabled:
            return []

        if platform.system() != "Windows":
            self._logger.info("FavoritesReader fallback to cache because platform=%s", platform.system())
            return self._load_cache()

        try:
            names = self._read_with_uia(window_info)
            if names:
                self._save_cache(names)
                return names
            self._logger.warning("FavoritesReader UIA returned no visible names, fallback to cache")
            return self._load_cache()
        except Exception as exc:
            self._logger.warning("FavoritesReader UIA failed, fallback to cache: %s", exc)
            return self._load_cache()

    def debug_dump(self, window_info: WindowInfo) -> dict[str, Any]:
        names = self.read_visible_names(window_info)
        return {
            "enabled": self._config.enabled,
            "cache_file": str(self._cache_path),
            "count": len(names),
            "names": names,
        }

    def _read_with_uia(self, window_info: WindowInfo) -> list[str]:
        # 避免在非 Windows 或依赖不存在时顶层 import 失败。
        from pywinauto import Desktop

        panel_rect = self._favorite_panel_rect(window_info.client_rect)
        wrapper = Desktop(backend="uia").window(handle=window_info.hwnd)
        descendants = wrapper.descendants()

        collected: list[tuple[int, int, str, str]] = []
        allowed_types = {item for item in self._config.include_control_types}
        excluded = {text.strip() for text in self._config.exclude_texts}
        for ctrl in descendants:
            try:
                element_info = getattr(ctrl, "element_info", None)
                control_type = getattr(element_info, "control_type", "") or ""
                if allowed_types and control_type not in allowed_types:
                    continue

                text = (ctrl.window_text() or "").strip()
                if not text or text in excluded:
                    continue
                if self._config.visible_only and not ctrl.is_visible():
                    continue

                rect_obj = ctrl.rectangle()
                rect = Rect(rect_obj.left, rect_obj.top, rect_obj.right, rect_obj.bottom)
                if rect.bottom <= panel_rect.top or rect.top >= panel_rect.bottom:
                    continue
                if rect.right <= panel_rect.left or rect.left >= panel_rect.right:
                    continue
                if rect.height <= 2 or rect.width <= 2:
                    continue
                collected.append((rect.top, rect.left, text, control_type))
            except Exception:
                continue

        return self._normalize_collected_names(collected, max_entries=self._config.max_entries)

    @staticmethod
    def _normalize_collected_names(
        collected: list[tuple[int, int, str, str]],
        *,
        max_entries: int,
    ) -> list[str]:
        if not collected:
            return []

        # 关键修复：现场左侧面板里经常同时混着系统授权提示、标题文案、父级目录和真正的点位叶子节点。
        # favorites_name 只应优先取最深层的可见 TreeItem/ListItem，避免把标题或父目录误当成点位名称。
        tree_like = [item for item in collected if item[3] in {"TreeItem", "ListItem"}]
        if tree_like:
            deepest_left = max(item[1] for item in tree_like)
            depth_tolerance_px = 12
            collected = [item for item in tree_like if item[1] >= deepest_left - depth_tolerance_px]

        collected.sort(key=lambda item: (item[0], item[1]))
        result: list[str] = []
        seen: set[str] = set()
        for _, _, text, _ in collected:
            if text in seen:
                continue
            result.append(text)
            seen.add(text)
            if len(result) >= max_entries:
                break
        return result

    def _favorite_panel_rect(self, client_rect: Rect) -> Rect:
        panel_width = int(client_rect.width * self._config.left_panel_width_ratio)
        top_cut = int(client_rect.height * self._config.top_exclusion_ratio)
        return Rect(
            left=client_rect.left,
            top=client_rect.top + top_cut,
            right=client_rect.left + panel_width,
            bottom=client_rect.bottom,
        )

    def _load_cache(self) -> list[str]:
        if not self._cache_path.exists():
            return []
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
            names = payload.get("names", [])
            if isinstance(names, list):
                return [str(item) for item in names]
        except Exception as exc:
            self._logger.warning("FavoritesReader cache parse failed: %s", exc)
        return []

    def _save_cache(self, names: list[str]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "names": names,
            "count": len(names),
            "config": asdict(self._config),
        }
        self._cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
