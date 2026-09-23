# 本地编译环境（A 方案）搭建记录

目的：**在本机获得 CANN 编译器（bisheng / ASC），使 `kernel.asc` 在提交前就能编译验证**，
从而彻底消除"交出去才知道编不过"。

编译**不需要 NPU**，只需要 CANN toolkit（编译器 + 头文件 + `find_package(ASC)` + 相关库）。
运行才需要 NPU。

## 已确认的环境事实（2026-09-23 实测）

| 项 | 状态 | 证据 |
|---|---|---|
| 本机 NPU | **无** | Windows 与 Kali 两侧均无 `npu-smi`、无 `/dev/davinci*`、无 `ASCEND_HOME_PATH` |
| 本机 CANN | **无** | 无 `C:\Ascend`、无 `/usr/local/Ascend` |
| Docker CLI | 有 | `C:\Program Files\Docker\Docker\resources\bin\docker.exe` |
| Docker 引擎 | 可用（v29.6.1, linux/x86_64） | `docker info` |
| Docker Desktop 自启 | **关闭**（`AutoStart: false`）→ 每次需手动启动 | `settings-store.json` |
| Docker 出口代理（原） | **失效**：`192.168.2.129:7890` | 拉 alpine 报该地址超时 |
| 本机可用代理 | **`127.0.0.1:7890`**（`iKuuuVPNCore.exe`，监听全网卡，Windows 侧三地址均返回 401 即可用） | `Get-Process -Id 7500` |
| WSL2 → 宿主代理 | **不通**（防火墙拦截入站） | Kali 内 `curl -x http://172.22.224.1:7890` 返回 000 |
| Docker Hub 直连 | **被墙** | `curl --noproxy '*' https://registry-1.docker.io/v2/` 超时 |
| 国内镜像源 | **`docker.m.daocloud.io` 可用** | 返回 401（即成功触达） |
| CANN 官方镜像源（华为 OBS） | 403（需签名/登录） | `ascend-repo.obs.*` 全部 403 |
| hiascend 下载页 | SPA + 许可协议门槛，无公开 XHR 接口 | 页面仅 541 字符文本 |
| PyPI `ascend-cann-toolkit` | **占位包，非真包**（0.0.1.dev1，0 MB） | PyPI JSON |
| PyPI `cann` | **假包**（"a fake package to warn user wrong installation"） | PyPI JSON |

## 已做的修改

1. `%APPDATA%\Docker\settings-store.json`：把失效的手工代理改为**系统代理模式**
   （`ProxyHTTPMode: "system"`、`ContainersProxyHTTPMode: "system"`，并清空四个 Override 字段）。
   备份在同目录 `settings-store.json.bak-*`。
   效果：`docker search` 与经镜像源的 `docker pull` 恢复可用。
2. 已验证：`docker.m.daocloud.io/library/alpine:3.20` 与 `ubuntu:22.04` 拉取成功。

## 候选 CANN 镜像（`docker search cann` 结果）

| 镜像 | 说明 |
|---|---|
| `openeuler/cann` | "The repository for Ascend CANN container images"（openEuler 官方） |
| `ascendai/cann` | 14 stars |
| 其他 | `cosdt/cann`、`wxkicey/cann` 等社区镜像 |

经国内镜像源拉取形式：`docker pull docker.m.daocloud.io/openeuler/cann:<tag>`

**待确认**：可用 tag 与镜像内 CANN 版本是否 **9.0.0**（判题机是 `cann-9.0.0/bin`）。
版本不匹配会导致"本机编过、判题机编不过"，那就白做了——**必须对齐 9.0.0**。

## 下一步

1. 确认镜像 tag 与其中 CANN 版本；必要时改从 hiascend 许可流程下载 `Ascend-cann-toolkit_9.0.0_linux-x86_64.run`。
2. 在该环境内用**组委会的 `CMakeLists.txt`**（`find_package(ASC REQUIRED)`、`--npu-arch=dav-2201`）编译 `kernel.asc`。
3. 编译通过后才提交，不再盲交。
