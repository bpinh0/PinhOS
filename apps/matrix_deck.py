# PinhOS Hot-Plugin: Matrix Cyberdeck Screensaver & Live Clock
import time, random, gc, picocalc

d = picocalc.display
kb = picocalc.keyboard
cols = [random.randint(-20, 0) for _ in range(40)]
kbuf = bytearray(8)

while True:
    if kb.keyCount() > 0:
        kb.readinto(kbuf)
        break
    d.fill(0)
    for cx in range(40):
        ry = cols[cx]
        if 0 <= ry < 36:
            ch = chr(random.randint(33, 90))
            d.text(ch, cx * 8, ry * 8, 15)
            if ry > 1:
                d.text("|", cx * 8, (ry - 1) * 8, 14)
        cols[cx] = (ry + 1) if ry < 38 else random.randint(-15, 0)
    d.fill_rect(40, 130, 240, 52, 0)
    d.rect(40, 130, 240, 52, 15)
    d.text("[ PinhOS // CYBER SCREENSAVER ]", 46, 140, 15)
    d.text("RAM FREE: " + str(gc.mem_free() // 1024) + "KB | PRESS ANY KEY", 48, 160, 14)
    d.show()
    time.sleep_ms(40)
