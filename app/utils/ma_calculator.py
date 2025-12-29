from db_utils import DatabaseUtils
import pandas as pd
import numpy as np

# 初始化数据库连接
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建MA和EMA数据表
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_ma_data` (
        `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
        `ma5` decimal(10,3) DEFAULT NULL COMMENT '5日移动平均线',
        `ma10` decimal(10,3) DEFAULT NULL COMMENT '10日移动平均线',
        `ma20` decimal(10,3) DEFAULT NULL COMMENT '20日移动平均线',
        `ma30` decimal(10,3) DEFAULT NULL COMMENT '30日移动平均线',
        `ma60` decimal(10,3) DEFAULT NULL COMMENT '60日移动平均线',
        `ma120` decimal(10,3) DEFAULT NULL COMMENT '120日移动平均线',
        `ema5` decimal(10,3) DEFAULT NULL COMMENT '5日指数移动平均线',
        `ema10` decimal(10,3) DEFAULT NULL COMMENT '10日指数移动平均线',
        `ema20` decimal(10,3) DEFAULT NULL COMMENT '20日指数移动平均线',
        `ema30` decimal(10,3) DEFAULT NULL COMMENT '30日指数移动平均线',
        `ema60` decimal(10,3) DEFAULT NULL COMMENT '60日指数移动平均线',
        `ema120` decimal(10,3) DEFAULT NULL COMMENT '120日指数移动平均线',
        PRIMARY KEY (`ts_code`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='股票移动平均线数据表';
''')

# 清空表
cursor.execute("TRUNCATE TABLE stock_ma_data")

# 获取所有股票代码
cursor.execute("SELECT ts_code FROM stock_basic")
stock_codes = [row[0] for row in cursor.fetchall()]

# 计算EMA的函数
def calculate_ema_manually(prices, period):
    """
    手动计算EMA，确保初始值和计算过程的准确性
    :param prices: 价格序列
    :param period: 周期
    :return: EMA值序列
    """
    if len(prices) < period:
        return None
    
    # 使用前n个价格的SMA作为第一个EMA值
    sma = np.mean(prices[:period])
    ema_values = [sma]
    
    # 计算权重
    multiplier = 2 / (period + 1)
    
    # 计算后续EMA
    for i in range(period, len(prices)):
        ema = (prices[i] * multiplier) + (ema_values[-1] * (1 - multiplier))
        ema_values.append(ema)
    
    return ema_values[-1]  # 返回最后一个EMA值

# 对每只股票计算MA和EMA
for ts_code in stock_codes:
    print(f"处理 {ts_code}")
    
    # 获取该股票的历史数据，为了计算长周期EMA，获取更多数据
    # 对于120日EMA，至少需要240天的数据来提高准确性
    cursor.execute(f"""
    SELECT ts_code, close 
    FROM stock_daily_history 
    WHERE ts_code = '{ts_code}'
    ORDER BY trade_date DESC
    LIMIT 250
    """)
    
    # 获取数据并转换为DataFrame
    rows = cursor.fetchall()
    if len(rows) < 5:  # 如果数据少于5天，跳过这只股票
        print(f"数据不足，跳过 {ts_code}")
        continue
        
    df = pd.DataFrame(rows, columns=['ts_code', 'close'])
    df = df.iloc[::-1]  # 反转数据顺序，使其按时间正序排列
    
    # 将close列转换为数值类型
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    
    # 计算各个周期的MA
    ma5 = df['close'].rolling(window=5).mean().iloc[-1] if len(df) >= 5 else None
    ma10 = df['close'].rolling(window=10).mean().iloc[-1] if len(df) >= 10 else None
    ma20 = df['close'].rolling(window=20).mean().iloc[-1] if len(df) >= 20 else None
    ma30 = df['close'].rolling(window=30).mean().iloc[-1] if len(df) >= 30 else None
    ma60 = df['close'].rolling(window=60).mean().iloc[-1] if len(df) >= 60 else None
    ma120 = df['close'].rolling(window=120).mean().iloc[-1] if len(df) >= 120 else None
    
    # 计算各个周期的EMA - 使用pandas内置函数（适用于较短周期）
    ema5 = df['close'].ewm(span=5, adjust=False).mean().iloc[-1] if len(df) >= 5 else None
    ema10 = df['close'].ewm(span=10, adjust=False).mean().iloc[-1] if len(df) >= 10 else None
    ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1] if len(df) >= 20 else None
    ema30 = df['close'].ewm(span=30, adjust=False).mean().iloc[-1] if len(df) >= 30 else None
    
    # 对于长周期的EMA，使用手动计算方法提高准确性
    close_values = df['close'].values
    ema60 = calculate_ema_manually(close_values, 60) if len(df) >= 60 else None
    ema120 = calculate_ema_manually(close_values, 120) if len(df) >= 120 else None
    
    # 插入数据
    try:
        cursor.execute('''
            INSERT INTO stock_ma_data 
            (ts_code, ma5, ma10, ma20, ma30, ma60, ma120, ema5, ema10, ema20, ema30, ema60, ema120)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            ma5 = VALUES(ma5),
            ma10 = VALUES(ma10),
            ma20 = VALUES(ma20),
            ma30 = VALUES(ma30),
            ma60 = VALUES(ma60),
            ma120 = VALUES(ma120),
            ema5 = VALUES(ema5),
            ema10 = VALUES(ema10),
            ema20 = VALUES(ema20),
            ema30 = VALUES(ema30),
            ema60 = VALUES(ema60),
            ema120 = VALUES(ema120)
        ''', (
            ts_code,
            float(ma5) if ma5 is not None else None,
            float(ma10) if ma10 is not None else None,
            float(ma20) if ma20 is not None else None,
            float(ma30) if ma30 is not None else None,
            float(ma60) if ma60 is not None else None,
            float(ma120) if ma120 is not None else None,
            float(ema5) if ema5 is not None else None,
            float(ema10) if ema10 is not None else None,
            float(ema20) if ema20 is not None else None,
            float(ema30) if ema30 is not None else None,
            float(ema60) if ema60 is not None else None,
            float(ema120) if ema120 is not None else None
        ))
    except Exception as e:
        print(f"插入 {ts_code} 数据时出错")
        print(f"错误信息: {str(e)}")
        continue
    
    # 每处理完一只股票就提交一次
    conn.commit()

# 关闭数据库连接
cursor.close()
conn.close()

print("MA和EMA计算完成!") 