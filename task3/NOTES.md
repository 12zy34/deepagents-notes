# ch04 任务规划 —— 深度笔记

配合 [README.md](./README.md) 的打卡记录，这里回答"为什么这样设计"。

## 1. 规划要解决的四个真实症状

复杂任务（多源搜索 → 对比 → 写报告）里，没有规划的 Agent 会：

| 症状 | 机制原因 |
|---|---|
| 遗漏步骤 | 计划只存在"这次模型输出"里，下一轮就被新信息挤掉 |
| 重复劳动 | 不知道自己搜过什么，只能靠消息历史回看，长对话里成本高 |
| 半途而废 | 上下文被中间结果占满，主线信息被挤到窗口边缘 |
| 质量不稳定 | 是否拆步骤完全取决于当次采样 |

规划的作用：把"接下来做什么"从**易失的上下文**搬到**独立的状态字段**。

## 2. 为什么 v0.7 要 opt-in

`TodoListMiddleware` 一次性注入三样东西：

1. `write_todos` 工具；
2. `todos` 状态字段（`PlanningState.todos`，带 `OmitFromInput`）；
3. 规划提示词（追加到 system prompt）。

代价是**每次模型调用都多一段提示词 + 一个工具定义**。单步问答里这属于纯开销，
还会诱导模型"为一件小事写五条计划"。所以默认关闭、按任务开启。

判断标准：**任务是否需要跨多轮保持主线**。需要就开，不需要就别开。

## 2.1 两种组合路径：`create_agent` vs `create_deep_agent`

| 路径 | 你负责什么 | 规划从哪来 |
|---|---|---|
| `create_agent(model, tools, middleware=[...])` | 手动挑中间件 | 自己把 `TodoListMiddleware()` 写进 `middleware` |
| `create_deep_agent(model, tools, middleware=[...])` | 只补可选策略 | 预设了文件系统/摘要/PatchToolCalls，**不含规划**，仍需显式加 |

两条路径的共同点：**规划是"可选项"，不是"基础能力"**。
`create_deep_agent` 只是帮你省掉文件系统、摘要、工具调用修补这些默认件，
不会替你做"要不要规划"的产品决策。

配置层面还有一条容易踩的规则：与默认中间件同名的实例是**原位替换**，
且是整实例替换、不按字段合并。比如你写 `TodoListMiddleware(system_prompt=...)`，
它会连同默认 `tool_description` 一起替换掉默认实例。

## 3. `todos` 的数据结构与"非状态机"本质

```json
{"content": "查询北京天气", "status": "pending"}
```

三态：`pending` / `in_progress` / `completed`。

关键认知：**它不是状态机**。框架不校验"pending 必须先变 in_progress"，
也不禁止跳步、回退、临时新增。你看到的"标准流转"是模型的行为习惯，
不是引擎的强制约束。所以：

- 想强制流程，要自己写校验（`after_model` 钩子里检查）；
- 想检查质量，要看产物，不能只看 `status == completed`。

## 4. 读轨迹时最容易被忽略的一点：每次都是全量覆盖

`write_todos(todos: list[Todo])` 的入参是**整份清单**。模型每次更新一项，
都要把其余项原样重发一遍（实验里你能看到每次 `write_todos` 的参数都是 5 条）。

推论：

- 清单越长，每次更新越费 token；
- 模型漏抄一项 = 直接丢掉那一项（不是"没更新"，是"删除"）；
- 并行调用多个 `write_todos` 会产生歧义，所以 `TodoListMiddleware.after_model`
  会检测并拒绝同轮多次调用（返回错误 ToolMessage，而不是抛异常）。

这也是 research 项目 COURSE.md 要求"每次模型响应最多调用一次 write_todos"的原因。

## 5. 持久化的四个条件（缺一不可）

| 条件 | 作用 | 不满足时 |
|---|---|---|
| `middleware=[TodoListMiddleware()]` | 才有 `todos` 字段 | 根本没有清单 |
| `checkpointer=...` | 保存图状态 | 每次 invoke 都是全新状态 |
| 复用同一 `thread_id` | 定位到同一份状态 | 读到的是空清单（线程隔离） |
| saver 的持久化级别 | 跨进程/重启恢复 | `InMemorySaver` 进程结束即丢 |

