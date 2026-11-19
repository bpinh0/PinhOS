# PinhOS Phase 2 — High-Density Terminal UI Backend (ui/tui.py)
# Crisp monochrome/accent grid layout, dense list rows, ASCII dividers,
# and minimal draw overhead via board display primitives (zero full-screen buffers).


class TUIBackend:
    """High-density terminal rendering backend for PinhOS Dual-UI Engine."""

    mode = "tui"
    mode_badge = "TUI"

    def __init__(self, board):
        self.board = board

    def clear_screen(self, theme):
        self.board.fill(theme.color("bg"))

    def draw_status_bar(self, bar, theme):
        b = self.board
        c_bg = theme.color("bg")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")
        c_bdr = theme.color("border")

        b.fill_rect(bar.x, bar.y, bar.w, bar.h, c_bg)
        left_txt = "[{}] {}".format(bar.mode_label[:4], bar.title)
        right_str = bar.right_text or ""
        right_w = len(right_str) * 6
        max_left = max(1, (bar.w - right_w - 8) // 6)

        b.text(left_txt[:max_left], bar.x + 2, bar.y + 4, c_acc)
        if right_str:
            rx = bar.x + bar.w - right_w - 4
            b.text(right_str, rx, bar.y + 4, c_txt)
        # Double-line terminal header rule
        b.hline(bar.x, bar.y + bar.h - 3, bar.w, c_bdr)
        b.hline(bar.x, bar.y + bar.h - 1, bar.w, c_acc)

    def draw_footer_bar(self, bar, theme):
        b = self.board
        c_bg = theme.color("bg")
        c_bdr = theme.color("border")
        c_acc = theme.color("accent")
        c_stat = theme.color(bar.status_kind, default="text")

        b.fill_rect(bar.x, bar.y, bar.w, bar.h, c_bg)
        b.hline(bar.x, bar.y, bar.w, c_bdr)

        max_ch = max(1, (bar.w - 4) // 6)
        b.text("> " + bar.status[:max(1, max_ch - 2)], bar.x + 2, bar.y + 6, c_stat)
        b.hline(bar.x, bar.y + 20, bar.w, c_bdr)
        b.text(bar.hints[:max_ch], bar.x + 2, bar.y + 27, c_acc)

    def draw_panel(self, panel, theme, dirty_rows=None):
        b = self.board
        c_bg = theme.color("bg")
        c_acc = theme.color("accent")
        c_muted = theme.color("text_muted")

        header_h = 14 if panel.title else 2
        row_h = 14
        start_y = panel.y + header_h + 2
        max_rows = max(1, (panel.h - header_h - 2) // row_h)

        if dirty_rows is None:
            b.fill_rect(panel.x, panel.y, panel.w, panel.h, c_bg)
            if panel.title:
                max_ch = max(1, panel.w // 6)
                hdr = "-- {} ".format(panel.title)
                if len(hdr) < max_ch:
                    hdr = hdr + ("-" * (max_ch - len(hdr)))
                b.text(hdr[:max_ch], panel.x, panel.y + 2, c_acc)
            row_indices = range(min(len(panel.rows), max_rows))
        else:
            row_indices = [i for i in dirty_rows if 0 <= i < min(len(panel.rows), max_rows)]

        val_x = panel.x + panel.label_width
        max_lbl_ch = max(1, (panel.label_width - 4) // 6)
        max_val_ch = max(1, (panel.x + panel.w - val_x) // 6)

        for idx in row_indices:
            row = panel.rows[idx]
            lbl = str(row[0])
            val = str(row[1])
            tok = row[2] if len(row) > 2 else "text"
            ry = start_y + idx * row_h

            b.fill_rect(panel.x, ry, panel.w, row_h, c_bg)
            b.text(lbl[:max_lbl_ch], panel.x + 2, ry + 2, c_muted)
            b.text(val[:max_val_ch], val_x, ry + 2, theme.color(tok, default="text"))

    def draw_list_menu(self, menu, theme, dirty_rows=None):
        b = self.board
        c_bg = theme.color("bg")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")
        c_muted = theme.color("text_muted")
        c_sbg = theme.color("sel_bg")
        c_sfg = theme.color("sel_fg")

        header_h = 16
        row_h = 18
        vis = menu.visible_rows(row_h=row_h, header_h=header_h)
        start_y = menu.y + header_h + 2
        total = len(menu.items)
        counter_str = "[{}/{}]".format(menu.selected + 1 if total else 0, total)
        counter_x = menu.x + menu.w - (len(counter_str) * 6) - 4

        if dirty_rows is None:
            b.fill_rect(menu.x, menu.y, menu.w, menu.h, c_bg)
            max_ch = max(1, (menu.w - len(counter_str) * 6 - 8) // 6)
            hdr = "== {} ".format(menu.title)
            if len(hdr) < max_ch:
                hdr = hdr + ("=" * (max_ch - len(hdr)))
            b.text(hdr[:max_ch], menu.x, menu.y + 3, c_acc)
            b.text(counter_str, counter_x, menu.y + 3, c_muted)
            indices = range(menu.scroll_offset, min(total, menu.scroll_offset + vis))
        else:
            b.fill_rect(menu.x + menu.w - 54, menu.y + 2, 54, 11, c_bg)
            b.text(counter_str, counter_x, menu.y + 3, c_muted)
            indices = [
                i for i in dirty_rows
                if menu.scroll_offset <= i < min(total, menu.scroll_offset + vis)
            ]

        for idx in indices:
            slot = idx - menu.scroll_offset
            ry = start_y + slot * row_h
            is_sel = (idx == menu.selected)
            label = menu.item_label(idx)
            badge = menu.item_badge(idx)

            bg_col = c_sbg if is_sel else c_bg
            fg_col = c_sfg if is_sel else c_txt
            prefix = ">" if is_sel else " "

            b.fill_rect(menu.x, ry, menu.w, row_h - 2, bg_col)
            badge_w = (len(badge) * 6 + 4) if badge else 0
            max_lbl = max(1, (menu.w - 4 - badge_w) // 6 - 2)
            b.text("{} {}".format(prefix, label[:max_lbl]), menu.x + 2, ry + 4, fg_col)
            if badge:
                bx = menu.x + menu.w - len(badge) * 6 - 4
                b.text(badge, bx, ry + 4, fg_col if is_sel else c_muted)

    def draw_progress_bar(self, pbar, theme):
        b = self.board
        c_bg = theme.color("bg")
        c_fill = theme.color(pbar.color_token, default="accent")
        c_txt = theme.color("text")

        b.fill_rect(pbar.x, pbar.y, pbar.w, pbar.h, c_bg)
        max_ch = max(8, pbar.w // 6)
        suffix = " {:3d}%".format(pbar.value)
        prefix = (pbar.label + " ") if pbar.label else ""
        bar_slots = max(4, max_ch - len(prefix) - len(suffix) - 2)
        filled = (bar_slots * pbar.value) // 100
        bar_str = "[" + ("#" * filled) + ("." * (bar_slots - filled)) + "]"
        line = (prefix + bar_str + suffix)[:max_ch]
        ty = pbar.y + max(0, (pbar.h - 8) // 2)
        b.text(line, pbar.x, ty, c_fill if pbar.value > 0 else c_txt)

    def draw_dialog(self, dlg, theme):
        b = self.board
        c_bg = theme.color("bg")
        c_hdr = theme.color(dlg.kind if dlg.kind in ("ok", "warn", "err") else "accent")
        c_txt = theme.color("text")
        c_muted = theme.color("text_muted")

        b.fill_rect(dlg.x, dlg.y, dlg.w, dlg.h, c_bg)
        b.rect(dlg.x, dlg.y, dlg.w, dlg.h, c_hdr)

        max_ch = max(1, (dlg.w - 12) // 6)
        b.text("[ " + dlg.title[:max(1, max_ch - 4)] + " ]", dlg.x + 6, dlg.y + 6, c_hdr)
        b.hline(dlg.x + 2, dlg.y + 18, dlg.w - 4, c_hdr)

        ly = dlg.y + 24
        max_lines = max(1, (dlg.h - 48) // 12)
        for line in dlg.lines[:max_lines]:
            b.text(str(line)[:max_ch], dlg.x + 6, ly, c_txt)
            ly += 12

        b.hline(dlg.x + 2, dlg.y + dlg.h - 18, dlg.w - 4, c_hdr)
        b.text(dlg.footer[:max_ch], dlg.x + 6, dlg.y + dlg.h - 13, c_muted)

    def draw_text_view(self, tv, theme):
        b = self.board
        c_bg = theme.color("bg")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")

        b.fill_rect(tv.x, tv.y, tv.w, tv.h, c_bg)
        header_h = 14 if tv.title else 2
        max_ch = max(1, (tv.w - 4) // 6)
        if tv.title:
            b.text("-- " + tv.title[:max(1, max_ch - 3)], tv.x + 2, tv.y + 2, c_acc)
            b.hline(tv.x, tv.y + 12, tv.w, c_acc)

        vis = tv.visible_lines(line_h=11, header_h=header_h)
        y = tv.y + header_h + 2
        for line in tv.lines[tv.scroll_offset:tv.scroll_offset + vis]:
            b.text(str(line)[:max_ch], tv.x + 2, y, c_txt)
            y += 11
