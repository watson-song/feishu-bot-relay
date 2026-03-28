---
name: feishu-bot-relay
description: 飞书 Bot 消息中转系统，基于 Bitable 实现 Bot 间通信。解决飞书限制：用户@Bot Bot能收到，但Bot之间无法@。需要两个前提：1) Bot有Bitable权限（通过邀请+封装SDK解决）；2) Bot知道群里哪些是Bot（通过bot_registry注册表解决）。去中心化设计：每个Bot写入消息到Bitable，同时轮询消费发给自己的消息。使用场景：(1) Bot-A需要触发Bot-B协作，(2) Bot间异步任务分发。触发条件：用户提及 bot间通信、bot协作、bitable消息队列、bot触发bot。
---

# 飞书 Bot 消息中转 Relay

基于飞书 Bitable 实现 **Bot → Bot** 的消息中转。

**适用范围**：
- ✅ 用户 @ Bot：直接走飞书消息，**不需要**此系统
- ✅ Bot @ Bot（Bot 触发 Bot）：飞书限制，**需要** Bitable 中转

**两个关键前提及解决方案**：

| 前提 | 问题 | 解决方案 |
|------|------|---------|
| Bot 需要 Bitable 能力 | Bot 开发者技术要求 | 封装 SDK，一行代码写入/轮询 |
| Bot 需要识别其他 Bot | 怎么知道 @ 的是 Bot 还是用户 | bot_registry 注册表，Bot 启动时读取 |

**设计**：去中心化，每个 Bot 自行写入，轮询消费。

## 快速开始

### 1. 环境准备

需要以下信息：
- Bitable `app_token`
- 表 1 `table_id`（bot_message_relay）
- 表 2 `table_id`（bot_registry）
- 本 Bot 的 `open_id`

### 关键前提如何解决？

**前提 1：Bot 需要会操作 Bitable**
- 本 Skill 提供封装好的 `relay_client.py`
- 写入消息只需 1 行代码：`relay.write_message(receiver_id, content)`
- 轮询消费只需几行代码即可启动

**前提 2：Bot 需要知道群里哪些是 Bot**
- 通过 `bot_registry` 表统一管理
- Bot 启动时读取注册表获取所有 Bot 的 ID
- 收到群消息时，检查 @ 目标是否在注册表中

### 什么时候使用？

| 场景 | 处理方式 |
|------|---------|
| 用户 @ 你的 Bot | **不使用**，直接处理飞书消息事件 |
| 你的 Bot 需要触发其他 Bot | **使用**，写 Bitable 让目标 Bot 接收 |

### 消息如何自动写入？

**⚠️ 重要：消息不会自动写入 Bitable！**

本 Skill 提供工具和方法，但**需要你在代码中显式调用**写入。

**Bot 收到 @ 消息后自动转发给其他 Bot：**

```python
from scripts.relay_client import RelayClient, BotRegistry

# 收到群消息时
def on_message(context):
    content = context["content"]
    
    # 检查是否 @ 了其他 Bot
    registry = BotRegistry(app_token, table_id_registry)
    
    # 解析消息中的 @ 目标
    for bot in registry.get_all_bots():
        if f"@{bot['bot_name']}" in content:
            # ⚠️ 这里显式写入 Bitable
            relay = RelayClient(app_token, table_id_relay)
            relay.write_message({
                "msg_id": str(uuid.uuid4()),
                "chat_id": context["chat_id"],
                "sender_id": context["sender_id"],
                "receiver_id": bot["bot_id"],  # 目标 Bot
                "content": content,
                "quote_msg_id": context["message_id"]
            })
            return f"已转发给 {bot['bot_name']}"
```

**总结：**
- ❌ 安装 Skill 不会自动拦截 @ 消息
- ✅ 需要你在 `on_message` 中显式调用 `write_message()`
- ✅ Skill 提供了封装好的工具，但调用权在你

---

### 初始化与注册

#### 1. 初始化 Bitable

运行初始化脚本创建表结构：

```bash
python scripts/init_bitable.py --app-token xxx --folder-token xxx
```

