#!/usr/bin/env python3
"""
实时技术指标数据库初始化脚本
创建技术指标相关的数据表
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.realtime_indicator import RealtimeIndicator

def init_realtime_indicators_db():
    """初始化实时技术指标数据库"""
    app = create_app()
    
    with app.app_context():
        try:
            print("🚀 开始初始化实时技术指标数据库...")
            
            # 创建技术指标表
            print("📊 创建技术指标数据表...")
            db.create_all()
            
            # 验证表是否创建成功
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'realtime_indicators' in tables:
                print("✅ 技术指标数据表创建成功")
                
                # 显示表结构
                columns = inspector.get_columns('realtime_indicators')
                print("\n📋 技术指标表结构:")
                for col in columns:
                    print(f"  - {col['name']}: {col['type']}")
                
                # 显示索引信息
                indexes = inspector.get_indexes('realtime_indicators')
                if indexes:
                    print("\n🔍 表索引:")
                    for idx in indexes:
                        print(f"  - {idx['name']}: {idx['column_names']}")
                
            else:
                print("❌ 技术指标数据表创建失败")
                return False
            
            print("\n🎉 实时技术指标数据库初始化完成!")
            print("\n📝 使用说明:")
            print("1. 运行 python test_realtime_indicators.py 进行功能测试")
            print("2. 访问 http://127.0.0.1:5001/realtime-analysis/indicators 查看前端界面")
            print("3. 使用 API 接口进行技术指标计算和查询")
            
            return True
            
        except Exception as e:
            print(f"❌ 初始化过程中发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    success = init_realtime_indicators_db()
    sys.exit(0 if success else 1) 