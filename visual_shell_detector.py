from __future__ import annotations

from typing import Any

from PIL import Image, ImageStat


SAMPLE_LONG_EDGE = 512


def analyze_windowed_shell_image(image: Image.Image) -> dict[str, float]:
    sample = _downsample(image.convert("RGB"))
    width, height = sample.size

    left_panel = sample.crop((0, 0, max(1, int(width * 0.22)), height))
    top_toolbar = sample.crop((0, 0, width, max(1, int(height * 0.10))))
    preview_area = sample.crop((max(1, int(width * 0.24)), max(1, int(height * 0.08)), width, height))

    left_metrics = _luma_metrics(left_panel)
    top_metrics = _luma_metrics(top_toolbar)
    preview_metrics = _luma_metrics(preview_area)

    metrics = {
        "windowed_shell_left_mean": left_metrics["mean"],
        "windowed_shell_left_std": left_metrics["std"],
        "windowed_shell_left_bright_ratio": left_metrics["bright_ratio"],
        "windowed_shell_left_dark_ratio": left_metrics["dark_ratio"],
        "windowed_shell_top_mean": top_metrics["mean"],
        "windowed_shell_top_std": top_metrics["std"],
        "windowed_shell_top_bright_ratio": top_metrics["bright_ratio"],
        "windowed_shell_top_dark_ratio": top_metrics["dark_ratio"],
        "windowed_shell_preview_mean": preview_metrics["mean"],
        "windowed_shell_preview_std": preview_metrics["std"],
        "windowed_shell_preview_bright_ratio": preview_metrics["bright_ratio"],
        "windowed_shell_preview_dark_ratio": preview_metrics["dark_ratio"],
    }
    metrics["windowed_shell_score"] = round(
        float(metrics["windowed_shell_left_bright_ratio"] * 55.0)
        + float(metrics["windowed_shell_top_bright_ratio"] * 35.0)
        + max(0.0, float(metrics["windowed_shell_left_mean"]) - float(metrics["windowed_shell_preview_mean"])) * 0.12,
        4,
    )
    metrics["windowed_shell_like"] = 1.0 if looks_like_windowed_shell(metrics) else 0.0
    return metrics


def looks_like_windowed_shell(metrics: dict[str, float]) -> bool:
    left_mean = float(metrics.get("windowed_shell_left_mean", 0.0))
    left_bright_ratio = float(metrics.get("windowed_shell_left_bright_ratio", 0.0))
    left_dark_ratio = float(metrics.get("windowed_shell_left_dark_ratio", 1.0))
    top_mean = float(metrics.get("windowed_shell_top_mean", 0.0))
    top_bright_ratio = float(metrics.get("windowed_shell_top_bright_ratio", 0.0))
    top_dark_ratio = float(metrics.get("windowed_shell_top_dark_ratio", 1.0))
    preview_mean = float(metrics.get("windowed_shell_preview_mean", 0.0))
    preview_dark_ratio = float(metrics.get("windowed_shell_preview_dark_ratio", 0.0))

    return (
        left_mean >= 150.0
        and left_bright_ratio >= 0.40
        and left_dark_ratio <= 0.25
        and top_mean >= 95.0
        and top_bright_ratio >= 0.10
        and top_dark_ratio <= 0.40
        and (left_mean - preview_mean) >= 65.0
        and preview_dark_ratio >= 0.45
    )


def _downsample(image: Image.Image) -> Image.Image:
    longest_edge = max(image.width, image.height)
    if longest_edge <= SAMPLE_LONG_EDGE:
        return image
    scale = SAMPLE_LONG_EDGE / float(longest_edge)
    resize_filter = getattr(Image, "Resampling", Image).BILINEAR
    return image.resize(
        (
            max(96, int(image.width * scale)),
            max(96, int(image.height * scale)),
        ),
        resize_filter,
    )


def _luma_metrics(image: Image.Image) -> dict[str, float]:
    grayscale = image.convert("L")
    stat = ImageStat.Stat(grayscale)
    histogram = grayscale.histogram()
    total_pixels = max(1, sum(histogram))
    return {
        "mean": round(float(stat.mean[0]), 4),
        "std": round(float(stat.stddev[0]), 4),
        "bright_ratio": round(sum(histogram[180:]) / total_pixels, 4),
        "dark_ratio": round(sum(histogram[:60]) / total_pixels, 4),
    }

