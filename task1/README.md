# DeepAgents 学习笔记

[Datawhale《DeepAgents 实战》](https://datawhalechina.github.io/deepagents-in-action/chapters/ch02-quickstart/) 课程学习记录。

## 目录

- [deepagent学习思维导图.png](./deepagent学习思维导图.png) — DeepAgents 核心概念思维导图
- [code/](./code/) — 课程练习脚本

## 练习脚本

| 文件 | 对应章节 | 验证点 |
|---|---|---|
| [code/helloworld.py](./code/helloworld.py) | ch02 Quickstart | 最小 DeepAgent + 单工具调用链路 |
| [code/计算器Agent.py](./code/计算器Agent.py) | ch02 | 多工具协作（换汇 + 计算串联规划） |
| [code/研究助手.py](./code/研究助手.py) | ch02 | 接入 Tavily 的联网研究 Agent |

## 环境要点（踩坑记录）

1. **不需要 conda**：依赖由 `uv` 管理在项目 `.venv`，运行统一用
   `uv run --frozen python code/xxx.py`（直接 `python3` 用的是系统解释器，会 ModuleNotFoundError）。
2. **`uv run` 不会自动加载 `.env`**：每个练习脚本开头必须
   `from dotenv import load_dotenv; load_dotenv()`，否则 `os.environ[...]` 直接 KeyError。
3. **模型兜底值要改**：课程默认 `Qwen/Qwen2.5-7B-Instruct`，在自用网关下会 503
   `model_not_found`（No available channel），兜底值应改为网关实际托管的模型。
4. **观察工具调用**：项目已配置 LangSmith（`LANGSMITH_TRACING=true` + `deepagents-course` 项目），
   trace 里能看到 middleware 洋葱模型：`before_*` 正序、`after_*` 倒序、`wrap_model_call` 嵌套。
