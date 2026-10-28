"""Task6（ch08 长期记忆）：验证 memory= 的"全文注入"与"会话快照"。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/

本脚本沿用 task5 的"录制型假模型"：不调用真实模型，把每次发给模型的 system prompt 抄下来再断言，
零 token 验证四条命题：

  1. memory= 的文件全文出现在 system prompt（而 skills= 的正文不出现）—— 全文 vs 索引；
  2. HTML 注释 <!-- ... --> 被剥掉，模型看不到；
  3. 同一个 thread 第二次 invoke 不重载 —— state 里已有 memory_contents 就跳过；
  4. 换 thread_id 才重载 —— 新 thread 的 state 里没有 memory_contents。

机制依据（deepagents 0.7.8）：
  - deepagents/middleware/memory.py:289   if "memory_contents" in state: return None
  - deepagents/middleware/memory.py:295   download_files(list(self.sources))  # 按精确路径拿全文
  - deepagents/middleware/memory.py:303   contents[path] = content.decode("utf-8")
  - deepagents/middleware/memory.py:262   _strip_html_comments（注入前剥 <!-- -->）
  - deepagents/middleware/memory.py:356   append_to_system_message（每次模型调用都拼全文）
  - deepagents/middleware/skills.py:946   skills 的同款快照判断（对照）

运行（在 research_deepagent 目录下，复用项目 .venv，无需 .env）：
    uv run --frozen python ../notes/task6/code/memory_loading.py
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

RECEIVED: list[list] = []
SEEN_SYSTEM_PROMPTS: list[str] = []


def text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


class RecordingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        RECEIVED.append(list(messages))
        for m in messages:
            if m.type == "system":
                SEEN_SYSTEM_PROMPTS.append(text_of(m))
                break
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


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
# 材料：一份记忆文件（含 HTML 注释）+ 一个技能（正文含埋点，用来对照"不注入"）
# ----------------------------------------------------------------------------

MEMORY_BODY = (
    "# 用户偏好\n"
    "- 代码注释用中文，变量名用英文\n"
    "- 喜欢简洁风格\n"
    "<!-- 内部备注：这段是机器标记，模型不该看到 -->\n"
    "MEMORY-TOKEN-8801\n"
)
SKILL_BODY = "# demo\n\n正文埋点：SKILL-TOKEN-1180"

FILES = {
    "/memories/preferences.md": create_file_data(MEMORY_BODY),
    # skills=["/skills/"] 只 ls 一层，所以技能目录必须直接挂在 /skills/ 下
    "/skills/demo/SKILL.md": skill_md("demo", "用于对照：skills 正文不进提示词。", SKILL_BODY),
}

print("$ uv run --frozen python ../notes/task6/code/memory_loading.py\n")

agent = create_deep_agent(
    model=RecordingModel(responses=[AIMessage(content="收到。")]),
    backend=StateBackend(),
    memory=["/memories/preferences.md"],
    skills=["/skills/"],
    checkpointer=MemorySaver(),
)

thread1 = {"configurable": {"thread_id": "t1"}}
thread2 = {"configurable": {"thread_id": "t2"}}


def invoke(payload: dict, config: dict) -> str:
    before = len(SEEN_SYSTEM_PROMPTS)
    agent.invoke(payload, config=config)
    return SEEN_SYSTEM_PROMPTS[before]


# 第 1 轮
p1 = invoke({"messages": [{"role": "user", "content": "你好"}], "files": FILES}, thread1)

# 第 2 轮：同一 thread，改了 memory 文件（把 token 换掉）
NEW_MEMORY_BODY = MEMORY_BODY.replace("MEMORY-TOKEN-8801", "MEMORY-TOKEN-9999")
p2 = invoke(
    {"messages": [{"role": "user", "content": "你好"}], "files": {"/memories/preferences.md": create_file_data(NEW_MEMORY_BODY)}},
    thread1,
)

# 第 3 轮：新 thread，用新内容
p3 = invoke(
    {"messages": [{"role": "user", "content": "你好"}], "files": {"/memories/preferences.md": create_file_data(NEW_MEMORY_BODY)}},
    thread2,
)

print("=== 各轮 system prompt 里的关键 token ===")
for name, prompt in [("第 1 轮", p1), ("第 2 轮(同 thread)", p2), ("第 3 轮(新 thread)", p3)]:
    print(f"{name}: 记忆全文 MEMORY-TOKEN-8801 = {('MEMORY-TOKEN-8801' in prompt)}，"
          f"新值 9999 = {('MEMORY-TOKEN-9999' in prompt)}，"
          f"skills 正文 SKILL-TOKEN = {('SKILL-TOKEN-1180' in prompt)}")

print("\n=== HTML 注释是否被剥掉 ===")
print("提示词里含 '内部备注':", "内部备注" in p1)

print("\n=== state 里的字段 ===")
st1 = agent.get_state(thread1).values
print("memory_contents 的键:", list(st1.get("memory_contents", {}).keys()))
print("skills_metadata 条数:", len(st1.get("skills_metadata", [])))

# ----------------------------------------------------------------------------
# 断言
# ----------------------------------------------------------------------------

print("\n=== 断言 ===")

# 1. memory 全文进提示词
assert "MEMORY-TOKEN-8801" in p1, "memory 全文没有进入 system prompt"
assert "变量名用英文" in p1, "memory 的具体内容没有进入 system prompt"
print("[1/5] memory= 的文件全文进入 system prompt")

# 2. skills 正文不进提示词（对照：全文 vs 索引）
assert "SKILL-TOKEN-1180" not in p1, "skills 正文被注入了：全文/索引的区分失败"
assert "- **demo**:" in p1, "skills 的索引（name+description）也没有出现"
print("[2/5] skills 只进索引、不进正文（对照成立）")

# 3. HTML 注释被剥掉
assert "内部备注" not in p1, "HTML 注释没有被剥掉，模型看到了不该看的内容"
print("[3/5] HTML 注释 <!-- --> 在注入前被剥掉")

# 4. 同 thread 不重载（快照）
assert "MEMORY-TOKEN-9999" not in p2, "同 thread 第二轮加载了新记忆：快照失效"
print("[4/5] 同 thread 第二轮不重载（state 已有 memory_contents）")

# 5. 换 thread 重载
assert "MEMORY-TOKEN-9999" in p3, "换 thread 后仍未加载新记忆"
print("[5/5] 换 thread_id 才重新加载")

print("\n>>> 验证通过：memory 全文注入 / skills 只进索引 / HTML 注释剥除 / 会话快照 / 换线程重载")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    "模型：未调用（录制型假模型，零 token 消耗）\n"
    "运行日期：2026-10-27"
)