脚本会自动创建两张表：
- `bot_message_relay`：消息队列
- `bot_registry`：Bot 注册表

#### 2. Bot 自动注册

**重要：** 每个 Bot 启动时需要自动注册到 `bot_registry`，这样其他 Bot 才能识别它。

```python
from scripts.relay_client import BotRegistry

# 初始化注册表客户端
registry = BotRegistry(app_token, table_id_registry)

# 自动注册本 Bot
result = registry.auto_register(
    bot_id="ou_xxx",              # ⚠️ 必须是飞书 open_id（从消息上下文获取）
    bot_name="MyBot",            # Bot 显示名称
    bot_type="AI助手",          # 类型/功能
    description="负责消息处理",  # 详细说明
    force_update=False           # 是否强制更新已存在的记录
)

# 检查结果
if result["success"]:
    print(f"注册结果: {result['action']}")  # created / unchanged / updated
else:
    print(f"注册失败: {result['error']}")
```

**⚠️ 重要：所有 ID 必须是飞书 open_id**

`bot_id`、`sender_id`、`receiver_id` 都必须是飞书真实的 `open_id`，不是随意填写的字符串。

**如何获取 open_id：**

| 方法 | 适用场景 | 操作 |
|------|---------|------|
| 消息上下文 | OpenClaw 运行时 | 从 `sender_id` 字段获取 |
| 飞书开放平台 | 开发阶段 | 在应用后台查看 |
| 其他 Bot 告知 | 测试阶段 | 让其他 Bot 打印收到的消息中的 sender_id |

**方式 1：从消息上下文获取（推荐）**

在 OpenClaw 中收到消息时：
```python
# 消息上下文包含 sender_id
my_bot_id = "ou_620f451250ec7731cf0a54f401fe816f"  # 从 context['sender_id'] 获取
```

**方式 2：在群里测试获取**

在你的 Bot 代码中添加：
```python
def on_message(context):
    print(f"我的 open_id: {context['sender_id']}")
    print(f"我的名称: {context.get('sender_name', 'Unknown')}")
```

然后发一条消息到群里，查看日志输出。

**方式 3：使用提供的工具脚本**

```bash
# 查看获取方法
python scripts/get_bot_info.py

# 使用 API 获取（需要提供凭证）
python scripts/get_bot_info.py --app-id xxx --app-secret xxx --method api
```

**方式 4：自动注册时自动获取（推荐实现）**

在 OpenClaw Skill 中，收到第一条消息时自动记录：

```python
class MyBotSkill:
    def __init__(self):
        self.bot_id = None  # 初始化时未知
        
    def on_message(self, context):
        # 第一次收到消息时，记录自己的 open_id
        if not self.bot_id:
            self.bot_id = context["sender_id"]
            print(f"自动获取到 Bot open_id: {self.bot_id}")
            
            # 然后自动注册到 bot_registry
            registry = BotRegistry(app_token, table_id_registry)
            registry.auto_register(
                bot_id=self.bot_id,
                bot_name="MyBot",
                bot_type="AI助手"
            )
        
        # 处理消息...
```

**open_id 格式：**
- 以 `ou_` 开头
- 后面跟着一串字符和数字
- 示例：`ou_620f451250ec7731cf0a54f401fe816f`

**错误示例（不要用）：**
```python
bot_id="my_bot"           # ❌ 错误
bot_id="test_bot_001"     # ❌ 错误
bot_id="ou_test_jvsclaw"  # ❌ 错误（不是飞书分配的）
```

**正确示例（要用）：**
```python
bot_id="ou_620f451250ec7731cf0a54f401fe816f"  # ✅ 正确
```

**auto_register 返回值：**
- `action: "created"` - Bot 是新注册的
- `action: "unchanged"` - Bot 已存在，未变更（force_update=False）
- `action: "updated"` - Bot 信息已更新（force_update=True）

**重要提示：**
- 每个 Bot 启动时都应该调用 `auto_register()`
- 这样其他 Bot 才能通过 `get_bot_by_name()` 或 `is_bot()` 识别它
- 注册是幂等的，多次调用不会重复创建 

