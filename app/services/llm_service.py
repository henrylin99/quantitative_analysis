"""
大模型服务
支持本地ollama和OpenAI等多种大模型提供商
"""

import json
import requests
import logging
from typing import Dict, List, Any, Optional
from flask import current_app

logger = logging.getLogger(__name__)


class LLMService:
    """大模型服务"""
    
    def __init__(self):
        self.config = current_app.config.get('LLM_CONFIG', {})
        self.provider = self.config.get('provider', 'ollama')
    
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """聊天完成接口"""
        try:
            if self.provider == 'ollama':
                return self._ollama_chat(messages, **kwargs)
            elif self.provider == 'openai':
                return self._openai_chat(messages, **kwargs)
            else:
                raise ValueError(f"不支持的大模型提供商: {self.provider}")
        
        except Exception as e:
            logger.error(f"大模型调用失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'content': None
            }
    
    def _ollama_chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Ollama聊天接口"""
        ollama_config = self.config.get('ollama', {})
        base_url = ollama_config.get('base_url', 'http://localhost:11434')
        model = ollama_config.get('model', 'qwen2.5-coder:latest')
        
        # 构建请求数据
        data = {
            'model': model,
            'messages': messages,
            'stream': False,
            'options': {
                'temperature': kwargs.get('temperature', ollama_config.get('temperature', 0.1)),
                'num_predict': kwargs.get('max_tokens', ollama_config.get('max_tokens', 2048))
            }
        }
        
        try:
            response = requests.post(
                f"{base_url}/api/chat",
                json=data,
                timeout=ollama_config.get('timeout', 60)
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'content': result.get('message', {}).get('content', ''),
                    'model': model,
                    'usage': result.get('usage', {})
                }
            else:
                return {
                    'success': False,
                    'error': f"Ollama API错误: {response.status_code} - {response.text}",
                    'content': None
                }
        
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': "无法连接到Ollama服务，请确保Ollama正在运行",
                'content': None
            }
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': "Ollama请求超时",
                'content': None
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Ollama调用异常: {str(e)}",
                'content': None
            }
    
    def _openai_chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """OpenAI聊天接口"""
        openai_config = self.config.get('openai', {})
        api_key = openai_config.get('api_key')
        
        if not api_key:
            return {
                'success': False,
                'error': "OpenAI API密钥未配置",
                'content': None
            }
        
        base_url = openai_config.get('base_url', 'https://api.openai.com/v1')
        model = openai_config.get('model', 'gpt-3.5-turbo')
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': model,
            'messages': messages,
            'temperature': kwargs.get('temperature', openai_config.get('temperature', 0.1)),
            'max_tokens': kwargs.get('max_tokens', openai_config.get('max_tokens', 2048))
        }
        
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=openai_config.get('timeout', 60)
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'content': result['choices'][0]['message']['content'],
                    'model': model,
                    'usage': result.get('usage', {})
                }
            else:
                return {
                    'success': False,
                    'error': f"OpenAI API错误: {response.status_code} - {response.text}",
                    'content': None
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': f"OpenAI调用异常: {str(e)}",
                'content': None
            }
    
    def enhance_sql_generation(self, user_query: str, context: Dict[str, Any]) -> str:
        """使用大模型增强SQL生成"""
        try:
            # 构建提示词
            prompt = self._build_sql_prompt(user_query, context)
            
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的SQL生成助手，专门为股票分析系统生成准确的SQL查询语句。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ]
            
            result = self.chat_completion(messages, temperature=0.1)
            
            if result['success']:
                return self._extract_sql_from_response(result['content'])
            else:
                logger.error(f"大模型SQL生成失败: {result['error']}")
                return None
        
        except Exception as e:
            logger.error(f"大模型SQL增强失败: {e}")
            return None
    
    def _build_sql_prompt(self, user_query: str, context: Dict[str, Any]) -> str:
        """构建SQL生成提示词"""
        # 获取表结构信息
        tables_info = context.get('tables_info', {})
        intent = context.get('intent', {})
        entities = context.get('entities', {})
        
        prompt = f"""
