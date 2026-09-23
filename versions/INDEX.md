# kernel.asc 版本留档

每一版 kernel.asc 的字节副本 + 假设 + 验证状态 + 官方得分。
得分只在真机/CANNJudge 上产生；本机**不可能**产生 `precision-on-device`。

| 版本 | sha256[:12] | 本地验证 | 官方均分 | submission | 假设 |
|---|---|---|---|---|---|
| v001 | `3c6f619449cf` | none | — | — | baseline: 组委会 kernel.asc 骨架，run_kernel 为空，不做任何计算 |
| v002 | `6948a03e7504` | none | — | — | V0: __mix__(1,2) 单核融合，AIC 做 ND2NZ+Mmad+Fixpipe(L0C->GM)，AIV 从 GM 读回... |
| v003 | `b2c2b086f781` | none | — | — | V0.1: 按编译器反馈修正——wsGm[offset] 直接作为张量实参（去掉多余 SetGlobalBuffer）；ReduceM... |
| v004 | `f807d27cf8fa` | none | — | — | V1: 改用高阶 AscendC::Matmul API + host 侧 MultiCoreMatmulTiling；转置/尾块/l... |
| v005 | `7efd8a89fac7` | compiled-on-device | — | — | v005 = v004 + __kfc_workspace__ workspace 传参（修 ret=507015：Matmul AP... |