### 3. 配置 Bot

在 OpenClaw 配置中添加：

```json
{
  "feishu_bot_relay": {
    "app_token": "xxx",
    "table_id_relay": "bot_message_relay 的 table_id",
    "table_id_registry": "bot_registry 的 table_id",
    "bot_id": "本Bot的open_id",
    "poll_interval": 30,
    "lock_timeout": 30
  }
}
```

### 4. 启动轮询（⚠️ 必须）

**⚠️ 重要：必须启动轮询才能接收消息！**

安装本 Skill 后，**需要额外启动一个定时任务**来轮询 Bitable。这是去中心化设计的必然要求——每个 Bot 需要自己检查是否有新消息。

**方式 1：使用 cron 定时任务（推荐）**

在 OpenClaw 中配置定时任务：

```bash
# 每 30 秒轮询一次
openclaw cron add \
  --name "feishu-relay-poll" \
  --schedule "*/30 * * * * *" \
  --task "python scripts/poll_messages.py --bot-id '你的open_id' --app-token 'xxx' --table-id-relay 'xxx' --table-id-registry 'xxx'"
```

或使用 systemd/crontab：
```bash
# crontab -e
*/1 * * * * cd /path/to/feishu-bot-relay && python scripts/poll_messages.py --once >> /var/log/relay.log 2>&1
```

**方式 2：后台持续运行**

```bash
nohup python scripts/poll_messages.py \
  --bot-id "你的open_id" \
  --app-token "xxx" \
  --table-id-relay "xxx" \
  --table-id-registry "xxx" \
  --interval 30 \
  > relay.log 2>&1 &
```

**方式 3：集成到 OpenClaw Skill 中**

如果你开发的是 OpenClaw Skill，可以在收到普通消息时顺便检查：

```python
def on_message(context):
    # 处理普通消息...
    
    # 顺便检查 Bitable 中是否有给自己的消息
    messages = relay.poll_messages(receiver_id=self.bot_id)
    for msg in messages:
        process_relay_message(msg)
```

**方式 4：手动查询（仅测试）**

```bash
# 一次性查询（不持续轮询）
python scripts/poll_messages.py --once
```

---

## 核心接口

### ⚠️ 重要：如何使用本 Skill

本 Skill 提供 **两种使用方式**：

| 方式 | 适用场景 | 说明 |
|------|---------|------|
| **直接调用工具**（推荐） | OpenClaw Skill | 直接使用 `feishu_bitable_*` 工具 |
| **使用 SDK** | 独立运行 | 使用 `relay_client.py` 框架，需实现 API 调用 |

**为什么 relay_client.py 是模拟实现？**

`relay_client.py` 是**框架/SDK**，不是可直接运行的完整实现：
- ✅ 提供业务逻辑封装（锁、状态流转、去重）
- ✅ 提供接口定义
- ⚠️ `_create_record`、`_update_record` 等是**模拟实现**
- 实际使用时需要替换为真实 API 调用

---

### 方式 1：在 OpenClaw 中直接调用工具（推荐）

在 OpenClaw Skill 中，**不要**使用 `relay_client.py` 的模拟方法，而是直接调用 OpenClaw 提供的 `feishu_bitable_*` 工具：

```python
# 写入消息
def write_message(app_token, table_id, message):
    result = feishu_bitable_app_table_record(
        action="create",
        app_token=app_token,
        table_id=table_id,
        fields={
            "msg_id": message["msg_id"],
            "chat_id": message["chat_id"],
            "sender_id": message["sender_id"],
            "receiver_id": message["receiver_id"],
            "content": message["content"],
            "status": "待处理",
            "created_at": int(time.time() * 1000)
        }
    )
    return result

# 查询消息
def poll_messages(app_token, table_id, receiver_id):
    result = feishu_bitable_app_table_record(
        action="list",
        app_token=app_token,
        table_id=table_id,
        filter={
            "conjunction": "and",
            "conditions": [
                {"field_name": "receiver_id", "operator": "is", "value": [receiver_id]},
                {"field_name": "status", "operator": "is", "value": ["待处理"]}
            ]
        }
    )
    return result.get("records", [])
```

