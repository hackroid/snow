# sources（conditions-v01）— 官方来源表与区域映射

只列官方来源。聚合站（SURF&SNOW、tenki.jp、JAPANSNOWLINE 等）只用于发现入口，其数值永不进入观测。
入口存在性分三档：**已确认**＝实见该官方页面本身；**已查范围未发现（仍待核）**＝在所查导航/页面内未定位到入口——只说明本次范围未见，不等于站点不提供，留下批复核；**站点不提供**＝仅当官网明示不提供时才可使用（目前十场无一例达到此档）。每行保留实际核查页、核查时间、确认范围与未知项。

## 1. JMA 官方（全场共用，按区域取）

| 用途 | 官方入口 |
|---|---|
| 预报 JSON（县级） | `https://www.jma.go.jp/bosai/forecast/data/forecast/<县code>.json`（新潟 150000／长野 200000）；含 reportDatetime、短期预报（区域别）、一周预报 |
| 警报 JSON（县级） | `https://www.jma.go.jp/bosai/warning/data/warning/<县code>.json`（市町村 code 别）；**注意过时副本风险**（method §2.4） |
| AMeDAS 最新时刻 | `https://www.jma.go.jp/bosai/amedas/data/latest_time.txt` |
| AMeDAS 全点数据 | `https://www.jma.go.jp/bosai/amedas/data/map/<YYYYMMDDHHMMSS>.json`（与 latest_time 对齐取） |
| AMeDAS 入口页 | `https://www.jma.go.jp/bosai/amedas/` |

JMA 预报区域 code：新潟县＝下越 150010／中越 150020／上越 150030／佐渡 150040；长野县＝北部 200010／中部 200020／南部 200030。

## 2. 十场官方入口与映射

