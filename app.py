from __future__ import annotations

import argparse
import atexit
import json
import os
import platform
import sys
from pathlib import Path

from common import enable_high_dpi_awareness, load_config
from logger_setup import setup_logger


WINDOWS_ONLY_ACTIONS = {
    "run scheduler": lambda args: bool(args.run),
    "calibrate preview": lambda args: bool(args.calibrate),
    "inspect calibration": lambda args: bool(args.inspect_calibration),
    "inspect runtime": lambda args: bool(args.inspect_runtime),
    "dump favorites": lambda args: bool(args.dump_favorites),
    "switch layout": lambda args: args.switch_layout is not None,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Windows automation for polling and zooming grid video cells in the Infovision client."
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--run", action="store_true", help="Run the polling scheduler")
    parser.add_argument(
        "--calibrate",
        choices=["windowed", "fullscreen"],
        help="Capture preview-area calibration for a mode and save ratios into config.yaml",
    )
    parser.add_argument(
        "--inspect-calibration",
        choices=["windowed", "fullscreen"],
        help="Generate an annotated preview image from the saved calibration profile",
    )
    parser.add_argument(
        "--inspect-runtime",
        action="store_true",
        help="Print the current detected mode/layout/runtime profile without starting the scheduler loop",
    )
    parser.add_argument(
        "--inspect-runtime-candidates",
        action="store_true",
        help="With --inspect-runtime, also print per-layout candidate scores and detector metrics",
    )
    parser.add_argument(
        "--dump-favorites",
        action="store_true",
        help="Read visible favorite names from the client left panel and print them as JSON",
    )
    parser.add_argument(
        "--switch-layout",
        type=int,
        choices=[4, 6, 9, 12, 13],
        help="Protected operation: manually close all live monitoring views first, then use the verified top toolbar '窗口分割' path to switch the client layout",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "windowed", "fullscreen"],
        help="Override config profiles.active_mode at runtime",
    )
    parser.add_argument(
        "--layout",
        type=int,
        choices=[4, 6, 9, 12],
        help="Override grid.layout at runtime and lock the scheduler to that layout until manually changed back",
    )
    parser.add_argument(
        "--no-auto-elevate",
        action="store_true",
        help="Disable automatic UAC relaunch when the target client is running at a higher integrity level.",
    )
    return parser.parse_args()


def require_windows_runtime(args: argparse.Namespace) -> None:
    if platform.system() == "Windows":
        return

    requested = [label for label, predicate in WINDOWS_ONLY_ACTIONS.items() if predicate(args)]
    if not requested:
        return

    action_summary = ", ".join(requested)
    raise SystemExit(
        "This project can be installed, self-tested, and packaged from WSL/Linux, "
        f"but runtime actions require a Windows desktop session. Requested: {action_summary}."
    )


def harden_runtime_console(*, minimize: bool, logger=None) -> None:
    if platform.system() != "Windows":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        std_input_handle = -10
        enable_extended_flags = 0x0080
        enable_quick_edit_mode = 0x0040
        enable_insert_mode = 0x0020
        enable_mouse_input = 0x0010
        show_min_no_active = 7

        input_handle = kernel32.GetStdHandle(std_input_handle)
        if input_handle not in (0, -1):
            mode = ctypes.c_uint()
            if kernel32.GetConsoleMode(input_handle, ctypes.byref(mode)):
                new_mode = mode.value | enable_extended_flags
                # 关键修复：Windows 控制台一旦进入“选择/QuickEdit”模式，
                # python 主线程会被整窗口冻结，自动化就会停在半路并出现乱点。
                # 这里直接禁掉 QuickEdit、插入模式和鼠标选择，避免误点控制台把调度器卡死。
                new_mode &= ~enable_quick_edit_mode
                new_mode &= ~enable_insert_mode
                new_mode &= ~enable_mouse_input
                if new_mode != mode.value:
                    kernel32.SetConsoleMode(input_handle, new_mode)
                    if logger:
                        logger.info("Hardened runtime console input mode=%s -> %s", mode.value, new_mode)

        if minimize:
            console_hwnd = kernel32.GetConsoleWindow()
            if console_hwnd:
                user32.ShowWindow(console_hwnd, show_min_no_active)
                if logger:
                    logger.info("Minimized runtime console hwnd=%s to avoid accidental foreground clicks", console_hwnd)
    except Exception as exc:
        if logger:
            logger.warning("Failed to harden runtime console: %s", exc)


