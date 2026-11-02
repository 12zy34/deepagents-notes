# -*- coding: utf-8 -*-
"""生成 task8 的思维导图（PNG），放在 notes/task8/ 下。

编辑方法：改 BRANCHES，然后：
    uv run --with matplotlib python notes/task8/mindmap.py
"""

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch

TASK_DIR = Path(__file__).resolve().parent
OUT = TASK_DIR / "教学Agent升级.png"

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
TINTS = ["#F3EAE6", "#EDEFE7", "#F2EFE4", "#E9EDEA", "#F3EAE6", "#EDEFE7"]

TITLE = "Task8 · 可复现教学 Agent：四能力同图"
SUBTITLE = "ch01–09 + ch13 综合 · deepagents 0.7.8 · 真实评分模型端到端闭环"
FOOTER = "配套：lessons/0007 · notes/task8/outputs/ 真实运行日志 · 代码单一信息源在 teach-agent/"

BRANCHES = [
    ("① 组装：同图正交", [
        "create_deep_agent 的独立配置项",
        "skills / memory / tools",
        "interrupt_on / middleware",
        "没有手写编排，四能力互不打架",
        "两处 tools 不通用",
    ]),
    ("② 记忆升级：record_mistake", [
        "@tool 结构化追加错题",
        "写进 learner.md「## 错题」段",
        "LEARNER_MD_PATH 可指向临时副本",
        "返回字符串：invoke 直接给 str",
        "新 thread 起号即注入 system prompt",
    ]),
    ("③ Rubric 激活与时序", [
        "invoke 带 rubric 字段才评分",
        "不带则整体 no-op",
        "after_agent：自然停止后才启动",
        "端到端闭环必须 hitl=False",
        "middleware.tools 只给评分模型",
    ]),
    ("④ 真实闭环结果", [
        "评审 2 轮，agnes-3.0-flash",
        "iter0 needs_revision（取证 ok）",
        "iter1 max_iterations_reached",
        "fail-closed：未放水",
        "satisfied ≠ 正确",
    ]),
    ("⑤ 验证策略", [
        "零 token 探针 5 项能力",
        "有 key 才跑真实评分闭环",
        "证据工具返回 ok + failures",
        "测试覆盖写路径防污染种子",
        "HITL 中断是重放不是弹窗",
    ]),
    ("⑥ 下一步修正", [
        "弱/强 Rubric 对照复现漏查",
        "错题拆 learner_mistakes.md",
        "HITL edit 接真实前端",
        "证据工具沙箱化（真跑单测）",
        "on_evaluation 只记日志不当钩子",
    ]),
]

WRAP = 30
ASCII_TOKEN = re.compile(r"[A-Za-z0-9_\-./:<>=()\[\]{}\"'`]+")


def wrap_tokens(text, limit=WRAP):
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

    fig, ax = plt.subplots(figsize=(16, 13.5), dpi=150)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.030, 0.968, TITLE, fontproperties=FB, fontsize=18, color=INK, va="top")
    ax.text(0.030, 0.933, SUBTITLE, fontproperties=F, fontsize=9, color=FAINT, va="top")
    ax.plot([0.030, 0.970], [0.915, 0.915], color=RULE, lw=0.9)

    top, bottom = 0.878, 0.070
    gap_units = 0.9 * len(BRANCHES)
    unit = (top - bottom) / (total_lines + gap_units)

    root_x, root_w, root_cx = 0.030, 0.118, 0.030 + 0.118 / 2
    root_y = 0.50
    root_h = 0.148
    ax.add_patch(FancyBboxPatch(
        (root_x, root_y - root_h / 2), root_w, root_h,
        boxstyle="round,pad=0.006,rounding_size=0.014",
        facecolor=ACCENT, edgecolor="none",
    ))
    ax.text(root_cx, root_y + 0.030, "教学Agent", fontproperties=FB, fontsize=14, color="white", ha="center", va="center")
    ax.text(root_cx, root_y, "四能力同图", fontproperties=FB, fontsize=14, color="white", ha="center", va="center")
    ax.text(root_cx, root_y - 0.034, "capstone", fontproperties=F, fontsize=8.0, color="#F0D6D0", ha="center", va="center")

    branch_x, branch_w = 0.205, 0.145
    leaf_x = 0.395
    cursor = top

    for i, ((name, _), lines_per_leaf) in enumerate(zip(BRANCHES, wrapped)):
        block_h = sum(len(lines) for lines in lines_per_leaf) * unit
        branch_cy = cursor - block_h / 2

        ax.add_patch(FancyBboxPatch(
            (branch_x, branch_cy - 0.030), branch_w, 0.060,
            boxstyle="round,pad=0.005,rounding_size=0.010",
            facecolor=TINTS[i % len(TINTS)], edgecolor=RULE, lw=0.9,
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
                    fontproperties=F, fontsize=10.0, color=SOFT,
                    ha="left", va="center", linespacing=1.55)
            y -= len(lines) * unit

        cursor -= block_h + 0.9 * unit

    ax.text(0.030, 0.020, FOOTER, fontproperties=F, fontsize=8.4, color=FAINT, va="bottom")

    fig.savefig(OUT, facecolor=PAPER, bbox_inches="tight", pad_inches=0.24)
    print("已生成:", OUT)


if __name__ == "__main__":
    main()
