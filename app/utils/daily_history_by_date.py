from db_utils import DatabaseUtils
import pandas as pd
import time
# 重复了，暂时不用
# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建表结构（如果还没有创建）
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_daily_history` (
      `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
      `trade_date` date NOT NULL COMMENT '交易日期',
      `open` decimal(10,2) DEFAULT NULL COMMENT '开盘价',
      `high` decimal(10,2) DEFAULT NULL COMMENT '最高价',
      `low` decimal(10,2) DEFAULT NULL COMMENT '最低价',
      `close` decimal(10,2) DEFAULT NULL COMMENT '收盘价',
      `pre_close` decimal(10,2) DEFAULT NULL COMMENT '昨收价【除权价，前复权】',
      `change_c` decimal(10,2) DEFAULT NULL COMMENT '涨跌额',
      `pct_chg` decimal(10,2) DEFAULT NULL COMMENT '涨跌幅 【基于除权后的昨收计算的涨跌幅：（今收-除权昨收）/除权昨收】',
      `vol` bigint DEFAULT NULL COMMENT '成交量 （手）',
      `amount` decimal(20,2) DEFAULT NULL COMMENT '成交额 （千元）',
      PRIMARY KEY (`ts_code`,`trade_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='股票日线行情数据表';
''')

# 获取A股日线行情数据（简单日线行情）
cursor.execute('''
select DATE_FORMAT(cal_date, '%Y%m%d') from stock_trade_calendar 
    where is_open = 1 
    and cal_date >= '2025-05-26' 
    and cal_date <= '2025-05-27'
    order by cal_date
''')
stock_list = cursor.fetchall()

batch_size = 5
data_list = []

for i in range(0, len(stock_list), batch_size):
    batch_stock_list = stock_list[i:i + batch_size]
    for stock in batch_stock_list:
        cal_date = stock[0]
        print(cal_date)
        data = pro.daily(trade_date=cal_date)
        data_list.append(data)

    # 合并当前批次的数据
    combined_data = pd.concat(data_list, ignore_index=True)
    time.sleep(0.1)


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