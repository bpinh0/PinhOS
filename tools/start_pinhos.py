import os, sys, io, gc, machine

u = machine.UART(0, 115200, rxbuf=4096)
os.dupterm(u, 0)

def bp(*args):
    s = " ".join(str(a) for a in args) + "\r\n"
    b = s.encode()
    mv = memoryview(b)
    for i in range(0, len(mv), 16):
        u.write(mv[i:i+16])
        u.flush()

try:
    if 'main' in sys.modules:
        del sys.modules['main']
    gc.collect()
    bp("FREE_BEFORE:", gc.mem_free())
    if '/sd/pinhos' not in sys.path:
        sys.path.insert(0, '/sd/pinhos')
    import main as pinhos_main
    bp("IMPORT_OK! FREE_AFTER:", gc.mem_free())
    pinhos_main.start()
except Exception as e:
    buf = io.StringIO()
    sys.print_exception(e, buf)
    bp("BOOT_ERR:\r\n" + buf.getvalue())
