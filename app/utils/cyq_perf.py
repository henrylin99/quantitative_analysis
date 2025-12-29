from db_utils import DatabaseUtils
import pandas as pd
import time

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建表结构
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_cyq_perf` (
      `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
      `trade_date` date NOT NULL COMMENT '交易日期',
      `his_low` decimal(10,2) DEFAULT NULL COMMENT '历史最低价',
      `his_high` decimal(10,2) DEFAULT NULL COMMENT '历史最高价',
      `cost_5pct` decimal(10,2) DEFAULT NULL COMMENT '5%成本分位',
      `cost_15pct` decimal(10,2) DEFAULT NULL COMMENT '15%成本分位',
      `cost_50pct` decimal(10,2) DEFAULT NULL COMMENT '50%成本分位',
      `cost_85pct` decimal(10,2) DEFAULT NULL COMMENT '85%成本分位',
      `cost_95pct` decimal(10,2) DEFAULT NULL COMMENT '95%成本分位',
      `weight_avg` decimal(10,2) DEFAULT NULL COMMENT '加权平均成本',
      `winner_rate` decimal(10,2) DEFAULT NULL COMMENT '胜率',
      PRIMARY KEY (`ts_code`,`trade_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='每日筹码及胜率数据表';
''')

# 获取交易日列表
cursor.execute('''
select DATE_FORMAT(cal_date, '%Y%m%d') from stock_trade_calendar 
    where is_open = 1 
    and cal_date >= '2025-05-27' 
    and cal_date <= '2025-05-27'
    order by cal_date
''')
trade_dates = cursor.fetchall()

# 按日期循环获取每日筹码及胜率数据
for trade_date_tuple in trade_dates:
    trade_date = trade_date_tuple[0]
    print(f"正在获取 {trade_date} 的筹码及胜率数据...")
    
    try:
        # 获取指定日期的筹码及胜率数据
        data = pro.cyq_perf(trade_date=trade_date,
                           fields=['ts_code', 'trade_date', 'his_low', 'his_high',
                                  'cost_5pct', 'cost_15pct', 'cost_50pct', 'cost_85pct',
                                  'cost_95pct', 'weight_avg', 'winner_rate'])
        time.sleep(15)
        if not data.empty:
            # 将数值列中的 NaN 值替换为 0
            numeric_columns = ['his_low', 'his_high', 'cost_5pct', 'cost_15pct',
                              'cost_50pct', 'cost_85pct', 'cost_95pct',
                              'weight_avg', 'winner_rate']
            for col in numeric_columns:
                data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0)
            
            # 非数值列的 NaN 替换为 None
            non_numeric_columns = ['ts_code', 'trade_date']
            for col in non_numeric_columns:
                data[col] = data[col].replace({float('nan'): None, 'nan': None})
            
            # 插入数据
            for index, row in data.iterrows():
                try:
                    cursor.execute('''
                    INSERT INTO stock_cyq_perf 
                    (ts_code, trade_date, his_low, his_high, cost_5pct, cost_15pct,
                     cost_50pct, cost_85pct, cost_95pct, weight_avg, winner_rate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    his_low = VALUES(his_low),
                    his_high = VALUES(his_high),
                    cost_5pct = VALUES(cost_5pct),
                    cost_15pct = VALUES(cost_15pct),
                    cost_50pct = VALUES(cost_50pct),
                    cost_85pct = VALUES(cost_85pct),
                    cost_95pct = VALUES(cost_95pct),
                    weight_avg = VALUES(weight_avg),
                    winner_rate = VALUES(winner_rate);
                    ''', (row['ts_code'], row['trade_date'], row['his_low'], row['his_high'],
                          row['cost_5pct'], row['cost_15pct'], row['cost_50pct'],
                          row['cost_85pct'], row['cost_95pct'], row['weight_avg'],
                          row['winner_rate']))
                except Exception as e:
                    print(f"Error inserting row: {row}")
                    print(f"Error message: {str(e)}")
                    continue

            # 提交事务
            conn.commit()
            print(f"成功处理 {trade_date} 的数据，共 {len(data)} 条记录")
        else:
            print(f"{trade_date} 没有数据")
            
    except Exception as e:
        print(f"获取 {trade_date} 数据时出错: {str(e)}")
        continue
    
    # 添加延时避免频率限制
    time.sleep(0.1)

# 关闭连接
cursor.close()
conn.close()