实验对应：A（同 thread）保留 4 项；B（新 thread）为空；C（无 checkpointer）无法恢复。

注意：`todos` 的隔离粒度是**线程**，不是用户。多用户场景要在 checkpointer 之上
再做 user → thread_id 的映射，否则会串数据。

## 6. 子 Agent 不继承（ch04 第 5 条）

默认 `general-purpose` 与 `subagents=[...]` 声明的子 Agent，**都不会**自动获得
`TodoListMiddleware`。原因：子 Agent 是用自己的 spec 单独 `create_agent` 编译的
（`deepagents/middleware/subagents.py` 只取 `spec.get("middleware", [])`）。

后果：

- 主 Agent 有清单，子 Agent 没有 → 委派出去的长任务在子 Agent 内部没有计划锚点；
- 子 Agent 即使开了，清单也在**自己的** `todos` 里，不读父清单、不回写父清单。

要做"全局计划"，只能由主 Agent 持有清单、把子任务描述写清楚，或自定义跨 Agent 的状态共享。

## 7. 中间件机制：两类 Hook 的选择

| 风格 | Hook | 图结构 | 适合 |
|---|---|---|---|
| Node-style | `before_agent` / `before_model` / `after_model` / `after_agent` | 独立节点，边界清晰 | 校验、状态更新、审计、**人工中断** |
| Wrap-style | `wrap_model_call` / `wrap_tool_call` | 包在一次调用内部 | 重试、缓存、降级、请求改写 |

对 `interrupt()` 尤其重要：Node-style 暂停/恢复时能推断哪些逻辑会重放；
Wrap-style 恢复可能连 handler 一起重跑。所以自定义人工中断优先放 Node-style。

配置层面的两个坑：

1. **同名实例原位替换**，不是在末尾叠加；
2. **替换是整实例替换，不按字段合并**——你写的 `TodoListMiddleware(system_prompt=...)`
   会连同默认 `tool_description` 一起替换掉默认实例。

## 8. `PatchToolCallsMiddleware` 补的是消息，不是执行

场景：模型发出 `internet_search`（call_1）后运行被取消，历史里缺对应 ToolMessage。
下次运行前，它在 `before_agent` 补一条"该调用已取消"的响应。

边界：

- 不重试工具、不修正结果；
- 已有响应（哪怕是错误）不算缺口；
- 补的说明**不能证明外部副作用已撤销**（搜索请求可能已经发出去）。

职责划分：缺响应 → Patch；可重试异常 → `ToolRetryMiddleware`；跨次继续 → Checkpointer；
结果对不对 → 应用自己的校验/评测/人工审核。

## 9. 与上下文管理的协同

10 步任务跑到第 6 步，前 5 步的搜索结果和读写记录会堆满上下文：

1. 大结果（> 约 20K tokens）先被卸载到虚拟文件系统，上下文只留路径 + 前 10 行；
2. 仍超阈值则总结旧消息，本次输入换成"摘要 + 近期消息"（`create_deep_agent` 默认
   按模型窗口的 85% 触发，窗口未知时用固定 token 阈值）。

**总结不会删除 `todos`**（它是独立状态字段），所以清单成为压缩后唯一还在的"主线"。
反过来说：清单如果没及时更新，压缩后 Agent 就真的迷路了。

## 10. 自测

1. 为什么 `write_todos` 每次都要传整份列表？漏传一项会发生什么？
2. 只加 `TodoListMiddleware` 不配 Checkpointer，第二次 invoke 能看到上次的计划吗？为什么？
3. 子 Agent 里看不到父 Agent 的计划，是 bug 还是设计？要共享该怎么改？
4. `todos` 全部 `completed` 能否证明任务完成？还需要检查什么？
5. `PatchToolCallsMiddleware` 补的那条 ToolMessage，能证明被取消的搜索没执行吗？
