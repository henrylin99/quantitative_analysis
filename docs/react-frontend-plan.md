# React 独立前端开发计划（feature/react-frontend 分支）

> **状态：一期（4 核心页面）+ 二期（三大优化）+ 三期（全站功能对齐，26 个路由）均已开发完成并按功能点验证通过。**
> 二期内容见文末「二期：体验升级」章节；三期内容见文末「三期：功能对齐」章节。

## 背景与约束

- 旧前端（Flask + Jinja2 模板）**功能与代码一律不改**；新前端为独立 React SPA，二者并存。
- 认证体系不做（单机使用），所有页面匿名访问。
- K 线图相关功能使用 **lightweight-charts v5**（与旧技术分析页 `analysis.html` 已迁移的 v5.2.1 同版本）。
- 后端 JSON API 直接复用，契约不变；不新增、不修改任何 `/api/*` 端点。

## 范围

首期覆盖 4 个核心页面 + 全局布局（旧版导航中纯 fetch 取数的页面，API 已完备）：

| 页面 | 路由（React） | 对应旧页面 | 后端 API |
|---|---|---|---|
| 股票列表 | `/stocks` | `stocks.html` | GET /api/stocks、/api/industries、/api/areas |
| 技术分析 | `/analysis` | `analysis.html` | GET /api/stocks/{code}、/history、/factors |
| 选股筛选 | `/screen` | `screen.html` | POST /api/analysis/screen |
| 回测验证 | `/backtest` | `backtest.html` | GET /api/stocks、POST /api/analysis/backtest |

多因子、实时分析、AI 工作台、试用功能等后续分期，不在本期。

## 技术选型

- Vite 7 + React 19 + TypeScript
- react-router-dom v7（SPA 路由）
- axios（API 客户端，统一解包 `{code, message, data}` 信封，`code===200` 为成功）
- lightweight-charts ^5.2.1（npm 引入，替代旧页 CDN standalone）
- Bootstrap 5 + 自定义暗色主题（对齐旧版 Obsidian Dark 观感：背景 `#0f172a`、主色 `#6366f1`）
- 状态管理：React hooks，不引入 redux

## 目录结构

```
frontend/
  index.html  package.json  vite.config.ts  tsconfig.json
  src/
    main.tsx  App.tsx
    api/        client.ts（axios 实例+信封解包）、types.ts、stocks.ts、analysis.ts
    components/ Layout.tsx（顶部导航）、StateViews.tsx（Loading/Error/Empty）
    charts/     chartData.ts（时序归一化纯函数）、MainChart.tsx、IndicatorChart.tsx
    pages/      StocksPage.tsx  AnalysisPage.tsx  ScreenPage.tsx  BacktestPage.tsx
    utils/      format.ts（formatNumber/formatPercent）
```

## 关键数据契约（开发与验证共同依据）

- 响应信封：`{code:number, message:string, data:T|null}`，HTTP 状态与 code 一致。
- `/history`、`/factors`：**按 trade_date 倒序（最新在前）**；`trade_date` 为 `'YYYY-MM-DD'` 字符串；图表消费前必须升序归一化（`localeCompare`），指标卡与数据表直接用原始倒序。
- history 字段：`open/high/low/close/pre_close/change/pct_chg/vol(手)/amount(千元)`；factors 字段：`pct_change`（注意与 history 的 `pct_chg` 不同名）、`macd_dif/macd_dea/macd`、`kdj_k/kdj_d/kdj_j`、`rsi_6/rsi_12/rsi_24`、`boll_upper/boll_mid/boll_lower`。
- null/NaN 一律不补 0：折线/指标序列输出 whitespace 点 `{time}`。
- screen 请求：数字以字符串提交，空值不发；响应 `stocks` 最多 200 条 + `has_more`。
- backtest 请求：`commission_rate` 传小数（UI 百分比 ÷100）；响应 `performance` 中比例字段为小数（0.05 = 5%）；`trades` 为最近 20 笔。
- 后端不返回净值曲线（`daily_values` 未暴露），本期与旧版一致不做净值图，仅指标卡 + 交易记录表。

## 有意为之的差异（相对旧版）

1. 涨跌配色统一为 A 股红涨绿跌（旧版指标卡/数据表残留 Bootstrap 绿涨红跌的不一致，予以修正）。
2. React npm 引入 lightweight-charts，不再有 CDN 缺失兜底分支。
3. 其余行为（默认值、归一化、交互时机）严格对齐旧版。

