#!/usr/bin/env python3
"""
获取当前 Bot 的 open_id 和基本信息

使用方法:
    python scripts/get_bot_info.py --app-id xxx --app-secret xxx
    
或在 OpenClaw 环境中直接获取（从消息上下文）
"""

import argparse
import json
import sys
from typing import Dict, Any


def get_bot_info_from_context() -> Dict[str, Any]:
    """
    从 OpenClaw 消息上下文获取 Bot 信息
    
    在 OpenClaw Skill 中使用：
        info = get_bot_info_from_context()
        print(f"我的 open_id: {info['open_id']}")
    
    Returns:
        {
            "open_id": "ou_xxx",
            "name": "Bot名称",
            "source": "context"
        }
    """
    # 注意：这个方法需要在 OpenClaw 运行时环境中使用
    # 实际使用时，从消息上下文的 sender_id 获取
    print("在 OpenClaw 中获取 Bot 信息的方法：")
    print()
    print("1. 在消息处理函数中：")
    print("   my_open_id = message_context.get('sender_id')")
    print()
    print("2. 或在 Skill 初始化时：")
    print("   # 收到任意消息后记录 sender_id")
    print("   self.bot_id = context['sender_id']")
    print()
    
    return {
        "open_id": None,
        "name": None,
        "source": "context",
        "note": "需要在 OpenClaw 运行时环境中使用"
    }


def get_bot_info_from_api(app_id: str, app_secret: str) -> Dict[str, Any]:
    """
    通过飞书 API 获取 Bot 信息
    
    需要：
    - app_id: 飞书应用的 App ID
    - app_secret: 飞书应用的 App Secret
    
    Returns:
        {
            "open_id": "ou_xxx",
            "name": "Bot名称",
            "source": "api"
        }
    """
    print(f"正在通过飞书 API 获取 Bot 信息...")
    print(f"App ID: {app_id[:8]}...")
    print()
    
    # 步骤 1: 获取 tenant_access_token
    print("步骤 1: 获取 tenant_access_token")
    print("POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal")
    print(f"Request Body: {{'app_id': '{app_id}', 'app_secret': '***'}}")
    print()
    
    # 步骤 2: 获取 Bot 自己的信息
    print("步骤 2: 获取 Bot 信息")
    print("GET https://open.feishu.cn/open-apis/contact/v3/users/me")
    print("Headers: {'Authorization': 'Bearer <tenant_access_token>'}")
    print()
    
    print("⚠️ 注意：实际的 API 调用需要在有网络访问权限的环境中执行")
    print()
    
    return {
        "open_id": None,
        "name": None,
        "source": "api",
        "note": "需要实现实际的 API 调用",
        "steps": [
            "1. POST /auth/v3/tenant_access_token/internal 获取 token",
            "2. GET /contact/v3/users/me 获取 Bot 信息"
        ]
    }


def get_bot_info_from_feishu_open(app_id: str) -> Dict[str, Any]:
    """
    引导用户从飞书开放平台获取
    
    Returns:
        操作指引
    """
    print("=" * 60)
    print("从飞书开放平台获取 Bot open_id")
    print("=" * 60)
    print()
    print("方法 1: 通过开发者后台查看")
    print("-" * 40)
    print("1. 登录 https://open.feishu.cn/")
    print("2. 进入应用管理 → 选择你的应用")
    print("3. 查看「事件订阅」→ 查看推送的消息格式")
    print("4. 在消息体中找到 'open_id' 字段")
    print()
    
    print("方法 2: 通过测试消息获取")
    print("-" * 40)
    print("1. 在你的 Bot 代码中添加调试输出：")
    print()
    print("   def on_message(context):")
    print('       print(f"我的 open_id: {context[\'sender_id\']}")')
    print()
    print("2. 发送一条消息到群里")
    print("3. 查看日志输出，获取 open_id")
    print()
    
    print("方法 3: 通过群成员列表")
    print("-" * 40)
    print("1. 调用飞书 API 获取群成员列表：")
    print()
    print(f"   GET /open-apis/im/v1/chats/{{chat_id}}/members")
    print()
    print("2. 在返回的成员列表中找到你的 Bot")
    print("3. 提取 member_id（即 open_id）")
    print()
    
    print("=" * 60)
    
    return {
        "open_id": None,
        "name": None,
        "source": "manual",
        "note": "请参考上方指引手动获取"
    }


def main():
    parser = argparse.ArgumentParser(
        description="获取 Bot 的 open_id",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查看获取方法
  python scripts/get_bot_info.py
  
  # 使用 API 获取（需要提供凭证）
  python scripts/get_bot_info.py --app-id xxx --app-secret xxx
        """
    )
    parser.add_argument("--app-id", help="飞书应用 App ID")
    parser.add_argument("--app-secret", help="飞书应用 App Secret")
    parser.add_argument("--method", choices=["context", "api", "manual"], 
                        default="manual", help="获取方式")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("飞书 Bot open_id 获取工具")
    print("=" * 60)
    print()
    
    if args.method == "api" and args.app_id and args.app_secret:
        result = get_bot_info_from_api(args.app_id, args.app_secret)
    elif args.method == "context":
        result = get_bot_info_from_context()
    else:
        result = get_bot_info_from_feishu_open(args.app_id)
    
    print()
    print("=" * 60)
    print("获取结果")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return 0 if result.get("open_id") else 1


if __name__ == "__main__":
    sys.exit(main())
