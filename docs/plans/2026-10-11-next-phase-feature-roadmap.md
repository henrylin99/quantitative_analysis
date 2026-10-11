# 下一阶段功能开发路线图（2026-10-11）

Date: 2026-10-11

## 一、背景与现状结论

本文档基于 2026-10-11 的全库盘点（8 项遗留缺口核查 + 数据资产消费扫描），结论如下：

- **主链路已闭环**：数据下载→因子计算（Alpha191 全套）→IC/分位回测研究链→ML 训练（防泄漏、训练快照、模型对比）→信号（筹码/行业轮动/regime）→每日预警与盘后调度→组合管理→AI 工作台。
- **旧缺口已清空**：2026-10-06 盘点的因子链 8 项缺口（标准化回填、分位回测、IC 前端化、预测跟踪、组合归因、去冗余、模型快照、训练进度）已全部被后续提交关闭，**勿重复建设**。
- **剩余开发空间**集中在四类：①已落地数据的深挖（分钟/财务/龙虎榜/指数）②功能断头路（报告导出、新闻推送、数据治理）③研究能力升级（多空回测、paper trading、寻优）④工程卫生（孤儿数据、因子验收）。
- 部分关键证据：`data/stock_minute/` 仅 8 只股票且 `sz.000001`/`000001.SZ` 双份混杂；`index_daily` 仅 6 只宽基；报告路由无导出端点、订阅外发缺省只记 log（`report_dispatch_service.py` channels=["log"]）；news 推送 payload 恒空（`websocket_push_service.py:336`）；`data/ml_factor_state/` 达 9.1GB 无清理机制；`backtest_engine._rebalance_portfolio` 为 long-only。

## 二、目标

1. 补齐三处功能断头路，让"框架已在、最后一公里"的能力真正可用。
2. 释放已落地数据的未开发价值：分钟、财务三表、龙虎榜/涨停、行业指数。
3. 升级研究能力：多空回测、模拟盘闭环、寻优扩展、AI 因子组合发现。
4. 工程卫生：孤儿数据处置、内置因子验收样例、因子状态存储治理。

## 三、非目标（永久排除）

- **实盘/券商交易对接**：不做券商 API、下单、easytrader/miniQMT/ptrade 等任何真实交易通道（2026-10-11 用户决策，**永久排除**，后续规划不再讨论）。注意：paper trading 模拟盘（纯虚拟记账、无券商接口）在范围内。
- 不重写存量页面与架构，不引入外部中间件（维持零 MySQL/Redis 依赖）。
- 不为事件因子承诺深历史回测（fuyao 历史深度有限，从"开始归档"做起）。

## 四、批次总览

| 批次 | 主题 | 内容 | 规模 | 依赖 | 状态 |
|---|---|---|---|---|---|
| 一 | 速赢与卫生 | 孤儿数据处置、内置因子验收样例 | S | 无 | ✅ 2026-10-11 |
| 二 | 断头路闭环 | 报告导出与真实外发、新闻/研报推送、ml_factor_state 治理 | M | 无 | ✅ 2026-10-11 |
| 三 | 分钟数据升级 | 代码规范统一、全市场 5min 覆盖、日内因子、分钟级回测 | L | 无 | ⬜ |
| 四 | 数据补全与因子扩展 | 指数数据补全、龙虎榜事件因子、财务 PIT 因子库 | M | 批次一部分 | ⬜ |
| 五 | 研究能力升级 | 回测多空化、paper trading、寻优扩展、AI 因子组合发现 | L | 部分依赖批次三/四 | ⬜ |

---

## 批次一：速赢与卫生

### 1.1 孤儿数据处置

- 现状：`data/index_basic.parquet` 全库零调用（唯一入口 `data_reader.get_index_basic` 无调用方）；`data/stock_ma_data.parquet` 仅被 Text2SQL/AI SQL 表目录引用，生成作业 `ma_calculator` 已标 `dangerous=True`。
- 改动：
  - `index_basic`：**保留并接入**（批次四指数补全会用到）——指数列表/信息展示接口补 `get_index_basic` 消费。
  - `stock_ma_data`：**下线**——移除 `ma_calculator` 作业注册与 parquet，MA 类指标已由 `realtime_indicator_engine` 按需计算，无存量价值；Text2SQL/AI SQL 表目录同步摘除。
- 验收：data_jobs 注册表中不存在"有写入无读取"的作业；`docs/宽表数据字典.md` 同步更新。

### 1.2 内置因子最小验收样例

