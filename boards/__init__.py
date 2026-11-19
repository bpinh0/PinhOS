# PinhOS Phase 1 — Board Hardware Abstraction Layer Factory (boards/__init__.py)
# Selects and initializes the active board profile ("picocalc" default, or "generic_spi").

from boards.base import (
    BoardBase,
    CAP_DISPLAY,
    CAP_KEYBOARD,
    CAP_POINTER,
    CAP_SDCARD,
    CAP_BATTERY,
    CAP_BACKLIGHT,
    CAP_KB_BACKLIGHT,
    CAP_AUDIO,
    CAP_RTC,
    CAP_WIFI,
    CAP_BLE,
    MOD_NONE,
    MOD_SHIFT,
    MOD_CTRL,
    MOD_ALT,
    MOD_SYM,
    MOD_META,
    rgb565,
    rgb565_swap,
)

__all__ = [
    "BoardBase",
    "CAP_DISPLAY",
    "CAP_KEYBOARD",
    "CAP_POINTER",
    "CAP_SDCARD",
    "CAP_BATTERY",
    "CAP_BACKLIGHT",
    "CAP_KB_BACKLIGHT",
    "CAP_AUDIO",
    "CAP_RTC",
    "CAP_WIFI",
    "CAP_BLE",
    "MOD_NONE",
    "MOD_SHIFT",
    "MOD_CTRL",
    "MOD_ALT",
    "MOD_SYM",
    "MOD_META",
    "rgb565",
    "rgb565_swap",
    "DEFAULT_BOARD_PROFILE",
    "detect_board_profile",
    "create_board",
    "get_board",
]

DEFAULT_BOARD_PROFILE = "picocalc"
_active_board = None


def detect_board_profile():
    """Auto-detect board profile if not explicitly configured."""
    try:
        import picocalc as _pc  # noqa: F401
        return "picocalc"
    except Exception:
        pass
    return DEFAULT_BOARD_PROFILE


def create_board(profile=None, config=None):
    """Instantiate a board driver by profile name ('picocalc' default)."""
    cfg = config if isinstance(config, dict) else {}
    chosen = (profile or cfg.get("board") or DEFAULT_BOARD_PROFILE).strip().lower()

    if chosen in ("generic_spi", "generic", "cardkb", "st7789", "ili9341"):
        from boards.generic_spi import GenericSPIBoard
        return GenericSPIBoard(cfg)

    from boards.picocalc import PicoCalcBoard
    return PicoCalcBoard(cfg)


def get_board(profile=None, config=None, force_new=False):
    """Return the active singleton BoardBase instance, initializing it if needed."""
    global _active_board
    if _active_board is None or force_new or (profile and _active_board.id != profile):
        _active_board = create_board(profile=profile, config=config)
        _active_board.init()
    return _active_board
