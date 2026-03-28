# 飞书 Bot 消息中转 Relay 需求文档

## 1. 项目概述

### 1.1 背景
飞书群聊限制：**Bot 之间无法互相 @**。用户 @ Bot 时 Bot 能直接收到消息，但 Bot 需要触发其他 Bot 协作时，无法直接 @。

本方案通过飞书 Bitable 作为消息队列，实现 **Bot → Bot** 的间接通信。

### 1.2 目标
- 解决 Bot 之间无法 @ 的限制
- 实现 Bot 间协作的消息中转
- 低成本、易部署、无需自建服务端

### 1.3 适用范围
| 场景 | 是否需要 Bitable | 说明 |
|------|-----------------|------|
| 用户 @ Bot | ❌ 不需要 | Bot 直接收到飞书消息 |
| Bot @ Bot | ✅ 需要 | 通过 Bitable 中转 |

### 1.4 关键前提与解决方案

#### 前提 1：Bot 需要 Bitable 操作能力

**问题**：每个 Bot 都需要能读写 Bitable，这对 Bot 开发者有技术要求。

**解决方案**：
1. **权限配置**：Bitable 创建者邀请所有 Bot 加入，授予「可编辑」权限
2. **封装 SDK**：提供统一的 `relay_client.py`，Bot 开发者只需调用简单方法：
   ```python
   # 写入消息（1行代码）
   relay.write_message(receiver_id="Bot-B", content="...")
   
   # 轮询消费（几行代码）
   for msg in relay.poll_messages():
       handle(msg)
   ```
3. **配置简化**：Bot 只需配置 `app_token`, `table_id`, `bot_id` 三个参数

#### 前提 2：Bot 需要知道群里哪些人是 Bot

**问题**：Bot 如何识别消息中的 @ 目标是另一个 Bot（而不是用户）？

**解决方案**：

**方案 A：Bot 注册表（推荐）**
在 Bitable 中创建第二张表 `bot_registry`：

| 字段 | 说明 |
|------|------|
| bot_id | Bot 的 open_id |
| bot_name | Bot 显示名称 |
| bot_type | 类型标识 |
| webhook_url | 可选：回调地址 |
| is_active | 是否在线 |

Bot 启动时：
1. 读取 `bot_registry` 获取所有 Bot 的 ID
2. 收到群消息时，检查 @ 的目标是否在列表中
3. 如果是 Bot，写 `bot_message_relay` 表触发它

**方案 B：命名约定**
所有 Bot 名称统一前缀，如 `Bot-XXX`，通过名称前缀识别。

**方案 C：群成员查询**
Bot 定期调用飞书 API 获取群成员列表，根据 `user_id` 特征（或企业内预定义的 Bot 列表）识别。

**推荐**：方案 A（Bot 注册表），简单可靠，支持动态增删 Bot。

---

## 2. 系统架构

```
+-------------+      +----------------+      +-------------+
| 群聊消息    |      | Bitable 消息表 |      | Bot-B       |
| (用户/Bot)  |      | (消息队列)     |      | (轮询消费)  |
+------+------+      +--------+-------+      +------+------+
       |                      |                      |
       |              +-------+-------+              |
       |              |               |              |
       +------------->|  Bot-A 写入   |<-------------+
                      |  (发送前)     |
                      +---------------+
```

**说明**：无中心中转节点，每个 Bot 自行写入消息到 Bitable，同时轮询消费发给自已的消息。

---

## 3. 数据模型

### 3.1 Bitable 表结构

本系统需要 **两张表**：

#### 表 1：bot_message_relay（消息队列）

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| msg_id | 文本 | 是 | 消息唯一ID (UUID)，主键 |
| chat_id | 文本 | 是 | 飞书群聊ID |
| chat_name | 文本 | 否 | 群聊名称（可读性）|
| sender_id | 文本 | 是 | 发送者 open_id |
| sender_name | 文本 | 否 | 发送者昵称 |
| receiver_id | 文本 | 是 | 接收 Bot 的 open_id |
| receiver_name | 文本 | 否 | 接收 Bot 名称 |
| content | 文本 | 是 | 消息内容（纯文本或JSON）|
| quote_msg_id | 文本 | 否 | 引用的原消息ID |
| status | 单选 | 是 | 待处理/处理中/已完成/失败 |
| lock_holder | 文本 | 否 | 当前处理实例标识 |
| lock_expire_at | 日期时间 | 否 | 锁过期时间 |
| created_at | 日期时间 | 是 | 创建时间 |
| processed_at | 日期时间 | 否 | 处理完成时间 |
| response | 文本 | 否 | Bot 的回复内容 |

#### 表 2：bot_registry（Bot 注册表）

