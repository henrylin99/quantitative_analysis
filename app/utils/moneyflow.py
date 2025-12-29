from db_utils import DatabaseUtils
import pandas as pd
import time

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建表结构
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_moneyflow` (
      `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
      `trade_date` date NOT NULL COMMENT '交易日期',
      `buy_sm_vol` decimal(20,2) DEFAULT NULL COMMENT '小单买入量（手）',
      `buy_sm_amount` decimal(20,2) DEFAULT NULL COMMENT '小单买入金额（万元）',
      `sell_sm_vol` decimal(20,2) DEFAULT NULL COMMENT '小单卖出量（手）',
      `sell_sm_amount` decimal(20,2) DEFAULT NULL COMMENT '小单卖出金额（万元）',
      `buy_md_vol` decimal(20,2) DEFAULT NULL COMMENT '中单买入量（手）',
      `buy_md_amount` decimal(20,2) DEFAULT NULL COMMENT '中单买入金额（万元）',
      `sell_md_vol` decimal(20,2) DEFAULT NULL COMMENT '中单卖出量（手）',
      `sell_md_amount` decimal(20,2) DEFAULT NULL COMMENT '中单卖出金额（万元）',
      `buy_lg_vol` decimal(20,2) DEFAULT NULL COMMENT '大单买入量（手）',
      `buy_lg_amount` decimal(20,2) DEFAULT NULL COMMENT '大单买入金额（万元）',
      `sell_lg_vol` decimal(20,2) DEFAULT NULL COMMENT '大单卖出量（手）',
      `sell_lg_amount` decimal(20,2) DEFAULT NULL COMMENT '大单卖出金额（万元）',
      `buy_elg_vol` decimal(20,2) DEFAULT NULL COMMENT '特大单买入量（手）',
      `buy_elg_amount` decimal(20,2) DEFAULT NULL COMMENT '特大单买入金额（万元）',
      `sell_elg_vol` decimal(20,2) DEFAULT NULL COMMENT '特大单卖出量（手）',
      `sell_elg_amount` decimal(20,2) DEFAULT NULL COMMENT '特大单卖出金额（万元）',
      `net_mf_vol` decimal(20,2) DEFAULT NULL COMMENT '净流入量（手）',
      `net_mf_amount` decimal(20,2) DEFAULT NULL COMMENT '净流入额（万元）',
      PRIMARY KEY (`ts_code`,`trade_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='个股资金流向数据表';
''')

# 获取交易日列表
cursor.execute('''
select DATE_FORMAT(cal_date, '%Y%m%d') from stock_trade_calendar 
    where is_open = 1 
    and cal_date >= '2025-01-01' 
    and cal_date <= '2025-05-27'
    order by cal_date
''')
trade_dates = cursor.fetchall()

# 按日期循环获取个股资金流向数据
for trade_date_tuple in trade_dates:
    trade_date = trade_date_tuple[0]
    print(f"正在获取 {trade_date} 的个股资金流向数据...")
    
    try:
        # 获取指定日期的个股资金流向数据
        data = pro.moneyflow(trade_date=trade_date)
        
        if not data.empty:
            # 将数值列中的 NaN 值替换为 0
            numeric_columns = [col for col in data.columns if col not in ['ts_code', 'trade_date']]
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
                    INSERT INTO stock_moneyflow 
                    (ts_code, trade_date, buy_sm_vol, buy_sm_amount, sell_sm_vol, 
                     sell_sm_amount, buy_md_vol, buy_md_amount, sell_md_vol, 
                     sell_md_amount, buy_lg_vol, buy_lg_amount, sell_lg_vol, 
                     sell_lg_amount, buy_elg_vol, buy_elg_amount, sell_elg_vol, 
                     sell_elg_amount, net_mf_vol, net_mf_amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                            %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    buy_sm_vol = VALUES(buy_sm_vol),
                    buy_sm_amount = VALUES(buy_sm_amount),
                    sell_sm_vol = VALUES(sell_sm_vol),
                    sell_sm_amount = VALUES(sell_sm_amount),
                    buy_md_vol = VALUES(buy_md_vol),
                    buy_md_amount = VALUES(buy_md_amount),
                    sell_md_vol = VALUES(sell_md_vol),
                    sell_md_amount = VALUES(sell_md_amount),
                    buy_lg_vol = VALUES(buy_lg_vol),
                    buy_lg_amount = VALUES(buy_lg_amount),
                    sell_lg_vol = VALUES(sell_lg_vol),
                    sell_lg_amount = VALUES(sell_lg_amount),
                    buy_elg_vol = VALUES(buy_elg_vol),
                    buy_elg_amount = VALUES(buy_elg_amount),
                    sell_elg_vol = VALUES(sell_elg_vol),
                    sell_elg_amount = VALUES(sell_elg_amount),
                    net_mf_vol = VALUES(net_mf_vol),
                    net_mf_amount = VALUES(net_mf_amount);
                    ''', tuple(row[col] for col in data.columns))
                except Exception as e:
                    print(f"Error inserting row: {row['ts_code']}")
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
