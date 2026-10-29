# Spreadsheet Handoff Lite v1：单 SKU 预测到整箱采购

版本 `1.0.0`，Case ID `CDD-SH-LITE-001`。这是独立于原版 Case 6 的短程任务；原工作簿、Gold、Oracle 和实验记录不得覆盖。

## 用户需求与公开输入

采购经理需要为 SKU-LAMP 制作一个不超预算的两个月补货决定。公开 Calc 文件 `forecast_input.ods` 给出 6–8 月销量、现有库存、确认在途和安全库存；`order_template.ods` 给出整箱规格、单价和预算上限。规则是：两个月需求 = 三个月平均销量 × 2；净需求 = max(0, 需求 + 安全库存 − 现有 − 在途)；采购量必须是覆盖净需求的最小整箱倍数；采购成本 = 采购量 × 单价，不能超过预算。原始数据和规则在两种拓扑中完全相同。

## 角色分工

- **A（预测核验）**：在已打开的 `forecast.ods` 的 `Forecast!H3` 填写净需求，在 `I3` 标出所用输入范围。通过 Calc GUI 保存、发布 revision，并把核验值和来源发送给 B。只编辑自己的工作簿。
- **B（采购规划）**：可先查看已打开的 `order_plan.ods` 中的箱规、单价和预算。收到 A 的已保存 revision 和消息后，在 `Order!E3` 填最小整箱采购量、`F3` 填采购成本；保存并发布。若无法调和预测或预算，向 A 说明。只编辑自己的工作簿。

两人可同时准备。Shared 中两个独立模型 Agent 并发操作同一个真实 Calc 桌面，键鼠和焦点不加锁；Isolated 中各用一个 Guest，消息与完整保存后的工作簿通过同一版次桥传播。B 的计划必须利用 A 已保存的预测；仅填写 revision/hash 字符串不能证明交接，行为审计另核对 A 保存与发信、B 读信和之后编辑保存的顺序。

## 产物、评分和边界

公开输出路径为 `outputs/agent_A/forecast.ods` 与 `outputs/agent_B/order_plan.ods`。评分侧 Oracle 从公开源单元格计算期望值，检查 A 数值与输入范围证据、B 最小整箱采购量与成本、预算和两文件一致性，并检查源单元格未被改写。接受等价数值输入，不依赖固定英文句子。Gold/Oracle 不安装进 Actor Guest。脚本正负控、真实 Guest 保存/回收/重开/reset 及模型轨迹分别报告；没有真实 Guest 和独立评分证据，不标为模型 PASS。

目标 scripted GUI 路径为 A 约 7 次、B 约 7 次桌面调用，合计约 14 次；每角色 25 次只是模型预算，不强制同时点击，也不加 Shared 专属障碍。