用于 Bot 识别其他 Bot，解决"哪些人是 Bot"的问题。

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| bot_id | 文本 | 是 | Bot 的 open_id，主键 |
| bot_name | 文本 | 是 | Bot 显示名称 |
| bot_type | 文本 | 否 | Bot 类型/功能描述 |
| description | 文本 | 否 | 功能说明 |
| is_active | 复选框 | 是 | 是否在线启用 |
| created_at | 日期时间 | 是 | 注册时间 |
| updated_at | 日期时间 | 否 | 最后更新时间 |

### 3.2 状态流转

```
待处理 --> 处理中 --> 已完成
   |         |
   +----> 失败（可重试）
```

**状态说明**:
- `待处理`: 消息已写入，等待 Bot 消费
- `处理中`: Bot 已抢到锁，正在处理
- `已完成`: 消息处理完毕，已回复
- `失败`: 处理异常，可人工或自动重试

---

## 4. 功能需求

### 4.1 核心功能

#### F1: 消息写入（Bot → Bot）
**描述**: 当 Bot-A 需要触发 Bot-B 时，将消息写入 Bitable
**触发场景**: 
- Bot-A 收到用户请求，发现需要 Bot-B 的专业能力
- Bot-A 主动需要 Bot-B 执行某个任务
- 任何 Bot 间协作场景
**输入**: sender_id(自已), receiver_id(目标Bot), content(消息内容)
**输出**: Bitable 新记录
**异常**: 重复消息（通过 msg_id 去重）

#### F2: 消息轮询
**描述**: 每个 Bot 定期查询 Bitable，获取发给自已的待处理消息
**输入**: Bot open_id, 轮询间隔
**输出**: 待处理消息列表
**异常**: 限流、超时

#### F3: 消息处理
**描述**: Bot 处理消息并回复
**输入**: 消息内容
**处理**: 业务逻辑处理
**输出**: 回复内容
**异常**: 处理失败，更新状态为"失败"

#### F4: 状态更新
**描述**: 处理完成后更新消息状态
**输入**: msg_id, 新状态, 回复内容
**输出**: 更新成功/失败

### 4.2 并发控制

#### F5: 锁机制
**描述**: 防止同一消息被重复处理
**实现**:
1. 轮询时只查询 `status=待处理` 或 `(status=处理中 AND lock_expire_at < now)`
2. 抢锁时更新 `lock_holder` 和 `lock_expire_at`（当前时间+30秒）
3. 处理期间定期续锁（每10秒）
4. 处理完成释放锁并更新状态

#### F6: 死锁处理
**描述**: 处理 Bot 崩溃导致锁未释放
**实现**: 锁过期时间机制，30秒后自动释放

### 4.3 辅助功能

#### F7: 消息去重
**描述**: 防止重复写入同一条消息
**实现**: msg_id 使用飞书消息ID，写入前检查是否已存在

#### F8: 目标 Bot 识别
**描述**: Bot 根据 receiver_id 判断消息是否是发给自已的
**实现**: 轮询时筛选 receiver_id = 自已 open_id 的记录

---

## 5. 接口定义

### 5.1 内部接口（Bot 实现）

```typescript
interface MessageRelay {
  // 写入消息（中转 Bot 调用）
  writeMessage(msg: RelayMessage): Promise<void>;
  
  // 轮询消息（消费 Bot 调用）
  pollMessages(receiverId: string): Promise<RelayMessage[]>;
  
  // 抢锁（消费 Bot 调用）
  acquireLock(msgId: string, holder: string): Promise<boolean>;
  
  // 续锁（消费 Bot 调用）
  renewLock(msgId: string, holder: string): Promise<boolean>;
  
  // 更新状态（消费 Bot 调用）
  updateStatus(msgId: string, status: Status, response?: string): Promise<void>;
}

interface RelayMessage {
  msg_id: string;
  chat_id: string;
  sender_id: string;
  receiver_id: string;
  content: string;
  quote_msg_id?: string;
  created_at: string;
}

type Status = '待处理' | '处理中' | '已完成' | '失败';
```

---

## 6. 使用流程

### 6.1 初始化流程

1. 创建飞书 Bitable，按 3.1 配置字段
2. 邀请所有 Bot 加入 Bitable（编辑权限）
3. 配置 Bot 的 open_id 映射表

### 6.2 消息流转

**场景 A：用户 @ Bot（无需 Bitable）**
```
用户 @Bot-A: "帮我分析数据"
        ↓
Bot-A 直接收到飞书消息事件（原有机制）
        ↓
Bot-A 处理或决定需要 Bot-B 协作
```

**场景 B：Bot-A 需要触发 Bot-B（需要 Bitable）**
```
Bot-A 决定需要 Bot-B 协作
        ↓
Bot-A 写 Bitable（receiver_id=Bot-B 的 open_id）
   - msg_id: 唯一ID
   - sender_id: Bot-A 的 open_id
   - receiver_id: Bot-B 的 open_id
   - content: 需要传递的内容
   - status: 待处理
        ↓
Bot-B 轮询（每 30 秒）
   - 查询 receiver_id=自己 AND status=待处理
        ↓
Bot-B 抢到锁，更新 status=处理中
        ↓
Bot-B 处理消息
        ↓
Bot-B 更新 status=已完成
        ↓
Bot-B 直接回复到飞书群聊（@ 用户 或 @ Bot-A）
        ↓
用户看到 Bot-B 的回复
```

