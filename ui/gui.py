# PinhOS Phase 2 — Graphical 320x320 UI Backend (ui/gui.py)
# Renders framed cards, accent header/footer bars, bordered panels, and graphical
# progress bars directly via board display primitives (zero full-screen buffers).


class GUIBackend:
    """Graphical 320x320 rendering backend for PinhOS Dual-UI Engine."""

    mode = "gui"
    mode_badge = "GUI"

    def __init__(self, board):
        self.board = board

    def clear_screen(self, theme):
        self.board.fill(theme.color("bg"))

    def draw_status_bar(self, bar, theme):
        b = self.board
        c_acc = theme.color("accent")
        c_afg = theme.color("accent_fg")
        c_sbg = theme.color("sel_bg")
        c_sfg = theme.color("sel_fg")

        b.fill_rect(bar.x, bar.y, bar.w, bar.h, c_acc)
        # Mode pill on left (PicoCalc font is 6x8)
        pill_txt = "[{}]".format(bar.mode_label[:4])
        pill_w = len(pill_txt) * 6 + 6
        b.fill_rect(bar.x + 2, bar.y + 2, pill_w, bar.h - 4, c_sbg)
        b.text(pill_txt, bar.x + 5, bar.y + 6, c_sfg)

        # Title after pill
        title_x = bar.x + pill_w + 6
        right_str = bar.right_text or ""
        right_w = len(right_str) * 6
        avail_title_px = max(0, (bar.x + bar.w - right_w - 6) - title_x)
        max_title_ch = avail_title_px // 6
        if max_title_ch > 0:
            b.text(bar.title[:max_title_ch], title_x, bar.y + 6, c_afg)

        # Right-aligned telemetry/theme badge
        if right_str:
            rx = bar.x + bar.w - right_w - 6
            b.text(right_str, rx, bar.y + 6, c_afg)

    def draw_footer_bar(self, bar, theme):
        b = self.board
        c_surf = theme.color("surface_alt")
        c_acc = theme.color("accent")
        c_afg = theme.color("accent_fg")
        c_bdr = theme.color("border")
        c_stat = theme.color(bar.status_kind, default="text")

        top_h = bar.h // 2
        bot_h = bar.h - top_h

        # Upper status strip
        b.fill_rect(bar.x, bar.y, bar.w, top_h, c_surf)
        b.hline(bar.x, bar.y, bar.w, c_bdr)
        max_ch = max(1, (bar.w - 12) // 6)
        b.text(bar.status[:max_ch], bar.x + 6, bar.y + (top_h - 8) // 2, c_stat)

        # Lower accent hotkey bar
        by = bar.y + top_h
        b.fill_rect(bar.x, by, bar.w, bot_h, c_acc)
        b.text(bar.hints[:max_ch], bar.x + 6, by + (bot_h - 8) // 2, c_afg)

    def draw_panel(self, panel, theme, dirty_rows=None):
        b = self.board
        c_surf = theme.color("surface")
        c_bdr = theme.color("border")
        c_acc = theme.color("accent")
        c_muted = theme.color("text_muted")

        header_h = 18 if panel.title else 4
        row_h = 15
        start_y = panel.y + header_h + 2
        max_rows = max(1, (panel.h - header_h - 4) // row_h)

        if dirty_rows is None:
            # Full panel frame + header redraw
            b.fill_rect(panel.x, panel.y, panel.w, panel.h, c_surf)
            b.rect(panel.x, panel.y, panel.w, panel.h, c_bdr)
            if panel.title:
                max_t = max(1, (panel.w - 16) // 6)
                b.text(panel.title[:max_t], panel.x + 8, panel.y + 5, c_acc)
                b.hline(panel.x + 4, panel.y + 16, panel.w - 8, c_bdr)
            row_indices = range(min(len(panel.rows), max_rows))
        else:
            row_indices = [i for i in dirty_rows if 0 <= i < min(len(panel.rows), max_rows)]

        val_x = panel.x + panel.label_width
        max_lbl_ch = max(1, (panel.label_width - 10) // 6)
        max_val_ch = max(1, (panel.x + panel.w - 8 - val_x) // 6)

        for idx in row_indices:
            row = panel.rows[idx]
            lbl = str(row[0])
            val = str(row[1])
            tok = row[2] if len(row) > 2 else "text"
            ry = start_y + idx * row_h

            # Clear only this row's interior rectangle for flicker-free partial update
            b.fill_rect(panel.x + 2, ry - 1, panel.w - 4, row_h, c_surf)
            b.text(lbl[:max_lbl_ch], panel.x + 8, ry + 2, c_muted)
            b.text(val[:max_val_ch], val_x, ry + 2, theme.color(tok, default="text"))

    def draw_list_menu(self, menu, theme, dirty_rows=None):
        b = self.board
        c_surf = theme.color("surface")
        c_bdr = theme.color("accent") if menu.focused else theme.color("border")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")
        c_muted = theme.color("text_muted")
        c_sbg = theme.color("sel_bg")
        c_sfg = theme.color("sel_fg")

        header_h = 18
        row_h = 19
        vis = menu.visible_rows(row_h=row_h, header_h=header_h)
        start_y = menu.y + header_h + 3
        total = len(menu.items)
        counter_str = "[{}/{}]".format(menu.selected + 1 if total else 0, total)
        counter_x = menu.x + menu.w - (len(counter_str) * 6) - 8

        if dirty_rows is None:
            b.fill_rect(menu.x, menu.y, menu.w, menu.h, c_surf)
            b.rect(menu.x, menu.y, menu.w, menu.h, c_bdr)
            b.text(menu.title[:34], menu.x + 8, menu.y + 5, c_acc)
            b.text(counter_str, counter_x, menu.y + 5, c_muted)
            b.hline(menu.x + 4, menu.y + 16, menu.w - 8, c_bdr)
            indices = range(menu.scroll_offset, min(total, menu.scroll_offset + vis))
        else:
            # Update only the tiny counter badge in header + changed rows
            b.fill_rect(menu.x + menu.w - 56, menu.y + 3, 52, 11, c_surf)
            b.text(counter_str, counter_x, menu.y + 5, c_muted)
            indices = [
                i for i in dirty_rows
                if menu.scroll_offset <= i < min(total, menu.scroll_offset + vis)
            ]

        row_x = menu.x + 5
        row_w = menu.w - 10

        for idx in indices:
            slot = idx - menu.scroll_offset
            ry = start_y + slot * row_h
            is_sel = (idx == menu.selected)
            label = menu.item_label(idx)
            badge = menu.item_badge(idx)

            bg_col = c_sbg if is_sel else c_surf
            fg_col = c_sfg if is_sel else c_txt
            prefix = "> " if is_sel else "  "

            b.fill_rect(row_x, ry, row_w, row_h - 2, bg_col)
            if is_sel:
                b.rect(row_x, ry, row_w, row_h - 2, c_acc)

            badge_w = (len(badge) * 6 + 6) if badge else 0
            max_lbl = max(1, (row_w - 8 - badge_w) // 6 - 2)
            b.text(prefix + label[:max_lbl], row_x + 4, ry + 4, fg_col)
            if badge:
                bx = row_x + row_w - len(badge) * 6 - 4
                b.text(badge, bx, ry + 4, fg_col if is_sel else c_muted)

    def draw_progress_bar(self, pbar, theme):
        b = self.board
        c_surf = theme.color("surface")
        c_bdr = theme.color("border")
        c_fill = theme.color(pbar.color_token, default="accent")
        c_txt = theme.color("text")

        b.fill_rect(pbar.x, pbar.y, pbar.w, pbar.h, c_surf)
        b.rect(pbar.x, pbar.y, pbar.w, pbar.h, c_bdr)

        inner_w = max(0, pbar.w - 4)
        fill_w = (inner_w * pbar.value) // 100
        if fill_w > 0:
            b.fill_rect(pbar.x + 2, pbar.y + 2, fill_w, max(1, pbar.h - 4), c_fill)

        pct_txt = "{} {}%".format(pbar.label, pbar.value).strip()
        if pct_txt:
            tx = pbar.x + max(4, (pbar.w - len(pct_txt) * 6) // 2)
            ty = pbar.y + max(1, (pbar.h - 8) // 2)
            b.text(pct_txt[:max(1, (pbar.w - 8) // 6)], tx, ty, c_txt)

    def draw_dialog(self, dlg, theme):
        b = self.board
        c_bg = theme.color("bg")
        c_surf = theme.color("surface")
        c_hdr = theme.color(dlg.kind if dlg.kind in ("ok", "warn", "err") else "accent")
        c_hfg = theme.color("accent_fg")
        c_txt = theme.color("text")
        c_muted = theme.color("text_muted")

        # Subtle drop border
        b.fill_rect(dlg.x + 3, dlg.y + 3, dlg.w, dlg.h, c_bg)
        b.fill_rect(dlg.x, dlg.y, dlg.w, dlg.h, c_surf)
        b.rect(dlg.x, dlg.y, dlg.w, dlg.h, c_hdr)

        # Header bar
        b.fill_rect(dlg.x + 1, dlg.y + 1, dlg.w - 2, 20, c_hdr)
        max_ch = max(1, (dlg.w - 16) // 6)
        b.text(dlg.title[:max_ch], dlg.x + 8, dlg.y + 6, c_hfg)

        # Body lines
        ly = dlg.y + 28
        max_lines = max(1, (dlg.h - 56) // 14)
        for line in dlg.lines[:max_lines]:
            b.text(str(line)[:max_ch], dlg.x + 8, ly, c_txt)
            ly += 14

        # Footer hint
        b.hline(dlg.x + 4, dlg.y + dlg.h - 22, dlg.w - 8, c_hdr)
        b.text(dlg.footer[:max_ch], dlg.x + 8, dlg.y + dlg.h - 15, c_muted)

    def draw_text_view(self, tv, theme):
        b = self.board
        c_surf = theme.color("surface")
        c_bdr = theme.color("accent") if tv.focused else theme.color("border")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")

        b.fill_rect(tv.x, tv.y, tv.w, tv.h, c_surf)
        b.rect(tv.x, tv.y, tv.w, tv.h, c_bdr)

        header_h = 18 if tv.title else 4
        max_ch = max(1, (tv.w - 12) // 6)
        if tv.title:
            b.text(tv.title[:max_ch], tv.x + 6, tv.y + 5, c_acc)
            b.hline(tv.x + 3, tv.y + 16, tv.w - 6, c_bdr)

        vis = tv.visible_lines(line_h=12, header_h=header_h)
        y = tv.y + header_h + 4
        for line in tv.lines[tv.scroll_offset:tv.scroll_offset + vis]:
            b.text(str(line)[:max_ch], tv.x + 6, y, c_txt)
            y += 12
