"""Task2 补充实验：同一个写入任务，StateBackend（默认）vs FilesystemBackend。

目的：亲眼看到「Agent 说写好了」和「文件真的在磁盘上」是两回事，
      从而理解 ch03 的核心——backend 决定产物存在哪、活多久。

运行（在 research_deepagent 目录下）：
    uv run --frozen python ../notes/task2/code/backend_compare.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[3] / "research_deepagent" / ".env")

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import FilesystemBackend  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

TASK2_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = TASK2_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "agnes-3.0-flash"),
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_API_BASE", "https://apihub.agnes-ai.com/v1"),
)

PROMPT = (
    "请用 write_file 在 {path} 写入一行内容：backend 对照实验。"
    "只做这一次写入，不要读、不要改。"
)


def run(label: str, backend, path: str) -> None:
    agent = create_deep_agent(model=model, backend=backend, system_prompt="你是文件操作助手。")
    result = agent.invoke({"messages": [{"role": "user", "content": PROMPT.format(path=path)}]})

    on_disk = (TASK2_DIR / path.lstrip("/")).exists()
    state_files = list((result.get("files") or {}).keys())

    print(f"\n=== {label} ===")
    print("Agent 回答:", str(result["messages"][-1].content)[:80].replace("\n", " "))
    print("state['files'] 里的键:", state_files)
    print("磁盘上文件是否存在:", on_disk, "|", TASK2_DIR / path.lstrip("/"))


print(">>> A：默认 backend（不传 backend 参数）")
run("A. StateBackend（默认）", None, "/outputs/state_note.md")

print("\n>>> B：FilesystemBackend（root_dir 指向 task2 目录）")
run(
    "B. FilesystemBackend",
    FilesystemBackend(root_dir=TASK2_DIR, virtual_mode=True),
    "/outputs/disk_note.md",
)
