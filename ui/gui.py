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
        from ui.widgets import draw_pine_logo, draw_wifi_icon, draw_battery_icon
        b = self.board
        c_acc = theme.color("accent")
        c_afg = theme.color("accent_fg")
        c_dim = theme.color("border")

        b.fill_rect(bar.x, bar.y, bar.w, bar.h, c_acc)
        draw_pine_logo(b, bar.x + 3, bar.y + max(1, (bar.h - 14) // 2), c_afg)

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

        title_x = bar.x + 19
        avail_title_px = max(0, (bar.x + bar.w - right_w - bat_w - wf_w - lnk_w - web_w - 8) - title_x)
        max_title_ch = avail_title_px // 6
        if max_title_ch > 0:
            b.text(bar.title[:max_title_ch], title_x, bar.y + 6, c_afg)

        cur_x = bar.x + bar.w - 4
        if bi is not None:
            cur_x -= 17
            ph = bi[2] if len(bi) > 2 else 0
            draw_battery_icon(b, cur_x, bar.y + max(2, (bar.h - 9) // 2), bi[0], bi[1], c_afg, c_afg, c_acc, phase=ph)
            cur_x -= 3
        if right_str:
            cur_x -= len(right_str) * 6
            b.text(right_str, cur_x, bar.y + 6, c_afg)
            cur_x -= 4
        if wl is not None:
            cur_x -= 13
            draw_wifi_icon(b, cur_x, bar.y + max(2, (bar.h - 10) // 2), wl, c_afg, c_dim)
            cur_x -= 4
        if lnk:
            cur_x -= 20
            by = bar.y + max(2, (bar.h - 12) // 2)
            b.fill_rect(cur_x, by, 20, 12, c_afg)
            b.text("LNK", cur_x + 1, by + 2, c_acc)
            cur_x -= 4
        if web_on:
            cur_x -= 20
            by = bar.y + max(2, (bar.h - 12) // 2)
            b.fill_rect(cur_x, by, 20, 12, c_afg)
            b.text("WEB", cur_x + 1, by + 2, c_acc)
            cur_x -= 4

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
            if isinstance(line, tuple):
                txt, tok = line[0], line[1]
                col = theme.color(tok, default="text")
            else:
                txt, col = line, c_txt
            b.text(str(txt)[:max_ch], tv.x + 6, y, col)
            y += 12

    def term_metrics(self, tv):
        """Return (x0, y0, line_h, cols, nrows, clear_x, clear_w) for a TermView (framed, 10px rows)."""
        lh = 10
        cols = min(53, (tv.w - 2) // 6)
        nrows = max(1, (tv.h - 6) // lh)
        return (tv.x + 1, tv.y + 3, lh, cols, nrows, tv.x + 1, tv.w - 2)

    def draw_term_view(self, tv, theme, dirty_rows=None):
        b = self.board
        geom = self.term_metrics(tv)
        if dirty_rows is None:
            c_bdr = theme.color("accent") if tv.focused else theme.color("border")
            b.fill_rect(tv.x, tv.y, tv.w, tv.h, theme.color("surface"))
            b.rect(tv.x, tv.y, tv.w, tv.h, c_bdr)
            indices = range(geom[4])
        else:
            indices = list(dirty_rows)
        tv.paint(b, theme, geom, "surface", indices)

    def _draw_tile_icon(self, kind, cx, cy, col, bg):
        b = self.board
        if kind == "dash":
            # Gauge / tachometer arc + needle
            b.rect(cx - 14, cy - 11, 28, 22, col)
            b.hline(cx - 10, cy + 5, 20, col)
            b.line(cx, cy + 5, cx + 8, cy - 6, col)
            b.fill_rect(cx - 2, cy + 3, 4, 4, col)
        elif kind == "apps":
            # Code studio window </>
            b.rect(cx - 15, cy - 11, 30, 22, col)
            b.hline(cx - 15, cy - 5, 30, col)
            b.text("</>", cx - 9, cy - 1, col)
        elif kind == "term":
            # Terminal prompt >_
            b.rect(cx - 15, cy - 11, 30, 22, col)
            b.hline(cx - 15, cy - 5, 30, col)
            b.text(">_", cx - 7, cy - 1, col)
        elif kind == "files":
            # Folder / SD tab
            b.rect(cx - 14, cy - 7, 28, 18, col)
            b.fill_rect(cx - 14, cy - 11, 12, 4, col)
            b.hline(cx - 10, cy, 20, col)
        elif kind == "net":
            # Radio / Wi-Fi fan waves
            b.fill_rect(cx - 2, cy + 7, 4, 4, col)
            b.hline(cx - 4, cy + 2, 9, col)
            b.pixel(cx - 5, cy + 3, col); b.pixel(cx + 5, cy + 3, col)
            b.hline(cx - 8, cy - 3, 17, col)
            b.line(cx - 9, cy - 2, cx - 11, cy, col)
            b.line(cx + 9, cy - 2, cx + 11, cy, col)
            b.hline(cx - 11, cy - 8, 23, col)
            b.line(cx - 12, cy - 7, cx - 14, cy - 5, col)
            b.line(cx + 12, cy - 7, cx + 14, cy - 5, col)
        elif kind == "hw":
            # IC chip + pins
            b.rect(cx - 9, cy - 9, 18, 18, col)
            b.rect(cx - 5, cy - 5, 10, 10, col)
            for off in (-6, 0, 6):
                b.hline(cx - 14, cy + off, 5, col)
                b.hline(cx + 9, cy + off, 5, col)
                b.vline(cx + off, cy - 14, 5, col)
                b.vline(cx + off, cy + 9, 5, col)
        else:
            # System gear / shield
            b.rect(cx - 11, cy - 11, 22, 22, col)
            b.rect(cx - 5, cy - 5, 10, 10, col)
            b.hline(cx - 14, cy, 3, col)
            b.hline(cx + 11, cy, 3, col)
            b.vline(cx, cy - 14, 3, col)
            b.vline(cx, cy + 11, 3, col)

    def draw_mosaic_grid(self, grid, theme, dirty_tiles=None):
        b = self.board
        c_bg = theme.color("bg")
        c_surf = theme.color("surface")
        c_bdr = theme.color("border")
        c_acc = theme.color("accent")
        c_txt = theme.color("text")
        c_sbg = theme.color("sel_bg")
        c_sfg = theme.color("sel_fg")
        c_muted = theme.color("text_muted")

        if getattr(grid, "layout", "grid") == "list":
            n = max(1, len(grid.items))
            gap = 4
            row_h = max(24, (grid.h - gap * (n - 1)) // n)
            if dirty_tiles is None:
                b.fill_rect(grid.x, grid.y, grid.w, grid.h, c_bg)
                indices = range(len(grid.items))
            else:
                indices = [i for i in dirty_tiles if 0 <= i < len(grid.items)]
            for idx in indices:
                item = grid.items[idx]
                ry = grid.y + idx * (row_h + gap)
                is_sel = (idx == grid.selected)
                fill_c = c_sbg if is_sel else c_surf
                edge_c = c_acc if is_sel else c_bdr
                fg_c = c_sfg if is_sel else c_txt
                b.fill_rect(grid.x, ry, grid.w, row_h, fill_c)
                b.rect(grid.x, ry, grid.w, row_h, edge_c)
                if is_sel:
                    b.rect(grid.x + 1, ry + 1, grid.w - 2, row_h - 2, edge_c)
                pref = "> " if is_sel else "  "
                lbl = "{}{}. {}".format(pref, idx + 1, str(item.get("label", "")))
                bdg = str(item.get("tui_badge", item.get("badge", "")))
                ty = ry + max(2, (row_h - 8) // 2)
                max_lbl = max(1, (grid.w - len(bdg) * 6 - 18) // 6)
                b.text(lbl[:max_lbl], grid.x + 8, ty, fg_c)
                if bdg:
                    bx = grid.x + grid.w - len(bdg) * 6 - 8
                    b.text(bdg, bx, ty, fg_c if is_sel else c_muted)
            return

        cols = grid.cols
        rows = max(1, (len(grid.items) + cols - 1) // cols)
        gap = 6
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
            fill_c = c_sbg if is_sel else c_surf
            edge_c = c_acc if is_sel else c_bdr
            fg_c = c_sfg if is_sel else c_txt
            ico_c = c_sfg if is_sel else (c_acc if (idx % 2 == 0) else c_txt)

            b.fill_rect(tx, ty, tw, th, fill_c)
            b.rect(tx, ty, tw, th, edge_c)
            if is_sel:
                b.rect(tx + 1, ty + 1, tw - 2, th - 2, edge_c)

            self._draw_tile_icon(item.get("icon", "sys"), tx + tw // 2, ty + 34, ico_c, fill_c)

            lbl = str(item.get("short", item.get("label", "")))[:14]
            lx = tx + max(3, (tw - len(lbl) * 6) // 2)
            b.text(lbl, lx, ty + th - 26, fg_c)

            bdg = str(item.get("badge", ""))[:12]
            if bdg:
                bx = tx + max(3, (tw - len(bdg) * 6) // 2)
                b.text(bdg, bx, ty + th - 13, fg_c if is_sel else c_muted)

    def draw_telemetry_strip(self, strip, theme):
        b = self.board
        c_surf = theme.color("surface")
        c_bdr = theme.color("border")
        c_ok = theme.color("ok")
        c_inf = theme.color("info")
        c_wrn = theme.color("warn")
        c_txt = theme.color("text")
        b.fill_rect(strip.x, strip.y, strip.w, strip.h, c_surf)
        b.rect(strip.x, strip.y, strip.w, strip.h, c_bdr)
        mid = strip.x + strip.w // 2
        b.vline(mid, strip.y + 2, strip.h - 4, c_bdr)

        # Left half: RAM label + sparkline
        b.text(strip.ram_label[:11], strip.x + 5, strip.y + (strip.h - 8) // 2, c_inf)
        sx1 = strip.x + 74
        sw1 = max(24, (mid - 4) - sx1)
        sh = strip.h - 8
        sy = strip.y + 4
        b.rect(sx1, sy, sw1, sh, c_bdr)
        rh = strip.ram_hist
        if rh:
            bw = max(2, (sw1 - 2) // max(1, strip.max_samples))
            for i, v in enumerate(rh):
                bh = max(1, (v * (sh - 2)) // 100)
                bx = sx1 + 1 + i * bw
                if bx + bw <= sx1 + sw1 - 1:
                    b.fill_rect(bx, sy + sh - 1 - bh, max(1, bw - 1), bh, c_ok if strip.ok else c_wrn)

        # Right half: CPU MHz/Temp label + sparkline
        b.text(strip.cpu_label[:13], mid + 5, strip.y + (strip.h - 8) // 2, c_txt)
        sx2 = mid + 86
        sw2 = max(24, (strip.x + strip.w - 4) - sx2)
        b.rect(sx2, sy, sw2, sh, c_bdr)
        ch = strip.cpu_hist
        if ch:
            bw = max(2, (sw2 - 2) // max(1, strip.max_samples))
            for i, v in enumerate(ch):
                bh = max(1, (v * (sh - 2)) // 100)
                bx = sx2 + 1 + i * bw
                if bx + bw <= sx2 + sw2 - 1:
                    b.fill_rect(bx, sy + sh - 1 - bh, max(1, bw - 1), bh, c_wrn if v >= 65 else c_inf)
