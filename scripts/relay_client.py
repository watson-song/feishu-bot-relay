#!/usr/bin/env python3
"""
飞书 Bot 消息中继客户端
提供消息写入、轮询、锁管理等功能

本客户端设计为与 OpenClaw 环境集成使用
"""

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any


class RelayClient:
    """
    Bitable 消息中继客户端
    
    使用示例:
        client = RelayClient(app_token, table_id)
        
        # 写入消息
        client.write_message({
            "msg_id": str(uuid.uuid4()),
            "chat_id": "oc_xxx",
            "sender_id": "ou_xxx",
            "receiver_id": "ou_yyy",
            "content": "消息内容"
        })
        
        # 轮询消息
        messages = client.poll_messages(receiver_id="ou_yyy")
        
        # 处理消息
        for msg in messages:
            if client.acquire_lock(msg["record_id"], "instance-1"):
                # 处理...
                client.update_status(msg["record_id"], "已完成", "回复内容")
    """
    
    def __init__(self, app_token: str, table_id: str, 
                 lock_timeout: int = 30, poll_interval: int = 30):
        """
        初始化客户端
        
        Args:
            app_token: Bitable app token
            table_id: 消息表 table_id
            lock_timeout: 锁过期时间（秒），默认30
            poll_interval: 轮询间隔（秒），默认30
        """
        self.app_token = app_token
        self.table_id = table_id
        self.lock_timeout = lock_timeout
        self.poll_interval = poll_interval
        
    def write_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        写入新消息（幂等，重复写入返回已存在记录）
        
        Args:
            message: 消息字典，必须包含:
                - msg_id: 消息唯一ID
                - chat_id: 群聊ID
                - sender_id: 发送者 open_id
                - receiver_id: 接收者 open_id
                - content: 消息内容
            可选字段:
                - chat_name, sender_name, receiver_name
                - quote_msg_id: 引用的原消息ID
        
        Returns:
            {"success": True, "record_id": "xxx"} 或 
            {"success": False, "error": "...", "existing": True}
        """
        # 检查必填字段
        required = ["msg_id", "chat_id", "sender_id", "receiver_id", "content"]
        for field in required:
            if field not in message:
                return {"success": False, "error": f"缺少必填字段: {field}"}
        
        # 先检查是否已存在
        existing = self._get_record_by_msg_id(message["msg_id"])
        if existing:
            return {
                "success": True, 
                "record_id": existing.get("record_id"),
                "existing": True
            }
        
        # 构造字段
        now = int(datetime.now().timestamp() * 1000)
        fields = {
            "msg_id": message["msg_id"],
            "chat_id": message["chat_id"],
            "chat_name": message.get("chat_name", ""),
            "sender_id": message["sender_id"],
            "sender_name": message.get("sender_name", ""),
            "receiver_id": message["receiver_id"],
            "receiver_name": message.get("receiver_name", ""),
            "content": message["content"],
            "quote_msg_id": message.get("quote_msg_id", ""),
            "status": "待处理",
            "lock_holder": "",
            "lock_expire_at": 0,
            "created_at": now,
            "processed_at": 0,
            "response": ""
        }
        
        return self._create_record(fields)
    
    def poll_messages(self, receiver_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        轮询指定接收者的待处理消息
        
        Args:
            receiver_id: 接收 Bot 的 open_id
            limit: 每次返回的最大数量
        
        Returns:
            消息列表，每个消息包含完整字段
        """
        now = int(datetime.now().timestamp() * 1000)
        
        # 查询待处理的消息
        pending = self._list_records({
            "conjunction": "and",
            "conditions": [
                {"field_name": "receiver_id", "operator": "is", "value": [receiver_id]},
                {"field_name": "status", "operator": "is", "value": ["待处理"]}
            ]
        }, limit)
        
        # 查询锁已过期的处理中消息
        expired = self._list_expired_locks(receiver_id, now, limit)
        
        return pending + expired
    
    def acquire_lock(self, record_id: str, holder: str) -> bool:
        """
        尝试获取消息处理锁
        
        Args:
            record_id: Bitable 记录 ID
            holder: 持有者标识（建议格式：bot_name-instance-id）
        
        Returns:
            是否成功获取锁
        """
        # 获取当前记录
        record = self._get_record(record_id)
        if not record:
            return False
        
        fields = record.get("fields", {})
        current_holder = fields.get("lock_holder", "")
        expire_at = fields.get("lock_expire_at", 0)
        now = int(datetime.now().timestamp() * 1000)
        
        # 检查是否被其他持有者锁定且未过期
        if current_holder and current_holder != holder and expire_at > now:
            return False
        
        # 更新锁信息
        new_expire = int((datetime.now() + timedelta(seconds=self.lock_timeout)).timestamp() * 1000)
        result = self._update_record(record_id, {
            "status": "处理中",
            "lock_holder": holder,
            "lock_expire_at": new_expire
        })
        
        return result.get("success", False)
    
    def renew_lock(self, record_id: str, holder: str) -> bool:
        """
        续期锁（处理耗时较长时调用）
        
        Args:
            record_id: Bitable 记录 ID
            holder: 持有者标识
        
        Returns:
            是否成功续期
        """
        record = self._get_record(record_id)
        if not record:
            return False
        
        fields = record.get("fields", {})
        if fields.get("lock_holder") != holder:
            return False
        
        new_expire = int((datetime.now() + timedelta(seconds=self.lock_timeout)).timestamp() * 1000)
        result = self._update_record(record_id, {
            "lock_expire_at": new_expire
        })
        
        return result.get("success", False)
    
    def update_status(self, record_id: str, status: str, response: str = "") -> Dict[str, Any]:
        """
        更新消息状态
        
        Args:
            record_id: Bitable 记录 ID
            status: 新状态（待处理/处理中/已完成/失败）
            response: 回复内容（可选）
        
        Returns:
            更新结果
        """
        fields = {
            "status": status,
            "lock_holder": "",  # 清空锁
            "lock_expire_at": 0,
        }
        
        if response:
            fields["response"] = response
        
        if status in ["已完成", "失败"]:
            fields["processed_at"] = int(datetime.now().timestamp() * 1000)
        
        return self._update_record(record_id, fields)
    
    @staticmethod
    def parse_at_users(content: str) -> List[str]:
        """
        解析消息中的 @ 用户列表
        
        Args:
            content: 飞书消息内容（可能包含 <at user_id="xxx">name</at>）
        
        Returns:
            user_id 列表
        """
        pattern = r'<at user_id="([^"]+)">[^<]*</at>'
        return re.findall(pattern, content)
    
    @staticmethod
    def strip_at_tags(content: str) -> str:
        """
        去除 @ 标签，保留纯文本
        
        Args:
            content: 飞书消息内容
        
        Returns:
            纯文本内容
        """
        # 移除 at 标签，保留名字
        content = re.sub(r'<at user_id="[^"]+">([^<]*)</at>', r'@\1', content)
        # 移除其他 HTML 标签
        content = re.sub(r'<[^>]+>', '', content)
        return content.strip()
    
    @staticmethod
    def generate_msg_id() -> str:
        """生成唯一消息ID"""
        return str(uuid.uuid4())
    
    # ========== 内部方法：模拟 Bitable 操作（需替换为实际 API 调用）==========
    
    def _get_record_by_msg_id(self, msg_id: str) -> Optional[Dict]:
        """
        通过 msg_id 查询记录
        
        实际使用时需要通过 OpenClaw 工具调用:
        feishu_bitable_app_table_record list --filter '{...}'
        """
        # 模拟实现，实际使用时替换
        return None
    
    def _get_record(self, record_id: str) -> Optional[Dict]:
        """
        通过 record_id 获取记录
        
        实际使用时需要通过 OpenClaw 工具调用:
        feishu_bitable_app_table_record list --record-id xxx
        """
        # 模拟实现，实际使用时替换
        return None
    
    def _create_record(self, fields: Dict) -> Dict[str, Any]:
        """
        创建记录
        
        实际使用时需要通过 OpenClaw 工具调用:
        feishu_bitable_app_table_record create --fields '{...}'
        """
        # 模拟实现，实际使用时替换
        return {"success": True, "record_id": "mock_record_id"}
    
    def _update_record(self, record_id: str, fields: Dict) -> Dict[str, Any]:
        """
        更新记录
        
        实际使用时需要通过 OpenClaw 工具调用:
        feishu_bitable_app_table_record update --record-id xxx --fields '{...}'
        """
        # 模拟实现，实际使用时替换
        return {"success": True}
    
    def _list_records(self, filter_dict: Dict, limit: int = 10) -> List[Dict]:
        """
        查询记录列表
        
        实际使用时需要通过 OpenClaw 工具调用:
        feishu_bitable_app_table_record list --filter '{...}' --page-size n
        """
        # 模拟实现，实际使用时替换
        return []
    
    def _list_expired_locks(self, receiver_id: str, now: int, limit: int) -> List[Dict]:
        """
        查询锁已过期的处理中消息
        
        筛选条件: receiver_id = xxx AND status = 处理中 AND lock_expire_at < now
        """
        # 先查询所有处理中的消息
        records = self._list_records({
            "conjunction": "and",
            "conditions": [
                {"field_name": "receiver_id", "operator": "is", "value": [receiver_id]},
                {"field_name": "status", "operator": "is", "value": ["处理中"]}
            ]
        }, limit * 2)
        
        # 本地过滤锁已过期的
        result = []
        for r in records:
            fields = r.get("fields", {})
            expire_at = fields.get("lock_expire_at", 0)
            if expire_at and expire_at < now:
                result.append(r)
        
        return result[:limit]


