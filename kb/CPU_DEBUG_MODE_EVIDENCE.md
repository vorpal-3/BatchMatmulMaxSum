# CPU 调测模式 / NPU 仿真模式 — corpus 取证报告

Corpus root: `D:\71_Other_Workspace\cann-batchmatmulmaxsum\kb\corpus\asc-devkit`
（下文所有 `path:line` 均相对该 root）

## 0. 语料实际内容（先决事实）

- corpus root 下**只有 `examples/` 一个顶层目录**，没有 `docs/`。`kb/fetch_corpus.py:46` 声明 roots 为 `["examples", "docs"]`，但 docs 未被落盘。
- `examples/` 下有：`README.md`、`README_en.md`、`01_simd_cpp_api/`…`05_simd_simt_hybrid/`。
- 文件类型统计（全库 573 个文件）：218 `.md`、98 `.py`、87 `.h`、85 `.txt`（其中 87 个是 CMakeLists.txt）、85 `.asc`。
- 全部 `.asc` / `.h` 代码只存在于 `01_simd_cpp_api/{03_basic_api,04_advanced_api,05_best_practices,06_compatibility_guide}`；
  `02_simd_c_api/`、`03_simt_api/`、`04_aicpu/`、`05_simd_simt_hybrid/` 下**只有 README.md / README_en.md**，没有任何样例源码。
- `examples/01_simd_cpp_api/01_utilities/` 下**只有 `README.md` 与 `README_en.md`**。
  `01_utilities/README.md:14` 列出 `06_cpu_debug`（CPU调测模式）、`:15` 列出 `08_simulator`（CAmodel仿真与问题分析），
  但 `06_cpu_debug/`、`08_simulator/` 目录在本 corpus 中**不存在**（`01_utilities/README.md:1-16` 即全部内容）。
- 成因：`kb/fetch_corpus.py:57-62` 的 `DEFAULT_KEYWORDS`（matmul/mmad/cube/…/perf）按**路径**过滤（`:176`），
  `06_cpu_debug`、`08_simulator` 路径不含任何关键词故未被下载。
- `examples/05_simd_simt_hybrid/README.md:32` 链接 `../01_simd_cpp_api/01_utilities/08_simulator` —— 在本 corpus 中是死链。

---

## 1. `-DCMAKE_ASC_RUN_MODE=cpu` 到底做什么 / 二进制怎么跑

**1.1 它是一个 CMake 缓存字符串变量，作为编译配置开关传入 `find_package(ASC)`。**
- `examples/01_simd_cpp_api/03_basic_api/03_matrix_compute/batch_matmul/README.md:196` —
  `| CMAKE_ASC_RUN_MODE | npu（默认）、cpu、sim | 运行模式：NPU运行、CPU调试、NPU仿真 |`
- `examples/01_simd_cpp_api/06_compatibility_guide/pattern_transformation/README.md:288` 同表。

**1.2 实测给出的构建命令（注意 `dav-2201` 与 `cpu` 同现）。**
- `examples/01_simd_cpp_api/06_compatibility_guide/pattern_transformation/README.md:278` —
  `cmake -DCMAKE_ASC_RUN_MODE=cpu -DCMAKE_ASC_ARCHITECTURES=dav-2201 -DSCENARIO_NUM=1 .. && make -j   # CPU 调试模式`
- `:279` — 同形 `sim` 命令。
- `examples/01_simd_cpp_api/04_advanced_api/04_reduce/sum/README.md:82-83` — `dav-2201` + `cpu` / `sim`。
- `examples/01_simd_cpp_api/03_basic_api/03_matrix_compute/batch_matmul/README.md:187-188` — 同上。
- `examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fused/README.md:88-89` — 同上。

**1.3 生成的二进制用同一个可执行文件、同一条命令运行 —— 没有单独的 run 命令。**
- 默认 npu 模式：`batch_matmul/README.md:177` 构建 → `:179` `./demo` → `:180` `python3 ../scripts/verify_result.py output/output.bin output/golden.bin`。
- cpu/sim 模式小节 `batch_matmul/README.md:182-190` **只给构建命令，不给任何新的运行命令**；`:179` 的 `./demo` 仍是唯一执行方式。
- 同样结构见 `sum/README.md:75`（`./demo`）与 `:78-84`（cpu/sim 只改构建）；
  `matmul_fused/README.md:80`（`./demo`）与 `:84-90`（cpu/sim 只改构建）。

