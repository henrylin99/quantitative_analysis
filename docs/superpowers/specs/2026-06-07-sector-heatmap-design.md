# 板块热力图功能设计

> Date: 2026-06-07
> Status: Approved

## 概述

新增 Treemap 热力图页面，展示 A 股 110 个行业板块的涨跌分布。板块面积 = 总市值占比，颜色 = 加权涨跌幅（红涨绿跌）。点击板块后页面内展开个股明细表格。

数据源：`data/data.parquet`（每日由数据下载任务更新，~5500 行，276 列）。

## 数据层

### 数据源

`data/data.parquet` — 每日全市场宽表快照，包含 industry、pct_chg、total_mv、net_mf_amount 等字段。

### 板块聚合逻辑（后端 Python）

1. 读取 parquet，过滤掉 `close == 0` 的停牌/退市股
2. 按 `industry` 分组，计算每个板块：
   - `avg_pct_chg`：加权平均涨跌幅（权重 = `total_mv`）
   - `total_mv`：板块总市值
   - `stock_count`：个股数量
   - `up_count` / `down_count`：涨/跌家数
   - `net_mf_amount`：板块主力净流入额合计
3. 按板块总市值降序排列

### 个股明细

前端 JS 从全量数据中按 `industry` 过滤，展示字段：

| 字段 | 说明 |
|---|---|
| `name` | 股票简称 |
| `pct_chg` | 涨跌幅 % |
| `close` | 收盘价 |
| `total_mv` | 总市值（亿元） |
| `net_mf_amount` | 主力净流入（万元） |
| `turnover_rate` | 换手率 % |

按 `pct_chg` 降序排列。

### 数据传递

后端将两份数据注入 Jinja2 模板：`sectors_json`（板块聚合）和 `stocks_json`（全量个股）。前端 JS 直接使用，无需额外 API 调用。

## 前端页面结构

### 页面布局（从上到下）

1. **页面标题栏**：板块热力图 · {trade_date}，含排序选项和图例说明
2. **Treemap 主区域**：ECharts treemap，每个矩形 = 一个行业板块
3. **个股展开区域**：点击板块后动态展开/收起的表格

### 交互行为

- **点击板块矩形**：treemap 下方展开/切换个股表格（带折叠动画），再次点击同板块则收起
- **悬停矩形**：ECharts tooltip 显示板块详情（涨跌家数、净流入、市值排名）
- **表格行点击**：不处理（保持简洁）

### 配色（A 股惯例）

- 涨：红色渐变 `#c0392b`（大涨）→ `#f5b7b1`（微涨）
- 跌：绿色渐变 `#27ae60`（大跌）→ `#a9dfbf`（微跌）
- 平盘：`#bdc3c7` 灰色

### ECharts Treemap 配置

- `visualMap` 连续型，范围取当日实际涨跌幅 min/max
- `leafDepth = 1`（只展示板块层级）
- `roam: false`（禁止缩放平移）

## 文件结构与集成

### 新增文件（3 个）

| 文件 | 用途 |
|---|---|
| `app/services/heatmap_service.py` | 数据聚合服务：读 parquet → 板块汇总 + 个股列表 |
| `app/templates/heatmap.html` | 页面模板：ECharts treemap + 个股展开表格 |
| `app/routes/heatmap.py` | 路由：`GET /heatmap` |

### 修改文件（2 个）

| 文件 | 改动 |
|---|---|
| `app/__init__.py` | 注册新 blueprint `heatmap_bp` |
| `app/templates/base.html` | 导航栏追加"板块热力图"链接 |

### HeatmapService 接口

```python
class HeatmapService:
    def get_heatmap_data(self) -> tuple[list[dict], list[dict]]:
        """返回 (sectors_json, stocks_json)"""
```

### Route

```python
heatmap_bp = Blueprint('heatmap', __name__)

@heatmap_bp.route('/heatmap')
def heatmap_page():
    sectors, stocks = HeatmapService().get_heatmap_data()
    return render_template('heatmap.html',
                           sectors_json=sectors,
                           stocks_json=stocks,
                           trade_date=sectors[0]['trade_date'])
```

### 前端 JS（内联，~150 行）

- `initTreemap(sectors)` — 初始化 ECharts treemap
- `onSectorClick(industry)` — 过滤 stocks 数据，渲染/切换下方表格
- 表格用原生 HTML `<table>` + Bootstrap 样式

### 依赖

无新依赖。使用项目已有的 pandas、ECharts 5.4.3、Bootstrap 5.1.3、Jinja2。

## 验收标准

1. 访问 `/heatmap` 能看到板块 Treemap 热力图，颜色和面积正确
2. 点击任意板块，下方展开该板块个股表格；再次点击收起
3. 点击不同板块，表格切换为对应板块的个股
4. 页面顶部导航有"板块热力图"入口
5. `data/data.parquet` 更新后刷新页面即可看到新数据
