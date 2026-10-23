# -*- coding: utf-8 -*-
"""生成 task4 的思维导图（PNG），与 task1–task3 的图同级放在 notes/task4/ 下。

为什么用代码画而不是 AI 生图：图中每个叶子都是机制断言，中文错一个字就废，
代码渲染可以随时改字重出图。

编辑方法：改下面的 BRANCHES，然后（任意有 matplotlib + 微软雅黑的 Python 下）：
    python notes/task4/mindmap.py
"""

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch

TASK_DIR = Path(__file__).resolve().parent
OUT = TASK_DIR / "子Agent与上下文隔离.png"

REG = r"C:\Windows\Fonts\msyh.ttc"
BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
F = FontProperties(fname=REG)
FB = FontProperties(fname=BOLD) if Path(BOLD).exists() else F

INK = "#16150F"
SOFT = "#454134"
FAINT = "#83806F"
RULE = "#D8D2C1"
PAPER = "#FDFCF8"
ACCENT = "#8A2B2B"
TINTS = ["#F3EAE6", "#EDEFE7", "#F2EFE4", "#E9EDEA", "#F3EAE6"]

TITLE = "第 5 章 · 子 Agent 与上下文隔离 —— 让 Agent 学会委派"
SUBTITLE = "叶片写机制，不写功能名 · 依据 deepagents 0.7.8：subagents.py:252-540，graph.py:728 / 740 / 806"
FOOTER = "配套：lessons/0001 交互课 · reference/ch05-subagent-mechanics.html 速查 · reference/interview-answers.html 面试答案"

BRANCHES = [
    ("① 为什么隔离", [
        "子任务 5 次搜索 × 3k tokens，全压父上下文",
        "主 Agent 只要结论，不要中间过程",
        "卸载治单次爆炸，不治跨子任务累积",
    ]),
    ("② 边界：两行赋值", [
        "入：messages 丢弃 → 重置为 [description]",
        "入：其余 state 键逐键拷贝（files 在内）",
        "出：取最后一条非空 AIMessage 文本",
        "出：files 经 state_update 合并回父",
    ]),
    ("③ 继承：spec 侧", [
        "有继承：tools / model / interrupt_on / permissions",
        "声明即整体替换：tools=[] 是清零，不是用默认",
        "完全不继承：system_prompt / middleware / skills",
        "general-purpose：中间件只继承同名覆盖",
    ]),
    ("④ 代价与失败模式", [
        "带宽只有两个字符串 → description 必须自包含",
        "子 Agent 回传原始数据 = 隔离白做",
        "description 语义重叠 → 派错人",
        "只写「是什么」不写「何时用」→ 从不委派",
    ]),
    ("⑤ 面试高频", [
        "隔离的是 messages，不是整个 state",
        "todos 双向不通：无 reducer、无清晰语义",
        "提示词不继承：角色冲突 + 工具指令失效",
        "文件是唯一双向无损的载体",
    ]),
]

WRAP = 46
ASCII_TOKEN = re.compile(r"[A-Za-z0-9_\-./:<>=()\[\]{}\"'`]+")


def wrap_tokens(text, limit=WRAP):
    """折行，但不切断英文标识符（HumanMessage、state_update 之类必须保持完整）。"""
    tokens, pos = [], 0
    for m in ASCII_TOKEN.finditer(text):
        if m.start() > pos:
            tokens.extend(text[pos:m.start()])
        tokens.append(m.group())
        pos = m.end()
    if pos < len(text):
        tokens.extend(text[pos:])

    lines, cur = [], ""
    for tok in tokens:
        if len(cur) + len(tok) > limit and cur:
            lines.append(cur)
            cur = tok
        else:
            cur += tok
    if cur:
        lines.append(cur)
    return lines


def main():
    wrapped = [[wrap_tokens(leaf) for leaf in leaves] for _, leaves in BRANCHES]
    total_lines = sum(len(w) for branch in wrapped for w in branch)

    fig, ax = plt.subplots(figsize=(16, 11), dpi=150)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.030, 0.962, TITLE, fontproperties=FB, fontsize=18, color=INK, va="top")
    ax.text(0.030, 0.925, SUBTITLE, fontproperties=F, fontsize=9, color=FAINT, va="top")
    ax.plot([0.030, 0.970], [0.905, 0.905], color=RULE, lw=0.9)

    top, bottom = 0.868, 0.075
    gap_units = 0.9 * len(BRANCHES)
    unit = (top - bottom) / (total_lines + gap_units)

    # 根节点
    root_x, root_w, root_cx = 0.030, 0.118, 0.030 + 0.118 / 2
    root_y = 0.50
    root_h = 0.148
    ax.add_patch(FancyBboxPatch(
        (root_x, root_y - root_h / 2), root_w, root_h,
        boxstyle="round,pad=0.006,rounding_size=0.014",
        facecolor=ACCENT, edgecolor="none",
    ))
    ax.text(root_cx, root_y + 0.030, "子 Agent",
            fontproperties=FB, fontsize=15, color="white", ha="center", va="center")
    ax.text(root_cx, root_y, "上下文隔离",
            fontproperties=FB, fontsize=15, color="white", ha="center", va="center")
    ax.text(root_cx, root_y - 0.034, "委派 = 一次函数调用",
            fontproperties=F, fontsize=8.6, color="#F0D6D0", ha="center", va="center")

    branch_x, branch_w = 0.205, 0.145
    leaf_x = 0.395
    cursor = top

    for i, ((name, _), lines_per_leaf) in enumerate(zip(BRANCHES, wrapped)):
        block_h = len(lines_per_leaf) * unit
        branch_cy = cursor - block_h / 2

        ax.add_patch(FancyBboxPatch(
            (branch_x, branch_cy - 0.030), branch_w, 0.060,
            boxstyle="round,pad=0.005,rounding_size=0.010",
            facecolor=TINTS[i], edgecolor=RULE, lw=0.9,
        ))
        ax.text(branch_x + branch_w / 2, branch_cy, name,
                fontproperties=FB, fontsize=11.4, color=INK, ha="center", va="center")

        ax.annotate(
            "",
            xy=(branch_x, branch_cy),
            xytext=(root_x + root_w + 0.006, root_y),
            arrowprops=dict(arrowstyle="-", color=RULE, lw=1.2,
                            connectionstyle="arc3,rad=%.2f" % (-0.05 + 0.025 * i)),
        )

        y = cursor
        for lines in lines_per_leaf:
            leaf_cy = y - len(lines) * unit / 2
            ax.plot([branch_x + branch_w, leaf_x - 0.010], [branch_cy, leaf_cy], color=RULE, lw=0.85)
            ax.plot([leaf_x - 0.010, leaf_x], [leaf_cy, leaf_cy], color=RULE, lw=0.85)
            ax.scatter([leaf_x], [leaf_cy], s=10, color=ACCENT, zorder=3)
            ax.text(leaf_x + 0.008, leaf_cy, "\n".join(lines),
                    fontproperties=F, fontsize=10.5, color=SOFT,
                    ha="left", va="center", linespacing=1.5)
            y -= len(lines) * unit

        cursor -= block_h + 0.9 * unit

    ax.text(0.030, 0.022, FOOTER, fontproperties=F, fontsize=8.4, color=FAINT, va="bottom")

    fig.savefig(OUT, facecolor=PAPER, bbox_inches="tight", pad_inches=0.24)
    print("已生成:", OUT)


if __name__ == "__main__":
    main()
