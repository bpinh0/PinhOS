import os, sys, machine, rp2, picocalc

u = machine.UART(0, 115200, rxbuf=4096)
os.dupterm(u, 0)

def bp(*args):
    s = " ".join(str(a) for a in args)
    b = (s + "\r\n").encode()
    mv = memoryview(b)
    for i in range(0, len(mv), 16):
        u.write(mv[i:i+16])
        u.flush()

try:
    # 1. Format and mount onboard Flash (bdev) as LittleFS2
    bp("Formatting bdev LittleFS2...")
    os.VfsLfs2.mkfs(bdev, progsize=256)
    vfs_flash = os.VfsLfs2(bdev, progsize=256)
    
    # Unmount /sd temporarily if needed, mount flash at /, then re-mount /sd
    try:
        os.umount('/sd')
    except Exception:
        pass
    os.mount(vfs_flash, '/')
    try:
        os.mkdir('/sd')
    except Exception:
        pass
    picocalc.sd.mount()
    bp("Mounted / ->", os.listdir('/'))
    bp("Mounted /sd -> count:", len(os.listdir('/sd')))

    # 2. Create /sd/picos directory structure for our modular OS
    for d in ['/sd/picos', '/sd/picos/core', '/sd/picos/apps', '/sd/picos/config', '/sd/picos/web']:
        try:
            os.mkdir(d)
        except Exception:
            pass

    # 3. Write /boot.py and /main.py to BOTH / (Flash) and /sd/ (SD Card)
    boot_code = """# PicoOS Persistent Bridge & Bootloader
import os, sys, machine, picocalc

try:
    _u = machine.UART(0, 115200, rxbuf=4096)
    os.dupterm(_u, 0)
    picocalc.uart_bridge = _u
except Exception:
    pass

try:
    picocalc.sd.mount()
except Exception:
    pass

if '/sd/picos' not in sys.path:
    sys.path.insert(0, '/sd/picos')
"""

    main_code = """# PicoOS Auto-Launcher
import os, sys, time, machine, picocalc

try:
    _u = machine.UART(0, 115200, rxbuf=4096)
    os.dupterm(_u, 0)
    picocalc.uart_bridge = _u
except Exception:
    pass

try:
    if 'picos_autostart.py' in os.listdir('/sd/picos'):
        exec(open('/sd/picos/picos_autostart.py').read(), globals())
except Exception as e:
    print("PicoOS boot err:", e)
"""

    for target in ['/boot.py', '/sd/boot.py']:
        with open(target, 'w') as f:
            f.write(boot_code)
    for target in ['/main.py', '/sd/main.py']:
        with open(target, 'w') as f:
            f.write(main_code)

    bp("Root files now: " + str(os.listdir('/')))
    bp("=== PERSISTENT BOOT INSTALLED OK ===")
except Exception as e:
    bp("ERR: " + repr(e))
