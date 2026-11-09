# EDIT-1 Writer 固定宽度审阅码交接 Lite v1

**案例 ID：** `CDD-EDIT-001`
**版本：** `lite_v1`

## 业务目标

发布协调员与文档审阅员共同完成一份待发布公告：状态行必须明确标记 `READY`，审阅码必须改为 `AB12`，保护语句保持原样。A、B 的工作可并发进行；两项修改在同一份共享公告中合并后才能发布。

## 初始文件

Actor 可见的 `release_notice.fodt` 包含三行：

1. `Release status: STATUS | HOLD-FOR-REVIEW`
2. `Reviewer code: ____; fixed-width field`
3. `Guard phrase: DO-NOT-ALTER-THIS-LINE`

Fixture 与隐藏 Gold 独立生成。Gold/Oracle 路径不得挂载到 Actor Guest 或放入 prompt。

## Agent A：发布协调员

在 Writer 中将 `READY ` 插入到 `HOLD-FOR-REVIEW` 前，形成 `READY HOLD-FOR-REVIEW`。不得破坏风险短语、审阅码或保护行。保存，并向 B 发送完成消息。A 可在 B 编辑期间先行工作。

## Agent B：文档审阅员

在 Writer 中将第二行的固定宽度 `____` 改为 `AB12`，其余字符保持不变。保存，并通知 A 已完成。B 可在 A 编辑期间先行工作。

## 协作依赖与拓扑

A 与 B 必须在同一公告发布前合并各自修改；双方消息和保存版本用于核验交接事实。

- Isolated：两个独立 Guest，A、B 各有独立桌面与初始文件副本，最终分别回收 `release_notice_A.fodt`、`release_notice_B.fodt`；联合评分要求 A 的状态行与 B 的审阅码正确。
- Shared：两名独立 Agent 操作同一 Guest、同一 Writer 文档和同一桌面，不加输入锁；最终只评分共享的 `release_notice.fodt`。
- Shared+PerActionLock：除逐动作输入锁外与 Shared 相同。

正式三臂必须复用相同 Fixture、角色指令、Agent 工具、预算和 Oracle。任务执行期间只能向 Actor 提供 public 文件。

## 成功条件

Shared 的最终文档必须逐行精确为：

```text
Release status: STATUS | READY HOLD-FOR-REVIEW
Reviewer code: AB12; fixed-width field
Guard phrase: DO-NOT-ALTER-THIS-LINE
```

Isolated 联合成功要求 A 输出中的状态行及保护行精确，且 B 输出中的审阅码行及保护行精确。除任务指定的内容外，任何额外变更都判对应角色失败。

只在以下证据同时成立时，将失败归因于 Insert/Overwrite 共享状态：B 的 GUI 轨迹确认切换到 OVR 并完成 AB12；A 的计划形成于 INS 观察之后且恢复时未刷新；同一 Writer 文档/窗口；A 的首个恢复输入实际覆盖了 `HOLD-FOR-REVIEW`；最终保存的完整文本具有 `READY OR-REVIEW` 覆盖特征。共享状态仅被改变但任务最后恢复成功，应记为恢复，不记为最终失败。

每角色目标约 10–15 个有效 GUI 操作。模型额外操作按真实轨迹记录，不因超出目标而截断。
