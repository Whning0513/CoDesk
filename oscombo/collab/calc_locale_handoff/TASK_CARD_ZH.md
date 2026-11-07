# CALC-LOCALE1 candidate-0.1：多地区报价核验与采购建议

**状态：候选设计。** 这张任务卡对应新增目录中的独立版本，不修改既有 Case。当前仅完成真实 Guest 的 Calc 数值解析机制门和离线 Oracle 骨架。

## 用户需求

采购台需要比较 Northstar 的 USD 报价和 Elbe Office Supplies 的 EUR 报价，判断哪家供应商符合 250 美元预算并给出可追溯建议。两份报价使用不同的小数约定。最终建议必须使用 B 保存的 EU 报价数值，不能只根据消息里手打的版本号或金额。

## 工作簿与公开 Fixture

Actor 只拿到 `fixtures/public/` 下的三个 ODS 文件：

- `vendor_us.ods`：Northstar 的 USD 单价、运费源文本及 10 件数量。A 将源文本录为数值，并填写 landed total。
- `vendor_eu.ods`：Elbe 的 EUR 单价、运费源文本、10 件数量和 1.08 USD/EUR 汇率。B 将逗号小数录为数值，计算 USD landed total。
- `purchase_decision.ods`：250 美元预算和待填写的两家总额、推荐供应商、来源说明。

所有角色都可看到原始报价和规则。任何 `fixtures/private/` 文件或 Oracle 结果都不进入 Guest、Actor Prompt 或 Actor 可读取目录。

## A/B 分工与信息依赖

### Agent A — Northstar 与最终决策

处理 USD 报价，保存单价、运费和公式计算的总额。可以先独立完成自己的报价核验。随后打开 B 保存的 `vendor_eu.ods`，核实其中的数值和来源，再把两家的总额写入 `purchase_decision.ods`，应用预算并保存推荐。

### Agent B — Elbe EU 报价

根据 EU 报价中的逗号小数，在 Calc 中设置与报价相符的地区格式，将单价和运费录为数值，按数量和汇率计算 USD landed total，保留源报价并保存 ODS。通过消息及已保存附件告知 A 产物已就绪。

两人可以并发开始。A 最终推荐依赖 B 的已保存 EU 总额，因此不是两项互不相干的单人任务。不会要求 Agent 同时点击或使用同一控件。

## 成功条件

1. 两份报价中的源文本未改写，数量、汇率等输入保持完整。
2. A、B 的录入单价和运费都是 ODS 中的数值类型；总额由公式计算并与源报价一致。
3. A 打开并核对 B 已保存的 ODS；`purchase_decision.ods` 中的 EU 总额等于 B 文件的实际保存值。
4. 最终推荐符合预算及两家报价比较结果；A/B 文件与消息、保存 revision、GUI 轨迹相互吻合。
5. 文件同步失败、应用启动失败、模型停机与 GUI/协作行为失败分开记录。

离线 Gold/Oracle 检查数值类型、公式位置、源值保护、A/B 总额一致性及推荐；协作交接和共享状态因果必须另由消息、revision、GUI 操作和截图证明，不能由一个非空 Evidence 或填写的 hash 字符串代替。

## 条件一致性

- **MA-ID：** A、B 各有独立 Guest 与 LibreOffice 用户配置；公开任务文件、角色 Prompt 和桥接信息相同，B 保存的完整 ODS 必须实际传到 A。
- **MA-SD：** 两个独立模型 Agent 使用同一个真实 Guest、桌面、窗口和 GUI 焦点，不增加输入锁。B 的正常 Calc 地区设置可能影响 A 的另一份已打开工作簿。
- **MA-SD+PerActionLock：** 与 Shared 相同，只使用现有逐 GUI 动作锁；它不会恢复 A 的本地 locale 状态。

保留正常界面提示；若 Agent 识别变化并正确恢复，仍然计为任务成功。共享桌面失败必须有明确截图、动作和已保存单元格证据，不能仅凭终态失败推断发生了 locale 干扰。

## 预计 GUI 工作量

设计目标约 A 12–18 步、B 12–18 步。B 的设置路径属于候选核心状态操作，不是从任务中移除的纯无关步骤。该步数是设计估计，不是模型预算硬上限；模型预算和模型 Agent 可解性尚未验证。
