# Case 7 v2：三次资源受限 Guest 诊断

这三次均为 scripted 诊断，**不是正式控制或模型样本**。两个 Shared 使用不同代码提交，不能作为同一冻结配置的重复；没有运行模型、Isolated 负控或正式对照。全部保留，未按结果筛选。Guest 为 Ubuntu OSWorld / QEMU TCG，设置和 QEMU 参数均为每 Guest 8 vCPU、8 GiB。

| run_id（前缀均为 `wa-lite-v2-diagnostic-`） | 结果 | 提交 | 初始空闲磁盘 / 采样最小值 | 采样 QEMU RSS 峰值 |
|---|---|---|---|---|
| `shared-20261031T1517Z` | 基础设施无效；文件打开对话框未关闭 | `6cc7e77` | 17.13 / 16.64 GiB | 4.92 GiB |
| `shared-openretry-20261031T1750Z` | scripted 诊断 PASS：A/B/联合 Oracle、同步、重开和 reset | `d172666` | 17.12 / 16.64 GiB | 4.98 GiB |
| `isolated-openretry-20261031T1810Z` | 基础设施无效；B Guest 控制接口失联，无 Oracle | `d172666` | 17.10 / 16.06 GiB | 9.28 GiB |

初始空闲由 `df` 记录，采样最小值与 RSS 峰值来自各 run 的 `resource_samples_v2.jsonl`；均是采样值而非绝对峰值，不能证明未来运行的容量上界。三次启动时原 inotify 准入均为 **64/64**，没有放宽原门槛；结束后复查也是 64/64。运行期间未见磁盘 ENOSPC。两个 Shared 的首次检查在此前 2/64 限额不足恢复后进行，资源条件仍可能变化。

第一次 Shared 中，B 前置报告保存，A 修订的只读副本经 SHA 和 0444 校验并回收到宿主。B 在 Writer 文件选择器输入正确修订路径并按 Enter 后，[动作截图](evidence/case7_v2_diagnostic/shared_first_open.png)及[等待结束截图](evidence/case7_v2_diagnostic/shared_first_open_timeout.png)均显示对话框仍打开；等待只读标题超时，未进行最终 Oracle。截图能证明未打开，不能区分 GTK 路径确认行为、输入时序或软件虚拟化延迟。失败记录和 Guest 清理均保留。

第二次 Shared 在 `d172666` 增加了仅供脚本控制使用、仅对仍打开的固定尺寸文件选择器生效的一次 Open 按钮重试。此次初次输入后文件自行打开，[截图](evidence/case7_v2_diagnostic/shared_second_readonly.png)显示真实 Writer 只读 revision 1；**新增重试没有触发，不能声称其实际 GUI 效果已经验证**。消息、SHA、只读镜像及 A 原文件可写模式均有记录；Oracle A/B/联合通过，两个产物重开字节一致，reset workspace clean。资源审计 176 次采样、最大间隔 5.058 秒、结果 valid；全流程约 879 秒。此为脚本正控证据，不是模型成功。

Isolated 中，两个 Guest 桌面启动，[B 的 Writer 初始截图](evidence/case7_v2_diagnostic/isolated_B_setup.png)和 B 前置报告保存已记录；A revision 1 的 B Guest 镜像通过 SHA/0444 检查且副本回收。随后重新激活 B Writer 时，Guest bash 和截图接口连续 `RemoteDisconnected` / timeout，桥后续记录 `guest_probe_error` 与 `sync_error`；最终 `failure.json` 为 `InfraError: no Guest screenshot for 45 s`，没有最终评分。尚不能判断根因是 Guest 服务、QEMU、通信或桥；成功交付的一次视图检查不能证明后续桥健康。运行器自然退出，日志记录两个 Guest 已关闭，事后核实该 run 无容器残留、writer lease 可获取。但桥 stop 曾报 worker 未停止并要求保留 Guest，旧 runner 仍关闭两者；这是需单独修复和验证的清理语义缺口，不能称为完整正常的桥停止。

原始 run、每步截图/动作、bridge 事件、preflight、资源采样、Oracle、重开/reset 和失败记录保留在本机 `CoDesk-case7/runs/<完整 run_id>/` 及 `CoDesk-case7/audits/three_lite_cases_20261029/<完整 run_id>-*.log`，原始目录未纳入 Git；本报告链接的四张原图为选取副本。后续控制和 Pilot 必须在同一新提交上重新执行两种拓扑的完整门槛，不把这里的诊断补作正式结果。
