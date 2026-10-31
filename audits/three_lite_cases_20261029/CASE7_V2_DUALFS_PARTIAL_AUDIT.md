# Case 7 v2 双盘控制：阶段审计（尚未完成）

本页截至 2026-10-31，汇总运行在 `/data2/whn/CoDesk-case7-v2-dualfs` 的控制；不是模型实验。完整逐步截图、动作、原产物、Oracle、桥事件及资源记录留在该工作树的 `runs/<run_id>/`，每次 `resource_audit.json` 记录双盘采样和 Guest 配置。历史记录不覆盖，不将不同源提交的控制混为一套。

源 `d35f2083d6b1136fafe9f9e79a418c65ea489334` 的离线测试为 314 passed、2 skipped。以下四控的 `_control` 验证、资源审计、桥无历史错误、双产物重新打开、全部 Guest workspace clean reset 均通过。两次正控 Oracle A/B/联合均 PASS；两次负控故意填错标签，Oracle A PASS、B/联合 FAIL，B local 唯一失败是标签不等于实际交付。截图经人工核对。

| 控制 run ID | 实际 Oracle | 全程秒 | /data2 run 采样最低 GiB | /data3 Docker/Git 采样最低 GiB | 关键截图（相对于该 run） |
|---|---|---:|---:|---:|---|
| `wa-lite-v2-dualfs-positive-shared-20261031a` | PASS / PASS / PASS | 899.7 | 289.77 | 17.00 | `screenshots/B-004.png`、`screenshots/control_B_peer_view.png` |
| `wa-lite-v2-dualfs-positive-isolated-20261031a` | PASS / PASS / PASS | 1345.1 | 289.22 | 17.00 | `screenshots/B-003.png`、`screenshots/control_B_peer_view.png` |
| `wa-lite-v2-dualfs-negative-shared-20261031a` | PASS / FAIL / FAIL（预期拒绝） | 912.6 | 289.72 | 17.00 | `screenshots/B-014.png` |
| `wa-lite-v2-dualfs-negative-isolated-20261031a` | PASS / FAIL / FAIL（预期拒绝） | 1366.0 | 289.23 | 17.00 | `screenshots/B-010.png` |

四控启动时 inotify 均达 64/64；每 Guest 请求与实际 QEMU 参数均为 8 vCPU、8 GiB，运行盘、Docker data 和 Git common 的 15 GiB 及 inode 门槛均有 preflight 和全程采样记录。采样最小值不是未来峰值保证。

同一 `d35f208` 的 Shared 修订探针 `wa-lite-v2-dualfs-probe-shared-20261031a` 为基础设施/探针无效：GUI Text Editor 保存恢复文本时多了一个末尾 LF，原始 revision 1 为 91 字节，revision 3 为 92 字节，因此原样保留的 SHA 字节检查正确拒绝。三版归档与 `screenshots/A-012.png` 保留；未给该运行判模型失败。失败没有 `result.elapsed_s`，所以资源审计时间覆盖同时标 invalid；双盘采样本身未越线，Guest 已精确清理。

此后仅修改 scripted 探针恢复 EOF 操作，保持 fixture、任务、Prompt、Oracle、模型 Actor 和 revision1/3 字节检查不变；新源 `b09d2aadbcb5bc42c1390666c7c5f0d43bf394d9` 离线全量 318 passed、2 skipped。新 Shared probe `wa-lite-v2-dualfs-probe-shared-eoffix-20261031b` 完整 PASS：revision 1 与 3 SHA 相同、revision 2 不同，三份 view 均 444、A 原文件 644；B 的 `screenshots/control_B_peer_view.png` 显示只读 revision 3，Oracle / bridge / 重开 / reset / 双盘采样均通过，freeze `_control` 通过，耗时 1058.6 秒。**该新源 probe 不补入旧源四控，旧源四控也不补入新源控制集。**

同一新源的 Isolated probe 与四项正负控仍需独立完成；完成前不运行模型或宣布六控通过。
