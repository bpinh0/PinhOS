# PinhOS Official Sandboxed Applet: Zero-Flicker SD Audio Player (apps/audio_player.py)
# Plays PCM .wav files from /sd/music, /sd/pinhos/music, or /sd via ctx.board PWM HAL.
# Uses partial dirty-region redraws only (zero board.fill() inside the event loop).

import gc
import os
import time

APP_META = {
    "id": "audio_player",
    "name": "Audio Player",
    "version": "1.0.0",
    "category": "Media",
    "description": "Zero-flicker SD WAV audio player (62.5 kHz PWM HAL)",
    "entry": "main",
    "min_sram": 24576,
    "min_block": 16384,
    "needs_radio": False,
    "ui_modes": ["gui", "tui", "native"],
    "native_libs": [],
}

SCAN_DIRS = ("/sd/music", "/sd/pinhos/music", "/sd")
VIS_ROWS = 8


def _tok(theme, name, fallback):
    if theme is not None and hasattr(theme, "color"):
        return theme.color(name)
    return fallback


def _fmt_mmss(sec):
    s = max(0, int(sec))
    return "{:02d}:{:02d}".format(s // 60, s % 60)


def _scan_tracks():
    tracks = []
    seen = set()
    for d in SCAN_DIRS:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for fn in names:
            low = fn.lower()
            if not (low.endswith(".wav") or low.endswith(".mp3")):
                continue
            full = d.rstrip("/") + "/" + fn
            if full in seen:
                continue
            seen.add(full)
            kind = "wav" if low.endswith(".wav") else "mp3"
            tracks.append((full, fn, kind))
    return tracks


def _draw_chrome(board, c):
    board.fill(c["bg"])
    board.fill_rect(0, 0, 320, 22, c["acc"])
    board.text("PINHOS AUDIO PLAYER [PWM WAV]", 10, 7, c["afg"])
    # Now Playing card frame
    board.fill_rect(8, 28, 304, 78, c["surf"])
    board.rect(8, 28, 304, 78, c["bdr"])
    # Playlist card frame
    board.fill_rect(8, 112, 304, 168, c["surf"])
    board.rect(8, 112, 304, 168, c["bdr"])
    board.text("SD TRACKS (/sd/music, /sd)", 16, 118, c["acc"])
    board.hline(12, 130, 296, c["bdr"])
    # Footer bar frame
    board.fill_rect(8, 286, 304, 26, c["surf"])
    board.rect(8, 286, 304, 26, c["acc"])
    board.show()


def _draw_now_playing(board, c, track, st, playing):
    board.fill_rect(10, 30, 300, 74, c["surf"])
    badge = "PLAYING" if playing else "STOPPED"
    bcol = c["ok"] if playing else c["mut"]
    board.text("NOW " + badge, 16, 36, bcol)
    if st.get("rate"):
        fmt = "{}Hz {}b {}".format(st["rate"], st["bits"], "ST" if st["ch"] == 2 else "MO")
        board.text(fmt[:20], 178, 36, c["mut"])
    if track:
        board.text(track[1][:34], 16, 52, c["txt"])
    else:
        board.text("No .wav files found on /sd", 16, 52, c["mut"])
    # Progress bar + MM:SS / MM:SS
    pos_s = int(st.get("pos_s", 0))
    dur_s = int(st.get("dur_s", 0))
    bx, by, bw, bh = 16, 70, 288, 10
    board.fill_rect(bx, by, bw, bh, c["bg"])
    board.rect(bx, by, bw, bh, c["bdr"])
    if dur_s > 0 and pos_s > 0:
        fw = min(bw - 2, max(2, ((bw - 2) * pos_s) // dur_s))
        board.fill_rect(bx + 1, by + 1, fw, bh - 2, c["ok"] if playing else c["acc"])
    board.text("{} / {}".format(_fmt_mmss(pos_s), _fmt_mmss(dur_s)), 16, 86, c["txt"])
    board.text("Vol: HW Wheel", 206, 86, c["mut"])
    board.show()


def _draw_playlist(board, c, tracks, sel, scroll, playing_path):
    board.fill_rect(10, 132, 300, 146, c["surf"])
    if not tracks:
        board.text("Drop 8/16-bit PCM .wav files in", 18, 154, c["mut"])
        board.text("/sd/music/ or /sd/pinhos/music/", 18, 170, c["acc"])
        board.text("Press [R] to rescan SD card.", 18, 194, c["txt"])
        board.show()
        return
    end = min(len(tracks), scroll + VIS_ROWS)
    for row, idx in enumerate(range(scroll, end)):
        full, fn, kind = tracks[idx]
        y = 136 + row * 17
        is_sel = (idx == sel)
        is_cur = (playing_path == full)
        if is_sel:
            board.fill_rect(12, y - 1, 296, 15, c["sbg"])
            fg = c["sfg"]
        else:
            fg = c["ok"] if is_cur else (c["txt"] if kind == "wav" else c["mut"])
        mark = ">" if is_cur else ("*" if is_sel else " ")
        tag = "[WAV]" if kind == "wav" else "[MP3]"
        board.text("{} {}".format(mark, fn[:28]), 16, y + 2, fg)
        board.text(tag, 268, y + 2, fg if is_sel else (c["acc"] if kind == "wav" else c["wrn"]))
    board.show()


def _draw_footer(board, c, msg, kind="info"):
    board.fill_rect(10, 288, 300, 22, c["surf"])
    col = c["err"] if kind == "err" else (c["wrn"] if kind == "warn" else (c["ok"] if kind == "ok" else c["txt"]))
    txt = msg if msg else "[ENT]Play [N/P]Trk [R]Scan [ESC]Exit"
    board.text(txt[:37], 16, 295, col)
    board.show()


def main(ctx):
    board = ctx.board
    theme = getattr(ctx, "theme", None)
    if board is None:
        return {"ok": False, "reason": "no_board"}

    c = {
        "bg": _tok(theme, "bg", 0),
        "surf": _tok(theme, "surface", 1),
        "bdr": _tok(theme, "border", 2),
        "acc": _tok(theme, "accent", 3),
        "afg": _tok(theme, "accent_fg", 4),
        "txt": _tok(theme, "text", 15),
        "mut": _tok(theme, "text_muted", 6),
        "ok": _tok(theme, "ok", 10),
        "wrn": _tok(theme, "warn", 11),
        "err": _tok(theme, "err", 12),
        "sbg": _tok(theme, "sel_bg", 3),
        "sfg": _tok(theme, "sel_fg", 0),
    }

    tracks = _scan_tracks()
    saved = ctx.load_state(default={"sel": 0})
    sel = int(saved.get("sel", 0)) if isinstance(saved, dict) else 0
    if tracks:
        sel = max(0, min(sel, len(tracks) - 1))
    else:
        sel = 0
    scroll = max(0, sel - VIS_ROWS + 1)
    playing_path = None
    last_pos_s = -1

    def _status():
        if hasattr(board, "audio_status"):
            return board.audio_status()
        return {"playing": False, "pos_s": 0, "dur_s": 0, "rate": 0, "ch": 0, "bits": 0, "error": ""}

    def _start_track(idx):
        nonlocal playing_path, last_pos_s
        if not tracks or idx < 0 or idx >= len(tracks):
            return
        full, fn, kind = tracks[idx]
        if kind == "mp3":
            board.stop_audio()
            playing_path = None
            _draw_now_playing(board, c, tracks[idx], _status(), False)
            _draw_playlist(board, c, tracks, sel, scroll, playing_path)
            _draw_footer(board, c, "WAV only (MP3 needs C codec)", "warn")
            return
        gc.collect()
        ok = board.play_audio(full) if hasattr(board, "play_audio") else False
        st = _status()
        if ok:
            playing_path = full
            last_pos_s = -1
            ctx.log("Play: " + fn[:32])
            _draw_now_playing(board, c, tracks[idx], st, True)
            _draw_playlist(board, c, tracks, sel, scroll, playing_path)
            _draw_footer(board, c, "", "info")
        else:
            playing_path = None
            err = st.get("error") or "Unsupported WAV format"
            _draw_now_playing(board, c, tracks[idx], st, False)
            _draw_playlist(board, c, tracks, sel, scroll, playing_path)
            _draw_footer(board, c, err, "err")

    _draw_chrome(board, c)
    _draw_now_playing(board, c, tracks[sel] if tracks else None, _status(), False)
    _draw_playlist(board, c, tracks, sel, scroll, playing_path)
    _draw_footer(board, c, "", "info")

    if hasattr(board, "clear_input"):
        board.clear_input()
    poll_fn = getattr(board, "poll_key", None) or getattr(board, "read_key", None)

    try:
        while True:
            is_play = hasattr(board, "audio_playing") and board.audio_playing()
            if hasattr(ctx, "yield_"):
                ctx.yield_(step_web=not is_play)
            now_play = hasattr(board, "audio_playing") and board.audio_playing()
            if is_play and not now_play:
                # Track finished cleanly -> advance or update UI
                playing_path = None
                _draw_now_playing(board, c, tracks[sel] if tracks else None, _status(), False)
                _draw_playlist(board, c, tracks, sel, scroll, playing_path)
            elif now_play:
                st = _status()
                ps = int(st.get("pos_s", 0))
                if ps != last_pos_s:
                    last_pos_s = ps
                    _draw_now_playing(board, c, tracks[sel] if tracks else None, st, True)

            k = poll_fn() if poll_fn else None
            if not k:
                if not now_play:
                    if hasattr(time, "sleep_ms"):
                        time.sleep_ms(25)
                    else:
                        time.sleep(0.025)
                continue

            ku = str(k).upper()
            if ku in ("ESC", "Q", "BACK", "BACKSPACE"):
                board.stop_audio()
                board.beep(900, 10)
                break
            elif ku == "UP" and tracks:
                sel = (sel - 1) % len(tracks)
                if sel < scroll:
                    scroll = sel
                elif sel >= scroll + VIS_ROWS:
                    scroll = max(0, sel - VIS_ROWS + 1)
                _draw_playlist(board, c, tracks, sel, scroll, playing_path)
            elif ku == "DOWN" and tracks:
                sel = (sel + 1) % len(tracks)
                if sel < scroll:
                    scroll = sel
                elif sel >= scroll + VIS_ROWS:
                    scroll = max(0, sel - VIS_ROWS + 1)
                _draw_playlist(board, c, tracks, sel, scroll, playing_path)
            elif ku in ("ENTER", "RETURN", "SPACE", " ") and tracks:
                if now_play and playing_path == tracks[sel][0]:
                    board.stop_audio()
                    playing_path = None
                    _draw_now_playing(board, c, tracks[sel], _status(), False)
                    _draw_playlist(board, c, tracks, sel, scroll, playing_path)
                else:
                    _start_track(sel)
            elif ku == "N" and tracks:
                sel = (sel + 1) % len(tracks)
                if sel >= scroll + VIS_ROWS:
                    scroll = max(0, sel - VIS_ROWS + 1)
                elif sel < scroll:
                    scroll = sel
                _start_track(sel)
            elif ku == "P" and tracks:
                sel = (sel - 1) % len(tracks)
                if sel < scroll:
                    scroll = sel
                elif sel >= scroll + VIS_ROWS:
                    scroll = max(0, sel - VIS_ROWS + 1)
                _start_track(sel)
            elif ku == "R":
                board.stop_audio()
                playing_path = None
                tracks = _scan_tracks()
                sel = min(sel, max(0, len(tracks) - 1))
                scroll = max(0, sel - VIS_ROWS + 1)
                _draw_now_playing(board, c, tracks[sel] if tracks else None, _status(), False)
                _draw_playlist(board, c, tracks, sel, scroll, playing_path)
                _draw_footer(board, c, "Found {} track(s)".format(len(tracks)), "ok")
    finally:
        if hasattr(board, "stop_audio"):
            board.stop_audio()
        ctx.save_state({"sel": sel})
        gc.collect()

    return {"app_id": ctx.app_id, "tracks": len(tracks), "sel": sel}
