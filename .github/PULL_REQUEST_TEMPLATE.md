## Summary
<!-- Link the issue using "Refs #N" — NEVER "Closes #N" so issues are closed only after hardware verification. -->
Refs #

## Changes
-

## Memory Impact (Before / After on PicoCalc)
<!-- Required for all runtime code changes. Use largest_free(cap=96*1024) (96 KB cap, NOT 32 KB). -->

| Metric | Before (`main`) | After (this PR) |
|---|---|---|
| `gc.mem_free()` | | |
| `largest_free(cap=96*1024)` | | |

## Test Output
<!-- Paste output of `.\picocalc.ps1 test` (12/12 gates) and `mpy-cross -O2` compile check. -->
```text
```

## Checklist
- [ ] Single issue per PR; commits use `Refs #N` (no bulk-closing issues)
- [ ] All modified core OS modules compile cleanly with `mpy-cross -O2` (v6.3)
- [ ] Tools/apps remain plain `.py` on `/sd/pinhos`; I/O in `<= 1 KB` chunks; no hardcoded pins outside `boards/`
- [ ] Hardware results observed directly on PicoCalc (not fabricated)
