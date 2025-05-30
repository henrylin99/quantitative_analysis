#!/usr/bin/env python3
"""
交易信号数据库表初始化脚本
创建trading_signals表用于存储实时交易信号
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.trading_signal import TradingSignal

def init_trading_signals_table():
    """初始化交易信号表"""
    app = create_app()
    
    with app.app_context():
        try:
            # 创建表
            db.create_all()
            print("✅ 交易信号表创建成功")
            
            # 验证表结构
            inspector = db.inspect(db.engine)
            if 'trading_signals' in inspector.get_table_names():
                print("✅ trading_signals表已存在")
                
                # 获取表的列信息
                columns = inspector.get_columns('trading_signals')
                print(f"📊 表结构信息:")
                for col in columns:
                    print(f"   - {col['name']}: {col['type']}")
                
                # 获取索引信息
                indexes = inspector.get_indexes('trading_signals')
                print(f"🔍 索引信息:")
                for idx in indexes:
                    print(f"   - {idx['name']}: {idx['column_names']}")
                
                print(f"✅ 交易信号表初始化完成")
                return True
            else:
                print("❌ trading_signals表创建失败")
                return False
                
        except Exception as e:
            print(f"❌ 初始化失败: {str(e)}")
            return False

if __name__ == '__main__':
    print("🚀 开始初始化交易信号数据库表...")
    success = init_trading_signals_table()
    
    if success:
        print("\n🎉 交易信号表初始化成功！")
        print("现在可以使用以下功能:")
        print("- 生成交易信号")
        print("- 信号融合分析")
        print("- 信号监控管理")
        print("- 策略回测验证")
    else:
        print("\n💥 交易信号表初始化失败！")
        sys.exit(1) 