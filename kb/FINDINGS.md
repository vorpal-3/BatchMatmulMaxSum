# 平台事实（有证据）

本文件只记录**有出处**的事实。每条给出：断言、证据、证据强度、适用范围。

证据强度只有三档，不要混用：

- **A｜编译器/判题机直接产出** — 来自 CANNJudge 返回的 bisheng 编译日志或 profiling 结果。可当作硬约束。
- **B｜官方一手源码** — 来自 `kb/corpus/` 的 asc-devkit / cann-samples 真实源码或官方文档。
- **C｜推断** — 由 A/B 组合得出的结论，**尚未验证**，必须标明。

适用范围均锚定 **CANN 9.0.0 / `dav-2201`**。换版本或换芯片必须重新取证。

---

## F1｜判题机提交契约（A）

`POST https://cannjudge.cn/api/submissions/submit`，`Content-Type: application/json`，
凭据是 Cookie `cannjudge_auth=<JWT>`（HttpOnly 会话令牌）。

```json
{
  "problemId": "6a9aa054bf41025d6014f3ef",
  "files": [{"path": "kernel.asc", "content": "<源码>"}],
  "tiling_h": "", "tiling_key_h": "", "host_cpp": "", "kernel_cpp": "",
  "userId": "<uid>"
}
```

返回 `{"code":0,"msg":"success","data":{"submissionId":"<id>"}}`。

浏览器的网页编辑器**只提交 `kernel.asc`**（实测请求体中其余四个槽位为空串）。
**证据**：2026-09-23 13:56 抓取的真实提交请求（练习题目 `quantbatchmatmulv3pertoken`，提交 ID 419920）。

## F2｜结果查询接口暴露逐用例 T（A）

`GET /api/submissions/{id}?userId={uid}` 的 `result` 是 **15 条**记录，每条含：
`testcase_id`、`time`、`precision_ratio`、`testcase_status`、`msg`、`score`、`type`、**`best_time`**。

`best_time` 就是计分公式 `100/(1+log_1.5(t/T))` 里的 **T**。
**这意味着：任何一次成功提交都会返回官方 T 表**，可用于把本地隐藏评测集与官方分数做校准——不必猜测 T。
**证据**：同上。

## F3｜每次迭代必须恰好启动 1 个 kernel（A）

空 kernel 被 profiling 拦下：

```
Profiling rule violated: each iteration must launch exactly 1 kernel.
Expected 75 launches, got 0.
```

75 = **15 用例 × 5 轮迭代**（与题目元数据 `iterations: 5` 一致）。
**推论**：题面里作为性能基线的「BatchMatMul + ReduceMax + ReduceSum 拆分实现」**不可能作为提交通过**（那是 3 次启动）——**必须真正融合成单 kernel**。
**证据**：提交 ID 419920 的 15 条记录，全部同一条消息。

## F4｜`__global__` 必须带正确的核类型限定（A）

```
WARNING: kernel type of __global__ func:
  batch_matmul_max_sum_custom(unsigned char*, unsigned char*, unsigned char*,
                              long, long, long, long, bool, bool) is not ma[tched]
```

不带核类型限定（`__cube__` / `__vector__`）的 `__global__` 函数**类型不被匹配**。
模板注释给出的目标签名是 `__global__ __cube__ void batch_matmul_max_sum_custom(...)`。
**证据**：提交 ID 413801 的编译日志。
**待补**：该 warning 是否升级为失败的确切条件（本次提交因其它原因失败，警告本身是否致命未单独验证）。

## F5｜`SetSysWorkspace` 在 CANN 9.0 已废弃（A+B）

```
warning: 'SetSysWorkspace' is deprecated: NOTICE: SetSysWorkSpace has been deprecated
         and will be removed in the next version. [-Wdeprecated-declarations]
```

对应的**现行写法**在官方样例中是 `AscendC::InitSocState();`（B 级证据，见
`kb/corpus/asc-devkit/examples/01_simd_cpp_api/03_basic_api/01_memory_vector_compute/duplicate/duplicate.asc`）。
**证据**：提交 ID 414065 的编译日志 + 上述官方源码。

## F6｜后端不支持 bf16 类型转换（A）

```
fatal error: error in backend: not support bf16 type cast
bisheng: error: clang frontend command failed with exit code 70
```

**这是致命错误，直接编译失败。** 题目要求支持 BFLOAT16 输入，因此 bf16 路径必须**绕开类型转换**（例如以整型/reinterpret 方式处理，或选用不经由该 cast 的 API）——具体替代方案**尚未取证，属待办**。
**证据**：提交 ID 414177 的编译日志。

## F7｜编译工具链身份（A）

- 编译器：**bisheng**（clang 15.0.5，`clang-5c68a1cb1231 flang-5c68a1cb1231`）
- 安装路径：`<ascend>cann-9.0.0/bin`
- 目标三元组：`aarch64-unknown-linux-gnu`；设备架构经 `--npu-arch=${SOC_ARCH}`（默认 `dav-2201`）
- 构建：CMake 3.16+，`find_package(ASC REQUIRED)`，`project(... LANGUAGES ASC CXX)`

