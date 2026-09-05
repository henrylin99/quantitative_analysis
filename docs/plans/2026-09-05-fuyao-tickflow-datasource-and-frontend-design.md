# 数据源整合（fuyao / tickflow）与前端焕新 设计方案

Date: 2026-09-05

## 一、背景（Context）

参考项目 `tick-stock-panel`（MIT 协议，代码可合法借鉴）内置了两个数据源，经实测 key 均有效：

| 数据源 | 实测结论 | 能力 |
|---|---|---|
| **fuyao**（同花顺扶摇，`https://fuyao.aicubes.cn`） | key 有效，全部接口实测通过 | 全市场实时快照（5567 只）、单标的 10 年历史日K、**全市场日K dump（172MB parquet 一次下载）**、财务三表、估值快照、龙虎榜、竞价风向标、交易日历（近一年）、除权因子 dump |
| **tickflow**（`https://api.tickflow.org`） | key 有效，但为 **free 档**：除权因子与分钟K均返回 403 | 仅单标的日K（约 5 次/分钟限速）+ 小批量实时行情，无法承担全市场批量任务 |

本项目现状：

- 日频数据全部依赖 tushare：17 个 data job 中 15 个 `source_name="tushare"`，经 `DatabaseUtils.init_tushare_api()`（`app/utils/db_utils.py`）取数；无 provider 抽象层，**真正的系统契约是 Parquet 表结构**（`ParquetDataReader.TABLE_DIRS/STANDARD_COLUMNS`）。
- 前端为 React 19 + Bootstrap 5.3 CSS + 手写 `theme.css`（886 行），无 Tailwind、无组件库、emoji 图标、无代码分割、无 query 缓存层，视觉上偏粗糙。
- tick-stock-panel 前端为 Tailwind 3.4 + HSL 语义色 CSS 变量 + 自研薄组件层（无 shadcn/radix 依赖），暗色默认、1px 边框分层、等宽数字、信息密度高，观感明显更好。

## 二、目标（Goals）

1. **数据源整合**：将 fuyao、tickflow 作为独立于 tushare 的数据源接入，复用现有 data job / Parquet 架构，读取侧零改动。
2. **前端焕新**：参考 tick-stock-panel 的设计风格（不照抄），建立新的设计 token 与组件层，新开发的页面全部采用新风格。
3. 围绕 fuyao 独有能力（实时快照、龙虎榜、竞价风向标）新增有实际价值的页面。

## 三、非目标（Non-Goals）

- 不引入 tick-stock-panel 的插件体系 / 按数据集路由 / 能力探测引擎（对本项目过重）。
- 不替换、不下线 tushare：`trade_calendar`（历史）、`daily_basic`（历史估值）、`stk_factor`、`moneyflow`、`cyq_perf`、`stock_company` 等任务继续走 tushare（fuyao/tickflow free 档不覆盖）。
- 不整体重写存量 30 个旧页面（仅做基础设施打通，旧页面迁移作为可选后续阶段）。
- 不引入 tickflow 官方 SDK（`tickflow[all]` 依赖过重，free 档只用到日K/行情两个 GET 接口，纯 REST 封装即可）。
- 不新增定时调度器（数据更新仍由数据管理页手动触发）。

## 四、Part 1：数据源整合设计

### 4.1 与 tushare 区分的原则

| 维度 | tushare（现状） | fuyao / tickflow（新增） |
|---|---|---|
| 凭证 | `TUSHARE_TOKEN` | 独立的 `FUYAO_API_KEY` / `TICKFLOW_API_KEY`（`.env`） |
| 取数入口 | `DatabaseUtils.init_tushare_api()` | `app/utils/data_sources/` 下各自 client，互不引用 |
| job 标识 | `source_name="tushare"` | `source_name="fuyao"` / `"tickflow"` |
| 落盘 | 同一套 Parquet 表、同一套 schema | **相同**（数据源只是同一张表的可替换生产者） |
| 依赖包 | `tushare` | 零新增（复用 `requests`） |

核心思路：**数据源只在"写入侧"区分，读取侧契约不变**。不跑 fuyao job 即自动退回 tushare job，回退路径天然存在。

### 4.2 新增模块结构

