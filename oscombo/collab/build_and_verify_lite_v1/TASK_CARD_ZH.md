# Build-and-Verify Lite v1

一页静态 OrderDesk 页面有一个筛选项拼写错误。A 在真实 GUI 文本编辑器中修复 Delivered 选项并保存、发布 HTML 版本；B 可以提前检查浏览器里的原始页面，但必须收到 A 的已保存版本和消息后，在地址栏打开 A 的输出 HTML 路径，用浏览器做 North + Delivered 组合筛选，再在 GUI 文本编辑器里保存 QA 记录。

交付：A 的 `orderdesk.html`，B 的 `qa_note.txt`。两种拓扑使用相同页面、角色指令、消息工具与评分。Shared 是无输入锁的同一桌面；Isolated 是两个 Guest，已保存 HTML 由版本桥同步。评分侧检查源文件只修复目标缺陷、QA 记录的查询/状态/可见订单/源文件；实际浏览器操作、保存版本和消息时序必须另外从轨迹确认，不能凭 QA 文本单独认定真实协作。

Gold 和 Oracle 不安装进 Actor Guest。原版 Build-and-Verify 文件及记录保持独立。
