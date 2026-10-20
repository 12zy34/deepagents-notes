"""Task3（ch04 任务规划）：显式启用 TodoListMiddleware，让 Agent 先规划再执行。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch04-task-planning/

v0.7 的关键变化：TodoListMiddleware 默认不装，必须通过 middleware=[...] 显式加入，
加入后才获得 write_todos 工具 + todos 状态 + 规划提示词三件套。

本脚本用一个确定性的三步任务（查三城天气 → 算平均温度 → 写报告），
避免外部搜索的不确定性，方便观察 todos 的状态流转与产物。

运行（在 research_deepagent 目录下）：
    uv run --frozen python ../notes/task3/code/planning_agent.py
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

model = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "agnes-3.0-flash"),
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_API_BASE", "https://apihub.agnes-ai.com/v1"),
)

# ---- 确定性工具：固定返回，便于核对 Agent 是否真的用了工具结果 ----
WEATHER = {
    "北京": {"temp": 12, "sky": "晴"},
    "上海": {"temp": 18, "sky": "多云"},
    "广州": {"temp": 25, "sky": "小雨"},
}


@tool
def get_weather(city: str) -> str:
    """查询指定城市的天气（温度 ℃ 与天气现象）。"""
    data = WEATHER.get(city)
    if data is None:
        return f"未收录城市：{city}"
    return f"{city}：{data['temp']}℃，{data['sky']}"


@tool
def average_temperature(temps: list[float]) -> float:
    """计算一组温度的平均值（保留一位小数）。"""
    return round(sum(temps) / len(temps), 1)


SYSTEM_PROMPT = """你是严谨的天气分析助手。面对任务时：
1. 必须先调用 write_todos 制定计划，把任务拆成 3-5 个可执行步骤；
2. 每开始一步，先把该项置为 in_progress；每完成一步，立即置为 completed；
3. 需要数据时调用 get_weather，需要算平均时调用 average_temperature，
   不要自己心算；
4. 最后用 write_file 把报告写入 /weather_report.md（Markdown，含三城数据与平均温度）；
5. 报告写完后，用一段文字给出结论，不要在 write_todos 同一次调用里给结论。
"""

agent = create_deep_agent(
    model=model,
    tools=[get_weather, average_temperature],
    # ★ 本章核心：v0.7 默认不装，必须显式加入
    middleware=[TodoListMiddleware()],
    system_prompt=SYSTEM_PROMPT,
)

TASK = "整理北京、上海、广州三地的天气，计算三地平均气温，并写一份简短报告。"

result = agent.invoke({"messages": [{"role": "user", "content": TASK}]})

# ---- 证据 1：工具调用序列（含 write_todos 的每次更新）----
print("=== 工具调用序列 ===")
for message in result["messages"]:
    for tool_call in getattr(message, "tool_calls", None) or []:
        name = tool_call["name"]
        args = tool_call["args"]
        if name == "write_todos":
            states = [f"{t['content']}={t['status']}" for t in args.get("todos", [])]
            print("- write_todos:")
            for state in states:
                print(f"    · {state}")
        else:
            print(f"- {name}: {str(args)[:120]}")

# ---- 证据 2：最终 todos 状态 ----
print("\n=== 最终 todos ===")
todos = result.get("todos") or []
for todo in todos:
    print(f"[{todo['status']}] {todo['content']}")
assert todos, "todos 为空：模型没有使用 write_todos"
assert all(t["status"] == "completed" for t in todos), "仍有未完成步骤，检查轨迹"

# ---- 证据 3：产物（默认 StateBackend，文件在 state['files'] 里）----
print("\n=== 产物（state['files']）===")
files = result.get("files") or {}
print("文件列表:", list(files.keys()))
report = files.get("/weather_report.md") or {}
content = report.get("content", "") if isinstance(report, dict) else str(report)
print("--- /weather_report.md ---")
print(content[:800])

print("\n=== Agent 最终回答 ===")
print(result["messages"][-1].content)
