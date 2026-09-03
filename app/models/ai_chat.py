"""AI 智能工作台的会话与消息持久化。"""

from app.extensions import db
from app.utils.time_utils import now_local


class AiChatSession(db.Model):
    """一次对话会话。"""

    __tablename__ = 'ai_chat_session'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(128), nullable=False, default='新对话')
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_local, onupdate=now_local)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class AiChatMessage(db.Model):
    """会话内的一条消息。

    role:
    - user: 用户输入
    - assistant: 助手的文本回复
    - tool: 一次工具调用记录（tool_name/tool_args/tool_result）
    """

    __tablename__ = 'ai_chat_message'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey('ai_chat_session.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    role = db.Column(db.String(16), nullable=False, index=True)
    content = db.Column(db.Text)
    tool_name = db.Column(db.String(64))
    tool_args = db.Column(db.JSON)
    tool_ok = db.Column(db.Boolean)
    tool_result = db.Column(db.JSON)
    duration_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'role': self.role,
            'content': self.content,
            'tool_name': self.tool_name,
            'tool_args': self.tool_args,
            'tool_ok': self.tool_ok,
            'tool_result': self.tool_result,
            'duration_ms': self.duration_ms,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