**1.4 唯一被文档化的环境变量是 CANN 的 `set_env.sh`，对两种模式通用，不是 cpu 专用。**
- `batch_matmul/README.md:166-169` — `source ${install_path}/cann/set_env.sh`；
  `sum/README.md:63`、`matmul_fused/README.md:68`、`pattern_transformation/README.md:259` 同。
- 全库 `.md` 中出现的其他环境变量只有 `ASCENDC_DUMP`（`examples/01_simd_cpp_api/05_best_practices/03_fusion_compute/matmul_gelu_high_performance/README.md:475,489`）
  与 `ASCENDC_CUBE_ONLY` 宏（`examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_ibshareB/README.md:74,76`）。
- **`ASCENDC_CPU_DEBUG` 从未在任何文档中被描述为环境变量 —— NOT FOUND**（它只作为 C 预处理宏出现在源码中，见 §3）。

**1.5 已知操作约束：切换模式必须清 CMake 缓存。**
- `batch_matmul/README.md:190` / `sum/README.md:86` / `matmul_fused/README.md:92` / `pattern_transformation/README.md:282` —
  `> **注意：** 切换编译模式前需清理 cmake 缓存，可在 build 目录下执行 rm CMakeCache.txt 后重新 cmake。`
- 另外两个样例把这条升级为显式告诫：`examples/01_simd_cpp_api/05_best_practices/01_matrix_compute/matmul_mxfp4_basic_api_high_performance/README.md:528`、
  `.../matmul_mxfp4_high_performance/README.md:252`。

**1.6 corpus 无法回答的部分：`cpu` 与 `sim` 在编译期各自展开成什么（宏、替换库、链接目标）不在此库中。**
全库无任何 `.cmake` 文件；`find_package(ASC)` 提供的 `ASCConfig.cmake` / 相关 module 不在 corpus 内。

---

## 2. 项目 CMakeLists.txt 需要什么

**2.1 只有 3 个样例自己声明 `CMAKE_ASC_RUN_MODE`（其余全部依赖 ASC 包默认值）。**
- 声明为 `npu, cpu, sim` 三值：
  - `examples/01_simd_cpp_api/06_compatibility_guide/pattern_transformation/CMakeLists.txt:14` —
    `set(CMAKE_ASC_RUN_MODE "npu" CACHE STRING "Run mode: npu, cpu, sim")`
  - `examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul/CMakeLists.txt:14` — 同字面量。
  - `examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fused/CMakeLists.txt:14` — 同字面量。
  - 以及 `.../matmul_ibshareAB/CMakeLists.txt:14`、`.../matmul_l0cache/CMakeLists.txt:14`、`.../matmul_vecout/CMakeLists.txt:14` 等（grep `CMAKE_ASC_RUN_MODE` 命中约 30 个 CMakeLists）。
- 只声明为 `npu, sim`（**显式排除 cpu**）：
  - `examples/01_simd_cpp_api/05_best_practices/03_fusion_compute/ssbuf_aiv_aic_comm/CMakeLists.txt:13` —
    `set(CMAKE_ASC_RUN_MODE "npu" CACHE STRING "Run mode: npu, sim")`
  - `examples/01_simd_cpp_api/05_best_practices/03_fusion_compute/quant_group_matmul_high_performance/CMakeLists.txt:14` — 同。
- **完全不声明 `CMAKE_ASC_RUN_MODE`，但其 README 却宣传 sim 模式**：
  - `examples/01_simd_cpp_api/05_best_practices/01_matrix_compute/matmul_high_performance/CMakeLists.txt:14`（`set(CMAKE_ASC_ARCHITECTURES ...)`）、`:17`（`find_package`），无 RUN_MODE；
    而 `.../matmul_high_performance/README.md:568` 写着 `CMAKE_ASC_RUN_MODE | npu（默认）、sim`。
  - 同类：`.../matmul_mxfp4_high_performance/CMakeLists.txt:16-20` 无 RUN_MODE，`README.md:249` 却列出 `sim`。

