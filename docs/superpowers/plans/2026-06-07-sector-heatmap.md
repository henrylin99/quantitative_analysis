# 板块热力图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Treemap heatmap page showing A-share sector performance with in-page drill-down to individual stocks.

**Architecture:** Flask route → HeatmapService reads `data/data.parquet` → injects JSON into Jinja2 template → ECharts renders treemap + JS handles click-to-expand stock table. No new dependencies.

**Tech Stack:** Flask, pandas, ECharts 5.4.3, Bootstrap 5.1.3, Jinja2

**Spec:** `docs/superpowers/specs/2026-06-07-sector-heatmap-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/services/heatmap_service.py` | Read parquet, aggregate by industry, return JSON |
| Create | `app/routes/heatmap.py` | Blueprint with `GET /heatmap` route |
| Create | `app/templates/heatmap.html` | ECharts treemap + expandable stock table |
| Modify | `app/__init__.py:38-52` | Register `heatmap_routes` blueprint |
| Modify | `app/templates/base.html:333` | Add nav link before 多因子模型 dropdown |
| Create | `tests/services/test_heatmap_service.py` | Unit tests for HeatmapService |

---

### Task 1: HeatmapService — Failing Tests

**Files:**
- Create: `tests/services/test_heatmap_service.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for HeatmapService — sector aggregation logic."""
import json
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


@pytest.fixture
def sample_df():
    """Minimal DataFrame matching data/data.parquet schema."""
    return pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '000003.SZ', '000004.SZ', '000005.SZ'],
        'name': ['平安银行', '万科Ａ', '测试银行', '测试地产', '停牌股'],
        'industry': ['银行', '全国地产', '银行', '全国地产', '全国地产'],
        'pct_chg': [1.5, -2.0, 0.5, -1.0, 0.0],
        'close': [11.0, 3.5, 5.0, 8.0, 0.0],
        'total_mv': [21300, 3900, 5000, 2000, 100],
        'net_mf_amount': [14000, -5000, 3000, -2000, 0],
        'turnover_rate': [0.5, 1.7, 1.0, 2.0, 0.0],
        'trade_date': ['20260605'] * 5,
    })


@pytest.fixture
def service():
    from app.services.heatmap_service import HeatmapService
    return HeatmapService()


class TestGetHeatmapData:
    """Test HeatmapService.get_heatmap_data()."""

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_returns_two_lists(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, stocks = service.get_heatmap_data()
        assert isinstance(sectors, list)
        assert isinstance(stocks, list)

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_filters_suspended_stocks(self, mock_read, service, sample_df):
        """Stocks with close == 0 should be excluded."""
        mock_read.return_value = sample_df
        sectors, stocks = service.get_heatmap_data()
        # 停牌股 (close=0) should not appear in stocks
        stock_names = [s['name'] for s in stocks]
        assert '停牌股' not in stock_names

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_sector_count(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        industry_names = [s['name'] for s in sectors]
        assert len(industry_names) == 2  # 银行 + 全国地产

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_sector_weighted_pct_chg(self, mock_read, service, sample_df):
        """avg_pct_chg should be market-cap weighted average."""
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        bank = next(s for s in sectors if s['name'] == '银行')
        # Weighted: (1.5*21300 + 0.5*5000) / (21300+5000) = 34450/26300 ≈ 1.3103
        assert abs(bank['avg_pct_chg'] - 1.3103) < 0.01

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_sector_stock_count(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        bank = next(s for s in sectors if s['name'] == '银行')
        assert bank['stock_count'] == 2  # 2 银行 after filtering

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_sector_up_down_count(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        realestate = next(s for s in sectors if s['name'] == '全国地产')
        # 万科 -2.0, 测试地产 -1.0 (停牌股 filtered out)
        assert realestate['down_count'] == 2
        assert realestate['up_count'] == 0

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_stocks_have_required_fields(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        _, stocks = service.get_heatmap_data()
        required = {'name', 'ts_code', 'pct_chg', 'close', 'total_mv',
                    'net_mf_amount', 'turnover_rate', 'industry'}
        for s in stocks:
            assert required.issubset(s.keys()), f"Missing keys: {required - s.keys()}"

    @patch('app.services.heatmap_service.pd.read_parquet')
    def test_trade_date_returned(self, mock_read, service, sample_df):
        mock_read.return_value = sample_df
        sectors, _ = service.get_heatmap_data()
        assert sectors[0]['trade_date'] == '20260605'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_heatmap_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.heatmap_service'`

---

### Task 2: HeatmapService — Implementation

**Files:**
- Create: `app/services/heatmap_service.py`

- [ ] **Step 1: Write HeatmapService**

