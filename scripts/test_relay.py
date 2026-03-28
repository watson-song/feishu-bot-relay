#!/usr/bin/env python3
"""
飞书 Bot 消息中继 - 测试脚本
用于验证系统各功能是否正常工作

使用方法:
    python scripts/test_relay.py --app-token xxx --table-id-relay xxx --table-id-registry xxx --bot-id xxx
"""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime

sys.path.insert(0, '/root/.openclaw/workspace/skills/feishu-bot-relay/scripts')

from relay_client import RelayClient, BotRegistry


class RelayTester:
    """测试器"""
    
    def __init__(self, app_token: str, table_id_relay: str, 
                 table_id_registry: str, bot_id: str):
        self.app_token = app_token
        self.table_id_relay = table_id_relay
        self.table_id_registry = table_id_registry
        self.bot_id = bot_id
        
        self.relay = RelayClient(app_token, table_id_relay)
        self.registry = BotRegistry(app_token, table_id_registry)
        
        self.tests_passed = 0
        self.tests_failed = 0
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("飞书 Bot 消息中继 - 功能测试")
        print("=" * 60)
        print()
        
        # 功能测试
        self.test_tc01_write_message()
        self.test_tc02_poll_messages()
        self.test_tc03_acquire_lock()
        self.test_tc04_update_status()
        self.test_tc05_duplicate_message()
        
        # 并发测试
        self.test_tc06_lock_competition()
        self.test_tc07_lock_expiry()
        
        # 注册表测试
        self.test_registry()
        
        # 输出结果
        print()
        print("=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        print(f"通过: {self.tests_passed}")
        print(f"失败: {self.tests_failed}")
        print(f"总计: {self.tests_passed + self.tests_failed}")
        
        if self.tests_failed == 0:
            print("\n✅ 所有测试通过！")
        else:
            print(f"\n❌ 有 {self.tests_failed} 个测试失败")
        
        return self.tests_failed == 0
    
    def _assert(self, condition: bool, test_name: str, message: str = ""):
        """断言测试结果"""
        if condition:
            print(f"  ✅ {test_name}")
            self.tests_passed += 1
        else:
            print(f"  ❌ {test_name}: {message}")
            self.tests_failed += 1
    
    # ========== 功能测试 ==========
    
    def test_tc01_write_message(self):
        """TC-01: 正常消息写入"""
        print("【TC-01】消息写入测试")
        
        msg_id = str(uuid.uuid4())
        result = self.relay.write_message({
            "msg_id": msg_id,
            "chat_id": "test_chat",
            "sender_id": self.bot_id,
            "receiver_id": "target_bot_id",
            "content": "测试消息"
        })
        
        self._assert(
            result.get("success", False),
            "写入消息",
            result.get("error", "")
        )
        
        # 记录用于后续测试
        self.test_msg_id = msg_id
        self.test_record_id = result.get("record_id")
    
    def test_tc02_poll_messages(self):
        """TC-02: 消息轮询"""
        print("\n【TC-02】消息轮询测试")
        
        messages = self.relay.poll_messages(receiver_id="target_bot_id")
        
        self._assert(
            isinstance(messages, list),
            "轮询返回列表",
            f"类型: {type(messages)}"
        )
    
    def test_tc03_acquire_lock(self):
        """TC-03: 抢锁"""
        print("\n【TC-03】抢锁测试")
        
        if not hasattr(self, 'test_record_id'):
            print("  ⏭️  跳过（依赖 TC-01）")
            return
        
        result = self.relay.acquire_lock(self.test_record_id, "test-instance")
        
        self._assert(
            result,
            "抢锁成功",
            "无法获取锁"
        )
    
    def test_tc04_update_status(self):
        """TC-04: 状态更新"""
        print("\n【TC-04】状态更新测试")
        
        if not hasattr(self, 'test_record_id'):
            print("  ⏭️  跳过（依赖 TC-01）")
            return
        
        result = self.relay.update_status(
            self.test_record_id, 
            "已完成", 
            "测试回复"
        )
        
        self._assert(
            result.get("success", False),
            "更新状态",
            result.get("error", "")
        )
    
    def test_tc05_duplicate_message(self):
        """TC-05: 消息去重"""
        print("\n【TC-05】消息去重测试")
        
        # 使用相同的 msg_id 再次写入
        result = self.relay.write_message({
            "msg_id": self.test_msg_id,  # 重复 ID
            "chat_id": "test_chat",
            "sender_id": self.bot_id,
            "receiver_id": "target_bot_id",
            "content": "重复消息"
        })
        
        self._assert(
            result.get("success", False) and result.get("existing", False),
            "重复消息幂等处理",
            "未正确识别重复消息"
        )
    
    # ========== 并发测试 ==========
    
    def test_tc06_lock_competition(self):
        """TC-06: 锁竞争"""
        print("\n【TC-06】锁竞争测试")
        
        # 创建新消息
        msg_id = str(uuid.uuid4())
        result = self.relay.write_message({
            "msg_id": msg_id,
            "chat_id": "test_chat",
            "sender_id": self.bot_id,
            "receiver_id": "target_bot_id",
            "content": "锁竞争测试"
        })
        
        if not result.get("success"):
            print("  ⏭️  跳过（写入失败）")
            return
        
        record_id = result.get("record_id")
        
        # 第一个实例抢锁
        lock1 = self.relay.acquire_lock(record_id, "instance-1")
        
        # 第二个实例抢锁（应该失败）
        lock2 = self.relay.acquire_lock(record_id, "instance-2")
        
        self._assert(
            lock1 and not lock2,
            "锁竞争（只有一个成功）",
            f"lock1={lock1}, lock2={lock2}"
        )
    
    def test_tc07_lock_expiry(self):
        """TC-07: 锁过期"""
        print("\n【TC-07】锁过期测试")
        
        # 创建新消息
        msg_id = str(uuid.uuid4())
        result = self.relay.write_message({
            "msg_id": msg_id,
            "chat_id": "test_chat",
            "sender_id": self.bot_id,
            "receiver_id": "target_bot_id",
            "content": "锁过期测试"
        })
        
        if not result.get("success"):
            print("  ⏭️  跳过（写入失败）")
            return
        
        record_id = result.get("record_id")
        
        # 抢锁（设置很短的过期时间用于测试）
        self.relay.lock_timeout = 1  # 1秒过期
        lock1 = self.relay.acquire_lock(record_id, "instance-1")
        
        # 等待锁过期
        time.sleep(2)
        
        # 另一个实例应该能抢到锁
        self.relay.lock_timeout = 30  # 恢复默认
        lock2 = self.relay.acquire_lock(record_id, "instance-2")
        
        self._assert(
            lock1 and lock2,
            "锁过期后重新获取",
            f"lock1={lock1}, lock2={lock2}"
        )
    
    # ========== 注册表测试 ==========
    
    def test_registry(self):
        """测试 Bot 注册表"""
        print("\n【注册表测试】")
        
        # 测试获取所有 Bot
        bots = self.registry.get_all_bots()
        self._assert(
            isinstance(bots, list),
            "获取 Bot 列表",
            f"类型: {type(bots)}"
        )
        
        # 测试检查是否是 Bot
        is_bot = self.registry.is_bot(self.bot_id)
        # 如果 bot_id 在注册表中应该返回 True
        print(f"  ℹ️  {self.bot_id} 是否是注册 Bot: {is_bot}")


def main():
    parser = argparse.ArgumentParser(
        description="飞书 Bot 消息中继 - 测试脚本"
    )
    parser.add_argument("--app-token", required=True, help="Bitable app_token")
    parser.add_argument("--table-id-relay", required=True, help="消息队列表 ID")
    parser.add_argument("--table-id-registry", required=True, help="Bot 注册表 ID")
    parser.add_argument("--bot-id", required=True, help="测试 Bot 的 open_id")
    
    args = parser.parse_args()
    
    tester = RelayTester(
        app_token=args.app_token,
        table_id_relay=args.table_id_relay,
        table_id_registry=args.table_id_registry,
        bot_id=args.bot_id
    )
    
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
