# 形态选股功能设计文档

## 概述

为 quantitative_analysis 项目添加形态选股（Pattern Screening）功能。基于 `data/data.parquet` 宽表中的 132 个 `pattern_*` / `break_high_*` / `consec_up_*` 二值字段，提供分组筛选界面和 API。

参考项目：`/Users/henrylin/vscode_space/stock_screener/backend`

## 方案选型

**Approach A: 独立页面 + 独立服务**

理由：`data/data.parquet` 是预计算宽表（5524 行 × 132 pattern 列），与现有 `ParquetDataReader` 的分区表体系不同，直接 pandas 读取最简单高效，无需耦合现有选股模块。

## 后端架构

### 文件结构

```
app/services/pattern_screen_service.py   # 服务层
app/api/pattern_screen_api.py            # API 层
app/routes/pattern_screen.py             # 页面路由
app/templates/pattern_screen.html        # 页面模板
```

### 数据层

- 通过 `current_app.config['DATA_DIR']` 解析路径，读取 `{DATA_DIR}/data.parquet` 到内存，缓存 DataFrame
- 132 个二值形态字段 + 基础字段（ts_code, name, industry, pct_chg, close, amount, total_mv, turnover_rate, vol_ratio_5 等）
- 提供字段元数据（分组定义、中文标签、当日命中数）
- 提供 `invalidate_cache()` 方法，在宽表重建 data job 完成后调用以刷新缓存

### 服务层 — PatternScreenService

```python
class PatternScreenService:
    _df: pd.DataFrame          # 缓存宽表
    _field_meta: list[dict]    # 分组元数据

    def get_groups() -> list[dict]
        # 返回 [{id, label, fields: [{key, label, count}]}]

    def screen(patterns, sort_by, order, limit, offset) -> dict
        # 纯 AND 筛选：所有勾选字段必须 == 1
        # patterns: list[str]，每个 key 必须存在于 DataFrame 列中，否则返回 400
        # sort_by: 必须在白名单内: ["pct_chg", "close", "amount", "total_mv",
        #          "turnover_rate", "vol_ratio_5", "consec_up_days"]，默认 "pct_chg"
        # order: 仅接受 "asc" 或 "desc"，默认 "desc"
        # limit: 1-500，默认 50
        # offset: >= 0，默认 0
        # 返回 {total, offset, limit, trade_date, rows: [...]}

    def invalidate_cache()
        # 清除缓存的 DataFrame，下次调用时重新读取 parquet
```

### API 端点

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/pattern-screen/groups` | GET | 返回分组元数据（含命中数） |
| `/api/pattern-screen/screen` | POST | 执行筛选，返回结果表格 |

POST `/api/pattern-screen/screen` 请求体：

```json
{
  "patterns": ["pattern_golden_cross", "pattern_ma_bull"],
  "sort_by": "pct_chg",
  "order": "desc",
  "limit": 50,
  "offset": 0
}
```

响应格式（遵循 `analysis_api.py` 的 `{code, message, data}` 约定）：

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "total": 42,
    "offset": 0,
    "limit": 50,
    "trade_date": "20260605",
    "rows": [
      {
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "industry": "银行",
        "pct_chg": 2.5,
        "close": 12.5,
        "amount": 1500000,
        "total_mv": 24000000,
        "turnover_rate": 1.2,
        "vol_ratio_5": 1.8
      }
    ]
  }
}
```

#### 参数校验规则

- `patterns`: 可选，默认 `[]`（返回全部股票）；若提供，每个 key 必须在 DataFrame 列中，否则 400
- `sort_by`: 可选，默认 `"pct_chg"`；必须在白名单中，否则 400
- `order`: 可选，默认 `"desc"`；仅接受 `"asc"` / `"desc"`，否则 400
- `limit`: 可选，默认 50；范围 1-500，超出截断
- `offset`: 可选，默认 0；必须 >= 0

### 形态分组定义

直接从参考项目 `meta.py` 的 `_PATTERN_GROUPS` 提取前 7 组（legacy groups）：

| 分组 ID | 中文名 | 字段数 |
|---|---|---|
| single_candle | 单K形态 | 50 |
| double_candle | 双K形态 | 21 |
| triple_candle | 三K形态 | 14 |
| trend_structure | 趋势结构 | 12 |
| volume_price | 量价形态 | 16 |
| compound | 复合形态 | 11 |
| momentum | 动量因子 | 6 |

运行时自动过滤掉 DataFrame 中不存在的字段。

### Blueprint 注册

在 `app/__init__.py` 中注册（Pattern A：url_prefix 在 Blueprint 构造函数中声明）：
- API blueprint: `pattern_screen_api = Blueprint('pattern_screen_api', __name__, url_prefix='/api/pattern-screen')`，然后 `app.register_blueprint(pattern_screen_api)`
- 页面 blueprint: `pattern_screen_bp = Blueprint('pattern_screen', __name__)`，路由 `@pattern_screen_bp.route('/pattern-screen/')`

## 前端设计

### 页面布局

继承 `base.html`，左右分栏：

- **左侧面板**（固定宽度 300px）：
  - 顶部搜索框（按中文名过滤形态）
  - 分组手风琴（可折叠），每组显示 checkbox + 中文名 + 命中数
  - 底部"重置"和"筛选"按钮

- **右侧内容区**：
  - 统计栏（已选形态数 + 匹配结果数）
  - 结果表格（代码、名称、行业、涨跌幅、现价、成交额、总市值、换手率、量比）
  - 表头可点击排序
  - 底部分页控件

### 交互流程

1. 页面加载 → GET `/api/pattern-screen/groups` → 渲染分组面板
2. 勾选形态 → 点击"筛选" → POST `/api/pattern-screen/screen` → 更新表格
3. 点击表头 → 重新筛选（带 sort_by 参数）
4. 点击页码 → 重新筛选（带 offset 参数）
5. 点击"重置" → 清空勾选，显示全部

### 技术栈

- Bootstrap 5（与项目一致）
- 原生 JavaScript（无额外框架）
- 项目已有 CSS 主题 (`financial-theme.css`)

## 筛选逻辑

- **纯 AND**：所有勾选的形态字段必须同时为 1
- 无勾选时（`patterns` 为空或省略）返回全部股票（仅排序和分页）
- 不在分组定义中的 DataFrame 列（如 `consec_up_days`）仍可作为 `sort_by` 使用，但不显示在筛选面板中

## 导航集成

在 `base.html` 导航栏中添加"形态选股"链接，使用 `url_for('pattern_screen.index')` 生成 URL。

## 不做的事情

- 不做形态回测（与现有 backtest 功能不同）
- 不做自然语言查询
- 不做形态组合的 AND/OR 混合逻辑（纯 AND）
- 不修改现有选股模块
