#!/usr/bin/env python3
"""
Text2SQL数据库初始化脚本
创建Text2SQL相关的数据表并初始化基础数据
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models.text2sql_metadata import (
    TableMetadata, FieldMetadata, QueryTemplate, 
    QueryHistory, BusinessDictionary
)


def init_text2sql_tables():
    """初始化Text2SQL相关表"""
    print("正在创建Text2SQL相关表...")
    
    # 创建表
    db.create_all()
    
    print("Text2SQL表创建完成！")


def init_table_metadata():
    """初始化表元数据"""
    print("正在初始化表元数据...")
    
    tables_data = [
        {
            'table_name': 'stock_business',
            'table_alias': '股票业务数据',
            'description': '股票基础业务数据，包含价格、涨跌幅、成交量等信息',
            'business_domain': '股票基础'
        },
        {
            'table_name': 'stock_factor',
            'table_alias': '股票技术因子',
            'description': '股票技术指标数据，包含MACD、RSI、KDJ等技术指标',
            'business_domain': '技术面'
        },
        {
            'table_name': 'stock_moneyflow',
            'table_alias': '股票资金流向',
            'description': '股票资金流向数据，包含主力资金、大单流入流出等',
            'business_domain': '资金面'
        },
        {
            'table_name': 'stock_ma_data',
            'table_alias': '股票均线数据',
            'description': '股票移动平均线数据，包含各周期均线值',
            'business_domain': '技术面'
        },
        {
            'table_name': 'factor_values',
            'table_alias': '因子数值',
            'description': 'ML因子计算结果数据',
            'business_domain': '因子分析'
        }
    ]
    
    for table_data in tables_data:
        existing = TableMetadata.query.get(table_data['table_name'])
        if not existing:
            table_meta = TableMetadata(**table_data)
            db.session.add(table_meta)
    
    db.session.commit()
    print("表元数据初始化完成！")


def init_field_metadata():
    """初始化字段元数据"""
    print("正在初始化字段元数据...")
    
    fields_data = [
        # stock_business表字段
        {
            'table_name': 'stock_business',
            'field_name': 'ts_code',
            'field_alias': '股票代码',
            'field_type': 'string',
            'description': '股票唯一标识代码',
            'business_meaning': '用于标识具体股票的代码',
            'synonyms': ['代码', '证券代码', '股票代码']
        },
        {
            'table_name': 'stock_business',
            'field_name': 'stock_name',
            'field_alias': '股票名称',
            'field_type': 'string',
            'description': '股票中文名称',
            'business_meaning': '股票的中文简称',
            'synonyms': ['名称', '股票名称', '简称']
        },
        {
            'table_name': 'stock_business',
            'field_name': 'daily_close',
            'field_alias': '收盘价',
            'field_type': 'float',
            'description': '当日收盘价格',
            'business_meaning': '股票当日最后成交价格',
            'synonyms': ['收盘价', '收盘', '价格', 'close']
        },
        {
            'table_name': 'stock_business',
            'field_name': 'factor_pct_change',
            'field_alias': '涨跌幅',
            'field_type': 'float',
            'description': '当日涨跌幅百分比',
            'business_meaning': '相对前一交易日的价格变化百分比',
            'synonyms': ['涨跌幅', '涨幅', '跌幅', '涨跌', 'pct_change']
        },
        {
            'table_name': 'stock_business',
            'field_name': 'vol',
            'field_alias': '成交量',
            'field_type': 'float',
            'description': '当日成交量',
            'business_meaning': '当日股票交易的股数',
            'synonyms': ['成交量', '量', 'volume', '交易量']
        },
        {
            'table_name': 'stock_business',
            'field_name': 'amount',
            'field_alias': '成交额',
            'field_type': 'float',
            'description': '当日成交金额',
            'business_meaning': '当日股票交易的总金额',
            'synonyms': ['成交额', '额', 'amount', '交易额']
        },
        {
            'table_name': 'stock_business',
            'field_name': 'pe_ttm',
            'field_alias': '市盈率',
            'field_type': 'float',
            'description': '滚动市盈率',
            'business_meaning': '股价与每股收益的比率',
            'synonyms': ['市盈率', 'PE', 'pe_ttm', 'P/E']
        },
        {
            'table_name': 'stock_business',
            'field_name': 'pb',
            'field_alias': '市净率',
            'field_type': 'float',
            'description': '市净率',
            'business_meaning': '股价与每股净资产的比率',
            'synonyms': ['市净率', 'PB', 'pb', 'P/B']
        },
        
        # stock_factor表字段
        {
            'table_name': 'stock_factor',
            'field_name': 'macd',
            'field_alias': 'MACD',
            'field_type': 'float',
            'description': 'MACD指标值',
            'business_meaning': '移动平均收敛发散指标',
            'synonyms': ['MACD', 'macd', 'MACD指标']
        },
        {
            'table_name': 'stock_factor',
            'field_name': 'macd_dif',
            'field_alias': 'MACD_DIF',
            'field_type': 'float',
            'description': 'MACD DIF线',
            'business_meaning': 'MACD指标的DIF线值',
            'synonyms': ['DIF', 'macd_dif', 'MACD_DIF']
        },
        {
            'table_name': 'stock_factor',
            'field_name': 'macd_dea',
            'field_alias': 'MACD_DEA',
            'field_type': 'float',
            'description': 'MACD DEA线',
            'business_meaning': 'MACD指标的DEA线值',
            'synonyms': ['DEA', 'macd_dea', 'MACD_DEA']
        },
        {
            'table_name': 'stock_factor',
            'field_name': 'rsi_6',
            'field_alias': 'RSI6',
            'field_type': 'float',
            'description': '6日RSI指标',
            'business_meaning': '6日相对强弱指标',
            'synonyms': ['RSI', 'rsi', 'RSI6', 'rsi_6']
        },
        
        # stock_moneyflow表字段
        {
            'table_name': 'stock_moneyflow',
            'field_name': 'net_mf_amount',
            'field_alias': '净流入金额',
            'field_type': 'float',
            'description': '资金净流入金额',
            'business_meaning': '主力资金净流入的金额',
            'synonyms': ['净流入', '资金净流入', 'net_mf_amount']
        },
        {
            'table_name': 'stock_moneyflow',
            'field_name': 'net_mf_vol',
            'field_alias': '净流入量',
            'field_type': 'float',
            'description': '资金净流入量',
            'business_meaning': '主力资金净流入的股数',
            'synonyms': ['净流入量', 'net_mf_vol']
        }
    ]
    
    for field_data in fields_data:
        existing = FieldMetadata.query.filter_by(
            table_name=field_data['table_name'],
            field_name=field_data['field_name']
        ).first()
        
        if not existing:
            field_meta = FieldMetadata(**field_data)
            db.session.add(field_meta)
    
    db.session.commit()
    print("字段元数据初始化完成！")


def init_query_templates():
    """初始化查询模板"""
    print("正在初始化查询模板...")
    
    templates_data = [
        {
            'template_id': 'stock_screening_by_price',
            'template_name': '按价格筛选股票',
            'intent_pattern': r'收盘价.*大于.*的股票',
            'sql_template': '''
                SELECT ts_code, stock_name, daily_close, factor_pct_change, vol
                FROM stock_business 
                WHERE daily_close > {price_threshold}
                ORDER BY daily_close DESC
                LIMIT {limit}
            ''',
            'parameters': ['price_threshold', 'limit']
        },
        {
            'template_id': 'stock_screening_by_pct_change',
            'template_name': '按涨跌幅筛选股票',
            'intent_pattern': r'涨幅.*大于.*的股票',
            'sql_template': '''
                SELECT ts_code, stock_name, daily_close, factor_pct_change, vol
                FROM stock_business 
                WHERE factor_pct_change > {pct_threshold}
                ORDER BY factor_pct_change DESC
                LIMIT {limit}
            ''',
            'parameters': ['pct_threshold', 'limit']
        },
        {
            'template_id': 'technical_indicator_macd',
            'template_name': 'MACD技术指标查询',
            'intent_pattern': r'MACD.*金叉.*股票',
            'sql_template': '''
                SELECT sb.ts_code, sb.stock_name, sf.macd_dif, sf.macd_dea, sf.macd
                FROM stock_business sb
                JOIN stock_factor sf ON sb.ts_code = sf.ts_code
                WHERE sf.macd_dif > sf.macd_dea 
                ORDER BY sf.macd DESC
                LIMIT {limit}
            ''',
            'parameters': ['limit']
        },
        {
            'template_id': 'fundamental_analysis_pe',
            'template_name': '市盈率基本面分析',
            'intent_pattern': r'市盈率.*小于.*的股票',
            'sql_template': '''
                SELECT ts_code, stock_name, daily_close, pe_ttm, pb
                FROM stock_business 
                WHERE pe_ttm > 0 AND pe_ttm < {pe_threshold}
                ORDER BY pe_ttm ASC
                LIMIT {limit}
            ''',
            'parameters': ['pe_threshold', 'limit']
        },
        {
            'template_id': 'money_flow_analysis',
            'template_name': '资金流向分析',
            'intent_pattern': r'资金.*净流入.*股票',
            'sql_template': '''
                SELECT sb.ts_code, sb.stock_name, sm.net_mf_amount, sm.net_mf_vol
                FROM stock_business sb
                JOIN stock_moneyflow sm ON sb.ts_code = sm.ts_code
                WHERE sm.net_mf_amount > 0
                ORDER BY sm.net_mf_amount DESC
                LIMIT {limit}
            ''',
            'parameters': ['limit']
        }
    ]
    
    for template_data in templates_data:
        existing = QueryTemplate.query.get(template_data['template_id'])
        if not existing:
            template = QueryTemplate(**template_data)
            db.session.add(template)
    
    db.session.commit()
    print("查询模板初始化完成！")


def init_business_dictionary():
    """初始化业务词典"""
    print("正在初始化业务词典...")
    
    dictionary_data = [
        # 股票字段词典
        {
            'category': 'stock_fields',
            'standard_term': '股票代码',
            'synonyms': ['代码', '证券代码', 'ts_code', '股票'],
            'description': '股票唯一标识',
            'mapping_field': 'ts_code',
            'mapping_table': 'stock_business'
        },
        {
            'category': 'stock_fields',
            'standard_term': '收盘价',
            'synonyms': ['收盘', '收价', 'close', '价格'],
            'description': '股票收盘价格',
            'mapping_field': 'daily_close',
            'mapping_table': 'stock_business'
        },
        {
            'category': 'stock_fields',
            'standard_term': '涨跌幅',
            'synonyms': ['涨幅', '跌幅', '涨跌', 'pct_change', '涨跌率'],
            'description': '股票涨跌幅度',
            'mapping_field': 'factor_pct_change',
            'mapping_table': 'stock_business'
        },
        {
            'category': 'stock_fields',
            'standard_term': '成交量',
            'synonyms': ['量', 'vol', 'volume', '交易量'],
            'description': '股票成交量',
            'mapping_field': 'vol',
            'mapping_table': 'stock_business'
        },
        {
            'category': 'stock_fields',
            'standard_term': '市盈率',
            'synonyms': ['PE', 'pe_ttm', 'P/E'],
            'description': '市盈率指标',
            'mapping_field': 'pe_ttm',
            'mapping_table': 'stock_business'
        },
        
        # 技术指标词典
        {
            'category': 'technical_indicators',
            'standard_term': 'MACD',
            'synonyms': ['macd', 'MACD指标', 'macd_dif', 'macd_dea'],
            'description': 'MACD技术指标',
            'mapping_field': 'macd',
            'mapping_table': 'stock_factor'
        },
        {
            'category': 'technical_indicators',
            'standard_term': 'RSI',
            'synonyms': ['rsi', 'RSI指标', 'rsi_6', 'rsi_12', 'rsi_24'],
            'description': 'RSI技术指标',
            'mapping_field': 'rsi_6',
            'mapping_table': 'stock_factor'
        },
        
        # 条件词典
        {
            'category': 'conditions',
            'standard_term': '大于',
            'synonyms': ['>', '超过', '高于', '大于等于', '>='],
            'description': '大于比较条件'
        },
        {
            'category': 'conditions',
            'standard_term': '小于',
            'synonyms': ['<', '低于', '少于', '小于等于', '<='],
            'description': '小于比较条件'
        },
        {
            'category': 'conditions',
            'standard_term': '排序',
            'synonyms': ['排名', '排序', '排列', 'order by'],
            'description': '排序操作'
        }
    ]
    
    for dict_data in dictionary_data:
        existing = BusinessDictionary.query.filter_by(
            category=dict_data['category'],
            standard_term=dict_data['standard_term']
        ).first()
        
        if not existing:
            dictionary = BusinessDictionary(**dict_data)
            db.session.add(dictionary)
    
    db.session.commit()
    print("业务词典初始化完成！")


def main():
    """主函数"""
    print("开始初始化Text2SQL数据库...")
    
    # 创建应用上下文
    app = create_app()
    
    with app.app_context():
        try:
            # 1. 创建表
            init_text2sql_tables()
            
            # 2. 初始化表元数据
            init_table_metadata()
            
            # 3. 初始化字段元数据
            init_field_metadata()
            
            # 4. 初始化查询模板
            init_query_templates()
            
            # 5. 初始化业务词典
            init_business_dictionary()
            
            print("\n✅ Text2SQL数据库初始化完成！")
            print("\n可以使用以下查询示例测试：")
            print("- 找出收盘价大于100元的股票")
            print("- 涨幅超过5%的股票有哪些")
            print("- MACD金叉的股票")
            print("- 市盈率小于20的股票排名")
            print("- 资金净流入最多的10只股票")
            
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            db.session.rollback()
            return 1
    
    return 0


if __name__ == '__main__':
    exit(main()) 