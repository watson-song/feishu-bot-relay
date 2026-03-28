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

### 4. 启动轮询

每个 Bot 独立启动轮询：

```bash
python scripts/poll_messages.py \
  --bot-id "Bot-B的open_id" \
  --app-token "xxx" \
  --table-id-relay "xxx" \
  --table-id-registry "xxx"
```

## 核心接口

### 写入消息（发送 Bot）

当 Bot 需要触发其他 Bot 时：

```python
from scripts.relay_client import RelayClient

client = RelayClient(app_token, table_id_relay)
client.write_message({
    "msg_id": generate_uuid(),           # 唯一消息ID
    "chat_id": chat_id,
    "sender_id": "ou_xxx",               # ⚠️ 本Bot的真实open_id
    "receiver_id": "ou_yyy",             # ⚠️ 目标Bot的真实open_id（从bot_registry查询）
    "content": "需要处理的内容",
    "quote_msg_id": original_message_id  # 可选：引用的原消息
})
```

**注意：** `sender_id` 和 `receiver_id` 必须是飞书真实的 `open_id`，格式为 `ou_` 开头。

### 轮询消息（接收 Bot）

```python
messages = client.poll_messages(receiver_id="本Bot的open_id")
for msg in messages:
    if client.acquire_lock(msg["msg_id"], holder="instance-1"):
        # 处理消息
        response = process_message(msg)
        # 更新状态
        client.update_status(msg["msg_id"], "已完成", response)
        # 回复到群聊
        send_to_chat(chat_id, response)
```

### 读取 Bot 注册表

```python
from scripts.relay_client import BotRegistry

registry = BotRegistry(app_token, table_id_registry)
bots = registry.get_all_bots()  # 获取所有 Bot
bot = registry.get_bot_by_name("Bot-A")  # 按名称查找
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
from scripts.relay_client import RelayClient, BotRegistry

# 配置
APP_TOKEN = "xxx"
TABLE_RELAY = "xxx"
TABLE_REGISTRY = "xxx"
MY_BOT_ID = "ou_xxx"  # ⚠️ 必须是本Bot的真实open_id（从飞书消息上下文获取）

# 初始化
relay = RelayClient(APP_TOKEN, TABLE_RELAY)
registry = BotRegistry(APP_TOKEN, TABLE_REGISTRY)

# 场景：收到用户消息，需要 Bot-B 协作
def on_user_message(chat_id, sender_id, content):
    # 1. 检查是否需要其他 Bot
    target_bot = registry.get_bot_by_name("Bot-B")
    if not target_bot:
        return "Bot-B 未注册"
    
    # 2. 写入消息到 Bitable
    # ⚠️ sender_id 和 receiver_id 必须是真实的 open_id
    relay.write_message({
        "msg_id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "sender_id": MY_BOT_ID,                    # 本Bot的真实open_id
        "receiver_id": target_bot["bot_id"],       # 目标Bot的真实open_id
        "content": f"用户 {sender_id} 请求：{content}"
    })
    
    return "已转发给 Bot-B 处理"

# 场景：轮询消费其他 Bot 发给我的消息
def poll_and_process():
    # ⚠️ receiver_id 必须是本Bot的真实open_id
    messages = relay.poll_messages(receiver_id=MY_BOT_ID)
    
    for msg in messages:
        # 抢锁
        if not relay.acquire_lock(msg["msg_id"], holder="instance-1"):
            continue
        
        try:
            # 处理消息
            result = process(msg["content"])
            
            # 更新状态
            relay.update_status(msg["msg_id"], "已完成", result)
            
            # 回复到群聊
            send_reply(msg["chat_id"], result)
            
        except Exception as e:
            relay.update_status(msg["msg_id"], "失败", str(e))

if __name__ == "__main__":
    # 启动轮询
    import time
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