def acquire_instance_lock(lock_name: str, *, project_root: Path) -> tuple[int | None, Path | None]:
    if not lock_name:
        return None, None

    lock_dir = project_root / "tmp" / "runtime_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in lock_name)
    lock_path = lock_dir / f"{safe_name}.lock"

    def _lock_process_matches_payload(pid: int, payload: dict[str, object]) -> bool:
        try:
            import psutil  # type: ignore

            process = psutil.Process(pid)
            cmdline = [str(part).strip() for part in process.cmdline() if str(part).strip()]
        except Exception:
            return True
        if not cmdline:
            return False
        payload_argv = payload.get("argv")
        if not isinstance(payload_argv, list):
            return True
        normalized_cmdline = [Path(part).name.lower() for part in cmdline]
        normalized_payload = [Path(str(part)).name.lower() for part in payload_argv if str(part).strip()]
        for token in normalized_payload:
            if token not in normalized_cmdline:
                return False
        return True

    def _release_stale_lock_if_present() -> None:
        if not lock_path.exists():
            return
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        pid = payload.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return
        try:
            import psutil  # type: ignore

            pid_active = psutil.pid_exists(pid)
        except Exception:
            pid_active = True
        if pid_active and _lock_process_matches_payload(pid, payload):
            return
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    _release_stale_lock_if_present()

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SystemExit(
            f"Another fixed-layout runtime is already active for lock '{lock_name}'. "
            f"If the previous process crashed, delete {lock_path} and retry."
        ) from exc

    payload = {
        "pid": os.getpid(),
        "lock_name": lock_name,
        "argv": sys.argv,
    }
    os.write(fd, (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))

    def _cleanup() -> None:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    atexit.register(_cleanup)
    return fd, lock_path


