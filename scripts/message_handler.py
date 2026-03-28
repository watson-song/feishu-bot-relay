#!/usr/bin/env python3
"""
消息处理器模板
提供多种消息处理模式供 Bot 开发者参考

使用方式:
1. 继承 BaseMessageHandler 实现自定义处理器
2. 或使用预设处理器（EchoHandler, CommandHandler 等）
3. 在 poll_messages.py 中传入 handler 参数
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
import re


class BaseMessageHandler(ABC):
    """
    Bot 消息处理抽象基类
    
    使用方式：
        class MyHandler(BaseMessageHandler):
            def handle(self, msg: dict) -> str:
                # 实现处理逻辑
                return "回复内容"
        
        handler = MyHandler(bot_id, bot_name)
        poller = MessagePoller(..., handler=handler.handle)
    """
    
    def __init__(self, bot_id: str, bot_name: str):
        """
        初始化处理器
        
        Args:
            bot_id: Bot 的 open_id
            bot_name: Bot 的显示名称
        """
        self.bot_id = bot_id
        self.bot_name = bot_name
    
    @abstractmethod
    def handle(self, msg: Dict[str, Any]) -> str:
        """
        处理消息（必须实现）
        
        Args:
            msg: Bitable 记录，包含:
                - record_id: 记录 ID
                - fields: {
                    msg_id, chat_id, sender_id, sender_name,
                    receiver_id, receiver_name, content,
                    quote_msg_id, status, created_at, ...
                }
        
        Returns:
            回复内容（将保存到 response 字段并发送到群聊）
        """
        pass
    
    def pre_process(self, content: str) -> str:
        """
        预处理消息内容
        
        默认实现：去除首尾空格
        可覆盖以实现自定义预处理
        """
        return content.strip()
    
    def post_process(self, response: str) -> str:
        """
        后处理回复内容
        
        默认实现：限制长度、添加前缀
        可覆盖以实现自定义后处理
        """
        max_length = 2000  # 飞书消息长度限制
        if len(response) > max_length:
            response = response[:max_length - 3] + "..."
        return response
    
    def extract_content(self, msg: Dict[str, Any]) -> str:
        """从消息中提取内容"""
        return msg.get("fields", {}).get("content", "")
    
    def extract_sender(self, msg: Dict[str, Any]) -> Dict[str, str]:
        """从消息中提取发送者信息"""
        fields = msg.get("fields", {})
        return {
            "id": fields.get("sender_id", ""),
            "name": fields.get("sender_name", "未知")
        }


class EchoHandler(BaseMessageHandler):
    """
    回声处理器
    简单返回收到的消息内容
    """
    
    def handle(self, msg: Dict[str, Any]) -> str:
        content = self.extract_content(msg)
        sender = self.extract_sender(msg)
        content = self.pre_process(content)
        
        response = f"[{self.bot_name}] 收到 {sender['name']} 的消息: {content}"
        return self.post_process(response)


class CommandHandler(BaseMessageHandler):
    """
    命令处理器
    支持 /command 格式的命令处理
    """
    
    def __init__(self, bot_id: str, bot_name: str):
        super().__init__(bot_id, bot_name)
        self.commands: Dict[str, Dict[str, Any]] = {}
        self._register_default_commands()
    
    def _register_default_commands(self):
        """注册默认命令"""
        self.register_command("help", self._cmd_help, "显示帮助信息")
        self.register_command("ping", self._cmd_ping, "测试连通性")
        self.register_command("status", self._cmd_status, "查看状态")
    
    def register_command(self, name: str, handler: Callable, description: str = ""):
        """
        注册命令
        
        Args:
            name: 命令名称（不带 /）
            handler: 处理函数，接收 (args, msg) 返回 str
            description: 命令描述
        """
        self.commands[name] = {
            "handler": handler,
            "description": description
        }
    
    def handle(self, msg: Dict[str, Any]) -> str:
        content = self.extract_content(msg)
        content = self.pre_process(content)
        sender = self.extract_sender(msg)
        
        # 检查是否是命令格式
        if not content.startswith("/"):
            return self._handle_plain_text(content, sender)
        
        # 解析命令
        parts = content[1:].split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # 查找命令
        cmd = self.commands.get(cmd_name)
        if not cmd:
            return f"[{self.bot_name}] 未知命令: {cmd_name}\n{self._show_help()}"
        
        # 执行命令
        try:
            response = cmd["handler"](args, msg)
            return self.post_process(response)
        except Exception as e:
            return f"[{self.bot_name}] 命令执行失败: {e}"
    
    def _handle_plain_text(self, content: str, sender: Dict[str, str]) -> str:
        """处理非命令文本"""
        return f"[{self.bot_name}] 收到 {sender['name']} 的消息: {content[:100]}"
    
    def _show_help(self) -> str:
        """显示帮助信息"""
        lines = [f"可用命令："]
        for name, info in self.commands.items():
            lines.append(f"  /{name} - {info['description']}")
        return "\n".join(lines)
    
    def _cmd_help(self, args: str, msg: Dict[str, Any]) -> str:
        """help 命令"""
        return f"[{self.bot_name}]\n{self._show_help()}"
    
    def _cmd_ping(self, args: str, msg: Dict[str, Any]) -> str:
        """ping 命令"""
        return f"[{self.bot_name}] pong!"
    
    def _cmd_status(self, args: str, msg: Dict[str, Any]) -> str:
        """status 命令"""
        return f"[{self.bot_name}] 状态：正常运行\nBot ID: {self.bot_id}"


class KeywordHandler(BaseMessageHandler):
    """
    关键词处理器
    根据关键词匹配自动回复
    """
    
    def __init__(self, bot_id: str, bot_name: str):
        super().__init__(bot_id, bot_name)
        self.keywords: Dict[str, str] = {}
        self.default_response = f"[{bot_name}] 抱歉，我不太明白你的意思。"
    
    def register_keyword(self, keyword: str, response: str):
        """
        注册关键词回复
        
        Args:
            keyword: 关键词（不区分大小写）
            response: 回复内容
        """
        self.keywords[keyword.lower()] = response
    
    def set_default_response(self, response: str):
        """设置默认回复"""
        self.default_response = response
    
    def handle(self, msg: Dict[str, Any]) -> str:
        content = self.extract_content(msg)
        content = self.pre_process(content).lower()
        sender = self.extract_sender(msg)
        
        # 关键词匹配
        for keyword, response in self.keywords.items():
            if keyword in content:
                return self.post_process(response)
        
        return self.post_process(self.default_response)


class RegexHandler(BaseMessageHandler):
    """
    正则表达式处理器
    使用正则匹配消息并提取信息
    """
    
    def __init__(self, bot_id: str, bot_name: str):
        super().__init__(bot_id, bot_name)
        self.patterns: List[Dict[str, Any]] = []
        self.default_response = f"[{bot_name}] 无法处理该消息。"
    
    def register_pattern(self, pattern: str, handler: Callable, description: str = ""):
        """
        注册正则模式
        
        Args:
            pattern: 正则表达式
            handler: 处理函数，接收 (match, msg) 返回 str
            description: 模式描述
        """
        self.patterns.append({
            "pattern": re.compile(pattern, re.IGNORECASE),
            "handler": handler,
            "description": description
        })
    
    def handle(self, msg: Dict[str, Any]) -> str:
        content = self.extract_content(msg)
        content = self.pre_process(content)
        
        # 依次匹配模式
        for p in self.patterns:
            match = p["pattern"].search(content)
            if match:
                try:
                    response = p["handler"](match, msg)
                    return self.post_process(response)
                except Exception as e:
                    return f"[{self.bot_name}] 处理失败: {e}"
        
        return self.post_process(self.default_response)


class ChainHandler(BaseMessageHandler):
    """
    链式处理器
    将多个处理器串联，依次尝试处理
    """
    
    def __init__(self, bot_id: str, bot_name: str):
        super().__init__(bot_id, bot_name)
        self.handlers: List[BaseMessageHandler] = []
    
    def add_handler(self, handler: BaseMessageHandler):
        """添加处理器到链"""
        self.handlers.append(handler)
    
    def handle(self, msg: Dict[str, Any]) -> str:
        for handler in self.handlers:
            try:
                response = handler.handle(msg)
                # 如果处理器返回了有效回复，直接返回
                if response and not response.startswith(f"[{handler.bot_name}] 收到"):
                    return response
            except Exception:
                continue
        
        # 所有处理器都无法处理
        return f"[{self.bot_name}] 无法处理该消息。"


class ContextHandler(BaseMessageHandler):
    """
    上下文处理器
    维护对话上下文，支持多轮交互
    """
    
    def __init__(self, bot_id: str, bot_name: str, max_context: int = 5):
        super().__init__(bot_id, bot_name)
        self.max_context = max_context
        self.contexts: Dict[str, List[Dict[str, str]]] = {}
    
    def _get_session_key(self, msg: Dict[str, Any]) -> str:
        """获取会话键"""
        fields = msg.get("fields", {})
        chat_id = fields.get("chat_id", "")
        sender_id = fields.get("sender_id", "")
        return f"{chat_id}:{sender_id}"
    
    def _get_context(self, session_key: str) -> List[Dict[str, str]]:
        """获取会话上下文"""
        return self.contexts.get(session_key, [])
    
    def _add_to_context(self, session_key: str, role: str, content: str):
        """添加到上下文"""
        if session_key not in self.contexts:
            self.contexts[session_key] = []
        
        self.contexts[session_key].append({
            "role": role,
            "content": content
        })
        
        # 限制上下文长度
        if len(self.contexts[session_key]) > self.max_context * 2:
            self.contexts[session_key] = self.contexts[session_key][-self.max_context * 2:]
    
    def handle(self, msg: Dict[str, Any]) -> str:
        content = self.extract_content(msg)
        session_key = self._get_session_key(msg)
        sender = self.extract_sender(msg)
        
        # 添加用户消息到上下文
        self._add_to_context(session_key, "user", content)
        
        # 生成回复（子类应覆盖此方法实现具体逻辑）
        response = self._generate_response(msg, self._get_context(session_key))
        
        # 添加助手回复到上下文
        self._add_to_context(session_key, "assistant", response)
        
        return self.post_process(response)
    
    def _generate_response(self, msg: Dict[str, Any], context: List[Dict[str, str]]) -> str:
        """
        生成回复（子类应覆盖）
        
        Args:
            msg: 当前消息
            context: 对话上下文
        
        Returns:
            回复内容
        """
        # 默认实现：简单的回声
        return f"[{self.bot_name}] 收到，上下文长度: {len(context)}"


# ========== 使用示例 ==========

def example_usage():
    """使用示例"""
    
    # 1. 回声处理器
    echo = EchoHandler(bot_id="ou_xxx", bot_name="EchoBot")
    
    # 2. 命令处理器
    cmd = CommandHandler(bot_id="ou_xxx", bot_name="CmdBot")
    
    def handle_query(args: str, msg: Dict[str, Any]) -> str:
        return f"查询结果：{args}"
    
    def handle_calc(args: str, msg: Dict[str, Any]) -> str:
        try:
            result = eval(args)  # 注意：实际使用时要安全检查
            return f"计算结果：{result}"
        except:
            return "计算失败"
    
    cmd.register_command("query", handle_query, "查询信息")
    cmd.register_command("calc", handle_calc, "计算表达式")
    
    # 3. 关键词处理器
    keyword = KeywordHandler(bot_id="ou_xxx", bot_name="KeywordBot")
    keyword.register_keyword("帮助", "我可以帮你：查询、计算、提醒")
    keyword.register_keyword("时间", "当前时间是...")
    keyword.set_default_response("请说「帮助」查看我能做什么")
    
    # 4. 正则处理器
    regex = RegexHandler(bot_id="ou_xxx", bot_name="RegexBot")
    
    def handle_phone(match, msg):
        phone = match.group(1)
        return f"识别到手机号：{phone[:3]}****{phone[-4:]}"
    
    def handle_email(match, msg):
        email = match.group(1)
        return f"识别到邮箱：{email}"
    
    regex.register_pattern(r"1[3-9]\d{9}", handle_phone, "手机号")
    regex.register_pattern(r"[\w.-]+@[\w.-]+\.\w+", handle_email, "邮箱")
    
    # 在 poll_messages.py 中使用
    # poller = MessagePoller(..., handler=echo.handle)


if __name__ == "__main__":
    print("=" * 60)
    print("MessageHandler 模板")
    print("=" * 60)
    print()
    print("可用处理器:")
    print()
    print("1. EchoHandler - 简单回声")
    print("   handler = EchoHandler(bot_id, bot_name)")
    print()
    print("2. CommandHandler - 命令处理")
    print("   handler = CommandHandler(bot_id, bot_name)")
    print("   handler.register_command('cmd', func, '描述')")
    print()
    print("3. KeywordHandler - 关键词匹配")
    print("   handler = KeywordHandler(bot_id, bot_name)")
    print("   handler.register_keyword('关键词', '回复')")
    print()
    print("4. RegexHandler - 正则匹配")
    print("   handler = RegexHandler(bot_id, bot_name)")
    print("   handler.register_pattern(r'正则', func)")
    print()
    print("5. ContextHandler - 上下文对话")
    print("   继承 ContextHandler 实现 _generate_response")
    print()
    print("6. ChainHandler - 链式处理")
    print("   chain = ChainHandler(bot_id, bot_name)")
    print("   chain.add_handler(handler1)")
    print("   chain.add_handler(handler2)")
    print()
    print("=" * 60)
