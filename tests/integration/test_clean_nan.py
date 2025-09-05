import numpy as np
import pandas as pd

def _clean_nan_values(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            if pd.isna(value):
                return None
            if np.isinf(value):
                return None
        return value
    except (TypeError, ValueError):
        return None

# 测试
test_values = [1.0, np.nan, np.inf, -np.inf, None, 'test']
for val in test_values:
    cleaned = _clean_nan_values(val)
    print(f'{val} -> {cleaned}')

# 测试列表清理
test_list = [1.0, np.nan, 2.5, np.inf, 3.0]
cleaned_list = [_clean_nan_values(v) for v in test_list]
print(f'原始列表: {test_list}')
print(f'清理后: {cleaned_list}')

# 测试JSON序列化
import json
try:
    json_str = json.dumps(cleaned_list)
    print(f'JSON序列化成功: {json_str}')
except Exception as e:
    print(f'JSON序列化失败: {e}') 