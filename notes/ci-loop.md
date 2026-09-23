# CANNLab CI 闭环（方案 A）已建立

## 结论：编译回路通了，运行回路还缺 NPU

### 已建立的能力

实例内 `ci/watch.sh` 常驻轮询 `master`：新 commit → `git reset --hard` → `source CANN 环境`
→ `cd work && bash run.sh` → 日志推到 **`ci-logs` 分支**。
开发侧用 `git fetch origin ci-logs` 读取，**完全不依赖终端**（该 Web IDE 的终端是 canvas 渲染，读不到文本）。

首次运行已验证：`ci-logs/result-99a0810.log` 成功产出。

### 首次 CI 结果（commit 99a0810）

```
=== [2/4] Build ===
-- CMAKE_ASC_COMPILER: /home/developer/Ascend/cann-9.0.0/bin/bisheng
[100%] Linking ASC executable batch_matmul_max_sum_custom
[100%] Built target batch_matmul_max_sum_custom
=== [3/4] Gen test data ===
Generated test data and golden output for 1 cases.
=== [4/4] Run + Verify ===
[ERROR] aclInit(nullptr) failed at main.asc:40, ret=500000
=== FAILED (kernel exited non-zero or timed out) ===
=== EXIT=1 ===
```

### 由此确立的事实（A 级证据）

| 断言 | 证据 |
|---|---|
| **CPU 实例只能编译，不能运行算子** | `aclInit` 失败 `ret=500000`（无 Ascend 驱动/设备） |
| 编译工具链与判题机一致 | `CMAKE_ASC_COMPILER=/home/developer/Ascend/cann-9.0.0/bin/bisheng`，clang 15.0.5 |
| `__kfc_workspace__` 注解被编译器接受 | `make` 无 error，仅 `cce_global` 属性 warning（组委会 `main.asc` 同样报） |
| 组委会本地 harness 依赖 device | `main.asc:40` 的 `aclInit` + `main.asc` 中 `aclrtSetDevice(0)` |

⇒ **要验证"跑通"，必须用 NPU 实例（`bmms_dev`）或判题机。** CPU 环境无法替代。

### 当前阻塞

`bmms_dev`（NPU A2 910B3）状态为**「异常」**，操作列只有「关机」（无「启动」），
且其按钮对浏览器自动化的合成/真实点击均无响应。公共池此前启动时报
「当前资源不足，请稍后重试」。

### 迭代路径

```
改 kernel.asc → git push master
   → CI 自动编译（CANN 9.0.0，与判题机同版本）
   → 日志回到 ci-logs 分支 → 开发侧读取
运行/精度验证：判题机（真实设备）或 NPU 实例
```