```
app/utils/data_sources/
├── __init__.py
├── fuyao_client.py      # fuyao REST 客户端（借鉴 tick-stock-panel backend/app/plugins/fuyao/client.py，MIT，改 httpx→requests）
│                        #   含：X-api-key 认证、{code,message,data} 信封解包、错误码处理（4001限频/1002无效代码）、
│                        #   请求节流（页间 0.15s / 单标的 0.12s）、dump 预签名 URL 下载（不得带 api-key 头）
├── tickflow_client.py   # tickflow 轻量 REST 客户端（约 120 行：日K GET /v1/klines + 实时 GET/POST /v1/quotes）
└── fuyao_dump.py        # 日K dump 三档取数策略（借鉴 tick-stock-panel provider.py 的 get_daily 分层）：
                         #   ① 近端窗口(≤12天)→daily-k-10d dump（约1MB 一次覆盖全市场）
                         #   ② 深回填→daily-k 10年全量 dump（172MB，按 release 版本缓存于 data/cache/fuyao/）
                         #   ③ 兜底→单标的 historical 接口（10年自动分片）
```

下载脚本（沿用现有"脚本即 job"模式）：

```
app/utils/daily_history_fuyao.py     # 日线行情 → daily_history/daily/ 分区（核心，优先做）
app/utils/financial_fuyao.py         # 财务三表 → income_statement/ balance_sheet/ cash_flow/（按 end_date 分区）
app/utils/stock_basic_fuyao.py       # 股票列表 → stock_basic.parquet（可选，无退市股是其短板）
```

复用 `DailyFetchJob` 骨架（`app/utils/parquet_job_helpers.py:188`）与 `parquet_writer` 的原子写/锁机制。

### 4.3 schema 对齐（风险控制重点）

落盘必须与 tushare 产出完全同构，单位/口径换算如下：

| 字段 | tushare 契约 | fuyao 原始 | 换算 |
|---|---|---|---|
| 代码 | `ts_code`（600000.SH） | `thscode`（同格式） | 直传 |
| 日期 | `trade_date`（YYYYMMDD） | `date_ms` | **按北京时区解析**（date_ms 为北京时间零点 epoch ms，按 UTC 解析会偏一天） |
| 开高低收 | `open/high/low/close` | `*_price` | 直传 |
| 成交量 | `vol`（**手**） | `volume`（**股**） | `÷100` 取整 |
| 成交额 | `amount`（**千元**） | `turnover`（**元**） | `÷1000` |
| 前收盘 | `pre_close` | 无 | 从前一日 close 推导（首个交易日从 dump 元数据/快照 `prev_price` 补） |
| 涨跌/涨跌幅 | `change` / `pct_chg`（百分数） | 无 / `price_change_ratio_pct`（百分数） | 推导 / 直传（注意：tickflow 的 `ext.change_pct` 是**小数制**，若接 tickflow 需 ×100） |

快照接口字段双命名兼容（`high_price` / `highest_price`）在 client 层统一处理。财务三表按 tick-stock-panel `provider.py:757-799` 的映射思路改为映射到 tushare 列名（如 `operating_income→revenue`、`parent_holder_net_profit→n_income_attr_pid`），fuyao 独有字段作为扩展列透传，两源数据按（ts_code, end_date）合并取最新非空。

### 4.4 job 注册与配套改动

- `app/services/data_jobs/registry.py`：注册 `daily_history_fuyao`、`income_fuyao`、`balance_sheet_fuyao`、`cash_flow_fuyao`（合并为一个 `financial_fuyao` 亦可，实现时定），`source_name="fuyao"`；页面可见白名单 `_visible_job_types` 增加。tushare 对应 job 保留，两者是同一张表的两个可选生产者。
- `app/services/ai/tools.py:365`：token 检查条件从 `source_name == 'tushare'` 扩展为按 source→env 映射（tushare→TUSHARE_TOKEN、fuyao→FUYAO_API_KEY、tickflow→TICKFLOW_API_KEY）。
- `.env.example`：新增 `FUYAO_API_KEY=`、`TICKFLOW_API_KEY=`。key 不入库、不硬编码。
- 借鉴代码文件头保留 MIT 版权注释（协议要求）。

### 4.5 数据源状态 API（为前端页面服务）

新增 `app/api/market_api.py`（Blueprint）：

