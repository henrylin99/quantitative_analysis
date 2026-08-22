"""AI 智能工作台服务包。

- llm_client: OpenAI 兼容的流式对话客户端（DeepSeek / Qwen / GLM / OpenAI / Ollama v1）
- tools: 大模型可调用的工具层（只读查询 + 项目已有功能动作）
- prompts: 系统提示词构建
- assistant_service: 对话编排（工具调用循环 + 会话持久化）
"""
