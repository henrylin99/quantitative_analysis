from db_utils import DatabaseUtils
import pandas as pd

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建表结构
cursor.execute('''
    CREATE TABLE IF NOT EXISTS `stock_moneyflow_ths` (
      `ts_code` varchar(20) NOT NULL COMMENT '股票代码',
      `trade_date` date NOT NULL COMMENT '交易日期',
      `name` varchar(50) DEFAULT NULL COMMENT '股票名称',
      `pct_change` decimal(10,2) DEFAULT NULL COMMENT '涨跌幅',
      `latest` decimal(10,2) DEFAULT NULL COMMENT '最新价',
      `net_amount` decimal(20,2) DEFAULT NULL COMMENT '净流入额',
      `net_d5_amount` decimal(20,2) DEFAULT NULL COMMENT '5日净流入额',
      `buy_lg_amount` decimal(20,2) DEFAULT NULL COMMENT '大单买入额',
      `buy_lg_amount_rate` decimal(10,2) DEFAULT NULL COMMENT '大单买入额占比',
      `buy_md_amount` decimal(20,2) DEFAULT NULL COMMENT '中单买入额',
      `buy_md_amount_rate` decimal(10,2) DEFAULT NULL COMMENT '中单买入额占比',
      `buy_sm_amount` decimal(20,2) DEFAULT NULL COMMENT '小单买入额',
      `buy_sm_amount_rate` decimal(10,2) DEFAULT NULL COMMENT '小单买入额占比',
      PRIMARY KEY (`ts_code`,`trade_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='同花顺个股资金流向数据表';
''')

cursor.execute('''truncate table stock_moneyflow_ths;''')

# 获取同花顺个股资金流向数据
data = pro.moneyflow_ths(trade_date='20250523')

if not data.empty:
    # 将数值列中的 NaN 值替换为 0
    numeric_columns = [col for col in data.columns if col not in ['ts_code', 'trade_date', 'name']]
    for col in numeric_columns:
        data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0)
    
    # 非数值列的 NaN 替换为 None
    non_numeric_columns = ['ts_code', 'trade_date', 'name']
    for col in non_numeric_columns:
        data[col] = data[col].replace({float('nan'): None, 'nan': None})
    
    # 插入数据
    for index, row in data.iterrows():
        try:
            cursor.execute('''
            INSERT INTO stock_moneyflow_ths 
            (trade_date, ts_code,  name, pct_change, latest, net_amount, 
             net_d5_amount, buy_lg_amount, buy_lg_amount_rate, buy_md_amount, 
             buy_md_amount_rate, buy_sm_amount, buy_sm_amount_rate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            pct_change = VALUES(pct_change),
            latest = VALUES(latest),
            net_amount = VALUES(net_amount),
            net_d5_amount = VALUES(net_d5_amount),
            buy_lg_amount = VALUES(buy_lg_amount),
            buy_lg_amount_rate = VALUES(buy_lg_amount_rate),
            buy_md_amount = VALUES(buy_md_amount),
            buy_md_amount_rate = VALUES(buy_md_amount_rate),
            buy_sm_amount = VALUES(buy_sm_amount),
            buy_sm_amount_rate = VALUES(buy_sm_amount_rate);
            ''', tuple(row[col] for col in data.columns))
        except Exception as e:
            print(f"Error inserting row: {row['ts_code']}")
            print(f"Error message: {str(e)}")
            continue

    # 提交事务
    conn.commit()

# 关闭连接
cursor.close()
conn.close()
