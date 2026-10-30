# Spreadsheet Handoff Lite v1.1：单 SKU 预测到整箱采购

独立于 Lite v1.0.0 和原版 Case 6；保留旧 Task Card、Fixture、Gold、Oracle 与全部实验记录。本版沿用单 SKU、两份 Calc 文件、相同的真实交接和预算规则，只明确单位与保存步骤，减少非核心窗口导航。

## 用户需求与公开输入

采购经理需要为 SKU-LAMP 制作不超预算的两个月补货决定。`forecast_input.ods` 给出 6–8 月销量、库存、在途和安全库存，全部以**件**为单位。`order_template.ods` 给出每箱件数、每件美元单价和预算上限。两个月需求 = 三个月平均销量 × 2；净需求 = max(0, 两个月需求 + 安全库存 − 现有 − 在途)。采购量必须是覆盖净需求的最小整箱倍数，**E3 填件数而非箱数**；F3 = E3 × 每件单价，且不超过预算。

## 角色与信息交接

- **A（预测核验）**：在已打开的 `forecast.ods` 中，把净需求填入 `Forecast!H3`，在 `I3` 标出输入单元格范围。每格按 Enter 提交，保存 Calc 文件后发布修订，并把已核验值与来源发给 B。仅发消息而没有保存修订不算交付。
- **B（采购规划）**：可先查看已打开的 `order_plan.ods` 中每箱件数、每件单价和预算。收到 A 的**已保存修订与消息**后，将最小整箱采购件数填入 `Order!E3`，采购总成本填入 `F3`；保存并发布。若修订与消息矛盾，再通过 GUI 打开 A 文件核对。未收到交付时可请求并挂起，由公共生命周期唤醒，不需用 GUI 轮询。

两人可同时准备。Shared 中两个独立模型 Actor 操作同一 Calc 桌面、同一键鼠与窗口焦点；Isolated 中各用一个 Guest，消息及完整保存的工作簿经相同版本桥传播。B 的数字必须由 A 的正确交付支撑。行为审计核对 A 的保存/发布/发信、B 的修订与消息读取及之后的编辑/保存，不能只凭自报的 revision 字符串宣称完成协作。

## 产物、评分与边界

交付 `outputs/agent_A/forecast.ods` 和 `outputs/agent_B/order_plan.ods`。私有 Oracle 由公开源单元格推导期望值，核对 A 净需求、来源范围、B 最小整箱件数、单价乘法、预算、两份工作簿一致性与源单元格未改写。Gold 和 Oracle 不安装进 Actor Guest；接受等价数值输入。Isolated、Shared 无锁与 Shared+Lock 使用相同 Prompt、Fixture、预算与评分。脚本正负控、真实 Guest 重开/reset、模型轨迹分别报告。

核心 scripted GUI 路径仍约 A 7 次、B 7 次调用；25 次每角色是模型恢复预算。Shared 基线不加 GUI 输入锁。若研究输入锁，另设 `Shared+Lock` 实验臂，保持任务与评分完全一致。
