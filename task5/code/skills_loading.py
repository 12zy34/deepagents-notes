"""Task5（ch07 Skills）：验证 Skills 的 L1 加载与"会话快照"行为。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/

本脚本不调用真实模型：用一个"录制型假模型"把每次发给模型的 messages 原样存下来，
因此可以在零 token 的前提下断言"系统提示词里到底有什么"。
这是本任务的核心取证手段 —— 技能有没有加载、加载了几次，不靠肉眼看输出。

验证六条命题：
  1. 索引进 system prompt：只有 name + description + path，正文一个字都不进去；
  2. 正文不在 messages 里：说明 L2 是模型自己 read_file 读的，不是中间件预加载；
  3. 同一 thread 第二次 invoke 不重扫：新增 SKILL.md 不生效（state 里已有 skills_metadata）；
  4. 换 thread_id 才重扫：新技能出现；
  5. 同名技能 last wins：后出现的源覆盖先出现的，且提示词里标 (higher priority)；
  6. 只扫一层：/skills/deep/nested/only-skill/SKILL.md 在 skills=["/skills/deep/"] 下不可见。

机制依据（deepagents 0.7.8）：
  - deepagents/middleware/skills.py:928-971  before_agent：state 里已有 skills_metadata 则跳过
  - deepagents/middleware/skills.py:951-963  多源按顺序扫描，all_skills[name] = skill（last wins）
  - deepagents/middleware/skills.py:613-644  只 ls 一层，逐子目录取 SKILL.md
  - deepagents/middleware/skills.py:861-878  索引渲染：**name**: description -> Read `path`
  - deepagents/middleware/skills.py:900-926  modify_request：每次模型调用都重拼 system message
  - deepagents/graph.py:818-819              主 Agent：if skills is not None 才装中间件

运行（在 research_deepagent 目录下，复用项目 .venv）：
    uv run --frozen python ../notes/task5/code/skills_loading.py
无需 .env，无需模型额度。
"""

import json
import platform
from importlib.metadata import version

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

# ----------------------------------------------------------------------------
# 录制型假模型：记录每次调用收到的 messages，然后回一句固定答案
# ----------------------------------------------------------------------------


# pydantic 模型不允许类级可变属性，取证数据放模块级
RECEIVED: list[list] = []
SEEN_SYSTEM_PROMPTS: list[str] = []


class RecordingModel(FakeMessagesListChatModel):
    """只做两件事：记下 messages、返回不带 tool_calls 的 AIMessage。"""

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        # create_agent 会把工具绑到模型上；假模型不需要，原样返回即可。
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        RECEIVED.append(list(messages))
        for message in messages:
            if message.type == "system":
                SEEN_SYSTEM_PROMPTS.append(text_of(message))
                break
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def text_of(message) -> str:
    """把 message.content 压成纯文本（system prompt 是 content block 列表）。"""
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict):
            parts.append(block.get("text", ""))
        else:
            parts.append(str(block))
    return "\n".join(parts)


def skill_md(name: str, description: str, body: str) -> dict:
    """按 SKILL.md 规范拼一份文件，返回 backend 需要的 FileData。

    description 用 JSON 字符串字面量包起来：YAML 双引号字符串是 JSON 的超集，
    这样描述里出现冒号也不会把 frontmatter 解析坏（本脚本第一次就栽在这上面）。
    """
    text = (
        "---\n"
        f"name: {json.dumps(name, ensure_ascii=False)}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"{body}\n"
    )
    return create_file_data(text)


# ----------------------------------------------------------------------------
# 技能库：故意埋了同名冲突（base vs project）和一层多余嵌套（deep/nested）
# ----------------------------------------------------------------------------

BASE_DEMO = skill_md(
    "demo",
    "BASE VERSION: 用于验证同名技能被后者覆盖。",
    "# demo\n\n正文埋点：BODY-TOKEN-BASE",
)
PROJECT_DEMO = skill_md(
    "demo",
    "PROJECT VERSION: 用于验证同名技能被后者覆盖。",
    "# demo\n\n正文埋点：BODY-TOKEN-PROJECT",
)
ARCHIVE = skill_md(
    "archive",
    "归档检索技能，第一轮就能被发现。",
    "# archive\n\n正文埋点：BODY-TOKEN-ARCHIVE",
)
# 第二轮才加进来的技能：用来验证"同 thread 不重扫"
LATE = skill_md(
    "late-comer",
    "第二轮才出现的技能，用来验证会话快照。",
    "# late-comer\n\n正文埋点：BODY-TOKEN-LATE",
)
# 层级过深：skills=["/skills/deep/"] 只 ls 一层，看不到它
TOO_DEEP = skill_md(
    "only-skill",
    "埋在第三层的技能，框架只扫一层，应该看不见。",
    "# only-skill\n\n正文埋点：BODY-TOKEN-DEEP",
)

ROUND1_FILES = {
    "/skills/base/demo/SKILL.md": BASE_DEMO,
    "/skills/project/demo/SKILL.md": PROJECT_DEMO,
    "/skills/archive/archive/SKILL.md": ARCHIVE,
    "/skills/deep/nested/only-skill/SKILL.md": TOO_DEEP,
}
ROUND2_FILES = {"/skills/archive/late-comer/SKILL.md": LATE}