| 端点 | 数据来源 | 用途 |
|---|---|---|
| `GET /api/market/snapshot?codes=` | fuyao 快照（≤100/批） | 自选实时行情 |
| `GET /api/market/dashboard` | fuyao 指数快照 + 全市场快照聚合（涨跌家数/分布/榜单，内存缓存 30~60s） | 市场看板 |
| `GET /api/market/indices` | fuyao 指数接口 | 指数行情 |
| `GET /api/market/dragon-tiger?date=` | fuyao 龙虎榜（按日缓存落 parquet） | 龙虎榜页 |
| `GET /api/market/auction-benchmark?date=` | fuyao 竞价风向标（按日缓存） | 竞价风向标页 |
| `GET /api/datasources/status` | 探测 fuyao/tickflow/tushare key 有效性与档位（tickflow 档位探测：日K成功+除权因子403⇒free） | 数据源状态展示 |

后端服务层新建 `app/services/market_snapshot_service.py` 统一做缓存与降级（fuyao 失败时看板降级为本地 Parquet 最近交易日数据）。

### 4.6 分阶段实施

- **M1 客户端与配置**（~0.5 天）：`data_sources/` 三模块 + `.env` + 单元测试（mock 响应，覆盖信封错误码/单位换算/时区解析）。
- **M2 日线链路**（~1 天）：`daily_history_fuyao.py` + registry 注册 + 合约测试（与 tushare 同日数据抽样比对 OHLC 一致、vol/amount 换算正确）。跑通全市场一天增量（10d dump 路径）。
- **M3 财务三表**（~1 天）：字段映射表 + 三表 job + 合约测试。
- **M4 行情 API**（~1 天）：`market_api.py` + 缓存服务 + 龙虎榜/风向标按日落盘。

验收标准：数据管理页可见并成功执行 fuyao 任务；`ParquetDataReader` 读取 fuyao 产出的分区无感知差异（列白名单全通过）；fuyao job 失败不影响任何现有 tushare 任务。

## 五、Part 2：前端焕新设计

### 5.1 总体策略

**新页面走新体系，旧页面不动，基础设施共存**：

- 引入 Tailwind 3.4（**关闭 preflight**，避免与 Bootstrap reset 冲突），旧页面继续用 bootstrap 类，新页面用 tailwind 语义类。
- 设计 token 借鉴 tick-stock-panel 的架构但**换掉其品牌色**：采用其锌灰中性底（`--base 240 5% 5%`、`--surface 240 7% 10%`、暗色靠 1px 边框分层不靠阴影、卡片圆角 8px）+ 本项目现有靛蓝 `#6366f1` 作为 accent（保留本项目品牌识别，即"参考风格不照抄"）。红涨绿跌（`--bull #F04438` / `--bear #12B76A`）与数字排版规范（JetBrains Mono + tabular-nums）直接采纳。
- 暗色模式沿用现有 `data-theme` 属性（Tailwind 配 `darkMode: ['[data-theme="dark"]']`），补上 localStorage 持久化与 `index.html` 内联防闪白脚本（现刷新会闪回暗色）。
- 图标从 emoji 换为 `lucide-react`；新页面数据获取用 `@tanstack/react-query`（旧页面不迁移）。

### 5.2 基础设施改造（一次性）

| 事项 | 内容 |
|---|---|
| 依赖 | `tailwindcss@3 postcss autoprefixer`（dev）+ `clsx tailwind-merge lucide-react @tanstack/react-query`（runtime）；React 19 下 Tailwind 3.4 兼容 |
| `tailwind.config.ts` | 语义色映射 HSL 变量（base/surface/elevated/border/fg 三级/accent/bull/bear/warning）、圆角 token（card 8px/btn 6px/input 4px/dialog 12px）、`preflight: false` |
| `src/styles/tsp.css` | `@tailwind` 指令 + 双主题 CSS 变量段（暗色默认）+ 等宽数字工具类；`main.tsx` 中与 bootstrap css 共存 |
| 组件层 `src/components/ui/` | 从 tick-stock-panel 搬零依赖件并适配：`cn.ts`、`PageHeader`（细线下边框页头）、`EmptyState`、`Modal`（焦点陷阱/ESC/aria）、`Toast`、`SectionTitle`（accent 竖条+图标）；新增 `KpiCard`、`QuoteBadge`（半透明同色 pill：`bg-x/12 border-x/25 text-x`）、`DataTable`（轻表格：列自定义、mono 数字列、板块彩色徽章） |
| 路由 | 新页面在 `App.tsx` 单独 `lazy()`（不影响旧页同步加载现状） |
| QueryClient | `main.tsx` 挂 Provider，新页面独享 |

