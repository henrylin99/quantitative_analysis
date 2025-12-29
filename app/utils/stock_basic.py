from db_utils import DatabaseUtils

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 获取股票基础信息数据
data = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')

# 创建表
cursor.execute('''
CREATE TABLE IF NOT EXISTS stock_basic (
  ts_code varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'TS代码',
  symbol varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '股票代码',
  name varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '股票名称',
  area varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '地域',
  industry varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '所属行业',
  list_date date DEFAULT NULL COMMENT '上市日期',
  PRIMARY KEY (ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='股票公司基本信息表';
''')

cursor.execute('''truncate table stock_basic;''')

conn.commit()

# 准备批量插入的数据
insert_data = [
    tuple(row) for index, row in data.iterrows()
]

# 批量插入数据
cursor.executemany('''
REPLACE INTO stock_basic (ts_code, symbol, name, area, industry, list_date)
VALUES (%s, %s, %s, %s, %s, %s)
''', insert_data)
conn.commit()

# 关闭数据库连接
cursor.close()
conn.close()
