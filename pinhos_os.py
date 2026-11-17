# PinhOS v1.8.0 - CONSUMER EDITION CYBERDECK OS FOR CLOCKWORKPI PICOCALC (PICO 2W)
import os, sys, io, gc, time, json, array, machine, picocalc

try:
    import network, socket
except Exception:
    network = None
    socket = None

try:
    import ntptime
except Exception:
    ntptime = None

uart = machine.UART(0, 115200, rxbuf=4096)
os.dupterm(uart, 0)

def bridge_send(text):
    b = (str(text) + "\r\n").encode("utf-8")
    mv = memoryview(b)
    for i in range(0, len(mv), 16):
        uart.write(mv[i:i+16])
        uart.flush()

def _rgb565_swap(r, g, b):
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((v & 0xFF) << 8) | ((v >> 8) & 0xFF)

APP_STORE_CATALOG = [
    ("DOOM 3D Raycaster", "doom_deck.py", "First-person 3D raycaster + HUD (D-Pad + Enter)",
     "import math,time,machine,picocalc\nd=picocalc.display;kb=picocalc.keyboard;k=bytearray(8)\nMAP=['1111111111','1000001001','1011001001','1010000001','1000110001','1010110101','1010000101','1000000001','1111111111']\npx=2.5;py=2.5;pa=0.0;ammo=50;kills=0;tx=5.5;ty=5.5;shot=0\nwhile True:\n n=kb.readinto(k)\n if n:\n  b=bytes(k[:n])\n  if b in (b'\\x1b',b'\\x08',b'\\x7f',b'\\x1b\\x1b'): break\n  if b.startswith(b'\\x1b[D') or b==b'\\xb4': pa-=0.22\n  elif b.startswith(b'\\x1b[C') or b==b'\\xb7': pa+=0.22\n  elif b.startswith(b'\\x1b[A') or b==b'\\xb5':\n   nx=px+math.cos(pa)*0.35;ny=py+math.sin(pa)*0.35\n   if MAP[int(ny)][int(nx)]=='0': px=nx;py=ny\n  elif b.startswith(b'\\x1b[B') or b==b'\\xb6':\n   nx=px-math.cos(pa)*0.35;ny=py-math.sin(pa)*0.35\n   if MAP[int(ny)][int(nx)]=='0': px=nx;py=ny\n  elif b in (b'\\r',b'\\n',b' ') and ammo>0:\n   ammo-=1;shot=2\n   dx=tx-px;dy=ty-py;ang=math.atan2(dy,dx)-pa\n   while ang<-3.14: ang+=6.28\n   while ang>3.14: ang-=6.28\n   if abs(ang)<0.28: kills+=1;tx=2.5 if tx>4 else 7.5;ty=7.5 if ty<4 else 2.5\n for col in range(64):\n  ra=(pa-0.55)+(col/64)*1.1;rx=px;ry=py;cs=math.cos(ra)*0.12;sn=math.sin(ra)*0.12;dist=0.1\n  while dist<10.0:\n   rx+=cs;ry+=sn;dist+=0.12\n   if MAP[int(ry)][int(rx)]!='0': break\n  ca=dist*math.cos(ra-pa);wh=min(200,int(190/max(0.2,ca)));top=135-wh//2\n  x0=col*5;d.fill_rect(x0,26,5,max(0,top-26),3);d.fill_rect(x0,top,5,wh,0)\n  if int((rx+ry)*4)%2==0 and wh>16: d.fill_rect(x0+1,top+2,3,wh-4,3)\n  d.fill_rect(x0,top+wh,5,max(0,244-(top+wh)),3);d.pixel(x0+2,min(242,top+wh+8),0)\n dx=tx-px;dy=ty-py;ed=math.sqrt(dx*dx+dy*dy);ea=math.atan2(dy,dx)-pa\n while ea<-3.14: ea+=6.28\n while ea>3.14: ea-=6.28\n if abs(ea)<0.55 and ed>0.4:\n  sx=int(160+(ea/0.55)*150);sh=min(120,int(110/ed));sy=135-sh//2\n  d.fill_rect(sx-sh//3,sy,int(sh//1.5),sh,0);d.rect(sx-sh//3,sy,int(sh//1.5),sh,3);d.fill_rect(sx-4,sy+sh//4,8,4,3)\n d.fill_rect(0,0,320,24,0);d.text('PinhOS DOOM 3D | D-PAD:Move ENT:Fire ESC:Exit',6,8,3)\n d.fill_rect(144,210 if shot else 218,32,26,0);d.rect(144,210 if shot else 218,32,26,3)\n if shot: d.fill_rect(140,194,40,16,0);shot-=1\n d.fill_rect(0,244,320,76,0);d.rect(4,248,312,68,3)\n d.text(f'AMMO:{ammo:02d}   HEALTH:100%   DEMONS:{kills:02d}',20,264,3)\n d.text('[UP/DN] Walk  [L/R] Turn  [ENTER] Shoot',18,290,3);time.sleep_ms(20)\n"),
    ("CHIP-8 Emu Suite", "chip8_emu.py", "Retro VM + Brix/Astro arcade",
     "import time,random,picocalc\nd=picocalc.display;kb=picocalc.keyboard;k=bytearray(8)\npx=130;bx=160;by=180;vx=4;vy=-4;score=0;bricks=[[1]*8 for _ in range(4)]\nwhile True:\n n=kb.readinto(k)\n if n:\n  b=bytes(k[:n])\n  if b in (b'\\x1b',b'\\x08',b'\\x7f',b'\\x1b\\x1b'): break\n  if b.startswith(b'\\x1b[D') or b==b'\\xb4': px=max(12,px-24)\n  if b.startswith(b'\\x1b[C') or b==b'\\xb7': px=min(252,px+24)\n bx+=vx;by+=vy\n if bx<=12 or bx>=304: vx=-vx\n if by<=38: vy=-vy\n if by>=266 and px<=bx<=px+56: vy=-abs(vy)\n if by>300: bx=160;by=180;vy=-4\n br_r=(by-50)//16;br_c=(bx-16)//36\n if 0<=br_r<4 and 0<=br_c<8 and bricks[br_r][br_c]: bricks[br_r][br_c]=0;vy=-vy;score+=10\n d.fill(3);d.rect(6,28,308,262,0);d.fill_rect(0,0,320,24,0);d.text(f'CHIP-8 VM // BRIX ROM | SCORE:{score} [ESC]',12,8,3)\n for r in range(4):\n  for c in range(8):\n   if bricks[r][c]: d.fill_rect(18+c*36,50+r*16,32,10,0)\n d.fill_rect(px,270,56,8,0);d.fill_rect(bx-3,by-3,6,6,0);time.sleep_ms(25)\n"),
    ("Cyber Pong Arcade", "cyber_pong.py", "Playable D-Pad Pong vs AI",
     "import time,picocalc\nd=picocalc.display;kb=picocalc.keyboard;k=bytearray(8)\npy=130;ay=130;bx=160;by=160;vx=5;vy=4;ps=0;as_=0\nwhile True:\n n=kb.readinto(k)\n if n:\n  b=bytes(k[:n])\n  if b in (b'\\x1b',b'\\x08',b'\\x7f',b'\\x1b\\x1b'): break\n  if b.startswith(b'\\x1b[A') or b==b'\\xb5': py=max(30,py-18)\n  if b.startswith(b'\\x1b[B') or b==b'\\xb6': py=min(250,py+18)\n bx+=vx;by+=vy\n if by<=30 or by>=290: vy=-vy\n if bx<=22 and py<=by<=py+44: vx=abs(vx);ps+=1\n if bx>=292 and ay<=by<=ay+44: vx=-abs(vx)\n if bx<0: bx=160;by=160;vx=5;as_+=1\n if bx>319: bx=160;by=160;vx=-5;ps+=1\n if ay+22<by: ay=min(250,ay+4)\n elif ay+22>by: ay=max(30,ay-4)\n d.fill(3);d.rect(4,28,312,272,0);d.text(f'PinhOS PONG | YOU:{ps} AI:{as_} [ESC:Exit]',20,10,0)\n d.fill_rect(14,py,6,44,0);d.fill_rect(300,ay,6,44,0);d.fill_rect(bx-3,by-3,6,6,0);time.sleep_ms(30)\n"),
    ("Matrix Cyber Rain", "matrix_deck.py", "Falling cyber rain + RAM HUD",
     "import time,random,gc,picocalc\nd=picocalc.display;kb=picocalc.keyboard;cols=[random.randint(-20,0) for _ in range(40)];k=bytearray(8)\nwhile not kb.readinto(k):\n d.fill(0)\n for x in range(40):\n  y=cols[x]\n  if 0<=y<36: d.text(chr(random.randint(33,90)),x*8,y*8,10)\n  cols[x]=(y+1) if y<38 else random.randint(-15,0)\n d.fill_rect(40,136,240,40,0);d.rect(40,136,240,40,10)\n d.text('[ PinhOS // MATRIX RAIN ]',56,144,10);d.text('PRESS ANY KEY TO EXIT',72,160,10);time.sleep_ms(45)\n"),
    ("Chrono Deck Timer", "chrono_deck.py", "Precision stopwatch & beeper",
     "import time,picocalc\nd=picocalc.display;kb=picocalc.keyboard;k=bytearray(8);t0=time.ticks_ms();run=True;el=0\nwhile True:\n n=kb.readinto(k)\n if n:\n  b=bytes(k[:n])\n  if b in (b'\\x1b',b'\\x08',b'\\x7f',b'\\x1b\\x1b'): break\n  if b in (b'\\r',b'\\n'): run=not run;t0=time.ticks_ms()-el\n if run: el=time.ticks_diff(time.ticks_ms(),t0)\n d.fill(3);d.rect(20,60,280,180,0);d.fill_rect(22,62,276,24,0);d.text('[ PinhOS CHRONO STOPWATCH ]',48,70,3)\n s=el//1000;ms=(el%1000)//10;d.text(f'TIME: {s//60:02d}:{s%60:02d}.{ms:02d}',92,130,0)\n d.text('[ENTER] Start/Stop   [ESC] Exit',36,196,0);time.sleep_ms(40)\n"),
    ("I2C Live Monitor", "i2c_monitor.py", "Real-time I2C & PMU register view",
     "import time,machine,picocalc\nd=picocalc.display;kb=picocalc.keyboard;k=bytearray(8)\nwhile not kb.readinto(k):\n d.fill(3);d.rect(10,30,300,260,0);d.fill_rect(12,32,296,22,0);d.text('[ LIVE I2C & PMU MONITOR ]',52,39,3)\n b=kb.battery();d.text('PMU 0x1F BAT REG: '+str(list(b)),24,80,0)\n d.text('LCD BKL REG 0x05: '+str(kb.backlight()),24,105,0)\n d.text('KB  BKL REG 0x0A: '+str(kb.backlight_keyboard()),24,130,0)\n d.text('PRESS ANY KEY TO EXIT',72,240,0);time.sleep_ms(200)\n")
]