```python
"""板块热力图数据服务 — 读取 data/data.parquet 并按行业聚合。"""
import os
import pandas as pd
import numpy as np
from loguru import logger


class HeatmapService:
    """板块热力图数据聚合服务。"""

    def __init__(self):
        self._data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'data.parquet'
        )

    def get_heatmap_data(self):
        """读取 parquet，返回 (sectors_json, stocks_json)。

        Returns:
            tuple: (list[dict], list[dict])
                - sectors: 板块聚合数据，按 total_mv 降序
                - stocks: 全量个股数据（已过滤停牌）
        """
        df = pd.read_parquet(self._data_path)
        trade_date = str(df['trade_date'].iloc[0])

        # 过滤停牌/退市
        df = df[df['close'] > 0].copy()

        # 板块聚合
        sectors = []
        for industry, group in df.groupby('industry'):
            total_mv_sum = group['total_mv'].sum()
            if total_mv_sum == 0:
                continue
            avg_pct_chg = np.average(group['pct_chg'], weights=group['total_mv'])
            sectors.append({
                'name': industry,
                'avg_pct_chg': round(avg_pct_chg, 2),
                'total_mv': round(total_mv_sum, 2),
                'stock_count': len(group),
                'up_count': int((group['pct_chg'] > 0).sum()),
                'down_count': int((group['pct_chg'] < 0).sum()),
                'net_mf_amount': round(group['net_mf_amount'].sum(), 2),
                'trade_date': trade_date,
            })

        sectors.sort(key=lambda x: x['total_mv'], reverse=True)

        # 个股明细
        stock_cols = ['ts_code', 'name', 'industry', 'pct_chg', 'close',
                      'total_mv', 'net_mf_amount', 'turnover_rate']
        stocks_df = df[stock_cols].sort_values('pct_chg', ascending=False)
        stocks = stocks_df.where(stocks_df.notna(), None).to_dict(orient='records')

        return sectors, stocks
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/services/test_heatmap_service.py -v`
Expected: All 8 tests PASS

- [ ] **Step 3: Commit**

```bash
git add app/services/heatmap_service.py tests/services/test_heatmap_service.py
git commit -m "feat: add HeatmapService with sector aggregation logic"
```

---

### Task 3: Heatmap Route

**Files:**
- Create: `app/routes/heatmap.py`

- [ ] **Step 1: Create route blueprint**

```python
"""板块热力图页面路由。"""
from flask import Blueprint, render_template
from loguru import logger
from app.services.heatmap_service import HeatmapService

heatmap_routes = Blueprint('heatmap_routes', __name__, url_prefix='/heatmap')


@heatmap_routes.route('/')
def index():
    """板块热力图页面。"""
    try:
        service = HeatmapService()
        sectors, stocks = service.get_heatmap_data()
        trade_date = sectors[0]['trade_date'] if sectors else ''
        return render_template(
            'heatmap.html',
            sectors_json=sectors,
            stocks_json=stocks,
            trade_date=trade_date,
        )
    except Exception as e:
        logger.error(f"热力图加载失败: {e}")
        return render_template(
            'heatmap.html',
            sectors_json=[],
            stocks_json=[],
            trade_date='',
            error='数据加载失败，请确认 data/data.parquet 是否存在',
        )
```

- [ ] **Step 2: Commit**

```bash
git add app/routes/heatmap.py
git commit -m "feat: add heatmap route blueprint"
```

---

### Task 4: Register Blueprint + Nav Link

**Files:**
- Modify: `app/__init__.py:38-52`
- Modify: `app/templates/base.html:333`

- [ ] **Step 1: Register heatmap_routes in app/__init__.py**

Add import at line 39 (after `realtime_analysis_routes`):
```python
from app.routes.heatmap import heatmap_routes
```

Add registration at line 52 (after `app.register_blueprint(realtime_analysis_routes)`):
```python
app.register_blueprint(heatmap_routes)
```

- [ ] **Step 2: Add nav link in base.html**

Insert after line 333 (after the 选股筛选 nav-item, before 多因子模型 dropdown):
```html
                    <li class="nav-item">
                        <a class="nav-link" href="/heatmap">
                            <i class="fas fa-th-large me-1"></i>板块热力图
                        </a>
                    </li>
```

- [ ] **Step 3: Verify app starts**

Run: `python -c "from app import create_app; app = create_app('development'); print('OK')" `
Expected: prints `OK`

- [ ] **Step 4: Commit**

```bash
git add app/__init__.py app/templates/base.html
git commit -m "feat: register heatmap blueprint and add nav link"
```

---

### Task 5: Heatmap Template

**Files:**
- Create: `app/templates/heatmap.html`