请根据用户的自然语言查询生成对应的SQL语句。

用户查询: {user_query}

识别的意图: {intent.get('name', 'unknown')}
提取的实体: {json.dumps(entities, ensure_ascii=False)}

可用的数据表结构:
{self._format_tables_info(tables_info)}

要求:
1. 生成标准的MySQL SQL语句
2. 只返回SQL语句，不要其他解释
3. 确保SQL语法正确
4. 使用适当的WHERE条件和ORDER BY子句
5. 添加合理的LIMIT限制

请生成SQL语句:
"""
        return prompt
    
    def _format_tables_info(self, tables_info: Dict[str, Any]) -> str:
        """格式化表结构信息"""
        if not tables_info:
            return """
stock_business表 (股票基础数据):
- ts_code: 股票代码
- stock_name: 股票名称  
- daily_close: 收盘价
- factor_pct_change: 涨跌幅
- vol: 成交量
- amount: 成交额
- pe_ttm: 市盈率
- pb: 市净率

stock_factor表 (技术指标):
- ts_code: 股票代码
- macd: MACD指标
- macd_dif: MACD DIF线
- macd_dea: MACD DEA线
- rsi_6: RSI指标

stock_moneyflow表 (资金流向):
- ts_code: 股票代码
- net_mf_amount: 净流入金额
- net_mf_vol: 净流入量
"""
        
        formatted = ""
        for table_name, table_info in tables_info.items():
            formatted += f"\n{table_name}表:\n"
            for field_name, field_info in table_info.items():
                formatted += f"- {field_name}: {field_info.get('description', '')}\n"
        
        return formatted
    
    def _extract_sql_from_response(self, response: str) -> str:
        """从大模型响应中提取SQL语句"""
        # 移除markdown代码块标记
        response = response.strip()
        if response.startswith('```sql'):
            response = response[6:]
        elif response.startswith('```'):
            response = response[3:]
        
        if response.endswith('```'):
            response = response[:-3]
        
        # 清理和格式化SQL
        sql = response.strip()
        
        # 确保SQL以分号结尾
        if not sql.endswith(';'):
            sql += ';'
        
        return sql
    
    def check_service_status(self) -> Dict[str, Any]:
        """检查大模型服务状态"""
        if self.provider == 'ollama':
            return self._check_ollama_status()
        elif self.provider == 'openai':
            return self._check_openai_status()
        else:
            return {
                'status': 'error',
                'message': f'不支持的提供商: {self.provider}'
            }
    
    def _check_ollama_status(self) -> Dict[str, Any]:
        """检查Ollama服务状态"""
        try:
            ollama_config = self.config.get('ollama', {})
            base_url = ollama_config.get('base_url', 'http://localhost:11434')
            
            response = requests.get(f"{base_url}/api/tags", timeout=5)
            
            if response.status_code == 200:
                models = response.json().get('models', [])
                target_model = ollama_config.get('model', 'qwen2.5-coder:latest')
                
                model_available = any(model.get('name') == target_model for model in models)
                
                return {
                    'status': 'online' if model_available else 'model_not_found',
                    'message': f'Ollama服务正常，模型{"可用" if model_available else "不可用"}',
                    'models': [model.get('name') for model in models],
                    'target_model': target_model
                }
            else:
                return {
                    'status': 'error',
                    'message': f'Ollama服务响应异常: {response.status_code}'
                }
        
        except requests.exceptions.ConnectionError:
            return {
                'status': 'offline',
                'message': 'Ollama服务未启动或无法连接'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'检查Ollama状态失败: {str(e)}'
            }
    
    def _check_openai_status(self) -> Dict[str, Any]:
        """检查OpenAI服务状态"""
        openai_config = self.config.get('openai', {})
        api_key = openai_config.get('api_key')
        
        if not api_key:
            return {
                'status': 'error',
                'message': 'OpenAI API密钥未配置'
            }
        
        return {
            'status': 'configured',
            'message': 'OpenAI API已配置'
        }


# 全局LLM服务实例
_llm_service = None

def get_llm_service() -> LLMService:
    """获取LLM服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service 