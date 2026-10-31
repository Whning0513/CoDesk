# Case 7 v2：截图 deadline 候选 Shared / Isolated 诊断

两次均为**真实 Ubuntu Guest 的 scripted 正控诊断**，源提交同为 `d20da177c7a7160e2420d400929a0fc47a32ee2b`，不是模型实验，也不补作预注册六项正式控制。模型未调用。旧运行和[此前失败诊断](CASE7_V2_DIAGNOSTICS_20261031.md)保留。

| 运行 ID | 拓扑 | A / B / 联合 Oracle | 全程 | 初始 / 采样最低可用磁盘 | QEMU 采样 RSS 峰值 |
|---|---|---|---:|---:|---:|
| `wa-lite-v2-diagnostic-shared-deadline-20261031T1850Z` | 单 Guest | PASS / PASS / PASS | 932.8 秒 | 17.04 / 16.54 GiB | 4.97 GiB |
| `wa-lite-v2-diagnostic-isolated-deadline-20261031T1910Z` | 双 Guest | PASS / PASS / PASS | 1320.8 秒 | 17.02 / 16.00 GiB | 9.23 GiB |

每 Guest 的请求和实际 QEMU 参数均为 8 vCPU、8 GiB；QEMU 使用 TCG。两次启动前 inotify 测试均为 64/64，无降低准入门槛；未观察到磁盘 ENOSPC。RSS 与磁盘低点均是采样值，不能保证未来峰值。Shared 资源审计 186 次采样、最大间隔 5.055 秒；Isolated 264 次、最大间隔 5.068 秒，均为 valid。两次 reset 与清理后，run 标签的 Guest 均已关闭；末次复核无本项目 Guest 或 runner，writer lease 可获取，inotify 为 64/64。

两次 B 的报告准备保存时间均早于 A 的 revision 1 提交，A 的记录消息仅通知文件与修订可用。A 的 revision 1 在 B 侧经 SHA 和 0444 校验，A 原文件模式 644；B 均在 GUI 打开该只读文件。脚本在两次均检测到打开对话框仍存在，触发一次有记录的按钮重试；[Shared 重试前截图](evidence/case7_v2_deadline_diagnostics/shared_before_retry.png)与[只读结果](evidence/case7_v2_deadline_diagnostics/shared_readonly.png)、[Isolated 重试前截图](evidence/case7_v2_deadline_diagnostics/isolated_before_retry.png)与[只读结果](evidence/case7_v2_deadline_diagnostics/isolated_readonly.png)均为原始截图副本。每次的 `control_B_open_retry.json` 和 `actor_runs/B/stage-03/trace.json` 保存触发原因和动作；该重试只用于脚本控制，不由框架替模型 Actor 操作。

两次桥 `final_sync_succeeded` / `verified` 均为 true，持久诊断未见历史故障；双方产物重新打开后 SHA 与回收时一致；Shared 的一个及 Isolated 的两个 Guest 均完成 workspace clean reset。每步截图、窗口与动作、消息、修订事件、文件副本、Oracle、资源采样、重开和 reset 证据保留在本机 `CoDesk-case7/runs/<完整运行ID>/`；启动 preflight 与 driver 日志位于 `CoDesk-case7/audits/three_lite_cases_20261029/<完整运行ID>-*`。上述四张截图的 SHA 列于同目录 `SHA256SUMS`。

正常真实 Guest 截图获取及正常退出已验证；两次均**未触发** Guest 截图超时或桥 worker 卡死，不能将这两条故障处置路径称为真实 Guest 实测通过。截图硬 deadline、helper 回收以及桥停止/延迟清理的异常分支目前由离线测试覆盖；清理 supervisor 的外层等待仍无整体 deadline，且标记写入或 Docker 不可用时需要人工核查。此前 Isolated 的失联根因仍未知。候选提交离线全量为 `311 passed, 2 skipped`，其中 FakeOSWorld 测试使用内存截图替身，独立截图 deadline 测试使用本地 HTTP 服务。