## 功能点验收清单（验证阶段逐项过）

### A. 全局
- [ ] A1 顶部导航 4 个页面可达，当前路由高亮；右上有"打开旧版"链接指向 Flask 首页。
- [ ] A2 后端未启动时页面显示错误态而非白屏；恢复后可重试。

### B. 股票列表 `/stocks`
- [ ] B1 默认加载第 1 页 100 条，显示总数徽章；列为 代码/名称/行业/地域/上市日期/操作。
- [ ] B2 行业、地域下拉选项来自 API，默认"全部"；筛选后回第 1 页。
- [ ] B3 关键字搜索（代码/名称）生效；重置清空条件并重查。
- [ ] B4 分页：上一页/下一页/页码窗口正确，单页时隐藏。
- [ ] B5 "详情"按钮指向旧版 `/stock/{ts_code}`（新窗口）。

### C. 技术分析 `/analysis`
- [ ] C1 初始仅显示表单：代码默认 `000001.SZ`，周期默认 60 天，图表类型 K线，主图视图"价格"，指标 MACD；5 个结果区块隐藏。
- [ ] C2 输入 6 位纯数字自动补后缀（0/3→.SZ，6→.SH）；blur 校验失败有错误提示。
- [ ] C3 点"分析"：并行请求 3 个 API；股票信息失败可容忍（降级卡），history/factors 失败报错提示。
- [ ] C4 主图：K线红涨绿跌 + 成交量副图（pane 高度 110）联动；十字光标图例显示 开/高/低/收/涨跌/量，随光标切换，默认显示最后一根。
- [ ] C5 区间最高/最低虚线参考线带轴标签；线图模式下按 close 极值、K线模式按 high/low。
- [ ] C6 图表类型切换 candlestick/line 即时生效（不重新请求）。
- [ ] C7 主图视图 价格/成交量 切换：成交量视图为单窗格柱状（volume 价格格式），无副图。
- [ ] C8 指标选项卡 MACD/KDJ/RSI/BOLL 即时切换：MACD=柱(正红负绿)+零轴点线+DIF/DEA；KDJ=三线+80/20 参考线；RSI=三线+70/30 参考线；BOLL=收盘+上中下轨（因子按日期对齐，缺口 whitespace）。
- [ ] C9 指标图十字光标图例显示各 series 数值（MACD 4 位小数）。
- [ ] C10 指标卡 4 张（最新价/涨跌幅、成交量/成交额、RSI、MACD），成交额按 `/100000 → 亿` 换算。
- [ ] C11 详细数据表取前 20 行，按 trade_date 合并 factors，列含 涨跌幅/RSI/MACD。
- [ ] C12 周期（30/60/120/250）修改后需重新提交才生效。
- [ ] C13 `?stock=` URL 参数预填输入框（不自动分析）；"详情"新窗口旧版页；"自选"为占位 alert。
- [ ] C14 数据 >90 根时初始缩放显示最近 90 根（右留 2 格），否则 fitContent。

### D. 选股筛选 `/screen`
- [ ] D1 行业/地域下拉来自 API；市场、数据日期可选。
- [ ] D2 估值/市值交易/技术指标/资金流各 min-max 输入成对提交；空值不发送。
- [ ] D3 动态条件行可增删（字段A + 操作符 + 字段B/固定值）。
- [ ] D4 提交后显示条件摘要、总数徽章；结果表 13 列（红涨绿跌）；超 200 条显示 has_more 提示。
- [ ] D5 模板保存到 localStorage 并可加载回填；重置清空。
- [ ] D6 导出 CSV（12 列，文件名含日期）；行操作：详情（旧版）、分析（旧版 `/analysis?stock=`）。

