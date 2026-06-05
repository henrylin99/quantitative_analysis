from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Dict, List

from app.services.minute_parquet_store import MinuteParquetStore
from app.services.tongdaxin.bars import normalize_tdx_minute_bars, period_type_to_tdx_category
from app.services.tongdaxin.client import connected_session, create_hq_api
from app.services.tongdaxin.code_mapping import any_style_code_to_tdx


logger = logging.getLogger(__name__)


class TongdaxinMinuteSyncService:
    PERIOD_TYPES = {"5min": 0, "15min": 1, "30min": 2, "60min": 3}

    def __init__(self):
        self.parquet_store = MinuteParquetStore()
        self.api = None
        self.session = None

    def __enter__(self):
        self.api = create_hq_api()
        self.session = connected_session(self.api)
        self.session.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session is not None:
            self.session.__exit__(exc_type, exc_val, exc_tb)
        self.session = None
        self.api = None

    def _fetch_minute_payload(self, ts_code: str, period_type: str, start_date: str, end_date: str):
        market, code = any_style_code_to_tdx(ts_code)
        category = period_type_to_tdx_category(period_type)
        payload = self.api.get_security_bars(category, market, code, 0, 800) or []
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        filtered = []
        for row in payload:
            row_dt = datetime.strptime(str(row["datetime"])[:16], "%Y-%m-%d %H:%M").date()
            if start_dt <= row_dt <= end_dt:
                filtered.append(row)
        return filtered

    def sync_single_stock_data(self, ts_code: str, period_type: str = "5min", start_date: str = None, end_date: str = None) -> Dict:
        try:
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d")
            if not start_date:
                start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            market, code = any_style_code_to_tdx(ts_code)
            payload = self._fetch_minute_payload(ts_code, period_type, start_date, end_date)
            df = normalize_tdx_minute_bars(payload, market=market, code=code, period_type=period_type)
            if df.empty:
                return {"success": False, "message": f"未获取到{ts_code}的{period_type}数据", "data_count": 0}
            parquet_count = self.parquet_store.write_frame(df, period_type)
            return {
                "success": True,
                "message": "同步完成",
                "data_count": parquet_count,
                "parquet_count": parquet_count,
                "error_count": max(len(df) - parquet_count, 0),
                "period_type": period_type,
                "date_range": f"{start_date} 到 {end_date}",
            }
        except Exception as exc:
            logger.error(f"通达信同步异常: {exc}")
            return {"success": False, "message": f"同步异常: {exc}", "data_count": 0}

    def sync_multiple_stocks_data(
        self,
        stock_list: List[str],
        period_type: str = "5min",
        start_date: str = None,
        end_date: str = None,
        batch_size: int = 10,
    ) -> Dict:
        success_stocks = 0
        failed_stocks = 0
        total_data_count = 0
        for ts_code in stock_list:
            result = self.sync_single_stock_data(ts_code, period_type, start_date, end_date)
            if result["success"]:
                success_stocks += 1
                total_data_count += result["data_count"]
            else:
                failed_stocks += 1
        return {
            "success": True,
            "message": "批量同步完成",
            "total_stocks": len(stock_list),
            "success_stocks": success_stocks,
            "failed_stocks": failed_stocks,
            "total_data_count": total_data_count,
            "parquet_data_count": total_data_count,
            "period_type": period_type,
        }

    def sync_all_periods_for_stock(self, ts_code: str, start_date: str = None, end_date: str = None) -> Dict:
        results = {}
        for period_type in self.PERIOD_TYPES:
            results[period_type] = self.sync_single_stock_data(ts_code, period_type, start_date, end_date)
        return results
