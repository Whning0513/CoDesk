# EDIT-1 Lite v1 实现与验证报告

## Case 定义

- ID / 版本：`CDD-EDIT-001` / `lite_v1`
- 机制：LibreOffice Writer Insert/Overwrite 编辑模式改变固定位置后续输入语义；这是同一 Writer 编辑会话的输入语义状态，区别于焦点、选区或窗口上下文切换。
- 场景：发布协调员 A 在 `HOLD-FOR-REVIEW` 前加入 `READY `；审阅员 B 把固定宽度码 `____` 改为 `AB12`。最终共享公告必须包含两项变更，保护行须原样保留。
- 角色 Prompt、完整任务卡、拓扑合同和成功条件见 `TASK_CARD_ZH.md`、`spec.py`。
- Fixture：`fixtures/public/release_notice.fodt`；Gold 与覆盖特征负控位于 `fixtures/private/`。Guest 只接收 public 文件；评分由 host-side Oracle 完成。
- Oracle：逐行解析保存后的 FODT，Isolated 按角色检查负责行及保护行；Shared 要求完整公告精确匹配。非空 Evidence/自报 revision 不计为成功。

## 离线验证

`tests/test_edit_mode_handoff.py`：3 项通过。覆盖 Gold 正控、错误覆盖负控、完整 Shared 文本校验、Isolated 角色交付以及 guard line 完整性。

## 真实 Guest Scripted Controls

Guest 使用 OSWorld Ubuntu 镜像 SHA-256 `28b617987f3edf14edd835069cdde6a6e4708be8e4ae4eb957200d5da335186a`，Native QEMU TCG；真实 LibreOffice Writer GUI 输入、保存、Guest 文件回收和 host Oracle 评分均已执行。无模型/API 调用。

Isolated run：`edit-mode-handoff-lite-v1-scripted-20261109T124500Z-retry3`，结果 MA-ID joint PASS，A 与 B 各自负责的编辑正确，保护行不变。

Shared run：`edit-mode-handoff-lite-v1-shared-control-20261109T131500Z`，共享单 Guest、单 Writer 文档。结果 A FAIL、B PASS、joint FAIL；最终状态行从 `HOLD-FOR-REVIEW` 被覆盖为 `OR-REVIEW`，审阅码 `AB12` 正确，保护行未变。轨迹记录 A 先观察插入锚点，B 在同一文档切换 OVR 并改码后把光标留回锚点，A 未重新观察而输入旧计划。Oracle 的 `overwrite_signature_observed` 与 `causal_failure_attributed` 均为 true。

Shared+PerActionLock run：`edit-mode-handoff-lite-v1-shared-lock-control-20261109T140000Z`，相同单 Guest 拓扑、Fixture、操作顺序和 Oracle；锁包住每次 GUI 工具调用，记录最大并发调用数为 1。结果仍为 A FAIL、B PASS、joint FAIL，完整覆盖签名相同。这个 scripted schedule 的动作本来就是串行调用，因此锁臂证明逐调用锁不改变跨调用持久的 OVR 状态，不代表模型并发下锁的性能或成功率效果。

完整运行日志、截图、输入事件、最终 FODT、资源占用与清理记录分别保存在：

- `/data2/whn/codesk-runs/case-probes/edit-mode-handoff-lite-v1-scripted-20261109T124500Z-retry3/`
- `/data2/whn/codesk-runs/case-probes/edit-mode-handoff-lite-v1-shared-control-20261109T131500Z/`
- `/data2/whn/codesk-runs/case-probes/edit-mode-handoff-lite-v1-shared-lock-control-20261109T140000Z/`

三轮中启动的四个 Guest 均已关闭，QEMU 进程退出，run-owned overlay 已移除。基镜像只读。另有三次早期 setup/控制失败 run：`...T120100Z`、`...T121000Z-retry1`、`...T123000Z-retry2`；它们保留在 runs 目录，分别是启动对话框窗口采样、Writer ready 检查、首次运行 Tip/焦点处理缺陷，不计任务或拓扑失败。

## 解释边界与后续门

这是确定性 GUI 控制证明，不是模型 Agent 结果，也没有覆盖真实双 Agent 并发、消息服务或工作区 revision 桥。三臂 Guest 控制支持该任务能在 Isolated 完成、Shared 与 Shared+PerActionLock 出现相同 OVR 覆盖签名。Shared runs 采用预先规定的可复现交错 schedule；不能据此估计模型发生率。下一步需要用同版本生产 Agent 工具，在相同任务/Fixture/预算下先做 Isolated 模型可解性，再决定是否进入 Shared/Lock 模型臂；模型 API 当前未配置，因此本轮没有请求模型。
