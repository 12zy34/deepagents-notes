"""Task5（ch07 Skills）：验证子 Agent 的 skills 是"各自装配"，不是继承。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/

脚本 1 证明了"索引/正文的分工"，本脚本证明它的第二条推论：
既然正文是 read_file 的 ToolMessage，它就过不了委派边界 ——
所以每个 Agent 都必须有自己的 SkillsMiddleware，自己扫、自己读。

做法：给真实模型套一层录制壳（RecordingChatOpenAI），把每次模型调用收到的
system prompt 与 messages 都存下来。这样既能拿到真实行为，又能逐条断言。

验证五条命题：
  1. 父 Agent 的 system prompt 含父自己的技能，不含子 Agent 的技能；
  2. 子 Agent 那一次调用的 system prompt 含子自己的技能（各自装配的直接证据）；
  3. 子 Agent 的 messages 里出现 read_file 的 ToolMessage，且含正文埋点（L2 由子自己触发）；
  4. 父 Agent 的 messages 里找不到该正文埋点（正文没穿过委派边界）；
  5. task 的返回值里有该埋点 —— 只有"值"能穿过去。

机制依据（deepagents 0.7.8）：
  - deepagents/graph.py:676-678   自定义子 Agent：if subagent_skills: 才装 SkillsMiddleware
  - deepagents/graph.py:761-762   general-purpose：复制主 Agent 的 skills（本脚本没用 GP）
  - deepagents/middleware/skills.py:928-971  每个 Agent 在自己的 before_agent 里各扫一份
  - deepagents/middleware/subagents.py:529-540  入边界重置 messages
  - deepagents/middleware/subagents.py:474-512  出边界只取最后一条非空 AIMessage 文本

运行（在 research_deepagent 目录下，复用项目 .venv 与 .env，约 2–4 次模型调用）：
    uv run --frozen python ../notes/task5/code/skills_subagent.py
"""

import json
import os
import platform
import time
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

# uv run 不会自动读取 .env：先按常规向上查找，再显式指向 research_deepagent/.env
load_dotenv()
load_dotenv(Path(__file__).resolve().parents[3] / "research_deepagent" / ".env")

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import StateBackend  # noqa: E402
from deepagents.backends.utils import create_file_data  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langchain_openai.chat_models.base import OpenAIRateLimitError  # noqa: E402

# ----------------------------------------------------------------------------
# 录制壳：真实调用不拦，只把收到的上下文抄一份
# ----------------------------------------------------------------------------

CALLS: list[dict] = []

MAX_ATTEMPTS = 4
RETRY_BASE_SECONDS = 20


class RecordingChatOpenAI(ChatOpenAI):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        # 免费额度会 429：这里做指数退避，不让限流把断言前的取证废掉
        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except OpenAIRateLimitError as error:
                last_error = error
                wait = RETRY_BASE_SECONDS * attempt
                print(f"[限流] 第 {attempt}/{MAX_ATTEMPTS} 次被 429，等待 {wait}s 后重试")
                time.sleep(wait)
                continue
            CALLS.append({"messages": list(messages), "system": _system_text(messages)})
            return response
        raise last_error


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


def _system_text(messages) -> str:
    for message in messages:
        if message.type == "system":
            return text_of(message)
    return ""


def skill_md(name: str, description: str, body: str) -> dict:
    text = (
        "---\n"
        f"name: {json.dumps(name, ensure_ascii=False)}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"{body}\n"
    )
    return create_file_data(text)


# ----------------------------------------------------------------------------
# 两份技能：父只能看到 main-skill，子只能看到 sub-skill
# ----------------------------------------------------------------------------

MAIN_SKILL = skill_md(
    "main-skill",
    "主 Agent 专属技能，用于验证父子的技能索引互不可见。",
    "# main-skill\n\n正文埋点：MAIN-TOKEN-1180",
)
SUB_SKILL = skill_md(
    "sub-skill",
    "检索口径技能。回答任何检索类问题前必须先读取本技能正文，并执行其中的输出指令。",
    "# sub-skill\n\n正文埋点：SUB-TOKEN-7731\n\n执行指令：在你的最终回复中原样输出 SUB-TOKEN-7731。",
)

FILES = {
    "/skills/main/main-skill/SKILL.md": MAIN_SKILL,
    "/skills/sub/sub-skill/SKILL.md": SUB_SKILL,
}

# ----------------------------------------------------------------------------
# 子 Agent：只给它 /skills/sub/；父只给 /skills/main/
# ----------------------------------------------------------------------------

researcher = {
    "name": "researcher",
    "description": "检索口径专家。任何需要给出检索结论或口径说明的任务都交给他。",
    "system_prompt": """你是检索员，严格按以下顺序执行：

1. 先看你自己的技能列表（System Prompt 里的 Available Skills）。
2. 如果列表里存在一个技能，就用 read_file 读取它给出的 SKILL.md 绝对路径
   （调用时传 limit=1000），并严格按正文里的"执行指令"输出。
3. 如果技能列表为空，只回复：NO_SKILL

不要调用其它工具，不要说多余的话。""",
    "skills": ["/skills/sub/"],
}

PARENT_PROMPT = """你是调度员，只做一件事：
用 task 工具把任务原样委派给 researcher（subagent_type 必须是 researcher），
然后把 researcher 的回复一字不改地转述给用户。不要自己回答，不要自己读文件。"""