- 现状：整改清单 4.2.1 仍开放——内置因子缺系统级验收，"数据不足时如何处理"无成文规则。
- 改动：`tests/` 新增因子抽样核对测试，覆盖 ≥5 个核心因子（动量、波动率、Alpha191 代表 2 个、筹码类 1 个），固定输入样例+期望输出；每因子文档化输入字段依赖、时间窗口、空值策略。
- 验收：pytest 全绿；因子空值/缺数据行为有明确断言（不静默返回假 0）。

---

## 批次二：断头路闭环

### 2.1 报告导出与真实外发

- 现状：`app/api/realtime_report.py` 17 个路由无任何 export/pdf/docx 端点，`RtReportsPage.tsx` 无导出按钮；`report_dispatch_service.py` channels 缺省 `["log"]` 只记日志（自述"不强依赖外部邮件或短信网关"）。
- 改动：
  - HTML→PDF 导出：`weasyprint`（加入 requirements 可选组；不可用时降级提示浏览器打印），新增 `GET .../reports/<id>/export.pdf`。
  - 真实投递：`report_dispatch_service` 复用 `alert_push_service` 已有的企业微信/钉钉/Server酱/Webhook 渠道，投递结果（成功/失败/渠道）落分发元数据。
  - 前端：报告详情页导出按钮；订阅页选择投递渠道。
- 验收：任一报告可下载 PDF；配置渠道后 dispatch 到达真实渠道并有投递记录；失败有日志与重试。

### 2.2 新闻/研报推送激活

- 现状：`websocket_push_service.py:336-338` news payload 恒返回空、通道默认 disabled——接好源即活的纯占位；东财研报下载解析管线已可用（`research_report_service.py`）。
- 改动：
  - 第一期只接**有现成源**的研报更新：基于东财研报列表增量（自选股/白名单股票的研报更新 → 推送摘要 + 链接）。
  - 推送节流与去重（按报告 ID）；通道保持默认关闭，配置开启。
  - 无源/未配置时保持现状（关闭、不报错），payload 不造假数据。
- 验收：开启后自选股研报更新可推送；关闭/无源时链路静默；去重生效。

### 2.3 ml_factor_state 数据治理

- 现状：`data/ml_factor_state/` 9.1GB（全库最大目录，约为日线的 20 倍），`parquet_state_store.py` 无 TTL/压缩/清理机制，长期运行持续膨胀。
- 改动：
  - 分区审计脚本：按 factor_id 统计分区数、最新日期、最近读取时间，输出孤儿/陈旧分区清单。
  - 清理策略：非采纳白名单因子超过 N 天未更新 → 归档（可选压缩）→ 删除；**必须先 dry-run 输出将删清单，人工确认后执行**。
  - 数据管理页新增存储看板：各 data 子目录体积 + ml_factor_state 明细 + 清理入口。
- 验收：清理后体积目标 <4GB；采纳白名单因子数据经覆盖率核验无损；清理有 dry-run 与操作日志。

---

### 批次一/二实施记录（2026-10-11 完成）

- **1.1**：`ma_calculator` 作业与 `stock_ma_data.parquet` 已下线（MA 数据源切 stk_factor 前复权字段，`data_reader.get_ma_data` 重写）；`index_basic` 经新端点 `GET /api/market/indices/search` 与 Text2SQL/AI SQL 表目录（`index_basic` 虚拟表）接入。
- **1.2**：`tests/services/test_builtin_factor_acceptance.py`——6 个核心因子可执行核对（合成输入断言文档化期望）+ 文档-实现一致性守卫 + 数据不足/除零 inf 行为断言。
- **2.1**：`app/services/report_export_service.py`（HTML 渲染/PDF 导出/推送摘要）；`GET /api/realtime-analysis/reports/reports/<id>/export?format=pdf|html`（weasyprint 缺失返回 501，前端自动降级 HTML）；`report_dispatch_service` 复用预警推送渠道真实外发，逐渠道结果落 `dispatch.delivery_results`；`AlertPushService.push_text` 通用文本推送。
- **2.2**：`websocket_push_service._get_news_payload` 激活——自选股当日东财研报 → news 推送，按 info_code 去重（落盘 `data/research_push/seen.json`），渠道默认关闭不变。
- **2.3**：`app/services/data_governance_service.py` + `GET /api/datasources/storage-overview|factor-values-audit` + `POST /api/datasources/factor-values-cleanup`（默认 dry-run，confirm=true 执行，retention_days≥90 硬约束，op log 落 `cleanup_log.json`）；数据管理页新增「存储治理」面板。实测：保留 300 天可回收 6.38GB（dry-run 未执行）；审计精确抓到退化因子 alpha_138（169 股）。
- 说明：factor_values 为单日全因子长表，按因子删行需重写全部历史分区，故清理原语按日期保留窗口设计。

