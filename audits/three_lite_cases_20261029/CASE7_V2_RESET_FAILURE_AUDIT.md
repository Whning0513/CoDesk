# Case 7 v2 Isolated 正控：reset 超时与容器归属审计

本记录不改变原运行或源提交。原运行位于 `/data2/whn/CoDesk-case7-v2-dualfs/runs/wa-lite-v2-dualfs-positive-isolated-eoffix-20261031b/`，源提交 `b09d2aadbcb5bc42c1390666c7c5f0d43bf394d9`。最终为 **INVALID_INFRA_OR_RUNNER_ERROR**，不能计为正控 PASS 或模型结果。

真实 GUI 阶段完成：A/B/联合独立 Oracle 均通过；`control_B_peer_view.json` 显示 B 的 Writer 打开 revision 1 只读视图，模式 444、A 源文件 644；`reopen_evidence.json` 显示两个产物分别重开且字节一致。桥记录一次 B 保存中内容变化重试，随后完整版本经传输 SHA/权限核验并提交；最终诊断 unresolved/unknown/historical faults 均为空。这些证据不替代 reset。

A reset 时旧容器 `cf4a15f9e9c2a51440789032363e20991f2a6b1820886ba1fcb243e44e233852` 已销毁，新容器 `db57d200c5a41c57457e13237cc6c0bcc1a08c6b15b750c6a997e8bee4b47fa8` 在 provider 1800 秒就绪期限内未提供截图，抛 `TimeoutError: VM failed to become ready within timeout period`。只读诊断中，新 A 的 `GET /screenshot` 5 秒无响应；旧 B 端点返回 200。QEMU 仍有 CPU 活动；仅凭此无法确定 Guest、虚拟机或服务层根因。

provider 的启动异常分支随后清理了新 A，runner finally 却仍依据旧 A ID 做核验，得到 NotFound 并记录 `cleanup_errors.jsonl`；B 的完整 ID `a44bfa6ba119a681dc7999a4826c61653f7d0604fcfbfa9a1b06ef2b0b4a708b` 有 `guest_closed` 记录。最终 Docker run 标签检查无残留容器、对应 QEMU 进程已退出，writer lease 非阻塞检查可获取。故实际无残留，但旧 runner 的清理身份记录与 reset 新旧代切换不一致；不能将 NotFound 当成新 Guest 已清理的证明。

原 run 的 `failure.json`、`cleanup_errors.jsonl`、`resource_actions.jsonl`、截图及双盘资源样本保留。原 run 没有正常 `result.elapsed_s`，所以资源审计的时间覆盖为 false；独立文件系统采样门槛本身为 true，不能据此把整个资源审计记为通过。不得重写原结果。后续 `a51270b` 仅为独立安全清理候选，新的单次 Isolated scripted 诊断不能证明此次 Guest 启动根因已经修复，也不是正式控制。
