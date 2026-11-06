# Spreadsheet Handoff Lite v1.3.1：预测交接到整箱补货

本目录是独立版本 **CDD-SH-LITE-003 / 1.3.1**。与 v1.3.0 相比，仅修复 scripted control 的 GUI 文件打开焦点和可见证据流程；任务卡角色目标、Fixture、Gold、Oracle 和模型 Prompt 保持语义一致。不得覆盖 v1.1、v1.2 或 v1.3.0 的记录。

## 用户需求

采购团队需要为 SKU-LAMP 做两个月补货。根据 Calc 中可见的三个月销量、库存、在途和安全库存计算非负净需求。采购决定以整箱下单：每箱数量、单件价格和预算在另一份 Calc 工作簿中。交付需要让采购表说明需求来自规划 Agent 保存的最新预测，并显示所需整箱数、总件数和总成本。

公开输入包含：

- Jun / Jul / Aug 销量：40 / 50 / 60 件；
- On-hand：39 件；Inbound：18 件；Safety stock：30 件；
- 每箱 10 件；单件 USD 28；预算 USD 2300。

Task Card 和 Actor Prompt 不含任何计算结果。

## A/B 分工与真实依赖

- **A：需求规划。** 在由 forecast_input.ods 初始化、已经打开的 forecast.ods 的 Forecast!H3 输入 Calc 公式，使用可见的销售、库存、在途和安全库存源单元格；提交并保存自己的预测，再发布 saved revision。A 只发送“forecast 已保存”的消息，不发送数值。
- **B：采购规划。** 可先检查由 order_template.ods 初始化、已打开的 order_plan.ods 中的包装、单价与预算。收到交接后，B 必须通过 Calc GUI 打开 A 的精确、只读 saved revision，目视读取 H3，再回到已经打开的 order_plan.ods。B 在 E3 录入以**单件**计的 forecast need，在 F3 录入需要的**整箱数**。工作表初始的零值只是尚未录入的占位值；输入后，公开公式算出 G3 订货件数和 H3 总成本。B 检查预算、保存并发布采购表。

B 依赖 A 的已保存 revision 才能完成采购表；ready 消息自身不携带答案。只有消息、revision 字符串或文件 hash 都不足以证明真实交接。行为审计必须结合 A 发布事件、revision/hash/权限、B 读取该 revision 的工具结果、peer-view 的 GUI 截图与时间顺序、B 后续编辑/保存和最终文件。

两种拓扑使用同一角色说明、任务输入与评分。Shared 两个 Agent 在一个真实桌面上自然地共享 Calc 的窗口焦点与键鼠；Isolated 使用各自独立的真实桌面，经等价 saved-revision/message 机制传递文件。任务不要求两人同时点击，也不规定结果方向。

## 工作簿结构与交付物

- outputs/agent_A/forecast.ods：保留 Forecast 的可见源数据，在 H3 保存需求公式和结果。
- outputs/agent_B/order_plan.ods：保留 E3 的需求件数、F3 的整箱数，以及 G3 和 H3 的预设计算公式及结果。

F3 的列名为 **WHOLE CARTONS TO ORDER**，G3 明确为 **TOTAL INDIVIDUAL UNITS**。该呈现把整箱数和单件数放在不同字段，避免单位歧义。订单总件数与成本公式在 Fixture 中预先提供，减少普通公式编辑；B 仍要从 A 的 saved revision 读取需求并作整箱决策。

## 评分

私有 Oracle 从原始 Fixture 独立计算需求、整箱订货量、总件数和总成本。它核对：

- A 的 H3 缓存值正确，且 H3 公式确实依赖 B3:G3 的全部对应源输入；源数据没有被改写。
- B 的 E3 与已保存 A 的需求一致；F3 是覆盖需求的最小整箱数；G3/H3 保留正确的通用公式，缓存结果正确且总成本不超预算。
- B 本地计算是否正确以及联合任务是否正确分开报告。若 A 的预测错，B 仍可能相对其实际看到的 A 值算对本地决策，但联合 Oracle 失败。

Gold 和 Oracle 不得进入 Actor 的 Guest、指令或消息。

## GUI 步数设计目标

按照正常快捷键操作，约 **12 次有状态 GUI 输入**：

- A：输入公式、提交公式、保存，共约 3 次；
- B：通过 GUI 打开 peer revision（Ctrl+O、Ctrl+L 聚焦路径栏、输入路径、Enter），切回订单工作簿（Alt+Tab），输入需求并 Tab 到整箱字段、输入整箱数并提交、保存，共约 10 次。

另有截图、模型推理和消息/附件工具调用，不计为键鼠输入；这些不是执行硬上限。B 打开 peer revision 与回到采购工作簿是完成信息依赖所需的操作，不当作可删除的杂项。

## 离线验证与边界

tests/test_spreadsheet_handoff_lite_v1_3.py 覆盖空白公开答案、确定性 Fixture、独立 Gold 正控、错误整箱/件数负控、错误预测公式、漏掉来源、改动源数据、公式完整性、损坏 ODS 和 Host I/O 异常。上述测试不验证 GUI 操作、桌面竞争、真实消息/桥同步或 saved revision 的 GUI 目视读取。

v1.3.1 现有版本专用的 scripted Guest Adapter，复用共享 pilot 的 Guest 生命周期助手与 saved-artifact bridge。v1.3.0 的正控虽然 Oracle 和文件生命周期通过，但 B 的 peer-view 截图仍显示文件选择框，因此不视为有效交接控件。v1.3.1 增加路径栏焦点、等待 Calc 活跃只读窗口和真实尺寸截图；离线测试仍不能代替真实 Guest、目视内容、桌面竞争、消息/桥同步、重开与 reset。模型入口已有离线覆盖，正式启动仍以双拓扑正负控、peer-view 截图人工核验和 reset 为门槛。见同目录 `ADAPTER.md`。
