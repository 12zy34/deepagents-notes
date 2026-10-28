# DeepAgents 学习笔记

[Datawhale《DeepAgents 实战》](https://datawhalechina.github.io/deepagents-in-action/) 课程学习记录，按任务（task）分目录组织。

## 任务目录

| 目录 | 内容 |
|---|---|
| [task1/](./task1/) | Task1（ch01–02）：我的第一个工具 Agent——Hello World / 多工具计算器 / 联网研究助手，附思维导图 |
| [task2/](./task2/) | Task2（ch03）：虚拟文件系统——「写入 — 读回 — 修改」全链路，FilesystemBackend 落盘验证 |
| [task3/](./task3/) | Task3（ch04）：任务规划——`TodoListMiddleware` 规划/执行/状态流转，`todos` 持久化对照实验 |
| [task4/](./task4/) | Task4（ch05）：子 Agent 与上下文隔离——委派边界双向验证（messages 隔离 / files 穿透）、spec 继承对照 |
| [task5/](./task5/) | Task5（ch07）：Skills——三级加载的真实分工（L1 元数据 / 正文由模型自读）、会话快照与 last wins、父子各自装配 |
| [task6/](./task6/) | Task6（ch08–09）：长期记忆与人机审批——memory 全文注入 vs skills 索引、短期/长期存储、中断存档与从头重放、四种决策对照 |

<!-- 后续章节在此追加，例如：
| [task2/](./task2/) | ch03 ... |
-->

## 引用与致谢

本仓库所有练习脚本与笔记均为学习用途，改编自以下课程资料：

| 资料 | 链接 |
|---|---|
| 课程教程（Datawhale） | <https://datawhalechina.github.io/deepagents-in-action/> |
| Task1 对应章节 | <https://datawhalechina.github.io/deepagents-in-action/chapters/ch02-quickstart/> |
| Task5 对应章节 | <https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/> |
| Task6 对应章节 | <https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/> · <https://datawhalechina.github.io/deepagents-in-action/chapters/ch09-human-in-the-loop/> |
| B站视频教程《Deep Agents 实战》 | <https://space.bilibili.com/28357052/lists/7757577?type=season> |
| 课程代码仓库（Datawhale） | <https://github.com/datawhalechina/deepagents-in-action> |
| DeepAgents 框架（LangChain 上游） | <https://github.com/langchain-ai/deepagents> |
| LangChain 官方文档 | <https://docs.langchain.com/> |

笔记中的示例代码在课程示例基础上做了适配（模型接入、`.env` 加载方式等），详见各 task 的说明。
