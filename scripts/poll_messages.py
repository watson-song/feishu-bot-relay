#!/usr/bin/env python3
"""
消息轮询消费示例
Bot 定期轮询 Bitable，处理发给自已的消息

使用方法:
    python scripts/poll_messages.py \
        --bot-id "ou_xxx" \
        --app-token "xxx" \
        --table-id-relay "xxx" \
        --table-id-registry "xxx" \
        --interval 30

注意:
    此脚本需要在 OpenClaw 环境中运行，或手动提供 tool_caller
    才能正常调用飞书 Bitable API
"""

import argparse
import json
import sys
import time
import traceback
from datetime import datetime

# 添加脚本目录到路径
sys.path.insert(0, '/root/.openclaw/workspace/skills/feishu-bot-relay/scripts')

from relay_client import OpenClawRelayClient, OpenClawBotRegistry


class MessagePoller:
    """消息轮询器"""
    
    def __init__(self, bot_id: str, bot_name: str, app_token: str, 
                 table_id_relay: str, table_id_registry: str, 
                 interval: int = 30, lock_timeout: int = 30,
                 handler=None, tool_caller=None):
        """
        初始化轮询器
        
        Args:
            bot_id: 本 Bot 的 open_id
            bot_name: 本 Bot 的名称
            app_token: Bitable app_token
            table_id_relay: 消息队列表 ID
            table_id_registry: Bot 注册表 ID
            interval: 轮询间隔秒数
            lock_timeout: 锁过期时间秒数
            handler: 消息处理函数，接收 msg 返回 response
            tool_caller: OpenClaw 工具调用器 (feishu_bitable_app_table_record)
        """
        self.bot_id = bot_id
        self.bot_name = bot_name
        self.interval = interval
        self.instance_id = f"{bot_name}-{int(time.time())}"
        self.running = False
        self.handler = handler or self._default_handler
        self.tool_caller = tool_caller
        
        # 初始化客户端（使用 OpenClaw 集成版本）
        self.relay = OpenClawRelayClient(
            app_token=app_token,
            table_id=table_id_relay,
            lock_timeout=lock_timeout
        )
        self.registry = OpenClawBotRegistry(app_token, table_id_registry)
        
        # 绑定工具调用器
        if tool_caller:
            self.relay.set_tool_caller(tool_caller)
            self.registry.set_tool_caller(tool_caller)
        
    def start(self):
        """启动轮询循环"""
        self.running = True
        
        # 启动时自动注册到 bot_registry
        print(f"[{self._now()}] 正在注册到 bot_registry...")
        reg_result = self.registry.auto_register(
            bot_id=self.bot_id,
            bot_name=self.bot_name,
            bot_type="消息中继Bot",
            description=f"实例: {self.instance_id}"
        )
        if reg_result["success"]:
            print(f"  注册成功: {reg_result['action']}")
        else:
            print(f"  注册失败: {reg_result.get('error')}")
        
        print(f"[{self._now()}] 轮询器启动")
        print(f"  Bot ID: {self.bot_id}")
        print(f"  Bot Name: {self.bot_name}")
        print(f"  Instance ID: {self.instance_id}")
        print(f"  轮询间隔: {self.interval}秒")
        print()
        
        while self.running:
            try:
                self._poll_once()
            except Exception as e:
                print(f"[{self._now()}] 轮询异常: {e}")
                traceback.print_exc()
                # 指数退避
                time.sleep(min(self.interval * 2, 60))
                continue
                
            time.sleep(self.interval)
    
    def stop(self):
        """停止轮询"""
        self.running = False
        print(f"[{self._now()}] 轮询器停止")
    
    def _poll_once(self):
        """执行一次轮询"""
        print(f"[{self._now()}] 开始轮询...")
        
        # 1. 查询待处理消息
        messages = self.relay.poll_messages(receiver_id=self.bot_id)
        if not messages:
            print("  无新消息")
            return
            
        print(f"  发现 {len(messages)} 条待处理消息")
        
        # 2. 处理每条消息
        for msg in messages:
            self._process_single_message(msg)
    
    def _process_single_message(self, msg: dict):
        """处理单条消息"""
        record_id = msg.get("record_id")
        msg_id = msg.get("fields", {}).get("msg_id", "unknown")
        content = msg.get("fields", {}).get("content", "")
        sender_id = msg.get("fields", {}).get("sender_id")
        chat_id = msg.get("fields", {}).get("chat_id")
        
        print(f"  处理消息 {msg_id}...")
        
        # 1. 抢锁
        if not self.relay.acquire_lock(record_id, self.instance_id):
            print(f"    抢锁失败，跳过")
            return
        print(f"    抢锁成功")
        
        # 2. 处理消息
        try:
            response = self.handler(msg)
            
            # 3. 更新状态为已完成
            result = self.relay.update_status(record_id, "已完成", response)
            if result.get("success"):
                print(f"    处理完成")
            else:
                print(f"    更新状态失败: {result.get('error')}")
            
            # 4. 回复到飞书群聊（如果处理成功且有回复）
            if response and chat_id:
                self._send_reply(chat_id, sender_id, response)
            
        except Exception as e:
            error_msg = f"处理异常: {str(e)}"
            print(f"    {error_msg}")
            traceback.print_exc()
            self.relay.update_status(record_id, "失败", error_msg)
    
    def _send_reply(self, chat_id: str, target_user_id: str, content: str):
        """
        回复消息到飞书群聊
        
        Args:
            chat_id: 群聊 ID
            target_user_id: 目标用户 ID（用于 @）
            content: 回复内容
        """
        # 构造回复内容
        if target_user_id:
            reply_content = f"<at user_id=\"{target_user_id}\"></at> {content}"
        else:
            reply_content = content
        
        print(f"    发送回复到群聊 {chat_id}")
        # 实际发送需要通过飞书 API
        # 这里仅打印，实际使用时需要调用 feishu_im_user_message
        print(f"    [模拟发送] {reply_content[:100]}...")
        return True
    
    def _default_handler(self, msg: dict) -> str:
        """
        默认消息处理器
        
        实际使用时应该传入自定义 handler
        """
        content = msg.get("fields", {}).get("content", "")
        sender_name = msg.get("fields", {}).get("sender_name", "")
        
        # 示例：简单的回声
        return f"收到 {sender_name} 的消息: {content[:50]}..."
    
    @staticmethod
    def _now() -> str:
        """获取当前时间字符串"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_echo_handler(bot_name: str):
    """创建回声处理器"""
    def handler(msg: dict) -> str:
        content = msg.get("fields", {}).get("content", "")
        sender_name = msg.get("fields", {}).get("sender_name", "未知")
        return f"[{bot_name}] 收到 {sender_name} 的消息: {content}"
    return handler


def create_command_handler(bot_name: str, commands: dict = None):
    """创建命令处理器"""
    default_commands = {
        "help": lambda args: f"可用命令: {', '.join(commands.keys()) if commands else 'help'}",
        "status": lambda args: f"[{bot_name}] 状态: 正常运行",
        "ping": lambda args: "pong"
    }
    commands = {**default_commands, **(commands or {})}
    
    def handler(msg: dict) -> str:
        content = msg.get("fields", {}).get("content", "").strip()
        
        # 检查是否是命令
        if not content.startswith("/"):
            return f"[{bot_name}] 收到消息: {content[:100]}"
        
        # 解析命令
        parts = content[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # 执行命令
        cmd_func = commands.get(cmd)
        if cmd_func:
            try:
                return cmd_func(args)
            except Exception as e:
                return f"[{bot_name}] 命令执行失败: {e}"
        else:
            return f"[{bot_name}] 未知命令: {cmd}\n可用命令: {', '.join(commands.keys())}"
    
    return handler


def main():
    parser = argparse.ArgumentParser(
        description="Bot 消息轮询消费",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础轮询（使用默认回声处理器）
  python poll_messages.py --bot-id ou_xxx --app-token xxx --table-id-relay xxx --table-id-registry xxx
  
  # 指定 Bot 名称和轮询间隔
  python poll_messages.py --bot-id ou_xxx --bot-name "Bot-A" --interval 10 ...
        """
    )
    parser.add_argument("--bot-id", required=True, help="Bot 的 open_id")
    parser.add_argument("--bot-name", default="Bot", help="Bot 显示名称")
    parser.add_argument("--app-token", required=True, help="Bitable app_token")
    parser.add_argument("--table-id-relay", required=True, help="消息队列表 ID")
    parser.add_argument("--table-id-registry", required=True, help="Bot 注册表 ID")
    parser.add_argument("--interval", type=int, default=30, help="轮询间隔秒数")
    parser.add_argument("--lock-timeout", type=int, default=30, help="锁过期时间秒数")
    parser.add_argument("--handler-type", choices=["echo", "command"], default="echo",
                       help="处理器类型: echo(回声) 或 command(命令)")
    
    args = parser.parse_args()
    
    # 选择处理器
    if args.handler_type == "echo":
        handler = create_echo_handler(args.bot_name)
    else:
        handler = create_command_handler(args.bot_name)
    
    # 尝试获取 OpenClaw 工具调用器
    tool_caller = None
    try:
        # 在 OpenClaw 环境中，feishu_bitable_app_table_record 可用
        from openclaw.tools import feishu_bitable_app_table_record
        tool_caller = feishu_bitable_app_table_record
        print("[INFO] 已检测到 OpenClaw 环境，工具调用器已绑定")
    except ImportError:
        print("[WARN] 未检测到 OpenClaw 环境，轮询功能将无法正常工作")
        print("[WARN] 请在 OpenClaw 环境中运行此脚本，或手动提供 tool_caller")
    
    # 创建轮询器
    poller = MessagePoller(
        bot_id=args.bot_id,
        bot_name=args.bot_name,
        app_token=args.app_token,
        table_id_relay=args.table_id_relay,
        table_id_registry=args.table_id_registry,
        interval=args.interval,
        lock_timeout=args.lock_timeout,
        handler=handler,
        tool_caller=tool_caller
    )
    
    # 启动
    try:
        poller.start()
    except KeyboardInterrupt:
        poller.stop()
        print("\n已安全退出")


if __name__ == "__main__":
    main()