---

## 批次三：分钟数据升级（最大杠杆）

### 3.1 分钟数据代码规范统一（前置）✅ 2026-10-11

- 现状：`data/stock_minute/` 仅 8 只不同代码、无 1min；`sz.000001`（通达信风格）与 `000001.SZ`（tushare 风格）是同一只股票存了两份，消费方按 ts_code 精确匹配会漏读一半数据。
- 改动：统一为 tushare 风格 ts_code；存量迁移脚本（合并双份、重命名分区）；`minute_parquet_store` 写入侧入口归一；读取层临时兼容旧风格并打 deprecation 日志。
- 验收：迁移后无双份代码；`realtime_indicator_engine` 等消费方读数与迁移前一致（抽样对账）。
- 实施：新增 `app/services/minute_code_style.py`（normalize_minute_code / minute_code_aliases 单一来源）；`MinuteParquetStore.write_frame` 对新帧与存量分区统一归一（同 bar 双风格自动去重 keep=last）；Baostock 同步与通达信 `normalize_tdx_minute_bars` 产出端同步归一；读侧别名兼容 + 非规范查询 debug 日志。迁移脚本 `scripts/migrate_minute_codes.py`（dry-run 默认 / `--execute` / 幂等）：真实数据 272 个分区 14286 行全部规范，二次执行零改动。全量测试 994 通过；实测指标计算链路 MA/RSI 正常出值并落库。

### 3.2 全市场 5min 覆盖 ✅ 2026-10-11（开发完成，回填已在后台执行）

- 改动：
  - `tongdaxin_minute_sync_service` 扩展全市场同步：分批、限频、断点续传、失败告警，接入盘后 18:30 调度链（在数据链路编排之后）。
  - **先做 6 个月滚动窗口**：量级估算 5600 只 × 48 bar/日 × ~120 交易日 ≈ 3200 万行，parquet 压缩后估 1-2GB；跑通后再评估是否长期保留。
- 验收：全市场 ≥5000 只 5min 数据持续更新；中断可续传；调度链失败不阻塞后续预警步骤。
- 实施：
  - **数据源定版（2026-10-11 实测 + 用户确认）**：分钟级 K 线唯一可用源是 **pytdx**（服务器 IP 常换，硬编码 4 主机已半死，可用主机集中在 pytdx 内置池后半段国泰君安块 117.34.114.x，周末实测可用）；baostock/akshare/tickflow/tushare 分钟线均不可用（详见记忆 minute-kline-source-pytdx-only）。
  - `app/services/minute_tdx_fetcher.py`：动态主机探测（真实 bars 金丝雀验证，非仅 TCP 握手）+ 可用主机缓存/轮换/全池重扫 + 分页回填（单页 800 根，6 个月 ≈ 8 页，实测 600000.SH 回填 5808 根精确覆盖 6 个月窗口）；跨页 pre_close 全序列重算。
  - `app/services/minute_market_sync_service.py`：全市场编排（增量 600 根/只；回填至 start_date 缺省 185 天），断点续传（state.json 已完成清单）、连续 30 只失败冷却停手（cooldown 标记区分"运行中"与"待续传"）、心跳 30 分钟过期。
  - 晚间链路：`daily_alert_service` 四步之后新增第五步（周末跳过、`MINUTE_MARKET_SYNC_ENABLED=0` 可关、异常不阻塞次日调度）。
  - 北交所支持：`code_mapping` 扩展 market=2（920/43/83 开头），实测可取 bars。
  - API：`GET /api/realtime-analysis/data/market-sync/status`、`POST .../run`（后台线程）；数据管理页新增"全市场分钟线同步"面板（进度条/启动增量/启动 6 个月回填）。
  - 治理：`DataGovernanceService.cleanup_minute_partitions`（保留窗口锚定最新分区、dry-run 默认）+ `POST /api/datasources/minute-cleanup`。
- 回填状态：2026-10-11 已通过 API 启动全市场 6 个月回填（~5300 只 A 股含北交所，预计数小时，断点可续，进度见数据管理页）。滚动保留窗口清理待回填完成后按需执行。

### 3.3 日内因子库

