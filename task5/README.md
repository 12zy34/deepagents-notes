# Task5：Skills——可复用的 Agent 能力包（ch07）

> 资料来源声明：本目录练习改编自 Datawhale《DeepAgents 实战》课程
> [ch07 Skills —— 可复用的 Agent 能力包](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)。
> 完整引用清单见[仓库根 README](../README.md#引用与致谢)。
>
> - 课程教程：<https://datawhalechina.github.io/deepagents-in-action/>
> - 课程 Notebook：<https://datawhalechina.github.io/deepagents-in-action/notebooks/ch07/01-skills-progressive-disclosure.ipynb>
> - B站视频：Lec 09 / Lec 10 <https://space.bilibili.com/28357052/lists/7757577?type=season>

## 目录

- [Skills能力包.png](./Skills能力包.png) — 本章思维导图（代码渲染，叶片刻意写机制不写功能名）
- [code/skills_loading.py](./code/skills_loading.py) — 加载机制实验：录制型假模型，零 token，6 条断言
- [code/skills_subagent.py](./code/skills_subagent.py) — 委派实验：父子各自装配 skills，5 条断言
- [outputs/skills_loading.log](./outputs/skills_loading.log) — 加载实验的真实运行日志
- [outputs/skills_subagent.log](./outputs/skills_subagent.log) — 委派实验的真实运行日志
- [mindmap.py](./mindmap.py) — 导图生成脚本（改字重出图，避免 AI 生图写错中文）

## 本章核心一句话

**框架只加载元数据，正文是模型自己 `read_file` 读进来的 `ToolMessage`。**
所以"三级加载"里只有 L1 是中间件干的；L2/L3 是提示词里的两句话。由此推出三件事：索引每次模型调用都重付一次钱、
正文过不了委派边界（子 Agent 得自己读）、索引是会话快照（同一 thread 改 SKILL.md 不生效）。

## 打卡：统一要求五项

### 1. 验证什么

**实验 A（`skills_loading.py`，零 token）** —— 课程说"渐进式披露"，但没说清哪一级由谁执行。逐条断言：

1. 索引（`name` + `description` + `path`）进 system prompt，正文一个字都不进；
2. 正文既不在 system prompt 也不在 `messages` 里 —— 说明 L2 完全由模型触发；
3. 同一 thread 第二次 `invoke` 不重扫 —— 新增 `SKILL.md` 不生效；
4. 换 `thread_id` 才重扫，新技能出现；
5. 同名技能 last wins，后出现的源覆盖先出现的，且提示词把最后一个源标 `(higher priority)`；
6. 只扫一层：`skills=["/skills/deep/"]` 看不见 `/skills/deep/nested/only-skill/SKILL.md`。

**实验 B（`skills_subagent.py`，真实模型 4 次调用）** —— 验证"skills 是各自装配，不是继承"：

1. 父的 system prompt 只含 `main-skill`，不含子的 `sub-skill`；
2. 子的 system prompt 只含 `sub-skill`，不含父的 `main-skill`；
3. 子自己调 `read_file`，正文埋点进入子的上下文（L2 由子触发）；
4. 父上下文里没有正文原文（正文没穿过委派边界）；
5. `task` 的返回值里有正文埋点 —— 只有"值"能穿过去。

### 2. 改了什么

课程示例是"配一个 `skills=` 然后看 Agent 用不用"。本练习把"提示词里到底有什么"变成**可断言的取证**：

1. **实验 A 用录制型假模型，零 token**：`RecordingModel` 继承 `FakeMessagesListChatModel`，
   在 `_generate` 里抄一份 `messages` 再返回固定答案。技能有没有加载、加载了几次，不靠肉眼看，靠断言。
   这一招可以复用到任何"我要看系统提示词"的场景，且不烧额度。
2. **实验 B 用录制壳包真实模型**：`RecordingChatOpenAI` 只记录不拦截，因此拿到的是真实行为，
   但"父/子各自的 system prompt"变成可检索的证据 —— 按提示词里出现哪个技能名，把 4 次调用自动分成父 2 次、子 2 次。
3. **埋点 token 化**：技能正文里写 `SUB-TOKEN-7731`，父/子提示词里写 `main-skill` / `sub-skill`。
   哪个 token 出现在哪一层，就是哪条边界在起作用，避免"看起来像隔离了"。
4. **故意造对抗条件**：同名技能（`/skills/base/` vs `/skills/project/`）、三层嵌套目录、
   第二轮才加入的技能 —— 每一条都对应源码里的一个分支，而不是正常路径下的顺风局。

### 3. 实际结果

**实验 A**（日志 `outputs/skills_loading.log`）：

| 观察项 | 实测值 |
|---|---|
| 可见技能 | `demo`（来自 project 源）、`archive`；`late-comer` 与 `only-skill` 不可见 |
| `demo` 的 description | `PROJECT VERSION ...`（base 源被覆盖） |
| 源标注 | `/skills/deep/` 带 `(higher priority)` |
| system prompt 里的正文埋点 | 无 |
| messages 里的正文埋点 | 无 |
| thread-1 第二轮能否看到 late-comer | `False` |
| thread-2（新线程）能否看到 late-comer | `True` |

**实验 B**（日志 `outputs/skills_subagent.log`）：

| 观察项 | 实测值 |
|---|---|
| 模型调用分布 | 共 4 次：父 2 次（只含 `main-skill`）、子 2 次（只含 `sub-skill`） |
| 子 Agent 的工具调用 | `['read_file']` |
| 子上下文中含 `SUB-TOKEN-7731` | 是 |
| 父 messages 中含正文原文 | 否（唯一命中来自 `task` 返回值） |
| `task` 返回值 | `SUB-TOKEN-7731` |

### 4. 证据与解释

- **L1 只取元数据**（`deepagents/middleware/skills.py:613-644`）：`backend.ls(source)` 拿直接子目录，
  逐目录下载 `SKILL.md` 后只解析 frontmatter；解析失败就 `logger.warning` 后跳过 —— 这正是"静默失败"的来源。
- **索引是每次重拼**（`:900-926` + `:1018-1033`）：`wrap_model_call` 每轮调 `modify_request`，
  用 `append_to_system_message` 把技能段拼到 system message。所以成本 = Σdescription × 模型调用次数，
  不是"会话启动一次"。这也解释了为什么 `description` 有 1024 字符上限（`:432-444`，超了截断后照用）。
- **快照**（`:946-948`）：`if "skills_metadata" in state: return None`，注释明说 "even if empty"。
  带 checkpointer 时它在 checkpoint 里，于是同 thread 永不重扫；空列表也会被缓存成"本会话没有技能"。
- **last wins**（`:951-963`）：`all_skills[skill["name"]] = skill` 一行字典赋值；提示词标注在 `:853-857`。
- **各自装配**（`graph.py:676-678` / `:761-762` / `:818-819`）：主 Agent 用 `is not None` 判空，
  自定义子 Agent 用**真值**判空，GP 是 `:761` 那行字面复制。三者行为不同，但都发生在建图时，
  运行期不存在"技能继承"这条路径 —— 每个 Agent 的 `before_agent` 各扫一份，`skills_metadata` 还标了
  `PrivateStateAttr`（`:294`），连委派边界都过不去，因此也不可能互相污染。
- **一个意外发现（本次最值钱的副作用）**：第一版脚本里 `description: BASE VERSION: 用于…` 直接让 YAML 解析失败，
  技能被静默跳过、只剩一个技能进了索引。这不是脚本 bug 的噪音，而是 `SKILL.md` 最常见的真实故障：
  **frontmatter 里出现未加引号的 `: ` 就会整份技能消失，而框架只写一行 warning**。
  已改成用 JSON 字符串字面量包 `description`（YAML 双引号是 JSON 超集），并在 `mindmap.py` 的失败模式分支里记录。

### 5. 下一步修正

1. **权限没做实验**：课程给的 `FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny")`
   与 `mode="interrupt"`（需 checkpointer）只读源码，未跑。补法是让模型尝试 `write_file` 到 `/skills/` 下，
   断言返回权限错误；`interrupt` 则断言图停在中断态。
2. **`CompositeBackend` 前缀剥离未验证**：课程强调 Store key 要写路由相对路径（`/test-skill/SKILL.md`），
   写全会变成 `/skills/skills/...`。这是"路径错了但不报错"的典型，值得用 `store.get` 直接对账。
3. **索引的 token 成本仍无实测**：实验 A 只证明了"每轮都拼"，没有量化"20 个技能 × 每轮多付多少"。
   可用录制壳统计 system prompt 字符数 × 调用次数，得出可引用的数字 —— 这条正好补 `RESOURCES.md` 的 Gaps。
4. **Skills vs Memory 没对照**：`MemoryMiddleware` 是"启动时就注入"，与 Skills 的按需读取是光谱两端。
   读一遍 `middleware/memory.py` 并与本实验的录制手段结合，能量化两者对上下文占用的差别。
5. **沙箱脚本 / 解释器技能未覆盖**：`scripts/` 与 QuickJS 中间件属于执行侧，与本章的加载机制正交，
   留到需要写脚本类技能时再学。

## 运行方式

```bash
cd /mnt/d/study/deepagents-in-action/research_deepagent

# 实验 A：零 token，只依赖 deepagents
uv run --frozen python ../notes/task5/code/skills_loading.py

# 实验 B：真实模型 4 次调用（脚本内置 429 指数退避）
uv run --frozen python ../notes/task5/code/skills_subagent.py
```

重出导图（Windows 侧，需要 matplotlib + 微软雅黑）：

```bash
uv run --with matplotlib python notes/task5/mindmap.py
```

两个脚本都会在任何一条命题不成立时于断言处失败，并指出是哪一条；日志追加写 `outputs/` 时请先删旧文件再重定向，
避免把上一轮的结果混进来。