**证据**：提交 ID 414177 的编译日志 + 模板 `CMakeLists.txt`。

## F8｜判题机的 `judge.asc` 契约（A）

判题机用 `judge.asc` `#include` 提交的 `kernel.asc`，内部有 `num_cases(15)` 与按 `case_end` 分段执行的逻辑；
本地 `main.asc` 则硬编码单个 64 字节极小用例（`x1={1,1,32}`、`x2={1,32,1}`、`y={1}`）。
**因此本地 harness 只能冒烟，15 个真实用例只在判题机跑。**
**证据**：编译日志中的 `judge.asc:59` 行 + 模板 `main.asc`。

## F9｜历次失败模式汇总（A）

截至 2026-09-23，本账号在上合赛区题目上的 9 次提交：

| 状态 | 次数 |
|---|---|
| Compile Error | 4 |
| Runtime Error | 3 |
| Time Limit Exceeded | 2 |

**全部 15 个用例均未被计分（逐用例条目数为 0 或全 0 分）。**
**证据**：`GET /api/submissions/user/{uid}/problem/{pid}`。

## F10｜提交配额与排名语义（B）

- 每天 **50** 次提交，两次间隔 **≥ 2 分钟**。
- 排名 **取比赛期间最后一次提交**（`ranking_submission_mode: "latest"`）。
- 单用例得分 `100/(1+log_1.5(t/T))`；**精度全过才计分**；最终分 = 全部用例均值。

**证据**：赛事规则页 + 题目元数据（`gitcode` 活动接口与 CANNJudge 题目接口）。

## F11｜失败模式目录（A）

本账号 9 次提交的**去重错误签名**，按时间排列。这是"通用 Ascend C 写法在此平台上具体错在哪"的一手证据。

| ID | 状态 | 关键信息 |
|---|---|---|
| 413801 | Compile Error | `WARNING: kernel type of __global__ func: batch_matmul_max_sum_custom(...) is not marked. auto type derivate may be failed.` → 随后 `ld.lld: error: Error: the type of kern...` |
| 413845 | TLE | （无消息） |
| 414065 | Compile Error | `'SetSysWorkspace' is deprecated`（`kernel_operator_common_impl.h:28`）+ **`error: no matching function for call to 'GetSysWorkSpacePtr'`**（`kernel.asc:135`） |
| 414141 | Compile Error | **`error: no matching function for call to 'ReduceSum'`**（`kernel.asc:139`）；候选：`reduce.h:240` "couldn't infer template argument **'pattern'**"；`kernel_operator_vec_reduce_intf_impl.h:935` "could not match **'LocalTensor' against 'TBuf'**"；`reduce.h:216` 需 **5 个参数**（实际给 4 个）；其余候选需 6 个 |
| 414177 | Compile Error | 前面同 F4 的 warning，真正致命的是 `fatal error: error in backend: **not support bf16 type cast**`（见 F6） |
| 414235 | Runtime Error | `aclrtSynchronizeStreamWithTimeout failed, ret=**507035**` + `Get profiling data failed` |
| 414293 | Runtime Error | `aclrtSynchronizeStreamWithTimeout failed, ret=**507046**` + `Get profiling data failed` |
| 414506 | TLE | 同 413845 |
| 419799 | Runtime Error | 同 414293（`ret=507046`） |

**可读出的推进轨迹**：编译错误（核类型未标记 → 废弃 workspace API → `ReduceSum` 签名/`pattern` 模板参数 → bf16 cast）
→ **能编译并成功启动 kernel**（否则会像 F3 那样报 "0 launches"），但在执行阶段失败或超时（`507035` / `507046`）。

**由此确立的下一步优先级**：当前瓶颈**不是性能优化，而是让单个 kernel 正确编译并跑完**。在拿到一次"精度通过"之前，讨论 tiling 与加速比没有意义。

**待补**：`507035` / `507046` 的 ACL 官方含义（未取证）；`ReduceSum` 的正确调用形态（`pattern` 取值、目标须为 `LocalTensor`）。

---

## 待取证清单（不要凭记忆回答）

1. F4 的 warning 是否致命。
2. F6 的 bf16 正确写法（替代 cast 的 API 路径）。
3. `__cube__` 核内**可用 API 集**（与 `__vector__` 的差异），以及 Cube 核是否可用 `Add` 等 Vector 指令。
4. `DataCopy` 的 32B 对齐规则与非对齐尾块的正确处理（本题明确要求支持非对齐）。
5. L1→L0A/L0B 的**分形(fractal)布局**转换；`Fixpipe` 在 **2201 与 3510** 下的参数结构体差异。
6. L0C 中的 (M,N) 分块如何沿 N 取 max（跨 fractal 归约放在 Cube 还是 Vector 侧）。
7. `TQue/TPipe` 队列深度与 Double Buffer 的成立条件（注意：官方 9.0 样例用的是 `LocalMemAllocator`，与模板注释建议的 `TPipe/TQue` 不同）。
8. `availableCoreNum`（`ACL_DEV_ATTR_CUBE_CORE_NUM`）在 `dav-2201` 上的实际取值与多核切分策略。