| 雪场 | 所在市町村 | JMA 区域 | 官网（官方） | 状态/缆车页 | Livecam |
|---|---|---|---|---|---|
| 神乐（かぐら） | 新潟・湯沢町 | 中越 150020（预报地点 湯沢 54841；AMeDAS 湯沢 54841） | https://www.princehotels.co.jp/ski/kagura/winter/ | 已确认：/winter/coursemap/ （ゲレンデ・コース，含课程/缆车/park 状态与積雪情報模块；首页同模块带更新戳） | 已确认：https://www.princehotels.co.jp/ski/kagura/livecamera/（6 机位＝神乐 3＋苗場 3，静止画＋延时回放式、自带时间戳；新鲜度逐帧不一） |
| 妙高杉之原 | 新潟・妙高市 | 上越 150030 | https://www.princehotels.co.jp/ski/myoko/ | 已确认：冬トップ「本日のゲレンデ情報」＋コース页リフト運行状況（coursemap?tab=lift） | 已确认：https://www.princehotels.co.jp/ski/myoko/livecamera/（杉ノ原ゴンドラ山頂付近／三田原第2高速リフト山頂付近 2 机位） |
| 戸狩温泉 | 长野・飯山市 | 北部 200010 | https://togari.jp/winter/ | 已确认：トップ「TODAY'S TOGARI」に天気/積雪（ベース・山頂）/リフト運行状況；/winter/gelande/ にフィールド别运行状况 | 已确认：https://togari.jp/winter/livecam/（2 机位＝アースドラゴン／スカイドラゴン，静止画查看器、自带数据条；2026-11-11 实查 1 号机帧停 11/04、2 号机无图） |
| 野沢温泉 | 长野・野沢温泉村 | 北部 200010 | https://nozawaski.com/ | 已确认：https://nozawaski.com/winter/course/ （ゲレンデ/リフト・ゴンドラ状況，带更新日時） | 已确认：冬トップに LIVE CAMERA（やまびこD／上ノ平／長坂，静止画带更新戳） |
| 舞子 | 新潟・南魚沼市 | 中越 150020 | https://www.maiko-resort.com/ （冬 https://www.maiko-resort.com/winter/ ） | 已确认：トップ「Today's」に気温/積雪（山頂）/雪質/風速＋リフト運行予定一覧；运行状况另可由ゲレンデマップ看 | 已确认：トップ「Today's」に気温/積雪（山頂）/雪質/風速＋リフト運行予定一覧；运行状况另可由ゲレンデマップ看 | **确认存在（2026-11-11 23:51 订正）**：入口不在主菜单/footer，在 WINTER トップ的「Today's maiko」overlay 内「ライブ カメラ」链接 → SKIDAY embed（https://skiday.app/46R2YtTNP53wSN7IOLg5/869223046913016/embed），机位 1：舞子/奥添地エリア，帧自带时刻（实读 2026-11-11 23:35、-4°C、夜间画面）。原记「已查范围未发现/仍待核」及其冲突说明（搜索索引片段命中ライブ カメラ、页面未定位）为旧查范围记录——当时未查 overlay 层，本次定位即在此层；订正依据 batchR 证据 C |
| X-JAM 高井富士 | 长野・山ノ内町 | 北部 200010 | https://x-jam.jp/ | 已确认：トップに LIFT 逐条状态（運行〇／一時休止△／運休✕，含よませ侧） | **已查范围未发现/仍待核**：2026-11-11 04:29–04:31 实查导航（TOP／リフト料金／大会・イベント／コース／施設／アクセス＋页脚ゲレンデマップ・ゲレンデ情報）与页面内検索「カメラ」均无入口；机位/形式仍未知。官网未明示不提供，不归"站点不提供" |
| 竜王 | 长野・山ノ内町 | 北部 200010 | https://www.ryuoo.com （/snow/ 跳转冬トップ /winter/） | 已确认：冬トップ「TODAY'S RYUOO」（标日付、気温/降雪季前空白、Lift Information）＋详情 https://ryuoo.com/winter/gelande/#lnk_status_course （只今のリフト運行・コース状況；未见显式更新时刻字段） | 入口已确认：冬トップ内嵌 YouTube 播放器（无独立页）；**机位仍未知**（页面未标机位名，不能确认是 SORA terrace）；2026-11-11 实查不可播、无画面。（旧记"山頂静止画"系第三方说法，已被实查推翻删除） |
| 八方尾根 | 长野・白馬村 | 北部 200010 | https://www.happo-one.jp/ | 未逐页核（状态页留下批） | 已确认（2026-11-11 逐页实查）：https://www.happo-one.jp/trekking/livecamera/ ，5 机位＝アルペンクワッド（1,678m）／うさぎ平（1,391m）／ゴンドラ乗り場（770m）／第3駐車場（737m）／八方池（2,060m）；前 4 个为 YouTube 直播（画面内嵌时间戳），八方池无图。注：直播的**流标题**可含旧日期（如 2026-03-09），判读以画面内时钟为准 |
| 岩原 | 新潟・湯沢町 | 中越 150020（AMeDAS 湯沢 54841 可作平地参考） | https://www.iwa-ppara.com/ | 已确认存在但内容为季末残留：首页「本日の天気／積雪／気温」表（季前无值）＋「詳しい営業情報」链接页仍是上季"…3月29日をもちまして営業を終了しました"公告、表空白无更新戳；26–27 状态须待官网换季更新 | **已查范围未发现/仍待核**：2026-11-11 04:29–04:31 实查导航（ゲレンデ・施設／チケット料金／レンタル／レッスン／FAQ／アクセス）＋首页検索「カメラ」均无入口，机位/形式仍未知。聚合站称无官方ゲレンデ摄像头仅作旁证，不足以定"站点不提供"（须官网明示）；周边国道道路摄像头非雪场来源，不采用 |
| 斑尾高原 | 长野・飯山市 | 北部 200010 | https://www.madarao.jp/ski | 已确认：https://www.madarao.jp/ski/conditions 「本日のゲレンデコンディション」（積雪／24H降雪／リフト運行予定／滑走可能コース，含 Live Camera 区） | 已确认：conditions 页内 Live Camera（インフォメーションセンターから） |

## 3. 使用注意

- Prince 系（神乐/杉之原）页面结构相近，但每场的状态字段与开业日期必须逐场读，禁止跨场套用。
- 野沢温泉状态页在本批检索快照里出现「更新日時：05/06」的旧季末状态——这正是 method §3 的过时判定样本：入口可用，内容须按更新戳判读，季前不得摘其状态。
- 道路摄像头（国道等）由道路管理者运营，只说明路面，不代表ゲレンデ状态，本项目不采用。
