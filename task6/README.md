# Task6：长期记忆与人机审批（ch08 + ch09）

> 资料来源声明：本目录练习改编自 Datawhale《DeepAgents 实战》课程
> [ch08 长期记忆](https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/) 与
> [ch09 Human-in-the-Loop](https://datawhalechina.github.io/deepagents-in-action/chapters/ch09-human-in-the-loop/)。
> 完整引用清单见[仓库根 README](../README.md#引用与致谢)。

## 目录

- [长期记忆与人机审批.png](./长期记忆与人机审批.png) — 本章思维导图（代码渲染）
- [code/memory_loading.py](./code/memory_loading.py) — memory 全文注入与会话快照（5 条断言，零 token）
- [code/memory_scope.py](./code/memory_scope.py) — 短期 StateBackend vs 长期 StoreBackend（5 条断言，零 token）
- [code/skills_index_cost.py](./code/skills_index_cost.py) — 技能索引 token 成本实测（真实模型 Agnes）
- [code/hitl_approval.py](./code/hitl_approval.py) — 中断 → 审批 → 恢复全链路（4 条断言，零 token）
- [code/hitl_replay.py](./code/hitl_replay.py) — 证明 resume 会从头重放（1 条断言）
- [code/hitl_reject_vs_respond.py](./code/hitl_reject_vs_respond.py) — reject 与 respond 对照（3 条断言）
- [outputs/](./outputs/) — 六份真实运行日志
- [mindmap.py](./mindmap.py) — 导图生成脚本

## 本章核心一句话

**Memory 与 Skills 是同一副骨架、一处相反：memory 塞全文、skills 塞索引。**
由此推出记忆的成本结构（全文 × 每轮调用）与存储结构（StateBackend=按 thread 短期，StoreBackend=跨 thread 长期）；
而 HITL 的本质不是弹窗，是 **interrupt() 抛异常暂停 + checkpoint 存档 + resume 从节点开头重放**。

## 打卡：统一要求五项

### 1. 验证什么

| 脚本 | 验证的命题 | 断言数 |
|---|---|---|
| `memory_loading.py` | memory 全文进提示词；skills 只进索引；HTML 注释被剥；同 thread 不重载；换 thread 重载 | 5 |
| `memory_scope.py` | `/memories/` 进 Store 且不留 state；`/notes.txt` 进 state；换 thread 短期消失长期仍在；namespace 隔离；前缀剥离 | 5 |
| `skills_index_cost.py` | 开 skills 的固定开销；每技能边际开销；每轮重复计费 | 3 组数字 |
| `hitl_approval.py` | 中断时可读到申请单；暂停时工具未执行；approve 后执行；reject 后不执行且回 error | 4 |
| `hitl_replay.py` | resume 时 `interrupt()` 之前的代码执行两次（从头重放） | 1 |
| `hitl_reject_vs_respond.py` | 两者都不执行工具，但 reject 回 `error`、respond 回 `success` | 3 |

### 2. 改了什么

1. **零 token 取证**：沿用 task5 的"录制型假模型"，并升级为**脚本化模型**——按顺序吐出指定的工具调用，
   因此 `write_file`、`delete_file`、`interrupt()` 这些真实链路都能确定性走完，不依赖模型"配合"。
2. **把口语结论变成数字**：ch07 一直说"索引是每轮租金"，本次用真实模型（Agnes）测出 414 / 43 两个数字。
3. **对照实验代替文字解释**：`reject` 与 `respond` 用**同一场景、同一句 message** 跑两遍，只改决策类型。
4. **证明"从头重放"**：在 `interrupt()` 之前放一个计数器，resume 后计数从 1 变 2。
5. **每个场景新建 agent**：编译好的图在构建时就绑定了模型，运行期改 `.model` 不生效（第一版踩过）。

### 3. 实际结果

**实验 A：memory 全文注入**（`outputs/memory_loading.log`）

| 轮次 | 旧记忆 8801 | 新记忆 9999 | skills 正文 |
|---|---|---|---|
| 第 1 轮（t1） | ✓ | ✗ | ✗ |
| 第 2 轮（同 t1） | ✓ | ✗ | ✗ |
| 第 3 轮（新 t2） | ✗ | ✓ | ✗ |

`state["memory_contents"]` 只有 `/memories/preferences.md` 一个键；`skills_metadata` 有 1 条（对照成立）。

**实验 B：短期 vs 长期**（`outputs/memory_scope.log`）

```
场景 1：state['files'] = ['/notes.txt']；Store 里 = 张三喜欢简洁代码，注释中文
场景 2（换 thread）：state['files'] = []；新线程提示词含记忆全文 = True
场景 3：user-456 读 /preferences.md = None
```

**实验 C：索引 token 成本**（`outputs/skills_index_cost.log`，真实模型）

| 配置 | input_tokens | 说明 |
|---|---|---|
| `skills=None` | 2 794 | 基线 |
| `skills=[]` | 3 208 | 固定开销 **+414** |
| `skills=3` | 3 337 | 每技能 **≈43** |
| `skills=8` | 3 552 | 每技能 **≈43** |
| 同 thread 两次调用 | 3 337 / 3 337 | 每轮重付 |

**实验 D：HITL 审批**（`outputs/hitl_approval.log`）

```
[1/4] 中断发生，action_requests 含工具名/参数，review_configs 含允许决策
[2/4] 暂停时 delete_file 未执行
[3/4] approve 恢复后，delete_file 按原参数执行了一次
[4/4] reject 恢复后，delete_file 未执行，模型收到 status=error 的拒绝消息
```

**实验 E：从头重放**（`outputs/hitl_replay.log`）

```
第一次 invoke 后  ENTERED: ['第 1 次进入 after_model']
resume 之后       ENTERED: ['第 1 次进入 after_model', '第 2 次进入 after_model']
```

**实验 F：reject vs respond**（`outputs/hitl_reject_vs_respond.log`）

| | 工具执行 | AI 收到的 status | AI 收到的内容 |
|---|---|---|---|
| reject | 0 | `error` | `User rejected ... with reason: 不要删除，改为归档。` |
| respond | 0 | `success` | `不要删除，改为归档。` |

### 4. 证据与解释

- **Memory 是全文加载**：`memory.py:295` 按精确路径 `download_files`（skills 是 `ls` 目录）、`:303` 存全文、`:356` 每次调用拼进 system prompt。所以成本 = 全文 × 调用次数。
- **HTML 注释被剥**：`memory.py:171-175` 定义正则、`:262` 在拼接前删除。模型看到的是"处理后的全文"。
- **缺失文件静默跳过**：`memory.py:296-301` 对 `file_not_found` 直接 `continue`，连 warning 都没有。
- **快照**：`memory.py:289` 与 `skills.py:946` 是同一句话——state 里已有字段就跳过，换 thread 才重载。
- **短期 vs 长期是存储问题**：`StateBackend` 的文件在 `state["files"]`（按 thread 隔离）；`StoreBackend` 在 Store（按 namespace 跨 thread）。`CompositeBackend` 把 `/memories/` 前缀剥掉后当 Store key。
- **memory_contents 不传子 Agent**：`memory.py:94` 标 `PrivateStateAttr`，与 `skills_metadata` 同待遇。
- **HITL 装配**：`graph.py:871-876`，配了 `interrupt_on` 才挂 `HumanInTheLoopMiddleware`；权限生成的 `interrupt_on` 在 `:182-197` 与用户配置合并（用户优先）。
- **四种决策**：`human_in_the_loop.py:345-392`。reject 造 `status="error"`、respond 造 `status="success"`，两者都不执行工具；edit 由 `:644-661` 在执行时替换参数。
- **从头重放**：`interrupt()` 抛异常暂停 → checkpoint 存档 → resume 时重放当前节点。推论是"副作用必须幂等或放 interrupt 之后"。
- **一个意外发现**：`respond` 在删除场景等于"伪造成功回执"——工具没跑，AI 却收到 `success`。这与 Replit 事故里"AI 谎称已完成"是同一类信息错位。

### 5. 下一步修正

1. **PostgresStore 未验证**：只用了 `InMemoryStore`，进程退出即丢。生产路径（`PostgresStore.from_conn_string` + `setup()`）没跑。
2. **多 Agent / 组织级 namespace 未实验**：只验证了 user 级隔离，`assistant_id` 与 `org_id` 组合未测。
3. **真实模型下的 HITL 未跑**：实验 D/E/F 都用脚本化模型保证确定性；真实模型是否会"绕过审批"（例如不调工具）值得对照。
4. **`respond` 的适用边界**：只验证了"不执行 + success"，没验证 `ask_user` 的真实多轮问答体验。
5. **token 成本只测了 skills 索引**：memory 全文的成本公式（全文 × 调用次数）还没有用真实模型测出一组数字。

## 错题记录

> 这是本任务最有价值的部分：下面六条都是"当时真的想错了"，不是笔误。

### ch08（Lesson 0004）

| # | 原题 | 当时的选择 | 错误理解 | 正确机制 |
|---|---|---|---|---|
| 1 | AGENTS.md 里的 HTML 注释，模型能看到吗 | 能 | 以为模型看到的是文件原始内容 | 注入前 `memory.py:262` 用正则剥掉 `<!-- -->`，模型看到的是"处理后的全文" |
| 2 | 配了不存在的 `memory=` 路径会怎样 | 会报错 | 以为框架会 fail fast | `memory.py:298` 对 `file_not_found` 直接 `continue`，连 warning 都没有 |
| 3 | 为什么 memory 文件要小、按主题拆分 | 以为是大文件解析慢 | 把成本算在"启动/一次"上 | `memory.py:303` 存全文 + `:356` 每轮重拼 → 成本 = 全文 × 调用次数 |

### ch09（Lesson 0005）

| # | 原题 | 当时的选择 | 错误理解 | 正确机制 |
|---|---|---|---|---|
| 4 | 拒绝删除文件该用哪个决策 | "reject 才会真的删除文件" | 把 reject 和"删除动作"绑在一起，方向反了 | reject **不执行**工具，返回 `status="error"`；approve 才执行 |
| 5 | reject 与 respond 是否等价 | 等价 | 以为两者都是"拒绝" | 都不执行，但 reject 回 `error`、respond 回 `success`（`human_in_the_loop.py:359-385`） |
| 6 | `action_requests` 里有什么 | 下一步要执行的代码 | 把审批载荷当成代码 | 只有 `name` + `args` + `allowed_decisions`，代码在工具内部 |

**共同盲区**：容易关注"东西放在哪 / 做了什么"，而忽略"**到底传了什么数据、返回了什么状态**"。
这六条错题里有五条的本质都是"没看消息内容，只猜了行为"。

## 运行方式

```bash
cd /mnt/d/study/deepagents-in-action/research_deepagent

# 零 token 的五个实验（不需要 .env、不需要网络）
uv run --frozen python ../notes/task6/code/memory_loading.py
uv run --frozen python ../notes/task6/code/memory_scope.py
uv run --frozen python ../notes/task6/code/hitl_approval.py
uv run --frozen python ../notes/task6/code/hitl_replay.py
uv run --frozen python ../notes/task6/code/hitl_reject_vs_respond.py

# 需要真实模型（Agnes 免费网关），约 7 次调用
uv run --frozen python ../notes/task6/code/skills_index_cost.py
```

重出导图（Windows 侧，需要 matplotlib + 微软雅黑）：

```bash
uv run --with matplotlib python notes/task6/mindmap.py
```

每个脚本都会在任何一条命题不成立时于断言处失败，并指出是哪一条；日志重定向到 `outputs/` 前请先删旧文件，避免混入上一轮结果。
