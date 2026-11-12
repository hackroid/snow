# method（planner-v01）— 共享 spec、组合规则与呈现

住宿方法以 `../../travel-v02/methods/` 为准、条件方法以 `../../conditions-v01/methods/` 为准，本文件只定两者的**接缝**：spec 形状、校验、拼接与输出。不复制两边方法正文。

## 1. 共享 spec（每批一份，JSON）

```json
{
  "kind": "test | actual",
  "resort_id": "kagura",
  "resort_name": "神乐",
  "first_ski_date": "2026-12-26",
  "nights": 1,
  "ski_days": 2,
  "adults": 3,
  "rooms": 1,
  "tickets_each_day": true,
  "ticket_holders_note": null,
  "currency": "JPY"
}
```

- `kind` 必填：test 的样例永远标测试；actual 只代表**规划草稿**，不代表已确认行程、更不授予任何预订权限。输出的 kind 标识只从 spec.kind 生成，任何一段自带 kind 与 spec 冲突即拒绝（见 §3）。
- 出发日 = 首滑日（沿用 travel 口径）；ski_days 通常 = nights+1，按当轮输入。
- 分房（rooms）与人数同为价格变量：未知且影响价格时先补问再查，不默认沿用上一批。
- 持季票/雪マジ等按人说明写 `ticket_holders_note`，那部分人不计票需求（沿用 travel 默认规则）。

## 2. 组合输入（每批一份 planner batch JSON）

三段：`spec`（如上）、`lodging`、`conditions`。后两段各带 `spec_echo`（first_ski_date/nights/adults/rooms 的回显）、自身的 resort_id 与币种、来源指针（source_batch / source_card 的相对路径＋读取时间）。**spec_echo 必须由来源批次自身记录的规格标准化生成，不许照抄本轮请求**——请求与旧批不一致时照抄会掩盖跨批拼接；来源批次没记录某项 → 该项 hold，不拼接。lodging 段带 `coverage`（实际查了几个平台、深核几个产品，明示覆盖），candidates 沿用 travel 的字段口径（已知小计、基础价＋票加购、餐食、装备、停车/步行、限制/取消、链接），并带 resort_id 与票覆盖四要素（ticket_days_covered、ticket_covers_people、ticket_scope_resort_ids、ticket_start_date），每项都要能指回来源原件，指不出就留空并按 §3 判不完整。conditions 段沿用 conditions 的卡口径（计划层带年份/雪季、实际开放、积雪分列官网与 AMeDAS、livecam 入口与帧时间）；其 forecast 只认**结构化来源字段**（issued 发布时间、coverage_end 适用末日、可选 applies_from 与 summary），期限必须来自原始记录（如 JMA 批次），不许从叙述文字里推造。

## 3. 规格检查（拼接前强制，tools/combine.py 实现，v2）

先验**共享 spec 本身**：kind 必须是 test/actual；first_ski_date 必须是真实存在的日期；resort_id 非空；nights/adults/rooms/ski_days 必须是明确的正整数（bool 不是人数）；tickets_each_day 必须是明确布尔；币种本阶段仅 JPY。**ticket_exempt_people 只要出现就始终校验**（非 bool 整数、0..adults），与 note 是否存在无关：正数必须有 ticket_holders_note 写明依据（如持季票/Yukimaji 资格），无依据的正免票一律拒绝——反例：3 成人/免票 3/无 note 不得绕过票需求；**混合免票（0 < 免票 < 全部）本版未实现逐人计价 → 直接 hold 转按人报价**，不假装支持、更不许从原套餐价里擅自减票钱。全员免票且有依据时才免除票覆盖检查。缺/空/非法一律拒绝，不设默认放行。

再验**拼接一致性**，任一不符 → 整批拒绝并报明哪项：
- echo 完整性：两段 spec_echo 四键必须齐全且有真实值——缺键是"来源未核，hold"，不许两个 None 互相匹配放行。
- 日期/人数/房数/晚数：spec_echo 与 spec 不一致 → 拒绝（防跨日期、跨人数拼接）。
- 身份/币种：两段各自的 resort_id、currency 必须显式给出且与 spec 一致（不从 spec 借默认）。
- 候选异场：任一 candidate 的 resort_id ≠ spec → 拒绝（不只核 conditions）。
- kind 一致：任一段自带 kind 与 spec.kind 冲突 → 拒绝；test 永不改标 actual。