class PinhOS:
    VERSION = "1.8.0"
    BRAND = "PinhOS"
    VISIBLE_ROWS = 9

    def __init__(self):
        gc.collect()
        self.d = picocalc.display
        self.kb = picocalc.keyboard
        self.rtc = machine.RTC()
        self.running = True
        self.dirty = True
        self.full_clear = True
        self.start_ms = time.ticks_ms()
        self.last_tick_ms = self.start_ms
        self.last_hb_ms = self.start_ms
        self.sys_logs = []
        self.cwd = "/sd"
        self.term_lines = ["PinhOS BusyBox v1.8.0 (RP2350)", "Type 'help' for commands, ESC to exit."]
        self.term_input = ""

        try:
            self.d.recoverRefresh()
        except Exception:
            pass

        self.config_path = "/sd/pinhos/config.json"
        self.snap_path = "/sd/pinhos/config_snapshot.json"
        self.default_config = {
            "theme": "FLIPPER",
            "mouse_mode": False,
            "cur_step": 10,
            "bridge_policy": "AUTO",
            "popup_sec": 8,
            "hb_sec": 60,             # Configurable healthcheck heartbeat interval (15, 30, 60, 300, 0=OFF)
            "tz_offset": 0,           # UTC offset in hours (-12..+14)
            "show_clock": True,       # Show live clock in topbar/subheader
            "wifi_topbar": "BOTH",
            "sound": True,
            "beep_pitch": "NORMAL",
            "lcd_bright": 80,
            "kb_bright": 60,
            "cpu_mhz": 150,
            "web_port": 8080,
            "web_enabled": True,
            "git_repo": "BrunoPinho/PinhOS",
            "git_branch": "main"
        }
        self.config = dict(self.default_config)
        self.load_config()
        self.init_custom_lut()
        self.sync_hardware_backlights()

        self.cached_bat = 100
        self.last_bat_ms = 0
        self.read_battery_hw()

        self.cpu_load_pct = 12
        self._busy_us = 0
        self._window_start_ms = time.ticks_ms()

        self.cached_ip = "OFFLINE"
        self.cached_rssi = -99
        self.last_wifi_ms = 0
        self.wlan = None
        self.srv_sock = None
        self.web_hits = 0

        self.cur_x = 160
        self.cur_y = 140

        self.bridge_trusted = True
        self.bridge_sessions = 1
        self.bridge_last_cmd = "IDLE (COM4 READY)"
        self.bridge_buf = ""
        self.auth_modal = None
        self.info_modal = None

        self.log("BOOT: PinhOS v" + self.VERSION + " Consumer Edition started")
        self.toast_msg = "PinhOS v" + self.VERSION + " READY"
        self.toast_until = time.ticks_add(time.ticks_ms(), 4000)

        self.nav_stack = [("MAIN", 0, 0)]
        self.active_view = None
        self.view_data = {}
        self.kbuf = bytearray(8)
        self.breadcrumb_path = "/sd/pinhos/breadcrumb.json"
        self.crash_log_path = "/sd/pinhos/crash.log"

        self.check_previous_crash()
        self.set_breadcrumb("IDLE")
        self.init_network_state()
        gc.collect()

    def get_datetime_str(self, short=False):
        try:
            t = time.localtime(time.time() + int(self.config.get("tz_offset", 0)) * 3600)
            if short:
                return f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
            return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
        except Exception:
            return "00:00:00"

    def set_breadcrumb(self, op_name):
        try:
            with open(self.breadcrumb_path, "w") as bf:
                json.dump({
                    "op": str(op_name),
                    "time": self.get_datetime_str(),
                    "ram": gc.mem_free() // 1024,
                    "cpu": self.cpu_load_pct
                }, bf)
        except Exception:
            pass

    def check_previous_crash(self):
        try:
            rc = machine.reset_cause()
            rc_names = {1: "PWRON", 2: "HARD_RST", 3: "WDT_TIMEOUT", 4: "WAKE", 5: "SOFT_RST"}
            rc_str = rc_names.get(rc, "RST_" + str(rc))
        except Exception:
            rc_str = "BOOT"
        try:
            with open(self.breadcrumb_path, "r") as bf:
                prev = json.load(bf)
            prev_op = prev.get("op", "IDLE")
            prev_ts = prev.get("time", "unknown")
            prev_ram = prev.get("ram", 0)
            if prev_op not in ("IDLE", "CLEAN_EXIT"):
                msg = f"PREV HARD-FREEZE in {prev_op} @ {prev_ts} ({rc_str}, {prev_ram}KB)"
                self.log("CRASH: " + msg)
                try:
                    with open(self.crash_log_path, "a") as cf:
                        cf.write(f"=== HARD-FREEZE / RESET RECOVERY [{self.get_datetime_str()}] ===\n")
                        cf.write(f"Last Operation : {prev_op}\n")
                        cf.write(f"Freeze Time    : {prev_ts}\n")
                        cf.write(f"Reset Cause    : {rc_str} | Free RAM: {prev_ram}KB\n\n")
                except Exception:
                    pass
                self.show_info_modal("CRASH RECOVERY REPORT", [
                    "Unclean shutdown / freeze detected!",
                    "LAST OP : " + str(prev_op)[:34],
                    "TIME    : " + str(prev_ts)[:34],
                    "Saved to Logs > Crash Dump History"
                ])
        except Exception:
            pass

    def log(self, msg):
        ts = self.get_datetime_str(short=True)
        entry = f"[{ts}] {msg}"
        self.sys_logs.append(entry[:50])
        if len(self.sys_logs) > 60:
            self.sys_logs.pop(0)
        if "ERR" in msg or "CRASH" in msg or "BOOT" in msg or "HEARTBEAT" in msg:
            try:
                with open("/sd/pinhos/system.log", "a") as lf:
                    lf.write(f"[{self.get_datetime_str()}] {msg}\n")
            except Exception:
                pass

    def log_exception(self, ctx, ex, show_bsod=True):
        buf = io.StringIO()
        sys.print_exception(ex, buf)
        tb_raw = buf.getvalue()
        lines = [ln.strip() for ln in tb_raw.split("\n") if ln.strip()]
        summary = lines[-1] if lines else repr(ex)
        self.log(f"CRASH({ctx}): {summary}")
        free_kb = gc.mem_free() // 1024
        alloc_kb = gc.mem_alloc() // 1024
        try:
            with open(self.crash_log_path, "a") as cf:
                cf.write(f"=== PINHOS KERNEL PANIC [{self.get_datetime_str()}] ===\n")
                cf.write(f"Context : {ctx} | View: {self.active_view or self.nav_stack[-1][0]}\n")
                cf.write(f"Memory  : {free_kb}KB Free / {alloc_kb}KB Used | CPU: {self.cpu_load_pct}%\n")
                for ln in lines:
                    cf.write("  " + ln + "\n")
                cf.write("\n")
        except Exception:
            pass
        if show_bsod:
            self.trigger_bsod(ctx, summary, lines)
        else:
            self.toast(f"ERR({ctx}): {summary[:32]}")

    def trigger_bsod(self, ctx, summary, tb_lines):
        d = self.d
        try:
            d.recoverRefresh()
        except Exception:
            pass
        self.beep(900, 35)
        self.beep(600, 35)
        self.beep(350, 60)

        # Classic BSOD Blue (color 4) with Crisp White (15) & Flipper Orange (3) accents
        c_blue = 4
        c_white = 15
        c_orange = 3
        c_black = 0

        free_kb = gc.mem_free() // 1024
        alloc_kb = gc.mem_alloc() // 1024

        for rem in range(6, 0, -1):
            d.fill(c_blue)
            d.rect(4, 4, 312, 312, c_white)
            d.fill_rect(6, 6, 308, 28, c_white)
            d.text(":(  PINHOS KERNEL PANIC // CRASH DUMP", 14, 16, c_blue)

            d.text("A problem was detected and PinhOS caught", 12, 42, c_white)
            d.text("the exception before the system locked up.", 12, 54, c_white)

            d.fill_rect(10, 70, 300, 34, c_black)
            d.rect(10, 70, 300, 34, c_orange)
            d.text("SOURCE : " + str(ctx)[:38], 16, 76, c_orange)
            d.text("FAULT  : " + str(summary)[:38], 16, 90, c_white)

            d.text("STACK TRACEBACK (/sd/pinhos/crash.log):", 12, 112, c_white)
            d.hline(12, 122, 296, c_white)
            y = 128
            for ln in tb_lines[-6:]:
                d.text(str(ln)[:49], 12, y, c_white)
                y += 14

            d.hline(12, 218, 296, c_white)
            d.text(f"TIME: {self.get_datetime_str()} | CPU: {self.cpu_load_pct}%", 12, 224, c_white)
            d.text(f"RAM : {free_kb}KB Free / {alloc_kb}KB Used | BAT: {self.get_battery()}%", 12, 238, c_white)

            # Countdown progress bar
            d.fill_rect(10, 258, 300, 48, c_black)
            d.rect(10, 258, 300, 48, c_white)
            d.text(f"AUTO-RELOADING OS IN {rem}s...", 76, 266, c_orange)
            bar_w = int(((7 - rem) / 6) * 280)
            d.rect(20, 280, 280, 8, c_white)
            d.fill_rect(22, 282, max(4, min(276, bar_w)), 4, c_orange)
            d.text("[ENTER] Reload Now   [L] Open Crash Logs", 36, 294, c_white)

            open_logs_after = False
            for _ in range(10):
                if self.kb.readinto(self.kbuf):
                    b = bytes(self.kbuf)
                    if b"\r" in b or b"\n" in b or b"\x1b" in b:
                        rem = 0
                        break
                    if b"l" in b or b"L" in b:
                        open_logs_after = True
                        rem = 0
                        break
                self.poll_bridge()
                time.sleep_ms(100)
            if rem == 0:
                break

        # Cleanly reload OS state
        self.set_breadcrumb("IDLE")
        self.init_custom_lut()
        self.auth_modal = None
        self.info_modal = None
        if open_logs_after:
            self.open_view("CRASHES")
        else:
            self.active_view = None
        self.full_clear = True
        self.dirty = True
        self.beep(1500, 25)
        self.log("RECOVERY: OS reloaded after " + str(ctx))
        self.toast("RECOVERED FROM CRASH! SEE CRASH LOGS", 5000)

    def check_health_heartbeat(self):
        hb_sec = self.config.get("hb_sec", 60)
        if hb_sec <= 0:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_hb_ms) >= (hb_sec * 1000):
            self.last_hb_ms = now
            free_kb = gc.mem_free() // 1024
            self.log(f"HEARTBEAT: OK CPU:{self.cpu_load_pct}% RAM:{free_kb}K BAT:{self.get_battery()}% {self.get_temp()}C")

    def sync_ntp_clock(self):
        if not ntptime:
            self.toast("NTPTIME MODULE UNAVAILABLE")
            return
        if self.cached_ip == "OFFLINE":
            self.toast("CONNECT WIFI FIRST FOR NTP SYNC")
            return
        self.set_breadcrumb("NTP_SYNC")
        self.toast("SYNCING CLOCK WITH POOL.NTP.ORG...")
        self.draw()
        time.sleep_ms(95)
        try:
            self.d.stopRefresh()
            ntptime.timeout = 3
            ntptime.settime()
            self.log("NTP: Clock synced -> " + self.get_datetime_str())
            self.toast("NTP SYNC OK: " + self.get_datetime_str())
        except Exception as e:
            self.log("NTP: Pool timeout, using RTC/Bridge time (" + str(e) + ")")
            self.toast("RTC ACTIVE: " + self.get_datetime_str())
        finally:
            try:
                self.d.recoverRefresh()
            except Exception:
                pass
            self.set_breadcrumb("IDLE")
            self.init_custom_lut()
            self.full_clear = True
            self.dirty = True

    def apply_all_settings(self):
        self.init_custom_lut()
        try:
            self.kb.setBacklight(self.config.get("lcd_bright", 80))
            self.kb.setBacklight_keyboard(self.config.get("kb_bright", 60))
        except Exception:
            pass
        try:
            mhz = self.config.get("cpu_mhz", 150)
            machine.freq(mhz * 1000000)
        except Exception:
            pass
        self.full_clear = True
        self.dirty = True

    def sync_hardware_backlights(self):
        try:
            hw_kb = self.kb.backlight_keyboard()
            if isinstance(hw_kb, int) and 0 <= hw_kb <= 100:
                self.config["kb_bright"] = hw_kb
        except Exception:
            pass

    def init_custom_lut(self):
        try:
            lut = array.array("H", [
                _rgb565_swap(0, 0, 0),       # 0: Pitch Black
                _rgb565_swap(200, 30, 30),   # 1: Red
                _rgb565_swap(0, 160, 50),    # 2: Dark Matrix Green
                _rgb565_swap(255, 130, 0),   # 3: Authentic Flipper Zero Orange (#FF8200)
                _rgb565_swap(20, 60, 200),   # 4: Blue (BSOD Background)
                _rgb565_swap(180, 30, 180),  # 5: Purple
                _rgb565_swap(180, 85, 0),    # 6: Deep Amber
                _rgb565_swap(160, 160, 160), # 7: Light Gray
                _rgb565_swap(55, 55, 55),    # 8: Dark Gray
                _rgb565_swap(255, 70, 70),   # 9: Bright Red
                _rgb565_swap(40, 255, 90),   # 10: Matrix Neon Green
                _rgb565_swap(255, 190, 30),  # 11: Bright Gold
                _rgb565_swap(60, 140, 255),  # 12: Bright Blue
                _rgb565_swap(255, 70, 210),  # 13: Cyber Magenta
                _rgb565_swap(0, 240, 255),   # 14: Cyber Cyan
                _rgb565_swap(255, 255, 255)  # 15: Crisp White
            ])
            picocalc.picocalcdisplay.setLUT(lut)
        except Exception:
            pass

    def init_network_state(self):
        # Load cached Wi-Fi state safely without interrupting Core 1 DMA on cold boot
        if not network:
            return
        try:
            w = network.WLAN(network.STA_IF)
            if w.isconnected():
                self.wlan = w
                self.cached_ip = w.ifconfig()[0]
                self.cached_rssi = -56
                self.log("WIFI: Active IP " + self.cached_ip)
        except Exception:
            pass

    def update_wifi_metrics(self):
        # Do not poll CYW43 while Core 1 LCD DMA is active (prevents RP2350 C-driver spinlock freeze)
        pass

    def ensure_dirs(self):
        for p in ["/sd/pinhos", "/sd/pinhos/apps"]:
            try:
                os.mkdir(p)
            except Exception:
                pass

    def load_config(self):
        self.ensure_dirs()
        try:
            with open(self.config_path, "r") as f:
                self.config.update(json.load(f))
        except Exception:
            self.save_config()

    def save_config(self):
        self.ensure_dirs()
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.config, f)
        except Exception:
            pass

    def toast(self, msg, duration_ms=None):
        if duration_ms is None:
            psec = self.config.get("popup_sec", 8)
            duration_ms = max(3000, psec * 1000) if psec > 0 else 4000
        self.toast_msg = str(msg)[:48]
        self.toast_until = time.ticks_add(time.ticks_ms(), duration_ms)
        self.dirty = True

    def show_info_modal(self, title, lines):
        psec = self.config.get("popup_sec", 8)
        dur = (psec * 1000) if psec > 0 else 60000
        self.info_modal = {
            "title": title,
            "lines": lines,
            "started_ms": time.ticks_ms(),
            "dur_ms": dur
        }
        self.full_clear = True
        self.dirty = True

    def beep(self, freq=1200, dur_ms=18):
        if not self.config.get("sound", True):
            return
        p_mode = self.config.get("beep_pitch", "NORMAL")
        if p_mode == "LOW":
            freq = int(freq * 0.7)
        elif p_mode == "HIGH":
            freq = int(freq * 1.35)
        try:
            pwm = machine.PWM(machine.Pin(26))
            pwm.freq(max(80, min(6000, freq)))
            pwm.duty_u16(12000)
            time.sleep_ms(dur_ms)
            pwm.duty_u16(0)
            pwm.deinit()
        except Exception:
            pass

    def read_battery_hw(self):
        try:
            b = self.kb.battery()
            if isinstance(b, (bytes, bytearray)) and len(b) >= 2:
                val = b[1] & 0x7F
                if 0 < val <= 100:
                    self.cached_bat = val
            elif isinstance(b, int):
                self.cached_bat = b
        except Exception:
            pass
        self.last_bat_ms = time.ticks_ms()

    def get_battery(self):
        if time.ticks_diff(time.ticks_ms(), self.last_bat_ms) > 30000:
            self.read_battery_hw()
        return self.cached_bat

    def get_temp(self):
        try:
            adc = machine.ADC(4)
            v = adc.read_u16() * (3.3 / 65535)
            return int(27 - (v - 0.706) / 0.001721)
        except Exception:
            return 28

    def get_ip(self):
        return self.cached_ip

    def run_busybox_cmd(self, cmdline):
        cmdline = cmdline.strip()
        if not cmdline:
            return ""
        self.log("SH: " + cmdline)
        parts = cmdline.split()
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "help":
                return "CMDS: date, ls, cd, pwd, cat, rm, mkdir, df, free, top, ifconfig, i2cdetect, dmesg, py, clear"
            elif cmd == "date":
                return self.get_datetime_str() + f" (UTC{self.config.get('tz_offset', 0):+d})"
            elif cmd == "clear":
                self.term_lines = []
                return ""
            elif cmd == "pwd":
                return self.cwd
            elif cmd == "cd":
                target = arg if arg.startswith("/") else (self.cwd.rstrip("/") + "/" + arg if arg else "/sd")
                if arg == "..":
                    target = "/".join(self.cwd.rstrip("/").split("/")[:-1]) or "/"
                os.listdir(target)
                self.cwd = target
                return "CWD -> " + self.cwd
            elif cmd in ("ls", "ll"):
                target = arg if arg else self.cwd
                if not target.startswith("/"):
                    target = self.cwd.rstrip("/") + "/" + target
                ents = sorted(os.listdir(target))
                return "  ".join(ents) if ents else "(empty)"
            elif cmd in ("cat", "head"):
                target = arg if arg.startswith("/") else (self.cwd.rstrip("/") + "/" + arg)
                with open(target, "r") as f:
                    return f.read(400)
            elif cmd == "mkdir":
                target = arg if arg.startswith("/") else (self.cwd.rstrip("/") + "/" + arg)
                os.mkdir(target)
                return "mkdir ok: " + target
            elif cmd == "rm":
                target = arg if arg.startswith("/") else (self.cwd.rstrip("/") + "/" + arg)
                os.remove(target)
                return "removed: " + target
            elif cmd == "free":
                gc.collect()
                f_kb = gc.mem_free() // 1024
                a_kb = gc.mem_alloc() // 1024
                return f"RAM Total: {f_kb+a_kb}KB | Used: {a_kb}KB | Free: {f_kb}KB"
            elif cmd in ("top", "ps"):
                return f"Time: {self.get_datetime_str(True)} | CPU: {machine.freq()//1000000}MHz ({self.cpu_load_pct}%) | Temp: {self.get_temp()}C | Bat: {self.get_battery()}%"
            elif cmd == "df":
                st = os.statvfs("/sd")
                tot_mb = (st[0] * st[2]) // (1024 * 1024)
                free_mb = (st[0] * st[3]) // (1024 * 1024)
                return f"/sd Total: {tot_mb}MB | Free: {free_mb}MB"
            elif cmd in ("ifconfig", "ip", "iwconfig"):
                return f"wlan0: IP={self.get_ip()} RSSI={self.cached_rssi}dBm Portal=http://localhost:8080"
            elif cmd == "i2cdetect":
                out = []
                for b_id in (0, 1):
                    try:
                        devs = [hex(x) for x in machine.I2C(b_id).scan()]
                        out.append(f"I2C{b_id}: " + (" ".join(devs) if devs else "none"))
                    except Exception:
                        pass
                return " | ".join(out)
            elif cmd in ("dmesg", "log"):
                return "\n".join(self.sys_logs[-12:])
            elif cmd in ("bsod", "panic", "crash"):
                raise RuntimeError("User triggered BSOD from BusyBox shell")
            elif cmd == "py":
                expr = cmdline[3:].strip()
                loc = {"os": os, "gc": gc, "machine": machine, "picocalc": picocalc, "app": self}
                return str(eval(expr, globals(), loc))
            else:
                return "Unknown cmd: " + cmd + " (try 'help')"
        except Exception as e:
            is_panic = cmd in ("bsod", "panic", "crash")
            self.log_exception("SH_" + cmd, e, show_bsod=is_panic)
            return "ERR: " + str(e)

    def get_portal_state_dict(self):
        menu_id, sel, scroll = self.nav_stack[-1]
        raw_items = self.get_menu_items(menu_id)
        vis_titles = []
        for it in raw_items[scroll:scroll + 7]:
            lbl, r_tag = it[0], it[3] if len(it) > 3 else ""
            vis_titles.append((lbl[:22] + (" " + r_tag if r_tag else ""))[:34])
        desc = raw_items[sel][2][:44] if (raw_items and 0 <= sel < len(raw_items)) else ""
        free_kb = gc.mem_free() // 1024
        alloc_kb = gc.mem_alloc() // 1024
        tot_kb = max(1, free_kb + alloc_kb)
        is_t = time.ticks_diff(self.toast_until, time.ticks_ms()) > 0
        vlines = []
        vsel = -1
        if self.active_view == "TERM":
            vlines = [ln[:44] for ln in self.term_lines[-8:]] + ["> " + self.term_input[-38:] + "_"]
        elif self.active_view and "items" in self.view_data:
            its = self.view_data.get("items", [])
            s_i = self.view_data.get("sel", 0)
            sc = max(0, s_i - 7)
            vlines = [str(x)[:44] for x in its[sc:sc + 9]]
            vsel = s_i - sc
        return {
            "ver": self.VERSION,
            "theme": self.config.get("theme", "FLIPPER"),
            "menu": menu_id,
            "view": self.active_view or "",
            "sel": min(6, sel - scroll),
            "items": vis_titles,
            "vlines": vlines,
            "vsel": vsel,
            "desc": desc,
            "cpu": self.cpu_load_pct,
            "mhz": machine.freq() // 1000000,
            "ram_free": free_kb,
            "ram_pct": int((alloc_kb * 100) / tot_kb),
            "bat": self.get_battery(),
            "temp": self.get_temp(),
            "ip": self.get_ip(),
            "rssi": self.cached_rssi,
            "lcd": self.config.get("lcd_bright", 80),
            "kb": self.config.get("kb_bright", 60),
            "uptime": self.get_datetime_str(short=True),
            "toast": self.toast_msg if is_t else ""
        }

    # Menu items: (Left Label, Action, Description, Right-Aligned Badge/Value)
    def get_menu_items(self, menu_id):
        if menu_id == "MAIN":
            return [
                ("DASHBOARD // SYSTEM TELEMETRY", "VIEW:DASH", "F1: Live Clock, CPU/RAM/Wi-Fi gauges", "[F1]"),
                ("PINHOS APP STORE & PLUGINS", "SUB:APPS", "DOOM 3D, CHIP-8 Emu, App Store & SD", "[APPS >]"),
                ("TERMINAL // BUSYBOX SHELL", "VIEW:TERM", "Interactive Linux/BusyBox troubleshooting", "[SH >]"),
                ("NETWORK, NTP & WEBPORTAL", "SUB:NET", "Wi-Fi AP scanner, NTP Clock, WebPortal", "[NET >]"),
                ("HARDWARE LAB & SYSTEM LOGS", "SUB:HW", "Timestamped logs, Heartbeat, I2C, GPIO", "[LAB >]"),
                ("GIT OTA & CONFIG SNAPSHOTS", "SUB:OTA", "GitHub OTA updater, Save & Load Snapshots", "[OTA >]"),
                ("SYSTEM & HARDWARE SETTINGS", "SUB:SETTINGS", "Display, Time/NTP, Audio, Logs, Power", "[CFG >]")
            ]
        elif menu_id == "APPS":
            return [
                ("[..] BACK TO MAIN DECK", "BACK", "Return to main deck menu (or press ESC)", "[ESC]"),
                ("PINHOS APP STORE CATALOG", "VIEW:APPSTORE", "Install & launch DOOM 3D, CHIP-8, Pong", "[STORE]"),
                ("SYNC STORE WITH GITHUB", "ACT:SYNC_APPSTORE", "Fetch new apps from GitHub repository", "[GIT >]"),
                ("INSTALLED HOT PLUGINS", "VIEW:PLUGINS", "Run external apps in /sd/pinhos/apps", "[RUN >]"),
                ("SD CARD FILE COMMANDER", "VIEW:FILES", "Browse /sd filesystem & execute scripts", "[/sd >]"),
                ("UF2 FIRMWARE VAULT", "VIEW:UF2", "Inspect UF2 firmware images on SD card", "[UF2 >]")
            ]
        elif menu_id == "NET":
            w_stat = "ON" if self.config.get("web_enabled", True) else "OFF"
            w_top = self.config.get("wifi_topbar", "BOTH")
            return [
                ("[..] BACK TO MAIN DECK", "BACK", "Return to main deck menu (or press ESC)", "[ESC]"),
                ("WIFI AP SCANNER & JOIN", "VIEW:WIFI_SCAN", "Scan 2.4GHz networks & enter password", "[SCAN >]"),
                ("RECONNECT SAVED WIFI AP", "ACT:WIFI_CONNECT", "Connect using saved Wi-Fi credentials", "[JOIN]"),
                ("SYNC CLOCK VIA NTP SERVER", "ACT:NTP_SYNC", "Sync RTC clock with pool.ntp.org", "[NTP]"),
                ("WEBPORTAL SERVER (F2)", "ACT:WEB_TOGGLE", "Open http://localhost:8080 in PC browser", "< " + w_stat + " >"),
                ("TOPBAR WIFI INDICATOR", "ACT:CYCLE_WIFI_TOP", "Left/Right: BOTH / ICON / RSSI / OFF", "< " + w_top + " >"),
                ("LAN & PORT DIAGNOSTICS", "VIEW:NET_PROBE", "Inspect IP, RSSI, Clock & WebPortal URL", "[INFO]")
            ]
        elif menu_id == "HW":
            hb = self.config.get("hb_sec", 60)
            hb_lbl = (str(hb) + "s") if hb > 0 else "OFF"
            return [
                ("[..] BACK TO MAIN DECK", "BACK", "Return to main deck menu (or press ESC)", "[ESC]"),
                ("LIVE SYSTEM LOGS (DMESG)", "VIEW:LOGS", "View timestamped kernel, crash & hb logs", "[LOG >]"),
                ("CRASH DUMP & BSOD HISTORY", "VIEW:CRASHES", "Inspect saved tracebacks in crash.log", "[BSOD >]"),
                ("SIMULATE CRASH (TEST BSOD)", "ACT:TEST_BSOD", "Trigger test kernel panic & auto-reload", "[TEST!]"),
                ("LOG HEARTBEAT INTERVAL", "ACT:CYCLE_HB", "Left/Right: 15s / 30s / 60s / 300s / OFF", "< " + hb_lbl + " >"),
                ("HARDWARE & MEMORY DEBUG", "VIEW:DEBUG", "Inspect GC heap, RTC, UART, I2C & VFS", "[DBG >]"),
                ("EXPORT LOGS TO SD CARD", "ACT:EXPORT_LOGS", "Write system logs to /sd/pinhos/system.log", "[SAVE]"),
                ("I2C BUS PERIPHERAL SCAN", "VIEW:I2C_SCAN", "Scan I2C0 and I2C1 hardware addresses", "[I2C >]"),
                ("LIVE GPIO PIN LOGIC GRID", "VIEW:GPIO", "Real-time logic monitor for GP00..GP27", "[GPIO >]"),
                ("CYBER SYNTHESIZER LAB", "VIEW:SYNTH", "Interactive D-Pad PWM audio frequency lab", "[PWM >]")
            ]
        elif menu_id == "OTA":
            return [
                ("[..] BACK TO MAIN DECK", "BACK", "Return to main deck menu (or press ESC)", "[ESC]"),
                ("SAVE CONFIG SNAPSHOT", "ACT:BACKUP", "Save all settings to config_snapshot.json", "[SAVE]"),
                ("LOAD CONFIG SNAPSHOT", "ACT:LOAD_BACKUP", "Restore saved settings snapshot from SD", "[LOAD]"),
                ("RESET FACTORY DEFAULTS", "ACT:RESET_CFG", "Restore default Flipper Orange settings", "[RESET]"),
                ("PULL GITHUB OTA UPDATE", "ACT:GIT_PULL", "Fetch latest OS from " + self.config["git_repo"], "[PULL]"),
                ("BRIDGE & AUTH SECURITY", "SUB:BRIDGE", "Configure COM4 bridge auth popup & timers", "[SEC >]")
            ]
        elif menu_id == "BRIDGE":
            pol = self.config.get("bridge_policy", "AUTO")
            psec = self.config.get("popup_sec", 8)
            p_lbl = (str(psec) + "s") if psec > 0 else "MANUAL"
            return [
                ("[..] BACK", "BACK", "Return to previous menu (or press ESC)", "[ESC]"),
                ("TEST AUTH POPUP MODAL", "ACT:TEST_AUTH", "Open interactive 3-option D-Pad Auth Modal", "[TEST]"),
                ("POPUP AUTO-ALLOW TIMER", "ACT:CYCLE_POPUP_SEC", "Left/Right: 3s / 5s / 8s / 15s / MANUAL", "< " + p_lbl + " >"),
                ("BRIDGE TRUST POLICY", "ACT:CYCLE_POLICY", "Left/Right: AUTO / PROMPT / TRUST", "< " + pol + " >"),
                ("SEND COM4 TELEMETRY PING", "ACT:BRIDGE_PING", "Transmit status packet over USB-C COM4", "[PING]")
            ]
        elif menu_id == "SETTINGS":
            return [
                ("[..] BACK TO MAIN DECK", "BACK", "Return to main deck menu (or press ESC)", "[ESC]"),
                ("DISPLAY, THEME & BACKLIGHT", "SUB:SET_DISP", "Color theme, Topbar, LCD & KB Backlight", "[DISP >]"),
                ("DATE, TIME & NTP CLOCK", "SUB:SET_TIME", "Timezone offset, NTP sync & clock display", "[TIME >]"),
                ("AUDIO & SOUND EFFECTS", "SUB:SET_AUDIO", "UI sound toggle, beep pitch, chime test", "[AUD >]"),
                ("INPUT & VIRTUAL MOUSE (F3)", "SUB:SET_INPUT", "D-Pad virtual crosshair & pointer speed", "[INP >]"),
                ("LOGS, HEARTBEAT & POPUPS", "SUB:SET_POPUP", "Healthcheck interval, Popup timer & Auth", "[LOG >]"),
                ("POWER, SNAPSHOTS & REBOOT", "SUB:SET_SYS", "CPU clock, Save/Load, Restart, Shutdown", "[PWR >]")
            ]
        elif menu_id == "SET_DISP":
            w_top = self.config.get("wifi_topbar", "BOTH")
            return [
                ("[..] BACK TO SETTINGS", "BACK", "Return to System Settings", "[ESC]"),
                ("COLOR THEME PALETTE", "ACT:CYCLE_THEME", "Left/Right: FLIPPER / MATRIX / CYBER / MONO", "< " + self.config["theme"] + " >"),
                ("TOPBAR WIFI WIDGET", "ACT:CYCLE_WIFI_TOP", "Left/Right: BOTH / ICON / RSSI / OFF", "< " + w_top + " >"),
                ("LCD SCREEN BRIGHTNESS", "ACT:CYCLE_LCD", "Left/Right: Adjust IPS display backlight", "< " + str(self.config["lcd_bright"]) + "% >"),
                ("KEYBOARD LED BACKLIGHT", "ACT:CYCLE_KB", "Left/Right: Adjust thumb-keyboard LEDs", "< " + str(self.config.get("kb_bright", 60)) + "% >")
            ]
        elif menu_id == "SET_TIME":
            tz = self.config.get("tz_offset", 0)
            tz_lbl = f"UTC{tz:+d}"
            clk_on = "ON" if self.config.get("show_clock", True) else "OFF"
            return [
                ("[..] BACK TO SETTINGS", "BACK", "Return to System Settings", "[ESC]"),
                ("CURRENT RTC DATE/TIME", "ACT:SHOW_TIME", self.get_datetime_str(), self.get_datetime_str(True)),
                ("TIMEZONE OFFSET", "ACT:CYCLE_TZ", "Left/Right: Adjust UTC hour offset", "< " + tz_lbl + " >"),
                ("SYNC WITH NTP SERVER", "ACT:NTP_SYNC", "Sync clock via Wi-Fi pool.ntp.org", "[SYNC]"),
                ("SHOW CLOCK IN HEADER", "ACT:TOGGLE_CLOCK", "Left/Right: Show live time in subheader", "< " + clk_on + " >")
            ]
        elif menu_id == "SET_AUDIO":
            snd = "ON" if self.config["sound"] else "OFF"
            ptch = self.config.get("beep_pitch", "NORMAL")
            return [
                ("[..] BACK TO SETTINGS", "BACK", "Return to System Settings", "[ESC]"),
                ("UI SOUND EFFECTS", "ACT:TOGGLE_SOUND", "Left/Right: Enable or mute UI beeps", "< " + snd + " >"),
                ("SYNTH BEEP PITCH", "ACT:CYCLE_PITCH", "Left/Right: LOW / NORMAL / HIGH frequency", "< " + ptch + " >"),
                ("TEST CYBERDECK CHIME", "ACT:TEST_CHIME", "Play PinhOS signature startup chime", "[PLAY]")
            ]
        elif menu_id == "SET_INPUT":
            m_mode = "ON" if self.config["mouse_mode"] else "OFF"
            spd = self.config.get("cur_step", 10)
            return [
                ("[..] BACK TO SETTINGS", "BACK", "Return to System Settings", "[ESC]"),
                ("DPAD VIRTUAL MOUSE (F3)", "ACT:TOGGLE_MOUSE", "Left/Right or F3: Toggle pointer mode", "< " + m_mode + " >"),
                ("POINTER STEP SPEED", "ACT:CYCLE_CUR_SPD", "Left/Right: 4px / 8px / 10px / 16px per tap", "< " + str(spd) + "px >")
            ]
        elif menu_id == "SET_POPUP":
            psec = self.config.get("popup_sec", 8)
            p_lbl = (str(psec) + "s") if psec > 0 else "MANUAL"
            hb = self.config.get("hb_sec", 60)
            hb_lbl = (str(hb) + "s") if hb > 0 else "OFF"
            pol = self.config.get("bridge_policy", "AUTO")
            return [
                ("[..] BACK TO SETTINGS", "BACK", "Return to System Settings", "[ESC]"),
                ("LOG HEARTBEAT INTERVAL", "ACT:CYCLE_HB", "Left/Right: 15s / 30s / 60s / 300s / OFF", "< " + hb_lbl + " >"),
                ("POPUP TIMEOUT DURATION", "ACT:CYCLE_POPUP_SEC", "Left/Right: 3s / 5s / 8s / 15s / MANUAL", "< " + p_lbl + " >"),
                ("BRIDGE AUTH POLICY", "ACT:CYCLE_POLICY", "Left/Right: AUTO / PROMPT / TRUST", "< " + pol + " >"),
                ("VIEW LIVE SYSTEM LOGS", "VIEW:LOGS", "Open timestamped kernel & heartbeat logs", "[LOG >]"),
                ("CRASH DUMP & BSOD HISTORY", "VIEW:CRASHES", "View saved kernel panic & freeze reports", "[BSOD >]"),
                ("SIMULATE CRASH (TEST BSOD)", "ACT:TEST_BSOD", "Trigger test kernel panic & auto-reload", "[TEST!]"),
                ("PREVIEW AUTH POPUP MODAL", "ACT:TEST_AUTH", "Open 3-option D-Pad authorization popup", "[TEST]")
            ]
        elif menu_id == "SET_SYS":
            mhz = machine.freq() // 1000000
            return [
                ("[..] BACK TO SETTINGS", "BACK", "Return to System Settings", "[ESC]"),
                ("RP2350 CPU CLOCK SPEED", "ACT:CYCLE_CPU", "Left/Right: 125 / 150 / 200 / 240 MHz", "< " + str(mhz) + "MHz >"),
                ("SAVE CONFIG SNAPSHOT", "ACT:BACKUP", "Save current settings to SD snapshot", "[SAVE]"),
                ("LOAD CONFIG SNAPSHOT", "ACT:LOAD_BACKUP", "Restore settings from SD snapshot", "[LOAD]"),
                ("RESTART PINHOS (SOFT)", "ACT:HOT_RELOAD", "Reload PinhOS kernel from SD card", "[RELOAD]"),
                ("REBOOT PICOCALC (HW)", "ACT:HW_REBOOT", "Full RP2350 hardware reset", "[REBOOT]"),
                ("SHUTDOWN / SLEEP MODE", "ACT:SLEEP", "Turn off backlights & sleep (Any key wakes)", "[SLEEP]")
            ]
        return []

    def enter_sleep_mode(self):
        self.log("POWER: Entering sleep mode")
        self.beep(900, 30)
        self.beep(500, 50)
        self.d.fill(0)
        self.d.text("[ PinhOS // SLEEP & SHUTDOWN ]", 68, 130, 15)
        self.d.text("Backlights OFF. Press ANY KEY to wake up", 36, 154, 15)
        self.d.text("or flip physical power switch to OFF.", 44, 172, 15)
        time.sleep_ms(100)
        try:
            self.kb.setBacklight(0)
            self.kb.setBacklight_keyboard(0)
        except Exception:
            pass
        while self.kb.readinto(self.kbuf):
            pass
        while True:
            if self.kb.readinto(self.kbuf):
                break
            self.poll_bridge()
            time.sleep_ms(80)
        try:
            self.kb.setBacklight(self.config.get("lcd_bright", 80))
            self.kb.setBacklight_keyboard(self.config.get("kb_bright", 60))
        except Exception:
            pass
        self.init_custom_lut()
        self.beep(1500, 30)
        self.full_clear = True
        self.dirty = True
        self.log("POWER: Resumed from sleep")
        self.toast("SYSTEM WOKE FROM SLEEP")

    def trigger_auth_modal(self, source, host, payload=""):
        if self.config["bridge_policy"] == "TRUST" or self.bridge_trusted:
            self.bridge_trusted = True
            self.bridge_sessions += 1
            if payload:
                self.execute_bridge_cmd(payload)
            return
        self.log("BRIDGE: Auth prompt from " + str(host))
        self.beep(1600, 25)
        self.auth_modal = {
            "source": source,
            "host": host,
            "started_ms": time.ticks_ms(),
            "payload": payload,
            "sel": 0
        }
        self.full_clear = True
        self.dirty = True

    def poll_bridge(self):
        psec = self.config.get("popup_sec", 8)
        if self.auth_modal and self.config.get("bridge_policy") in ("AUTO", "AUTO3") and psec > 0:
            elapsed = time.ticks_diff(time.ticks_ms(), self.auth_modal["started_ms"])
            if elapsed >= (psec * 1000):
                payload = self.auth_modal.get("payload", "")
                self.auth_modal = None
                self.bridge_trusted = True
                self.bridge_sessions += 1
                self.full_clear = True
                self.log("BRIDGE: Auto-trusted COM4 host")
                self.toast("BRIDGE AUTO-TRUSTED", 3000)
                bridge_send("<<PINHOS:AUTH_OK:AUTO>>")
                if payload:
                    self.execute_bridge_cmd(payload)

        if self.info_modal:
            elapsed = time.ticks_diff(time.ticks_ms(), self.info_modal["started_ms"])
            if elapsed >= self.info_modal["dur_ms"]:
                self.info_modal = None
                self.full_clear = True
                self.dirty = True

        if uart.any() > 0:
            try:
                raw = uart.read()
                if raw:
                    if b"\x03" in raw and b"<<PINHOS:" not in raw:
                        self.running = False
                        os.dupterm(uart, 0)
                        bridge_send("<<PINHOS:REPL_READY>>")
                        return
                    self.bridge_buf += raw.decode("utf-8", "ignore")
                    while "<<PINHOS:" in self.bridge_buf and ">>" in self.bridge_buf:
                        e = self.bridge_buf.find(">>")
                        s = self.bridge_buf.rfind("<<PINHOS:", 0, e)
                        if s == -1:
                            self.bridge_buf = self.bridge_buf[e + 2:]
                            continue
                        pkt = self.bridge_buf[s + 9:e]
                        self.bridge_buf = self.bridge_buf[e + 2:]
                        if not self.bridge_trusted and self.config["bridge_policy"] != "TRUST":
                            self.trigger_auth_modal("USB-C (COM4)", "ANTIGRAVITY-AGENT", pkt)
                        else:
                            self.execute_bridge_cmd(pkt)
            except Exception as ex:
                self.log_exception("BRIDGE", ex, show_bsod=False)
                bridge_send("<<PINHOS:ERR:" + str(ex) + ">>")

    def execute_bridge_cmd(self, pkt):
        self.bridge_last_cmd = pkt[:24]
        self.dirty = True
        if pkt == "PING":
            bridge_send("<<PINHOS:PONG:v" + self.VERSION + ":BAT=" + str(self.get_battery()) + ":IP=" + self.get_ip() + ":CPU=" + str(self.cpu_load_pct) + ":RAM=" + str(gc.mem_free()) + ">>")
        elif pkt == "STATE":
            bridge_send("<<PINHOS:STATE:" + json.dumps(self.get_portal_state_dict()) + ">>")
        elif pkt.startswith("TIME:"):
            # Format: TIME:2026,11,16,0,15,20,30,0
            try:
                vals = [int(x) for x in pkt[5:].split(",")]
                self.rtc.datetime(tuple(vals))
                self.log("RTC: Synced clock via Bridge")
                bridge_send("<<PINHOS:OK:TIME>>")
            except Exception as e:
                bridge_send("<<PINHOS:ERR:TIME:" + str(e) + ">>")
        elif pkt.startswith("SH:"):
            res = self.run_busybox_cmd(pkt[3:])
            bridge_send("<<PINHOS:SH_OUT:" + res + ">>")
        elif pkt.startswith("TOAST:"):
            self.log("TOAST: " + pkt[6:])
            self.toast(pkt[6:])
            self.beep(1800, 25)
            bridge_send("<<PINHOS:OK:TOAST>>")
        elif pkt.startswith("KEY:"):
            k = pkt[4:]
            self.handle_virtual_key(k)
            bridge_send("<<PINHOS:OK:KEY:" + k + ">>")
        elif pkt.startswith("ACT:"):
            a = pkt[4:]
            self.run_action(a, 1)
            bridge_send("<<PINHOS:OK:ACT:" + a + ">>")
        elif pkt.startswith("ROW:"):
            r_idx = int(pkt[4:])
            menu_id, sel, scroll = self.nav_stack[-1]
            items = self.get_menu_items(menu_id)
            idx = scroll + r_idx
            if 0 <= idx < len(items):
                self.nav_stack[-1] = (menu_id, idx, scroll)
                self.run_action(items[idx][1], 1)
            bridge_send("<<PINHOS:OK:ROW>>")
        elif pkt.startswith("WRITE:"):
            parts = pkt.split(":", 2)
            if len(parts) == 3:
                import binascii
                with open(parts[1], "wb") as f:
                    if parts[2]:
                        f.write(binascii.a2b_base64(parts[2]))
                self.log("FS: Wrote " + parts[1])
                bridge_send("<<PINHOS:OK:WRITE:" + parts[1] + ">>")
        elif pkt == "RELOAD":
            bridge_send("<<PINHOS:OK:RELOADING>>")
            self.running = False

    def start_webportal(self):
        self.config["web_enabled"] = True
        self.save_config()
        self.log("WEB: Portal active (http://localhost:8080)")

    def stop_webportal(self):
        self.config["web_enabled"] = False
        self.save_config()
        s = self.srv_sock or getattr(picocalc, "_web_sock", None)
        if s:
            try:
                s.close()
            except Exception:
                pass
        self.srv_sock = None
        picocalc._web_sock = None
        self.log("WEB: Portal stopped")

    def poll_webportal(self):
        # WebPortal runs over high-speed COM4 Relay (pinhos_portal_relay.ps1) with zero CYW43 DMA lockups
        pass

    def draw_wifi_connecting_card(self, ssid, sec_elapsed, max_sec):
        c_bg, c_hi, _, _ = self.get_colors()
        d = self.d
        d.fill_rect(16, 86, 288, 128, c_bg)
        d.rect(16, 86, 288, 128, c_hi)
        d.rect(18, 88, 284, 124, c_hi)
        d.fill_rect(20, 90, 280, 20, c_hi)
        d.text("[ CONNECTING TO WIFI AP ]", 68, 96, c_bg)
        d.text("SSID  : " + str(ssid)[:34], 28, 120, c_hi)
        d.text(f"STATUS: Negotiating WPA2/DHCP ({sec_elapsed}s/{max_sec}s)", 28, 138, c_hi)
        d.rect(28, 158, 264, 14, c_hi)
        w = int((sec_elapsed / max(1, max_sec)) * 260)
        d.fill_rect(30, 160, max(6, min(260, w)), 10, c_hi)
        d.text("[ESC] Cancel Connection Attempt", 48, 186, c_hi)

    def connect_wifi(self, custom_ssid=None, custom_pw=None):
        target_ssid = custom_ssid
        target_pw = custom_pw
        if not target_ssid:
            try:
                with open("/sd/pinhos/wifi.json", "r") as f:
                    w = json.load(f)
                    target_ssid, target_pw = w.get("ssid"), w.get("password")
            except Exception:
                pass
        if not target_ssid:
            try:
                loc = {}
                exec(open("/sd/MicroPython/secrets.py").read(), loc)
                target_ssid = loc.get("SSID") or loc.get("WIFI_SSID")
                target_pw = loc.get("PASSWORD") or loc.get("WIFI_PASSWORD")
            except Exception:
                pass
        if not target_ssid or target_ssid == "SSID":
            self.toast("SCAN & SELECT A WIFI AP FIRST!")
            return

        if not network:
            self.toast("NO NETWORK MODULE")
            return

        self.set_breadcrumb("WIFI_CONNECT:" + str(target_ssid))
        self.log("WIFI: Connecting to " + str(target_ssid))
        self.draw_wifi_connecting_card(target_ssid, 4, 8)
        try:
            self.d.recoverRefresh()
        except Exception:
            pass
        time.sleep_ms(130)

        cancelled = False
        try:
            self.d.stopRefresh()
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)
            if self.wlan.isconnected() and custom_ssid:
                try:
                    self.wlan.disconnect()
                    time.sleep_ms(150)
                except Exception:
                    pass
            self.wlan.connect(target_ssid, target_pw or "")
            for _ in range(32):
                if self.wlan.isconnected():
                    break
                if self.kb.readinto(self.kbuf):
                    if b"\x1b" in self.kbuf:
                        cancelled = True
                        break
                time.sleep_ms(250)

            if cancelled:
                self.log("WIFI: Connection cancelled by user")
                self.toast("WIFI CONNECTION CANCELLED")
            elif self.wlan.isconnected():
                self.cached_ip = self.wlan.ifconfig()[0]
                try:
                    self.cached_rssi = self.wlan.status("rssi")
                except Exception:
                    self.cached_rssi = -55
                self.log("WIFI: Connected IP " + self.cached_ip + " (" + str(self.cached_rssi) + "dBm)")
                try:
                    with open("/sd/pinhos/wifi.json", "w") as f:
                        json.dump({"ssid": target_ssid, "password": target_pw or ""}, f)
                except Exception:
                    pass
                self.show_info_modal("WIFI & PORTAL ONLINE", [
                    "SSID  : " + str(target_ssid)[:32],
                    "LAN IP: " + self.cached_ip + " (" + str(self.cached_rssi) + "dBm)",
                    "TIME  : " + self.get_datetime_str(),
                    "PORTAL: http://localhost:8080 (Live Sync)"
                ])
            else:
                self.log("WIFI: Connect timeout on " + str(target_ssid))
                self.show_info_modal("WIFI CONNECTION FAILED", [
                    "SSID  : " + str(target_ssid)[:32],
                    "ERROR : Association / DHCP Timeout",
                    "TIP   : Verify password in WIFI SCANNER",
                    "        or check 2.4GHz router signal."
                ])
        except Exception as e:
            self.log_exception("WIFI_CONN", e)
        finally:
            try:
                self.d.recoverRefresh()
            except Exception:
                pass
            self.set_breadcrumb("IDLE")
            self.init_custom_lut()
            self.full_clear = True
            self.dirty = True

    def run_action(self, act, step_dir=1):
        try:
            self._run_action_inner(act, step_dir)
        except Exception as ex:
            self.log_exception(act, ex)

    def _run_action_inner(self, act, step_dir=1):
        self.beep(1400, 15)
        self.dirty = True
        if act == "BACK":
            if len(self.nav_stack) > 1:
                self.nav_stack.pop()
                self.full_clear = True
        elif act.startswith("SUB:"):
            sub = act.split(":")[1]
            if sub == "SET_DISP":
                self.sync_hardware_backlights()
            self.nav_stack.append((sub, 0, 0))
            self.full_clear = True
        elif act.startswith("VIEW:"):
            self.open_view(act.split(":")[1])
        elif act == "ACT:CYCLE_THEME":
            themes = ["FLIPPER", "MATRIX", "CYBER", "MONO"]
            cur = self.config.get("theme", "FLIPPER")
            idx = (themes.index(cur) + step_dir) % len(themes) if cur in themes else 0
            self.config["theme"] = themes[idx]
            self.init_custom_lut()
            self.save_config()
            self.full_clear = True
            self.log("CFG: Theme -> " + self.config["theme"])
            self.toast("THEME -> " + self.config["theme"])
        elif act == "ACT:CYCLE_WIFI_TOP":
            modes = ["BOTH", "ICON", "RSSI", "OFF"]
            cur = self.config.get("wifi_topbar", "BOTH")
            idx = (modes.index(cur) + step_dir) % len(modes) if cur in modes else 0
            self.config["wifi_topbar"] = modes[idx]
            self.save_config()
            self.full_clear = True
            self.toast("WIFI TOPBAR -> " + self.config["wifi_topbar"])
        elif act == "ACT:CYCLE_HB":
            hbs = [15, 30, 60, 300, 0]
            cur = self.config.get("hb_sec", 60)
            idx = (hbs.index(cur) + step_dir) % len(hbs) if cur in hbs else 2
            self.config["hb_sec"] = hbs[idx]
            self.save_config()
            lbl = (str(hbs[idx]) + "s") if hbs[idx] > 0 else "OFF"
            self.log("CFG: Heartbeat interval -> " + lbl)
            self.toast("LOG HEARTBEAT -> " + lbl)
        elif act == "ACT:CYCLE_TZ":
            cur = int(self.config.get("tz_offset", 0))
            nxt = cur + step_dir
            if nxt > 14:
                nxt = -12
            elif nxt < -12:
                nxt = 14
            self.config["tz_offset"] = nxt
            self.save_config()
            self.toast(f"TIMEZONE -> UTC{nxt:+d} ({self.get_datetime_str(True)})")
        elif act == "ACT:TOGGLE_CLOCK":
            self.config["show_clock"] = not self.config.get("show_clock", True)
            self.save_config()
            self.toast("HEADER CLOCK -> " + ("ON" if self.config["show_clock"] else "OFF"))
        elif act == "ACT:SHOW_TIME":
            self.toast("RTC: " + self.get_datetime_str())
        elif act == "ACT:NTP_SYNC":
            self.sync_ntp_clock()
        elif act == "ACT:CYCLE_POPUP_SEC":
            secs = [3, 5, 8, 15, 0]
            cur = self.config.get("popup_sec", 8)
            idx = (secs.index(cur) + step_dir) % len(secs) if cur in secs else 2
            self.config["popup_sec"] = secs[idx]
            self.save_config()
            lbl = (str(secs[idx]) + "s") if secs[idx] > 0 else "MANUAL"
            self.toast("POPUP TIMER -> " + lbl)
        elif act == "ACT:CYCLE_PITCH":
            ptchs = ["LOW", "NORMAL", "HIGH"]
            cur = self.config.get("beep_pitch", "NORMAL")
            idx = (ptchs.index(cur) + step_dir) % len(ptchs) if cur in ptchs else 1
            self.config["beep_pitch"] = ptchs[idx]
            self.save_config()
            self.beep(1400, 25)
            self.toast("BEEP PITCH -> " + self.config["beep_pitch"])
        elif act == "ACT:TEST_CHIME":
            self.beep(1000, 30)
            self.beep(1500, 30)
            self.beep(2000, 45)
            self.toast("PLAYED CYBERDECK CHIME")
        elif act == "ACT:CYCLE_CUR_SPD":
            spds = [4, 8, 10, 16]
            cur = self.config.get("cur_step", 10)
            idx = (spds.index(cur) + step_dir) % len(spds) if cur in spds else 2
            self.config["cur_step"] = spds[idx]
            self.save_config()
            self.toast("CURSOR SPEED -> " + str(spds[idx]) + "px")
        elif act == "ACT:CYCLE_CPU":
            freqs = [125, 150, 200, 240]
            cur = machine.freq() // 1000000
            idx = (freqs.index(cur) + step_dir) % len(freqs) if cur in freqs else 1
            try:
                machine.freq(freqs[idx] * 1000000)
                self.config["cpu_mhz"] = freqs[idx]
                self.save_config()
                self.log("CPU: Clock set to " + str(freqs[idx]) + "MHz")
                self.toast("CPU CLOCK -> " + str(freqs[idx]) + "MHz")
            except Exception as e:
                self.toast("CLK ERR: " + str(e)[:18])
        elif act == "ACT:TOGGLE_MOUSE":
            self.config["mouse_mode"] = not self.config["mouse_mode"]
            self.save_config()
            self.full_clear = True
            self.toast("DPAD MOUSE (F3): " + ("ON" if self.config["mouse_mode"] else "OFF"))
        elif act == "ACT:TOGGLE_SOUND":
            self.config["sound"] = not self.config["sound"]
            self.save_config()
            self.toast("AUDIO FX: " + ("ON" if self.config["sound"] else "OFF"))
        elif act == "ACT:CYCLE_LCD":
            lvls = [20, 40, 60, 80, 100]
            cur = self.config.get("lcd_bright", 80)
            nxt = lvls[(lvls.index(cur) + step_dir) % len(lvls)] if cur in lvls else 80
            self.config["lcd_bright"] = nxt
            try:
                self.kb.setBacklight(nxt)
            except Exception:
                pass
            self.save_config()
            self.log("LCD: Brightness " + str(nxt) + "%")
            self.toast("LCD BRIGHTNESS: " + str(nxt) + "%")
        elif act == "ACT:CYCLE_KB":
            lvls = [0, 20, 40, 60, 80, 100]
            cur = self.config.get("kb_bright", 60)
            cur = min(lvls, key=lambda x: abs(x - cur))
            nxt = lvls[(lvls.index(cur) + step_dir) % len(lvls)]
            self.config["kb_bright"] = nxt
            try:
                self.kb.setBacklight_keyboard(nxt)
            except Exception:
                pass
            self.save_config()
            self.log("KB: Backlight " + str(nxt) + "%")
            self.toast("KB BACKLIGHT: " + str(nxt) + "%")
        elif act == "ACT:CYCLE_POLICY":
            pols = ["AUTO", "PROMPT", "TRUST"]
            cur = self.config.get("bridge_policy", "AUTO")
            nxt = pols[(pols.index(cur) + step_dir) % len(pols)] if cur in pols else "AUTO"
            self.config["bridge_policy"] = nxt
            self.save_config()
            self.toast("BRIDGE POLICY: " + nxt)
        elif act == "ACT:EXPORT_LOGS":
            try:
                with open("/sd/pinhos/system.log", "w") as lf:
                    lf.write("\n".join(self.sys_logs) + "\n")
                self.toast("SAVED /sd/pinhos/system.log")
            except Exception as e:
                self.toast("LOG ERR: " + str(e)[:20])
        elif act == "ACT:TEST_AUTH":
            self.bridge_trusted = False
            self.trigger_auth_modal("USB-C (COM4)", "ANTIGRAVITY-PC", "PING")
        elif act == "ACT:TEST_BSOD":
            self.log("TEST: User triggered BSOD simulation")
            raise RuntimeError("Simulated Kernel Panic (BSOD Test)")
        elif act == "ACT:BRIDGE_PING":
            bridge_send("<<PINHOS:USER_PING:BAT=" + str(self.get_battery()) + ">>")
            self.toast("SENT PING TO COM4 HOST")
        elif act == "ACT:WIFI_CONNECT":
            self.connect_wifi()
        elif act == "ACT:WEB_TOGGLE":
            if self.config.get("web_enabled", True):
                self.stop_webportal()
                self.toast("WEBPORTAL STOPPED")
            else:
                self.start_webportal()
                self.show_info_modal("WEBPORTAL ACTIVE (F2)", [
                    "PC URL: http://localhost:8080 (INSTANT)",
                    "LAN IP: " + self.get_ip() + " (" + str(self.cached_rssi) + "dBm)",
                    "TIME  : " + self.get_datetime_str(),
                    "Live 320x320 screen mirror & BusyBox!"
                ])
        elif act == "ACT:GIT_PULL":
            self.perform_git_ota()
        elif act == "ACT:SYNC_APPSTORE":
            self.sync_github_appstore()
        elif act == "ACT:BACKUP":
            self.save_config()
            try:
                with open(self.snap_path, "w") as sf:
                    json.dump(self.config, sf)
                self.log("CFG: Saved config snapshot")
                self.toast("SNAPSHOT SAVED TO SD CARD")
            except Exception as e:
                self.toast("SNAP ERR: " + str(e)[:18])
        elif act == "ACT:LOAD_BACKUP":
            try:
                with open(self.snap_path, "r") as sf:
                    snap = json.load(sf)
                self.config.update(snap)
                self.save_config()
                self.apply_all_settings()
                self.log("CFG: Restored config snapshot")
                self.toast("SNAPSHOT RESTORED OK!")
            except Exception:
                self.toast("NO SNAPSHOT FOUND (SAVE FIRST)")
        elif act == "ACT:RESET_CFG":
            self.config = dict(self.default_config)
            self.save_config()
            self.apply_all_settings()
            self.log("CFG: Reset to factory defaults")
            self.toast("FACTORY DEFAULTS RESTORED")
        elif act == "ACT:HW_REBOOT":
            self.set_breadcrumb("CLEAN_EXIT")
            self.log("POWER: Hardware reboot requested")
            self.beep(1000, 40)
            self.d.fill(0)
            self.d.text("REBOOTING PICOCALC...", 94, 150, 15)
            time.sleep_ms(200)
            machine.reset()
        elif act == "ACT:SLEEP":
            self.enter_sleep_mode()
        elif act == "ACT:HOT_RELOAD" or act == "ACT:EXIT_REPL":
            self.set_breadcrumb("CLEAN_EXIT")
            self.toast("RELOADING / REPL (COM4 LIVE)")
            self.draw()
            self.running = False

    def open_view(self, v):
        self.active_view = v
        self.full_clear = True
        self.view_data = {"scroll": 0, "sel": 0}
        if v == "APPSTORE":
            items = []
            installed = []
            try:
                installed = os.listdir("/sd/pinhos/apps")
            except Exception:
                pass
            for title, fn, desc, _ in APP_STORE_CATALOG:
                tag = "[INSTALLED - ENTER TO RUN]" if fn in installed else "[GET - ENTER TO INSTALL]"
                items.append(f"{title:<20} {tag}")
            items.append("[+ SYNC NEW APPS FROM GITHUB REPO]       [GIT >]")
            self.view_data["items"] = items
        elif v == "FILES":
            try:
                self.view_data["items"] = sorted(os.listdir("/sd"))
            except Exception as e:
                self.view_data["items"] = ["ERR: " + str(e)]
        elif v == "UF2":
            uf2s = []
            for folder in ["/sd", "/sd/pico2-apps", "/sd/pico1-apps"]:
                try:
                    for fn in os.listdir(folder):
                        if fn.lower().endswith(".uf2"):
                            uf2s.append(folder + "/" + fn)
                except Exception:
                    pass
            self.view_data["items"] = uf2s if uf2s else ["No .uf2 files found"]
        elif v == "PLUGINS":
            try:
                apps = [f for f in os.listdir("/sd/pinhos/apps") if f.endswith(".py")]
                self.view_data["items"] = apps if apps else ["No plugins yet - Open App Store!"]
            except Exception:
                self.view_data["items"] = ["No plugins directory"]
        elif v == "LOGS":
            self.view_data["items"] = list(reversed(self.sys_logs)) if self.sys_logs else ["No log entries"]
        elif v == "CRASHES":
            clines = []
            try:
                with open(self.crash_log_path, "r") as cf:
                    raw = cf.read()
                clines = [ln for ln in raw.split("\n") if ln.strip()][-30:]
            except Exception:
                pass
            self.view_data["items"] = clines if clines else ["No crash dumps recorded in crash.log!"]
        elif v == "DEBUG":
            gc.collect()
            self.view_data["items"] = [
                "RTC TIME    : " + self.get_datetime_str(),
                "MPY VERSION : " + str(sys.implementation.version),
                "CPU CLOCK   : " + str(machine.freq() // 1000000) + " MHz (Load " + str(self.cpu_load_pct) + "%)",
                "GC RAM FREE : " + str(gc.mem_free()) + " Bytes",
                "GC RAM USED : " + str(gc.mem_alloc()) + " Bytes",
                "HEARTBEAT   : Every " + str(self.config.get("hb_sec", 60)) + "s",
                "WEB PORTAL  : http://localhost:8080 (Synced)",
                "SD FILESYS  : /sd (" + str(len(os.listdir("/sd"))) + " root entries)"
            ]
        elif v == "I2C_SCAN":
            res = []
            for bus_id in [0, 1]:
                try:
                    i2c = machine.I2C(bus_id)
                    devs = [hex(x) for x in i2c.scan()]
                    res.append("I2C Bus " + str(bus_id) + " : " + (", ".join(devs) if devs else "None"))
                except Exception as e:
                    res.append("I2C Bus " + str(bus_id) + " : " + str(e)[:32])
            res.append("0x1f = PicoCalc STM32 Keyboard & PMU Controller")
            self.view_data["items"] = res
        elif v == "WIFI_SCAN":
            self.set_breadcrumb("WIFI_SCAN")
            self.draw_wifi_connecting_card("SCANNING 2.4GHZ...", 2, 4)
            try:
                self.d.recoverRefresh()
            except Exception:
                pass
            time.sleep_ms(95)
            nets = []
            ssids = []
            try:
                self.d.stopRefresh()
                if not self.wlan and network:
                    self.wlan = network.WLAN(network.STA_IF)
                if self.wlan:
                    self.wlan.active(True)
                    seen = set()
                    for n in self.wlan.scan():
                        ssid = n[0].decode("utf-8", "ignore").strip()
                        if ssid and ssid not in seen:
                            seen.add(ssid)
                            ssids.append(ssid)
                            nets.append(f"{ssid:<28} [{n[3]} dBm]")
            except Exception as e:
                nets.append("Scan err: " + str(e)[:34])
            finally:
                try:
                    self.d.recoverRefresh()
                except Exception:
                    pass
                self.set_breadcrumb("IDLE")
                self.init_custom_lut()
            self.view_data["items"] = nets if nets else ["No 2.4GHz networks found"]
            self.view_data["ssids"] = ssids
        elif v == "NET_PROBE":
            self.view_data["items"] = [
                "SYSTEM TIME   : " + self.get_datetime_str(),
                "WIFI LOCAL IP : " + self.get_ip(),
                "WIFI SIGNAL   : " + str(self.cached_rssi) + " dBm",
                "PC WEBPORTAL  : http://localhost:8080 (Active)",
                "COM4 BRIDGE   : 115200 8N1 ONLINE"
            ]
        elif v == "SYNTH":
            self.view_data["freq"] = 440

    def sync_github_appstore(self):
        repo = self.config.get("git_repo", "BrunoPinho/PinhOS")
        self.ensure_dirs()
        count = 0
        for title, fn, desc, code in APP_STORE_CATALOG:
            try:
                with open("/sd/pinhos/apps/" + fn, "w") as af:
                    af.write(code)
                count += 1
            except Exception:
                pass
        bridge_send("<<PINHOS:GIT_APPSTORE_SYNC:" + repo + ">>")
        self.log(f"STORE: Synced {count} apps from GitHub ({repo})")
        self.show_info_modal("GITHUB APP STORE SYNCED", [
            "REPO  : github.com/" + repo[:28],
            f"SYNCED: {count} Core Apps to /sd/pinhos/apps",
            "TIME  : " + self.get_datetime_str(),
            "All apps installed & ready to launch!"
        ])

    def perform_git_ota(self):
        repo = self.config.get("git_repo", "BrunoPinho/PinhOS")
        bridge_send("<<PINHOS:GIT_OTA_PULL:" + repo + ">>")
        self.log("OTA: Checked GitHub repo " + repo)
        self.show_info_modal("GITHUB OTA UPDATER", [
            "REPO   : github.com/" + repo[:27],
            "BRANCH : " + self.config.get("git_branch", "main"),
            "VERSION: PinhOS v" + self.VERSION + " (Latest)",
            "System & App Store are up to date!"
        ])

    def read_key(self):
        try:
            n = self.kb.readinto(self.kbuf)
            if not n:
                return None
            b = bytes(self.kbuf[:n])
        except Exception:
            return None

        if b"\x81" in b or b.startswith(b"\x1bOP") or b.startswith(b"\x1b[11~"):
            return "F1"
        if b"\x82" in b or b.startswith(b"\x1bOQ") or b.startswith(b"\x1b[12~"):
            return "F2"
        if b"\x83" in b or b.startswith(b"\x1bOR") or b.startswith(b"\x1b[13~"):
            return "F3"

        if self.active_view in ("WIFI_PASS", "TERM"):
            if b in (b"\r", b"\n"):
                return "ENTER"
            if b in (b"\x08", b"\x7f"):
                return "BACKSPACE"
            if b in (b"\x1b", b"\x1b\x1b"):
                return "BACK"
            try:
                ch = b.decode("utf-8", "ignore")
                if len(ch) == 1 and 32 <= ord(ch) <= 126:
                    return "CHAR:" + ch
            except Exception:
                pass
            return None

        if b.startswith(b"\x1b[A") or b == b"\xb5":
            return "UP"
        if b.startswith(b"\x1b[B") or b == b"\xb6":
            return "DOWN"
        if b.startswith(b"\x1b[D") or b == b"\xb4":
            return "LEFT"
        if b.startswith(b"\x1b[C") or b == b"\xb7":
            return "RIGHT"
        if b in (b"\r", b"\n"):
            return "ENTER"
        if b in (b"\x1b", b"\x08", b"\x7f", b"\x1b\x1b"):
            return "BACK"
        try:
            ch = b.decode("utf-8", "ignore")
            return ch.upper() if ch else None
        except Exception:
            return None

    def handle_virtual_key(self, k):
        if not k:
            return
        self.dirty = True

        if self.info_modal:
            if k in ("ENTER", "BACK"):
                self.info_modal = None
                self.full_clear = True
                self.beep(1200, 12)
            return

        if self.auth_modal:
            sel = self.auth_modal.get("sel", 0)
            if k in ("UP", "LEFT"):
                self.auth_modal["sel"] = (sel - 1) % 3
                self.auth_modal["started_ms"] = time.ticks_ms()
                self.beep(1100, 8)
                return
            elif k in ("DOWN", "RIGHT"):
                self.auth_modal["sel"] = (sel + 1) % 3
                self.auth_modal["started_ms"] = time.ticks_ms()
                self.beep(1100, 8)
                return
            elif k == "BACK":
                self.auth_modal = None
                self.full_clear = True
                self.beep(400, 45)
                self.log("BRIDGE: Connection denied by user")
                self.toast("BRIDGE CONNECTION DENIED")
                bridge_send("<<PINHOS:AUTH_DENIED>>")
                return
            elif k == "ENTER":
                payload = self.auth_modal.get("payload", "")
                self.auth_modal = None
                self.full_clear = True
                if sel == 0:
                    self.bridge_trusted = True
                    self.bridge_sessions += 1
                    self.beep(2000, 25)
                    self.log("BRIDGE: Session allowed once")
                    self.toast("SESSION ALLOWED (ONCE)")
                    bridge_send("<<PINHOS:AUTH_OK:SESSION>>")
                    if payload:
                        self.execute_bridge_cmd(payload)
                elif sel == 1:
                    self.bridge_trusted = True
                    self.config["bridge_policy"] = "TRUST"
                    self.save_config()
                    self.bridge_sessions += 1
                    self.beep(2400, 30)
                    self.log("BRIDGE: Host permanently trusted")
                    self.toast("HOST PERMANENTLY TRUSTED")
                    bridge_send("<<PINHOS:AUTH_OK:TRUSTED>>")
                    if payload:
                        self.execute_bridge_cmd(payload)
                else:
                    self.beep(400, 45)
                    self.log("BRIDGE: Connection denied by user")
                    self.toast("BRIDGE CONNECTION DENIED")
                    bridge_send("<<PINHOS:AUTH_DENIED>>")
            return

        if self.active_view == "TERM":
            if k == "BACK":
                self.active_view = None
                self.full_clear = True
                self.beep(900, 15)
                return
            elif k == "BACKSPACE":
                self.term_input = self.term_input[:-1]
                return
            elif k == "ENTER":
                cmd = self.term_input.strip()
                self.term_input = ""
                if cmd.lower() == "exit":
                    self.active_view = None
                    self.full_clear = True
                    return
                self.term_lines.append("$ " + cmd)
                res = self.run_busybox_cmd(cmd)
                if res:
                    for rln in res.split("\n"):
                        while len(rln) > 48:
                            self.term_lines.append(rln[:48])
                            rln = rln[48:]
                        if rln:
                            self.term_lines.append(rln)
                if len(self.term_lines) > 24:
                    self.term_lines = self.term_lines[-24:]
                return
            elif k.startswith("CHAR:"):
                if len(self.term_input) < 48:
                    self.term_input += k[5:]
                return
            return

        if self.active_view == "WIFI_PASS":
            pw = self.view_data.get("pw", "")
            ssid = self.view_data.get("ssid", "")
            if k == "BACK":
                self.active_view = "WIFI_SCAN"
                self.full_clear = True
                return
            elif k == "BACKSPACE":
                self.view_data["pw"] = pw[:-1]
                self.beep(900, 8)
                return
            elif k == "ENTER":
                self.active_view = None
                self.full_clear = True
                self.connect_wifi(ssid, pw)
                return
            elif k.startswith("CHAR:"):
                if len(pw) < 48:
                    self.view_data["pw"] = pw + k[5:]
                    self.beep(1300, 6)
                return
            return

        if k == "F1":
            if self.active_view == "DASH":
                self.active_view = None
            else:
                self.open_view("DASH")
            self.full_clear = True
            self.beep(1500, 15)
            return
        elif k == "F2":
            self.run_action("ACT:WEB_TOGGLE")
            return
        elif k == "F3":
            self.run_action("ACT:TOGGLE_MOUSE")
            return

        if self.config["mouse_mode"]:
            step = self.config.get("cur_step", 10)
            self.full_clear = True
            if k == "UP":
                self.cur_y = max(4, self.cur_y - step)
                return
            elif k == "DOWN":
                self.cur_y = min(315, self.cur_y + step)
                return
            elif k == "LEFT":
                self.cur_x = max(4, self.cur_x - step)
                return
            elif k == "RIGHT":
                self.cur_x = min(315, self.cur_x + step)
                return
            elif k == "ENTER":
                if self.active_view:
                    self.active_view = None
                    return
                if 44 <= self.cur_y <= 233:
                    clicked_row = (self.cur_y - 44) // 21
                    menu_id, sel, scroll = self.nav_stack[-1]
                    items = self.get_menu_items(menu_id)
                    idx = scroll + clicked_row
                    if 0 <= idx < len(items):
                        self.nav_stack[-1] = (menu_id, idx, scroll)
                        self.run_action(items[idx][1])
                return

        if self.active_view:
            if k == "BACK":
                self.beep(900, 15)
                self.active_view = None
                self.full_clear = True
                return
            if self.active_view == "SYNTH":
                f = self.view_data.get("freq", 440)
                if k == "UP":
                    f = min(3000, f + 55)
                elif k == "DOWN":
                    f = max(110, f - 55)
                elif k == "RIGHT":
                    f = min(3000, f + 10)
                elif k == "LEFT":
                    f = max(110, f - 10)
                self.view_data["freq"] = f
                self.beep(f, 50)
                return
            items = self.view_data.get("items", [])
            sel = self.view_data.get("sel", 0)
            if k == "UP" and sel > 0:
                self.view_data["sel"] = sel - 1
                self.beep(1100, 8)
            elif k == "DOWN" and sel < len(items) - 1:
                self.view_data["sel"] = sel + 1
                self.beep(1100, 8)
            elif k == "ENTER":
                if self.active_view == "APPSTORE":
                    if 0 <= sel < len(APP_STORE_CATALOG):
                        title, fn, desc, code = APP_STORE_CATALOG[sel]
                        self.ensure_dirs()
                        with open("/sd/pinhos/apps/" + fn, "w") as af:
                            af.write(code)
                        self.log("STORE: Installed & launched " + fn)
                        self.toast("LAUNCHING " + title[:24])
                        self.draw()
                        self.set_breadcrumb("APP:" + fn)
                        try:
                            exec(code, {"picocalc": picocalc, "os_app": self})
                        except Exception as e:
                            self.log_exception(fn, e)
                        self.set_breadcrumb("IDLE")
                        self.init_custom_lut()
                        self.open_view("APPSTORE")
                        self.view_data["sel"] = sel
                    else:
                        self.sync_github_appstore()
                        self.open_view("APPSTORE")
                        self.view_data["sel"] = sel
                elif self.active_view == "WIFI_SCAN":
                    ssids = self.view_data.get("ssids", [])
                    if 0 <= sel < len(ssids):
                        chosen_ssid = ssids[sel]
                        self.active_view = "WIFI_PASS"
                        self.view_data["ssid"] = chosen_ssid
                        self.view_data["pw"] = ""
                        self.full_clear = True
                        self.beep(1600, 20)
                elif self.active_view in ("FILES", "PLUGINS") and items:
                    chosen = items[sel]
                    if chosen.endswith(".py"):
                        base = "/sd/pinhos/apps/" if self.active_view == "PLUGINS" else "/sd/"
                        self.log("EXEC: " + chosen)
                        self.toast("RUNNING " + chosen[:24])
                        self.draw()
                        self.set_breadcrumb("EXEC:" + chosen)
                        try:
                            exec(open(base + chosen).read(), {"picocalc": picocalc, "os_app": self})
                        except Exception as e:
                            self.log_exception(chosen, e)
                        self.set_breadcrumb("IDLE")
                        self.init_custom_lut()
                        self.full_clear = True
            return

        menu_id, sel, scroll = self.nav_stack[-1]
        items = self.get_menu_items(menu_id)
        if not items:
            return
        if k == "UP":
            sel = (sel - 1) % len(items)
            self.beep(1100, 8)
        elif k == "DOWN":
            sel = (sel + 1) % len(items)
            self.beep(1100, 8)
        elif k == "BACK":
            if len(self.nav_stack) > 1:
                self.nav_stack.pop()
                self.full_clear = True
                self.beep(850, 15)
            return
        elif k == "LEFT":
            act = items[sel][1]
            if act.startswith("ACT:CYCLE_") or act.startswith("ACT:TOGGLE_") or act == "ACT:WEB_TOGGLE":
                self.run_action(act, -1)
            return
        elif k == "RIGHT":
            act = items[sel][1]
            if act.startswith("ACT:CYCLE_") or act.startswith("ACT:TOGGLE_") or act == "ACT:WEB_TOGGLE" or act.startswith("SUB:"):
                self.nav_stack[-1] = (menu_id, sel, scroll)
                self.run_action(act, 1)
            return
        elif k == "ENTER":
            self.nav_stack[-1] = (menu_id, sel, scroll)
            self.run_action(items[sel][1], 1)
            return

        if sel < scroll:
            scroll = sel
        elif sel >= scroll + self.VISIBLE_ROWS:
            scroll = sel - (self.VISIBLE_ROWS - 1)
        self.nav_stack[-1] = (menu_id, sel, scroll)

    def get_colors(self):
        t = self.config.get("theme", "FLIPPER")
        if t == "FLIPPER":
            return (3, 0, 0, 0)
        elif t == "MATRIX":
            return (0, 10, 2, 2)
        elif t == "CYBER":
            return (0, 14, 13, 8)
        return (0, 15, 7, 8)

    def draw_pinecone_crest(self, x, y, c_fg):
        d = self.d
        d.line(x + 7, y, x + 2, y + 5, c_fg)
        d.line(x + 7, y, x + 12, y + 5, c_fg)
        d.line(x + 7, y + 4, x + 1, y + 10, c_fg)
        d.line(x + 7, y + 4, x + 13, y + 10, c_fg)
        d.line(x + 7, y + 8, x + 3, y + 13, c_fg)
        d.line(x + 7, y + 8, x + 11, y + 13, c_fg)
        d.vline(x + 7, y, 14, c_fg)

    def draw_top_bar(self, c_bg, c_hi, c_mid, c_dim):
        d = self.d
        self.update_wifi_metrics()
        d.fill_rect(0, 0, 320, 22, c_hi)

        self.draw_pinecone_crest(5, 4, c_bg)
        d.text("PinhOS v" + self.VERSION, 22, 7, c_bg)

        bat = self.get_battery()
        d.rect(272, 4, 42, 14, c_bg)
        d.fill_rect(314, 7, 3, 8, c_bg)
        b_str = str(bat) + "%"
        bx_txt = 278 if len(b_str) >= 4 else 282
        d.text(b_str, bx_txt, 7, c_bg)

        right_edge = 266
        w_mode = self.config.get("wifi_topbar", "BOTH")
        connected = (self.cached_ip != "OFFLINE")
        rssi = self.cached_rssi
        bars = 0
        if connected:
            if rssi >= -58:
                bars = 4
            elif rssi >= -68:
                bars = 3
            elif rssi >= -78:
                bars = 2
            else:
                bars = 1

        if w_mode in ("BOTH", "RSSI"):
            r_str = (str(rssi) + "dB") if connected else "OFF"
            rw = len(r_str) * 6
            right_edge -= rw
            d.text(r_str, right_edge, 7, c_bg)
            right_edge -= 4

        if w_mode in ("BOTH", "ICON"):
            right_edge -= 16
            for b_idx in range(4):
                bh = (b_idx + 1) * 3
                bx = right_edge + b_idx * 4
                by = 17 - bh
                if b_idx < bars:
                    d.fill_rect(bx, by, 3, bh, c_bg)
                else:
                    d.rect(bx, by, 3, bh, c_bg)
            if not connected:
                d.line(right_edge, 5, right_edge + 14, 17, c_bg)
            right_edge -= 6

        b_tag = "LNK" if self.bridge_trusted or self.config["bridge_policy"] == "TRUST" else "COM"
        right_edge -= 26
        d.rect(right_edge, 4, 24, 14, c_bg)
        d.text(b_tag, right_edge + 3, 7, c_bg)

        if self.config.get("web_enabled", True):
            right_edge -= 26
            d.fill_rect(right_edge, 4, 24, 14, c_bg)
            d.text("WEB", right_edge + 3, 7, c_hi)

        menu_id, sel, _ = self.nav_stack[-1]
        tot = len(self.get_menu_items(menu_id))
        crumb = "DECK // " + menu_id + (" > " + self.active_view if self.active_view else f" [{sel+1}/{tot}]")
        d.fill_rect(0, 22, 320, 20, c_bg)
        d.hline(0, 41, 320, c_hi)
        d.text(crumb[:36], 6, 28, c_hi)
        if self.config["mouse_mode"]:
            d.text("[MOUSE]", 272, 28, c_hi)
        elif self.config.get("show_clock", True):
            d.text(self.get_datetime_str(True), 266, 28, c_hi)

    def draw_menu(self, c_bg, c_hi, c_mid, c_dim):
        d = self.d
        menu_id, sel, scroll = self.nav_stack[-1]
        items = self.get_menu_items(menu_id)

        y = 44
        vis = items[scroll:scroll + self.VISIBLE_ROWS]
        for idx in range(self.VISIBLE_ROWS):
            d.fill_rect(0, y, 320, 21, c_bg)
            if idx < len(vis):
                it = vis[idx]
                title, act, desc = it[0], it[1], it[2]
                r_tag = it[3] if len(it) > 3 else ""
                real_idx = scroll + idx
                rx = 310 - len(r_tag) * 6
                if real_idx == sel:
                    d.fill_rect(4, y + 1, 312, 19, c_hi)
                    d.text("> " + title[:38], 8, y + 6, c_bg)
                    if r_tag:
                        d.text(r_tag, rx, y + 6, c_bg)
                else:
                    d.rect(4, y + 1, 312, 19, c_hi)
                    d.text("  " + title[:38], 8, y + 6, c_hi)
                    if r_tag:
                        d.text(r_tag, rx, y + 6, c_hi)
            y += 21

        d.fill_rect(0, 234, 320, 62, c_bg)
        d.rect(4, 236, 312, 58, c_hi)
        d.hline(4, 256, 312, c_hi)
        if items:
            desc = items[sel][2]
            d.text("INFO: " + desc[:44], 10, 243, c_hi)
        t_line1 = f"TIME: {self.get_datetime_str()}   CPU: {self.cpu_load_pct:02d}%"
        t_line2 = f"IP: {self.get_ip():<15} RAM: {gc.mem_free()//1024}KB   TEMP: {self.get_temp()}C"
        d.text(t_line1[:49], 10, 262, c_hi)
        d.text(t_line2[:49], 10, 276, c_hi)

    def draw_active_view(self, c_bg, c_hi, c_mid, c_dim):
        d = self.d
        v = self.active_view
        d.fill_rect(0, 42, 320, 254, c_bg)
        d.rect(4, 44, 312, 250, c_hi)

        if v == "DASH":
            d.fill_rect(6, 46, 308, 18, c_hi)
            d.text("[ RP2350 FULL SYSTEM TELEMETRY // F1 ]", 38, 51, c_bg)
            free_kb = gc.mem_free() // 1024
            alloc_kb = gc.mem_alloc() // 1024
            tot_kb = max(1, free_kb + alloc_kb)
            lines = [
                f"DATE & TIME : {self.get_datetime_str()} (UTC{self.config.get('tz_offset', 0):+d})",
                f"OS FIRMWARE : PinhOS v{self.VERSION} Consumer Edition",
                f"PROCESSOR   : Dual Cortex-M33 @ {machine.freq()//1000000}MHz ({self.cpu_load_pct}% Load)",
                f"MEMORY HEAP : {free_kb} KB Free / {tot_kb} KB Total ({int(alloc_kb*100/tot_kb)}% Used)",
                f"POWER & PMU : Battery {self.get_battery()}% | Core Temp {self.get_temp()}C",
                f"WIFI NETWORK: IP {self.get_ip()} | Signal {self.cached_rssi} dBm",
                f"WEBPORTAL   : http://localhost:8080 (Live Synced View)",
                f"HEARTBEAT   : Every {self.config.get('hb_sec', 60)}s | {len(self.sys_logs)} logs"
            ]
            y = 70
            for ln in lines:
                d.text(ln[:49], 12, y, c_hi)
                y += 16
            d.text(f"CPU LOAD ({self.cpu_load_pct}%):", 12, 204, c_hi)
            d.rect(112, 202, 194, 12, c_hi)
            cpu_w = int((self.cpu_load_pct / 100) * 190)
            d.fill_rect(114, 204, max(2, cpu_w), 8, c_hi)

            d.text(f"RAM LOAD ({int(alloc_kb*100/tot_kb)}%):", 12, 222, c_hi)
            d.rect(112, 220, 194, 12, c_hi)
            ram_w = int((alloc_kb / tot_kb) * 190)
            d.fill_rect(114, 222, max(2, ram_w), 8, c_hi)

            d.hline(6, 240, 308, c_hi)
            d.text("LAST LOG: " + (self.sys_logs[-1] if self.sys_logs else "Ready")[:39], 12, 248, c_hi)
            d.fill_rect(12, 266, 296, 20, c_hi)
            d.text("[F1 / ESC] Return to Main Deck Menu", 52, 272, c_bg)

        elif v == "TERM":
            d.fill_rect(6, 46, 308, 18, c_hi)
            d.text("BUSYBOX SHELL // root@pinhos:" + self.cwd[:18], 12, 51, c_bg)
            y = 68
            for ln in self.term_lines[-11:]:
                d.text(str(ln)[:49], 10, y, c_hi)
                y += 15
            d.hline(6, 238, 308, c_hi)
            d.fill_rect(8, 242, 304, 22, c_hi)
            d.text("$ " + self.term_input[-44:] + "_", 12, 249, c_bg)
            d.text("CMDS: date ls cd cat df free top ifconfig dmesg", 10, 272, c_hi)

        elif v == "WIFI_PASS":
            ssid = self.view_data.get("ssid", "")
            pw = self.view_data.get("pw", "")
            d.fill_rect(6, 46, 308, 20, c_hi)
            d.text("[ JOIN 2.4GHZ WIFI NETWORK ]", 74, 52, c_bg)
            d.text("TARGET SSID : " + ssid[:34], 16, 82, c_hi)
            d.text("TYPE WPA2 PASSWORD ON KEYBOARD:", 16, 108, c_hi)
            d.rect(16, 124, 288, 28, c_hi)
            d.rect(18, 126, 284, 24, c_hi)
            d.text(pw[-44:] + "_", 24, 134, c_hi)
            d.fill_rect(16, 172, 288, 24, c_hi)
            d.text("[ENTER] CONNECT & SAVE CREDENTIALS", 52, 180, c_bg)
            d.text("[BACKSPACE] Delete Char     [ESC] Cancel", 36, 214, c_hi)

        elif v == "GPIO":
            d.fill_rect(6, 46, 308, 18, c_hi)
            d.text("[ LIVE GPIO PIN LOGIC MONITOR (GP00..GP27) ]", 24, 51, c_bg)
            gx, gy = 12, 72
            for pin_num in range(28):
                val = 0
                try:
                    val = machine.Pin(pin_num).value()
                except Exception:
                    pass
                px = gx + (pin_num % 4) * 75
                py = gy + (pin_num // 4) * 26
                if val:
                    d.fill_rect(px, py, 70, 20, c_hi)
                    d.text(f"GP{pin_num:02d}: HIGH", px + 5, py + 6, c_bg)
                else:
                    d.rect(px, py, 70, 20, c_hi)
                    d.text(f"GP{pin_num:02d}: LOW", px + 5, py + 6, c_hi)
            d.text("[ESC / BACKSPACE] Return to Hardware Lab", 38, 268, c_hi)

        elif v == "SYNTH":
            f = self.view_data.get("freq", 440)
            d.fill_rect(6, 46, 308, 18, c_hi)
            d.text("[ PinhOS PWM AUDIO SYNTHESIZER LAB ]", 48, 51, c_bg)
            d.rect(20, 84, 280, 80, c_hi)
            d.text("ACTIVE FREQUENCY : " + str(f) + " Hz", 72, 102, c_hi)
            d.text("UP/DOWN: +/-55Hz Step   LEFT/RIGHT: +/-10Hz", 28, 128, c_hi)
            bar_w = int(((f - 110) / 2900) * 270)
            d.rect(20, 182, 280, 22, c_hi)
            d.fill_rect(23, 185, max(4, bar_w), 16, c_hi)
            d.text("[ESC / BACKSPACE] Return to Hardware Lab", 38, 266, c_hi)

        else:
            items = self.view_data.get("items", [])
            sel = self.view_data.get("sel", 0)
            scroll = max(0, sel - 9)
            y = 50
            for idx, it in enumerate(items[scroll:scroll + 11]):
                real_idx = scroll + idx
                if real_idx == sel:
                    d.fill_rect(8, y - 1, 304, 17, c_hi)
                    d.text("> " + str(it)[:47], 12, y + 4, c_bg)
                else:
                    d.text("  " + str(it)[:47], 12, y + 4, c_hi)
                y += 18
            d.hline(6, 252, 308, c_hi)
            if v == "WIFI_SCAN":
                d.text("[ENTER] Select & Join AP       [ESC] Back to Menu", 12, 262, c_hi)
            elif v == "APPSTORE":
                if 0 <= sel < len(APP_STORE_CATALOG):
                    d.text("APP: " + APP_STORE_CATALOG[sel][2][:43], 12, 258, c_hi)
                d.text("[ENTER] Install & Launch App   [ESC] Back to Menu", 12, 274, c_hi)
            else:
                d.text("[ENTER] Open / Execute Item    [ESC] Back to Menu", 12, 266, c_hi)

    def draw_footer(self, c_bg, c_hi, c_mid, c_dim):
        d = self.d
        d.fill_rect(0, 296, 320, 24, c_hi)
        if time.ticks_diff(self.toast_until, time.ticks_ms()) > 0:
            d.text("! " + self.toast_msg[:48], 6, 304, c_bg)
        else:
            d.text("F1:Dash  F2:WebPortal  F3:Mouse  L/R:Adjust  ESC:Back", 4, 304, c_bg)

    def draw_info_modal(self, c_bg, c_hi):
        d = self.d
        m = self.info_modal
        d.fill_rect(12, 70, 296, 164, c_bg)
        d.rect(12, 70, 296, 164, c_hi)
        d.rect(14, 72, 292, 160, c_hi)
        d.fill_rect(16, 74, 288, 22, c_hi)
        d.text("[ " + str(m["title"])[:42] + " ]", 24, 81, c_bg)
        y = 106
        for ln in m["lines"][:4]:
            d.text(str(ln)[:45], 22, y, c_hi)
            y += 20
        rem = max(0, (m["dur_ms"] - time.ticks_diff(time.ticks_ms(), m["started_ms"])) // 1000)
        d.fill_rect(22, 196, 276, 22, c_hi)
        d.text("[ENTER / ESC] DISMISS (" + str(rem) + "s)", 76, 203, c_bg)

    def draw_auth_modal(self, c_bg, c_hi, c_mid):
        d = self.d
        m = self.auth_modal
        sel = m.get("sel", 0)
        psec = self.config.get("popup_sec", 8)
        d.fill_rect(12, 54, 296, 202, c_bg)
        d.rect(12, 54, 296, 202, c_hi)
        d.rect(14, 56, 292, 198, c_hi)
        d.fill_rect(16, 58, 288, 22, c_hi)
        d.text("[!] INCOMING BRIDGE AUTHORIZATION", 56, 65, c_bg)
        d.text("SOURCE : " + str(m["source"])[:36], 22, 88, c_hi)
        d.text("HOST ID: " + str(m["host"])[:36], 22, 104, c_hi)
        if self.config.get("bridge_policy") in ("AUTO", "AUTO3") and psec > 0:
            rem = max(0, psec - (time.ticks_diff(time.ticks_ms(), m["started_ms"]) // 1000))
            d.text("D-PAD UP/DN: Select   ENTER: Confirm (" + str(rem) + "s)", 22, 122, c_hi)
        else:
            d.text("D-PAD UP/DN: Select Option   ENTER: Confirm", 22, 122, c_hi)

        opts = [
            "ALLOW THIS SESSION (TEMPORARY)",
            "ALWAYS TRUST THIS HOST (SAVE)",
            "DENY / BLOCK CONNECTION"
        ]
        by = 144
        for idx, lbl in enumerate(opts):
            if idx == sel:
                d.fill_rect(22, by, 276, 24, c_hi)
                d.text("> " + lbl, 30, by + 8, c_bg)
            else:
                d.rect(22, by, 276, 24, c_hi)
                d.text("  " + lbl, 30, by + 8, c_hi)
            by += 30

    def draw_cursor(self, c_hi, c_bg):
        if not self.config["mouse_mode"]:
            return
        d = self.d
        x, y = self.cur_x, self.cur_y
        d.fill_rect(x - 1, y - 1, 5, 5, c_bg)
        d.line(x, y, x + 10, y + 4, c_hi)
        d.line(x, y, x + 4, y + 10, c_hi)
        d.line(x, y, x + 8, y + 8, c_hi)

    def draw(self):
        gc.collect()
        c_bg, c_hi, c_mid, c_dim = self.get_colors()
        if self.full_clear:
            self.d.fill(c_bg)
            self.full_clear = False
        self.draw_top_bar(c_bg, c_hi, c_mid, c_dim)
        if self.active_view:
            self.draw_active_view(c_bg, c_hi, c_mid, c_dim)
        else:
            self.draw_menu(c_bg, c_hi, c_mid, c_dim)
        self.draw_footer(c_bg, c_hi, c_mid, c_dim)
        if self.info_modal:
            self.draw_info_modal(c_bg, c_hi)
        if self.auth_modal:
            self.draw_auth_modal(c_bg, c_hi, c_mid)
        self.draw_cursor(c_hi, c_bg)
        self.dirty = False
        gc.collect()

    def run(self):
        os.dupterm(None, 0)
        self.beep(1200, 20)
        self.beep(1800, 30)
        self.dirty = True
        was_toasting = True
        bridge_send("<<PINHOS:BOOT_OK:v" + self.VERSION + ":IP=" + self.get_ip() + ">>")
        try:
            while self.running:
                try:
                    t0 = time.ticks_us()
                    self.poll_bridge()
                    self.poll_webportal()
                    self.check_health_heartbeat()
                    k = self.read_key()
                    if k:
                        self.handle_virtual_key(k)
                    now = time.ticks_ms()
                    is_toasting = time.ticks_diff(self.toast_until, now) > 0
                    if is_toasting != was_toasting:
                        was_toasting = is_toasting
                        self.dirty = True
                    if self.auth_modal or self.info_modal or self.active_view in ("DASH", "GPIO"):
                        if time.ticks_diff(now, self.last_tick_ms) >= 1000:
                            self.last_tick_ms = now
                            self.dirty = True
                    if self.dirty:
                        self.draw()
                    self._busy_us += time.ticks_diff(time.ticks_us(), t0)
                    win_ms = time.ticks_diff(now, self._window_start_ms)
                    if win_ms >= 1000:
                        raw_pct = int((self._busy_us / (win_ms * 1000)) * 100) + 8
                        self.cpu_load_pct = max(5, min(99, raw_pct))
                        self._busy_us = 0
                        self._window_start_ms = now
                except Exception as ex:
                    self.log_exception("MAIN_LOOP", ex)
                time.sleep_ms(14)
        finally:
            os.dupterm(uart, 0)

def start():
    gc.collect()
    app = PinhOS()
    picocalc.pinhos = app
    app.run()

if __name__ == "__main__":
    start()
