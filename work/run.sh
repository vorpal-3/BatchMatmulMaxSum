#!/bin/bash
# Local CI harness for BatchMatmulMaxSum.
#
# This file is OURS. The组委会-locked contract is problem/template/run.sh; that one
# is never edited. Here we run the SAME verification flow — gen_data.py, the op
# binary, verify_result.py, same case index, same 120s timeout — but configured so
# it can execute on the CANNLab CI instance, which has NO NPU.
#
# Why CPU debug mode is the right lever (all cited from our own corpus):
#   kb/corpus/asc-devkit/examples/01_simd_cpp_api/01_utilities/06_cpu_debug/README.md
#     :5   "...在不依赖 NPU 运行的情况下，对 Ascend C 核函数逻辑进行本地调试和问题定位"
#     :13  Atlas A2 训练/推理系列: >= CANN 9.0.0          (our CI instance is cann-9.0.0)
#     :48  cmake -DCMAKE_ASC_RUN_MODE=cpu -DCMAKE_ASC_ARCHITECTURES=dav-2201 ..;make -j;
#     :63  a successful run prints "[Success] Case accuracy is verification passed."
#     :72  "CPU Debug通过为每个核函数启动单独的子进程来模拟NPU的执行逻辑"
#   and cpu_debug.asc:64-75 shows the SAME harness shape we use: aclInit()/aclrtMalloc()
#   unguarded, and the kernel launched with the normal <<<blocks,0,stream>>> syntax.
#   So the组委会 main.asc is expected to run as-is under this mode.
#
# Set BMS_RUN_MODE=npu to reproduce the original on-device behaviour.
#
# NOTE: switching CMAKE_ASC_RUN_MODE requires clearing the CMake cache
# (06_cpu_debug ... batch_matmul/README.md:190). We always rm -rf build, so that is
# handled, but do not reintroduce an incremental build across modes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

OP_NAME="batch_matmul_max_sum_custom"
RUN_MODE="${BMS_RUN_MODE:-cpu}"
SOC_ARCH="${BMS_SOC_ARCH:-dav-2201}"

if [ -z "${ASCEND_HOME_PATH:-}" ]; then
    echo "ERROR: ASCEND_HOME_PATH is not set. Please run:"
    echo "  source /usr/local/Ascend/ascend-toolkit/set_env.sh"
    echo "or set ASCEND_HOME_PATH to your CANN toolkit path."
    exit 1
fi

echo "=== [0/5] Environment diagnostics ==="
echo "run_mode      : ${RUN_MODE}"
echo "soc_arch      : ${SOC_ARCH}"
echo "ASCEND_HOME   : ${ASCEND_HOME_PATH}"
echo "host          : $(uname -m) $(uname -r)"
echo "cann set_env  : $([ -f "${ASCEND_HOME_PATH}/set_env.sh" ] && echo present || echo MISSING)"
echo "cmake         : $(command -v cmake || echo MISSING) $(cmake --version 2>/dev/null | head -1)"
echo "python3       : $(command -v python3 || echo MISSING) $(python3 --version 2>&1)"
echo "--- ASC cmake package (find_package(ASC)) ---"
find / -name 'ASCConfig.cmake' -o -name 'asc-config.cmake' 2>/dev/null | head -5 || true
echo "--- bisheng ---"
ls -1 "${ASCEND_HOME_PATH}"/bin/ 2>/dev/null | head -20 || true
echo "--- anything mentioning cpu-debug / camodel ---"
find "${ASCEND_HOME_PATH}" -maxdepth 4 \( -iname '*cpudebug*' -o -iname '*cpu_debug*' -o -iname '*camodel*' \) 2>/dev/null | head -20 || true
echo "--- vector/cube kernel libs (sanity) ---"
ls -1 "${ASCEND_HOME_PATH}"/lib64 2>/dev/null | grep -iE 'ascendc|tikcpp|register' | head -10 || true
echo

echo "=== [1/5] Set CANN env ==="
source "${ASCEND_HOME_PATH}/set_env.sh"

echo "=== [2/5] Build (CMAKE_ASC_RUN_MODE=${RUN_MODE}) ==="
rm -rf build
mkdir -p build
cd build
cmake -DCMAKE_ASC_RUN_MODE="${RUN_MODE}" -DCMAKE_ASC_ARCHITECTURES="${SOC_ARCH}" ..
echo "--- cmake cache (run mode) ---"
grep -iE 'CMAKE_ASC_(RUN_MODE|ARCHITECTURES)' CMakeCache.txt || echo "(no CMAKE_ASC_* entries in cache)"
make -j4
cd ..

echo "=== [3/5] Gen test data ==="
cd build
python3 ../scripts/gen_data.py

echo "=== [4/5] Run + Verify ==="
rm -f input/*.bin
cp input/case0/* input/ 2>/dev/null || true
cp output/golden_case0/* output/ 2>/dev/null || true
find output -name '*.bin' ! -name 'golden_*' -delete 2>/dev/null || true

set +e
timeout 120 "./${OP_NAME}"
RUN_RC=$?
set -e
echo "--- op exit code: ${RUN_RC} ---"

if [ "${RUN_RC}" -ne 0 ]; then
    echo "=== FAILED (kernel exited non-zero or timed out) ==="
    exit 1
fi

set +e
python3 ../scripts/verify_result.py 0
VERIFY_RC=$?
set -e

if [ "${VERIFY_RC}" -eq 0 ]; then
    echo "=== PASSED ==="
else
    echo "=== FAILED (precision gate) ==="
    exit 1
fi