**2.2 `find_package(ASC REQUIRED)` + `project(... LANGUAGES ASC CXX)` 是固定骨架；ASC 包提供 ASC 编译语言与 `--npu-arch` 编译期约定。**
- `matmul/CMakeLists.txt:11-35` 全文即：
  - `:12` `cmake_minimum_required(VERSION 3.16)`
  - `:14` `set(CMAKE_ASC_RUN_MODE "npu" CACHE STRING "Run mode: npu, cpu, sim")`
  - `:15` `set(CMAKE_ASC_ARCHITECTURES "dav-2201" CACHE STRING "NPU architecture: dav-2201, dav-3510")`
  - `:17` `find_package(ASC REQUIRED)`
  - `:19` `project(kernel_samples LANGUAGES ASC CXX)`
  - `:21-23` `add_executable(demo matmul.asc)`
  - `:25-31` `target_link_libraries(demo PRIVATE tiling_api register platform m dl)`
  - `:33-35` `target_compile_options(demo PRIVATE $<$<COMPILE_LANGUAGE:ASC>:--npu-arch=${CMAKE_ASC_ARCHITECTURES}>)`
- `pattern_transformation/CMakeLists.txt:14-15,18,20,26-28` 为同一形状（无 `target_link_libraries`）。
- 结论：ASC 包提供的可验证可见面是 **ASC 语言 + `--npu-arch=<arch>` 编译选项 + `CMAKE_ASC_RUN_MODE` / `CMAKE_ASC_ARCHITECTURES` 两个约定变量**。
  **ASC 包内部如何使用 `CMAKE_ASC_RUN_MODE` —— NOT FOUND**（无 `.cmake`，无包源码）。

**2.3 corpus 中唯一一处对 `CMAKE_ASC_RUN_MODE` 做条件分支的 CMake 代码。**
- `examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_ibshareAB/CMakeLists.txt:47-51`：
  ```
  if (CMAKE_ASC_RUN_MODE STREQUAL "npu")
      target_compile_definitions(demo PRIVATE CYCLENUMS=10000)
  else()
      target_compile_definitions(demo PRIVATE CYCLENUMS=1)
  endif()
  ```
  即：该样例把 `else()`（含 cpu 与 sim）当作"少循环"的调试配置。

**2.4 反向证据：有样例在 CMake 层硬拒绝 cpu 模式。**
- `ssbuf_aiv_aic_comm/CMakeLists.txt:24-26`：
  ```
  if(NOT CMAKE_ASC_RUN_MODE MATCHES "^(npu|sim)$")
      message(FATAL_ERROR "CMAKE_ASC_RUN_MODE must be npu or sim, but got ${CMAKE_ASC_RUN_MODE}.")
  endif()
  ```
  → **cpu 调试模式并非所有样例都支持**，这是 corpus 内可见的硬证据。

**2.5 与 arch 的关系：`dav-2201` / `dav-3510` 由 `CMAKE_ASC_ARCHITECTURES` → `--npu-arch` 决定，与 RUN_MODE 正交。**
- `batch_matmul/CMakeLists.txt:13` 默认 `dav-2201`；`:24-26` 传 `--npu-arch=${CMAKE_ASC_ARCHITECTURES}`。
- `examples/README.md:21-25` 给出产品↔arch 对照表：`dav-2201` = Atlas A3/A2 训练与推理系列；`dav-3510` = Ascend 950PR/950DT；`dav-2002` = Atlas 推理系列 AI Core。
- 多个样例 CMakeLists 对 arch 做 `FATAL_ERROR` 守卫，例：`load_data_l12l0/CMakeLists.txt:15-17`（仅 dav-2201）、`fixpipe_l0c2ub/CMakeLists.txt:15-17`（仅 dav-3510）。

**2.6 没有发现任何名为 `ASCEND_CAMODEL`、`RUN_MODE`（裸名）的变量。**
- 全库变量名只有 `CMAKE_ASC_RUN_MODE` 与 `CMAKE_ASC_ARCHITECTURES`。`ASCEND_CAMODEL` —— **NOT FOUND**。

---