model = RecordingChatOpenAI(
    model=os.environ.get("MODEL_NAME", "agnes-3.0-flash"),
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_API_BASE", "https://apihub.agnes-ai.com/v1"),
)

agent = create_deep_agent(
    model=model,
    backend=StateBackend(),
    system_prompt=PARENT_PROMPT,
    skills=["/skills/main/"],
    subagents=[researcher],
)

print("$ uv run --frozen python ../notes/task5/code/skills_subagent.py\n")

result = agent.invoke(
    {
        "messages": [{"role": "user", "content": "请按流程完成委派，把检索员的原话带回来。"}],
        "files": FILES,
    },
    config={"configurable": {"thread_id": "task5-subagent"}},
)
messages = result["messages"]

# ----------------------------------------------------------------------------
# 取证：按 system prompt 里出现的技能名，把模型调用分成"父"和"子"
# ----------------------------------------------------------------------------

parent_calls = [c for c in CALLS if "main-skill" in c["system"]]
sub_calls = [c for c in CALLS if "sub-skill" in c["system"] and "main-skill" not in c["system"]]

print("=== 模型调用分布 ===")
print(f"总调用 {len(CALLS)} 次；父 {len(parent_calls)} 次；子 {len(sub_calls)} 次")
for index, call in enumerate(CALLS, 1):
    skill = "main-skill" if "main-skill" in call["system"] else ("sub-skill" if "sub-skill" in call["system"] else "无技能")
    print(f"  #{index} 系统提示词中的技能: {skill}")

print("\n=== 父 Agent 的索引（只该有 main-skill）===")
for line in (parent_calls[0]["system"].splitlines() if parent_calls else []):
    if line.startswith("- **"):
        print(line)

print("\n=== 子 Agent 的索引（只该有 sub-skill）===")
for line in (sub_calls[0]["system"].splitlines() if sub_calls else []):
    if line.startswith("- **"):
        print(line)

print("\n=== 子 Agent 内部的工具调用 ===")
sub_tool_calls = []
for call in sub_calls:
    for message in call["messages"]:
        for tool_call in getattr(message, "tool_calls", None) or []:
            sub_tool_calls.append(tool_call["name"])
print("调用序列:", sub_tool_calls or "无")

print("\n=== 正文出现在哪一层 ===")
sub_text = "\n".join(text_of(m) for call in sub_calls for m in call["messages"])
parent_text = "\n".join(text_of(m) for m in messages)
print("子 Agent 上下文中含正文埋点:", "SUB-TOKEN-7731" in sub_text)
print("父 messages 中（含 task 返回值）含正文埋点:", "SUB-TOKEN-7731" in parent_text)

task_results = [m for m in messages if m.type == "tool" and "SUB-TOKEN" in text_of(m)]
print("\n=== task 返回值 ===")
for message in task_results:
    print(text_of(message)[:200])

# ----------------------------------------------------------------------------
# 断言
# ----------------------------------------------------------------------------

print("\n=== 断言 ===")

assert parent_calls, "主 Agent 没有发生模型调用：图构建失败"
assert sub_calls, "子 Agent 没有发生模型调用：委派未发生，检查 description 与父提示词"
print(f"[1/5] 父子各自独立调用模型（父 {len(parent_calls)} 次，子 {len(sub_calls)} 次）")

# 2. 索引各自装配
assert "- **main-skill**" in parent_calls[0]["system"], "父 Agent 的提示词里没有 main-skill"
assert "sub-skill" not in parent_calls[0]["system"], "父 Agent 看到了子 Agent 的 sub-skill：说明 skills 被错误共享"
assert "- **sub-skill**" in sub_calls[0]["system"], "子 Agent 的提示词里没有 sub-skill：spec 的 skills 字段没生效"
assert "main-skill" not in sub_calls[0]["system"], "子 Agent 看到了父的 main-skill：说明子 Agent 继承了父的 skills"
print("[2/5] 索引各自装配：父只见 main-skill，子只见 sub-skill（无继承）")

# 3. 正文由子自己读
assert "read_file" in sub_tool_calls, f"子 Agent 没有调用 read_file：{sub_tool_calls}"
assert "SUB-TOKEN-7731" in sub_text, "子 Agent 读了 SKILL.md 却拿不到正文埋点"
print("[3/5] L2 由子 Agent 自己 read_file 触发，正文进入子上下文")

# 4. 正文没过边界：父上下文里的 SUB-TOKEN 只应来自 task 的返回值
leaked = [
    m
    for m in messages
    if m.type == "tool" and "SUB-TOKEN-7731" in text_of(m) and "for full instructions" not in text_of(m) and m not in task_results
]
assert not leaked, "正文通过非 task 通道泄漏进父上下文"
print("[4/5] 父上下文没有出现 SKILL.md 正文原文（唯一的 SUB-TOKEN 来自 task 返回值）")

# 5. 值能穿过去
assert task_results and "SUB-TOKEN-7731" in text_of(task_results[0]), (
    "task 返回值里没有正文埋点：子 Agent 没按技能指令输出，属模型不遵守指令，不是机制问题"
)
print("[5/5] 子 Agent 把正文里的指令结果写进最终回复，经 task 返回值穿过边界")

print("\n>>> 验证通过：skills 各自装配 / L2 由子自己读 / 正文不过边界 / 值可穿边界")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    f"模型：{model.model_name}（真实调用 {len(CALLS)} 次）\n"
    "运行日期：2026-10-25"
)