候选级（不拒绝整批，标"不完整"并写明原因）：
- **票覆盖四要素**（tickets_each_day 时）：天数 ≥ ski_days；覆盖人数 ≥ 需票人数（adults − ticket_exempt_people）；适用范围含目标雪场（按可核映射：Mt.Naeba 共通含神乐，苗場限定不含神乐，不猜新映射）；起始日 = 首滑日。任一未验证/不足 → 不完整，缺票需求不默认为 0 或已覆盖。
- 费用未知：金额为 null → 输出 unknown，**禁止填 0**、禁止拿旧批次同名产品补位；费用/维护费/押金口径沿用 travel（单列、不入小计）不变。

预报（不信自称 status，**由结构化期限对 spec 实际滑雪日计算**）：
- 结构化三件套缺一不可：issued（发布时间）、applies_from、coverage_end。缺任一 → 输出"待核（来源未给结构化发布时间/完整适用起止）"，不渲染 summary。理由与超窗分开。
- issued 必须可解析且带时区，并按**本批真实读取时刻**（conditions 段 read_at，须为带时区的完整时刻）判新鲜度：issued 在读取时刻之后（未来/时间异常）→ 待核；issued 距读取超 24 小时 → 待核（JMA 一日三发 05/11/17 时，超 24h 必是过期缓存，沿用 conditions 新鲜度思路）；read_at 本身缺失/不可解析 → 待核，不猜。
- 起止倒置或不可解析 → 待核。滑雪日不在 [applies_from, coverage_end] 内 → "超预报范围，待临近复核"，即使输入自称 in_window 且带 summary 也**不输出任何预测值**。反例锚点：目标 2026-12-26、适用 2026-11-11 至 11-17、summary=晴/-5 → 只能出超窗行。
- 全部通过且 summary 存在 → 才渲染，并同时带出来源发布时间与完整适用起止。窗口内的真实拼接至今未验（无真实窗口内样例，不为它捏造来源）。
- **24 小时口径的定位**：它只是组合器拒绝"明显旧缓存"的上限，**不证明已取到最新一轮**；实际取数是否新鲜，仍按 conditions 的发布节奏（JMA 一日三发）与新鲜度门在取数当轮判断，组合器不替代。

## 6. v02 迭代（2026-11-11 本批起，产物区 ../planner-v02/）

