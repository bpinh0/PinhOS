# Contributing to PinhOS

Thank you for your interest in contributing to **PinhOS**!

## Pull Requests
1. Fork the repository and create a feature or fix branch off `main`.
2. Respect the project's technical constraints:
   - No full-screen Python framebuffers; stream file I/O in `<= 1 KB` chunks.
   - Zero hardcoded GPIO pins outside `boards/`.
   - Ensure all on-device self-test gates pass (`.\picocalc.ps1 test`).
3. Open a Pull Request targeting `main` with a clear description of your changes.

## Contributor License Terms
By submitting a Pull Request, patch, or other contribution to this repository, you represent that you have the right to submit it and you grant **Bruno Pinho (`bpinh0`)** a perpetual, worldwide, non-exclusive, royalty-free, irrevocable copyright and patent license to use, modify, sublicense, distribute, and commercially license your contribution as part of PinhOS (under both the [PolyForm Noncommercial License 1.0.0](LICENSE) and any future commercial or alternative licenses).