class BotRegistry:
    """
    Bot 注册表客户端
    用于管理 Bot 注册信息和识别其他 Bot
    """
    
    def __init__(self, app_token: str, table_id: str):
        """
        初始化注册表客户端
        
        Args:
            app_token: Bitable app token
            table_id: bot_registry 表的 table_id
        """
        self.app_token = app_token
        self.table_id = table_id
        self._cache = {}  # 本地缓存
        self._cache_time = 0
        self._cache_ttl = 60  # 缓存60秒
    
    def get_all_bots(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        获取所有已注册的 Bot
        
        Args:
            force_refresh: 是否强制刷新缓存
        
        Returns:
            Bot 列表
        """
        # 检查缓存
        now = int(datetime.now().timestamp())
        if not force_refresh and self._cache and (now - self._cache_time) < self._cache_ttl:
            return list(self._cache.values())
        
        # 查询 Bitable
        bots = self._list_records({
            "conjunction": "and",
            "conditions": [
                {"field_name": "is_active", "operator": "is", "value": ["true"]}
            ]
        }, 100)
        
        # 更新缓存
        self._cache = {}
        for bot in bots:
            fields = bot.get("fields", {})
            bot_id = fields.get("bot_id")
            if bot_id:
                self._cache[bot_id] = {
                    "record_id": bot.get("record_id"),
                    "bot_id": bot_id,
                    "bot_name": fields.get("bot_name", ""),
                    "bot_type": fields.get("bot_type", ""),
                    "description": fields.get("description", ""),
                    "is_active": fields.get("is_active", False)
                }
        
        self._cache_time = now
        return list(self._cache.values())
    
    def get_bot_by_id(self, bot_id: str) -> Optional[Dict[str, Any]]:
        """
        通过 ID 获取 Bot 信息
        
        Args:
            bot_id: Bot 的 open_id
        
        Returns:
            Bot 信息或 None
        """
        # 先查缓存
        if bot_id in self._cache:
            return self._cache[bot_id]
        
        # 查询 Bitable
        bots = self._list_records({
            "conjunction": "and",
            "conditions": [
                {"field_name": "bot_id", "operator": "is", "value": [bot_id]}
            ]
        }, 1)
        
        if bots:
            fields = bots[0].get("fields", {})
            return {
                "record_id": bots[0].get("record_id"),
                "bot_id": bot_id,
                "bot_name": fields.get("bot_name", ""),
                "bot_type": fields.get("bot_type", ""),
                "description": fields.get("description", ""),
                "is_active": fields.get("is_active", False)
            }
        return None
    
    def get_bot_by_name(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """
        通过名称获取 Bot 信息
        
        Args:
            bot_name: Bot 显示名称
        
        Returns:
            Bot 信息或 None
        """
        # 先查缓存
        for bot in self._cache.values():
            if bot.get("bot_name") == bot_name:
                return bot
        
        # 查询 Bitable
        bots = self._list_records({
            "conjunction": "and",
            "conditions": [
                {"field_name": "bot_name", "operator": "is", "value": [bot_name]}
            ]
        }, 1)
        
        if bots:
            fields = bots[0].get("fields", {})
            return {
                "record_id": bots[0].get("record_id"),
                "bot_id": fields.get("bot_id", ""),
                "bot_name": bot_name,
                "bot_type": fields.get("bot_type", ""),
                "description": fields.get("description", ""),
                "is_active": fields.get("is_active", False)
            }
        return None
    
    def is_bot(self, user_id: str) -> bool:
        """
        检查 user_id 是否是已注册的 Bot
        
        Args:
            user_id: 用户 open_id
        
        Returns:
            是否是 Bot
        """
        bot = self.get_bot_by_id(user_id)
        return bot is not None and bot.get("is_active", False)
    
    def auto_register(self, bot_id: str, bot_name: str, bot_type: str = "", 
                      description: str = "", force_update: bool = False) -> Dict[str, Any]:
        """
        自动注册 Bot（启动时调用）
        
        如果 Bot 已存在：
        - force_update=False: 返回已存在，不更新
        - force_update=True: 更新信息并刷新 updated_at
        
        Args:
            bot_id: Bot 的 open_id
            bot_name: Bot 显示名称
            bot_type: 类型/功能描述
            description: 详细说明
            force_update: 是否强制更新已存在的记录
        
        Returns:
            {"success": True, "record_id": "xxx", "action": "created|updated|unchanged"}
        
        使用示例:
            registry = BotRegistry(app_token, table_id_registry)
            result = registry.auto_register(
                bot_id="ou_xxx",
                bot_name="MyBot",
                bot_type="AI助手",
                description="负责消息处理"
            )
            if result["success"]:
                print(f"注册成功: {result['action']}")
        """
        # 检查是否已存在
        existing = self.get_bot_by_id(bot_id)
        now = int(datetime.now().timestamp() * 1000)
        
        if existing:
            if not force_update:
                return {
                    "success": True,
                    "record_id": existing.get("record_id"),
                    "action": "unchanged",
                    "message": "Bot 已存在，未更新"
                }
            
            # 更新现有记录
            fields = {
                "bot_name": bot_name,
                "bot_type": bot_type,
                "description": description,
                "is_active": True,
                "updated_at": now
            }
            result = self._update_record(existing["record_id"], fields)
            if result.get("success"):
                # 刷新缓存
                self._cache.pop(bot_id, None)
                return {
                    "success": True,
                    "record_id": existing["record_id"],
                    "action": "updated"
                }
            return {"success": False, "error": result.get("error", "更新失败")}
        
        # 创建新记录
        fields = {
            "bot_id": bot_id,
            "bot_name": bot_name,
            "bot_type": bot_type,
            "description": description,
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        
        result = self._create_record(fields)
        if result.get("success"):
            # 添加到缓存
            self._cache[bot_id] = {
                "record_id": result.get("record_id"),
                "bot_id": bot_id,
                "bot_name": bot_name,
                "bot_type": bot_type,
                "description": description,
                "is_active": True
            }
            return {
                "success": True,
                "record_id": result.get("record_id"),
                "action": "created"
            }
        
        return {"success": False, "error": result.get("error", "创建失败")}
    
    def register_bot(self, bot_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        注册新 Bot（旧版接口，建议使用 auto_register）
        
        Args:
            bot_info: 包含 bot_id, bot_name, bot_type, description
        
        Returns:
            注册结果
        """
        # 检查是否已存在
        existing = self.get_bot_by_id(bot_info.get("bot_id"))
        if existing:
            return {"success": False, "error": "Bot 已存在", "existing": True}
        
        now = int(datetime.now().timestamp() * 1000)
        fields = {
            "bot_id": bot_info["bot_id"],
            "bot_name": bot_info.get("bot_name", ""),
            "bot_type": bot_info.get("bot_type", ""),
            "description": bot_info.get("description", ""),
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        
        return self._create_record(fields)
    
    def _list_records(self, filter_dict: Dict, limit: int = 10) -> List[Dict]:
        """
        查询记录列表
        
        实际使用时需要通过 OpenClaw 工具调用
        """
        # 模拟实现，实际使用时替换
        return []
    
    def _create_record(self, fields: Dict) -> Dict[str, Any]:
        """
        创建记录
        
        实际使用时需要通过 OpenClaw 工具调用
        """
        # 模拟实现，实际使用时替换
        return {"success": True, "record_id": "mock_record_id"}
    
    def _update_record(self, record_id: str, fields: Dict) -> Dict[str, Any]:
        """
        更新记录
        
        实际使用时需要通过 OpenClaw 工具调用
        """
        # 模拟实现，实际使用时替换
        return {"success": True}


# ========== OpenClaw 集成适配器 ==========

class OpenClawRelayClient(RelayClient):
    """
    与 OpenClaw feishu_bitable 工具集成的客户端
    在 OpenClaw 环境中使用此客户端
    """
    
    def __init__(self, app_token: str, table_id: str, 
                 lock_timeout: int = 30, poll_interval: int = 30):
        super().__init__(app_token, table_id, lock_timeout, poll_interval)
        # 在 OpenClaw 环境中，这些方法会被替换为实际工具调用
        
    def set_tool_caller(self, caller):
        """
        设置工具调用器
        
        Args:
            caller: 工具调用函数，接收 (tool_name, params) 返回结果
        """
        self._tool_caller = caller


class OpenClawBotRegistry(BotRegistry):
    """
    与 OpenClaw 集成的 BotRegistry
    """
    
    def __init__(self, app_token: str, table_id: str):
        super().__init__(app_token, table_id)
        
    def set_tool_caller(self, caller):
        """设置工具调用器"""
        self._tool_caller = caller


if __name__ == "__main__":
    print("=" * 60)
    print("飞书 Bot 消息中继客户端")
    print("=" * 60)
    print()
    print("使用示例:")
    print()
    print("# 初始化客户端")
    print("client = RelayClient(app_token, table_id)")
    print()
    print("# 写入消息")
    print('client.write_message({')
    print('    "msg_id": str(uuid.uuid4()),')
    print('    "chat_id": "oc_xxx",')
    print('    "sender_id": "ou_xxx",')
    print('    "receiver_id": "ou_yyy",')
    print('    "content": "消息内容"')
    print('})')
    print()
    print("# 轮询消费")
    print('messages = client.poll_messages(receiver_id="ou_yyy")')
    print('for msg in messages:')
    print('    if client.acquire_lock(msg["record_id"], "instance-1"):')
    print('        # 处理消息')
    print('        client.update_status(msg["record_id"], "已完成", "回复")')
    print()
    print("=" * 60)
