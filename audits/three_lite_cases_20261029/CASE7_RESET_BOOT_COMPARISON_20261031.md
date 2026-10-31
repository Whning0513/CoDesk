# Case 7 v2：两次 Isolated reset 启动资源对照

本报告只读取两次已结束运行的记录。失败样本 `wa-lite-v2-dualfs-positive-isolated-eoffix-20261031b` 的 A 新 Guest 在 provider 截图就绪期限内未就绪，整次运行标为 **INVALID_INFRA_OR_RUNNER_ERROR**。随后 `wa-lite-v2-resetdiag-isolated-20261031c` 的 A/B reset、重开及 scripted Oracle 均通过；它是诊断运行，不证明前次根因已修复，也不是模型样本。

## 配置与启动证据

两次 A reset 新容器的 `resource_audit.json` 实际 QEMU argv 除 run-owned overlay UUID 外完全相同：`-accel tcg,thread=multi -cpu Haswell-noTSX -m 8G -smp 8`，网络、磁盘设备和启动参数也相同。两次 provenance 中的只读 base image 路径、文件长度及 mtime 相同，runtime image ID 相同；这不是两次分别重新计算 base image SHA 的证据。两次开跑前 inotify 探针均为 64/64。失败运行的 provider 日志记录 `_wait_for_vm_ready()` 访问截图端点直至超时；provider 代码会将请求异常统一视为未就绪，配置的就绪期限为 1800 秒。

源提交不同：失败运行是 `b09d2aa`，成功诊断是 `a51270b`。后者增加 reset 后新旧容器 ID 核验和精确清理，并没有改 OSWorld provider、QEMU 启动参数或 base image 配置；一次随后成功不足以证明该改动修复了启动超时。

| 采样项 | 失败：A reset 新容器 `db57d200c5a4…` | 成功诊断：A reset 新容器 `631828a294c0…` |
|---|---:|---:|
| 首次至末次 QEMU 采样 | 22:04:41–22:35:09 UTC，约 1827 秒 | 22:57:23–23:01:41 UTC，约 258 秒 |
| 首次采样后约 61 秒 | RSS 约 557.5 MiB；`write_bytes` 475,136 | RSS 约 954 MiB；`write_bytes` 475,136 |
| 首次采样后约 182 秒 | RSS 约 557.7 MiB；`write_bytes` 475,136 | RSS 约 3,253 MiB；`write_bytes` 96,235,520 |
| 后续表现 | 直至最后采样 RSS 约 557 MiB，写入计数仍 475,136；约 61–182 秒累计 CPU 增加 121.5 秒，接近一核持续运行 | 约 91 秒时 RSS 已约 1,868 MiB、`write_bytes` 21,295,104；之后继续增长。B 的 reset 新容器约 22:59:29 开始被采样 |
| 容器采样 | `throttled_periods=0`、`throttled_time=0`；QEMU `VmSwap=0` | 同左 |

时间以 `resource_samples_v2.jsonl` 首次看到相应容器的样本为零点，约 5 秒采样一次；成功容器的末次采样不是精确的截图服务就绪时刻。`write_bytes` 是 QEMU 进程 `/proc/<pid>/io` 计数，不等于 Guest 内应用的逻辑写入量；`read_bytes=0` 也不能排除页面缓存命中。失败 overlay 仍保留，`file` 识别为 QCOW2 v3、虚拟大小 50 GiB、backing path `/System.qcow2`，文件长度 393,216 字节；仅凭这些不能断定磁盘格式损坏或排除其他磁盘问题。

两次采样中的最小可用空间分别为：run 盘约 **289.157/288.974 GiB**，Docker/Git 盘约 **16.946/16.945 GiB**，均高于 15 GiB 底线；相应 reset 时段宿主 `MemAvailable` 最低约 **947.7/945.6 GiB**，I/O PSI `some avg10` 的记录均为 `0.00`。失败运行的文件系统门槛审计为 true；其总体资源审计为 false，因为异常退出没有正常 `result.elapsed_s`，不能将总体审计说成通过。历史采样没有宿主 CPU PSI 或逐设备 I/O 延迟，显示为 `0.00` 也可能包含显示精度舍入。

## 端口证据与尚不能判定的原因

独立人工审计记录称：失败 A 的一次 `GET /screenshot` 在 5 秒内没有响应，而仍存活的旧 B 端点返回 200。该说明见原诊断工作树的 `audits/three_lite_cases_20261029/CASE7_V2_RESET_FAILURE_AUDIT_UNTRACKED.md`；本次没有找到保存的原始 HTTP 响应、端口绑定快照或完整逐次重试日志。systemd 用户日志只确认该失败新容器约在 22:04:37 启动、22:35:10 退出并累计约 31 分钟 CPU。QEMU 串口配置写入容器内 `/tmp/osworld-serial.log`；容器已由 provider 删除，运行目录没有保留对应串口文件。

因此，资源序列**支持该新 QEMU 在早期阶段长时间没有出现通常的内存和写入增长**，但无法判定卡在固件、Guest 内核、桌面/截图服务或端口转发；也无法仅凭这一次成败差异断言某种软件修复有效。当前证据不支持把失败直接归为 vCPU、RAM 或可用磁盘不足，也不足以排除未采样的 CPU 调度、单设备延迟或 Guest 内部故障。

下一次仅在资源窗口允许且遵守原预注册时，可为每个 run-owned reset 容器保存：完整容器 ID/标签与端口映射，带时间、连接/读取超时和状态码的有限截图健康探针，QEMU `/proc` CPU/RSS/I/O、宿主 CPU/I/O PSI，以及 provider 自动清理前的串口日志。任何日志回收与清理都应先核验完整 ID 和 run 标签。将这些作为环境诊断，不能依据一次成功或失败选择正式样本；不要在当前 Guest 活动时修改运行配置。

证据位置：失败运行 `/data2/whn/CoDesk-case7-v2-dualfs/runs/wa-lite-v2-dualfs-positive-isolated-eoffix-20261031b/`；成功诊断 `/data2/whn/CoDesk-case7-dualfs-reset-candidate/runs/wa-lite-v2-resetdiag-isolated-20261031c/`。主要文件为 `provenance.json`、`resource_samples_v2.jsonl`、`guest_resources.jsonl`、`resource_audit.json`、`filesystem_preflight.json`、`failure.json` 或 `result.json`、`reset_evidence.json` 与相应 driver log。