- **报价归一（tools/normalize.py）**：各来源的原始报价先归一成 §2 候选形状再进组合：必填 platform、property_group、产品链接（url）、本条报价的读取时刻（quote_read_at）；计价基准分 per_person（套餐人均价）与 room（OTA 整间价）两种，归一时验算——per_person：人均小计 = 基础人均 + 票加购人均，整组 = 人均小计 × adults；room：整组 = 间价 + 票加购人均 × adults，人均仅作显示（半上舍入，存整组精确值）。算术对不上 → 拒绝该条，不静默修正。
- **OTA 同口径**：OTA 报价默认不含票/餐，归一时把 spec 所需票按已核渠道价计入已知小计（如神乐官方 2 日券），餐食缺失记 unknown 单列，不折 0；套餐与 OTA 在同一张表里以同一"已知小计"口径比较，小计构成逐条可追溯。
- **跨平台分组**：同住宿跨平台按 travel 的身份规则归 property_group（名称＋地址＋至少一项硬特征）；同组内每个报价各自保留（房型/餐食/票/取消不同不合并、不吞条件）；おまかせ不归任何具体酒店（自成一组）。
- **排序**：完整且小计已知的候选按整组已知小计升序；小计未知或不完整的排在后面并标原因，**不以未知充 0、不给虚假"最低价"**。
- **链接提取**：产品链接只从详情/日历页实际所在 URL 提取并随报价保存；列表页链接与搜索入口分开记录；链接里带会话参数的，原样保存但在呈现时同时给可复制文本。
- **呈现给用户时收起工程字段**：spec_echo、校验细节等只留在批次 JSON 与检查记录里；报告正文只给摘要、候选卡（价格/票/餐/装备/距离停车/取消/链接/读取时刻）、条件卡、缺口与复核点。
- **位置≠目标≠票范围（2026-11-11 验收修正）**：三件事分开——滑雪目标（spec 的雪场）、住宿区域（物件实际在哪）、票的适用（按目标＋所选路线验证）。没有"酒店必须属于目标雪场"的规则：异区住宿可作自驾备选（车程/停车未知就记 unknown，不因此排除、也不假定）。票按路线选：自驾直达目标雪场 → 用目标雪场的已核票（如神乐官方 2 日券）计价，与住宿在苗場侧还是中里无关；只有明确选跨场路线（如ドラゴンドラ联通苗場⇄神乐）才需要核共通票，未核就把那条路线标未核，不拖累自驾路线的小计。归一字段里以 ticket_route 记录所选路线，ticket_scope_resort_ids 仍只写票本身的适用范围。
- **类型与金额门（2026-11-11 验收收紧，normalize.py 已实现）**：含票标志 ticket_included_in_base 必须是显式 bool——字符串 "false"/"true" 等非 bool 值直接拒绝该报价，禁止真值强转（强转会把"不含票"读成含票、抹掉所需票价）；一切进入加法的金额（基础价、间价、票加购、自称小计）必须是有限、非负的数值且非 bool（负数、NaN/inf、bool、字符串一律拒绝）。字段缺失与类型非法同等处理：拒绝并记录原因，不静默修正。
- **票筛选接线（2026-11-11 18:3x 首接、18:4x 收紧，combine.py 的 prepare/apply_ticket_screening 已实现）**：公开入口（CLI main / prepare）每次对输入深拷贝，不改调用方原 dict；输入自带的 _screening_applied 标记与旧 ticket_screening 记录一律丢弃，筛选按当轮 spec/purchase_context 必重跑（同对象换日期/购买时刻/会员会重筛）。筛选前按候选的 ticket_source 从基底重算票状态（来源与计价单位分离：included 任何计价都保留自有票、package_addon 保留套餐加购、external 才剥离重筛，带票字段而来源不明拒绝不猜；基底缺失/未过金额门拒绝当新报价），套餐来源记录的含票/加购才是自有路径，上轮选中的 ticket_selected_offer 不作证据；全员有据免票时 DIY 按间价基底计（整组＝间价）、套餐含票不擅自扣减，混合免票沿用原 hold。kind=actual 缺 ticket_offers 或 purchase_context → 拒绝；显式空 offers＝无可用加购，DIY 不保留未核票价。kind=test 无 offers 只作历史展示并明标"本轮未核"。筛选本体规则不变：全覆盖→alternative_only 不抵扣；部分覆盖保留缺口不填充；无自有票才选已准入且覆盖全程的最便宜票（金额/天数/repeatable 过 planner 类型门：有限非负非 bool、非 bool 正整数、仅显式 True），held 永不进小计。传递契约写在 methods/task-entry.md 的"票筛选输入契约"节。

## 4. 呈现

- Markdown 为主：标题即带 kind 标识（test 为"测试样例，非实际行程"），摘要卡在前（spec、覆盖、首选候选小计、条件一句话、缺项与复核时点），明细在后；窄屏可读优先，完整宽表（如需）放可展开的后段。
- HTML 可选：**真 HTML 语义卡片**（header/section/details），首屏有醒目 kind 横幅，产品链接同时给可点击链接与可复制原始 URL，窄屏单列不靠整块 pre；不部署、不外发。
- 每个候选保留原搜索链接与产品链接（可复制 URL 同 travel 纪律）；条件卡保留原始入口 URL。
- 输出末尾固定三项：实际覆盖声明、缺项清单、建议复核时点（按 conditions 的复核点口径）。