SOURCES = ["/skills/base/", "/skills/project/", "/skills/archive/", "/skills/deep/"]

print("$ uv run --frozen python ../notes/task5/code/skills_loading.py\n")


# ----------------------------------------------------------------------------
# 建图：StateBackend + checkpointer + 四个技能源
# ----------------------------------------------------------------------------

agent = create_deep_agent(
    model=RecordingModel(responses=[AIMessage(content="收到。")]),
    backend=StateBackend(),
    skills=SOURCES,
    checkpointer=MemorySaver(),
)

thread1 = {"configurable": {"thread_id": "thread-1"}}
thread2 = {"configurable": {"thread_id": "thread-2"}}
QUESTION = {"messages": [{"role": "user", "content": "有哪些可用技能？"}]}


def ask(payload: dict, config: dict) -> tuple[str, list]:
    """调一次图，返回（本次的 system prompt，本次收到的 messages）。"""
    before = len(RECEIVED)
    agent.invoke(payload, config=config)
    return SEEN_SYSTEM_PROMPTS[-1], RECEIVED[before]


# ---- 第 1 轮：thread-1 首次调用，四个源全部扫描 ----
prompt1, messages1 = ask({**QUESTION, "files": ROUND1_FILES}, thread1)

print("=== 第 1 轮 · thread-1 · system prompt 里的技能段 ===")
in_block = False
for line in prompt1.splitlines():
    if line.startswith("**Available Skills:**"):
        in_block = True
    elif line.startswith("**How to Use Skills"):
        in_block = False
    elif in_block and line.strip():
        print(line)
print("\n源标注（最后一个源带 higher priority）:")
for line in prompt1.splitlines():
    if "Skills**: `" in line:
        print(line)

# ---- 第 2 轮：同一个 thread，补一个 late-comer 技能 ----
prompt2, _ = ask({**QUESTION, "files": ROUND2_FILES}, thread1)

# ---- 第 3 轮：换 thread，文件一起带过去 ----
prompt3, _ = ask({**QUESTION, "files": {**ROUND1_FILES, **ROUND2_FILES}}, thread2)

print("\n=== 第 2 / 3 轮是否看到 late-comer ===")
print("thread-1（同线程，第二轮补文件）:", "late-comer" in prompt2)
print("thread-2（新线程，文件一起给）:", "late-comer" in prompt3)

print("\n=== 正文是否预先进入上下文 ===")
joined = "\n".join(text_of(m) for m in messages1)
body_tokens = [token for token in ("BODY-TOKEN-BASE", "BODY-TOKEN-PROJECT", "BODY-TOKEN-ARCHIVE") if token in joined]
print("messages 里出现的正文埋点:", body_tokens or "无")
print("system prompt 里出现的正文埋点:", [t for t in ("BODY-TOKEN-BASE", "BODY-TOKEN-PROJECT") if t in prompt1] or "无")

# ----------------------------------------------------------------------------
# 断言：六条命题逐条对账
# ----------------------------------------------------------------------------

print("\n=== 断言 ===")

# 1. 索引在，且字段齐全
assert "- **demo**:" in prompt1, "索引里没有 demo 技能：skills 未加载或目录层级不对"
assert "-> Read `/skills/project/demo/SKILL.md` for full instructions" in prompt1, "索引缺少可读取的正文路径"
print("[1/6] 索引进入 system prompt，含 name / description / path")

# 2. 正文不预加载
assert not body_tokens, f"正文被预加载了：{body_tokens} —— L2 应由模型自行 read_file"
assert "BODY-TOKEN-PROJECT" not in prompt1, "正文进了 system prompt：渐进式披露失效"
print("[2/6] 正文未进入 system prompt 与 messages（L2 完全由模型触发）")

# 3. 同 thread 不重扫
assert "late-comer" not in prompt2, "同 thread 第二轮发现了新技能：说明 before_agent 没有走快照分支"
assert "late-comer" in prompt3, "换 thread 后仍看不到新技能：扫描逻辑异常"
print("[3/6] 同 thread 不重扫（state 已有 skills_metadata），换 thread 才重扫")

# 4. last wins
assert "PROJECT VERSION" in prompt1, "后一个源没有覆盖前一个源：last wins 失效"
assert "BASE VERSION" not in prompt1, "先出现的源仍然残留：同名技能未按顺序覆盖"
print("[4/6] 同名技能 last wins：/skills/project/ 覆盖 /skills/base/")

# 5. 优先级标注
assert "(higher priority)" in prompt1, "提示词没有标注最高优先级源"
print("[5/6] 提示词把最后一个源标为 (higher priority)")

# 6. 只扫一层
assert "only-skill" not in prompt1, "第三层目录也被扫到了：与 _list_skills_with_errors 只 ls 一层不符"
print("[6/6] 只扫一层：/skills/deep/nested/only-skill/SKILL.md 不可见")

print("\n>>> 验证通过：L1 索引进提示词 / 正文不预加载 / 会话快照 / last wins / 只扫一层")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    "模型：未调用（录制型假模型，零 token 消耗）\n"
    "运行日期：2026-10-25"
)