## 3. cpu / sim 模式下 kernel 如何被调用

**3.1 唯一完整的 cpu 分支实现在 `matmul_fused.asc`，用的是 `ICPU_RUN_KF` 宏 + `AscendC::GmAlloc`。**
`examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fused/matmul_fused.asc`：
- `:283` `#ifdef ASCENDC_CPU_DEBUG`
- `:284-289` host 侧用 **`AscendC::GmAlloc(...)`** 申请 a / b / bias / c / tiling / workspace（不是 `aclrtMalloc`）：
  `uint8_t* a = (uint8_t*)AscendC::GmAlloc(aFileSize);` …
- `:295` **`ICPU_RUN_KF(matmul_fused_custom, numBlocks, a, b, bias, c, workspace, tiling);`**
- `:297` `WriteFile("./output/output.bin", c, cFileSize);`
- `:298-303` `AscendC::GmFree(...)`
- `:304` `#else` → `:305-368` 上板路径：`aclInit` / `aclrtSetDevice` / `aclrtCreateStream` / `aclrtMallocHost` /
  `:347-348` `matmul_fused_custom<<<numBlocks, 0, stream>>>(...)` / `aclrtSynchronizeStream` / `aclrtFree`
- `:369` `#endif`

→ **cpu 模式下：host 用 `GmAlloc` 拿"GM"缓冲，用 `ICPU_RUN_KF(kernel, numBlocks, args...)` 直接调 kernel，不经过 ACL stream 与 `<<<>>>`。**

**3.2 `ICPU_RUN_KF` 在全 corpus 中仅出现 1 次。**
grep `ICPU_RUN_KF|GmAlloc|GmFree` 全库命中 13 行，全部落在
`examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fused/matmul_fused.asc:284-303,295`。

**3.3 另一处 cpu-debug 相关的强制约定：cpu 调测下必须显式定义 `g_coreType`。**
`examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fp8/data_utils.h:28-34`：
```
#if defined(ASCENDC_CPU_DEBUG)
#define SET_G_CORE_TYPE_IS_AIV int g_coreType = 2
#define SET_G_CORE_TYPE_IS_AIC int g_coreType = 1
#else
#define SET_G_CORE_TYPE_IS_AIV
#define SET_G_CORE_TYPE_IS_AIC
#endif
```
→ cpu 调测时 `g_coreType`（1=AIC、2=AIV）必须作为**全局变量实体存在**；上板时该宏展开为空。
**哪一处 `main` 使用了这两个宏 —— 未在 corpus 中找到调用点（宏定义存在，使用点 NOT FOUND）。**

**3.4 绝大多数文档宣传 cpu 模式的样例，其 main 里根本没有 cpu 分支 —— 只改 platform 单例的芯片名。**
典型（`examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul/matmul.asc`）：
- `:186` `int32_t main(int32_t argc, char* argv[])`
- `:188-194`
  ```
  #if defined(ASCENDC_CPU_DEBUG) && (__NPU_ARCH__ == 2201)
      auto ascendcPlatform = platform_ascendc::PlatformAscendCManager::GetInstance("Ascend910B1");
  #elif defined(ASCENDC_CPU_DEBUG) && (__NPU_ARCH__ == 3510)
      auto ascendcPlatform = platform_ascendc::PlatformAscendCManager::GetInstance("Ascend950PR_9589");
  #else
      auto ascendcPlatform = platform_ascendc::PlatformAscendCManager::GetInstance();
  #endif
  ```
- `:216-219` `aclInit/aclrtSetDevice/aclrtCreateContext/aclrtCreateStream` —— **不在任何 ifdef 内**
- `:259` `matmul_custom<<<numBlocks, 0, stream>>>(...)` —— **不在任何 ifdef 内**
- 同样的"只在 cpu-debug 时按芯片名取 platform 单例"的写法重复出现在约 30 个 `.asc` 中，例：
  `.../matmul_unitflag/matmul_unitflag.asc:195-201`、`.../matmul_high_performance/matmul.asc:150-156`、
  `.../matmul_fused/matmul_fused.asc:261-267`、`.../matmul_fp8/matmul_fp8.asc:43-45,246-248,267-269,382-384`。