### E. 回测验证 `/backtest`
- [ ] E1 股票下拉来自 API（value=ts_code，文案 symbol - name）；策略 5 选 1，参数面板随策略切换并带默认值/范围；策略说明文案切换。
- [ ] E2 日期默认近一年；初始资金默认 100000；手续费 UI 百分比、提交 ÷100。
- [ ] E3 未选股票/策略有校验提示；状态徽章 等待/回测中/完成/失败 切换。
- [ ] E4 结果 4 张指标卡：策略信息 / 收益（total_return、annual_return、sharpe、最大回撤，百分比化）/ 交易统计（笔数、盈利笔数、胜率、平均持仓天数）/ 风险（波动率、期末资金、总成本、基准收益）。
- [ ] E5 交易记录表前 10 笔：日期/操作(buy 绿、sell 红 badge)/价格/数量/金额/收益率（正绿负红 → 统一红涨绿跌口径为：盈利红、亏损绿）。
- [ ] E6 重置按钮恢复默认表单。

## 开发顺序

1. 脚手架 + API 客户端 + 类型 + 布局导航
2. 图表数据纯函数 `chartData.ts`（升序归一化/whitespace/换算）
3. 技术分析页（重点，功能点最多）
4. 股票列表 → 选股 → 回测
5. 构建 + 部署路径（Vite dev proxy → 5000；`npm run build` 产物可后续由 Flask 挂载）
6. 按上文清单逐功能点浏览器验证

## 运行方式

```bash
# 终端1：后端（不变）
.venv/bin/python run.py          # 127.0.0.1:5000

# 终端2：新前端开发服务
cd frontend && npm install && npm run dev   # 127.0.0.1:5173，/api 代理到 5000
```

## 二期：体验升级（已完成并验证）

在用户授权的设计自主权范围内完成，旧前端与既有 API 契约保持兼容：

1. **回测资金曲线**：后端 `SingleStockBacktestEngine.run_backtest` 返回值增量新增 `daily_values`
   （date/cash/position_value/total_value，旧前端不消费该键）；前端回测页新增「资金曲线」面积图
   （lightweight-charts v5 AreaSeries + 初始资金基准线 + 十字光标图例）。
2. **技术分析图表升级**：原「主图 + 指标图」两个图表实例合并为单实例三窗格（价格/成交量窗格 340/100px、
   指标窗格 190px），共享时间轴与十字光标，一次 `subscribeCrosshairMove` 同时驱动主图与指标图例；
   布林带从独立指标页签升级为**主图叠加开关**（价格视图可用，成交量视图自动禁用），指标页签收敛为 MACD/KDJ/RSI。
3. **侧边栏布局 + 明暗主题**：左侧固定侧边栏（<992px 退化为顶栏），品牌渐变块 + 垂直导航 + 主题切换/旧版入口；
   `ThemeProvider` 管理 `data-theme`/`data-bs-theme`，全站 token 驱动双主题，lightweight-charts 通过
   ChartPalette（dark/light 两套色板）在主题切换时整体重建，红涨绿跌口径两套主题各自取色。

二期验证记录（Playwright 实测）：三窗格跨窗格十字光标联动 ✓、BOLL 叠加开/关 ✓、成交量视图下 BOLL 禁用 ✓、
线图/250 天/90 根初始缩放 ✓、资金曲线与指标卡数值一致（¥87,673.38 / -12.33%）✓、明暗主题切换后图表重建 ✓、
浏览器控制台 0 错误 ✓。


## 三期：功能对齐（已完成并验证）

用户反馈"页面功能不全，和原版相比还相差较多功能"，目标升级为与原版全站功能对齐。约束不变：原前端功能不改，后端仅增量。

### 后端增量（老页面 HTML 逐字节 diff 验证不变）

1. **抽取共享服务** `app/services/trial_analytics.py`：将 views.py 中 market-brief / financial-health /
   stock-radar / stock-panorama / moneyflow 五个试用页的计算逻辑原样迁移为服务函数，views.py 五个路由改为
   调用服务（重构前后 6 个页面 HTML `diff -q` 全部一致，零行为回归）。
2. **新增只读 JSON API**（`app/api/trial_api.py`，前缀 `/api/trial`）：`market-brief`、`financial-health`、
   `moneyflow`、`stock-radar`、`stock-panorama`、`heatmap`（复用 HeatmapService）。
3. **新增** `GET /api/data-jobs/init-status`（数据管理页初始化状态，供 React 页替代服务端模板注入）。

### 前端新增（22 个页面，路由总数 26）

- **前端基建**：echarts（按需引入）+ `EChart` 薄封装（主题切换整图重建、onClick 转发）、socket.io-client、
  裸响应 `rawGet/rawPost` 客户端族（ml-factor / data-jobs / realtime-analysis / ai-assistant / text2sql
  均为 `{success,...}` 而非信封）、侧边栏分组导航（概览/核心分析/多因子模型/实时分析/数据/试用工具/AI 助手）。
