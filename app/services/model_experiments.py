"""模型训练快照与实验对比（模型版本管理）。

model_definitions 重训即覆盖；本模块在每次训练成功后追加一行快照
（超参 + factor_list + 数据窗口 + 评估指标），供 A/B 对比与回溯。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.services.parquet_state_store import ParquetStateStore


def _json_loads(value: Any) -> Any:
    import json
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return None


def _json_dict(value: Any) -> Dict[str, Any]:
    parsed = _json_loads(value)
    return parsed if isinstance(parsed, dict) else {}


class TrainingSnapshotRepository:
    """训练快照表 model_training_snapshots"""

    TABLE = "model_training_snapshots"

    def __init__(self, store: ParquetStateStore = None):
        self.store = store or ParquetStateStore()

    def save_snapshot(self, model_id: str, model_name: str = None,
                      model_type: str = None, factor_list: List[str] = None,
                      model_params: Dict[str, Any] = None,
                      training_config: Dict[str, Any] = None,
                      train_start_date: str = None,
                      train_end_date: str = None,
                      metrics: Dict[str, Any] = None) -> Dict[str, Any]:
        import json

        def _to_jsonable(obj):
            # metrics 里混有 numpy 标量（int32/float64），不转换会
            # "Object of type int32 is not JSON serializable"
            if hasattr(obj, 'item'):
                return obj.item()
            return str(obj)

        record = {
            'snapshot_id': self.store.next_integer_id(self.TABLE, 'snapshot_id'),
            'model_id': model_id,
            'model_name': model_name,
            'model_type': model_type,
            'factor_list': json.dumps(list(factor_list or []), default=_to_jsonable),
            'model_params': json.dumps(model_params or {}, default=_to_jsonable),
            'training_config': json.dumps(training_config or {}, default=_to_jsonable),
            'train_start_date': train_start_date,
            'train_end_date': train_end_date,
            'metrics': json.dumps(metrics or {}, default=_to_jsonable),
            'created_at': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        with self.store.locked(self.TABLE):
            df = self.store.read_frame(self.TABLE)
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
            self.store.write_frame(self.TABLE, df)
        return record

    def list_snapshots(self, model_id: str = None) -> List[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE)
        if df.empty:
            return []
        if model_id:
            df = df[df['model_id'] == model_id]
        df = df.sort_values('snapshot_id', ascending=False)
        records = []
        for _, row in df.iterrows():
            rec = row.to_dict()
            for col in ('factor_list', 'model_params', 'training_config',
                        'metrics'):
                rec[col] = _json_loads(rec.get(col))
            records.append(rec)
        return records

    def get_snapshot(self, snapshot_id: int) -> Optional[Dict[str, Any]]:
        for rec in self.list_snapshots():
            if rec.get('snapshot_id') == int(snapshot_id):
                return rec
        return None

    def compare_models(self, model_ids: List[str]) -> Dict[str, Any]:
        """每个模型取最新快照做 A/B 并排对比。"""
        model_ids = [m for m in (model_ids or []) if m]
        if not model_ids:
            return {'error': '请指定至少一个模型'}
        rows = []
        for mid in model_ids:
            snaps = self.list_snapshots(mid)
            if not snaps:
                rows.append({'model_id': mid, 'error': '无训练快照'})
                continue
            latest = snaps[0]
            rows.append({
                'model_id': mid,
                'model_name': latest.get('model_name'),
                'model_type': latest.get('model_type'),
                'snapshot_id': latest.get('snapshot_id'),
                'trained_at': latest.get('created_at'),
                'train_window': [latest.get('train_start_date'),
                                 latest.get('train_end_date')],
                'n_factors': len(latest.get('factor_list') or []),
                'factor_list': latest.get('factor_list'),
                'model_params': latest.get('model_params'),
                'metrics': latest.get('metrics'),
            })
        return {'models': rows}
