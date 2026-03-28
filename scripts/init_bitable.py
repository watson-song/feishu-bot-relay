#!/usr/bin/env python3
"""
Bitable 初始化脚本
创建消息中继所需的两张表：
1. bot_message_relay - 消息队列
2. bot_registry - Bot 注册表

使用方法:
    python scripts/init_bitable.py --app-token xxx --folder-token xxx
    
或直接运行后按提示操作
"""

import argparse
import json


def get_relay_table_schema():
    """返回消息队列表结构定义"""
    return {
        "table_name": "bot_message_relay",
        "fields": [
            {"field_name": "msg_id", "type": 1, "property": {}},
            {"field_name": "chat_id", "type": 1, "property": {}},
            {"field_name": "chat_name", "type": 1, "property": {}},
            {"field_name": "sender_id", "type": 1, "property": {}},
            {"field_name": "sender_name", "type": 1, "property": {}},
            {"field_name": "receiver_id", "type": 1, "property": {}},
            {"field_name": "receiver_name", "type": 1, "property": {}},
            {"field_name": "content", "type": 1, "property": {}},
            {"field_name": "quote_msg_id", "type": 1, "property": {}},
            {
                "field_name": "status",
                "type": 3,  # 单选
                "property": {
                    "options": [
                        {"name": "待处理", "color": 0},
                        {"name": "处理中", "color": 1},
                        {"name": "已完成", "color": 2},
                        {"name": "失败", "color": 3}
                    ]
                }
            },
            {"field_name": "lock_holder", "type": 1, "property": {}},
            {"field_name": "lock_expire_at", "type": 5, "property": {}},  # 日期时间
            {"field_name": "created_at", "type": 5, "property": {}},
            {"field_name": "processed_at", "type": 5, "property": {}},
            {"field_name": "response", "type": 1, "property": {}},
        ]
    }


def get_registry_table_schema():
    """返回 Bot 注册表结构定义"""
    return {
        "table_name": "bot_registry",
        "fields": [
            {"field_name": "bot_id", "type": 1, "property": {}},
            {"field_name": "bot_name", "type": 1, "property": {}},
            {"field_name": "bot_type", "type": 1, "property": {}},
            {"field_name": "description", "type": 1, "property": {}},
            {"field_name": "is_active", "type": 7, "property": {}},  # 复选框
            {"field_name": "created_at", "type": 5, "property": {}},
            {"field_name": "updated_at", "type": 5, "property": {}},
        ]
    }


def print_init_guide(app_token: str, folder_token: str = None):
    """打印初始化指南"""
    relay_schema = get_relay_table_schema()
    registry_schema = get_registry_table_schema()
    
    print("=" * 60)
    print("飞书 Bot 消息中继 - Bitable 初始化指南")
    print("=" * 60)
    print()
    
    print("【步骤 1】创建 Bitable 应用（如未创建）")
    print("-" * 40)
    print(f"使用工具: feishu_bitable_create_app")
    print(f"参数:")
    if folder_token:
        print(f"  folder_token: {folder_token}")
    print(f"  name: BotMessageRelay")
    print()
    
    print("【步骤 2】创建消息队列表（bot_message_relay）")
    print("-" * 40)
    print(f"使用工具: feishu_bitable_app_table create")
    print(f"参数:")
    print(f"  app_token: {app_token}")
    print(f"  table: {json.dumps(relay_schema, indent=2, ensure_ascii=False)}")
    print()
    print("字段说明:")
    print("  - msg_id: 消息唯一ID（UUID）")
    print("  - chat_id: 群聊ID")
    print("  - sender_id/receiver_id: 发送/接收 Bot 的 open_id")
    print("  - content: 消息内容")
    print("  - status: 单选（待处理/处理中/已完成/失败）")
    print("  - lock_holder: 当前处理实例标识")
    print("  - lock_expire_at: 锁过期时间（日期时间）")
    print("  - created_at/processed_at: 创建/完成时间")
    print("  - response: Bot 的回复内容")
    print()
    
    print("【步骤 3】创建 Bot 注册表（bot_registry）")
    print("-" * 40)
    print(f"使用工具: feishu_bitable_app_table create")
    print(f"参数:")
    print(f"  app_token: {app_token}")
    print(f"  table: {json.dumps(registry_schema, indent=2, ensure_ascii=False)}")
    print()
    print("字段说明:")
    print("  - bot_id: Bot 的 open_id（主键）")
    print("  - bot_name: Bot 显示名称")
    print("  - bot_type: 类型/功能描述")
    print("  - description: 功能说明")
    print("  - is_active: 复选框（是否启用）")
    print("  - created_at/updated_at: 注册/更新时间")
    print()
    
    print("【步骤 4】邀请 Bot 加入 Bitable")
    print("-" * 40)
    print("操作：在 Bitable 中点击「分享」→「邀请协作者」")
    print("权限：所有 Bot 需要「可编辑」权限")
    print()
    
    print("【步骤 5】Bot 自动注册（推荐）")
    print("-" * 40)
    print("在 Bot 启动代码中添加：")
    print()
    print("from scripts.relay_client import BotRegistry")
    print()
    print("registry = BotRegistry(app_token, table_id_registry)")
    print("result = registry.auto_register(")
    print('    bot_id="ou_xxx",       # 本 Bot 的 open_id')
    print('    bot_name="MyBot",      # Bot 显示名称')
    print('    bot_type="AI助手",     # 类型')
    print('    description="负责消息处理"')
    print(")")
    print()
    print("# result['action'] 可能值：")
    print("#   'created'    - 新注册")
    print("#   'updated'    - 信息已更新（force_update=True 时）")
    print("#   'unchanged'  - 已存在，未变更")
    print()
    
    print("【步骤 6】记录配置信息")
    print("-" * 40)
    print("创建表后，记录以下信息用于 Bot 配置:")
    print(f"  app_token: {app_token}")
    print("  table_id_relay: （从步骤2获取）")
    print("  table_id_registry: （从步骤3获取）")
    print()
    
    print("=" * 60)
    print("初始化完成后，请更新各 Bot 的配置文件")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="初始化飞书 Bot 消息中继 Bitable",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/init_bitable.py --app-token xxx
  python scripts/init_bitable.py --app-token xxx --folder-token yyy
        """
    )
    parser.add_argument("--app-token", help="Bitable app token（如已有应用）")
    parser.add_argument("--folder-token", help="目标文件夹 token（可选）")
    
    args = parser.parse_args()
    
    if not args.app_token:
        print("【飞书 Bot 消息中继 - 初始化指南】")
        print()
        print("本脚本帮助您创建所需的 Bitable 表结构。")
        print()
        print("请提供以下信息：")
        print("  1. app_token: 现有 Bitable 应用的 token（如无，需先创建应用）")
        print("  2. folder_token: 可选，指定创建位置")
        print()
        print("运行示例:")
        print("  python scripts/init_bitable.py --app-token xxx")
        return
    
    print_init_guide(args.app_token, args.folder_token)
    
    # 输出 JSON 配置模板
    print()
    print("【OpenClaw 配置模板】")
    print("-" * 40)
    config = {
        "feishu_bot_relay": {
            "app_token": args.app_token,
            "table_id_relay": "待填写（创建 bot_message_relay 后获取）",
            "table_id_registry": "待填写（创建 bot_registry 后获取）",
            "bot_id": "本Bot的open_id",
            "poll_interval": 30,
            "lock_timeout": 30
        }
    }
    print(json.dumps(config, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