def main() -> int:
    args = parse_args()
    require_windows_runtime(args)
    enable_high_dpi_awareness()
    actions = (
        int(args.run)
        + int(bool(args.calibrate))
        + int(bool(args.inspect_calibration))
        + int(args.inspect_runtime)
        + int(args.dump_favorites)
        + int(args.switch_layout is not None)
    )
    if actions != 1:
        raise SystemExit(
            "Specify exactly one action: --run, --calibrate, --inspect-calibration, --inspect-runtime, --dump-favorites, or --switch-layout"
        )

    config = load_config(args.config)
    logger = setup_logger(config.logging, config.path.parent)
    logger.info("Loaded config from %s", config.path)
    if args.run:
        lock_fd, lock_path = acquire_instance_lock(
            config.controls.instance_lock_name,
            project_root=config.path.parent,
        )
        if lock_path is not None:
            logger.info("Acquired runtime instance lock %s", lock_path)
    if args.run:
        harden_runtime_console(minimize=True, logger=logger)
    use_status_overlay = config.status_overlay.enabled and args.switch_layout is None and not args.inspect_runtime

    from admin_utils import current_integrity_level, relaunch_as_admin
    from calibration import CalibrationManager
    from controller import Controller
    from detector import Detector
    from favorites_reader import FavoritesReader
    from grid_mapper import GridMapper
    from input_guard import InputGuard
    from layout_switcher import LayoutSwitchError, LayoutSwitcher
    from native_runtime_client import NativeRuntimeClient
    from runtime_guard import RuntimeGuard
    from scheduler import PollingScheduler
    from status_runtime import StatusPublisher
    from window_manager import WindowManager

    status_publisher = StatusPublisher(config.status_overlay, config.path, logger) if use_status_overlay else None
    native_client = NativeRuntimeClient(config.path.parent, config.window, logger) if config.window.native_runtime_enabled else None

    try:
        window_manager = WindowManager(config.window, logger, native_client=native_client)
        target_window = window_manager.find_target_window()
        current_integrity = current_integrity_level()
        logger.info(
            "Current integrity=%s target integrity=%s target hwnd=%s pid=%s",
            current_integrity.label,
            target_window.integrity_label,
            target_window.hwnd,
            target_window.process_id,
        )

        if target_window.integrity_rid > current_integrity.rid:
            logger.warning(
                "Target window is running at %s integrity and current Python process is %s. Elevation is required.",
                target_window.integrity_label,
                current_integrity.label,
            )
            if not args.no_auto_elevate and relaunch_as_admin(sys.argv, config.path.parent):
                logger.warning("Requested elevated relaunch. Accept the UAC prompt, then continue from the new console.")
                return 0
            raise SystemExit(
                "Target client is running with higher privileges. Re-run this command as administrator or allow the UAC relaunch."
            )

        if status_publisher:
            status_publisher.start()

        calibration_manager = CalibrationManager(config, window_manager, logger, status_publisher=status_publisher)
        favorites_reader = FavoritesReader(config.favorites, config.path, logger)
        detector = Detector(config.detection, logger)

        if args.calibrate:
            calibration_manager.run(args.calibrate)
            return 0
        if args.inspect_calibration:
            calibration_manager.inspect(args.inspect_calibration)
            return 0
        if args.dump_favorites:
            payload = favorites_reader.debug_dump(target_window)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.switch_layout is not None:
            controller = Controller(
                config.timing,
                logger,
                # 布局切换仍要求真实点击语义；native_engine 也走真实 Win32 输入，缺失时再退回 real_mouse。
                backend="native_engine" if config.window.native_runtime_enabled else "real_mouse",
                autohotkey_path=config.window.autohotkey_path,
                native_client=native_client,
            )
            try:
                result = LayoutSwitcher(
                    window_manager,
                    controller,
                    logger,
                    config=config,
                    detector=detector,
                    native_client=native_client,
                ).switch_layout(
                    args.switch_layout,
                    target_window=target_window,
                )
            except LayoutSwitchError as exc:
                raise SystemExit(str(exc))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        requested_mode = args.mode or config.profiles.active_mode
        if requested_mode not in {"auto", "windowed", "fullscreen"}:
            raise SystemExit("profiles.active_mode must be auto, windowed, or fullscreen")

        controller = Controller(
            config.timing,
            logger,
            backend=config.window.control_backend,
            autohotkey_path=config.window.autohotkey_path,
            native_client=native_client,
        )
        # self_test compatibility anchor:
        # runtime_layout_switcher = LayoutSwitcher(window_manager, controller, logger, config=config, detector=detector)
        runtime_layout_switcher = LayoutSwitcher(
            window_manager,
            controller,
            logger,
            config=config,
            detector=detector,
            native_client=native_client,
        )
        scheduler = PollingScheduler(
            config=config,
            window_manager=window_manager,
            grid_mapper=GridMapper(config.grid),
            detector=detector,
            controller=controller,
            input_guard=InputGuard(
                config.input_guard,
                logger,
                ignored_hotkeys={
                    config.hotkeys.profile_source_toggle,
                    config.hotkeys.mode_cycle,
                    config.hotkeys.layout_cycle,
                    config.hotkeys.grid_order_cycle,
                    config.hotkeys.start_pause,
                    config.hotkeys.next_cell,
                    config.hotkeys.stop,
                    config.hotkeys.emergency_recover,
                    config.hotkeys.calibration_capture,
                },
            ),
            logger=logger,
            requested_mode=requested_mode,
            requested_layout=args.layout,
            status_publisher=status_publisher,
            favorites_reader=favorites_reader,
            runtime_guard=RuntimeGuard(
                config.runtime_guard,
                window_manager,
                detector,
                controller,
                logger,
                config.path,
            ),
            layout_switcher=runtime_layout_switcher,
        )
        if args.inspect_runtime:
            print(
                json.dumps(
                    scheduler.inspect_runtime_state(include_candidates=args.inspect_runtime_candidates),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        logger.info(
            "Hotkey help: %s auto/manual | %s mode cycle(windowed/fullscreen) | %s layout cycle(12/9/6/4) | %s order cycle(left-right/top-down) | %s run/pause/continue | %s next while paused | %s safe-stop+exit | %s emergency-return-grid+restart-current | %s clear issue cooldown (then f2/f11)",
            config.hotkeys.profile_source_toggle,
            config.hotkeys.mode_cycle,
            config.hotkeys.layout_cycle,
            config.hotkeys.grid_order_cycle,
            config.hotkeys.start_pause,
            config.hotkeys.next_cell,
            config.hotkeys.stop,
            config.hotkeys.emergency_recover,
            config.hotkeys.clear_cooldown,
        )
        scheduler.run()
        return 0
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        if status_publisher:
            status_publisher.stop(message="Interrupted by user")
        return 130
    except SystemExit:
        raise
    except Exception:
        logger.exception("Application failed")
        if status_publisher:
            status_publisher.stop(message="Run failed")
        raise
    finally:
        if native_client is not None:
            native_client.close()


if __name__ == "__main__":
    raise SystemExit(main())
