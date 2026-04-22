from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageGrab, ImageStat

from common import ConfirmResult, ConfirmState, DEFAULT_LAYOUT_SPECS, DetectionConfig, DetectionResult, Rect, VisualViewState


SURFACE_METRIC_LONG_EDGE = 320


class Detector:
    def __init__(self, config: DetectionConfig, logger):
        self._config = config
        self._logger = logger

    def inspect(self, cell_rect: Rect) -> DetectionResult:
        if not self._config.enabled:
            return DetectionResult(status="disabled", metrics={})

        crop_rect = self._crop_rect(cell_rect)
        black_hits = 0
        preview_hits = 0
        final_metrics: dict[str, float] = {}

        for _ in range(max(self._config.black_screen_confirm_frames, self._config.preview_failure_confirm_frames, 1)):
            image = self.capture_image(crop_rect)
            grayscale = image.convert("L")
            metrics = self._inspect_metrics(grayscale)
            final_metrics = metrics

            if self._is_black_screen(metrics):
                black_hits += 1
            if self._is_preview_failure(metrics):
                preview_hits += 1

        if black_hits >= self._config.black_screen_confirm_frames:
            return DetectionResult(
                status="black_screen",
                metrics=final_metrics,
                reason="The cell looks like a black or blank frame",
            )

        if preview_hits >= self._config.preview_failure_confirm_frames:
            return DetectionResult(
                status="preview_failure",
                metrics=final_metrics,
                reason="The cell resembles a dark preview-failure overlay",
            )

        return DetectionResult(status="ok", metrics=final_metrics)

    def save_cell_snapshot(self, cell_rect: Rect, destination: Path) -> Path:
        if cell_rect.width <= 0 or cell_rect.height <= 0:
            raise RuntimeError(f"Cannot save snapshot for invalid rect: {cell_rect}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        image = self.capture_image(cell_rect)
        image.save(destination)
        return destination

    def capture_image(self, rect: Rect) -> Image.Image:
        if rect.width <= 0 or rect.height <= 0:
            raise RuntimeError(f"Cannot capture image for invalid rect: {rect}")
        return ImageGrab.grab(bbox=rect.to_bbox()).convert("RGB")

    def capture_probe(self, rect: Rect, size: tuple[int, int] = (48, 48)) -> Image.Image:
        return self.capture_image(rect).convert("L").resize(size)

    def capture_cell_probe(self, rect: Rect, size: tuple[int, int] = (128, 96)) -> Image.Image:
        return self.capture_image(rect).convert("L").resize(size)

    def measure_visual_change(self, before_image: Image.Image, after_image: Image.Image) -> dict[str, float]:
        before_gray = before_image.convert("L")
        after_gray = after_image.convert("L")
        if before_gray.size != after_gray.size:
            after_gray = after_gray.resize(before_gray.size)
        diff = ImageChops.difference(before_gray, after_gray)
        stats = ImageStat.Stat(diff)
        histogram = diff.histogram()
        total_pixels = max(1, sum(histogram))
        changed_pixels = sum(histogram[12:])
        return {
            "mean_diff": round(float(stats.mean[0]), 4),
            "changed_ratio": round(changed_pixels / total_pixels, 4),
        }

    def confirm_select(
        self,
        preview_rect: Rect,
        active_cell_rect: Rect,
        *,
        grid_probe=None,
    ) -> ConfirmResult:
        actual_view, metrics = self.classify_runtime_view(
            preview_rect,
            active_cell_rect,
            grid_probe=grid_probe,
            zoom_probe=None,
        )
        metrics = dict(metrics)
        if actual_view == VisualViewState.GRID or self.matches_expected_view(VisualViewState.GRID, metrics):
            metrics["select_view_confirmed"] = 1.0
            return ConfirmResult(
                state=ConfirmState.STATE_CONFIRMED,
                metrics=metrics,
                reason="grid_view_stable_after_select",
            )
        metrics["select_view_confirmed"] = 0.0
        return ConfirmResult(state=ConfirmState.PARTIAL_CHANGE, metrics=metrics, reason="select_view_uncertain")

    def confirm_zoom(
        self,
        preview_rect: Rect,
        active_cell_rect: Rect,
        *,
        cell_rect: Rect,
        before_preview_probe: Image.Image,
        before_cell_probe: Image.Image,
        grid_probe=None,
        soft_issue_hint: str = "",
        locked_fullscreen_layout: int | None = None,
    ) -> ConfirmResult:
        before_preview = before_preview_probe.convert("L")
        after_preview_rgb = self.capture_image(preview_rect)
        after_preview = after_preview_rgb.convert("L")
        if before_preview.size != after_preview.size:
            before_preview = before_preview.resize(after_preview.size)

        full_change_metrics = self.measure_visual_change(before_preview, after_preview)

        before_preview_center = self._center_crop(before_preview, ratio=0.34).resize(before_cell_probe.size)
        after_preview_center = self._center_crop(after_preview, ratio=0.34).resize(before_cell_probe.size)
        main_view_change_metrics = self.measure_visual_change(before_preview_center, after_preview_center)

        layout_metrics = self._divider_band_metrics(before_preview, after_preview, cell_rect)
        continuity_metrics = self._content_continuity_metrics(before_cell_probe, after_preview_center)

        runtime_view, runtime_metrics = self.classify_runtime_view(
            preview_rect,
            active_cell_rect,
            grid_probe=grid_probe,
            zoom_probe=None,
            preview_image=after_preview_rgb,
        )
        runtime_accept = runtime_view == VisualViewState.ZOOMED or self.matches_expected_view(
            VisualViewState.ZOOMED,
            runtime_metrics,
        )

        layout_change_confirmed = self._layout_change_confirmed(layout_metrics, runtime_accept)
        main_view_expansion_confirmed = self._main_view_expansion_confirmed(
            full_change_metrics,
            main_view_change_metrics,
            runtime_accept,
            layout_change_confirmed,
        )
        content_continuity_confirmed = self._content_continuity_confirmed(continuity_metrics)
        low_texture_zoom_confirmed = self._low_texture_zoom_confirmed(
            runtime_metrics=runtime_metrics,
            layout_metrics=layout_metrics,
            continuity_metrics=continuity_metrics,
            full_change_metrics=full_change_metrics,
            main_view_change_metrics=main_view_change_metrics,
            content_continuity_confirmed=content_continuity_confirmed,
            soft_issue_hint=soft_issue_hint,
        )
        preview_failure_zoom_confirmed = self._preview_failure_zoom_confirmed(
            runtime_metrics=runtime_metrics,
            layout_metrics=layout_metrics,
            continuity_metrics=continuity_metrics,
            full_change_metrics=full_change_metrics,
            main_view_change_metrics=main_view_change_metrics,
            content_continuity_confirmed=content_continuity_confirmed,
            soft_issue_hint=soft_issue_hint,
        )
        continuity_dominant_zoom_confirmed = self._continuity_dominant_zoom_confirmed(
            runtime_metrics=runtime_metrics,
            layout_metrics=layout_metrics,
            continuity_metrics=continuity_metrics,
            full_change_metrics=full_change_metrics,
            main_view_change_metrics=main_view_change_metrics,
            content_continuity_confirmed=content_continuity_confirmed,
        )
        locked_fullscreen_transition_zoom_confirmed = self._locked_fullscreen_transition_zoom_confirmed(
            locked_fullscreen_layout=locked_fullscreen_layout,
            runtime_metrics=runtime_metrics,
            layout_metrics=layout_metrics,
            continuity_metrics=continuity_metrics,
            full_change_metrics=full_change_metrics,
            main_view_change_metrics=main_view_change_metrics,
            content_continuity_confirmed=content_continuity_confirmed,
        )
        expansion_dominant_zoom_confirmed = self._expansion_dominant_zoom_confirmed(
            runtime_metrics=runtime_metrics,
            continuity_metrics=continuity_metrics,
            full_change_metrics=full_change_metrics,
            main_view_change_metrics=main_view_change_metrics,
            main_view_expansion_confirmed=main_view_expansion_confirmed,
        )
        runtime_transition_zoom_confirmed = self._runtime_transition_zoom_confirmed(
            runtime_accept=runtime_accept,
            continuity_metrics=continuity_metrics,
            full_change_metrics=full_change_metrics,
            main_view_change_metrics=main_view_change_metrics,
            main_view_expansion_confirmed=main_view_expansion_confirmed,
        )

        vote_count = sum(
            (
                1 if layout_change_confirmed else 0,
                1 if main_view_expansion_confirmed else 0,
                1 if content_continuity_confirmed else 0,
            )
        )
        partial_signal = (
            full_change_metrics["mean_diff"] >= self._config.zoom_confirm_mean_diff_threshold * 0.45
            or full_change_metrics["changed_ratio"] >= self._config.zoom_confirm_changed_ratio_threshold * 0.55
            or continuity_metrics["continuity_score"] <= 108.0
            or runtime_accept
        )

        metrics = {
            **runtime_metrics,
            **layout_metrics,
            **continuity_metrics,
            "full_frame_mean_diff": full_change_metrics["mean_diff"],
            "full_frame_changed_ratio": full_change_metrics["changed_ratio"],
            "main_view_mean_diff": main_view_change_metrics["mean_diff"],
            "main_view_changed_ratio": main_view_change_metrics["changed_ratio"],
            "layout_change_confirmed": 1.0 if layout_change_confirmed else 0.0,
            "main_view_expansion_confirmed": 1.0 if main_view_expansion_confirmed else 0.0,
            "content_continuity_confirmed": 1.0 if content_continuity_confirmed else 0.0,
            "low_texture_zoom_confirmed": 1.0 if low_texture_zoom_confirmed else 0.0,
            "preview_failure_zoom_confirmed": 1.0 if preview_failure_zoom_confirmed else 0.0,
            "continuity_dominant_zoom_confirmed": 1.0 if continuity_dominant_zoom_confirmed else 0.0,
            "locked_fullscreen_transition_zoom_confirmed": 1.0 if locked_fullscreen_transition_zoom_confirmed else 0.0,
            "expansion_dominant_zoom_confirmed": 1.0 if expansion_dominant_zoom_confirmed else 0.0,
            "runtime_transition_zoom_confirmed": 1.0 if runtime_transition_zoom_confirmed else 0.0,
            "soft_issue_black_screen_hint": 1.0 if soft_issue_hint == "black_screen" else 0.0,
            "soft_issue_preview_failure_hint": 1.0 if soft_issue_hint == "preview_failure" else 0.0,
            "zoom_vote_count": float(vote_count),
            "runtime_view_zoomed": 1.0 if runtime_accept else 0.0,
        }

        # 关键修复：非政务网 / 预览失败占位图这类低纹理单路放大态，
        # 分隔线不一定足够明显，但只要整帧变化、主视区变化、内容连续性同时成立，
        # 也必须认定已经放大成功，否则状态机会误以为没放大，后续无法正确回宫格。
        # 关键修复：政务网现场里，放大后的单路画面会偶发叠加 OSD / 编码抖动 / 错误页刷新，
        # 导致 content_continuity_confirmed 被保守打成 False。只要运行时视图或弱连续性证据
        # 已经表明“中心内容仍基本延续自原 cell”，并且主视区扩张足够强，就不能继续反复重试。
        if (
            vote_count >= 2
            or low_texture_zoom_confirmed
            or preview_failure_zoom_confirmed
            or continuity_dominant_zoom_confirmed
            or locked_fullscreen_transition_zoom_confirmed
            or expansion_dominant_zoom_confirmed
            or runtime_transition_zoom_confirmed
        ):
            return ConfirmResult(state=ConfirmState.STATE_CONFIRMED, metrics=metrics, reason="zoom_confirmed")
        if vote_count == 1 or partial_signal:
            return ConfirmResult(state=ConfirmState.PARTIAL_CHANGE, metrics=metrics, reason="zoom_partial_change")
        return ConfirmResult(state=ConfirmState.NO_CHANGE, metrics=metrics, reason="zoom_no_change")

    def confirm_grid(
        self,
        preview_rect: Rect,
        active_cell_rect: Rect,
        *,
        grid_probe=None,
        zoom_probe=None,
    ) -> ConfirmResult:
        actual_view, metrics = self.classify_runtime_view(
            preview_rect,
            active_cell_rect,
            grid_probe=grid_probe,
            zoom_probe=zoom_probe,
        )
        metrics = dict(metrics)
        grid_score = float(metrics.get("grid_probe_score", 9999.0))
        zoom_score = float(metrics.get("zoom_probe_score", 9999.0))
        structure_ratio = float(metrics.get("structure_changed_ratio", 0.0))
        if actual_view == VisualViewState.GRID or self.matches_expected_view(VisualViewState.GRID, metrics):
            return ConfirmResult(state=ConfirmState.STATE_CONFIRMED, metrics=metrics, reason="grid_confirmed")
        if grid_score < zoom_score or structure_ratio >= self._config.resume_grid_changed_ratio_min * 0.7:
            return ConfirmResult(state=ConfirmState.PARTIAL_CHANGE, metrics=metrics, reason="grid_partial_change")
        return ConfirmResult(state=ConfirmState.NO_CHANGE, metrics=metrics, reason="grid_no_change")

    def matches_expected_view(self, expected: VisualViewState, metrics: dict[str, float]) -> bool:
        if expected == VisualViewState.GRID:
            grid_mean = metrics.get("grid_probe_mean_diff")
            grid_ratio = metrics.get("grid_probe_changed_ratio")
            zoom_mean = metrics.get("zoom_probe_mean_diff")
            zoom_ratio = metrics.get("zoom_probe_changed_ratio")
            if grid_mean is not None and grid_ratio is not None:
                if self._matches_known_probe({"mean_diff": grid_mean, "changed_ratio": grid_ratio}):
                    return True
                if (
                    grid_mean <= self._config.resume_grid_mean_diff_min * 0.75
                    and grid_ratio <= self._config.resume_grid_changed_ratio_min * 1.8
                ):
                    return True
                if zoom_mean is not None and zoom_ratio is not None:
                    grid_score = self._probe_score({"mean_diff": grid_mean, "changed_ratio": grid_ratio})
                    zoom_score = self._probe_score({"mean_diff": zoom_mean, "changed_ratio": zoom_ratio})
                    if grid_score <= zoom_score * 0.92:
                        return True
            structure_mean = metrics.get("structure_mean_diff")
            structure_ratio = metrics.get("structure_changed_ratio")
            if structure_mean is not None and structure_ratio is not None:
                return (
                    structure_mean >= self._config.resume_grid_mean_diff_min * 0.8
                    or structure_ratio >= self._config.resume_grid_changed_ratio_min * 0.8
                )

        if expected == VisualViewState.ZOOMED:
            zoom_mean = metrics.get("zoom_probe_mean_diff")
            zoom_ratio = metrics.get("zoom_probe_changed_ratio")
            grid_mean = metrics.get("grid_probe_mean_diff")
            grid_ratio = metrics.get("grid_probe_changed_ratio")
            if metrics.get("runtime_transition_zoom_confirmed") == 1.0:
                return True
            if metrics.get("expansion_dominant_zoom_confirmed") == 1.0:
                return True
            if metrics.get("layout_change_confirmed") == 1.0 and metrics.get("content_continuity_confirmed") == 1.0:
                return True
            if zoom_mean is not None and zoom_ratio is not None:
                if self._matches_known_probe({"mean_diff": zoom_mean, "changed_ratio": zoom_ratio}):
                    return True
                if grid_mean is not None and grid_ratio is not None:
                    zoom_score = self._probe_score({"mean_diff": zoom_mean, "changed_ratio": zoom_ratio})
                    grid_score = self._probe_score({"mean_diff": grid_mean, "changed_ratio": grid_ratio})
                    if zoom_score <= grid_score * 0.92:
                        return True
            structure_mean = metrics.get("structure_mean_diff")
            structure_ratio = metrics.get("structure_changed_ratio")
            if structure_mean is not None and structure_ratio is not None:
                return (
                    structure_mean <= self._config.resume_zoomed_mean_diff_max * 1.3
                    and structure_ratio <= self._config.resume_zoomed_changed_ratio_max * 1.3
                )

        return False

    def classify_runtime_view(
        self,
        preview_rect: Rect,
        active_cell_rect: Rect,
        *,
        grid_probe=None,
        zoom_probe=None,
        preview_image: Image.Image | None = None,
    ) -> tuple[VisualViewState, dict[str, float]]:
        preview_capture = preview_image if preview_image is not None else self.capture_image(preview_rect)
        preview_gray = preview_capture.convert("L")
        current_preview = preview_gray.resize((64, 64))
        metrics: dict[str, float] = {}

        strong_probe_scores: dict[VisualViewState, float] = {}
        if zoom_probe is not None:
            zoom_metrics = self.measure_visual_change(zoom_probe, current_preview)
            metrics["zoom_probe_mean_diff"] = zoom_metrics["mean_diff"]
            metrics["zoom_probe_changed_ratio"] = zoom_metrics["changed_ratio"]
            metrics["zoom_probe_score"] = round(self._probe_score(zoom_metrics), 4)
            if self._matches_known_probe(zoom_metrics):
                strong_probe_scores[VisualViewState.ZOOMED] = self._probe_score(zoom_metrics)

        if grid_probe is not None:
            grid_metrics = self.measure_visual_change(grid_probe, current_preview)
            metrics["grid_probe_mean_diff"] = grid_metrics["mean_diff"]
            metrics["grid_probe_changed_ratio"] = grid_metrics["changed_ratio"]
            metrics["grid_probe_score"] = round(self._probe_score(grid_metrics), 4)
            if self._matches_known_probe(grid_metrics):
                strong_probe_scores[VisualViewState.GRID] = self._probe_score(grid_metrics)

        surface_metrics = self._preview_surface_metrics_from_image(preview_capture)
        metrics.update(surface_metrics)
        flat_interface_like = self._looks_like_flat_interface(metrics)
        metrics["flat_interface_like"] = 1.0 if flat_interface_like else 0.0

        if strong_probe_scores:
            # 关键修复：全屏弱纹理场景下，zoom/grid 两个 probe 可能都会落入“已知相似区间”。
            # 这时不能让后写入的 GRID 结果覆盖更接近当前画面的 ZOOMED probe，
            # 否则会在 ZOOM_DWELL / F11 恢复后把已经放大的画面误判回宫格。
            if (
                VisualViewState.ZOOMED in strong_probe_scores
                and VisualViewState.GRID in strong_probe_scores
            ):
                zoom_score = strong_probe_scores[VisualViewState.ZOOMED]
                grid_score = strong_probe_scores[VisualViewState.GRID]
                if zoom_score <= grid_score:
                    return VisualViewState.ZOOMED, metrics
                return VisualViewState.GRID, metrics

            strong_probe_match = min(strong_probe_scores.items(), key=lambda item: item[1])[0]
            return strong_probe_match, metrics

        if zoom_probe is not None and grid_probe is not None:
            zoom_score = float(metrics["zoom_probe_score"])
            grid_score = float(metrics["grid_probe_score"])
            if zoom_score * 1.45 < grid_score:
                return VisualViewState.ZOOMED, metrics
            if grid_score * 1.45 < zoom_score:
                return VisualViewState.GRID, metrics

        active_probe = self._capture_active_probe_from_preview(
            preview_rect,
            active_cell_rect,
            preview_gray,
            size=(64, 64),
        )
        structure_metrics = self.measure_visual_change(current_preview, active_probe)
        metrics["structure_mean_diff"] = structure_metrics["mean_diff"]
        metrics["structure_changed_ratio"] = structure_metrics["changed_ratio"]
        repeated_grid_like = self._looks_like_repeated_grid_layout(
            preview_gray,
            preview_rect,
            active_cell_rect,
            metrics,
        )
        metrics["repeated_grid_like"] = 1.0 if repeated_grid_like else 0.0
        if repeated_grid_like:
            # 关键修复：6/9 宫格里的“预览失败占位页”往往每一路内容都很相似，
            # 会让 current_preview vs active_probe 的差异显著变小，之前会被误判成 UNKNOWN。
            # 只要预览区内部按当前格大小仍能稳定看到多条横竖分隔线，就应当认定仍在宫格态。
            return VisualViewState.GRID, metrics
        if not flat_interface_like and (
            structure_metrics["mean_diff"] <= self._config.resume_zoomed_mean_diff_max
            and structure_metrics["changed_ratio"] <= self._config.resume_zoomed_changed_ratio_max
        ):
            return VisualViewState.ZOOMED, metrics
        if not flat_interface_like and zoom_probe is None and (
            structure_metrics["mean_diff"] >= self._config.resume_grid_mean_diff_min
            or structure_metrics["changed_ratio"] >= self._config.resume_grid_changed_ratio_min
        ):
            return VisualViewState.GRID, metrics
        return VisualViewState.UNKNOWN, metrics

    def classify_resume_view(
        self,
        preview_rect: Rect,
        active_cell_rect: Rect,
        *,
        grid_probe=None,
        zoom_probe=None,
    ) -> tuple[VisualViewState, dict[str, float]]:
        return self.classify_runtime_view(
            preview_rect,
            active_cell_rect,
            grid_probe=grid_probe,
            zoom_probe=zoom_probe,
        )

    def inspect_runtime_interface(
        self,
        preview_rect: Rect,
        active_cell_rect: Rect,
        *,
        expected_view: VisualViewState | None,
        grid_probe=None,
        zoom_probe=None,
    ) -> DetectionResult:
        actual_view, metrics = self.classify_runtime_view(
            preview_rect,
            active_cell_rect,
            grid_probe=grid_probe,
            zoom_probe=zoom_probe,
        )
        metrics = dict(metrics)
        expected_match = True
        if expected_view is not None:
            expected_match = actual_view == expected_view or self.matches_expected_view(expected_view, metrics)
        metrics["expected_match"] = 1.0 if expected_match else 0.0
        metrics["actual_view"] = actual_view.value
        metrics["expected_view"] = expected_view.value if expected_view is not None else ""

        # 关键修复：有些现场客户端会把“宫格里的预览失败占位图”渲染成低纹理界面。
        # 只要它仍然满足当前阶段的预期视图，就不能误判成 unexpected_interface 并强行恢复。
        if expected_view is not None and expected_match:
            return DetectionResult(status="ok", metrics=metrics, reason="runtime_view_matches_expected")
        if expected_view is None and actual_view != VisualViewState.UNKNOWN:
            return DetectionResult(status="ok", metrics=metrics, reason="runtime_view_ok")
        if metrics.get("flat_interface_like") == 1.0:
            return DetectionResult(status="unexpected_interface", metrics=metrics, reason="flat_or_wrong_interface")
        if expected_view is not None and not expected_match:
            return DetectionResult(status="view_mismatch", metrics=metrics, reason="unexpected_runtime_view")
        if actual_view == VisualViewState.UNKNOWN:
            return DetectionResult(status="view_unknown", metrics=metrics, reason="runtime_view_unknown")
        return DetectionResult(status="ok", metrics=metrics, reason="runtime_view_ok")

    def _preview_surface_metrics(self, preview_rect: Rect) -> dict[str, float]:
        image = self.capture_image(preview_rect)
        return self._preview_surface_metrics_from_image(image)

    def _preview_surface_metrics_from_image(self, image: Image.Image) -> dict[str, float]:
        # 关键修复：runtime 视图分类里最慢的不是截图，而是对整张预览图做熵/边缘/主色统计。
        # 对 2K/4K 预览直接跑 numpy.unique 成本极高；这里先做一份低分辨率采样图，
        # 保留界面平坦度判断所需的统计特征，同时把单次分类耗时从秒级压下来。
        sample_image = image
        longest_edge = max(image.width, image.height)
        if longest_edge > SURFACE_METRIC_LONG_EDGE:
            scale = SURFACE_METRIC_LONG_EDGE / float(longest_edge)
            sample_size = (
                max(64, int(image.width * scale)),
                max(64, int(image.height * scale)),
            )
            resize_filter = getattr(Image, "Resampling", Image).BILINEAR
            sample_image = image.resize(sample_size, resize_filter)

        grayscale = sample_image.convert("L")
        stats = ImageStat.Stat(grayscale)
        histogram = grayscale.histogram()
        total_pixels = max(1, sum(histogram))
        entropy = 0.0
        for count in histogram:
            if count <= 0:
                continue
            probability = count / total_pixels
            entropy -= float(probability * np.log2(probability))

        edge_image = grayscale.filter(ImageFilter.FIND_EDGES)
        edge_hist = edge_image.histogram()
        edge_pixels = sum(edge_hist[30:])
        edge_ratio = edge_pixels / total_pixels

        rgb = np.asarray(sample_image, dtype=np.uint8)
        quantized = (rgb // 16).reshape(-1, 3)
        if len(quantized) == 0:
            dominant_ratio = 1.0
        else:
            _, counts = np.unique(quantized, axis=0, return_counts=True)
            dominant_ratio = float(counts.max() / len(quantized))

        return {
            "preview_entropy": round(entropy, 4),
            "preview_std": round(float(stats.stddev[0]), 4),
            "preview_edge_ratio": round(edge_ratio, 4),
            "preview_dominant_ratio": round(dominant_ratio, 4),
        }

    def _capture_active_probe_from_preview(
        self,
        preview_rect: Rect,
        active_cell_rect: Rect,
        preview_gray: Image.Image,
        *,
        size: tuple[int, int],
    ) -> Image.Image:
        left = max(0, active_cell_rect.left - preview_rect.left)
        top = max(0, active_cell_rect.top - preview_rect.top)
        right = min(preview_gray.width, active_cell_rect.right - preview_rect.left)
        bottom = min(preview_gray.height, active_cell_rect.bottom - preview_rect.top)
        if right <= left or bottom <= top:
            return self.capture_probe(active_cell_rect, size=size)
        return preview_gray.crop((left, top, right, bottom)).resize(size)

    def _looks_like_repeated_grid_layout(
        self,
        preview_gray: Image.Image,
        preview_rect: Rect,
        active_cell_rect: Rect,
        metrics: dict[str, float],
    ) -> bool:
        preview_width = max(1, preview_rect.width)
        preview_height = max(1, preview_rect.height)
        # 关键修复：运行期分类传进来的是 active_cell.rect（去掉 padding 的内框），
        # 不是完整 cell_rect。直接拿它反推宫格列数，会把 6 宫格误估成 4 列。
        # 当前项目默认 cell_padding_ratio=0.08，因此用 0.84 反推出更接近真实格宽/格高。
        inferred_slot_ratio = 0.84
        cell_width = max(1.0, active_cell_rect.width / inferred_slot_ratio)
        cell_height = max(1.0, active_cell_rect.height / inferred_slot_ratio)

        estimated_cols = max(1, int(round(preview_width / cell_width)))
        estimated_rows = max(1, int(round(preview_height / cell_height)))
        metrics["grid_divider_rows_estimate"] = float(estimated_rows)
        metrics["grid_divider_cols_estimate"] = float(estimated_cols)

        if estimated_rows * estimated_cols <= 1:
            metrics["grid_divider_hit_count"] = 0.0
            metrics["grid_divider_expected_count"] = 0.0
            metrics["grid_divider_mean_strength"] = 0.0
            return False

        # 关键修复：只有当活动格确实只是预览区的一部分时，才尝试用“分隔线结构”
        # 来兜底识别宫格，避免把单路画面强行解释成多宫格。
        width_ratio = cell_width / float(preview_width)
        height_ratio = cell_height / float(preview_height)
        if width_ratio >= 0.82 and height_ratio >= 0.82:
            metrics["grid_divider_hit_count"] = 0.0
            metrics["grid_divider_expected_count"] = 0.0
            metrics["grid_divider_mean_strength"] = 0.0
            return False

        edge_image = preview_gray.filter(ImageFilter.FIND_EDGES)
        edge_array = np.asarray(edge_image, dtype=np.float32)
        band_half_width = max(2, min(preview_gray.width, preview_gray.height) // 180)
        peak_match_tolerance = max(18, min(preview_gray.width, preview_gray.height) // 25)
        peak_min_gap = max(18, min(preview_gray.width, preview_gray.height) // 50)

        divider_strengths: list[float] = []
        expected_col_positions: list[int] = []
        for index in range(1, estimated_cols):
            x = int(round(preview_gray.width * index / estimated_cols))
            expected_col_positions.append(x)
            left = max(0, x - band_half_width)
            right = min(preview_gray.width, x + band_half_width + 1)
            if right > left:
                divider_strengths.append(float(edge_array[:, left:right].mean()))
        expected_row_positions: list[int] = []
        for index in range(1, estimated_rows):
            y = int(round(preview_gray.height * index / estimated_rows))
            expected_row_positions.append(y)
            top = max(0, y - band_half_width)
            bottom = min(preview_gray.height, y + band_half_width + 1)
            if bottom > top:
                divider_strengths.append(float(edge_array[top:bottom, :].mean()))

        expected_count = len(divider_strengths)
        if expected_count == 0:
            metrics["grid_divider_hit_count"] = 0.0
            metrics["grid_divider_expected_count"] = 0.0
            metrics["grid_divider_mean_strength"] = 0.0
            return False

        mean_strength = float(sum(divider_strengths) / expected_count)
        hit_count = sum(1 for strength in divider_strengths if strength >= 22.0)
        metrics["grid_divider_hit_count"] = float(hit_count)
        metrics["grid_divider_expected_count"] = float(expected_count)
        metrics["grid_divider_mean_strength"] = round(mean_strength, 4)

        row_profile = edge_array.mean(axis=1)
        col_profile = edge_array.mean(axis=0)

        def collect_profile_peaks(profile: np.ndarray) -> list[int]:
            peaks: list[int] = []
            for idx in np.argsort(profile)[::-1]:
                index = int(idx)
                if index < 10 or index >= len(profile) - 10:
                    continue
                if any(abs(index - existing) < peak_min_gap for existing in peaks):
                    continue
                peaks.append(index)
                if len(peaks) >= 12:
                    break
            return peaks

        row_peaks = collect_profile_peaks(row_profile)
        col_peaks = collect_profile_peaks(col_profile)

        def peak_match_count(peaks: list[int], positions: list[int]) -> int:
            return sum(1 for pos in positions if any(abs(peak - pos) <= peak_match_tolerance for peak in peaks))

        def local_peak_mean(profile: np.ndarray, positions: list[int]) -> float:
            if not positions:
                return 0.0
            values: list[float] = []
            for pos in positions:
                left = max(0, int(pos - peak_match_tolerance))
                right = min(len(profile), int(pos + peak_match_tolerance + 1))
                values.append(float(profile[left:right].max()))
            return float(sum(values) / len(values))

        metrics["grid_divider_row_peak_match_count"] = float(peak_match_count(row_peaks, expected_row_positions))
        metrics["grid_divider_col_peak_match_count"] = float(peak_match_count(col_peaks, expected_col_positions))
        metrics["grid_divider_row_local_peak_mean"] = round(local_peak_mean(row_profile, expected_row_positions), 4)
        metrics["grid_divider_col_local_peak_mean"] = round(local_peak_mean(col_profile, expected_col_positions), 4)

        required_hits = max(2, expected_count // 2)
        preview_edge_ratio = float(metrics.get("preview_edge_ratio", 0.0))
        preview_entropy = float(metrics.get("preview_entropy", 999.0))
        preview_std = float(metrics.get("preview_std", 999.0))
        preview_dominant_ratio = float(metrics.get("preview_dominant_ratio", 0.0))
        row_peak_match_count = float(metrics.get("grid_divider_row_peak_match_count", 0.0))
        col_peak_match_count = float(metrics.get("grid_divider_col_peak_match_count", 0.0))
        row_local_peak_mean = float(metrics.get("grid_divider_row_local_peak_mean", 0.0))
        col_local_peak_mean = float(metrics.get("grid_divider_col_local_peak_mean", 0.0))
        if hit_count >= required_hits and (mean_strength >= 18.0 or preview_edge_ratio >= 0.045):
            return True

        # 关键修复：真全屏 4 宫格的“预览失败 / 低纹理占位页”边缘很弱，
        # 传统分隔线 hit_count 门槛经常会掉到 0，但 2x2 结构的平均分隔线强度
        # 仍然会明显高于错误的 6/9/12 候选布局。这里补一条窄兜底，只放宽
        # fullscreen-like 2x2 宫格失败页，不把所有 flat interface 都当成宫格。
        structure_changed_ratio = float(metrics.get("structure_changed_ratio", 0.0))
        flat_interface_like = float(metrics.get("flat_interface_like", 0.0)) == 1.0
        row_peak_support = row_peak_match_count >= 1.0 or row_local_peak_mean >= 15.0
        col_peak_support = col_peak_match_count >= 1.0 or col_local_peak_mean >= 6.3
        if (
            estimated_rows == 2
            and estimated_cols == 2
            and expected_count == 2
            and row_peak_match_count >= 1.0
            and col_peak_match_count >= 1.0
            and row_local_peak_mean >= 120.0
            and col_local_peak_mean >= 120.0
            and preview_edge_ratio >= 0.04
            and structure_changed_ratio >= 0.08
        ):
            # 根因修复：这类真全屏 4 宫格样本在 detector 层已经具备稳定的 2x2 峰值结构，
            # 不应该继续落到 UNKNOWN 再依赖上层 prepare-target 特判兜底。
            return True
        if (
            flat_interface_like
            and estimated_rows == 2
            and estimated_cols == 2
            and expected_count == 2
            and row_peak_support
            and col_peak_support
            and row_local_peak_mean >= 12.0
            and col_local_peak_mean >= 6.0
            and preview_dominant_ratio >= 0.95
            and preview_entropy <= 0.7
            and preview_std <= 6.5
            and preview_edge_ratio >= 0.025
            and structure_changed_ratio >= 0.06
        ):
            # 根因修复：弱纹理全屏 4 宫格在启动或恢复后，某一侧分隔线峰值可能轻微漂移，
            # 但局部峰值强度仍然稳定。detector 应直接把这种 2x2 结构识别为 GRID。
            return True
        if (
            flat_interface_like
            and estimated_rows == 2
            and estimated_cols == 2
            and expected_count == 2
            and row_peak_support
            and col_peak_support
            and row_local_peak_mean >= 15.0
            and col_local_peak_mean >= 6.3
            and preview_dominant_ratio >= 0.90
            and preview_entropy <= 1.1
            and preview_std <= 11.2
            and preview_edge_ratio >= 0.03
            and structure_changed_ratio >= 0.10
        ):
            # 根因修复：首轮启动的全屏 4 宫格样本会比恢复态更“脏”，熵和方差更高，
            # 之前 detector 直接给 UNKNOWN，才导致 PREPARE_TARGET 在第一窗格误暂停。
            return True
        if (
            flat_interface_like
            and estimated_rows == 2
            and estimated_cols == 2
            and expected_count == 2
            and mean_strength >= 8.0
            and preview_edge_ratio >= 0.03
            and structure_changed_ratio >= 0.06
        ):
            return True
        if (
            flat_interface_like
            and estimated_rows == 2
            and estimated_cols == 2
            and expected_count == 2
            and mean_strength >= 9.0
            and preview_edge_ratio >= 0.02
            and structure_changed_ratio >= 0.06
        ):
            # 关键修复：全屏 4 宫格在“当前画面几乎全黑/全平，但宫格分隔仍然可见”时，
            # 边缘占比可能会掉到 0.02~0.03 之间。这里再补一条更窄的兜底，
            # 只接受 2x2、分隔线平均强度更高的场景，避免把普通单路黑页误认成宫格。
            return True
        fullscreen_six_resume_failure_grid = (
            flat_interface_like
            and estimated_rows == 2
            and estimated_cols == 3
            and expected_count == 3
            and row_peak_support
            and col_peak_support
            and mean_strength >= 4.5
            and preview_dominant_ratio >= 0.90
            and preview_entropy <= 1.2
            and preview_std <= 11.5
            and preview_edge_ratio >= 0.035
            and structure_changed_ratio >= 0.10
        )
        if fullscreen_six_resume_failure_grid:
            # 关键修复：全屏 6 宫格恢复后的失败页宫格并不一定是超低熵/超低方差，
            # 但只要 2x3 的横纵峰位、边缘和结构变化仍然稳定，就应该直接识别为 GRID，
            # 避免 PREPARE_TARGET 反复掉进 prepare_not_grid/cooldown。
            return True
        fullscreen_six_dark_flat_grid = (
            flat_interface_like
            and estimated_rows == 2
            and estimated_cols == 3
            and expected_count == 3
            and row_peak_support
            and col_peak_support
            and mean_strength >= 3.8
            and preview_dominant_ratio >= 0.93
            and preview_entropy <= 0.9
            and preview_std <= 7.0
            and preview_edge_ratio >= 0.03
            and structure_changed_ratio >= 0.075
        )
        if fullscreen_six_dark_flat_grid:
            # 关键修复：真全屏 6 宫格在“多路失败页/暗色平坦 2x3 宫格”时，UIA 读不到窗口
            # 分割面板，旧阈值又会把这类真实宫格卡成 UNKNOWN。这里给 2x3 一条更窄的兜底，
            # 只接受 dominant 高、entropy/std 低、横纵分隔和结构变化同时成立的场景，
            # 用来把 fullscreen 6 从 UNKNOWN 拉回 GRID，而不会把普通单路黑页误翻成 6。
            return True
        fullscreen_six_weak_post_recover_grid = (
            flat_interface_like
            and estimated_rows == 2
            and estimated_cols == 3
            and expected_count == 3
            and row_peak_support
            and col_peak_support
            and mean_strength >= 3.5
            and preview_dominant_ratio >= 0.93
            and preview_entropy <= 0.9
            and preview_std <= 6.0
            and preview_edge_ratio >= 0.03
            and structure_changed_ratio >= 0.03
        )
        if fullscreen_six_weak_post_recover_grid:
            # 关键修复：全屏 6 宫格在人工回宫格后的恢复链上，还会出现更弱的 2x3 暗色宫格，
            # 结构变化只剩 0.03~0.04，但横纵峰位仍在。detector 应直接把这类 post-recover
            # 样本识别为 GRID，避免 scheduler 再次把它压回 prepare_not_grid/cooldown。
            return True
        return False

    def _looks_like_flat_interface(self, metrics: dict[str, float]) -> bool:
        entropy = float(metrics.get("preview_entropy", 999.0))
        edge_ratio = float(metrics.get("preview_edge_ratio", 1.0))
        dominant_ratio = float(metrics.get("preview_dominant_ratio", 0.0))
        return (
            entropy <= self._config.runtime_flat_entropy_max
            and edge_ratio <= self._config.runtime_flat_edge_ratio_max
            and dominant_ratio >= self._config.runtime_flat_dominant_ratio_min
        )

    def _inspect_metrics(self, grayscale: Image.Image) -> dict[str, float]:
        stats = ImageStat.Stat(grayscale)
        mean_luma = float(stats.mean[0])
        std_luma = float(stats.stddev[0])
        histogram = grayscale.histogram()
        total_pixels = max(1, sum(histogram))
        dark_pixels = sum(histogram[:30])
        bright_pixels = sum(histogram[180:])
        dark_ratio = dark_pixels / total_pixels
        bright_ratio = bright_pixels / total_pixels

        edge_image = grayscale.filter(ImageFilter.FIND_EDGES)
        edge_hist = edge_image.histogram()
        edge_pixels = sum(edge_hist[30:])
        edge_ratio = edge_pixels / total_pixels

        return {
            "mean_luma": round(mean_luma, 4),
            "std_luma": round(std_luma, 4),
            "dark_ratio": round(dark_ratio, 4),
            "bright_ratio": round(bright_ratio, 4),
            "edge_ratio": round(edge_ratio, 4),
        }

    def _is_black_screen(self, metrics: dict[str, float]) -> bool:
        return (
            metrics["mean_luma"] <= self._config.black_screen_mean_threshold
            and metrics["std_luma"] <= self._config.black_screen_std_threshold
            and metrics["bright_ratio"] <= self._config.black_screen_bright_ratio_threshold
            and metrics["edge_ratio"] <= self._config.black_screen_edge_ratio_threshold
        )

    def _is_preview_failure(self, metrics: dict[str, float]) -> bool:
        return (
            metrics["dark_ratio"] >= self._config.failure_dark_ratio_threshold
            and self._config.failure_bright_ratio_min <= metrics["bright_ratio"] <= self._config.failure_bright_ratio_max
            and self._config.failure_edge_ratio_min <= metrics["edge_ratio"] <= self._config.failure_edge_ratio_max
        )

    def _matches_known_probe(self, metrics: dict[str, float]) -> bool:
        return (
            metrics["mean_diff"] <= self._config.resume_grid_mean_diff_min
            and metrics["changed_ratio"] <= self._config.resume_grid_changed_ratio_min
        )

    @staticmethod
    def _probe_score(metrics: dict[str, float]) -> float:
        return float(metrics["mean_diff"]) + float(metrics["changed_ratio"]) * 100.0

    def _layout_change_confirmed(self, layout_metrics: dict[str, float], runtime_accept: bool) -> bool:
        before_density = layout_metrics["divider_edge_before"]
        after_density = layout_metrics["divider_edge_after"]
        reduction = layout_metrics["divider_edge_reduction"]
        if before_density >= 0.015 and (reduction >= 0.012 or after_density <= before_density * 0.72):
            return True
        return runtime_accept and reduction >= 0.008

    def _main_view_expansion_confirmed(
        self,
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
        runtime_accept: bool,
        layout_change_confirmed: bool,
    ) -> bool:
        full_score = full_change_metrics["mean_diff"] + full_change_metrics["changed_ratio"] * 100.0
        center_score = main_view_change_metrics["mean_diff"] + main_view_change_metrics["changed_ratio"] * 100.0
        if full_score >= max(20.0, self._config.zoom_confirm_mean_diff_threshold * 1.1) and center_score >= 16.0:
            return True
        if layout_change_confirmed and self._layout_change_plus_frame_change_confirmed(
            full_change_metrics,
            main_view_change_metrics,
        ):
            return True
        return runtime_accept and (
            full_change_metrics["changed_ratio"] >= self._config.zoom_confirm_changed_ratio_threshold * 0.8
            and main_view_change_metrics["changed_ratio"] >= 0.12
        )

    def _low_texture_zoom_confirmed(
        self,
        *,
        runtime_metrics: dict[str, float],
        layout_metrics: dict[str, float] | None = None,
        continuity_metrics: dict[str, float],
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
        content_continuity_confirmed: bool,
        soft_issue_hint: str = "",
    ) -> bool:
        # 关键修复：固定布局程序必须以“真实单路转场证据”作为通用准则，
        # 不能依赖 black_screen / preview_failure 这类软异常标签才能通过。
        # 这里把原先针对黑屏/失败页补丁里的窄阈值统一收敛成“低纹理/平坦表面转场”
        # 通用路径，让真实监控画面、低纹理失败页和深色单路都走同一条确认链。
        dominant_surface_min = 0.82
        full_change_ratio_min = max(0.072, self._config.zoom_confirm_changed_ratio_threshold * 0.52)
        layout_metrics = dict(layout_metrics or {})
        divider_rows_estimate = int(
            round(
                float(
                    runtime_metrics.get(
                        "grid_divider_rows_estimate",
                        runtime_metrics.get(
                            "divider_rows_estimate",
                            layout_metrics.get("divider_rows_estimate", 0.0),
                        ),
                    )
                )
            )
        )
        divider_cols_estimate = int(
            round(
                float(
                    runtime_metrics.get(
                        "grid_divider_cols_estimate",
                        runtime_metrics.get(
                            "divider_cols_estimate",
                            layout_metrics.get("divider_cols_estimate", 0.0),
                        ),
                    )
                )
            )
        )
        preview_dominant_ratio = float(runtime_metrics.get("preview_dominant_ratio", 0.0))
        preview_std = float(runtime_metrics.get("preview_std", 999.0))
        preview_entropy = float(runtime_metrics.get("preview_entropy", 999.0))
        flat_surface_like = runtime_metrics.get("flat_interface_like") == 1.0 or (
            preview_dominant_ratio >= dominant_surface_min
            and preview_std <= 13.5
            and preview_entropy <= 2.2
        )
        if not flat_surface_like or not content_continuity_confirmed:
            return False

        histogram_corr = float(continuity_metrics.get("histogram_corr", 0.0))
        orb_vote = float(continuity_metrics.get("orb_vote", 0.0))
        if histogram_corr < 0.985 and orb_vote != 1.0:
            return False

        confirmed = (
            full_change_metrics["mean_diff"] >= 2.4
            and full_change_metrics["changed_ratio"] >= full_change_ratio_min
            and main_view_change_metrics["changed_ratio"] >= max(0.14, self._config.zoom_confirm_changed_ratio_threshold)
            and main_view_change_metrics["mean_diff"] >= 3.0
        )
        if confirmed:
            return True

        continuity_score = float(continuity_metrics.get("continuity_score", 999.0))
        continuity_ratio = float(continuity_metrics.get("continuity_changed_ratio", 999.0))
        relaxed_surface_transition = (
            histogram_corr >= 0.999
            and (orb_vote == 1.0 or continuity_score <= 24.0)
            and continuity_ratio <= 0.18
            and preview_dominant_ratio >= 0.93
            and preview_std <= 12.5
            and preview_entropy <= 0.95
            and full_change_metrics["mean_diff"] >= 3.5
            and full_change_metrics["changed_ratio"] >= 0.086
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        )
        if relaxed_surface_transition:
            return True

        relaxed_fullscreen_four_transition = (
            divider_rows_estimate == 2
            and divider_cols_estimate == 2
            and histogram_corr >= 0.997
            and continuity_score <= 18.0
            and continuity_ratio <= 0.16
            and preview_dominant_ratio >= 0.9
            and preview_std <= 13.0
            and preview_entropy <= 0.95
            and full_change_metrics["mean_diff"] >= 5.6
            and full_change_metrics["changed_ratio"] >= 0.145
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        )
        if relaxed_fullscreen_four_transition:
            # 全屏 4 宫格右下角等单路，中心裁剪区的变化会偏弱，
            # 但整帧变化、2x2 布局上下文和内容连续性已经足够说明放大成功。
            return True

        divider_edge_before = float(layout_metrics.get("divider_edge_before", 0.0))
        divider_edge_after = float(layout_metrics.get("divider_edge_after", 0.0))
        divider_edge_reduction = float(layout_metrics.get("divider_edge_reduction", 0.0))
        relaxed_fullscreen_four_layout_reduction = (
            divider_rows_estimate == 2
            and divider_cols_estimate == 2
            and histogram_corr >= 0.997
            and continuity_score <= 19.0
            and continuity_ratio <= 0.15
            and preview_dominant_ratio >= 0.9
            and preview_std <= 12.5
            and preview_entropy <= 0.95
            and divider_edge_before >= 0.009
            and divider_edge_after <= 0.0025
            and divider_edge_reduction >= 0.007
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        )
        if relaxed_fullscreen_four_layout_reduction:
            # 全屏 4 宫格左上角等单路在真机上有时几乎全屏都偏黑，
            # 整帧变化会低到 0.05 左右，但宫格分隔线已经明显消失。
            # 这里只在 2x2 + 分隔线收缩明确成立时放宽。
            return True

        relaxed_fullscreen_four_partial_change = (
            divider_rows_estimate == 2
            and divider_cols_estimate == 2
            and histogram_corr >= 0.999
            and continuity_score <= 8.0
            and continuity_ratio <= 0.06
            and preview_dominant_ratio >= 0.9
            and preview_std <= 12.5
            and preview_entropy <= 0.9
            and divider_edge_before >= 0.0068
            and divider_edge_after <= 0.0025
            and divider_edge_reduction >= 0.0048
            and full_change_metrics["mean_diff"] >= 2.4
            and full_change_metrics["changed_ratio"] >= 0.058
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        )
        if relaxed_fullscreen_four_partial_change:
            # 根因修复：全屏 4 宫格第二窗这类深色/低纹理单路在放大成功后，
            # 整帧变化会卡在 0.06 左右，只够得到 PARTIAL_CHANGE；但连续性、2x2 上下文
            # 和分隔线收缩都已经明确说明画面从宫格进入了单路放大，不应再被重试到自动暂停。
            return True

        relaxed_fullscreen_four_ultra_flat = (
            divider_rows_estimate == 2
            and divider_cols_estimate == 2
            and histogram_corr >= 0.9998
            and continuity_score <= 4.7
            and continuity_ratio <= 0.035
            and preview_dominant_ratio >= 0.963
            and preview_std <= 6.9
            and preview_entropy <= 0.42
            and divider_edge_before >= 0.0062
            and divider_edge_after <= 0.002
            and divider_edge_reduction >= 0.0047
            and full_change_metrics["mean_diff"] >= 1.55
            and full_change_metrics["changed_ratio"] >= 0.04
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        )
        if relaxed_fullscreen_four_ultra_flat:
            # 真机右上/左下单路在放大成功后，整帧变化和分隔线收缩都比左上角更弱，
            # 但会稳定呈现“超平坦表面 + 2x2 + 主视区变化成立 + 连续性极高”的组合。
            # 这里只对这类极窄样本放宽，避免全屏 4 的中间几路反复误停。
            return True

        relaxed_fullscreen_transition = (
            histogram_corr >= 0.998
            and continuity_score <= 18.0
            and preview_dominant_ratio >= 0.9
            and preview_std <= 13.0
            and preview_entropy <= 1.0
        )
        if not relaxed_fullscreen_transition:
            return False

        # 关键修复：真全屏 4 宫格深色单路在放大成功后，主视区 changed_ratio 往往只落在
        # 0.076 左右，但整帧变化、连续性和低纹理特征已经同时成立。这里保留一条更窄的
        # 真机兜底，但不再依赖软异常提示。
        return (
            full_change_metrics["mean_diff"] >= 3.4
            and full_change_metrics["changed_ratio"] >= 0.084
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        )

    def _preview_failure_zoom_confirmed(
        self,
        *,
        runtime_metrics: dict[str, float],
        layout_metrics: dict[str, float] | None = None,
        continuity_metrics: dict[str, float],
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
        content_continuity_confirmed: bool,
        soft_issue_hint: str = "",
    ) -> bool:
        if not content_continuity_confirmed:
            return False

        layout_metrics = dict(layout_metrics or {})
        divider_rows_estimate = int(
            round(
                float(
                    runtime_metrics.get(
                        "grid_divider_rows_estimate",
                        runtime_metrics.get(
                            "divider_rows_estimate",
                            layout_metrics.get("divider_rows_estimate", 0.0),
                        ),
                    )
                )
            )
        )
        divider_cols_estimate = int(
            round(
                float(
                    runtime_metrics.get(
                        "grid_divider_cols_estimate",
                        runtime_metrics.get(
                            "divider_cols_estimate",
                            layout_metrics.get("divider_cols_estimate", 0.0),
                        ),
                    )
                )
            )
        )
        flat_surface_like = runtime_metrics.get("flat_interface_like") == 1.0 and (
            float(runtime_metrics.get("preview_dominant_ratio", 0.0)) >= 0.91
            and float(runtime_metrics.get("preview_std", 999.0)) <= 12.5
            and float(runtime_metrics.get("preview_entropy", 999.0)) <= 1.2
        )
        relaxed_fullscreen_flat_surface_like = runtime_metrics.get("flat_interface_like") == 1.0 and (
            divider_rows_estimate == 2
            and divider_cols_estimate == 2
            and float(runtime_metrics.get("preview_dominant_ratio", 0.0)) >= 0.9
            and float(runtime_metrics.get("preview_std", 999.0)) <= 13.0
            and float(runtime_metrics.get("preview_entropy", 999.0)) <= 0.95
        )
        if not flat_surface_like and not relaxed_fullscreen_flat_surface_like:
            return False

        histogram_corr = float(continuity_metrics.get("histogram_corr", 0.0))
        orb_vote = float(continuity_metrics.get("orb_vote", 0.0))
        continuity_score = float(continuity_metrics.get("continuity_score", 999.0))
        continuity_ratio = float(continuity_metrics.get("continuity_changed_ratio", 999.0))
        if histogram_corr < 0.99 and orb_vote != 1.0:
            return False
        if continuity_score > 36.0 and continuity_ratio > 0.27:
            return False

        confirmed = (
            full_change_metrics["mean_diff"] >= 5.0
            and full_change_metrics["changed_ratio"] >= max(0.14, self._config.zoom_confirm_changed_ratio_threshold)
            and main_view_change_metrics["mean_diff"] >= 2.4
            and main_view_change_metrics["changed_ratio"] >= 0.084
        )
        if confirmed:
            return True

        relaxed_fullscreen_preview_failure = (
            divider_rows_estimate == 2
            and divider_cols_estimate == 2
            and float(runtime_metrics.get("preview_dominant_ratio", 0.0)) >= 0.9
            and float(runtime_metrics.get("preview_std", 999.0)) <= 13.0
            and float(runtime_metrics.get("preview_entropy", 999.0)) <= 0.9
            and histogram_corr >= 0.991
            and continuity_score <= 26.0
            and continuity_ratio <= 0.18
            and full_change_metrics["mean_diff"] >= 6.0
            and full_change_metrics["changed_ratio"] >= 0.145
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        )
        return relaxed_fullscreen_preview_failure

    def _runtime_transition_zoom_confirmed(
        self,
        *,
        runtime_accept: bool,
        continuity_metrics: dict[str, float],
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
        main_view_expansion_confirmed: bool,
    ) -> bool:
        if not main_view_expansion_confirmed:
            return False

        weak_continuity = (
            float(continuity_metrics.get("histogram_corr", 0.0)) >= 0.58
            or (
                float(continuity_metrics.get("orb_participated", 0.0)) == 1.0
                and float(continuity_metrics.get("orb_good_matches", 0.0)) >= 3.0
            )
            or (
                float(continuity_metrics.get("continuity_mean_diff", 999.0)) <= 48.0
                and float(continuity_metrics.get("continuity_changed_ratio", 999.0)) <= 0.62
            )
        )
        if not weak_continuity:
            return False

        strong_frame_change = (
            full_change_metrics["mean_diff"] >= max(3.0, self._config.zoom_confirm_mean_diff_threshold * 0.18)
            and full_change_metrics["changed_ratio"] >= max(0.10, self._config.zoom_confirm_changed_ratio_threshold * 0.72)
            and main_view_change_metrics["mean_diff"] >= 3.0
            and main_view_change_metrics["changed_ratio"] >= max(0.10, self._config.zoom_confirm_changed_ratio_threshold * 0.72)
        )
        if not strong_frame_change:
            return False

        if runtime_accept:
            return True

        return (
            float(continuity_metrics.get("histogram_corr", 0.0)) >= 0.64
            and full_change_metrics["changed_ratio"] >= max(0.12, self._config.zoom_confirm_changed_ratio_threshold * 0.82)
            and main_view_change_metrics["changed_ratio"] >= 0.11
        )

    def _locked_fullscreen_transition_zoom_confirmed(
        self,
        *,
        locked_fullscreen_layout: int | None,
        runtime_metrics: dict[str, float],
        layout_metrics: dict[str, float] | None = None,
        continuity_metrics: dict[str, float],
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
        content_continuity_confirmed: bool,
    ) -> bool:
        if locked_fullscreen_layout not in DEFAULT_LAYOUT_SPECS:
            return False

        expected_rows, expected_cols = DEFAULT_LAYOUT_SPECS[int(locked_fullscreen_layout)]
        layout_metrics = dict(layout_metrics or {})
        divider_rows_estimate = int(
            round(
                float(
                    runtime_metrics.get(
                        "grid_divider_rows_estimate",
                        runtime_metrics.get(
                            "divider_rows_estimate",
                            layout_metrics.get("divider_rows_estimate", 0.0),
                        ),
                    )
                )
            )
        )
        divider_cols_estimate = int(
            round(
                float(
                    runtime_metrics.get(
                        "grid_divider_cols_estimate",
                        runtime_metrics.get(
                            "divider_cols_estimate",
                            layout_metrics.get("divider_cols_estimate", 0.0),
                        ),
                    )
                )
            )
        )
        if divider_rows_estimate != expected_rows or divider_cols_estimate != expected_cols:
            return False

        if locked_fullscreen_layout == 6:
            return self._locked_fullscreen_six_transition_zoom_confirmed(
                runtime_metrics=runtime_metrics,
                layout_metrics=layout_metrics,
                continuity_metrics=continuity_metrics,
                full_change_metrics=full_change_metrics,
                main_view_change_metrics=main_view_change_metrics,
                content_continuity_confirmed=content_continuity_confirmed,
            )

        divider_edge_before = float(layout_metrics.get("divider_edge_before", 0.0))
        divider_edge_after = float(layout_metrics.get("divider_edge_after", 0.0))
        divider_edge_reduction = float(layout_metrics.get("divider_edge_reduction", 0.0))
        divider_transition_confirmed = (
            divider_edge_before >= 0.004
            and divider_edge_after <= 0.0026
            and divider_edge_reduction >= 0.0035
        )
        if not divider_transition_confirmed:
            return False

        histogram_corr = float(continuity_metrics.get("histogram_corr", 0.0))
        orb_vote = float(continuity_metrics.get("orb_vote", 0.0))
        continuity_score = float(continuity_metrics.get("continuity_score", 999.0))
        continuity_ratio = float(continuity_metrics.get("continuity_changed_ratio", 999.0))
        if not (content_continuity_confirmed or histogram_corr >= 0.99 or orb_vote == 1.0):
            return False
        if continuity_score > 28.0 and continuity_ratio > 0.18:
            return False

        return (
            full_change_metrics["mean_diff"] >= 3.2
            and full_change_metrics["changed_ratio"] >= 0.082
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        )

    def _locked_fullscreen_six_transition_zoom_confirmed(
        self,
        *,
        runtime_metrics: dict[str, float],
        layout_metrics: dict[str, float],
        continuity_metrics: dict[str, float],
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
        content_continuity_confirmed: bool,
    ) -> bool:
        if not content_continuity_confirmed:
            return False

        preview_dominant_ratio = float(runtime_metrics.get("preview_dominant_ratio", 0.0))
        preview_std = float(runtime_metrics.get("preview_std", 999.0))
        preview_entropy = float(runtime_metrics.get("preview_entropy", 999.0))
        if (
            preview_dominant_ratio < 0.9
            or preview_std > 12.8
            or preview_entropy > 1.15
        ):
            return False

        divider_edge_before = float(layout_metrics.get("divider_edge_before", 0.0))
        divider_edge_after = float(layout_metrics.get("divider_edge_after", 0.0))
        divider_edge_reduction = float(layout_metrics.get("divider_edge_reduction", 0.0))
        divider_transition_confirmed = (
            divider_edge_before >= 0.0135
            and divider_edge_after <= 0.0062
            and divider_edge_after <= divider_edge_before * 0.5
            and divider_edge_reduction >= 0.0075
        )
        if not divider_transition_confirmed:
            return False

        histogram_corr = float(continuity_metrics.get("histogram_corr", 0.0))
        continuity_score = float(continuity_metrics.get("continuity_score", 999.0))
        continuity_ratio = float(continuity_metrics.get("continuity_changed_ratio", 999.0))
        if histogram_corr < 0.997 or continuity_score > 18.0 or continuity_ratio > 0.13:
            return False

        return (
            full_change_metrics["mean_diff"] >= 3.5
            and full_change_metrics["changed_ratio"] >= 0.085
            and main_view_change_metrics["mean_diff"] >= 0.65
            and main_view_change_metrics["changed_ratio"] >= 0.025
        )

    def _expansion_dominant_zoom_confirmed(
        self,
        *,
        runtime_metrics: dict[str, float],
        continuity_metrics: dict[str, float],
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
        main_view_expansion_confirmed: bool,
    ) -> bool:
        if not main_view_expansion_confirmed:
            return False
        if float(runtime_metrics.get("flat_interface_like", 0.0)) == 1.0:
            return False

        strong_structure = (
            float(runtime_metrics.get("structure_mean_diff", 0.0)) >= 34.0
            and float(runtime_metrics.get("structure_changed_ratio", 0.0)) >= 0.78
        )
        divider_hits = float(runtime_metrics.get("grid_divider_hit_count", 0.0))
        expected_hits = max(1.0, float(runtime_metrics.get("grid_divider_expected_count", 0.0)))
        divider_support = (
            divider_hits >= max(3.0, expected_hits - 1.0)
            or (
                float(runtime_metrics.get("grid_divider_row_peak_match_count", 0.0))
                + float(runtime_metrics.get("grid_divider_col_peak_match_count", 0.0))
            ) >= max(2.0, expected_hits - 1.0)
        )
        if not strong_structure or not divider_support:
            return False

        strong_frame_change = (
            full_change_metrics["mean_diff"] >= 36.0
            and full_change_metrics["changed_ratio"] >= max(0.74, self._config.zoom_confirm_changed_ratio_threshold * 5.2)
            and main_view_change_metrics["mean_diff"] >= 30.0
            and main_view_change_metrics["changed_ratio"] >= max(0.74, self._config.zoom_confirm_changed_ratio_threshold * 5.2)
        )
        if not strong_frame_change:
            return False

        return (
            float(continuity_metrics.get("histogram_corr", 0.0)) >= 0.42
            or float(continuity_metrics.get("orb_good_matches", 0.0)) >= 1.0
            or float(continuity_metrics.get("continuity_mean_diff", 999.0)) <= 86.0
        )

    def _continuity_dominant_zoom_confirmed(
        self,
        *,
        runtime_metrics: dict[str, float],
        layout_metrics: dict[str, float] | None = None,
        continuity_metrics: dict[str, float],
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
        content_continuity_confirmed: bool,
    ) -> bool:
        # 关键修复：窗口态的第二行第一列等中间窗格，放大后的失败页/低纹理大图
        # 往往还保留少量分隔线痕迹，导致 layout_change/main_view_expansion 两票都拿不到，
        # 但中心内容连续、整帧变化和主视区变化其实都已经明显成立。这里补一条很窄的
        # “连续性主导”确认分支，专门收这类真实成功却被误判成重试的样本。
        if not content_continuity_confirmed:
            return False

        preview_dominant_ratio = float(runtime_metrics.get("preview_dominant_ratio", 0.0))
        preview_std = float(runtime_metrics.get("preview_std", 999.0))
        preview_entropy = float(runtime_metrics.get("preview_entropy", 999.0))
        flat_surface_like = runtime_metrics.get("flat_interface_like") == 1.0 or (
            preview_dominant_ratio >= 0.9
            and preview_std <= 14.0
            and preview_entropy <= 1.4
        )

        histogram_corr = float(continuity_metrics.get("histogram_corr", 0.0))
        orb_vote = float(continuity_metrics.get("orb_vote", 0.0))
        continuity_score = float(continuity_metrics.get("continuity_score", 999.0))
        continuity_ratio = float(continuity_metrics.get("continuity_changed_ratio", 999.0))
        if histogram_corr < 0.997 and orb_vote != 1.0:
            return False
        if continuity_score > 20.5:
            return False

        layout_metrics = dict(layout_metrics or {})
        divider_rows_estimate = int(
            round(
                float(
                    runtime_metrics.get(
                        "grid_divider_rows_estimate",
                        runtime_metrics.get(
                            "divider_rows_estimate",
                            layout_metrics.get("divider_rows_estimate", 0.0),
                        ),
                    )
                )
            )
        )
        divider_cols_estimate = int(
            round(
                float(
                    runtime_metrics.get(
                        "grid_divider_cols_estimate",
                        runtime_metrics.get(
                            "divider_cols_estimate",
                            layout_metrics.get("divider_cols_estimate", 0.0),
                        ),
                    )
                )
            )
        )
        divider_edge_before = float(layout_metrics.get("divider_edge_before", 0.0))
        divider_edge_after = float(layout_metrics.get("divider_edge_after", 0.0))
        divider_edge_reduction = float(layout_metrics.get("divider_edge_reduction", 0.0))
        fullscreen_four_transition_support = (
            divider_rows_estimate == 2
            and divider_cols_estimate == 2
            and divider_edge_before >= 0.0061
            and divider_edge_after <= 0.0025
            and divider_edge_reduction >= 0.0042
        )
        if (
            fullscreen_four_transition_support
            and flat_surface_like
            and histogram_corr >= 0.9985
            and continuity_score <= 10.5
            and continuity_ratio <= 0.08
            and full_change_metrics["mean_diff"] >= 2.3
            and full_change_metrics["changed_ratio"] >= 0.058
            and main_view_change_metrics["mean_diff"] >= 2.0
            and main_view_change_metrics["changed_ratio"] >= 0.075
        ):
            # 全屏 4 宫格的低纹理单路在真机上经常只表现为“分隔线收缩 + 主视区中等变化”。
            # 这里只根据 2x2 布局上下文、连续性和分隔线收缩确认放大成功，
            # 不再依赖 black_screen 软异常提示，便于把当前黑屏样本当作真实监控单路来校准。
            return True

        if not flat_surface_like:
            return False

        relaxed_real_machine_floor = (
            histogram_corr >= 0.999
            and continuity_score <= 16.5
            and preview_dominant_ratio >= 0.95
            and preview_std <= 8.0
            and preview_entropy <= 0.75
        )
        changed_ratio_floor = max(0.086, self._config.zoom_confirm_changed_ratio_threshold * 0.61) if relaxed_real_machine_floor else max(
            0.088,
            self._config.zoom_confirm_changed_ratio_threshold * 0.63,
        )

        return (
            full_change_metrics["mean_diff"] >= max(3.0, self._config.zoom_confirm_mean_diff_threshold * 0.17)
            and full_change_metrics["changed_ratio"] >= changed_ratio_floor
            and main_view_change_metrics["mean_diff"] >= 2.2
            # 关键修复：非政务网真机的第 2 行第 1 列失败样本里，
            # changed_ratio 会稳定落在 0.0872 / 0.0867 左右。只有在
            # “极低纹理 + 极高连续性”的窄窗口里，才把门槛再轻微放宽。
            and main_view_change_metrics["changed_ratio"] >= changed_ratio_floor
        )

    def _layout_change_plus_frame_change_confirmed(
        self,
        full_change_metrics: dict[str, float],
        main_view_change_metrics: dict[str, float],
    ) -> bool:
        # 关键修复：全屏 + 预览失败占位图时，中心区域变化往往比真实视频更弱，
        # 但只要分隔线明显消失，同时整帧和主视区都出现中等以上变化，就应认定为放大成功。
        return (
            full_change_metrics["mean_diff"] >= max(4.0, self._config.zoom_confirm_mean_diff_threshold * 0.22)
            and full_change_metrics["changed_ratio"] >= max(0.10, self._config.zoom_confirm_changed_ratio_threshold * 0.7)
            and main_view_change_metrics["mean_diff"] >= 2.5
            and main_view_change_metrics["changed_ratio"] >= 0.10
        )

    def _content_continuity_confirmed(self, continuity_metrics: dict[str, float]) -> bool:
        direct_confirmed = (
            continuity_metrics["continuity_score"] <= 92.0
            or continuity_metrics["histogram_corr"] >= 0.72
            or (
                continuity_metrics["continuity_mean_diff"] <= 34.0
                and continuity_metrics["continuity_changed_ratio"] <= 0.5
            )
        )
        orb_confirmed = continuity_metrics["orb_participated"] == 1.0 and continuity_metrics["orb_vote"] == 1.0
        return direct_confirmed or orb_confirmed

    def _divider_band_metrics(
        self,
        before_preview: Image.Image,
        after_preview: Image.Image,
        cell_rect: Rect,
    ) -> dict[str, float]:
        before_array = np.array(before_preview.convert("L"))
        after_array = np.array(after_preview.convert("L").resize(before_preview.size))
        preview_height, preview_width = before_array.shape
        cols = max(1, round(preview_width / max(cell_rect.width, 1)))
        rows = max(1, round(preview_height / max(cell_rect.height, 1)))
        band_width = max(2, int(min(max(cell_rect.width, 1), max(cell_rect.height, 1)) * 0.04))

        before_density = self._divider_edge_density(before_array, rows, cols, band_width)
        after_density = self._divider_edge_density(after_array, rows, cols, band_width)
        reduction = max(0.0, before_density - after_density)
        return {
            "divider_edge_before": round(before_density, 4),
            "divider_edge_after": round(after_density, 4),
            "divider_edge_reduction": round(reduction, 4),
            "divider_rows_estimate": float(rows),
            "divider_cols_estimate": float(cols),
        }

    def _content_continuity_metrics(self, before_cell_probe: Image.Image, after_center_probe: Image.Image) -> dict[str, float]:
        reference = before_cell_probe.convert("L").resize((160, 120))
        candidate = after_center_probe.convert("L").resize(reference.size)
        continuity = self.measure_visual_change(reference, candidate)
        histogram_corr = self._histogram_correlation(reference, candidate)
        orb_metrics = self._orb_metrics(reference, candidate) if self._config.use_orb_zoom_confirm else {
            "orb_ref_keypoints": 0.0,
            "orb_candidate_keypoints": 0.0,
            "orb_good_matches": 0.0,
            "orb_match_ratio": 0.0,
            "orb_participated": 0.0,
            "orb_vote": 0.0,
        }
        continuity_score = continuity["mean_diff"] + continuity["changed_ratio"] * 100.0
        metrics = {
            "continuity_mean_diff": continuity["mean_diff"],
            "continuity_changed_ratio": continuity["changed_ratio"],
            "continuity_score": round(continuity_score, 4),
            "histogram_corr": round(histogram_corr, 4),
        }
        metrics.update(orb_metrics)
        return metrics

    def _orb_metrics(self, reference: Image.Image, candidate: Image.Image) -> dict[str, float]:
        ref_array = np.array(reference)
        cand_array = np.array(candidate)
        orb = cv2.ORB_create(nfeatures=300)
        kp1, des1 = orb.detectAndCompute(ref_array, None)
        kp2, des2 = orb.detectAndCompute(cand_array, None)
        ref_keypoints = float(len(kp1) if kp1 is not None else 0)
        candidate_keypoints = float(len(kp2) if kp2 is not None else 0)
        metrics = {
            "orb_ref_keypoints": ref_keypoints,
            "orb_candidate_keypoints": candidate_keypoints,
            "orb_good_matches": 0.0,
            "orb_match_ratio": 0.0,
            "orb_participated": 0.0,
            "orb_vote": 0.0,
        }
        if des1 is None or des2 is None:
            return metrics

        orb_participated = ref_keypoints >= 14 and candidate_keypoints >= 14
        metrics["orb_participated"] = 1.0 if orb_participated else 0.0
        if not orb_participated:
            return metrics

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = matcher.match(des1, des2)
        if not matches:
            return metrics
        good_matches = [match for match in matches if match.distance <= 52]
        match_ratio = len(good_matches) / max(len(matches), 1)
        metrics["orb_good_matches"] = float(len(good_matches))
        metrics["orb_match_ratio"] = round(match_ratio, 4)
        metrics["orb_mean_distance"] = round(float(sum(match.distance for match in matches) / len(matches)), 4)
        metrics["orb_vote"] = 1.0 if (len(good_matches) >= 8 or match_ratio >= 0.16) else 0.0
        return metrics

    @staticmethod
    def _histogram_correlation(reference: Image.Image, candidate: Image.Image) -> float:
        ref_hist = cv2.calcHist([np.array(reference)], [0], None, [32], [0, 256])
        cand_hist = cv2.calcHist([np.array(candidate)], [0], None, [32], [0, 256])
        cv2.normalize(ref_hist, ref_hist)
        cv2.normalize(cand_hist, cand_hist)
        return float(cv2.compareHist(ref_hist, cand_hist, cv2.HISTCMP_CORREL))

    @staticmethod
    def _center_crop(image: Image.Image, ratio: float) -> Image.Image:
        width, height = image.size
        crop_w = max(8, int(width * ratio))
        crop_h = max(8, int(height * ratio))
        left = (width - crop_w) // 2
        top = (height - crop_h) // 2
        return image.crop((left, top, left + crop_w, top + crop_h))

    @staticmethod
    def _divider_edge_density(image_array: np.ndarray, rows: int, cols: int, band_width: int) -> float:
        edges = cv2.Canny(image_array, 60, 160)
        mask = np.zeros_like(edges, dtype=np.uint8)
        height, width = edges.shape
        for row in range(1, rows):
            y = int(round(row * height / rows))
            top = max(0, y - band_width)
            bottom = min(height, y + band_width)
            mask[top:bottom, :] = 1
        for col in range(1, cols):
            x = int(round(col * width / cols))
            left = max(0, x - band_width)
            right = min(width, x + band_width)
            mask[:, left:right] = 1
        valid = mask > 0
        if not np.any(valid):
            return 0.0
        return float(np.count_nonzero(edges[valid]) / np.count_nonzero(valid))

    def _crop_rect(self, cell_rect: Rect) -> Rect:
        crop_ratio = self._config.precheck_crop_ratio
        x_padding = int(cell_rect.width * (1 - crop_ratio) / 2)
        y_padding = int(cell_rect.height * (1 - crop_ratio) / 2)
        return cell_rect.inset(x_padding, y_padding)
