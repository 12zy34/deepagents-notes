"""Task4（ch05）：子 Agent 的 spec 继承规则 —— 两组对照实验。

课程里的继承表有 10 个字段，背不下来。本脚本只钉住最容易记错的两条：

  A. system_prompt 不继承 —— 父提示词里的标记不会出现在子 Agent 的回答里；
  B. tools 声明即整体替换 —— 写 tools=[] 是"清零"，不是"用默认"。

机制依据（deepagents 0.7.8, deepagents/graph.py）：
  - :728  raw_subagent_tools = spec.get("tools") if "tools" in spec else tools   ← 有继承分支
  - :740  processed_spec["system_prompt"] = _apply_profile_prompt(..., spec["system_prompt"])  ← 无继承分支
  - :806  general-purpose 用框架自带的 DEFAULT_SUBAGENT_PROMPT

运行（在 research_deepagent 目录下）：
    uv run --frozen python ../notes/task4/code/subagent_spec.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[3] / "research_deepagent" / ".env")

from deepagents import create_deep_agent  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

model = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "agnes-3.0-flash"),
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_API_BASE", "https://apihub.agnes-ai.com/v1"),
)

LOOKUP_CALLS: list[str] = []


@tool
def lookup(topic: str) -> str:
    """检索指定主题，返回固定结果 BLUE-42。"""
    LOOKUP_CALLS.append(topic)
    return f"topic={topic} 的检索结果：BLUE-42"


def last_task_result(run_result) -> str:
    """取出本次运行里 task 工具返回的那条 ToolMessage 文本。"""
    messages = run_result["messages"]
    task_ids = {
        tool_call["id"]
        for message in messages
        for tool_call in (getattr(message, "tool_calls", None) or [])
        if tool_call["name"] == "task"
    }
    for message in reversed(messages):
        if message.type == "tool" and getattr(message, "tool_call_id", None) in task_ids:
            raw = getattr(message, "content", "")
            return raw if isinstance(raw, str) else str(raw)
    return ""


# ============================================================
# 实验 A：system_prompt 是否继承
# 父与子各埋一个互斥标记，看子 Agent 的回答里是哪一个。
# ============================================================
marker_child = {
    "name": "marker",
    "description": "回答身份类问题时使用。",
    "system_prompt": "无论被问什么，你的回答必须以 MARK-CHILD 开头，并且只说一句话。",
    "tools": [],
}

agent_a = create_deep_agent(
    model=model,
    tools=[],
    system_prompt="无论被问什么，你的回答必须以 MARK-PARENT 开头。",
    subagents=[marker_child],
)

result_a = agent_a.invoke(
    {"messages": [{"role": "user", "content": "用 task 工具委派给 marker（subagent_type 必须是 marker），问它：你是谁？"}]}
)
answer_a = last_task_result(result_a)

print("=== 实验 A：system_prompt 不继承 ===")
print(f"子 Agent 的回答: {answer_a}")
print(f"含 MARK-CHILD : {'MARK-CHILD' in answer_a}")
print(f"含 MARK-PARENT: {'MARK-PARENT' in answer_a}")

assert answer_a, "实验 A 没有拿到 task 返回值：委派未发生"
assert "MARK-CHILD" in answer_a, "子 Agent 没用上自己的 system_prompt，检查 spec"
assert "MARK-PARENT" not in answer_a, "父 system_prompt 泄漏进了子 Agent：继承规则与源码不符"
print(">>> 通过：子 Agent 只认自己的 system_prompt\n")


# ============================================================
# 实验 B：tools 声明即整体替换（tools=[] 等于清零）
# 父有 lookup，子显式声明 tools=[]，并要求：没有该工具就输出 NO_TOOL。
# ============================================================
scoped_child = {
    "name": "scoped",
    "description": "工具集受限的执行者。",
    "system_prompt": (
        "你的第一步必须调用 lookup 工具，参数 topic='alpha'。"
        "如果你的工具列表里没有 lookup，就只输出 NO_TOOL 四个字符，不要解释。"
    ),
    "tools": [],
}

agent_b = create_deep_agent(
    model=model,
    tools=[lookup],
    system_prompt="遇到需要检索的任务时，用 task 委派给 scoped（subagent_type 必须是 scoped），不要自己调用工具。",
    subagents=[scoped_child],
)

before = len(LOOKUP_CALLS)
result_b = agent_b.invoke(
    {"messages": [{"role": "user", "content": "委派给 scoped：用 lookup 查一下 alpha。"}]}
)
answer_b = last_task_result(result_b)
after = len(LOOKUP_CALLS)

print("=== 实验 B：tools 整体替换 ===")
print(f"子 Agent 的回答: {answer_b}")
print(f"lookup 调用次数（父有该工具）: {after - before}")

assert answer_b, "实验 B 没有拿到 task 返回值：委派未发生"
assert after - before == 0, "lookup 被子 Agent 调用了：说明 tools=[] 被当成'用默认'，与源码不符"
print(">>> 通过：tools=[] 是清零，父子工具集不会合并")

print("\n>>> 两条对照实验全部通过。源码依据：deepagents/graph.py:728 与 :740")
