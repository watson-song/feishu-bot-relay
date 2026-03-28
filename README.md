# 飞书 Bot 消息中转 Relay

基于飞书 Bitable 实现 **Bot → Bot** 的消息中转系统，解决飞书群聊中 Bot 无法互相 @ 的限制。

## 📋 背景

| 场景 | 飞书原生支持 | 解决方案 |
|------|-------------|---------|
| 用户 @ Bot | ✅ 支持 | 无需本系统 |
| Bot @ Bot（Bot 触发 Bot）| ❌ 不支持 | **使用本系统** |

## 🏗️ 架构

**去中心化设计**：每个 Bot 自行写入消息到 Bitable，同时轮询消费发给自己的消息。

```
Bot-A 需要触发 Bot-B
    ↓
Bot-A 写 Bitable (receiver_id=Bot-B)
    ↓
Bot-B 轮询发现 → 处理 → 回复群里
```

## 📁 文件结构

```
skills/feishu-bot-relay/
├── SKILL.md                  # 使用说明
├── REQUIREMENTS.md           # 详细需求文档（含测试用例）
├── config.example.json       # 配置示例
├── scripts/
│   ├── init_bitable.py       # Bitable 初始化脚本
│   ├── relay_client.py       # 核心客户端库
│   ├── poll_messages.py      # 消息轮询消费示例
│   ├── message_handler.py    # 消息处理器模板
│   └── test_relay.py         # 功能测试脚本
```

## 🚀 快速开始

### 1. 初始化 Bitable

```bash
python scripts/init_bitable.py --app-token xxx
```

根据提示创建两张表：
- `bot_message_relay` - 消息队列
- `bot_registry` - Bot 注册表

### 2. 配置 Bot

复制配置示例并填写：

```bash
cp config.example.json config.json
# 编辑 config.json 填写参数
```

### 3. 在 Bot 代码中使用

```python
from scripts.relay_client import RelayClient, BotRegistry

# 初始化
relay = RelayClient(app_token, table_id_relay)
registry = BotRegistry(app_token, table_id_registry)

# 写入消息（Bot-A 触发 Bot-B）
relay.write_message({
    "msg_id": str(uuid.uuid4()),
    "chat_id": chat_id,
    "sender_id": "Bot-A的open_id",
    "receiver_id": "Bot-B的open_id",
    "content": "需要处理的内容"
})

# 轮询消费（Bot-B 接收）
messages = relay.poll_messages(receiver_id="自已的open_id")
for msg in messages:
    if relay.acquire_lock(msg["record_id"], "instance-1"):
        # 处理消息
        response = process(msg)
        # 更新状态
        relay.update_status(msg["record_id"], "已完成", response)
        # 回复到群聊
        send_reply(chat_id, response)
```

### 4. 启动轮询

```bash
python scripts/poll_messages.py \
  --bot-id "ou_xxx" \
  --app-token "xxx" \
  --table-id-relay "xxx" \
  --table-id-registry "xxx" \
  --interval 30
```

## 🧪 测试

```bash
python scripts/test_relay.py \
  --app-token "xxx" \
  --table-id-relay "xxx" \
  --table-id-registry "xxx" \
  --bot-id "ou_xxx"
```

## 📊 数据模型

### bot_message_relay（消息队列）

| 字段 | 类型 | 说明 |
|------|------|------|
| msg_id | 文本 | 消息唯一ID |
| chat_id | 文本 | 群聊ID |
| sender_id | 文本 | 发送者 open_id |
| receiver_id | 文本 | 接收者 open_id |
| content | 文本 | 消息内容 |
| status | 单选 | 待处理/处理中/已完成/失败 |
| lock_holder | 文本 | 锁持有者 |
| lock_expire_at | 日期时间 | 锁过期时间 |

### bot_registry（Bot 注册表）

| 字段 | 类型 | 说明 |
|------|------|------|
| bot_id | 文本 | Bot open_id |
| bot_name | 文本 | 显示名称 |
| bot_type | 文本 | 类型/功能 |
| is_active | 复选框 | 是否启用 |

## 🔒 并发控制

- **锁机制**：抢锁时更新 `lock_holder` + `lock_expire_at`（30秒过期）
- **死锁处理**：锁过期后其他实例可重新抢锁
- **幂等写入**：相同 `msg_id` 不重复创建记录

## 📝 消息处理器

提供多种处理器模板：

```python
from scripts.message_handler import EchoHandler, CommandHandler, KeywordHandler

# 回声处理器
handler = EchoHandler(bot_id, bot_name)

# 命令处理器
handler = CommandHandler(bot_id, bot_name)
handler.register_command("query", query_func, "查询信息")

# 关键词处理器
handler = KeywordHandler(bot_id, bot_name)
handler.register_keyword("帮助", "我可以帮你...")
```

## ⚠️ 注意事项

1. **权限**：确保所有 Bot 被邀请加入 Bitable 并有「可编辑」权限
2. **轮询频率**：建议 10-30 秒，避免触发飞书 API 限流
3. **消息长度**：Bitable 文本字段约 1 万字符限制
4. **锁超时**：处理耗时任务时需定期续锁

## 📄 文档

- **需求文档**：`REQUIREMENTS.md`（含11个测试用例）
- **使用说明**：`SKILL.md`
- **API 文档**：代码内 docstring

## 🔧 开发状态

- ✅ 需求文档（v1.0）
- ✅ 核心客户端（RelayClient, BotRegistry）
- ✅ 消息处理器模板
- ✅ 轮询消费示例
- ✅ 测试脚本
- ⏳ 与 OpenClaw 工具集成（待测试）

## 📜 License

MIT