- **含义（谨慎陈述）**：这些样例在 cpu 模式下的实际行为依赖 ASC 包把 ACL 宿主 API 替换/桩化，corpus 中没有这部分实现。
  语料只能证明"文档承诺支持 cpu 模式"，**不能证明**这些样例的 `main` 在 cpu 模式下如何真正执行 —— NOT FOUND。

**3.5 与 §3.4 明显矛盾的两个样例，值得注意。**
- `examples/01_simd_cpp_api/03_basic_api/03_matrix_compute/batch_matmul/README.md:187` 承诺 `-DCMAKE_ASC_RUN_MODE=cpu`，
  但 `batch_matmul.asc:253-308` 的 `main` **只有纯 ACL + `:291` `batch_matmul_custom<<<numBlocks, 0, stream>>>(...)`**，
  全文无 `ASCENDC_CPU_DEBUG`（该文件仅 `:139,149,180,205,208,215` 使用 `__NPU_ARCH__`）。
- `examples/01_simd_cpp_api/05_best_practices/03_fusion_compute/quant_group_matmul_high_performance/quant_group_matmul_custom.asc:639-641`
  有 `ASCENDC_CPU_DEBUG` 分支，但其 `CMakeLists.txt:14` 写明 `Run mode: npu, sim`、README `:453` 也只宣传 sim。

---

## 4. 哪些 CANN 版本支持这些模式

**4.1 corpus 中不存在"RUN_MODE × CANN 版本"的支持矩阵 —— 没有任何一处把 cpu/sim 模式绑定到版本号。NOT FOUND。**

**4.2 最直接的间接证据：一个声明 CANN 最低版本为 9.0.0 的样例，明确给出 dav-2201 + cpu 的构建命令。**
- `examples/01_simd_cpp_api/06_compatibility_guide/pattern_transformation/README.md:23-25`：
  ```
  | Ascend 950PR/Ascend 950DT | >= CANN 9.1.0 |
  | Atlas A3 训练系列产品/Atlas A3 推理系列产品 | >= CANN 9.0.0 |
  | Atlas A2 训练系列产品/Atlas A2 推理系列产品 | >= CANN 9.0.0 |
  ```
- 同文件 `:278` 给出 `cmake -DCMAKE_ASC_RUN_MODE=cpu -DCMAKE_ASC_ARCHITECTURES=dav-2201 ...`。
- → **这是 corpus 内支持"cann 9.0.0 + dav-2201 可用 cpu 调测模式"的最强单点证据**（文档层面）。

**4.3 同类证据（README 声明 A2/A3 ≥ 9.0.0，且文档化 cpu 模式）：**
- `examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fused/README.md:12-13`（≥ 9.0.0）+ `:84,88`（cpu 模式命令与说明）。
- `examples/01_simd_cpp_api/04_advanced_api/04_reduce/sum/README.md:15-16` + `:78,82`。
- `examples/01_simd_cpp_api/04_advanced_api/04_reduce/reducemax/README.md:17-18` + `:86,90`。
- `examples/01_simd_cpp_api/03_basic_api/01_memory_vector_compute/transpose/README.md:12-13` + `:89,93`。
- `examples/01_simd_cpp_api/03_basic_api/01_memory_vector_compute/element_wise_arithmetic/README.md:12-13` + `:84,89`。
- `examples/01_simd_cpp_api/05_best_practices/01_matrix_compute/matmul_high_performance/README.md:13-14`（A2/A3 ≥ 9.0.0）+ `:554,558`（sim 模式；该表只列 npu/sim）。
- `examples/01_simd_cpp_api/06_compatibility_guide/fixpipe_params_switch/README.md:39-40`（≥ 9.0.0）+ `:109`（cpu 模式）。

**4.4 计数器证据：若干"需要 ≥ CANN 9.2.0"的样例也文档化 cpu 模式 —— 说明这些版本表是"样例自身的最低版本"，不是"RUN_MODE 的支持版本"。**
- `examples/01_simd_cpp_api/03_basic_api/03_matrix_compute/batch_matmul/README.md:12-14`（A2/A3 均 ≥ CANN 9.2.0）+ `:187`（cpu 模式命令）。
- `examples/01_simd_cpp_api/03_basic_api/03_matrix_compute/load_data_with_stride/README.md:12`（≥ 9.2.0）+ `:117`（cpu 模式命令）。
- `examples/01_simd_cpp_api/05_best_practices/01_matrix_compute/matmul_high_performance/README.md:13-14` 为 ≥9.0.0 而 `.../matmul_basic_api_high_performance/README.md:11-13` 为 ≥9.2.0 —— 同类样例不同版本门槛。

