# planner-core（最小核心导出 · GitHub 候选骨架）

从 planner-v01 稳定根白名单导出的可离线运行最小核心：统一组合入口
（校验/小计/票筛选/日期判定/渲染）。**不含**真实批次数据、用户偏好、
凭据、旧小时系统与数据库。fixture 为合成测试数据（匿名产品、
example.invalid 链接），**不是真实报价**。

## 布局（相对路径即依赖关系，勿改层级）

- planner-v01/tools/：combine.py（普通入口）、normalize.py、date_rules.py、fee_check.py
- planner-v01/methods/：task-entry.md（契约与自检）
- travel-v02/tools/：report.py、totals.py（combine 的显示取整/排序依赖）
- opportunities-v01/tools/：admission.py（票两层准入，combine 依赖）
- fixtures/：batch-good.json（合成正常批）、batch-bad-echo.json（echo 错配负例）、expected.md

combine.py 以自身文件位置相对发现 travel/opportunities 工具目录，
不依赖任何绝对路径或 VM 根。

## 运行（离线，Python 3 标准库即可）

在包根目录执行：

    python3 planner-v01/tools/combine.py fixtures/batch-good.json --md out.md --html out.html --json out.json
    python3 planner-v01/tools/combine.py fixtures/batch-bad-echo.json --md bad.md   # 预期 REFUSED、exit 2、无输出文件
    python3 planner-v01/tools/fee_check.py --spec <spec.json> --rules <rules.json> --purchase-at <ISO+tz>

预期结果见 fixtures/expected.md。冻结包诊断时用 python3 -B 且
PYTHONDONTWRITEBYTECODE=1，避免 __pycache__ 混入包内。

## 忽略规则（.gitignore 同步）

__pycache__/、*.pyc、out.md/out.html/out.json 等运行产物、真实批次
JSON（data/ 下）、凭据与会话文件永不入包。

## r2 自包含说明（2026-11-12）

- 方法与短入口已随包：planner-v01/START.md＋methods/、travel-v02/START.md
  ＋methods/（method/orion-params/ota-params）、conditions-v01/START.md＋
  methods/、opportunities-v01/START.md＋methods/method.md。task-entry 与
  START 的必读指针在本包内均有对应文件（指针核查见验收补充包日志）。
  未随包：opportunities 的 sources 台账与各模块 history/status（VM 内
  研究记录，非运行必需）。
- 能力边界：浏览取价、证据判断、票资格判断来自运行本包的 AI 平台
  （如 Muse 的浏览器）；本包离线只能对已采集的结构化输入做校验、
  计算与渲染，不能自行产生新报价或新观测。
- 导出副本中性化：积分口径在包内写作「本项目报价口径示例」，VM 原件的
  权威表述不变；fixture 全部合成（匿名产品/example.invalid/合成规则）。
- .gitignore 已补 data/批次/凭据/会话/库文件模式；但忽略规则只是防误入
  的一层，不等于秘密扫描，也不构成可公开发布的保证——发布前须另行审查。