- **核心**：首页真实仪表盘（统计 + 分组入口）、个股详情六 Tab（历史/技术因子/资金流/筹码/财务/公司，
  ECharts 图 + 派生指标口径与旧版一致）、功能介绍静态页。
- **试用工具 7 页**：板块热力图（treemap 下钻）、形态选股（131 形态 AND 组合 + 排序 + 分页）、资金流统计、
  每日市场简报（复制全文）、财务健康度、个股雷达、个股全景。
- **数据管理**：初始化状态、大宽表状态/构建（18:00 门禁）、日频任务提交 + 3s 轮询 + 日志、分钟同步/批量/
  聚合/质检。
- **多因子模型 6 页**：因子管理（筛选/创建/白名单/计算）、模型管理（创建/删除/详情/异步训练 1s 轮询/
  预测 + CSV）、股票评分、投资组合（优化一体化/再平衡预览与执行/保存/导出）、分析报告（5 图）、组合回测。
- **实时分析 6 页**：技术指标（计算/多周期/对比/统计）、交易信号（生成/融合/监控/回测）、实时监控
  （30s 轮询 + 板块 bar + 情绪 gauge）、风险管理（VaR/相关性热力图/预警/止损止盈/压力测试）、报告管理
  （含 section 分发渲染器）、推送管理（socket.io + vite `ws` 代理）。
- **AI**：AI 工作台（SSE-over-fetch 流式、工具调用卡、会话持久化、轻量 markdown 渲染）、text2sql
  （解析/SQL/表格与图表/CSV/历史）。

### 三期发现并修正的旧版缺陷（React 版修复，旧版保持原样未动）

1. **评分日期格式**：`scoring/latest-trade-date` 返回 `YYYY-MM-DD`，但 `factor-based` 因子库按 `YYYYMMDD`
   索引，旧页面直接回填日期导致"未找到因子数据"404。React 版提交前规范化日期。
2. **评分因子回退**：最新交易日仅有财务类因子有值，旧页硬编码动量/资金流因子组合必然 404。React 版
   失败时自动回退"当日全部可用因子等权"并明示提示。
3. **持仓权重空值**：`portfolio/<id>` 的 `positions[].weight` 可能为 null，React 版显示 `--` 而非 0.00%。
4. **组合回测执行模式**：单机无 Celery worker 时 `mode='async'` 任务永久 queued；React 版与旧版一致改用
   `mode='sync'`（前端 600s 超时）。

### 三期验证记录（Playwright 实测，2026-09-03）

- 老 6 页 HTML diff 一致 ✓；7 个新 API curl 冒烟 200 ✓（雷达/全景含 400 错误分支）✓
- 热力图 treemap 渲染 + 板块下钻 ✓；形态选股「阳包阴」48 只与后端命中数一致 ✓
- 个股详情六 Tab 数据/图表/派生指标 ✓；首页仪表盘统计卡 ✓；功能介绍 ✓
- 数据管理页 init 状态/宽表状态（宽表日期 + 三源日期 + 原因）/分钟库统计/推荐顺序联动 ✓
- 因子管理 18 因子渲染 ✓；模型管理 5 模型 + 操作按钮 ✓；评分 Top50（回退提示）✓
- 投资组合列表/详情弹窗 ✓；分析报告统计卡与空态 ✓；组合回测因子策略 +10.74%/夏普 4.75/胜率 57.14%/11 只 ✓
- 实时监控大盘结构（自动刷新/切换/空态）✓；指标页 4 Tab + 指标清单 ✓；信号页 4 Tab + 统计 ✓
- 风险页组合加载 + 持仓明细 ✓；报告页 4 Tab + 统计 ✓；推送管理 socket.io 连接 → 订阅 → 启动推送 →
  收到 market_data_update ✓（已停止推送）
- AI 工作台 SSE 流式回复 + 工具调用 + markdown 表格 + 会话持久化 ✓；text2sql 查询（解析/SQL/20 行结果）✓
- 股票列表「详情」内链跳转个股详情 ✓；技术分析回归（图表/统计/表格/内链）✓
- `tsc -b` 0 错误、`vite build` 通过 ✓
