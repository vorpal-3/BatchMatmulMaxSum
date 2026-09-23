# CANNLab 环境已就绪（2026-09-23）

## 账号额度（CANNLab 公共资源池）

| 资源 | 额度 | 已用 |
|---|---|---|
| CPU 通算 | 720 核时 | 0 |
| A2/A3 智算 NPU | 100 卡时 | 0 |
| CANN 积分 | 200 | — |

## 已创建实例

| 名称 | 类型 | 镜像 | 规格 | 状态 |
|---|---|---|---|---|
| `bmms_cpu` | CPU | `cann_9_0_0-py3.12-a5-arm-20260921` | ARM 16vCPU/32GiB | 开机中 |
| `bmms_dev` | NPU A2 | `cann_9_0_0-py3.11-a2-arm-20260921` | 1×NPU 910B3, 16vCPU, 32GiB | 已关机（公共池暂时无空闲卡） |

持久化目录：`/mnt/workspace`、`/home`。

## 判题机与云端的对齐情况

| 维度 | 判题机 | CANNLab | 对齐 |
|---|---|---|---|
| CANN 版本 | `cann-9.0.0` | `cann_9_0_0` | ✅ |
| 架构 | `dav-2201`（A2/910B） | 910B3（A2） | ✅ |
| 工具链 | bisheng clang 15.0.5 | 同镜像 | 预期一致 |

## 意义

1. **编译反馈可以拿到本地侧** → 不再"盲交"。这是之前流程错误的根治。
2. CPU 环境即可完成 `find_package(ASC)` + `--npu-arch=dav-2201` 的编译验证。
3. NPU 环境用于真实运行与性能数据（等容量释放）。

## 入口

- 能力概览：`https://gitcode.com/?tn=cannlab-overview`
- 我的环境：`https://gitcode.com/?tn=cannlab-environment`
