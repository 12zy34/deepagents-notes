"""Task2（ch03 虚拟文件系统）：让 Agent 完成「写入 — 读回 — 修改」，并验证产物落盘。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch03-virtual-filesystem/

与 task1 的关键差异：task1 没有指定 backend（默认 StateBackend），文件只存在
LangGraph 线程状态里，会话结束即丢、磁盘上摸不到；本练习换成 FilesystemBackend，
产物是真实磁盘文件，可以亲手在 notes/task2/outputs/ 下找到。

运行（在 research_deepagent 目录下，复用项目 .venv 与 .env）：
    uv run --frozen python ../notes/task2/code/write_read_edit.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# uv run 不会自动读取 .env：先按常规向上查找，再显式指向 research_deepagent/.env
load_dotenv()
_PROJECT_ENV = Path(__file__).resolve().parents[3] / "research_deepagent" / ".env"
load_dotenv(_PROJECT_ENV)

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import FilesystemBackend  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

# ---- 1. 产物落盘目录：notes/task2/outputs/（由脚本位置推导，与运行目录无关）----
TASK2_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = TASK2_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- 2. 模型（与 task1 相同的接入方式）----
model = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "agnes-3.0-flash"),
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_API_BASE", "https://apihub.agnes-ai.com/v1"),
)

# ---- 3. 关键差异：可插拔 Backend ----
# FilesystemBackend 把 Agent 的虚拟路径映射到真实磁盘：
#   /outputs/agent_note.md  →  {TASK2_DIR}/outputs/agent_note.md
# virtual_mode=True 开启路径沙箱：拦截 `..`、`~` 与越界绝对路径（v0.6.0 起必填）。
backend = FilesystemBackend(root_dir=TASK2_DIR, virtual_mode=True)

# ---- 4. 三步任务的系统提示 ----
SYSTEM_PROMPT = """你是一个严谨的笔记助手。请严格按以下三步操作虚拟文件系统：

1. 写入：用 write_file 创建 /outputs/agent_note.md，内容为不超过 10 行的
   Markdown 笔记，主题为「DeepAgents 虚拟文件系统的三个核心机制」，
   必须包含一行占位文本：`TODO: 待补充`。
2. 读回：用 read_file 读取 /outputs/agent_note.md，核对内容与你写入的一致。
3. 修改：用 edit_file 将 `TODO: 待补充` 精确替换为 `DONE: 已由 Agent 二次确认`。

完成后用一句话汇报：做了哪三步、最终文件路径是什么。
不要做这三步以外的任何文件操作。"""

agent = create_deep_agent(
    model=model,
    backend=backend,
    system_prompt=SYSTEM_PROMPT,
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "开始执行你的三步任务。"}]}
)

# ---- 5. 打印 Agent 行为轨迹与最终回答 ----
print("=== 工具调用序列 ===")
for message in result["messages"]:
    for tool_call in getattr(message, "tool_calls", None) or []:
        print(f"- {tool_call['name']}: {str(tool_call['args'])[:150]}")

print("\n=== Agent 最终回答 ===")
print(result["messages"][-1].content)

# ---- 6. 人工验证：亲手在项目目录里找到那份产物 ----
artifact = OUTPUT_DIR / "agent_note.md"
print("\n=== 磁盘验证 ===")
print(f"文件存在: {artifact.exists()} | 路径: {artifact}")
if artifact.exists():
    text = artifact.read_text(encoding="utf-8")
    print(f"大小: {artifact.stat().st_size} bytes | 行数: {len(text.splitlines())}")
    print("--- 文件全文 ---")
    print(text)
    assert "DONE: 已由 Agent 二次确认" in text, "edit_file 的修改未生效"
    assert "TODO: 待补充" not in text, "占位文本未被替换"
    print(">>> 验证通过：写入 → 读回 → 修改 全链路完成，产物已真实落盘")
else:
    raise SystemExit(">>> 验证失败：产物不在磁盘上，检查 backend 是否为 FilesystemBackend")
