# task-entry（planner-v01）— 新会话/新实例的短任务入口与授予说明

## 给新实例的任务文本（照抄填空即可）

> 你负责一次滑雪周末规划组合。先读授予你的 planner-v01/START.md 与 planner-v01/methods/method.md，按其中流程执行。本轮 spec：kind=（test/actual）、雪场=（ ）、首滑日=（ ）、泊数=（ ）、成人数=（ ）、房数=（ ）、每日需票=（是/否）。住宿检索按 travel-v02 的方法文件执行，条件观测按 conditions-v01 的方法文件执行；组合前必须用 planner-v01/tools/combine.py 的校验（或按 method §3 人工逐项核对），任一不匹配就停下报告，不拼接。只读，不预订/付款/联系。结果存 planner-v01/data/batches/ 新批次，不改旧批次与两个子项目的方法文件。

## 授予清单（按执行者类型分开，不假定能力）

| 执行者 | 能给什么 | 不能假定 |
|---|---|---|
| 主聊天（Muse 本体） | 直接读 snow-runtime 全目录＋用浏览器工具与本地工具 | — |
| 浏览器任务（新实例） | 用 files 参数授予**单个文件**：planner START、planner method、travel 的 START/method/orion-params/ota-params、conditions 的 START/method/sources 中本轮需要的子集 | 它读不到 VM 路径、不能跑 combine.py；校验由主线在回收后做。它自带实时浏览器，只读执行检索/观测并回报证据 |
| 通用子任务（subagent） | 任务文本内嵌 spec 与规则要点；可做文本处理、JMA JSON 抓取（公开接口）类工作 | **没有实时浏览器**（网站交互会被退回浏览器路线）；也不能假定能读 VM 文件——需要的文件内容要么随任务授予、要么在任务文本里给出 |

## 组合回收检查（主线做）

1. 子实例回报的住宿/条件证据先落各自子项目的批次文件（travel-v02 / conditions-v01），planner 只引用不复制。
2. 组 planner batch JSON（spec＋两段 spec_echo＋来源指针），跑 combine.py；REFUSED 就按报错修正来源，不绕过校验。
3. 产物（MD/HTML）存 planner-v01/data/batches/，status 更新覆盖与缺项。

## 票筛选输入契约（2026-11-11 接线，combine.prepare 执行）

- 新报价的 batch JSON 顶层除 spec/lodging/conditions 外，必须带当轮输入的两个键：**ticket_offers**（结构化优惠票清单：价格、天数、repeatable、范围、有效期、黑名单、截止规则、会员体系、七项 checks 与来源）与 **purchase_context**（purchase_at 带时区购买时刻、memberships 按体系的会员事实）。spec、购买时刻、会员体系都属当轮输入，不是用户永久事实，不得从旧批次或样例里继承。
- 每个住宿候选必须带 **ticket_source**（included＝基础价含票 / package_addon＝套餐自带加购 / external＝外购或无票），按来源证据填写（normalize 校验与含票标志的一致性）；计价单位（room/per_person）不决定票来源。带票字段而来源不明的新报价一律拒绝、不猜；room 含票与 per_person 含票都保留自有票，per_person 外购与间价外购一样剥离重筛。
- **kind=actual 缺任一键 → 拒绝（REFUSED）**，不渲染。ticket_offers 显式为空列表是合法输入，含义是"本轮无可用加购"：DIY 间价候选的外购票会被剥离并判不完整，不保留未经本轮核验的票价。
- kind=test 且不带 ticket_offers 时只作**历史展示**：原样渲染原批次小计，标题下明标"票价与小计为原批次当轮来源，本轮未核，不作为当前报价"，不得当新报价引用。
- 入口每次对输入深拷贝后 prepare：输入自带的 _screening_applied 标记或旧 ticket_screening 记录一律丢弃、不信任；候选的票状态按 ticket_source 从未变的基底价重算——included/package_addon 是自有票路径（保留；上轮筛选选中的 ticket_selected_offer 不作证据、按 external 重筛），external 的旧加购一律剥离重筛，与计价单位（room/per_person）无关。调用方原 dict 不被改动；同对象改日期/购买时刻/会员后重新 prepare 会重筛。
- 金额/类型沿用 planner 既有门：价格须有限、非负、非 bool；天数须非 bool 正整数；repeatable 仅显式 True 才可按日重复计价。全员有据免票时 DIY 按间价基底计、套餐含票不扣减；混合免票沿用 spec 校验的 hold。
- 积分口径（本项目报价口径示例，权威文本在 travel-v02/methods/method.md §4.1）：报价的主价、总价、排序与主比较参考式一律用不抵扣任何积分的房价＋已核必付费用——常驻/等级积分也不例外；积分回馈、即时抵扣、既有积分支付只写备注，候选的 instant_* 字段经入口只渲染为"积分备注"行、不入小计。
- 路线观测（travel-v02/methods/method.md §8）：目的地点先经雪场官网 access/停车信息核对统一、全批同一点；路线以顶层 route_observations 按物件组提交（起终点标签/来源链接/km/地图时长原文/观察时刻/时间设置/提示或 unknown 原因），与报价分开存，不得用路线的新读取时刻刷新报价的 quote_read_at。

## 交付前自检（2026-11-12 batchR 验收沉淀）
- 小计措辞：只写「住宿＋票已知小计」，另付项（免责、停车等）同句明示不在小计内；票条件未核的参考式不得写成与完整报价的最终同权比较结论；散订最低只写「本批已核散订住宿价最低」，不写全场/全网最低。
- 询价/暂定制：リクエスト・暂定价等成立方式必须前置到候选标题或价格旁，不只埋长备注。
- checks 与结构值诚实：未核齐的检查置 false（如季终日未载时 valid_dates 不得 true）；未知结构值置 null（如 forecast 首末），不留事后会被代码当事实的假精确；页面粗记只留证据。
- 证据粒度（采集时存，不事后补搜）：必要最小原文在采集当轮保存——结构化原件（如 JMA 原 JSON/timeDefines）、关键原页摘录（所选票配置条款）、完整测试日志；只有摘要粒度时在交付中如实标注，不为补证重开搜索。
- 顶层文本清单契约（2026-11-12 batchR r4 落地）：missing / recheck / choice_directions 若提供必须是 list 且各项为非空 str；省略视为空，显式 null/str/dict/数字/非 str 成员由入口 validate 拒绝并报字段位置——生产侧写批次时同样按 list 逐句写，整段 str 会被拒（r3 实证：str 输入曾被逐字渲染）。
- 日期判定必用路径（2026-11-12 batchS 落地）：停车收费日、票贩售截止等日期判定禁止肉眼判读——结构化规则（清单/区间/星期默认/默认语义，带来源与源时刻）存批次规则文件（如 batchS-rules.json），组装经 tools/date_rules.py 判定、tools/fee_check.py 可按 spec+purchase_at 复现；截止永远比 purchase_at（按规则声明时区、按日粒度），不拿滑雪日比截止；规则不完整或形态未支持一律待核/unknown，不猜 0、不编时分。
