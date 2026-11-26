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
        from ui.widgets import draw_pine_logo, draw_wifi_icon, draw_battery_icon
        b = self.board
        c_bg = theme.color("bg")
        c_acc = theme.color("accent")
        c_afg = theme.color("accent_fg")
        c_txt = theme.color("text")
        c_bdr = theme.color("border")

        b.fill_rect(bar.x, bar.y, bar.w, bar.h, c_bg)
        draw_pine_logo(b, bar.x + 2, bar.y + 1, c_acc)
        left_x = bar.x + 18
        right_str = bar.right_text or ""
        right_w = (len(right_str) * 6 + 4) if right_str else 0
        wl = getattr(bar, "wifi_level", None)
        bi = getattr(bar, "bat_info", None)
        lnk = bool(getattr(bar, "serial_link", False))
        web_on = bool(getattr(bar, "web_active", False))
        bat_w = 20 if bi is not None else 0
        wf_w = 17 if wl is not None else 0
        lnk_w = 24 if lnk else 0
        web_w = 24 if web_on else 0
        max_left = max(1, (bar.w - left_x - right_w - bat_w - wf_w - lnk_w - web_w - 6) // 6)
        t_title = theme.format_header(bar.title) if hasattr(theme, "format_header") else str(bar.title)

        b.text(t_title[:max_left], left_x, bar.y + 4, c_acc)
        cur_x = bar.x + bar.w - 3
        if bi is not None:
            cur_x -= 17
            fill_c = theme.color("ok" if (bi[1] or bi[0] > 25) else "err")
            ph = bi[2] if len(bi) > 2 else 0
            draw_battery_icon(b, cur_x, bar.y + 3, bi[0], bi[1], c_txt, fill_c, c_bg, phase=ph)
            cur_x -= 3
        if right_str:
            cur_x -= len(right_str) * 6
            b.text(right_str, cur_x, bar.y + 4, c_txt)
            cur_x -= 4
        if wl is not None:
            cur_x -= 13
            draw_wifi_icon(b, cur_x, bar.y + 3, wl, c_acc, c_bdr)
            cur_x -= 4
        if lnk:
            cur_x -= 20
            b.fill_rect(cur_x, bar.y + 2, 20, 11, c_acc)
            b.text("LNK", cur_x + 1, bar.y + 4, c_afg)
            cur_x -= 4
        if web_on:
            cur_x -= 20
            b.fill_rect(cur_x, bar.y + 2, 20, 11, c_acc)
            b.text("WEB", cur_x + 1, bar.y + 4, c_afg)
            cur_x -= 4
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
        from ui.widgets import draw_styled_bar
        b = self.board
        c_bg = theme.color("bg")
        c_fill = theme.color(pbar.color_token, default="accent")
        c_txt = theme.color("text")
        bar_style = theme.style_token("bar_style", "solid") if hasattr(theme, "style_token") else "solid"

        b.fill_rect(pbar.x, pbar.y, pbar.w, pbar.h, c_bg)
        max_ch = max(8, pbar.w // 6)
        suffix = " {:3d}%".format(pbar.value)
        prefix = (pbar.label + " ") if pbar.label else ""
        bar_slots = max(4, max_ch - len(prefix) - len(suffix) - 2)
        filled = (bar_slots * pbar.value) // 100
        ch_on = "=" if bar_style == "striped" else "#"
        ch_off = "-" if bar_style == "striped" else "."
        bar_str = "[" + (ch_on * filled) + (ch_off * (bar_slots - filled)) + "]"
        line = (prefix + bar_str + suffix)[:max_ch]
        ty = pbar.y + max(0, (pbar.h - 8) // 2)
        b.text(line, pbar.x, ty, c_fill if pbar.value > 0 else c_txt)

    def draw_dialog(self, dlg, theme):
        from ui.widgets import draw_styled_frame
        b = self.board
        c_bg = theme.color("bg")
        c_hdr = theme.color(dlg.kind if dlg.kind in ("ok", "warn", "err") else "accent")
        c_txt = theme.color("text")
        c_muted = theme.color("text_muted")
        bdr_style = theme.style_token("border_style", "single") if hasattr(theme, "style_token") else "single"
        title_s = theme.format_header(dlg.title) if hasattr(theme, "format_header") else str(dlg.title)

        b.fill_rect(dlg.x, dlg.y, dlg.w, dlg.h, c_bg)
        draw_styled_frame(b, dlg.x, dlg.y, dlg.w, dlg.h, c_hdr, bg_col=c_bg, style=bdr_style)

        max_ch = max(1, (dlg.w - 12) // 6)
        b.text("[ " + title_s[:max(1, max_ch - 4)] + " ]", dlg.x + 6, dlg.y + 6, c_hdr)
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
            if isinstance(line, tuple):
                txt, tok = line[0], line[1]
                col = theme.color(tok, default="text")
            else:
                txt, col = line, c_txt
            b.text(str(txt)[:max_ch], tv.x + 2, y, col)
            y += 11

    def term_metrics(self, tv):
        """Return (x0, y0, line_h, cols, nrows, clear_x, clear_w) for a TermView (full-density, 8px rows)."""
        lh = 8
        cols = min(53, tv.w // 6)
        nrows = max(1, (tv.h - 2) // lh)
        return (tv.x, tv.y + 1, lh, cols, nrows, tv.x, tv.w)

    def draw_term_view(self, tv, theme, dirty_rows=None):
        b = self.board
        geom = self.term_metrics(tv)
        if dirty_rows is None:
            b.fill_rect(tv.x, tv.y, tv.w, tv.h, theme.color("bg"))
            indices = range(geom[4])
        else:
            indices = list(dirty_rows)
        tv.paint(b, theme, geom, "bg", indices)

    def draw_mosaic_grid(self, grid, theme, dirty_tiles=None):
        """Render the 6 launcher categories in either TUI 3x2 GRID or TUI 1-6 LIST."""
        b = self.board
        c_bg = theme.color("bg")
        c_bdr = theme.color("border")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")
        c_muted = theme.color("text_muted")
        c_sbg = theme.color("sel_bg")
        c_sfg = theme.color("sel_fg")

        if getattr(grid, "layout", "list") == "grid":
            cols = grid.cols
            rows = max(1, (len(grid.items) + cols - 1) // cols)
            gap = 4
            tw = (grid.w - gap * (cols - 1)) // cols
            th = (grid.h - gap * (rows - 1)) // rows
            if dirty_tiles is None:
                b.fill_rect(grid.x, grid.y, grid.w, grid.h, c_bg)
                indices = range(len(grid.items))
            else:
                indices = [i for i in dirty_tiles if 0 <= i < len(grid.items)]
            for idx in indices:
                item = grid.items[idx]
                r, c = idx // cols, idx % cols
                tx = grid.x + c * (tw + gap)
                ty = grid.y + r * (th + gap)
                is_sel = (idx == grid.selected)
                fill_c = c_sbg if is_sel else c_bg
                fg_c = c_sfg if is_sel else c_txt
                b.fill_rect(tx, ty, tw, th, fill_c)
                b.rect(tx, ty, tw, th, c_acc if is_sel else c_bdr)
                num = "[{}]".format(idx + 1)
                b.text(num, tx + 5, ty + 6, fg_c if is_sel else c_acc)
                bdg = str(item.get("tui_badge", item.get("badge", "")))[:10]
                if bdg:
                    b.text(bdg, tx + max(4, tw - len(bdg) * 6 - 5), ty + 6, fg_c if is_sel else c_muted)
                b.hline(tx + 2, ty + 18, tw - 4, c_acc if is_sel else c_bdr)
                lbl = str(item.get("short", item.get("label", "")))[:14]
                lx = tx + max(4, (tw - len(lbl) * 6) // 2)
                b.text(lbl, lx, ty + th // 2 + 2, fg_c)
                mark = ">> OPEN <<" if is_sel else ""
                if mark:
                    mx = tx + max(4, (tw - len(mark) * 6) // 2)
                    b.text(mark, mx, ty + th - 14, fg_c)
            return

        row_h = max(18, (grid.h - 8) // max(1, len(grid.items)))
        if dirty_tiles is None:
            b.fill_rect(grid.x, grid.y, grid.w, grid.h, c_bg)
            b.rect(grid.x, grid.y, grid.w, grid.h, c_bdr)
            indices = range(len(grid.items))
        else:
            indices = [i for i in dirty_tiles if 0 <= i < len(grid.items)]

        for idx in indices:
            item = grid.items[idx]
            ry = grid.y + 4 + idx * row_h
            is_sel = (idx == grid.selected)
            bg_c = c_sbg if is_sel else c_bg
            fg_c = c_sfg if is_sel else c_txt
            b.fill_rect(grid.x + 2, ry, grid.w - 4, row_h - 2, bg_c)

            pref = ">" if is_sel else " "
            lbl = "{} {}. {}".format(pref, idx + 1, str(item.get("label", "")))
            bdg = str(item.get("tui_badge", item.get("badge", "")))
            max_lbl = max(1, (grid.w - len(bdg) * 6 - 16) // 6)
            b.text(lbl[:max_lbl], grid.x + 6, ry + (row_h - 10) // 2, fg_c)
            if bdg:
                bx = grid.x + grid.w - len(bdg) * 6 - 6
                b.text(bdg, bx, ry + (row_h - 10) // 2, fg_c if is_sel else c_acc)

    def draw_telemetry_strip(self, strip, theme):
        b = self.board
        c_bg = theme.color("bg")
        c_bdr = theme.color("border")
        c_ok = theme.color("ok")
        c_inf = theme.color("info")
        c_wrn = theme.color("warn")
        c_txt = theme.color("text")
        b.fill_rect(strip.x, strip.y, strip.w, strip.h, c_bg)
        b.rect(strip.x, strip.y, strip.w, strip.h, c_bdr)
        mid = strip.x + strip.w // 2
        b.vline(mid, strip.y + 2, strip.h - 4, c_bdr)

        b.text(strip.ram_label[:11], strip.x + 4, strip.y + (strip.h - 8) // 2, c_inf)
        sx1 = strip.x + 74
        sw1 = max(24, (mid - 4) - sx1)
        sh = strip.h - 8
        sy = strip.y + 4
        b.rect(sx1, sy, sw1, sh, c_bdr)
        if strip.ram_hist:
            bw = max(2, (sw1 - 2) // max(1, strip.max_samples))
            for i, v in enumerate(strip.ram_hist):
                bh = max(1, (v * (sh - 2)) // 100)
                bx = sx1 + 1 + i * bw
                if bx + bw <= sx1 + sw1 - 1:
                    b.fill_rect(bx, sy + sh - 1 - bh, max(1, bw - 1), bh, c_ok if strip.ok else c_wrn)

        b.text(strip.cpu_label[:13], mid + 4, strip.y + (strip.h - 8) // 2, c_txt)
        sx2 = mid + 86
        sw2 = max(24, (strip.x + strip.w - 4) - sx2)
        b.rect(sx2, sy, sw2, sh, c_bdr)
        if strip.cpu_hist:
            bw = max(2, (sw2 - 2) // max(1, strip.max_samples))
            for i, v in enumerate(strip.cpu_hist):
                bh = max(1, (v * (sh - 2)) // 100)
                bx = sx2 + 1 + i * bw
                if bx + bw <= sx2 + sw2 - 1:
                    b.fill_rect(bx, sy + sh - 1 - bh, max(1, bw - 1), bh, c_wrn if v >= 65 else c_inf)
