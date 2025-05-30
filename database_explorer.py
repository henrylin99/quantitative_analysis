#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库探索和自定义因子生成工具
基于现有的股票数据库表结构，提供数据查看和因子计算功能
"""

import pymysql
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class DatabaseExplorer:
    """数据库探索器"""
    
    def __init__(self, host='localhost', user='root', password='root', 
                 database='stock_cursor', charset='utf8mb4'):
        """初始化数据库连接"""
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.connection = None
        
    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=pymysql.cursors.DictCursor
            )
            print(f"✅ 成功连接到数据库: {self.database}")
            return True
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            print("🔒 数据库连接已关闭")
    
    def show_tables(self):
        """显示所有表"""
        if not self.connection:
            if not self.connect():
                return None
                
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                
            print("\n📊 数据库表列表:")
            print("=" * 50)
            for i, table in enumerate(tables, 1):
                table_name = list(table.values())[0]
                print(f"{i:2d}. {table_name}")
            
            return [list(table.values())[0] for table in tables]
            
        except Exception as e:
            print(f"❌ 获取表列表失败: {e}")
            return None
    
    def describe_table(self, table_name):
        """查看表结构"""
        if not self.connection:
            if not self.connect():
                return None
                
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"DESCRIBE {table_name}")
                columns = cursor.fetchall()
                
                # 获取表注释
                cursor.execute(f"""
                    SELECT TABLE_COMMENT 
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = '{self.database}' 
                    AND TABLE_NAME = '{table_name}'
                """)
                table_comment = cursor.fetchone()
                
            print(f"\n📋 表结构: {table_name}")
            if table_comment and table_comment['TABLE_COMMENT']:
                print(f"📝 表说明: {table_comment['TABLE_COMMENT']}")
            print("=" * 80)
            
            df = pd.DataFrame(columns)
            print(df.to_string(index=False))
            
            return df
            
        except Exception as e:
            print(f"❌ 查看表结构失败: {e}")
            return None
    
    def get_table_sample(self, table_name, limit=5):
        """获取表的样本数据"""
        if not self.connection:
            if not self.connect():
                return None
                
        try:
            query = f"SELECT * FROM {table_name} LIMIT {limit}"
            df = pd.read_sql(query, self.connection)
            
            print(f"\n📊 表 {table_name} 样本数据 (前{limit}行):")
            print("=" * 100)
            print(df.to_string(index=False))
            
            return df
            
        except Exception as e:
            print(f"❌ 获取样本数据失败: {e}")
            return None
    
    def get_table_stats(self, table_name):
        """获取表的统计信息"""
        if not self.connection:
            if not self.connect():
                return None
                
        try:
            with self.connection.cursor() as cursor:
                # 获取行数
                cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name}")
                row_count = cursor.fetchone()['row_count']
                
                # 获取表大小
                cursor.execute(f"""
                    SELECT 
                        ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
                    FROM information_schema.tables 
                    WHERE table_schema = '{self.database}' 
                    AND table_name = '{table_name}'
                """)
                size_info = cursor.fetchone()
                
            print(f"\n📈 表 {table_name} 统计信息:")
            print("=" * 40)
            print(f"📊 总行数: {row_count:,}")
            print(f"💾 表大小: {size_info['size_mb']} MB")
            
            return {
                'row_count': row_count,
                'size_mb': size_info['size_mb']
            }
            
        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return None

class CustomFactorGenerator:
    """自定义因子生成器"""
    
    def __init__(self, db_explorer):
        """初始化因子生成器"""
        self.db = db_explorer
        
    def calculate_price_momentum_factors(self, ts_code=None, start_date=None, end_date=None):
        """计算价格动量因子"""
        print("\n🚀 计算价格动量因子...")
        
        # 构建查询条件
        where_conditions = []
        if ts_code:
            where_conditions.append(f"ts_code = '{ts_code}'")
        if start_date:
            where_conditions.append(f"trade_date >= '{start_date}'")
        if end_date:
            where_conditions.append(f"trade_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            ts_code,
            trade_date,
            close,
            pre_close,
            pct_chg,
            vol,
            amount,
            -- 动量因子
            LAG(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) as close_5d_ago,
            LAG(close, 10) OVER (PARTITION BY ts_code ORDER BY trade_date) as close_10d_ago,
            LAG(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date) as close_20d_ago,
            LAG(close, 60) OVER (PARTITION BY ts_code ORDER BY trade_date) as close_60d_ago,
            
            -- 成交量动量
            AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as vol_ma5,
            AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as vol_ma20,
            
            -- 价格波动率
            STDDEV(pct_chg) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as volatility_20d
            
        FROM stock_daily_history 
        WHERE {where_clause}
        ORDER BY ts_code, trade_date
        """
        
        try:
            df = pd.read_sql(query, self.db.connection)
            
            # 计算动量因子
            df['momentum_5d'] = (df['close'] / df['close_5d_ago'] - 1) * 100
            df['momentum_10d'] = (df['close'] / df['close_10d_ago'] - 1) * 100
            df['momentum_20d'] = (df['close'] / df['close_20d_ago'] - 1) * 100
            df['momentum_60d'] = (df['close'] / df['close_60d_ago'] - 1) * 100
            
            # 成交量比率
            df['volume_ratio'] = df['vol'] / df['vol_ma20']
            
            # 相对强弱指标
            df['rsi_momentum'] = df['momentum_20d'] / df['volatility_20d']
            
            print(f"✅ 成功计算 {len(df)} 条动量因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算动量因子失败: {e}")
            return None
    
    def calculate_fundamental_factors(self, ts_code=None, end_date=None):
        """计算基本面因子"""
        print("\n📊 计算基本面因子...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"i.ts_code = '{ts_code}'")
        if end_date:
            where_conditions.append(f"i.end_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            i.ts_code,
            i.end_date,
            i.total_revenue,
            i.revenue,
            i.n_income,
            i.n_income_attr_p,
            i.basic_eps,
            i.operate_profit,
            i.total_profit,
            
            b.total_assets,
            b.total_liab,
            b.total_hldr_eqy_inc_min_int as total_equity,
            b.money_cap,
            b.accounts_receiv,
            b.inventories,
            b.fix_assets,
            
            c.n_cashflow_act as operating_cashflow,
            c.n_cashflow_inv_act as investing_cashflow,
            c.n_cash_flows_fnc_act as financing_cashflow,
            c.free_cashflow,
            
            -- 计算财务比率
            CASE WHEN b.total_assets > 0 THEN i.n_income_attr_p / b.total_assets * 100 ELSE NULL END as roa,
            CASE WHEN b.total_hldr_eqy_inc_min_int > 0 THEN i.n_income_attr_p / b.total_hldr_eqy_inc_min_int * 100 ELSE NULL END as roe,
            CASE WHEN b.total_assets > 0 THEN b.total_liab / b.total_assets * 100 ELSE NULL END as debt_ratio,
            CASE WHEN i.revenue > 0 THEN i.n_income_attr_p / i.revenue * 100 ELSE NULL END as net_margin
            
        FROM stock_income_statement i
        LEFT JOIN stock_balance_sheet b ON i.ts_code = b.ts_code AND i.end_date = b.end_date
        LEFT JOIN stock_cash_flow c ON i.ts_code = c.ts_code AND i.end_date = c.end_date
        WHERE {where_clause}
        ORDER BY i.ts_code, i.end_date
        """
        
        try:
            df = pd.read_sql(query, self.db.connection)
            
            # 计算增长率因子
            df = df.sort_values(['ts_code', 'end_date'])
            df['revenue_growth'] = df.groupby('ts_code')['revenue'].pct_change(4) * 100  # 同比增长
            df['profit_growth'] = df.groupby('ts_code')['n_income_attr_p'].pct_change(4) * 100
            df['asset_growth'] = df.groupby('ts_code')['total_assets'].pct_change(4) * 100
            
            # 计算资产周转率
            df['asset_turnover'] = df['revenue'] / df['total_assets']
            
            # 计算现金流质量
            df['cashflow_quality'] = df['operating_cashflow'] / df['n_income_attr_p']
            
            print(f"✅ 成功计算 {len(df)} 条基本面因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算基本面因子失败: {e}")
            return None
    
    def calculate_technical_factors(self, ts_code=None, start_date=None, end_date=None):
        """计算技术面因子"""
        print("\n📈 计算技术面因子...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"ts_code = '{ts_code}'")
        if start_date:
            where_conditions.append(f"trade_date >= '{start_date}'")
        if end_date:
            where_conditions.append(f"trade_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            ts_code,
            trade_date,
            close,
            high,
            low,
            vol,
            macd_dif,
            macd_dea,
            macd,
            kdj_k,
            kdj_d,
            kdj_j,
            rsi_6,
            rsi_12,
            rsi_24,
            boll_upper,
            boll_mid,
            boll_lower,
            cci
        FROM stock_factor 
        WHERE {where_clause}
        ORDER BY ts_code, trade_date
        """
        
        try:
            df = pd.read_sql(query, self.db.connection)
            
            # 计算布林带位置
            df['boll_position'] = (df['close'] - df['boll_lower']) / (df['boll_upper'] - df['boll_lower'])
            
            # 计算MACD信号强度
            df['macd_signal_strength'] = abs(df['macd_dif'] - df['macd_dea'])
            
            # 计算KDJ超买超卖信号
            df['kdj_overbought'] = (df['kdj_k'] > 80) & (df['kdj_d'] > 80)
            df['kdj_oversold'] = (df['kdj_k'] < 20) & (df['kdj_d'] < 20)
            
            # 计算RSI综合信号
            df['rsi_divergence'] = df['rsi_6'] - df['rsi_24']
            
            # 计算技术指标一致性
            conditions = [
                df['macd'] > 0,
                df['kdj_k'] > 50,
                df['rsi_12'] > 50,
                df['boll_position'] > 0.5
            ]
            df['technical_consensus'] = sum(conditions)
            
            print(f"✅ 成功计算 {len(df)} 条技术面因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算技术面因子失败: {e}")
            return None
    
    def calculate_market_microstructure_factors(self, ts_code=None, start_date=None, end_date=None):
        """计算市场微观结构因子"""
        print("\n🔬 计算市场微观结构因子...")
        
        where_conditions = []
        if ts_code:
            where_conditions.append(f"m.ts_code = '{ts_code}'")
        if start_date:
            where_conditions.append(f"m.trade_date >= '{start_date}'")
        if end_date:
            where_conditions.append(f"m.trade_date <= '{end_date}'")
            
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            m.ts_code,
            m.trade_date,
            m.buy_sm_amount,
            m.sell_sm_amount,
            m.buy_md_amount,
            m.sell_md_amount,
            m.buy_lg_amount,
            m.sell_lg_amount,
            m.buy_elg_amount,
            m.sell_elg_amount,
            m.net_mf_amount,
            
            d.turnover_rate,
            d.volume_ratio,
            d.pe,
            d.pb,
            d.total_mv,
            d.circ_mv
            
        FROM stock_moneyflow m
        LEFT JOIN stock_daily_basic d ON m.ts_code = d.ts_code AND m.trade_date = d.trade_date
        WHERE {where_clause}
        ORDER BY m.ts_code, m.trade_date
        """
        
        try:
            df = pd.read_sql(query, self.db.connection)
            
            # 计算资金流向因子
            df['total_buy'] = df['buy_sm_amount'] + df['buy_md_amount'] + df['buy_lg_amount'] + df['buy_elg_amount']
            df['total_sell'] = df['sell_sm_amount'] + df['sell_md_amount'] + df['sell_lg_amount'] + df['sell_elg_amount']
            
            # 大单净流入比例
            df['large_order_ratio'] = (df['buy_lg_amount'] + df['buy_elg_amount'] - df['sell_lg_amount'] - df['sell_elg_amount']) / df['total_mv']
            
            # 主力资金净流入强度
            df['main_force_intensity'] = df['net_mf_amount'] / df['circ_mv']
            
            # 散户资金比例
            df['retail_ratio'] = (df['buy_sm_amount'] - df['sell_sm_amount']) / df['total_buy']
            
            # 资金流向一致性
            df['money_flow_consistency'] = (
                (df['buy_lg_amount'] > df['sell_lg_amount']).astype(int) +
                (df['buy_md_amount'] > df['sell_md_amount']).astype(int) +
                (df['net_mf_amount'] > 0).astype(int)
            )
            
            print(f"✅ 成功计算 {len(df)} 条市场微观结构因子数据")
            return df
            
        except Exception as e:
            print(f"❌ 计算市场微观结构因子失败: {e}")
            return None
    
    def save_custom_factors(self, factor_data, factor_type, factor_name):
        """保存自定义因子到数据库"""
        print(f"\n💾 保存自定义因子: {factor_name}")
        
        try:
            # 首先在factor_definition表中定义因子
            factor_id = f"{factor_type}_{factor_name}_{datetime.now().strftime('%Y%m%d')}"
            
            with self.db.connection.cursor() as cursor:
                # 插入因子定义
                insert_definition = """
                INSERT INTO factor_definition 
                (factor_id, factor_name, factor_formula, factor_type, description, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                factor_name = VALUES(factor_name),
                factor_formula = VALUES(factor_formula),
                description = VALUES(description),
                updated_at = CURRENT_TIMESTAMP
                """
                
                cursor.execute(insert_definition, (
                    factor_id,
                    factor_name,
                    f"Custom {factor_type} factor calculation",
                    factor_type,
                    f"自定义{factor_type}因子: {factor_name}",
                    1
                ))
                
                # 保存因子值（这里需要根据具体的factor_data结构来调整）
                # 假设factor_data包含ts_code, trade_date和因子值列
                if 'ts_code' in factor_data.columns and 'trade_date' in factor_data.columns:
                    for _, row in factor_data.iterrows():
                        # 这里可以选择保存哪些计算出的因子值
                        # 示例：保存第一个数值型列作为因子值
                        numeric_cols = factor_data.select_dtypes(include=[np.number]).columns
                        if len(numeric_cols) > 0:
                            factor_value = row[numeric_cols[0]]
                            
                            insert_value = """
                            INSERT INTO factor_values 
                            (ts_code, trade_date, factor_id, factor_value)
                            VALUES (%s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            factor_value = VALUES(factor_value)
                            """
                            
                            cursor.execute(insert_value, (
                                row['ts_code'],
                                row['trade_date'],
                                factor_id,
                                float(factor_value) if pd.notna(factor_value) else None
                            ))
                
                self.db.connection.commit()
                print(f"✅ 成功保存因子: {factor_id}")
                
        except Exception as e:
            print(f"❌ 保存因子失败: {e}")
            self.db.connection.rollback()

def main():
    """主函数 - 演示数据库探索和因子计算功能"""
    print("🚀 股票数据库探索和自定义因子生成工具")
    print("=" * 60)
    
    # 初始化数据库探索器
    db_explorer = DatabaseExplorer()
    
    if not db_explorer.connect():
        return
    
    try:
        # 1. 显示所有表
        tables = db_explorer.show_tables()
        
        # 2. 查看几个重要表的结构
        important_tables = ['stock_basic', 'stock_daily_history', 'stock_factor', 'stock_moneyflow']
        
        for table in important_tables:
            if table in tables:
                print(f"\n{'='*20} {table} {'='*20}")
                db_explorer.describe_table(table)
                db_explorer.get_table_stats(table)
                db_explorer.get_table_sample(table, 3)
        
        # 3. 初始化因子生成器
        factor_generator = CustomFactorGenerator(db_explorer)
        
        # 4. 计算各类自定义因子
        print("\n" + "="*60)
        print("🧮 开始计算自定义因子")
        print("="*60)
        
        # 选择一个股票进行演示
        sample_stock = "000001.SZ"  # 平安银行
        end_date = "2024-01-31"
        start_date = "2023-01-01"
        
        # 计算动量因子
        momentum_factors = factor_generator.calculate_price_momentum_factors(
            ts_code=sample_stock, 
            start_date=start_date, 
            end_date=end_date
        )
        
        if momentum_factors is not None and not momentum_factors.empty:
            print("\n📊 动量因子样本:")
            print(momentum_factors[['ts_code', 'trade_date', 'momentum_5d', 'momentum_20d', 'volume_ratio']].tail())
        
        # 计算基本面因子
        fundamental_factors = factor_generator.calculate_fundamental_factors(
            ts_code=sample_stock,
            end_date=end_date
        )
        
        if fundamental_factors is not None and not fundamental_factors.empty:
            print("\n📊 基本面因子样本:")
            print(fundamental_factors[['ts_code', 'end_date', 'roa', 'roe', 'revenue_growth', 'profit_growth']].tail())
        
        # 计算技术面因子
        technical_factors = factor_generator.calculate_technical_factors(
            ts_code=sample_stock,
            start_date=start_date,
            end_date=end_date
        )
        
        if technical_factors is not None and not technical_factors.empty:
            print("\n📊 技术面因子样本:")
            print(technical_factors[['ts_code', 'trade_date', 'boll_position', 'macd_signal_strength', 'technical_consensus']].tail())
        
        # 计算市场微观结构因子
        microstructure_factors = factor_generator.calculate_market_microstructure_factors(
            ts_code=sample_stock,
            start_date=start_date,
            end_date=end_date
        )
        
        if microstructure_factors is not None and not microstructure_factors.empty:
            print("\n📊 市场微观结构因子样本:")
            print(microstructure_factors[['ts_code', 'trade_date', 'large_order_ratio', 'main_force_intensity', 'money_flow_consistency']].tail())
        
        print("\n✅ 数据库探索和因子计算完成!")
        print("\n💡 提示:")
        print("1. 可以修改 sample_stock 变量来分析不同股票")
        print("2. 可以调整日期范围来获取不同时期的数据")
        print("3. 可以在各个因子计算函数中添加更多自定义因子")
        print("4. 使用 save_custom_factors() 方法可以将计算结果保存到数据库")
        
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")
        
    finally:
        db_explorer.close()

if __name__ == "__main__":
    main() 