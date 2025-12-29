from db_utils import DatabaseUtils
import pandas as pd

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 创建表结构（复杂日线行情）
cursor.execute('''
CREATE TABLE IF NOT EXISTS stock_daily_basic (
  ts_code varchar(20) NOT NULL COMMENT 'TS股票代码',
  trade_date date NOT NULL COMMENT '交易日期',
  close decimal(10,2) DEFAULT NULL COMMENT '当日收盘价',
  turnover_rate decimal(10,2) DEFAULT NULL COMMENT '换手率（%）',
  turnover_rate_f decimal(10,2) DEFAULT NULL COMMENT '换手率（自由流通股）',
  volume_ratio decimal(10,2) DEFAULT NULL COMMENT '量比',
  pe decimal(10,2) DEFAULT NULL COMMENT '市盈率（总市值/净利润， 亏损的PE为空）',
  pe_ttm decimal(10,2) DEFAULT NULL COMMENT '市盈率（TTM，亏损的PE为空）',
  pb decimal(10,2) DEFAULT NULL COMMENT '市净率（总市值/净资产）',
  ps decimal(10,2) DEFAULT NULL COMMENT '市销率',
  ps_ttm decimal(10,2) DEFAULT NULL COMMENT '市销率（TTM）',
  dv_ratio decimal(10,2) DEFAULT NULL COMMENT '股息率 （%）',
  dv_ttm decimal(10,2) DEFAULT NULL COMMENT '股息率（TTM）（%）',
  total_share decimal(20,2) DEFAULT NULL COMMENT '总股本 （万股）',
  float_share decimal(20,2) DEFAULT NULL COMMENT '流通股本 （万股）',
  free_share decimal(20,2) DEFAULT NULL COMMENT '自由流通股本 （万）',
  total_mv decimal(20,2) DEFAULT NULL COMMENT '总市值 （万元）',
  circ_mv decimal(20,2) DEFAULT NULL COMMENT '流通市值（万元）',
  PRIMARY KEY (ts_code,trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='股票日线基本数据表';
''')

cursor.execute('''truncate table stock_daily_basic;''')

conn.commit()

# 一次性获取所有股票的日线基本面数据
df = pro.daily_basic(trade_date='20250523', fields=[
    "ts_code", "trade_date", "close", "turnover_rate",
    "turnover_rate_f", "volume_ratio", "pe", "pe_ttm",
    "pb", "ps", "ps_ttm", "dv_ratio", "dv_ttm",
    "total_share", "float_share", "free_share", "total_mv",
    "circ_mv"
])

# 将NaN值替换为None（这会在MySQL中转换为NULL）
df = df.replace({pd.NA: None, float('nan'): None})

# 将DataFrame转换为元组列表用于数据库插入
insert_data = [tuple(row) for row in df.values]

# 插入数据到数据库
cursor.executemany('''
INSERT INTO stock_daily_basic (ts_code, trade_date, close, turnover_rate, turnover_rate_f, volume_ratio, pe,
                                pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm, total_share, float_share,
                                free_share, total_mv, circ_mv)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
''', insert_data)

# 提交事务
conn.commit()

# 关闭连接
cursor.close()
conn.close()