- 改动：新增 `services/intraday_factors.py`（或并入 factor_engine）：VWAP 乖离、开盘 30min 动量、日内动量/反转、尾盘收益、日内波动占比等 ~10 个因子，走既有 factor_values 落库与 percentile_rank/z_score 标准化管线。
- 验收：日内因子可被 IC 分析/分位回测/因子体检直接消费；体检（覆盖率/共线性）通过后进入生命周期管理。

### 3.4 分钟级回测

- 改动：轻量 `intraday_backtest`（日内出场、T+1 开仓约束、涨跌停不可成交沿用现有 tradability 逻辑），或扩展 `signal_backtest_service` 支持分钟粒度。
- 验收：日内策略回测净值/逐笔可查；同一信号在日线与分钟口径交叉验证无系统性趋势偏差。

---

## 批次四：数据补全与因子扩展

### 4.1 指数数据补全

- 现状：`data/index_daily/` 仅 6 只宽基、无行业/概念指数；回测默认基准 000300.SH 实际靠 fallback 到 399300.SZ（`backtest_engine.py:1027-1090`，alpha/beta 口径已偏）。
- 改动：
  - `index_daily` 下载作业扩展：申万一级行业指数（tushare `sw_daily`）+ 主要宽基补齐，概念指数视数据源情况二期。
  - `get_index_basic` 接入指数列表查询接口（顺带解决 1.1 的孤儿问题）。
  - 修复回测基准：补齐 000300.SH 数据后移除 fallback（或保留仅作告警），alpha/beta/IR 统一口径。
- 验收：行业轮动可基于真实行业指数做策略回测；回测基准无降级 warning；行业轮动评分与指数动量口径交叉验证。

### 4.2 龙虎榜/涨停事件因子

- 现状：fuyao 已接龙虎榜、游资机构榜、热股榜、涨停池/连板梯队（全部真数据），但仅有展示页，无任何因子/统计消费。
- 改动：
  - 事件数据历史落库：每日盘后调度链新增归档作业（龙虎榜明细、涨停池、连板梯队 → `data/event_archive/`）。
  - 事件研究工具：上榜后 N 日超额收益、连板高度→次日晋级率、游资席位净买跟踪（统计页即可，先进信号实验室）。
  - 因子化 2-3 个市场情绪因子入 factor_values：涨停家数 z-score、连板高度、炸板率（`market_mood` 已算，需入因子管线接受体检）。
  - 纳入每日预警（情绪极值提醒）。
- 验收：情绪因子过体检并可查历史 IC；事件统计页上线；预警含情绪指标；归档作业随调度链自动运行。

### 4.3 财务 PIT 因子库

- 现状：三大报表 parquet 已有（57~104MB）+ point-in-time 公告日打点已支持；财务质量分仅单票杜邦分解，未入因子体系。
- 改动：
  - 5-8 个基本面因子按公告日 PIT 落 factor_values：应计质量、经营现金流/净利润、毛利率变化、杠杆变化、资产周转变化、ROE 变化。
  - 与价量因子做相关性去冗余 → 过体检 → 采纳白名单 → 可喂 ML 训练。
  - 财务异动扫描（财务健康页已有名单）与因子异常联动标注。
- 验收：基本面因子过体检；**PIT 无前视抽查**（公告日边界前后因子值正确）；与价量因子相关性 |ρ|<0.5；基本面 4 因子止于 2026-08-24 的覆盖缺口一并评估是否回补。

---

## 批次五：研究能力升级

### 5.1 回测引擎多空化

- 现状：`backtest_engine` 为 long-only（`_rebalance_portfolio` 先卖后买、无负仓位）；因子研究链的组间差检验能证明"多空显著"，但引擎层无法回测空头腿，两端接不上。
- 改动：
  - 分位多空模式：多头组 + 空头组负仓位、等名义本金。
  - 行业中性约束（组内行业暴露对齐基准）与可选波动率目标仓位。
  - 明确文档口径：A股个股融券不可得的现实下，此为**研究级多空口径，非可交易口径**；空头腿的涨跌停/停牌处理规则显式声明。
- 验收：多空净值方向与组间差检验结论一致；成本模型（佣金/滑点/印花税）在双腿各计一次；文档口径声明完整。

### 5.2 Paper trading 模拟盘（价值兑现闭环）