**4.5 关于 API 演进的时间锚（用于交叉核对版本传播）：**
- `examples/01_simd_cpp_api/03_basic_api/01_memory_vector_compute/reduce_data_block/README.md:7` —
  `注：ReduceDataBlock 为 CANN 9.1.0 重命名后的 API。CANN 9.0.0 及之前版本请使用 BlockReduceMax，BlockReduceMin，BlockReduceSum。`
- 同形：`.../reduce_repeat/README.md:7`、`.../reduce_pair_elem/README.md:7`。
- → **本语料自身横跨 CANN 9.0.0 / 9.1.0 / 9.2.0 三代，且大量样例文件头 copyright 为 2025-2026，
  因此"某些 README 的 RUN_MODE 表格"反映的是 devkit HEAD（≈9.2 时代）的能力，不能直接外推到 9.0.0。**

**4.6 没有任何证据显示 cpu 调试模式需要比 9.0.0 更新的版本。**
反向声明（"cpu 模式要求 ≥ CANN x.y.z"）在 corpus 中 **NOT FOUND**。

**4.7 corpus 外部（明确标注，非本次取证范围）：**
`kb/FINDINGS.md` F7 记录判题机工具链为 CANN 9.0.0 / bisheng（clang 15.0.5）/ CMake 3.16+ / `find_package(ASC REQUIRED)` /
`project(... LANGUAGES ASC CXX)` / `--npu-arch=${SOC_ARCH}`（默认 `dav-2201`）。该文件不在 corpus root 下，属旁证。

---

## 5. cpu 模式与 sim 模式的"限制"陈述

**5.1 corpus 中没有任何一句针对 cpu 调测模式或 CAmodel 仿真模式本身的限制说明。NOT FOUND。**
（`06_cpu_debug`、`08_simulator` 两个目录整体缺失 —— 见 §0，限制说明本应在那里。）
具体地，以下问题在 corpus 中**全部 NOT FOUND**：
- 是否仿真 Cube 单元；
- 是否支持 Matmul 高阶 API；
- 是否建模多核；
- 是否做精度校验；
- 是否支持 MIX（AIC+AIV）任务。

**5.2 corpus 中能找到的、与模式相关的边缘约束（都不是"模式本身的限制"）：**

| 陈述 | 出处 |
|---|---|
| 某样例固定 dav-3510，"仅支持NPU和仿真运行模式" | `examples/01_simd_cpp_api/05_best_practices/03_fusion_compute/ssbuf_aiv_aic_comm/README.md:13` |
| 同样例 CMake 硬拒 `cpu` | `.../ssbuf_aiv_aic_comm/CMakeLists.txt:24-26` |
| 切换 CMAKE_ASC_RUN_MODE 前必须清 CMakeCache.txt | `batch_matmul/README.md:190`、`sum/README.md:86`、`matmul_fused/README.md:92`、`pattern_transformation/README.md:282` |
| 该告诫被强调为独立 Notice（含 arch / SCENARIO_NUM） | `matmul_mxfp4_high_performance/README.md:252`、`matmul_mxfp4_basic_api_high_performance/README.md:528` |
| `matmul_ibshareAB` 在非 npu 模式下把 `CYCLENUMS` 从 10000 降到 1（暗示调试/仿真模式执行慢，不宜跑长循环） | `examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_ibshareAB/CMakeLists.txt:47-51` |
| `msopprof` / `msopprof simulator` 是"上板或仿真"两种模式的性能采集工具（暗示仿真模式可采性能数据，但**没有说明仿真模式是否给出可信性能数**） | `examples/01_simd_cpp_api/05_best_practices/01_matrix_compute/matmul_high_performance/README.md:579`；`.../matmul_mxfp4_high_performance/README.md:262`；`.../matmul_basic_api_high_performance/README.md:507`；`.../matmul_gelu_high_performance/README.md:494` |
| `printf`/`DumpTensor` 影响性能，可用 `ASCENDC_DUMP=0` 关闭 | `examples/01_simd_cpp_api/05_best_practices/03_fusion_compute/matmul_gelu_high_performance/README.md:475,489` |

