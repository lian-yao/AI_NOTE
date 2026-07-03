# 10分钟讲清楚 Prompt, Agent, MCP 是什么

- 来源: https://www.bilibili.com/video/BV1aeLqzUE6L/?spm_id_from=333.337.search-card.all.click&vd_source=468f1a9e75e01aac8f044869f34d0717
- UP主: 隔壁的程序员老王
- 时长: 00:11:38
- 转录方式: whisper:large-v3-turbo
- 视频ID: BV1aeLqzUE6L
- 上传日期: 2025-05-01

## 一句话总结

视频用「聊天框逐步演化成能调用工具的自动化系统」这条线，把 User Prompt、System Prompt、AI Agent、Agent Tool、Function Calling 和 MCP 串起来: Prompt 负责表达用户意图和上下文，Agent 负责在用户、模型和工具之间调度，Function Calling 规范模型调用工具的格式，MCP 则规范 Agent 与工具服务之间的通信。

## 关键要点

- User Prompt 是用户直接发给模型的问题、指令或对话内容。
- System Prompt 用来描述 AI 的角色、性格、背景、语气和行为约束，让对话更稳定、更自然。
- 早期聊天机器人主要是「你问一句，模型答一句」，即使人设再完整，也仍然只是给答案，不能真正动手完成任务。
- AI Agent 是负责在用户、AI 模型和外部工具之间传递信息并组织流程的程序。
- Agent Tool 是提供给 Agent 或模型调用的函数或服务，例如列目录、读文件、浏览网页等。
- 早期 Agent 会把工具说明写进 System Prompt，让模型按约定格式返回工具调用请求，但模型可能输出格式错误，因此 Agent 常需要重试。
- Function Calling 把工具描述和工具调用格式标准化，通常用结构化 JSON 定义工具名、说明和参数，降低模型乱输出的概率。
- System Prompt 工具调用和 Function Calling 目前是并存关系: 前者兼容性强，后者更规范，但不同厂商 API 不完全统一，部分开源模型支持也有限。
- MCP 是 Agent 和 Tool 服务之间的通信协议，不是模型协议，也不直接规定 AI 模型如何推理。
- MCP Server 负责提供 tool、resource、prompt 等能力，MCP Client 通常是调用这些能力的 Agent。
- MCP Server 可以和 Agent 跑在同一台机器上，通过标准输入输出通信，也可以部署成网络服务，通过 HTTP 通信。
- Prompt、Agent、Function Calling、MCP 不是互相替代的概念，而是组成 AI 自动化协作体系的不同层。

## 时间线大纲

- [00:00 - 00:34] **概念引入**: Agent、MCP、Function Calling 等 AI 名词不断出现，视频目标是用简单语言把这些概念串起来。
- [00:34 - 01:25] **User Prompt**: 用户在聊天框里发给模型的内容就是 User Prompt，也就是问题、指令或想说的话。
- [01:25 - 02:47] **System Prompt**: 为了让 AI 不只是给通用答案，人们把角色、人设、语气和背景信息放到 System Prompt 中，并由系统在每次对话时一起发送给模型。
- [02:47 - 04:26] **AI Agent 与 Agent Tool**: 以 Auto GPT 为例，Agent 可以注册文件管理等工具，把工具说明交给模型，模型决定调用哪个工具，Agent 执行后再把结果交回模型，循环直到任务完成。
- [04:26 - 05:00] **自然语言工具说明的问题**: 如果只靠 System Prompt 约定工具调用格式，模型仍可能返回格式错误的内容，Agent 只能解析失败后重试。
- [05:00 - 06:41] **Function Calling**: 大模型厂商把工具定义和调用格式标准化，让工具名、说明、参数等进入结构化字段，并让模型按固定格式返回工具调用，从而提升可靠性并减少用户端重试成本。
- [06:41 - 07:03] **两种方式并存**: Function Calling 更规范，但各厂商实现不同，部分开源模型不支持，所以 Prompt 约定和 Function Calling 仍会同时存在。
- [07:03 - 08:41] **MCP 的出现**: 当多个 Agent 都需要浏览网页、文件读写等通用工具时，把工具统一托管成服务更合理。MCP 就是规范 Agent 与这些工具服务如何交互的协议。
- [08:41 - 08:57] **MCP 与模型无关**: MCP 虽然为 AI 场景设计，但它本身不关心 Agent 使用哪个模型，只管理工具、资源和提示词的提供方式。
- [08:57 - 10:29] **完整流程示例**: 用户向 Agent 提问，Agent 从 MCP Server 获取工具信息，再把工具信息转成 System Prompt 或 Function Calling 格式发给模型；模型请求调用网页浏览工具，Agent 通过 MCP 调用工具，把结果返回给模型，最后模型生成答案并由 Agent 展示给用户。
- [10:29 - 11:30] **结尾观点**: AI 进步会带来焦虑，但理解这些基础概念，能让普通人更清醒地参与技术变化，而不是被动被时代推着走。

## 概念关系

| 概念 | 解决的问题 | 位置 |
| --- | --- | --- |
| User Prompt | 用户要模型理解和完成什么 | 用户到模型 |
| System Prompt | 模型应该以什么身份、语气和规则回应 | 系统到模型 |
| AI Agent | 谁来调度用户、模型和工具之间的流程 | 应用层协调器 |
| Agent Tool | 模型可以借助哪些外部能力做事 | 函数或服务 |
| Function Calling | 模型如何可靠地表达「我要调用哪个工具、传什么参数」 | 模型 API 与 Agent 之间 |
| MCP | Agent 如何发现和调用外部工具、资源、提示词服务 | Agent 与工具服务之间 |

## 重要观点

- AI 从「会聊天」变成「能做事」，核心变化不是模型突然拥有了电脑权限，而是 Agent 把模型、工具和用户请求组织成了可循环执行的流程。
- Agent 不是模型本身，而是围绕模型构建的调度程序。它负责给模型上下文、解析模型意图、调用工具、回传结果。
- Function Calling 的价值在于把「自然语言约定」变成「结构化协议」，让工具描述和工具调用更适合模型训练和服务端校验。
- MCP 的价值在于把通用工具服务化，减少每个 Agent 重复实现同一套工具代码的成本。
- MCP 不等于 Function Calling。Function Calling 解决模型如何表达工具调用，MCP 解决 Agent 如何和工具服务通信。
- 这些概念不是替代关系，而是分工关系: Prompt 提供上下文，Agent 负责流程，Function Calling 规范模型侧工具调用，MCP 规范工具服务侧通信。

## 注意事项

- 视频口播中的「Function Coding」按上下文应理解为 `Function Calling`。
- `MCP Server` 可以提供的不只是普通工具，还可以提供 `resource` 和 `prompt`。
- MCP 常被类比成「AI 时代的 USB 协议」，但它不能接 U 盘；这个类比强调的是统一连接和发现能力，而不是硬件能力。
- 如果要开发跨模型通用的 Agent，需要同时考虑模型是否支持 Function Calling、厂商 API 差异、以及 MCP Server 的工具接口设计。
