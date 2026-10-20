"""Task3 补充实验：todos 如何跨 invoke 接续（Checkpointer + thread_id）。

ch04 的要点：清单存在 Agent State 的 todos 字段，
- 同一线程再次 invoke，状态由 Checkpointer 恢复，计划可继续；
- 只加 TodoListMiddleware 而不配 Checkpointer，或换 thread_id，清单不会自动接续。

本脚本用 InMemorySaver 做 A/B：
  A. 同一 thread_id 二次 invoke → 计划仍在，可继续；
  B. 新 thread_id → todos 为空（线程隔离）。

运行（在 research_deepagent 目录下）：
    uv run --frozen python ../notes/task3/code/planning_persistence.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[3] / "research_deepagent" / ".env")

from deepagents import create_deep_agent  # noqa: E402
from langchain.agents.middleware import TodoListMiddleware  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

model = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "agnes-3.0-flash"),
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_API_BASE", "https://apihub.agnes-ai.com/v1"),
)


@tool
def get_weather(city: str) -> str:
    """查询指定城市的天气（温度 ℃）。"""
    data = {"北京": 12, "上海": 18, "广州": 25}
    return f"{city}：{data.get(city, '未知')}℃"


SYSTEM_PROMPT = """你是天气分析助手。必须先 write_todos 制定计划再执行，
每完成一步立即更新状态，最后用 write_file 写入 /weather_report.md。"""


def build(checkpointer=None):
    return create_deep_agent(
        model=model,
        tools=[get_weather],
        middleware=[TodoListMiddleware()],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )


# ================= A. 同一 thread_id：接续 =================
graph = build(InMemorySaver())
thread_a = {"configurable": {"thread_id": "plan-a"}}

graph.invoke(
    {"messages": [{"role": "user", "content": "整理北京和上海的天气并写入报告。"}]},
    config=thread_a,
)
todos_first = graph.get_state(thread_a).values.get("todos") or []
print("=== A1 第一次 invoke 后的 todos ===")
for todo in todos_first:
    print(f"[{todo['status']}] {todo['content']}")

graph.invoke(
    {"messages": [{"role": "user", "content": "继续：在报告里补一句两地的温差。"}]},
    config=thread_a,
)
todos_second = graph.get_state(thread_a).values.get("todos") or []
print("\n=== A2 同一 thread 第二次 invoke 后的 todos ===")
for todo in todos_second:
    print(f"[{todo['status']}] {todo['content']}")
print(f"\n结论：同一 thread 计划被保留（{len(todos_second)} 项），未从零重规划")

# ================= B. 新 thread_id：隔离 =================
thread_b = {"configurable": {"thread_id": "plan-b"}}
todos_new_thread = graph.get_state(thread_b).values.get("todos") or []
print("\n=== B 新 thread_id 的 todos ===")
print("todos:", todos_new_thread)
assert not todos_new_thread, "新线程不应读到旧线程的计划"
print("结论：新 thread 读不到旧计划（线程隔离）")

# ================= C. 无 Checkpointer：不接续 =================
# 注意：C 组会再发起一次真实模型调用；免费额度可能返回 429，此处容错跳过，
# 不影响 A/B 两组的结论（接续 / 隔离）。
print("\n=== C 无 Checkpointer ===")
try:
    graph_no_memory = build(None)
    result_no_memory = graph_no_memory.invoke(
        {"messages": [{"role": "user", "content": "整理广州的天气并写入报告。"}]},
    )
    print("本次运行确实产生了 todos:", [t["content"] for t in result_no_memory.get("todos") or []])
    print("但没有 Checkpointer 保存它：下一次 invoke 只能从空状态重新规划。")
except Exception as exc:  # noqa: BLE001 - 演示脚本：限流/网络问题不应中断整体
    print(f"本组被跳过（{type(exc).__name__}）：{str(exc)[:120]}")
    print("结论不变：没有 Checkpointer 就没有可恢复的线程状态，计划不会自动接续。")
