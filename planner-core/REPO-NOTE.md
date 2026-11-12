# planner-core — 仓库说明（候选版 v0.1，对应 batchT r3 + batchU 文案清理）

本目录是滑雪规划项目的**最小计算核心与方法**的版本化备份候选：
统一组合入口（校验/小计/票筛选/日期判定/渲染）＋四个子项目的短入口
与方法。它**只**备份核心与方法：不含活业务库（真实批次数据）、
用户记忆与偏好原件、凭据/会话、真实行程与预订信息。VM 原数据根
不迁移，本目录是白名单逐文件导出的副本。

## 恢复（离线，Python 3 标准库）

在含 planner-core/ 的目录执行：

    cd planner-core
    python3 planner-v01/tools/combine.py fixtures/batch-good.json --md out.md --html out.html --json out.json
    python3 planner-v01/tools/combine.py fixtures/batch-bad-echo.json --md bad.md   # 预期 REFUSED exit 2

fixture 为合成数据（匿名产品、example.invalid），不是真实报价；
预期结果见 fixtures/expected.md。浏览取价与资格判断来自运行方的
AI 平台，离线只对已采集的结构化输入做计算，见 README.md。
