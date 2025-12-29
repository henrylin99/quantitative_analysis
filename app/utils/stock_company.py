from db_utils import DatabaseUtils
import pandas as pd

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 获取上市公司基本信息数据  交易所代码 ，SSE上交所 SZSE深交所 BSE北交所
data = pro.stock_company(exchange='SSE', fields='ts_code,exchange,chairman,manager,secretary,reg_capital,setup_date,province')

# 确保数据中包含所有需要的字段
expected_fields = ['ts_code', 'exchange', 'chairman', 'manager', 'secretary', 'reg_capital', 'setup_date', 'province']

# 创建表
cursor.execute('''
CREATE TABLE IF NOT EXISTS stock_company (
  ts_code varchar(20) NOT NULL COMMENT 'TS股票代码',
  exchange varchar(100) DEFAULT NULL COMMENT '交易所代码',
  chairman varchar(100) DEFAULT NULL COMMENT '法人代表',
  manager varchar(100) DEFAULT NULL COMMENT '总经理',
  secretary varchar(100) DEFAULT NULL COMMENT '董秘',
  reg_capital varchar(100) DEFAULT NULL COMMENT '注册资本',
  setup_date varchar(100) DEFAULT NULL COMMENT '成立日期',
  province varchar(100) DEFAULT NULL COMMENT '所在省份',
  PRIMARY KEY (ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='上市公司基本信息';
''')

cursor.execute('''truncate table stock_company;''')

conn.commit()

# 准备批量插入的数据
insert_data = [
    tuple(row) for index, row in data.iterrows()
]

# 批量插入数据
cursor.executemany('''
REPLACE INTO stock_company (ts_code, exchange, chairman, manager, secretary, reg_capital, setup_date, province)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
''', insert_data)
conn.commit()

# 关闭数据库连接
cursor.close()
conn.close()
