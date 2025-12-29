from db_utils import DatabaseUtils
import pandas as pd
import time

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建表结构（如果还没有创建）
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_daily_history` (
      `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
      `trade_date` date NOT NULL COMMENT '交易日期',
      `open` decimal(10,4) DEFAULT NULL COMMENT '开盘价',
      `high` decimal(10,4) DEFAULT NULL COMMENT '最高价',
      `low` decimal(10,4) DEFAULT NULL COMMENT '最低价',
      `close` decimal(10,4) DEFAULT NULL COMMENT '收盘价',
      `pre_close` decimal(10,4) DEFAULT NULL COMMENT '昨收价【除权价，前复权】',
      `change_c` decimal(10,4) DEFAULT NULL COMMENT '涨跌额',
      `pct_chg` decimal(10,4) DEFAULT NULL COMMENT '涨跌幅 【基于除权后的昨收计算的涨跌幅：（今收-除权昨收）/除权昨收】',
      `vol` bigint DEFAULT NULL COMMENT '成交量 （手）',
      `amount` decimal(20,4) DEFAULT NULL COMMENT '成交额 （千元）',
      PRIMARY KEY (`ts_code`,`trade_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='股票日线行情数据表';
''')

# 获取A股日线行情数据（简单日线行情）
cursor.execute('''
SELECT ts_code FROM stock_basic;
''')
stock_list = cursor.fetchall()

batch_size = 100
data_list = []

for i in range(0, len(stock_list), batch_size):
    batch_stock_list = stock_list[i:i + batch_size]
    for stock in batch_stock_list:
        ts_code = stock[0]
        data = pro.daily(ts_code=ts_code, start_date='20250101', end_date='20250326')
        data_list.append(data)

    # 合并当前批次的数据
    combined_data = pd.concat(data_list, ignore_index=True)
    time.sleep(0.1)
    print(i)

    # 插入数据
    for index, row in combined_data.iterrows():
        cursor.execute('''
        INSERT INTO stock_daily_history (ts_code, trade_date, open, high, low, close, pre_close, change_c, pct_chg, vol, amount)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        ''', (row['ts_code'], row['trade_date'], row['open'], row['high'], row['low'], row['close'],
              row['pre_close'], row['change'], row['pct_chg'], row['vol'], row['amount']))

    # 提交事务
    conn.commit()

    # 清空当前批次的数据列表，为下一个批次做准备
    data_list.clear()

# 关闭连接
cursor.close()
conn.close()