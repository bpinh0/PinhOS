#!/usr/bin/env bash
# PinhOS Custom RP2350 PicoCalc MicroPython UF2 Builder
# Runs inside WSL2 (Ubuntu-22.04) or any Linux environment with arm-none-eabi-gcc & cmake.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"
FROZEN_DIR="${SCRIPT_DIR}/frozen"
BUILD_ROOT="${PINHOS_UF2_CACHE:-/tmp/pinhos-uf2-build}"
MPY_TAG="${MPY_TAG:-v1.25.0}"
BOARD="RPI_PICO2_W"

mkdir -p "${BUILD_ROOT}" "${DIST_DIR}"

echo "[PinhOS UF2] Build cache : ${BUILD_ROOT}"
echo "[PinhOS UF2] Target board: ${BOARD} (MicroPython ${MPY_TAG})"

# 1. Clone MicroPython (shallow) if not already cached
if [ ! -d "${BUILD_ROOT}/micropython/.git" ]; then
    echo "[PinhOS UF2] Cloning micropython (${MPY_TAG})..."
    git clone --depth 1 --branch "${MPY_TAG}" https://github.com/micropython/micropython.git "${BUILD_ROOT}/micropython"
fi

# 2. Clone PicoCalc MicroPython C drivers if not already cached
if [ ! -d "${BUILD_ROOT}/PicoCalc-micropython-driver/.git" ]; then
    echo "[PinhOS UF2] Cloning zenodante/PicoCalc-micropython-driver..."
    git clone --depth 1 https://github.com/zenodante/PicoCalc-micropython-driver.git "${BUILD_ROOT}/PicoCalc-micropython-driver"
fi

# 3. Build mpy-cross
echo "[PinhOS UF2] Building mpy-cross..."
make -C "${BUILD_ROOT}/micropython/mpy-cross" -j"$(nproc)"

# 4. Initialize RP2 submodules (pico-sdk, cyw43-driver, lwip, mbedtls, tinyusb, etc.)
echo "[PinhOS UF2] Initializing RP2 submodules..."
make -C "${BUILD_ROOT}/micropython/ports/rp2" BOARD="${BOARD}" submodules

# 5. Stage PicoCalc Python helper modules + PinhOS frozen boot router into ports/rp2/modules/
RP2_MODS="${BUILD_ROOT}/micropython/ports/rp2/modules"
echo "[PinhOS UF2] Staging PicoCalc & PinhOS frozen modules into ${RP2_MODS}..."
if [ -d "${BUILD_ROOT}/PicoCalc-micropython-driver/pico_files/modules" ]; then
    cp -f "${BUILD_ROOT}/PicoCalc-micropython-driver/pico_files/modules/"*.py "${RP2_MODS}/"
fi
cp -f "${FROZEN_DIR}/_boot.py" "${RP2_MODS}/_boot.py"
cp -f "${FROZEN_DIR}/pinhos_boot.py" "${RP2_MODS}/pinhos_boot.py"

# 5b. Hook ports/rp2/main.c so pinhos_boot.py runs AFTER mp_usbd_init() with Ctrl-C active
RP2_MAIN_C="${BUILD_ROOT}/micropython/ports/rp2/main.c"
if ! grep -q 'pinhos_boot.py' "${RP2_MAIN_C}"; then
    python3 -c "
p = '${RP2_MAIN_C}'
txt = open(p).read()
old = 'ret = pyexec_file_if_exists(\"main.py\");'
new = 'ret = pyexec_frozen_module(\"pinhos_boot.py\", false);'
assert old in txt, 'Expected main.py hook in ports/rp2/main.c'
open(p, 'w').write(txt.replace(old, new, 1))
"
fi

# 6. Locate PicoCalc User C Module cmake files
DRIVER_ROOT="${BUILD_ROOT}/PicoCalc-micropython-driver"
USER_C_MODS=""
for mod_name in picocalcdisplay vtterminal; do
    if [ -f "${DRIVER_ROOT}/${mod_name}/micropython.cmake" ]; then
        if [ -n "${USER_C_MODS}" ]; then
            USER_C_MODS="${USER_C_MODS};${DRIVER_ROOT}/${mod_name}/micropython.cmake"
        else
            USER_C_MODS="${DRIVER_ROOT}/${mod_name}/micropython.cmake"
        fi
    fi
done

if [ -z "${USER_C_MODS}" ]; then
    echo "[ERROR] Could not locate picocalcdisplay/micropython.cmake under ${DRIVER_ROOT}"
    ls -la "${DRIVER_ROOT}"
    exit 1
fi
echo "[PinhOS UF2] USER_C_MODULES=${USER_C_MODS}"

# 7. Configure and compile with CMake + Ninja
BUILD_DIR="${BUILD_ROOT}/micropython/ports/rp2/build-${BOARD}-pinhos"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

cmake -S "${BUILD_ROOT}/micropython/ports/rp2" -B "${BUILD_DIR}" -G Ninja \
    -DMICROPY_BOARD="${BOARD}" \
    -DUSER_C_MODULES="${USER_C_MODS}"

cmake --build "${BUILD_DIR}" -j"$(nproc)"

# 8. Export final UF2
UF2_OUT="${BUILD_DIR}/firmware.uf2"
if [ ! -f "${UF2_OUT}" ]; then
    echo "[ERROR] Expected ${UF2_OUT} not found!"
    ls -la "${BUILD_DIR}"
    exit 1
fi

cp -f "${UF2_OUT}" "${DIST_DIR}/pinhos-picocalc-pico2w.uf2"
ls -lh "${DIST_DIR}/pinhos-picocalc-pico2w.uf2"
echo "[PinhOS UF2] SUCCESS: ${DIST_DIR}/pinhos-picocalc-pico2w.uf2"
