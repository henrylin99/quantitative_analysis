#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多因子模型系统初始化脚本
"""

from app import create_app
from app.extensions import db
from app.models import (
    FactorDefinition, FactorValues, MLModelDefinition, MLPredictions,
    StockBasic
)
from datetime import datetime
import json

def init_database():
    """初始化数据库表"""
    app = create_app()
    with app.app_context():
        try:
            # 创建表
            db.create_all()
            print("✅ 数据库表创建成功")
            
            # 检查现有因子定义
            existing_count = FactorDefinition.query.count()
            print(f"📊 现有因子定义数量: {existing_count}")
            
            if existing_count == 0:
                init_builtin_factors()
            
            return True
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")
            return False

def init_builtin_factors():
    """初始化内置因子定义"""
    builtin_factors = [
        # 技术面因子
        {
            'factor_id': 'momentum_1d',
            'factor_name': '1日动量',
            'factor_formula': '(close - pre_close) / pre_close',
            'factor_type': 'technical',
            'description': '1日价格动量，反映短期价格变化',
            'params': {'period': 1}
        },
        {
            'factor_id': 'momentum_5d',
            'factor_name': '5日动量',
            'factor_formula': '(close - close_5d_ago) / close_5d_ago',
            'factor_type': 'technical',
            'description': '5日价格动量，反映短期趋势',
            'params': {'period': 5}
        },
        {
            'factor_id': 'momentum_20d',
            'factor_name': '20日动量',
            'factor_formula': '(close - close_20d_ago) / close_20d_ago',
            'factor_type': 'technical',
            'description': '20日价格动量，反映中期趋势',
            'params': {'period': 20}
        },
        {
            'factor_id': 'volatility_20d',
            'factor_name': '20日波动率',
            'factor_formula': 'std(pct_change, 20)',
            'factor_type': 'technical',
            'description': '20日收益率标准差，反映价格波动性',
            'params': {'period': 20}
        },
        {
            'factor_id': 'volume_ratio_20d',
            'factor_name': '20日量比',
            'factor_formula': 'volume / mean(volume, 20)',
            'factor_type': 'technical',
            'description': '当日成交量与20日均量的比值',
            'params': {'period': 20}
        },
        {
            'factor_id': 'price_to_ma20',
            'factor_name': '价格相对20日均线',
            'factor_formula': '(close - ma20) / ma20',
            'factor_type': 'technical',
            'description': '当前价格相对20日移动平均线的偏离度',
            'params': {'period': 20}
        },
        
        # 基本面因子
        {
            'factor_id': 'pe_percentile',
            'factor_name': 'PE历史分位数',
            'factor_formula': 'percentile_rank(pe, 252)',
            'factor_type': 'fundamental',
            'description': 'PE在过去一年中的历史分位数',
            'params': {'period': 252}
        },
        {
            'factor_id': 'pb_percentile',
            'factor_name': 'PB历史分位数',
            'factor_formula': 'percentile_rank(pb, 252)',
            'factor_type': 'fundamental',
            'description': 'PB在过去一年中的历史分位数',
            'params': {'period': 252}
        },
        {
            'factor_id': 'ps_percentile',
            'factor_name': 'PS历史分位数',
            'factor_formula': 'percentile_rank(ps, 252)',
            'factor_type': 'fundamental',
            'description': 'PS在过去一年中的历史分位数',
            'params': {'period': 252}
        },
        {
            'factor_id': 'roe_ttm',
            'factor_name': 'ROE(TTM)',
            'factor_formula': 'net_profit_ttm / total_equity',
            'factor_type': 'fundamental',
            'description': '净资产收益率(滚动12个月)',
            'params': {}
        },
        {
            'factor_id': 'roa_ttm',
            'factor_name': 'ROA(TTM)',
            'factor_formula': 'net_profit_ttm / total_assets',
            'factor_type': 'fundamental',
            'description': '总资产收益率(滚动12个月)',
            'params': {}
        },
        {
            'factor_id': 'revenue_growth',
            'factor_name': '营收增长率',
            'factor_formula': '(revenue_ttm - revenue_ttm_1y_ago) / revenue_ttm_1y_ago',
            'factor_type': 'fundamental',
            'description': '营业收入同比增长率',
            'params': {}
        },
        {
            'factor_id': 'profit_growth',
            'factor_name': '利润增长率',
            'factor_formula': '(net_profit_ttm - net_profit_ttm_1y_ago) / net_profit_ttm_1y_ago',
            'factor_type': 'fundamental',
            'description': '净利润同比增长率',
            'params': {}
        },
        
        # 资金面因子
        {
            'factor_id': 'money_flow_strength',
            'factor_name': '资金流向强度',
            'factor_formula': 'net_mf_amount / total_mv',
            'factor_type': 'money_flow',
            'description': '净流入金额相对市值的比例',
            'params': {}
        },
        {
            'factor_id': 'big_order_ratio',
            'factor_name': '大单占比',
            'factor_formula': '(buy_lg_amount + sell_lg_amount) / (buy_lg_amount + buy_md_amount + buy_sm_amount + sell_lg_amount + sell_md_amount + sell_sm_amount)',
            'factor_type': 'money_flow',
            'description': '大单交易金额占总交易金额的比例',
            'params': {}
        },
        {
            'factor_id': 'money_flow_momentum',
            'factor_name': '资金流向动量',
            'factor_formula': 'mean(net_mf_amount, 5) / std(net_mf_amount, 20)',
            'factor_type': 'money_flow',
            'description': '5日平均净流入相对20日波动的比值',
            'params': {'short_period': 5, 'long_period': 20}
        },
        
        # 筹码面因子
        {
            'factor_id': 'chip_concentration',
            'factor_name': '筹码集中度',
            'factor_formula': '(cost_95pct - cost_5pct) / cost_50pct',
            'factor_type': 'chip',
            'description': '筹码分布的集中程度',
            'params': {}
        },
        {
            'factor_id': 'winner_rate_change',
            'factor_name': '胜率变化',
            'factor_formula': 'winner_rate - winner_rate_5d_ago',
            'factor_type': 'chip',
            'description': '当前胜率相对5日前的变化',
            'params': {'period': 5}
        }
    ]
    
    try:
        for factor_data in builtin_factors:
            # 检查是否已存在
            existing = FactorDefinition.query.filter_by(factor_id=factor_data['factor_id']).first()
            if not existing:
                factor = FactorDefinition(
                    factor_id=factor_data['factor_id'],
                    factor_name=factor_data['factor_name'],
                    factor_formula=factor_data['factor_formula'],
                    factor_type=factor_data['factor_type'],
                    description=factor_data['description'],
                    params=factor_data['params'],
                    is_active=True
                )
                db.session.add(factor)
        
        db.session.commit()
        print(f"✅ 成功初始化 {len(builtin_factors)} 个内置因子定义")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ 初始化内置因子失败: {e}")

def check_data_availability():
    """检查数据可用性"""
    app = create_app()
    with app.app_context():
        try:
            # 检查股票基础数据
            stock_count = StockBasic.query.count()
            print(f"📈 股票基础数据: {stock_count} 只股票")
            
            # 检查各类数据表的数据量
            from app.models import (
                StockDailyHistory, StockDailyBasic, StockFactor,
                StockMoneyflow, StockCyqPerf
            )
            
            history_count = StockDailyHistory.query.count()
            basic_count = StockDailyBasic.query.count()
            factor_count = StockFactor.query.count()
            money_count = StockMoneyflow.query.count()
            cyq_count = StockCyqPerf.query.count()
            
            print(f"📊 日线行情数据: {history_count:,} 条")
            print(f"📊 基本面数据: {basic_count:,} 条")
            print(f"📊 技术因子数据: {factor_count:,} 条")
            print(f"📊 资金流向数据: {money_count:,} 条")
            print(f"📊 筹码分布数据: {cyq_count:,} 条")
            
            # 检查最新数据日期
            if history_count > 0:
                latest_date = db.session.query(db.func.max(StockDailyHistory.trade_date)).scalar()
                print(f"📅 最新交易日期: {latest_date}")
            
            return True
            
        except Exception as e:
            print(f"❌ 检查数据可用性失败: {e}")
            return False

def main():
    """主函数"""
    print("🚀 开始初始化多因子模型系统...")
    
    # 1. 初始化数据库
    if not init_database():
        return
    
    # 2. 检查数据可用性
    if not check_data_availability():
        return
    
    print("\n✅ 多因子模型系统初始化完成！")
    print("\n📋 下一步操作:")
    print("1. 启动应用: python run.py")
    print("2. 访问因子管理: http://127.0.0.1:5001/ml-factor")
    print("3. 计算因子值: 在因子管理页面点击'计算因子'")
    print("4. 创建ML模型: 访问模型管理页面")
    print("5. 进行股票评分: 访问股票评分页面")

if __name__ == '__main__':
    main() 