**5.3 各样例 README 的"执行结果"统一是 `test pass!` 文案，但精度对比由外部 python 脚本完成，不是模式内建的校验。**
- 判据：`batch_matmul/README.md:180`（`python3 ../scripts/verify_result.py output/output.bin output/golden.bin`）→ `:202`（`test pass!`）；
  `sum/README.md:97`；`matmul_fused/README.md:105`；`pattern_transformation/README.md:297`。
- → **精度校验发生在 host 侧脚本，与 RUN_MODE 无关**；corpus 未说明 cpu/sim 模式自身是否做任何精度检查（NOT FOUND）。

---

## 6. `ASCENDC_CPU_DEBUG` / `ccec -cpu` / "kernel 直调 CPU" 路径在 corpus 中的实际存在情况

**6.1 `ASCENDC_CPU_DEBUG`：只作为 C 预处理宏存在，不是环境变量，也没有任何文档解释它的语义或谁定义它。**
- 首次/最完整定义性使用：`examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fp8/data_utils.h:28-34`（见 §3.3）。
- 作为"cpu 分支守卫"使用：`examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fused/matmul_fused.asc:283`（`#ifdef`）。
- 作为"cpu 时按芯片名取 platform"守卫使用（约 30 处），例：
  `matmul/matmul.asc:188,190`、`matmul_unitflag/matmul_unitflag.asc:195,197`、`matmul_high_performance/matmul.asc:150,152`、
  `matmul_fp8/matmul_fp8.asc:43,45,246,248,267,269,382,384`、`quant_group_matmul_custom.asc:639,641`、
  `matmul_mx.asc:52,54`、`matmul_tscm_src_vecout.asc:216,218`、`matmul_vecout.asc:248,250`、`batch_matmul_iterate_n_batch.asc:40,42,244,246,369,371` 等。
- **谁定义 `ASCENDC_CPU_DEBUG`（编译器 `-D`？ASC 包？`-DCMAKE_ASC_RUN_MODE=cpu` 的副作用？）—— NOT FOUND。**

**6.2 `ccec -cpu`：NOT FOUND。**
全库无字符串 `ccec`（grep `ccec` 命中 0）。
（旁证：`kb/FINDINGS.md` F7 记录判题机编译器是 `bisheng`，`<ascend>cann-9.0.0/bin`，目标三元组 `aarch64-unknown-linux-gnu`。该文件不在 corpus 内。）

**6.3 `__CCE_KT_TEST__`：NOT FOUND（0 命中）。**

**6.4 "kernel 直调 CPU"路径：corpus 中唯一形态就是 §3.1 的 `GmAlloc` + `ICPU_RUN_KF`，且只有一个文件。**
- `examples/01_simd_cpp_api/04_advanced_api/00_matmul/matmul_fused/matmul_fused.asc:284-295`。
- 未找到 `aclrtLaunchKernel`、`ACLRT_LAUNCH_KERNEL`、独立的 CPU host stub 库、或任何 `host` 侧独立 run 目标（NOT FOUND）。
- 上板路径的统一形态就是 `<<<blocks, l2ctrl, stream>>>(args)` 直调，例：
  `batch_matmul.asc:291`、`matmul.asc:259`、`matmul_unitflag.asc:266-267`、`matmul_high_performance/matmul.asc:305`、
  `matmul_fused.asc:347-348`；`05_simd_simt_hybrid/README.md:141,146,154-156` 说明 `<<<>>>` 各参数含义。

**6.5 `06_cpu_debug` 与 `08_simulator` 的存在性：**
- 在本 corpus 中**只有索引条目**：`examples/01_simd_cpp_api/01_utilities/README.md:14`（CPU调测模式，支持 Ascend 950PR/DT + Atlas A2/A3）、
  `:15`（CAmodel仿真与问题分析，支持 Ascend 950PR/DT + Atlas A3 + Atlas A2）、
  `examples/01_simd_cpp_api/01_utilities/README_en.md:18`（`08_simulator` 英文条目：`CAmodel simulation and problem analysis`）。
