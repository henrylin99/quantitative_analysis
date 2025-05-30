import requests
import json

# 测试API调用
url = 'http://127.0.0.1:5001/api/realtime-analysis/indicators/calculate'
data = {
    'ts_code': '000001.SZ',
    'period_type': '5min',
    'indicators': ['MA', 'RSI'],
    'lookback_days': 30
}

try:
    response = requests.post(url, json=data)
    print('状态码:', response.status_code)
    print('原始响应文本:')
    print(repr(response.text))
    print('响应头:')
    print(response.headers)
    
    if response.text:
        try:
            json_data = response.json()
            print('解析后的JSON数据:')
            print(json.dumps(json_data, indent=2, ensure_ascii=False))
        except json.JSONDecodeError as e:
            print('JSON解析失败:', e)
    else:
        print('响应为空')
        
except Exception as e:
    print('请求失败:', e) 