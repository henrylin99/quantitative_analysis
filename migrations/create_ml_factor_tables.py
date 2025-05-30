"""
创建多因子选股和机器学习相关表的迁移脚本
"""

from app import create_app
from app.extensions import db
from app.models import (
    FactorDefinition, FactorValues, MLModelDefinition, MLPredictions,
    StockIncomeStatement, StockBalanceSheet
)

def create_tables():
    """创建表"""
    app = create_app()
    
    with app.app_context():
        try:
            # 创建因子相关表
            print("创建因子定义表...")
            FactorDefinition.__table__.create(db.engine, checkfirst=True)
            
            print("创建因子值表...")
            FactorValues.__table__.create(db.engine, checkfirst=True)
            
            # 创建机器学习相关表
            print("创建ML模型定义表...")
            MLModelDefinition.__table__.create(db.engine, checkfirst=True)
            
            print("创建ML预测结果表...")
            MLPredictions.__table__.create(db.engine, checkfirst=True)
            
            # 创建财务数据表
            print("创建利润表...")
            StockIncomeStatement.__table__.create(db.engine, checkfirst=True)
            
            print("创建资产负债表...")
            StockBalanceSheet.__table__.create(db.engine, checkfirst=True)
            
            print("所有表创建完成！")
            
        except Exception as e:
            print(f"创建表失败: {e}")

def drop_tables():
    """删除表"""
    app = create_app()
    
    with app.app_context():
        try:
            # 删除表（注意顺序，先删除有外键依赖的表）
            print("删除ML预测结果表...")
            MLPredictions.__table__.drop(db.engine, checkfirst=True)
            
            print("删除因子值表...")
            FactorValues.__table__.drop(db.engine, checkfirst=True)
            
            print("删除ML模型定义表...")
            MLModelDefinition.__table__.drop(db.engine, checkfirst=True)
            
            print("删除因子定义表...")
            FactorDefinition.__table__.drop(db.engine, checkfirst=True)
            
            print("删除财务数据表...")
            StockIncomeStatement.__table__.drop(db.engine, checkfirst=True)
            StockBalanceSheet.__table__.drop(db.engine, checkfirst=True)
            
            print("所有表删除完成！")
            
        except Exception as e:
            print(f"删除表失败: {e}")

def init_factor_definitions():
    """初始化内置因子定义"""
    app = create_app()
    
    with app.app_context():
        try:
            # 内置因子定义
            builtin_factors = [
                {
                    'factor_id': 'momentum_1d',
                    'factor_name': '1日动量',
                    'factor_formula': 'close.pct_change(1)',
                    'factor_type': 'momentum',
                    'description': '1日价格变化率',
                    'params': {'period': 1}
                },
                {
                    'factor_id': 'momentum_5d',
                    'factor_name': '5日动量',
                    'factor_formula': 'close.pct_change(5)',
                    'factor_type': 'momentum',
                    'description': '5日价格变化率',
                    'params': {'period': 5}
                },
                {
                    'factor_id': 'momentum_20d',
                    'factor_name': '20日动量',
                    'factor_formula': 'close.pct_change(20)',
                    'factor_type': 'momentum',
                    'description': '20日价格变化率',
                    'params': {'period': 20}
                },
                {
                    'factor_id': 'volatility_20d',
                    'factor_name': '20日波动率',
                    'factor_formula': 'close.pct_change().rolling(20).std()',
                    'factor_type': 'volatility',
                    'description': '20日收益率标准差',
                    'params': {'period': 20}
                },
                {
                    'factor_id': 'rsi_14d',
                    'factor_name': '14日RSI',
                    'factor_formula': 'RSI(close, 14)',
                    'factor_type': 'technical',
                    'description': '14日相对强弱指标',
                    'params': {'period': 14}
                },
                {
                    'factor_id': 'ma_ratio_5_20',
                    'factor_name': '5日/20日均线比',
                    'factor_formula': 'close.rolling(5).mean() / close.rolling(20).mean() - 1',
                    'factor_type': 'technical',
                    'description': '5日均线相对20日均线的比率',
                    'params': {'short_period': 5, 'long_period': 20}
                },
                {
                    'factor_id': 'turnover_rate_20d',
                    'factor_name': '20日平均换手率',
                    'factor_formula': 'turnover_rate.rolling(20).mean()',
                    'factor_type': 'volume',
                    'description': '20日平均换手率',
                    'params': {'period': 20}
                },
                {
                    'factor_id': 'volume_ratio_5_20',
                    'factor_name': '5日/20日成交量比',
                    'factor_formula': 'vol.rolling(5).mean() / vol.rolling(20).mean()',
                    'factor_type': 'volume',
                    'description': '5日平均成交量相对20日平均成交量的比率',
                    'params': {'short_period': 5, 'long_period': 20}
                },
                {
                    'factor_id': 'pe_ttm',
                    'factor_name': 'PE(TTM)',
                    'factor_formula': 'pe_ttm',
                    'factor_type': 'fundamental',
                    'description': '市盈率(滚动12个月)',
                    'params': {}
                },
                {
                    'factor_id': 'pb_ratio',
                    'factor_name': 'PB比率',
                    'factor_formula': 'pb',
                    'factor_type': 'fundamental',
                    'description': '市净率',
                    'params': {}
                },
                {
                    'factor_id': 'roe_ttm',
                    'factor_name': 'ROE(TTM)',
                    'factor_formula': 'n_income_attr_p / total_hldr_eqy_exc_min_int',
                    'factor_type': 'fundamental',
                    'description': '净资产收益率(滚动12个月)',
                    'params': {}
                },
                {
                    'factor_id': 'revenue_growth_yoy',
                    'factor_name': '营收同比增长率',
                    'factor_formula': 'revenue.pct_change(4)',
                    'factor_type': 'fundamental',
                    'description': '营业收入同比增长率',
                    'params': {}
                }
            ]
            
            # 插入因子定义
            for factor_def in builtin_factors:
                existing = FactorDefinition.query.filter_by(factor_id=factor_def['factor_id']).first()
                if not existing:
                    factor = FactorDefinition(**factor_def)
                    db.session.add(factor)
                    print(f"添加因子定义: {factor_def['factor_id']}")
            
            db.session.commit()
            print("内置因子定义初始化完成！")
            
        except Exception as e:
            db.session.rollback()
            print(f"初始化因子定义失败: {e}")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python create_ml_factor_tables.py [create|drop|init]")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == 'create':
        create_tables()
    elif action == 'drop':
        drop_tables()
    elif action == 'init':
        init_factor_definitions()
    else:
        print("无效的操作，支持的操作: create, drop, init") 