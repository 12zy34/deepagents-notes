"""Task4（ch05 子 Agent 与上下文隔离）：验证委派边界的两个方向。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch05-subagents/

本脚本只验证一件事，但把它拆成三个可断言的命题：

  1. messages 方向被阻断 —— 子 Agent 内部的工具调用原文不会进父上下文；
  2. files 方向放行     —— 父 Agent 写的文件，子 Agent 能读到（这是最反直觉的一条）；
  3. 返回值被压缩       —— 父 Agent 只收到一条精简的 ToolMessage。

机制依据（deepagents 0.7.8）：
  - deepagents/middleware/subagents.py:252-256  _EXCLUDED_STATE_KEYS = {messages, todos, structured_response}
  - deepagents/middleware/subagents.py:529-540  入边界：state 过滤 + messages 重置为 HumanMessage(description)
  - deepagents/middleware/subagents.py:474-512  出边界：只取最后一条非空 AIMessage 的文本

运行（在 research_deepagent 目录下，复用项目 .venv 与 .env）：
    uv run --frozen python ../notes/task4/code/delegation_boundary.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# uv run 不会自动读取 .env：先按常规向上查找，再显式指向 research_deepagent/.env
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

# ---- 确定性工具 + 进程内计数器 ----
# 计数器是本脚本的取证核心：它记录"lookup 到底被调用了几次"，
# 而父 Agent 的 messages 里看不到这些调用 —— 两者对照就是隔离的证据。
NOISE_PAD = "【原始检索噪声】一段本不该出现在父上下文里的长文本。" * 40
LOOKUP_CALLS: list[str] = []


@tool
def lookup(topic: str) -> str:
    """检索指定主题的资料，返回较长的原文（模拟真实搜索结果）。"""
    LOOKUP_CALLS.append(topic)
    return f"[RAW-NOISE] topic={topic}：{NOISE_PAD}"


# ---- 子 Agent：唯一职责是"读文件 → 多次检索 → 压成一句话" ----
researcher = {
    "name": "researcher",
    "description": "需要读取本地简报、进行多次资料检索、并把结果压缩成一句话结论时使用。",
    "system_prompt": """你是检索员，严格按顺序执行：
1. 先 read_file 读取 /data/brief.md，从中取出形如 ALPHA-XXXX 的口令；
2. 分别用 topic='alpha'、topic='beta'、topic='gamma' 调用 lookup 三次；
3. 最后只回一句不超过 60 字的中文结论，句末附上该口令。

禁止输出原始检索内容，禁止超过一句话。""",
    "tools": [lookup],
}

# ---- 父 Agent：写文件 → 委派 → 汇报，自己不查资料 ----
PARENT_PROMPT = """你是研究协调者。严格按以下步骤执行：

1. 用 write_file 把下面这段背景原文一字不差地写入 /data/brief.md：
   口令：ALPHA-7391；主题：子 Agent 上下文隔离验证。
2. 用 task 工具委派，subagent_type 必须是 researcher。
   description 里要说明：读取 /data/brief.md 取得口令，用 lookup 检索 alpha、beta、gamma，
   然后只回一句结论加口令。
3. 收到子 Agent 的结论后，直接转述给用户。不要自己调用 lookup。
"""

agent = create_deep_agent(
    model=model,
    tools=[lookup],
    system_prompt=PARENT_PROMPT,
    subagents=[researcher],
)

result = agent.invoke({"messages": [{"role": "user", "content": "请按流程完成委派，并告诉我最终结论。"}]})
messages = result["messages"]

# ---- 证据 1：父 Agent 自己发起了哪些工具调用 ----
parent_tool_calls = []
for message in messages:
    for tool_call in getattr(message, "tool_calls", None) or []:
        parent_tool_calls.append(tool_call)

print("=== 父 Agent 的工具调用序列 ===")
for tool_call in parent_tool_calls:
    print(f"- {tool_call['name']}: {str(tool_call['args'])[:100]}")

# ---- 证据 2：lookup 在进程内被调用了多少次（全部发生在子 Agent 内部）----
print("\n=== lookup 调用计数（进程内）===")
print(f"共 {len(LOOKUP_CALLS)} 次：{LOOKUP_CALLS}")
print("说明：这些调用只发生在子 Agent 的上下文里，父 Agent 的 messages 中不应出现其原文。")

# ---- 证据 3：父上下文里有没有检索原文泄漏 ----
def content_of(message) -> str:
    raw = getattr(message, "content", "")
    return raw if isinstance(raw, str) else str(raw)


leaked = [m for m in messages if m.type == "tool" and "[RAW-NOISE]" in content_of(m)]
print("\n=== 泄漏检查 ===")
print(f"父上下文中含 [RAW-NOISE] 的 ToolMessage 数量: {len(leaked)}")

# ---- 证据 4：task 的返回值（出边界的那一条 ToolMessage）----
task_call_ids = {
    tool_call["id"]
    for tool_call in parent_tool_calls
    if tool_call["name"] == "task"
}
task_results = [m for m in messages if m.type == "tool" and getattr(m, "tool_call_id", None) in task_call_ids]

print("\n=== task 返回值（子 Agent 交回的全部内容）===")
for message in task_results:
    text = content_of(message)
    print(f"长度: {len(text)} 字符")
    print(f"内容: {text}")

# ---- 证据 5：父写的文件确实进了 state（files 是 files 方向能穿透的前提）----
print("\n=== state['files'] ===")
files = result.get("files") or {}
print("文件列表:", list(files.keys()))
brief = files.get("/data/brief.md") or {}
brief_content = brief.get("content", "") if isinstance(brief, dict) else str(brief)
print("--- /data/brief.md ---")
print(brief_content[:300])

# ---- 断言：三个命题逐条对账 ----
print("\n=== 断言 ===")
parent_names = [tc["name"] for tc in parent_tool_calls]
assert "task" in parent_names, "父 Agent 没有调用 task：委派未发生，检查 description 与系统提示"
print("[1/5] 父 Agent 确实调用了 task")
assert "lookup" not in parent_names, "父 Agent 自己调用了 lookup：本次实验要求全部检索发生在子 Agent 内部"
print("[2/5] 父 Agent 没有自己去查资料")
assert LOOKUP_CALLS, "lookup 一次都没被调用：子 Agent 没有执行检索，检查其 tools 与提示词"
print(f"[3/5] 子 Agent 内部执行了 {len(LOOKUP_CALLS)} 次检索")
assert not leaked, "子 Agent 的检索原文泄漏进了父上下文：messages 隔离失效"
print("[4/5] 检索原文未进入父上下文（messages 方向已阻断）")
assert task_results, "找不到 task 的返回消息"
task_text = content_of(task_results[-1])
assert "ALPHA-7391" in task_text, "子 Agent 没能读到 /data/brief.md 里的口令：files 方向未穿透"
assert len(task_text) < 400, f"task 返回值过长（{len(task_text)} 字符）：子 Agent 没有压缩结果，隔离失去意义"
print("[5/5] 子 Agent 读到了父写的文件（files 方向穿透），且返回值被压缩")

print("\n>>> 验证通过：messages 隔离 / files 穿透 / 返回值压缩 三条同时成立")
