# Task4：子 Agent 与上下文隔离——让 Agent 学会委派（ch05）

> 资料来源声明：本目录练习改编自 Datawhale《DeepAgents 实战》课程
> [ch05 子 Agent 与上下文隔离](https://datawhalechina.github.io/deepagents-in-action/chapters/ch05-subagents/)。
> 完整引用清单见[仓库根 README](../README.md#引用与致谢)。
>
> - 课程教程：<https://datawhalechina.github.io/deepagents-in-action/>
> - B站视频：《Deep Agents 实战》 <https://space.bilibili.com/28357052/lists/7757577?type=season>
> - 课程仓库：<https://github.com/datawhalechina/deepagents-in-action>

## 目录

- [子Agent与上下文隔离.png](./子Agent与上下文隔离.png) — 本章思维导图（代码渲染，叶片刻意写机制不写功能名）
- [code/delegation_boundary.py](./code/delegation_boundary.py) — 边界实验：验证 messages 隔离 / files 穿透 / 返回值压缩
- [code/subagent_spec.py](./code/subagent_spec.py) — spec 继承对照：system_prompt 不继承、tools 整体替换
- [outputs/delegation_boundary.log](./outputs/delegation_boundary.log) — 边界实验的真实运行日志
- [outputs/subagent_spec.log](./outputs/subagent_spec.log) — 继承实验的真实运行日志
- [mindmap.py](./mindmap.py) — 导图生成脚本（改字重出图，避免 AI 生图写错中文）

## 本章核心一句话

**委派只发生在两个字符串上**——进去一个 `description`，出来一条 `ToolMessage`；
所以「上下文隔离」在实现层就是两行赋值，而且**它隔离的是 `messages`，不是整个 state**（`files` 双向穿透）。

## 打卡：统一要求五项

### 1. 验证什么

1. **messages 方向被阻断**：子 Agent 内部的工具调用原文不会进入父 Agent 上下文；
2. **files 方向放行**：父 Agent 写的文件，子 Agent 能直接读到（这是最反直觉、也最容易答错的一条）；
3. **返回值被压缩**：父 Agent 只收到一条精简的 `ToolMessage`，而不是子 Agent 的全部过程；
4. **spec 侧不继承**：父 `system_prompt` 不进子 Agent，`tools=[]` 是"清零"而不是"用默认"。

### 2. 改了什么

课程里的示例是"定义一个 researcher 子 Agent 然后观察它能干事"。本练习把它改成**可对账的取证实验**：

1. 工具 `lookup` 返回一段带唯一标记 `[RAW-NOISE]` 的长文本（约 1.1k 字符），
   并挂一个**进程内计数器**记录被调用次数——计数器与父上下文形成对照：
   工具明明跑了 3 次，父上下文里却一个字都没有，这才是隔离的直接证据；
2. 父 Agent 被要求先用 `write_file` 写 `/data/brief.md` 并埋入口令 `ALPHA-7391`，
   再委派子 Agent 去**读该文件**取口令——如果 `files` 不穿透，子 Agent 绝无可能拿到这个口令；
3. 两个脚本都用断言把关，并打印"长度"而不只是内容，让"压缩"这条可量化；
4. 继承实验不用肉眼判断：父与子各埋互斥标记 `MARK-PARENT` / `MARK-CHILD`，
   子 Agent 回答里出现哪个就是哪个的提示词在生效。

### 3. 实际结果

**边界实验**（`delegation_boundary.py`，日志见 `outputs/delegation_boundary.log`）：

| 观察项 | 实测值 |
|---|---|
| 父 Agent 的工具调用序列 | `write_file` → `task`（父自己没查过资料） |
| `lookup` 在进程内被调用 | **3 次**，主题 `alpha` / `gamma` / `beta` |
| 父上下文中含 `[RAW-NOISE]` 的 ToolMessage | **0 条** |
| `task` 返回值 | **41 字符**：「已完成三项主题检索并验证子 Agent 上下文隔离，口令为 ALPHA-7391。」 |
| `state['files']` | 含 `/data/brief.md`，内容即父写入的口令 |

三条断言同时成立：子 Agent 确实执行了 3 次检索，但检索原文一条都没进父上下文；
返回值被压缩到 41 字符；而它能说出 `ALPHA-7391`，只能是因为读到了父写的文件。

**继承实验**（`subagent_spec.py`，日志见 `outputs/subagent_spec.log`）：

| 实验 | 结果 |
|---|---|
| A. `system_prompt` 是否继承 | 子 Agent 回答 `MARK-CHILD …`，**不含** `MARK-PARENT` → 只认自己的提示词 |
| B. `tools=[]` 是否等于"用默认" | 子 Agent 回答 `NO_TOOL`，父虽有 `lookup` 但**调用 0 次** → 是清零，不合并 |

### 4. 证据与解释

- **隔离机制**（`deepagents/middleware/subagents.py:529-540`）：
  入边界把父 state 逐键拷贝，但 `messages` 被丢弃并重置为 `[HumanMessage(description)]`；
  `_EXCLUDED_STATE_KEYS = {messages, todos, structured_response}`（`:252-256`）。
  因为 `files` 不在排除名单里，它才会出现在 `state['files']` 里被子 Agent 读到。
- **回收机制**（`:474-512`）：出边界取"最后一条非空 `AIMessage`"的文本，包成一条 `ToolMessage`；
  其余 state 键走 `state_update` 合并回父。所以**对话不通、文件通**。
- **spec 侧**（`deepagents/graph.py:728` 与 `:740`）：`tools` 用
  `spec.get("tools") if "tools" in spec else tools`（有继承分支），
  `system_prompt` 直接用 `spec["system_prompt"]`（无继承分支）。
  同一个函数相邻两行，一个有继承一个没有——这比任何继承表都更能说明"哪些继承是设计、哪些不是"。
- **一个意外发现**：实验 A 里子 Agent 的回答混入了模型的 `</think>` 残片，并被**原样**包进 `ToolMessage`。
  这反过来证明出边界没有任何清洗或裁剪逻辑（连 `strip` 之外的加工都没有）。
  实用推论是：**子 Agent 的输出格式必须在它自己的 `system_prompt` 里约束**，
  或者用 `response_format` 结构化，不能指望边界替你把脏输出洗干净。

### 5. 下一步修正

1. `todos` 双向不通这条**没做实验**，只在源码上确认。补法是：父装 `TodoListMiddleware`、
   子也用同名 spec 装上，跑完后断言父 `todos` 里不含子任务的条目；
2. `tools` 只验证了 `tools=[]` 清零，**"部分声明"未验证**：给子 Agent 只声明 2 个工具中的 1 个，
   断言另一个不可调用——这条能顺带证明"替换不是合并"；
3. 本次是确定性工具，没有测**真实长搜索结果下的 token 收益**。补法：同一任务分别用
   "父直查" 与 "委派子 Agent"，对比两者的 `usage_metadata` 总 token；
4. 子 Agent 输出含 `</think>` 残片，说明默认配置对输出清洗是零。下一步试 `response_format`，
   观察结构化之后父上下文是否变干净（同时会引入"键不回、值回"的新现象，值得单独记；
5. 换弱模型复跑，观察是否出现"从不委派 / 派错人 / 回传原始数据"三类失败模式。

## 运行方式

```bash
cd /mnt/d/study/deepagents-in-action/research_deepagent
uv run --frozen python ../notes/task4/code/delegation_boundary.py
uv run --frozen python ../notes/task4/code/subagent_spec.py
```

重出导图（需要 matplotlib + 微软雅黑，Windows 侧直接跑）：

```bash
python notes/task4/mindmap.py
```

复用项目 `.venv`（deepagents 0.7.8）与 `.env`（模型凭据）。两个脚本各调用模型 2–4 次，
注意免费额度限流；失败时脚本会在断言处报错并指出是哪一条命题没成立。