- [ ] **Step 1: Create the template**

```html
{% extends "base.html" %}

{% block title %}板块热力图{% endblock %}

{% block extra_css %}
<style>
.heatmap-page { padding: 20px 0; }
.heatmap-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px; flex-wrap: wrap; gap: 12px;
}
.heatmap-title { font-size: 20px; font-weight: 600; color: #e2e8f0; }
.heatmap-date { color: #94a3b8; font-size: 14px; }
.heatmap-legend {
    display: flex; align-items: center; gap: 8px; font-size: 12px; color: #94a3b8;
}
.legend-bar {
    width: 120px; height: 12px; border-radius: 3px;
    background: linear-gradient(to right, #27ae60, #a9dfbf, #bdc3c7, #f5b7b1, #c0392b);
}
#treemap-chart { width: 100%; height: 520px; }
.stock-detail-panel {
    margin-top: 16px; display: none;
    animation: slideDown 0.3s ease;
}
@keyframes slideDown {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}
.panel-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; background: #1e293b; border-radius: 8px 8px 0 0;
    border-bottom: 1px solid #334155;
}
.panel-title { font-size: 16px; font-weight: 600; color: #e2e8f0; }
.panel-summary { font-size: 13px; color: #94a3b8; }
.panel-close {
    background: none; border: none; color: #94a3b8; cursor: pointer;
    font-size: 18px; padding: 0 4px;
}
.panel-close:hover { color: #e2e8f0; }
.stock-table { width: 100%; }
.stock-table thead th {
    background: #0f172a; color: #94a3b8; font-size: 12px; font-weight: 500;
    padding: 8px 12px; border-bottom: 1px solid #1e293b; position: sticky; top: 0;
    text-transform: uppercase; letter-spacing: 0.5px;
}
.stock-table tbody tr { border-bottom: 1px solid #1e293b; }
.stock-table tbody tr:hover { background: rgba(99, 102, 241, 0.08); }
.stock-table td { padding: 8px 12px; color: #e2e8f0; font-size: 13px; }
.stock-table td:first-child { font-weight: 500; }
.pct-up { color: #ef4444; }
.pct-down { color: #22c55e; }
.pct-flat { color: #94a3b8; }
.error-banner {
    padding: 20px; text-align: center; color: #ef4444;
    background: #1e293b; border-radius: 8px; margin: 20px 0;
}
</style>
{% endblock %}

{% block content %}
<div class="container-fluid heatmap-page">
    {% if error is defined and error %}
    <div class="error-banner">{{ error }}</div>
    {% else %}
    <div class="heatmap-header">
        <div>
            <span class="heatmap-title">板块热力图</span>
            <span class="heatmap-date" style="margin-left:12px;">{{ trade_date }}</span>
        </div>
        <div class="heatmap-legend">
            <span>跌</span>
            <div class="legend-bar"></div>
            <span>涨</span>
        </div>
    </div>
    <div id="treemap-chart"></div>
    <div id="stock-detail" class="stock-detail-panel"></div>
    {% endif %}
</div>
{% endblock %}

{% block extra_js %}
<script>
(function() {
    var sectors = {{ sectors_json | tojson }};
    var stocks = {{ stocks_json | tojson }};

    // ---- Treemap ----
    var chart = echarts.init(document.getElementById('treemap-chart'), 'financial');

    function pctColor(val) {
        if (val > 0) {
            var t = Math.min(val / 5, 1);
            return 'rgb(' + Math.round(192 + (245-192)*(1-t)) + ',' +
                            Math.round(57 + (183-57)*(1-t)) + ',' +
                            Math.round(43 + (177-43)*(1-t)) + ')';
        } else if (val < 0) {
            var t = Math.min(Math.abs(val) / 5, 1);
            return 'rgb(' + Math.round(39 + (169-39)*(1-t)) + ',' +
                            Math.round(174 + (223-174)*(1-t)) + ',' +
                            Math.round(96 + (191-96)*(1-t)) + ')';
        }
        return '#bdc3c7';
    }

    var treemapData = sectors.map(function(s) {
        return {
            name: s.name,
            value: s.total_mv,
            avg_pct_chg: s.avg_pct_chg,
            stock_count: s.stock_count,
            up_count: s.up_count,
            down_count: s.down_count,
            net_mf_amount: s.net_mf_amount,
            itemStyle: { color: pctColor(s.avg_pct_chg) }
        };
    });

    var option = {
        tooltip: {
            formatter: function(info) {
                var d = info.data;
                return '<b>' + d.name + '</b><br/>' +
                    '加权涨跌: <b>' + d.avg_pct_chg.toFixed(2) + '%</b><br/>' +
                    '涨/跌: ' + d.up_count + '/' + d.down_count +
                    ' (共' + d.stock_count + '只)<br/>' +
                    '净流入: ' + (d.net_mf_amount / 10000).toFixed(2) + '亿';
            }
        },
        series: [{
            type: 'treemap',
            data: treemapData,
            roam: false,
            nodeClick: false,
            breadcrumb: { show: false },
            levels: [{
                itemStyle: { borderColor: '#0f172a', borderWidth: 2, gapWidth: 2 },
                upperLabel: { show: false }
            }],
            label: {
                show: true,
                formatter: function(params) {
                    var d = params.data;
                    var sign = d.avg_pct_chg >= 0 ? '+' : '';
                    return d.name + '\n' + sign + d.avg_pct_chg.toFixed(2) + '%';
                },
                fontSize: 13,
                color: '#fff',
                textShadowColor: 'rgba(0,0,0,0.5)',
                textShadowBlur: 4
            }
        }]
    };

    chart.setOption(option);

    // ---- Sector Click → Stock Table ----
    var activeIndustry = null;

    chart.on('click', function(params) {
        var industry = params.data.name;
        var panel = document.getElementById('stock-detail');

        if (activeIndustry === industry) {
            panel.style.display = 'none';
            activeIndustry = null;
            return;
        }
        activeIndustry = industry;

        var sector = sectors.find(function(s) { return s.name === industry; });
        var filtered = stocks.filter(function(s) { return s.industry === industry; });

        var sign = sector.avg_pct_chg >= 0 ? '+' : '';
        var html = '<div class="panel-header">' +
            '<div><span class="panel-title">' + industry + '（' + filtered.length + '只）</span>' +
            '<span class="panel-summary" style="margin-left:16px;">加权涨跌: ' +
            '<span style="color:' + (sector.avg_pct_chg >= 0 ? '#ef4444' : '#22c55e') + '">' +
            sign + sector.avg_pct_chg.toFixed(2) + '%</span></span></div>' +
            '<button class="panel-close" onclick="document.getElementById(\'stock-detail\').style.display=\'none\';' +
            'window._activeIndustry=null;">&times;</button>' +
            '</div>' +
            '<table class="stock-table"><thead><tr>' +
            '<th>名称</th><th>涨跌幅</th><th>收盘价</th><th>总市值(亿)</th>' +
            '<th>净流入(万)</th><th>换手率</th>' +
            '</tr></thead><tbody>';

        filtered.forEach(function(s) {
            var cls = s.pct_chg > 0 ? 'pct-up' : (s.pct_chg < 0 ? 'pct-down' : 'pct-flat');
            var pSign = s.pct_chg > 0 ? '+' : '';
            html += '<tr>' +
                '<td>' + s.name + '</td>' +
                '<td class="' + cls + '">' + pSign + (s.pct_chg != null ? s.pct_chg.toFixed(2) : '--') + '%</td>' +
                '<td>' + (s.close != null ? s.close.toFixed(2) : '--') + '</td>' +
                '<td>' + (s.total_mv != null ? (s.total_mv / 10000).toFixed(1) : '--') + '</td>' +
                '<td class="' + (s.net_mf_amount > 0 ? 'pct-up' : (s.net_mf_amount < 0 ? 'pct-down' : '')) + '">' +
                (s.net_mf_amount != null ? s.net_mf_amount.toFixed(0) : '--') + '</td>' +
                '<td>' + (s.turnover_rate != null ? s.turnover_rate.toFixed(2) + '%' : '--') + '</td>' +
                '</tr>';
        });

        html += '</tbody></table>';
        panel.innerHTML = html;
        panel.style.display = 'block';
        window._activeIndustry = industry;
    });

    window.addEventListener('resize', function() { chart.resize(); });
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/heatmap.html
git commit -m "feat: add heatmap template with ECharts treemap and stock table"
```

---

### Task 6: End-to-End Verification

- [ ] **Step 1: Run all tests**

Run: `pytest -v`
Expected: All existing + new tests PASS

- [ ] **Step 2: Start the app and verify**

Run: `python run.py`
Open browser → `http://localhost:5000/heatmap`

Verify:
- [ ] Treemap renders with colored rectangles sized by market cap
- [ ] Hover shows tooltip with sector details
- [ ] Click sector → stock table expands below
- [ ] Click same sector → table collapses
- [ ] Click different sector → table switches
- [ ] Nav bar shows "板块热力图" link and it navigates correctly
- [ ] Red = up, green = down

- [ ] **Step 3: Final commit (if any fixes needed)**

```bash
git add -A && git commit -m "fix: heatmap end-to-end adjustments"
```
