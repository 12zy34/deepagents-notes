"""Task6 补充实验：实测"技能索引"每轮到底花多少 token（用真实模型 Agnes）。

对应课程：ch07 的结论是"索引是每轮租金"，但一直只有量级估算。本脚本用真实模型
（Agnes 免费网关）跑最小调用，拿到模型自己计数的 input_tokens，把这条结论变成数字。

测量三件事：
  1. 开 skills 的"固定开销"：skills=None 与 skills=[]（空列表）之间差多少——即那段
     "How to Use Skills" 说明文字本身的成本；
  2. 每个技能一行索引的"边际成本"：3 个技能 vs 8 个技能；
  3. "每轮都重付"：同一 thread 连续两次 invoke，两次的 input_tokens 都含索引、几乎相同。

用法说明：
  - RecordingChatOpenAI 只负责把每次模型调用收到的 system prompt 抄下来；
  - UsageCapture 是一个回调，在每次 LLM 调用结束时抓 usage_metadata（Agnes 自己算的）。
  两者按调用顺序对齐。

运行（在 research_deepagent 目录下，复用 .venv 与 .env，约 7 次真实模型调用）：
    uv run --frozen python ../notes/task6/code/skills_index_cost.py
"""

import json
import os
import platform
import time
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[3] / "research_deepagent" / ".env")

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import StateBackend  # noqa: E402
from deepagents.backends.utils import create_file_data  # noqa: E402
from langchain_core.callbacks import BaseCallbackHandler  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langchain_openai.chat_models.base import OpenAIRateLimitError  # noqa: E402

CALLS: list[str] = []          # 每次模型调用的 system prompt
USAGES: list[int] = []         # 每次模型调用的 input_tokens（与 CALLS 对齐）


def text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


class RecordingChatOpenAI(ChatOpenAI):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        for attempt in range(1, 5):
            try:
                result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except OpenAIRateLimitError as e:
                print(f"[限流] 第 {attempt} 次 429，等 {15*attempt}s")
                time.sleep(15 * attempt)
                continue
            break
        else:
            raise RuntimeError("多次限流仍失败")
        for m in messages:
            if m.type == "system":
                CALLS.append(text_of(m))
                break
        return result


class UsageCapture(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):  # noqa: ARG002
        try:
            gen = response.generations[0][0]
            um = getattr(gen.message, "usage_metadata", None) or {}
            USAGES.append(um.get("input_tokens", 0))
        except Exception:  # noqa: BLE001
            USAGES.append(0)


def skill_md(name: str, description: str) -> dict:
    return create_file_data(
        "---\n"
        f"name: {json.dumps(name, ensure_ascii=False)}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n# body\n"
    )


def make_model() -> RecordingChatOpenAI:
    return RecordingChatOpenAI(
        model=os.environ.get("AGENTSEEK_MODEL", "agnes-3.0-flash"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_API_BASE"],
        temperature=0,
    )


def make_files(count: int) -> dict:
    return {
        f"/skills/s{n}/SKILL.md": skill_md(f"s{n}", f"用于 token 成本测量的第 {n} 号技能，描述固定约六十个字符左右。")
        for n in range(count)
    }


def index_chars(system: str) -> int:
    start = system.find("**Available Skills:**")
    end = system.find("**How to Use Skills")
    if start == -1:
        return 0
    if end == -1:
        return len(system) - start
    return end - start


def run_once(skills, files, thread) -> int:
    CALLS.clear()
    USAGES.clear()
    capture = UsageCapture()
    agent = create_deep_agent(model=make_model(), backend=StateBackend(), skills=skills)
    agent.invoke(
        {"messages": [{"role": "user", "content": "只回复：ok"}], "files": files},
        config={"configurable": {"thread_id": thread}, "callbacks": [capture]},
    )
    return USAGES[-1] if USAGES else 0


print("$ uv run --frozen python ../notes/task6/code/skills_index_cost.py\n")

none_tok = run_once(None, {}, "none")
empty_tok = run_once([], {}, "empty")
three_tok = run_once(["/skills/"], make_files(3), "three")
eight_tok = run_once(["/skills/"], make_files(8), "eight")

print("=== input_tokens（Agnes 实际计数，单次模型调用）===")
print(f"skills=None        : {none_tok}")
print(f"skills=[]（空列表） : {empty_tok}   （固定开销 = {empty_tok - none_tok}）")
print(f"skills=3 个        : {three_tok}   （每技能边际 ≈ {(three_tok - empty_tok)/3:.0f}）")
print(f"skills=8 个        : {eight_tok}   （每技能边际 ≈ {(eight_tok - empty_tok)/8:.0f}）")

# 索引区字符数（供参考）
CALLS.clear()
agent8 = create_deep_agent(model=make_model(), backend=StateBackend(), skills=["/skills/"])
agent8.invoke(
    {"messages": [{"role": "user", "content": "只回复：ok"}], "files": make_files(8)},
    config={"configurable": {"thread_id": "chars"}},
)
print("\n=== 索引区字符数（8 个技能）===")
print(f"索引区约 {index_chars(CALLS[-1])} 字符（name + description + 路径三行 × 8）")

# 每轮重付：同 thread 两次 invoke
CALLS.clear()
USAGES.clear()
capture = UsageCapture()
agent = create_deep_agent(model=make_model(), backend=StateBackend(), skills=["/skills/"])
cfg = {"configurable": {"thread_id": "twoturn"}, "callbacks": [capture]}
files = make_files(3)
agent.invoke({"messages": [{"role": "user", "content": "只回复：ok"}], "files": files}, config=cfg)
agent.invoke({"messages": [{"role": "user", "content": "只回复：ok"}], "files": files}, config=cfg)
print("\n=== 同一 thread 连续两次调用的 input_tokens ===")
for i, tok in enumerate(USAGES, 1):
    print(f"第 {i} 次模型调用: {tok}（索引在提示词里：{'Available Skills' in CALLS[i-1]}）")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    f"模型：{os.environ.get('AGENTSEEK_MODEL', 'agnes-3.0-flash')}（真实调用）\n"
    "运行日期：2026-10-28"
)