### 6.3 异常处理流程

**场景 1: Bot-B 处理超时**
- lock_expire_at 过期后，其他实例或重试逻辑可重新抢锁

**场景 2: Bot-B 崩溃**
- 重启后重新轮询，处理 lock_expire_at 已过期但 status=处理中 的消息

**场景 3: 重复写入**
- 使用 msg_id 去重，重复写入返回成功（幂等）

---

## 7. 测试用例

### 7.1 功能测试

| 用例ID | 场景 | 步骤 | 预期结果 |
|--------|------|------|----------|
| TC-01 | 正常消息写入 | 用户@Bot，中转Bot写入 | Bitable新增记录，status=待处理 |
| TC-02 | 消息轮询 | Bot查询自己的待处理消息 | 返回未处理消息列表 |
| TC-03 | 消息处理 | Bot抢锁、处理、更新状态 | status=已完成，有回复内容 |
| TC-04 | 消息回复 | Bot处理完回复到群聊 | 群聊出现Bot的回复消息 |
| TC-05 | 消息去重 | 同一消息重复写入 | 第二次写入不报错，不新增记录 |

### 7.2 并发测试

| 用例ID | 场景 | 步骤 | 预期结果 |
|--------|------|------|----------|
| TC-06 | 重复处理 | 两个实例同时抢同一条消息 | 只有一个实例成功处理 |
| TC-07 | 锁过期 | 实例抢锁后崩溃，锁过期 | 其他实例可重新抢锁处理 |
| TC-08 | 锁续期 | 长耗时任务持续处理 | 锁被定期续期，不被其他实例抢走 |

### 7.3 异常测试

| 用例ID | 场景 | 步骤 | 预期结果 |
|--------|------|------|----------|
| TC-09 | 处理失败 | Bot处理抛出异常 | status=失败，可人工查看 |
| TC-10 | 限流处理 | 高频轮询触发飞书限流 | 指数退避重试，不丢失消息 |
| TC-11 | 消息体过大 | content超过Bitable限制 | 截断或分片存储，记录日志 |

---

## 8. 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 消息延迟 | < 35 秒 | 轮询间隔30秒 + 处理5秒 |
| 去重准确率 | 100% | 不允许重复处理 |
| 消息丢失率 | 0% | 至少投递一次 |
| 并发处理能力 | 支持10个Bot | 每个Bot独立轮询 |

---

## 9. 部署清单

### 9.1 Bitable 准备

- [ ] 创建飞书 Bitable
- [ ] 创建表 1：`bot_message_relay`，配置字段（见 3.1）
- [ ] 创建表 2：`bot_registry`，配置字段（见 3.1）
- [ ] 邀请所有 Bot 加入 Bitable，授予「可编辑」权限
- [ ] 获取 `app_token` 和两个 `table_id`

### 9.2 Bot 注册

- [ ] 在 `bot_registry` 表中注册所有 Bot：
  - bot_id: Bot 的 open_id
  - bot_name: 显示名称
  - is_active: 勾选启用
- [ ] 每个 Bot 配置中记录其他 Bot 的 ID 映射（或运行时读取 registry）

### 9.3 Bot 部署

- [ ] 每个 Bot 配置 `app_token`, `table_id`（relay）, `table_id`（registry）
- [ ] 每个 Bot 部署轮询消费逻辑
- [ ] 每个 Bot 实现写入逻辑（需要触发其他 Bot 时调用）
- [ ] 验证端到端消息流转

### 9.4 权限检查

- [ ] 确认所有 Bot 能正常读写 `bot_message_relay`
- [ ] 确认所有 Bot 能正常读取 `bot_registry`
- [ ] 确认 Bot 能正常发送群消息

---

## 10. 附录

### 10.1 飞书 API 权限需求

| API | 权限 | 用途 |
|-----|------|------|
| 读取 Bitable | bitable:record:read | 轮询消息 |
| 写入 Bitable | bitable:record:write | 写入消息、更新状态 |
| 读取群消息 | im:message.group_msg | 中转 Bot 监听消息 |
| 发送群消息 | im:message:send | Bot 回复消息 |

### 10.2 字段类型映射

| 逻辑类型 | Bitable 字段类型 | 字段属性 |
|----------|------------------|----------|
| UUID | 文本 | 无 |
| open_id | 文本 | 无 |
| 消息内容 | 文本 | 允许多行 |
| 状态 | 单选 | 选项：待处理/处理中/已完成/失败 |
| 日期时间 | 日期 | 格式：日期时间 |

---

文档版本: v1.0
创建日期: 2026-03-28
