from db_utils import DatabaseUtils

# 初始化Tushare API
pro = DatabaseUtils.init_tushare_api()

# 连接到MySQL数据库
conn, cursor = DatabaseUtils.connect_to_mysql()

# 获取交易日历数据
data = pro.trade_cal(exchange='', start_date='20240101', end_date='20251231', fields='exchange,cal_date,is_open,pretrade_date')

# 创建表
cursor.execute('''
CREATE TABLE IF NOT EXISTS stock_trade_calendar (
    exchange VARCHAR(10) COMMENT '交易所代码',
    cal_date DATE PRIMARY KEY COMMENT '日历日期',
    is_open TINYINT COMMENT '是否交易日',
    pretrade_date DATE COMMENT '上一个交易日'
)
''')

cursor.execute('''truncate table stock_trade_calendar;''')

conn.commit()

# 准备批量插入的数据
insert_data = [
    tuple(row) for index, row in data.iterrows()
]

# 批量插入数据
cursor.executemany('''
REPLACE INTO stock_trade_calendar (exchange, cal_date, is_open, pretrade_date)
VALUES (%s, %s, %s, %s)
''', insert_data)
conn.commit()

# 关闭数据库连接
cursor.close()
conn.close() 