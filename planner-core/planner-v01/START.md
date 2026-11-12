# planner-v01 START — 统一规划入口（住宿＋天气组合）

给"周末＋雪场＋人数"，出一个组合结果。本项目只做**归一化、规格校验、组合呈现**，不自创检索方法：
- 住宿/套餐：按 `../travel-v02/` 现行入口执行（先读其 START 与 methods）。
- 天气/开放/影像：按 `../conditions-v01/` 现行入口执行（先读其 START 与 methods）。
- 方法与工具是骨架；spec、结果、库存、观测是每批变量，存 `data/batches/`。

## 入口流程（细则以 methods/method.md 为准）

1. 先判定本轮是**测试**还是**实际规划**，写进 spec，不混淆；测试结论不冒充实际行程决定。
2. 归一化 spec：日期、首滑日、泊数、雪场、成人数与分房、每日票需求。装备只作结果权益、永不作筛选。年假/请假不猜；分房等影响价格而未知时，简短补问，不把本轮假设写成永久偏好。
3. 住宿按 travel 方法查：两 tour 平台优先、OTA 备选；条件按 conditions 方法取同雪场同日期的开放/天气/雪量/livecam。
4. 组合前过规格检查（tools/combine.py）：日期/人数/房数/晚数/币种/票范围任一不匹配 → **拒绝拼接**；缺项写 unknown，不以旧批次报价补位；来源时间与范围带进输出；历史观测不冒充现在；只有进入预报窗才有预测值。
5. 输出：已知小计＋票/餐/装备/距离停车/资格取消＋原搜索与产品链接＋条件卡＋缺项与建议复核时点；明示实际覆盖（如"深核 1 个产品"），不以单产品声称全面。

## 当前批次（发现指针）

- 2026-11-11 本批（A 12/26 主样例 / B 12/25 小样例 / C 11/14–15 窗口内天气，全部测试）：产物在 `../planner-v02/data/batches/`，该目录只是本批产物区，方法/工具仍在本项目内迭代（见 methods/method.md 的 v02 迭代节）。旧样例 r1–r3 保留在本项目 data/batches/ 不动。
- 关联模块（点读）：机会日历＋优惠雪票在 `../opportunities-v01/START.md`——窗口是候选、不是行程，须用户选定才可作 spec 日期；票条目按其资格/范围/日期字段交接，进入本项目报价仍过归一/校验。

## 边界
只读与本地组合；不预订/付款/联系；不查私有日历；不建通知/定时；不调用 XHS；不动旧控制/库/凭据/GitHub（不读 PAT、不发布）；control 路由只出提案（proposals/），不直接改四控制/Goal/记忆，不恢复 P3，规划入口不授予旧 XHS 或调度权限。

## 恢复与分工（短）

- 不变量（骨架）：methods/ 与 tools/ 的方法、代码、雪场代码映射（如 orion-params 的 GelandeCd）——跨批不变，改动走修订与回归。
- 当轮变量：spec、报价、规则观测（结构化规则连来源/源时刻存批次目录）、purchase_context；派生结果分两段——含票小计由 normalize 先算并随归一产物携带，combine 当轮重算外购剥离后小计、票筛选与 date_facts；输入自带的派生标记一律不信、丢弃重算。
- 分工：日期/雪场/人数由用户给；AI 负责浏览取价、证据摘要、票条件与资格的判断（held/准入按 opportunities 两层门）；代码分两步——源报价先经 tools/normalize.py 归一（输入 spec JSON＋原始报价 JSON，输出 candidates/refused；included 与 package_addon 的已归一小计由归一产物携带），combine 只承接已归一数据、不回算这两类小计，它当轮重算的是 external 剥离后小计、票筛选重演、日期判定与预报行（日期判定经 tools/date_rules.py，combine 在渲染前自动计算并写入「日期判定」段；fee_check.py 是同一计算的独立复现路径）。可照做例：python3 tools/normalize.py spec.json quotes.json > normalized.json，再把其 candidates 与 spec/conditions/ticket_offers/purchase_context/date_rules 组装为批次 JSON 过 combine.py。
- 未知边界：无结构化规则 = 无日期判定段，不猜免费/截止；票截止判定 ≠ 票可购/可用；未知金额永不作 0 或最便宜。
- 状态与历史分开：status.md 记当前状态，history.md 只追加既成事实；批次原件保留、修订用新版号文件。（导出包不含 status/history 文件，此为来源项目的工作方式说明。）
- 最小核心导出（GitHub 候选骨架）：exports/planner-core/（白名单：运行代码＋必要方法＋合成 fixture），隔离恢复演练见 planner-v02 批次区 batchT 记录；导出不含真实批次数据/偏好/凭据。