**这是推荐的使用方式**，因为：
- ✅ 直接调用真实的飞书 API
- ✅ 无需实现 `_create_record` 等模拟方法
- ✅ 简单直接

---

### 方式 2：使用 SDK 框架（独立运行）

如果你要在 OpenClaw 之外独立运行，可以使用 `relay_client.py` 框架，但需要实现 API 调用层：

```python
from scripts.relay_client import RelayClient

class MyRelayClient(RelayClient):
    def _create_record(self, fields):
        # 实现真实的创建记录逻辑
        # 例如：使用 requests 调用飞书 API
        pass
    
    def _update_record(self, record_id, fields):
        # 实现真实的更新记录逻辑
        pass
```

---

### 写入消息（发送 Bot）

当 Bot 需要触发其他 Bot 时，**直接调用 OpenClaw 工具**：

```python
import uuid

# 直接调用 feishu_bitable_app_table_record 工具
feishu_bitable_app_table_record(
    action="create",
    app_token=app_token,
    table_id=table_id_relay,
    fields={
        "msg_id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "sender_id": "ou_xxx",               # ⚠️ 本Bot的真实open_id
        "receiver_id": "ou_yyy",             # ⚠️ 目标Bot的真实open_id
        "content": "需要处理的内容",
        "status": "待处理",
        "created_at": int(time.time() * 1000)
    }
)
```

**注意：** `sender_id` 和 `receiver_id` 必须是飞书真实的 `open_id`，格式为 `ou_` 开头。

### 轮询消息（接收 Bot）

```python
import time

# 使用 OpenClaw 工具轮询
messages = feishu_bitable_app_table_record(
    action="list",
    app_token=app_token,
    table_id=table_id_relay,
    filter={
        "conjunction": "and",
        "conditions": [
            {"field_name": "receiver_id", "operator": "is", "value": [my_bot_id]},
            {"field_name": "status", "operator": "is", "value": ["待处理"]}
        ]
    }
)

for record in messages.get("records", []):
    fields = record["fields"]
    record_id = record["record_id"]
    
    # 抢锁（更新状态为"处理中"）
    feishu_bitable_app_table_record(
        action="update",
        app_token=app_token,
        table_id=table_id_relay,
        record_id=record_id,
        fields={
            "status": "处理中",
            "lock_holder": "instance-1",
            "lock_expire_at": int(time.time() * 1000) + 30000  # 30秒后过期
        }
    )
    
    # 处理消息
    response = process_message(fields["content"])
    
    # 更新状态为"已完成"
    feishu_bitable_app_table_record(
        action="update",
        app_token=app_token,
        table_id=table_id_relay,
        record_id=record_id,
        fields={
            "status": "已完成",
            "response": response,
            "processed_at": int(time.time() * 1000)
        }
    )
```

### 读取 Bot 注册表

```python
# 查询所有 Bot
bots = feishu_bitable_app_table_record(
    action="list",
    app_token=app_token,
    table_id=table_id_registry
)

# 按名称查找
for record in bots.get("records", []):
    fields = record["fields"]
    if fields.get("bot_name") == "Bot-A":
        bot_id = fields.get("bot_id")
```

## 并发控制

使用乐观锁机制防止重复处理：

1. 轮询时只查询 `status=待处理` 或锁已过期的消息
2. 抢锁时更新 `lock_holder` 和 `lock_expire_at`
3. 处理期间每 10 秒续锁
4. 处理完成释放锁并更新状态

锁过期时间：30 秒（可配置）

## 错误处理

| 错误类型 | 处理策略 |
|---------|---------|
| 飞书限流 | 指数退避重试（1s, 2s, 4s, 8s, 16s）|
| 锁竞争失败 | 放弃本次，下次轮询再试 |
| 处理异常 | 更新 status=失败，记录错误信息 |
| 消息重复 | 幂等处理，返回已存在记录 |

## 完整使用示例