### 5.3 新增页面（4 个，全部新风格）

均参考 tick-stock-panel 对应页面的**布局模式与信息密度**，视觉与交互按本项目 token 重做：

1. **市场看板 `MarketDashboardPage`**（参考 Dashboard.tsx 的结构）
   指数 ticker 行（grid-cols-4）→ 市场宽度 KPI 行（涨跌家数/涨停跌停/成交额/振幅中位数）→ 主体两栏：左侧涨跌分布柱阵 + 领涨/领跌/成交额/换手 TOP 榜卡，右侧龙虎榜/风向标摘要 aside。数据：`/api/market/dashboard`，30s 轮询。点击个股弹出日K预览 Dialog（数据走本地 Parquet 已有接口）。
2. **自选行情 `WatchlistPage`**（参考 Watchlist.tsx 模式）
   分组卡片 + 实时快照表（fuyao 快照 5~10s 轮询，限 100 只/批），涨跌幅 bull/bear 着色、mono 数字、板块徽章；支持添加/删除自选（localStorage 起步，不建后端表）。
3. **龙虎榜与竞价风向标 `DragonTigerPage`**（fuyao 独有数据，tick-stock-panel 无此页，自由发挥）
   日期选择 + 三榜 Tab（机构/游资/全部）榜单表 + 当日风向标卡片组（每日约 5~6 只，含 auction_pct 与标签）。
4. **数据源中心 `DataSourceCenterPage`**（参考 Settings/DataSources.tsx 的能力矩阵思路）
   三个数据源卡片（tushare/fuyao/tickflow）：key 配置状态（脱敏显示）、实测档位/可用接口、近期 job 成功率；每数据集的当前生产者标注（daily: fuyao / stk_factor: tushare…）。与现有 `DataManagementPage` 互补（该页管任务执行，新页管数据源健康）。

侧栏导航新增"市场"分组（市场看板/自选行情/龙虎榜）+ "数据源中心"入口，新分组用新组件渲染。

### 5.4 分阶段实施

- **F1 基础设施**（~1 天）：Tailwind/token/组件层/QueryClient/防闪白，产出 1 个演示性骨架页验收视觉方向。
- **F2 市场看板 + 数据源中心**（~1.5 天）：依赖 M4 的 API。
- **F3 自选行情 + 龙虎榜**（~1.5 天）。
- **F4（可选后续）旧页面渐进迁移**：按访问频率逐页改造（HomePage → StocksPage → DataManagementPage…），不在本期承诺。

验收标准：新旧页面共存无样式互相污染（preflight 关闭验证点）；暗/亮主题切换新页面正常；Lighthouse 新页面无 console 报错；行情页在 fuyao 接口异常时显示降级提示而非白屏。

## 六、风险与对策

| 风险 | 对策 |
|---|---|
| 单位/时区换算错误导致脏数据进 Parquet | M2 合约测试与 tushare 同日数据抽样比对；换算集中在 client 层一处，脚本不做二次换算 |
| fuyao 限频（4001）/服务不可用 | client 内置节流与退避；行情 API 降级到本地 Parquet；下载 job 失败不影响 tushare 任务 |
| tickflow free 档 5rpm 误用于批量任务 | tickflow 定位为校验/兜底源，不注册批量 job；文档与代码注释注明档位限制 |
| Tailwind 与 Bootstrap 样式冲突 | 关闭 preflight；新页面不用 bootstrap 类；CI/lint 层面约定新页面目录禁引 bootstrap |
| fuyao 财务单标的接口全市场耗时（约 11 分钟） | job 内进度落 Parquet 状态库可断点续跑；报告期增量只拉新披露 |
| key 泄露 | 仅 `.env`，`.env.example` 留空占位；日志与前端脱敏 |

## 七、工期汇总

M1–M4 后端约 3.5 天，F1–F3 前端约 4 天，联调验收 0.5 天，合计约 **8 个工作日**。建议顺序：M1→M2→F1（尽早锁定视觉方向）→M3→M4→F2→F3。