- **两个目录的正文（README、CMakeLists、源码、脚本）全部 NOT FOUND。**
- `examples/05_simd_simt_hybrid/README.md:32` 与 `:31`（英文）又各引用一次 `08_simulator` 为"仿真模式下进行功能调试和基础性能数据采集"。

---

## 7. 本 corpus 中 NOT FOUND 清单（汇总）

1. `examples/01_simd_cpp_api/01_utilities/06_cpu_debug/**` 与 `.../08_simulator/**` 的任何文件（目录不存在）。
2. `docs/` 整棵目录树（README 广泛引用的 `docs/zh/quick_start.md`、`docs/zh/api/SIMD-API/...` 均不在本 corpus）。
3. `find_package(ASC)` 提供的 `ASCConfig.cmake` / 任何 `.cmake` 文件（因此 `CMAKE_ASC_RUN_MODE=cpu|sim` 在编译期展开成什么，无法在本地验证）。
4. `-DCMAKE_ASC_RUN_MODE=cpu` 的官方语义说明（宏定义列表、替换库、链接目标、是否内建精度校验）。
5. `ASCENDC_CPU_DEBUG` 作为环境变量的任何文档；以及"谁定义该宏"。
6. 任何 `ccec -cpu` 相关文档或调用。
7. `__CCE_KT_TEST__` 的任何出现。
8. RUN_MODE × CANN 版本的支持矩阵；以及"cpu 模式要求 ≥ CANN x.y.z"的反向声明。
9. cpu/sim 模式本身的限制说明（Cube 仿真、Matmul 高阶 API 支持、多核建模、精度校验、MIX 支持等）。
10. `sim`（CAmodel）模式的命令行入口、运行方式、日志路径、问题分析方法（全部在缺失的 `08_simulator` 下）。
11. 除 `matmul_fused.asc` 外的第二个 `ICPU_RUN_KF` / `GmAlloc` 使用点。
12. `SET_G_CORE_TYPE_IS_AIC` / `SET_G_CORE_TYPE_IS_AIV` 宏的实际使用点（宏在 `matmul_fp8/data_utils.h:29-30` 定义，调用点 NOT FOUND）。
13. 变量名 `ASCEND_CAMODEL` / 裸名 `RUN_MODE`。
14. 任何形式的多核 cpu 调试示例或说明。

---

## 8. 对本地（无 NPU）验证路径的可执行结论（仅限 corpus 可支撑的部分）

可以确定的（有 file:line 支撑）：
- 在 CMake 配置阶段加 `-DCMAKE_ASC_RUN_MODE=cpu`（或 `sim`），arch 用 `-DCMAKE_ASC_ARCHITECTURES=dav-2201`，然后 `make -j`；产物仍是 `./demo`（§1.2、§1.3）。
- 切换模式前必须清 `CMakeCache.txt`（§1.5）。
- 项目骨架必须是 `find_package(ASC REQUIRED)` + `project(... LANGUAGES ASC CXX)` + `add_executable` + `$<$<COMPILE_LANGUAGE:ASC>:--npu-arch=...>`（§2.2）。
- 若要在 cpu 模式下脱离 ACL 运行，语料给出的唯一范式是 `#ifdef ASCENDC_CPU_DEBUG` + `AscendC::GmAlloc` + `ICPU_RUN_KF`（§3.1）。
- 有样例在 CMake 层明确禁止 cpu 模式，因此不能假设它普遍可用（§2.4、§5.2）。
- 精度确认始终由外部 python 脚本完成，与 RUN_MODE 无关（§5.3）。

不能确定的（必须在真机上验证，corpus 无证据）：
- 该判题/开发环境（CANN 9.0.0 + dav-2201）是否真的能成功配置 `-DCMAKE_ASC_RUN_MODE=cpu`。
- cpu/sim 模式下 Cube 单元、Matmul 高阶 API、多核、MIX 任务的行为与精度。
- sim（CAmodel）模式的调用与输出。