- 现状：无任何虚拟账户；预测跟踪是模型级（逐日预测 IC、top-N 实现收益），缺组合级"每天实际会选出什么"的持续跟踪。
- 改动：
  - 虚拟账户模型：现金 + 持仓 + 流水（复用组合交易流水的加权利成本/账本为准思路），**无券商接口**。
  - 挂载每日调度链：18:30 信号 → 生成待执行单 → 次日开盘虚拟成交（T+1）；停牌/涨跌停不可成交沿用 tradability 规则。
  - 逐日盯市净值 + **与回测预期的对齐报告**（跟踪误差归因：成交价差/停牌/涨跌停/信号时点）。
  - 前端模拟盘页：净值、持仓、待执行单、流水、对齐偏差。
- 验收：连续运行 ≥20 个交易日净值无手工干预；对齐报告能解释偏差来源；与回测同信号段的净值趋势一致。

### 5.3 寻优扩展

- 现状：`backtest_optimizer` 仅支持 ma_cross/kdj/rsi；筹码信号阈值硬编码于 `signal_defs.py`（历史坑：chip_signal 与 signal_backtest 两处需人工同步）。
- 改动：筹码信号阈值、行业轮动权重纳入网格寻优（walk-forward OOS 验证沿用现有框架）；寻优结果写回 `signal_defs.py` 单一源，保持"一处定义、两处消费"的纪律不破坏。
- 验收：寻优写回后 chip_signal/signal_backtest 读到同一阈值；OOS 验证报告可查。

### 5.4 AI 因子组合自动发现

- 改动：AI 工作台新增组合工具链：自然语言（如"帮我找最近一年最有效的 3 个低相关因子并回测"）→ 因子体检排名 → 贪心去冗余 → 分位回测 → 研究报告输出；产物可收藏复跑（复用 save_board/save_query 沉淀机制）。底层全部复用 `factor_screening` / 去冗余 / 分位回测既有服务，仅新增 ai/tools 注册与编排。
- 验收：一句话复现全链路且产物可收藏重跑；工具轮数不超现有上限（必要时拆分步骤）。

---

## 五、里程碑建议

| 时间 | 内容 |
|---|---|
| 第 1 周 | 批次一 + 批次二（断头路全部闭环） |
| 第 2-3 周 | 批次三：3.1 → 3.2，3.3 可并行，3.4 收尾 |
| 第 4 周 | 批次四（4.1 优先——回测基准口径问题影响所有回测结论） |
| 第 5-6 周 | 批次五（5.2 paper trading 优先，5.1 多空其次，5.3/5.4 穿插） |

批次四与批次三的 3.3/3.4 相互独立，可并行推进。

## 六、跨批次风险与纪律

1. **分钟数据量级**：先 6 个月滚动窗口验证读取性能与磁盘占用，再决定长期策略；通达信接口限频，全市场同步必须分批+断点续传。
2. **fuyao 历史深度有限**：事件因子从"开始归档"做起，不承诺深历史回测；归档作业一旦上线不可断（数据断档不可回补）。
3. **ml_factor_state 清理防误删**：必须 dry-run + 采纳白名单核验（覆盖率对比）后才可执行删除。
4. **PIT 纪律**：基本面因子必须按公告日打点，验收含边界抽查；事件因子同规则（信号日只能用 T 日及以前数据）。
5. **新因子一律走既有体检/生命周期管线**，不开旁路；退化因子（alpha_138 仅 169 股、alpha_030/143/146 缺席）在体检报告中持续可见。
6. **每批次完成后**：更新 README 能力现状表 + 本文档批次状态（⬜→✅），相关记忆文件同步。

## 附录：盘点证据要点（2026-10-11）

- 分钟数据：`data/stock_minute/` 4 周期（无 1min）、8 只代码、`sz.000001`/`000001.SZ` 双份；消费方全为展示类，因子/策略/回测零消费。
- 指数：`data/index_daily/stock/` 仅 6 只宽基；`backtest_engine.py:1027-1090` 基准 fallback；`data_reader.py:359-361 get_index_basic` 零调用。
- 报告：`report_dispatch_service.py:9-17` 自述最小可用、`:68` channels=["log"]；`realtime_report.py` 无 export 端点。
- news 占位：`websocket_push_service.py:336-338` payload 恒空、`:51` 默认 disabled。
- 存储：`data/ml_factor_state/` 9.1GB 无清理；`parquet_state_store.py` 无 TTL。
- 回测：`backtest_engine.py:763-828` long-only；`:169` 滑点、`:448-514` 分红送转、`:1027-1090` 基准降级均已支持。
- 实盘：全库无 broker/下单/easytrader/miniQMT 代码（**按用户决策永久不做**）。
