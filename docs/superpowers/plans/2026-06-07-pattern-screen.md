# 形态选股 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pattern-based stock screening page that reads `data/data.parquet` and provides a grouped checkbox filter panel + results table.

**Architecture:** Independent service reads the pre-computed wide parquet into a cached DataFrame. Pure-AND filtering across 132 binary pattern fields. Flask blueprint exposes two API endpoints and one page route. Frontend is a single Jinja template with vanilla JS.

**Tech Stack:** Flask Blueprint, pandas, Bootstrap 5, vanilla JS, ECharts theme from base template.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/services/pattern_screen_service.py` | Data loading, group metadata, AND-filtering, sort, paginate |
| Create | `app/api/pattern_screen_api.py` | REST endpoints: `/api/pattern-screen/groups` and `/api/pattern-screen/screen` |
| Create | `app/routes/pattern_screen.py` | Page route: `/pattern-screen/` |
| Create | `app/templates/pattern_screen.html` | Left panel (grouped checkboxes) + right table |
| Create | `tests/services/test_pattern_screen_service.py` | Service unit tests |
| Create | `tests/api/test_pattern_screen_api.py` | API contract tests |
| Modify | `app/__init__.py:40,54` | Register new blueprints |

---

### Task 1: PatternScreenService — metadata and screening logic

**Files:**
- Create: `app/services/pattern_screen_service.py`
- Test: `tests/services/test_pattern_screen_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_pattern_screen_service.py
"""PatternScreenService unit tests."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


@pytest.fixture
def sample_df():
    """Minimal DataFrame mimicking data/data.parquet structure."""
    return pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '000003.SZ', '000004.SZ'],
        'name': ['平安银行', '万科A', '国农科技', '国信证券'],
        'industry': ['银行', '房地产', '综合', '证券'],
        'trade_date': ['20260605'] * 4,
        'pct_chg': [1.5, -0.5, 3.0, 0.0],
        'close': [12.5, 8.0, 25.0, 15.0],
        'amount': [1000000, 500000, 200000, 300000],
        'total_mv': [2400000, 1200000, 600000, 900000],
        'turnover_rate': [1.2, 0.8, 2.5, 0.5],
        'vol_ratio_5': [1.8, 0.6, 2.1, 0.9],
        'consec_up_days': [2, 0, 3, 1],
        'pattern_golden_cross': [1, 0, 1, 0],
        'pattern_ma_bull': [0, 0, 1, 1],
        'pattern_bull_candle': [1, 0, 1, 0],
        'pattern_bear_candle': [0, 1, 0, 1],
        'break_high_20': [1, 0, 1, 0],
    })


@pytest.fixture
def service(sample_df):
    """Service with injected test DataFrame."""
    with patch('app.services.pattern_screen_service.PatternScreenService._load_df', return_value=sample_df):
        from app.services.pattern_screen_service import PatternScreenService
        svc = PatternScreenService()
        svc._df = sample_df
        return svc


class TestGetGroups:
    def test_returns_groups_with_hits(self, service):
        groups = service.get_groups()
        assert isinstance(groups, list)
        assert len(groups) > 0
        # Each group has id, label, fields
        g = groups[0]
        assert 'id' in g
        assert 'label' in g
        assert 'fields' in g
        for f in g['fields']:
            assert 'key' in f
            assert 'label' in f
            assert 'count' in f
            assert isinstance(f['count'], int)

    def test_fields_not_in_dataframe_are_excluded(self, service):
        groups = service.get_groups()
        df_cols = set(service._df.columns)
        for g in groups:
            for f in g['fields']:
                assert f['key'] in df_cols


class TestScreen:
    def test_no_patterns_returns_all(self, service, sample_df):
        result = service.screen(patterns=[])
        assert result['total'] == len(sample_df)
        assert len(result['rows']) == len(sample_df)

    def test_single_pattern_filters(self, service):
        result = service.screen(patterns=['pattern_golden_cross'])
        assert result['total'] == 2
        codes = [r['ts_code'] for r in result['rows']]
        assert '000001.SZ' in codes
        assert '000003.SZ' in codes

    def test_multiple_patterns_and_logic(self, service):
        result = service.screen(patterns=['pattern_golden_cross', 'pattern_ma_bull'])
        # Only 000003.SZ has both
        assert result['total'] == 1
        assert result['rows'][0]['ts_code'] == '000003.SZ'

    def test_sort_desc(self, service):
        result = service.screen(patterns=[], sort_by='pct_chg', order='desc')
        pcts = [r['pct_chg'] for r in result['rows']]
        assert pcts == sorted(pcts, reverse=True)

    def test_sort_asc(self, service):
        result = service.screen(patterns=[], sort_by='pct_chg', order='asc')
        pcts = [r['pct_chg'] for r in result['rows']]
        assert pcts == sorted(pcts)

    def test_pagination(self, service):
        result = service.screen(patterns=[], limit=2, offset=0)
        assert len(result['rows']) == 2
        assert result['limit'] == 2
        assert result['offset'] == 0
        assert result['total'] == 4

    def test_offset_beyond_results(self, service):
        result = service.screen(patterns=[], offset=100)
        assert result['total'] == 4
        assert len(result['rows']) == 0

    def test_invalid_sort_by_raises(self, service):
        with pytest.raises(ValueError, match='sort_by'):
            service.screen(patterns=[], sort_by='invalid_column')

    def test_invalid_order_raises(self, service):
        with pytest.raises(ValueError, match='order'):
            service.screen(patterns=[], order='random')

    def test_invalid_pattern_key_raises(self, service):
        with pytest.raises(ValueError, match='pattern.*not found'):
            service.screen(patterns=['nonexistent_pattern'])

    def test_limit_capped_at_500(self, service):
        result = service.screen(patterns=[], limit=9999)
        assert result['limit'] == 500

    def test_includes_trade_date(self, service):
        result = service.screen(patterns=[])
        assert result['trade_date'] == '20260605'

    def test_nan_converted_to_none(self, sample_df):
        # Add NaN to test conversion
        sample_df.loc[0, 'industry'] = np.nan
        with patch('app.services.pattern_screen_service.PatternScreenService._load_df', return_value=sample_df):
            from app.services.pattern_screen_service import PatternScreenService
            svc = PatternScreenService()
            svc._df = sample_df
            result = svc.screen(patterns=[])
            # industry for first row should be None, not NaN
            assert result['rows'][0]['industry'] is None


class TestInvalidateCache:
    def test_clears_df(self, service):
        assert service._df is not None
        service.invalidate_cache()
        assert service._df is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_pattern_screen_service.py -v`
Expected: FAIL — module `pattern_screen_service` not found

- [ ] **Step 3: Write the service implementation**

```python
# app/services/pattern_screen_service.py
"""形态选股服务 — 读取 data/data.parquet，提供分组元数据和纯AND筛选。"""
import os
import pandas as pd
import numpy as np
from flask import current_app
from loguru import logger

# ── 形态分组定义 ──────────────────────────────────────────
# 从 stock_screener/backend/meta.py 前7组提取
PATTERN_GROUPS = [
    {
        "id": "single_candle",
        "label": "单K形态",
        "fields": [
            {"key": "pattern_bull_candle", "label": "阳线"},
            {"key": "pattern_bear_candle", "label": "阴线"},
            {"key": "pattern_hammer", "label": "锤头线"},
            {"key": "pattern_doji", "label": "十字星"},
            {"key": "pattern_spinning_top", "label": "纺锤线"},
            {"key": "pattern_shooting_star", "label": "流星线"},
            {"key": "pattern_long_upper_shadow", "label": "长上影线"},
            {"key": "pattern_long_lower_shadow", "label": "长下影线"},
            {"key": "pattern_gravestone_doji", "label": "墓碑十字"},
            {"key": "pattern_dragonfly_doji", "label": "蜻蜓十字"},
            {"key": "pattern_hanging_man", "label": "上吊线"},
            {"key": "pattern_inverted_hammer", "label": "倒锤头"},
            {"key": "pattern_big_bull", "label": "大阳线"},
            {"key": "pattern_big_bear", "label": "大阴线"},
            {"key": "pattern_medium_bull", "label": "中阳线"},
            {"key": "pattern_medium_bear", "label": "中阴线"},
            {"key": "pattern_small_bull", "label": "小阳线"},
            {"key": "pattern_small_bear", "label": "小阴线"},
            {"key": "pattern_no_body", "label": "无实体线"},
            {"key": "pattern_no_upper_bull", "label": "光头阳线"},
            {"key": "pattern_no_upper_bear", "label": "光头阴线"},
            {"key": "pattern_no_lower_bull", "label": "光脚阳线"},
            {"key": "pattern_no_lower_bear", "label": "光脚阴线"},
            {"key": "pattern_t_shape", "label": "T字线"},
            {"key": "pattern_inverted_t_shape", "label": "倒T字线"},
            {"key": "pattern_low_open_high_close", "label": "低开高走"},
            {"key": "pattern_high_open_low_close", "label": "高开低走"},
            {"key": "pattern_gap_up", "label": "跳空高开"},
            {"key": "pattern_gap_down", "label": "跳空低开"},
            {"key": "pattern_close_above_prev_close", "label": "收盘站上前收"},
            {"key": "pattern_close_below_prev_close", "label": "收盘跌破前收"},
            {"key": "pattern_gap_reclaim_prev_close", "label": "低开收回前收"},
            {"key": "pattern_gap_fade_below_prev_close", "label": "高开回落失守前收"},
            {"key": "pattern_close_high", "label": "收盘近最高"},
            {"key": "pattern_flat_open_high_close", "label": "平开高走"},
            {"key": "pattern_flat_open_low_close", "label": "平开低走"},
            {"key": "pattern_gap_up_close_bull", "label": "高开收阳"},
            {"key": "pattern_gap_down_close_bear", "label": "低开收阴"},
            {"key": "pattern_open_near_high_close_high", "label": "开盘即最高附近收盘"},
            {"key": "pattern_open_near_low_close_low", "label": "开盘即最低附近收盘"},
            {"key": "pattern_flat_open", "label": "平开"},
            {"key": "pattern_gap_up_fill", "label": "高开补缺"},
            {"key": "pattern_gap_down_fill", "label": "低开补缺"},
            {"key": "pattern_pin_bar", "label": "Pin Bar"},
            {"key": "pattern_reversal_prelude", "label": "反包前兆"},
            {"key": "pattern_high_resistance", "label": "高位受阻"},
            {"key": "pattern_low_stabilization", "label": "低位止跌"},
            {"key": "pattern_break_prev_high", "label": "向上突破前高"},
            {"key": "pattern_break_prev_low", "label": "向下跌破前低"},
            {"key": "pattern_false_break", "label": "假突破回落"},
            {"key": "pattern_false_breakdown_recovery", "label": "假跌破回升"},
        ],
    },
    {
        "id": "double_candle",
        "label": "双K形态",
        "fields": [
            {"key": "pattern_bullish_engulfing", "label": "阳包阴"},
            {"key": "pattern_bearish_engulfing", "label": "阴包阳"},
            {"key": "pattern_inside_bar", "label": "孕线"},
            {"key": "pattern_dark_cloud", "label": "乌云盖顶"},
            {"key": "pattern_piercing", "label": "刺透形态"},
            {"key": "pattern_tweezer_top", "label": "镊子顶"},
            {"key": "pattern_tweezer_bottom", "label": "镊子底"},
            {"key": "pattern_gap_break", "label": "跳空上攻"},
            {"key": "pattern_gap_down_break", "label": "跳空下跌"},
            {"key": "pattern_gap_up_no_fill", "label": "跳空不补上行"},
            {"key": "pattern_gap_down_no_fill", "label": "跳空不补下行"},
            {"key": "pattern_reversal_bar", "label": "反转包线"},
            {"key": "pattern_flat_top", "label": "平头顶"},
            {"key": "pattern_flat_bottom", "label": "平头底"},
            {"key": "pattern_island_reversal", "label": "岛形反转"},
            {"key": "pattern_t_limit", "label": "T字板"},
            {"key": "pattern_limit_reversal_wrap", "label": "涨停反包"},
            {"key": "pattern_vol_up", "label": "放量上涨"},
            {"key": "pattern_vol_down", "label": "缩量下跌"},
            {"key": "pattern_double_volume_bar", "label": "倍量柱"},
            {"key": "pattern_breakout_volume_confirm", "label": "突破放量确认"},
        ],
    },
    {
        "id": "triple_candle",
        "label": "三K形态",
        "fields": [
            {"key": "pattern_morning_star", "label": "早晨之星"},
            {"key": "pattern_evening_star", "label": "黄昏之星"},
            {"key": "pattern_morning_doji_star", "label": "启明星"},
            {"key": "pattern_evening_doji_star", "label": "黄昏十字星"},
            {"key": "pattern_three_black_crows", "label": "三只乌鸦"},
            {"key": "pattern_red_three", "label": "红三兵"},
            {"key": "pattern_three_outside_up", "label": "三外升"},
            {"key": "pattern_three_outside_down", "label": "三外降"},
            {"key": "pattern_rising_three_methods", "label": "上升三法"},
            {"key": "pattern_falling_three_methods", "label": "下降三法"},
            {"key": "pattern_three_up", "label": "三连阳"},
            {"key": "pattern_three_down", "label": "三连阴"},
            {"key": "pattern_three_yang_kaitai", "label": "三阳开泰"},
            {"key": "pattern_three_yin_breakdown", "label": "三阴破位"},
        ],
    },
    {
        "id": "trend_structure",
        "label": "趋势结构",
        "fields": [
            {"key": "pattern_up_trend", "label": "上升趋势"},
            {"key": "pattern_down_trend", "label": "下降趋势"},
            {"key": "pattern_sideways", "label": "横盘整理"},
            {"key": "pattern_golden_cross", "label": "均线金叉"},
            {"key": "pattern_duck_head", "label": "老鸭头"},
            {"key": "pattern_double_bottom", "label": "双底"},
            {"key": "pattern_arc_bottom", "label": "圆弧底"},
            {"key": "pattern_ma_bull", "label": "均线多头排列"},
            {"key": "pattern_high_tight", "label": "高位强势整理"},
            {"key": "pattern_pullback_hold", "label": "回踩不破"},
            {"key": "pattern_trend_continue", "label": "趋势中继"},
            {"key": "pattern_ma_spread_bull", "label": "均线发散多头"},
        ],
    },
    {
        "id": "volume_price",
        "label": "量价形态",
        "fields": [
            {"key": "pattern_box_breakout", "label": "箱体放量突破"},
            {"key": "pattern_vol_price_up", "label": "量价齐升"},
            {"key": "pattern_platform_break", "label": "平台突破"},
            {"key": "pattern_triangle_squeeze", "label": "三角收敛突破"},
            {"key": "pattern_limit_turnover_strong", "label": "涨停换手强"},
            {"key": "pattern_price_volume_bear_divergence", "label": "价量顶背离"},
            {"key": "pattern_price_volume_bull_divergence", "label": "价量底背离"},
            {"key": "pattern_price_down_volume_up", "label": "价跌量增"},
            {"key": "pattern_volume_staircase", "label": "量能阶梯"},
            {"key": "pattern_pullback_volume_shrink", "label": "回调缩量"},
            {"key": "pattern_high_turnover", "label": "高换手"},
            {"key": "pattern_limit_up_volume_shrink", "label": "一字板缩量"},
            {"key": "pattern_false_breakout_volume_weak", "label": "假突破量弱"},
            {"key": "pattern_floor_volume_price", "label": "地量价稳"},
            {"key": "pattern_blowoff_volume_price", "label": "天量滞涨"},
            {"key": "pattern_v_reversal", "label": "V型反转"},
        ],
    },
    {
        "id": "compound",
        "label": "复合形态",
        "fields": [
            {"key": "pattern_first_limit", "label": "首板"},
            {"key": "pattern_multi_limit", "label": "连板"},
            {"key": "pattern_one_word_limit", "label": "一字板"},
            {"key": "pattern_limit_down_to_up", "label": "地天板"},
            {"key": "pattern_lotus_breakout", "label": "莲花突破"},
            {"key": "pattern_midway_refuel", "label": "中继加油"},
            {"key": "pattern_consolidation_platform", "label": "整理平台"},
            {"key": "pattern_n_breakout", "label": "N字突破"},
            {"key": "pattern_gap_breakaway", "label": "跳空突破"},
            {"key": "pattern_channel_breakout", "label": "通道突破"},
            {"key": "pattern_flag_breakout", "label": "旗形突破"},
        ],
    },
    {
        "id": "momentum",
        "label": "动量因子",
        "fields": [
            {"key": "break_high_20", "label": "突破20日新高"},
            {"key": "break_high_60", "label": "突破60日新高"},
            {"key": "break_high_120", "label": "突破120日新高"},
            {"key": "break_high_250", "label": "突破250日新高"},
            {"key": "consec_up_3", "label": "连续上涨3日"},
            {"key": "consec_up_5", "label": "连续上涨5日"},
        ],
    },
]

SORT_WHITELIST = [
    "ts_code", "pct_chg", "close", "amount", "total_mv",
    "turnover_rate", "vol_ratio_5", "consec_up_days",
]

DISPLAY_COLUMNS = [
    "ts_code", "name", "industry", "pct_chg", "close",
    "amount", "total_mv", "turnover_rate", "vol_ratio_5",
]


class PatternScreenService:
    """形态选股服务：读取宽表，提供分组元数据和筛选。"""

    def __init__(self):
        self._df = None

    def _load_df(self) -> pd.DataFrame:
        data_dir = current_app.config.get('DATA_DIR')
        path = os.path.join(data_dir, 'data.parquet')
        logger.info(f"PatternScreenService loading {path}")
        return pd.read_parquet(path)

    def _ensure_df(self) -> pd.DataFrame:
        if self._df is None:
            self._df = self._load_df()
        return self._df

    def get_groups(self) -> list:
        """返回分组元数据，每个字段附带当日命中数。

        Returns:
            list[dict]: [{id, label, fields: [{key, label, count}]}]
        """
        df = self._ensure_df()
        df_cols = set(df.columns)
        result = []
        for group in PATTERN_GROUPS:
            fields = []
            for f in group["fields"]:
                if f["key"] not in df_cols:
                    continue
                count = int(df[f["key"]].fillna(0).sum())
                fields.append({"key": f["key"], "label": f["label"], "count": count})
            if fields:
                result.append({"id": group["id"], "label": group["label"], "fields": fields})
        return result

    def screen(self, patterns=None, sort_by="pct_chg", order="desc", limit=50, offset=0):
        """纯AND筛选 + 排序 + 分页。

        Args:
            patterns: list[str] of pattern field keys to filter (all must == 1).
            sort_by: column to sort by (must be in SORT_WHITELIST).
            order: "asc" or "desc".
            limit: page size, capped at 500.
            offset: page offset, must be >= 0.

        Returns:
            dict with total, offset, limit, trade_date, rows.

        Raises:
            ValueError: on invalid sort_by, order, or pattern keys.
        """
        # Validate
        if sort_by not in SORT_WHITELIST:
            raise ValueError(f"sort_by '{sort_by}' not in whitelist: {SORT_WHITELIST}")
        if order not in ("asc", "desc"):
            raise ValueError(f"order must be 'asc' or 'desc', got '{order}'")

        patterns = patterns or []
        df = self._ensure_df()

        # Validate pattern keys
        df_cols = set(df.columns)
        for p in patterns:
            if p not in df_cols:
                raise ValueError(f"pattern '{p}' not found in data columns")

        # Filter: pure AND
        mask = pd.Series(True, index=df.index)
        for p in patterns:
            mask = mask & (df[p].fillna(0) == 1)
        filtered = df.loc[mask]

        # Sort
        filtered = filtered.sort_values(by=sort_by, ascending=(order == "asc"))

        # Paginate
        total = len(filtered)
        limit = max(1, min(500, int(limit)))
        offset = max(0, int(offset))
        page = filtered.iloc[offset:offset + limit]

        # Build rows — convert NaN to None for JSON
        rows_df = page[DISPLAY_COLUMNS].copy()
        rows = rows_df.where(rows_df.notna(), None).to_dict(orient="records")

        trade_date = str(df['trade_date'].iloc[0]) if 'trade_date' in df.columns else ''

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "trade_date": trade_date,
            "rows": rows,
        }

    def invalidate_cache(self):
        """清除缓存的 DataFrame，下次调用时重新读取。"""
        self._df = None
        logger.info("PatternScreenService cache invalidated")


# ── 模块级单例 ──────────────────────────────────────────
_service = None


def get_pattern_screen_service() -> PatternScreenService:
    """获取服务单例（缓存 DataFrame 跨请求复用）。"""
    global _service
    if _service is None:
        _service = PatternScreenService()
    return _service
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_pattern_screen_service.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/pattern_screen_service.py tests/services/test_pattern_screen_service.py
git commit -m "feat: add PatternScreenService with metadata and AND-filtering"
```

---

### Task 2: API endpoints — groups and screen

**Files:**
- Create: `app/api/pattern_screen_api.py`
- Test: `tests/api/test_pattern_screen_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_pattern_screen_api.py
"""Pattern screen API contract tests."""
import pytest
import json


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mock_service(app):
    """Register a mock service on the app for API tests."""
    from unittest.mock import MagicMock
    svc = MagicMock()
    svc.get_groups.return_value = [
        {
            "id": "trend_structure",
            "label": "趋势结构",
            "fields": [
                {"key": "pattern_golden_cross", "label": "均线金叉", "count": 304},
                {"key": "pattern_ma_bull", "label": "均线多头排列", "count": 259},
            ],
        }
    ]
    svc.screen.return_value = {
        "total": 2,
        "offset": 0,
        "limit": 50,
        "trade_date": "20260605",
        "rows": [
            {"ts_code": "000001.SZ", "name": "平安银行", "industry": "银行",
             "pct_chg": 1.5, "close": 12.5, "amount": 1000000,
             "total_mv": 2400000, "turnover_rate": 1.2, "vol_ratio_5": 1.8},
            {"ts_code": "000003.SZ", "name": "国农科技", "industry": "综合",
             "pct_chg": 3.0, "close": 25.0, "amount": 200000,
             "total_mv": 600000, "turnover_rate": 2.5, "vol_ratio_5": 2.1},
        ],
    }

    # Patch the singleton getter in the API module
    from unittest.mock import patch
    patcher = patch(
        'app.api.pattern_screen_api.get_pattern_screen_service',
        return_value=svc,
    )
    patcher.start()
    yield svc
    patcher.stop()


class TestGetGroups:
    def test_returns_200(self, client, mock_service):
        resp = client.get('/api/pattern-screen/groups')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 200
        assert isinstance(data['data'], list)

    def test_group_structure(self, client, mock_service):
        resp = client.get('/api/pattern-screen/groups')
        data = resp.get_json()['data']
        g = data[0]
        assert 'id' in g
        assert 'label' in g
        assert 'fields' in g


class TestScreen:
    def test_returns_200(self, client, mock_service):
        resp = client.post('/api/pattern-screen/screen',
                           json={'patterns': ['pattern_golden_cross']})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 200
        assert data['data']['total'] == 2

    def test_empty_patterns(self, client, mock_service):
        resp = client.post('/api/pattern-screen/screen', json={})
        assert resp.status_code == 200

    def test_invalid_sort_by_returns_400(self, client, mock_service):
        from unittest.mock import patch
        mock_service.screen.side_effect = ValueError("sort_by 'bad' not in whitelist")
        resp = client.post('/api/pattern-screen/screen',
                           json={'sort_by': 'bad'})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 400

    def test_response_format(self, client, mock_service):
        resp = client.post('/api/pattern-screen/screen',
                           json={'patterns': ['pattern_golden_cross']})
        data = resp.get_json()['data']
        assert 'total' in data
        assert 'offset' in data
        assert 'limit' in data
        assert 'trade_date' in data
        assert 'rows' in data
        row = data['rows'][0]
        for col in ['ts_code', 'name', 'industry', 'pct_chg', 'close',
                     'amount', 'total_mv', 'turnover_rate', 'vol_ratio_5']:
            assert col in row
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_pattern_screen_api.py -v`
Expected: FAIL — module `pattern_screen_api` not found

- [ ] **Step 3: Write the API blueprint**

```python
# app/api/pattern_screen_api.py
"""形态选股 API 端点。"""
from flask import Blueprint, request, jsonify
from loguru import logger

pattern_screen_api = Blueprint('pattern_screen_api', __name__, url_prefix='/api/pattern-screen')


@pattern_screen_api.route('/groups', methods=['GET'])
def get_groups():
    """返回形态分组元数据（含命中数）。"""
    try:
        from app.services.pattern_screen_service import get_pattern_screen_service
        svc = get_pattern_screen_service()
        groups = svc.get_groups()
        return jsonify({'code': 200, 'message': '成功', 'data': groups})
    except Exception as e:
        logger.error(f"获取形态分组失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500


@pattern_screen_api.route('/screen', methods=['POST'])
def screen():
    """执行形态筛选，返回结果表格。"""
    try:
        data = request.get_json() or {}
        patterns = data.get('patterns', [])
        sort_by = data.get('sort_by', 'pct_chg')
        order = data.get('order', 'desc')
        limit = data.get('limit', 50)
        offset = data.get('offset', 0)

        from app.services.pattern_screen_service import get_pattern_screen_service
        svc = get_pattern_screen_service()
        result = svc.screen(
            patterns=patterns,
            sort_by=sort_by,
            order=order,
            limit=limit,
            offset=offset,
        )
        return jsonify({'code': 200, 'message': '成功', 'data': result})
    except ValueError as e:
        logger.warning(f"形态筛选参数错误: {e}")
        return jsonify({'code': 400, 'message': str(e), 'data': None}), 400
    except Exception as e:
        logger.error(f"形态筛选失败: {e}")
        return jsonify({'code': 500, 'message': f'服务器错误: {str(e)}', 'data': None}), 500
```

- [ ] **Step 4: Register the API blueprint in `app/__init__.py`**

Add after the existing `heatmap_routes` import (around line 40):

```python
from app.api.pattern_screen_api import pattern_screen_api
```

Add after the `app.register_blueprint(heatmap_routes)` line (around line 54):

```python
app.register_blueprint(pattern_screen_api)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/api/test_pattern_screen_api.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/pattern_screen_api.py tests/api/test_pattern_screen_api.py app/__init__.py
git commit -m "feat: add pattern screen API endpoints (groups + screen)"
```

---

### Task 3: Page route and template

**Files:**
- Create: `app/routes/pattern_screen.py`
- Create: `app/templates/pattern_screen.html`
- Modify: `app/__init__.py:40,54` — add page blueprint registration
- Modify: `app/templates/base.html:335-338` — add nav link

- [ ] **Step 1: Create page route**

```python
# app/routes/pattern_screen.py
"""形态选股页面路由。"""
from flask import Blueprint, render_template

pattern_screen_bp = Blueprint('pattern_screen', __name__)


@pattern_screen_bp.route('/pattern-screen/')
def index():
    """形态选股页面。"""
    return render_template('pattern_screen.html')
```

- [ ] **Step 2: Register page blueprint in `app/__init__.py`**

Add import near line 40:

```python
from app.routes.pattern_screen import pattern_screen_bp
```

Add registration near line 54:

```python
app.register_blueprint(pattern_screen_bp)
```

- [ ] **Step 3: Add nav link in `app/templates/base.html`**

After the "板块热力图" nav item (around line 338), add:

```html
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('pattern_screen.index') }}">
        <i class="fas fa-crosshairs me-1"></i>形态选股
    </a>
</li>
```

- [ ] **Step 4: Create the template**

Create `app/templates/pattern_screen.html` with the following full content:

```html
{% extends "base.html" %}
{% block title %}形态选股{% endblock %}
{% block extra_css %}
<style>
.pattern-page { display: flex; min-height: calc(100vh - 56px); }
.filter-panel {
    width: 300px; min-width: 300px;
    background: var(--obs-surface, #1e293b);
    border-right: 1px solid var(--obs-border, #334155);
    overflow-y: auto; padding: 16px;
    display: flex; flex-direction: column;
}
.filter-panel .search-box {
    margin-bottom: 12px;
}
.filter-panel .search-box input {
    width: 100%; padding: 6px 10px; border-radius: 4px;
    border: 1px solid var(--obs-border, #334155);
    background: var(--obs-bg, #0f172a); color: var(--obs-text, #e2e8f0);
    font-size: 13px;
}
.filter-panel .search-box input::placeholder { color: #64748b; }
.accordion-item { border: none; margin-bottom: 4px; }
.accordion-button {
    background: transparent; color: #e2e8f0; font-size: 13px;
    font-weight: 600; padding: 8px 12px; border: none; box-shadow: none;
}
.accordion-button:not(.collapsed) {
    background: rgba(99, 102, 241, 0.1); color: #818cf8;
}
.accordion-button::after { filter: invert(0.7); }
.accordion-body { padding: 4px 8px; }
.pattern-check {
    display: flex; align-items: center; padding: 3px 4px; border-radius: 3px;
    font-size: 12px; color: #94a3b8; cursor: pointer;
}
.pattern-check:hover { background: rgba(99, 102, 241, 0.08); }
.pattern-check input[type="checkbox"] {
    margin-right: 6px; accent-color: #6366f1;
}
.pattern-check .hit-count {
    margin-left: auto; color: #64748b; font-size: 11px;
}
.filter-actions {
    margin-top: auto; padding-top: 12px;
    display: flex; gap: 8px;
}
.filter-actions .btn { flex: 1; font-size: 13px; }
.result-area { flex: 1; padding: 20px; overflow-x: auto; }
.stats-bar {
    display: flex; align-items: center; gap: 16px;
    margin-bottom: 16px; color: #94a3b8; font-size: 14px;
}
.stats-bar .badge { background: rgba(99, 102, 241, 0.2); color: #818cf8; }
.result-table {
    width: 100%; font-size: 13px; color: #e2e8f0;
}
.result-table thead th {
    background: var(--obs-surface, #1e293b); color: #94a3b8;
    font-weight: 600; padding: 10px 12px; border-bottom: 1px solid #334155;
    cursor: pointer; user-select: none; white-space: nowrap;
}
.result-table thead th:hover { color: #818cf8; }
.result-table thead th .sort-icon { margin-left: 4px; font-size: 10px; }
.result-table tbody td {
    padding: 8px 12px; border-bottom: 1px solid rgba(51, 65, 85, 0.4);
    white-space: nowrap;
}
.result-table tbody tr:hover { background: rgba(99, 102, 241, 0.05); }
.pct-up { color: #ef4444; }
.pct-down { color: #22c55e; }
.pct-flat { color: #94a3b8; }
.pagination-bar {
    display: flex; align-items: center; justify-content: center;
    gap: 6px; margin-top: 16px;
}
.page-btn {
    padding: 4px 10px; border-radius: 4px; border: 1px solid #334155;
    background: transparent; color: #94a3b8; font-size: 12px; cursor: pointer;
}
.page-btn:hover { border-color: #6366f1; color: #e2e8f0; }
.page-btn.active { background: #6366f1; color: #fff; border-color: #6366f1; }
.page-btn:disabled { opacity: 0.4; cursor: default; }
.empty-state { text-align: center; padding: 60px 20px; color: #64748b; }
.empty-state i { font-size: 48px; margin-bottom: 16px; }
@media (max-width: 768px) {
    .pattern-page { flex-direction: column; }
    .filter-panel { width: 100%; min-width: auto; max-height: 40vh; }
}
</style>
{% endblock %}

{% block content %}
<div class="pattern-page">
  <!-- Left Panel -->
  <div class="filter-panel">
    <div class="search-box">
      <input type="text" id="searchInput" placeholder="搜索形态名称..." oninput="filterBySearch()">
    </div>
    <div class="accordion" id="groupAccordion"></div>
    <div class="filter-actions">
      <button class="btn btn-outline-secondary" onclick="resetFilters()">
        <i class="fas fa-undo me-1"></i>重置
      </button>
      <button class="btn btn-primary" onclick="doScreen()" style="background:#6366f1;border-color:#6366f1;">
        <i class="fas fa-search me-1"></i>筛选
      </button>
    </div>
  </div>

  <!-- Right Area -->
  <div class="result-area">
    <div class="stats-bar" id="statsBar">
      <span>交易日: <strong id="tradeDate">--</strong></span>
      <span>|</span>
      <span>已选: <span class="badge" id="selectedCount">0</span> 个形态</span>
      <span>|</span>
      <span>匹配: <strong id="totalCount">0</strong> 只</span>
    </div>
    <div id="tableContainer">
      <div class="empty-state">
        <i class="fas fa-crosshairs d-block"></i>
        <div>加载中...</div>
      </div>
    </div>
    <div class="pagination-bar" id="paginationBar"></div>
  </div>
</div>

<script>
// ── State ──
let currentSort = 'pct_chg';
let currentOrder = 'desc';
let currentOffset = 0;
let currentLimit = 50;
let currentTotal = 0;
let allGroups = [];

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    loadGroups();
    doScreen();
});

// ── Load groups into left panel ──
async function loadGroups() {
    try {
        const resp = await axios.get('/api/pattern-screen/groups');
        const data = resp.data.data;
        if (!data) return;
        allGroups = data;
        renderGroups(data);
    } catch (e) {
        console.error('加载分组失败:', e);
    }
}

function renderGroups(groups) {
    const container = document.getElementById('groupAccordion');
    container.innerHTML = '';
    groups.forEach((g, idx) => {
        const show = idx < 2; // first two expanded by default
        container.innerHTML += `
        <div class="accordion-item">
          <h2 class="accordion-header">
            <button class="accordion-button ${show ? '' : 'collapsed'}" type="button"
                    data-bs-toggle="collapse" data-bs-target="#group-${g.id}">
              ${g.label} <span style="margin-left:auto;font-weight:400;font-size:11px;color:#64748b;">${g.fields.length}</span>
            </button>
          </h2>
          <div id="group-${g.id}" class="accordion-collapse collapse ${show ? 'show' : ''}"
               data-bs-parent="#groupAccordion">
            <div class="accordion-body">
              ${g.fields.map(f => `
                <label class="pattern-check" data-label="${f.label}">
                  <input type="checkbox" value="${f.key}" onchange="updateSelectedCount()">
                  ${f.label}
                  <span class="hit-count">${f.count}</span>
                </label>
              `).join('')}
            </div>
          </div>
        </div>`;
    });
}

// ── Search filter ──
function filterBySearch() {
    const q = document.getElementById('searchInput').value.trim().toLowerCase();
    document.querySelectorAll('.pattern-check').forEach(el => {
        const label = el.getAttribute('data-label').toLowerCase();
        el.style.display = (!q || label.includes(q)) ? '' : 'none';
    });
}

// ── Selected count ──
function updateSelectedCount() {
    const count = document.querySelectorAll('.pattern-check input:checked').length;
    document.getElementById('selectedCount').textContent = count;
}

// ── Get checked patterns ──
function getCheckedPatterns() {
    return Array.from(document.querySelectorAll('.pattern-check input:checked'))
        .map(cb => cb.value);
}

// ── Screen ──
async function doScreen() {
    const patterns = getCheckedPatterns();
    try {
        const resp = await axios.post('/api/pattern-screen/screen', {
            patterns,
            sort_by: currentSort,
            order: currentOrder,
            limit: currentLimit,
            offset: currentOffset,
        });
        const result = resp.data.data;
        if (!result) return;
        currentTotal = result.total;
        document.getElementById('tradeDate').textContent = formatDate(result.trade_date);
        document.getElementById('totalCount').textContent = result.total;
        renderTable(result.rows);
        renderPagination(result.total, result.limit, result.offset);
    } catch (e) {
        console.error('筛选失败:', e);
        document.getElementById('tableContainer').innerHTML =
            '<div class="empty-state"><i class="fas fa-exclamation-triangle d-block"></i><div>筛选失败，请重试</div></div>';
    }
}

// ── Render table ──
function renderTable(rows) {
    if (!rows || rows.length === 0) {
        document.getElementById('tableContainer').innerHTML =
            '<div class="empty-state"><i class="fas fa-inbox d-block"></i><div>暂无匹配结果</div></div>';
        return;
    }
    const sortIcon = (col) => {
        if (col !== currentSort) return '<i class="fas fa-sort sort-icon" style="opacity:0.3"></i>';
        return currentOrder === 'desc'
            ? '<i class="fas fa-sort-down sort-icon"></i>'
            : '<i class="fas fa-sort-up sort-icon"></i>';
    };
    let html = `<table class="result-table">
      <thead><tr>
        <th onclick="sortTable('ts_code')">代码 ${sortIcon('ts_code')}</th>
        <th>名称</th>
        <th>行业</th>
        <th onclick="sortTable('pct_chg')">涨跌幅 ${sortIcon('pct_chg')}</th>
        <th onclick="sortTable('close')">现价 ${sortIcon('close')}</th>
        <th onclick="sortTable('amount')">成交额 ${sortIcon('amount')}</th>
        <th onclick="sortTable('total_mv')">总市值 ${sortIcon('total_mv')}</th>
        <th onclick="sortTable('turnover_rate')">换手率 ${sortIcon('turnover_rate')}</th>
        <th onclick="sortTable('vol_ratio_5')">量比 ${sortIcon('vol_ratio_5')}</th>
      </tr></thead><tbody>`;
    rows.forEach(r => {
        const pctClass = r.pct_chg > 0 ? 'pct-up' : (r.pct_chg < 0 ? 'pct-down' : 'pct-flat');
        const pctStr = r.pct_chg > 0 ? '+' + r.pct_chg.toFixed(2) : r.pct_chg.toFixed(2);
        html += `<tr>
          <td>${r.ts_code || ''}</td>
          <td>${r.name || ''}</td>
          <td>${r.industry || '--'}</td>
          <td class="${pctClass}">${pctStr}%</td>
          <td>${fmtNum(r.close, 2)}</td>
          <td>${fmtAmount(r.amount)}</td>
          <td>${fmtAmount(r.total_mv)}</td>
          <td>${fmtNum(r.turnover_rate, 2)}%</td>
          <td>${fmtNum(r.vol_ratio_5, 2)}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('tableContainer').innerHTML = html;
}

// ── Sort ──
function sortTable(field) {
    if (currentSort === field) {
        currentOrder = currentOrder === 'desc' ? 'asc' : 'desc';
    } else {
        currentSort = field;
        currentOrder = 'desc';
    }
    currentOffset = 0;
    doScreen();
}

// ── Pagination ──
function renderPagination(total, limit, offset) {
    const bar = document.getElementById('paginationBar');
    if (total <= limit) { bar.innerHTML = ''; return; }
    const pages = Math.ceil(total / limit);
    const cur = Math.floor(offset / limit) + 1;
    let html = `<button class="page-btn" onclick="gotoPage(${offset - limit})" ${cur === 1 ? 'disabled' : ''}>
        <i class="fas fa-chevron-left"></i></button>`;
    // Show max 7 page buttons
    let start = Math.max(1, cur - 3);
    let end = Math.min(pages, start + 6);
    start = Math.max(1, end - 6);
    for (let i = start; i <= end; i++) {
        const off = (i - 1) * limit;
        html += `<button class="page-btn ${i === cur ? 'active' : ''}" onclick="gotoPage(${off})">${i}</button>`;
    }
    html += `<button class="page-btn" onclick="gotoPage(${offset + limit})" ${cur === pages ? 'disabled' : ''}>
        <i class="fas fa-chevron-right"></i></button>`;
    bar.innerHTML = html;
}

function gotoPage(offset) {
    currentOffset = Math.max(0, offset);
    doScreen();
}

// ── Reset ──
function resetFilters() {
    document.querySelectorAll('.pattern-check input').forEach(cb => cb.checked = false);
    document.getElementById('searchInput').value = '';
    filterBySearch();
    updateSelectedCount();
    currentOffset = 0;
    currentSort = 'pct_chg';
    currentOrder = 'desc';
    doScreen();
}

// ── Formatters ──
function fmtNum(v, digits) {
    if (v == null) return '--';
    return Number(v).toFixed(digits);
}

function fmtAmount(v) {
    if (v == null) return '--';
    v = Number(v);
    if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + '亿';
    if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + '万';
    return v.toFixed(2);
}

function formatDate(d) {
    if (!d || d.length !== 8) return d || '--';
    return d.slice(0, 4) + '-' + d.slice(4, 6) + '-' + d.slice(6, 8);
}
</script>
{% endblock %}
```

- [ ] **Step 5: Verify page loads**

Run: `python run.py` and open `http://localhost:5000/pattern-screen/`
Expected: page renders with left panel showing grouped checkboxes and right panel showing stock table

- [ ] **Step 6: Verify nav link works**

From any page, click "形态选股" in the nav bar.
Expected: navigates to `/pattern-screen/`

- [ ] **Step 7: Commit**

```bash
git add app/routes/pattern_screen.py app/templates/pattern_screen.html app/__init__.py app/templates/base.html
git commit -m "feat: add pattern screening page with left panel + right table layout"
```

---

### Task 4: Integration verification

**Files:** None new — verification only.

- [ ] **Step 1: Run all tests**

Run: `pytest -v`
Expected: all existing tests + new pattern screen tests pass

- [ ] **Step 2: Manual smoke test**

1. `python run.py`
2. Open `/pattern-screen/`
3. Verify: groups load with hit counts
4. Check a pattern (e.g. "均线金叉") → click "筛选" → verify table filters
5. Check a second pattern (e.g. "均线多头排列") → verify AND logic (fewer results)
6. Click a table header → verify sorting changes
7. Click page 2 → verify pagination
8. Click "重置" → verify all checkboxes clear and table shows all stocks
9. Type in search box → verify checkbox labels filter

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "fix: pattern screen integration fixes"
```