```python
import uuid
import time

# 配置
APP_TOKEN = "xxx"
TABLE_RELAY = "xxx"
TABLE_REGISTRY = "xxx"
MY_BOT_ID = "ou_xxx"  # ⚠️ 必须是本Bot的真实open_id（从飞书消息上下文获取）

# 场景：收到用户消息，需要 Bot-B 协作
def on_user_message(chat_id, sender_id, content):
    # 1. 查询 Bot-B 的 open_id
    bots = feishu_bitable_app_table_record(
        action="list",
        app_token=APP_TOKEN,
        table_id=TABLE_REGISTRY,
        filter={
            "conjunction": "and",
            "conditions": [{"field_name": "bot_name", "operator": "is", "value": ["Bot-B"]}]
        }
    )
    
    target_bot = None
    for record in bots.get("records", []):
        if record["fields"].get("bot_name") == "Bot-B":
            target_bot = record["fields"]
            break
    
    if not target_bot:
        return "Bot-B 未注册"
    
    # 2. 写入消息到 Bitable
    feishu_bitable_app_table_record(
        action="create",
        app_token=APP_TOKEN,
        table_id=TABLE_RELAY,
        fields={
            "msg_id": str(uuid.uuid4()),
            "chat_id": chat_id,
            "sender_id": MY_BOT_ID,                              # 本Bot的真实open_id
            "receiver_id": target_bot.get("bot_id"),             # 目标Bot的真实open_id
            "content": f"用户 {sender_id} 请求：{content}",
            "status": "待处理",
            "created_at": int(time.time() * 1000)
        }
    )
    
    return "已转发给 Bot-B 处理"

# 场景：轮询消费其他 Bot 发给我的消息
def poll_and_process():
    # 查询发给我的待处理消息
    messages = feishu_bitable_app_table_record(
        action="list",
        app_token=APP_TOKEN,
        table_id=TABLE_RELAY,
        filter={
            "conjunction": "and",
            "conditions": [
                {"field_name": "receiver_id", "operator": "is", "value": [MY_BOT_ID]},
                {"field_name": "status", "operator": "is", "value": ["待处理"]}
            ]
        }
    )
    
    for record in messages.get("records", []):
        record_id = record["record_id"]
        fields = record["fields"]
        
        # 抢锁
        feishu_bitable_app_table_record(
            action="update",
            app_token=APP_TOKEN,
            table_id=TABLE_RELAY,
            record_id=record_id,
            fields={
                "status": "处理中",
                "lock_holder": "instance-1",
                "lock_expire_at": int(time.time() * 1000) + 30000
            }
        )
        
        try:
            # 处理消息
            result = process_message(fields["content"])
            
            # 更新状态为已完成
            feishu_bitable_app_table_record(
                action="update",
                app_token=APP_TOKEN,
                table_id=TABLE_RELAY,
                record_id=record_id,
                fields={
                    "status": "已完成",
                    "response": result,
                    "processed_at": int(time.time() * 1000)
                }
            )
            
            # 回复到群聊
            send_reply(fields["chat_id"], result)
            
        except Exception as e:
            # 更新状态为失败
            feishu_bitable_app_table_record(
                action="update",
                app_token=APP_TOKEN,
                table_id=TABLE_RELAY,
                record_id=record_id,
                fields={
                    "status": "失败",
                    "response": str(e)
                }
            )

if __name__ == "__main__":
    # 启动轮询
    while True:
        poll_and_process()
        time.sleep(30)
```

## 相关文件

- `REQUIREMENTS.md` - 详细需求文档和测试用例
- `scripts/init_bitable.py` - Bitable 初始化脚本
- `scripts/relay_client.py` - 核心客户端库（含 BotRegistry）
- `scripts/poll_messages.py` - 轮询消费示例
- `scripts/message_handler.py` - 消息处理模板

## 注意事项

1. Bitable 文本字段有长度限制（约 1 万字符），超长消息会被截断
2. 轮询频率建议 10-30 秒，避免触发飞书 API 限流
3. 每个 Bot 实例应有唯一的 `lock_holder` 标识
4. 定期清理已完成的消息（可配置保留天数）
5. 确保所有 Bot 都被邀请加入 Bitable 并有编辑权限
