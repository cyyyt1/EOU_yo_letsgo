# 智能旅行搭子：开源项目与技术调研报告

- 调研日期：2026-11-13
- 使用方式：立项候选筛选与实验设计，不是生产验收、法律意见或完整许可证审计
- 对应设计：`DESIGN.MD`
- 已确认项目约束：Flutter、Android APK + iOS源码、用户自备API、无必需后端、单城多类景点、实时语音、本地知识与确认记忆、位置为主的拍照触发

## 1. 摘要

**没有核实到一个可以直接改名发布、完整覆盖本项目所有需求的开源仓库。**更合理的路线是：旅行业务独立实现，参考开源旅行项目的数据与操作流程，借鉴语音项目的协议和打断处理，以原生桥接完成手机能力。

值得参考的方向：

1. **TREK、AI-TripPlanner：**借鉴行程、地图、偏好与协作设计，不能替代可信景点语音导游。
2. **小智、Pipecat、LiveKit Agents：**借鉴语音状态机、供应商适配、工具和实时音频；多数要求服务端，不直接符合纯客户端BYOK。
3. **Open-LLM-VTuber：**借鉴人格和表现，前端存在独立许可，不能把全项目笼统标为MIT。
4. **Mem0：**借鉴记忆筛选与更新；V1可用本地SQLite，不需要额外LLM/向量服务或云记忆平台。
5. **云端实时模型：**满足手机小包体和无自建GPU目标，但服务能力、账号地域、网络和费用需要实测；项目开源不意味着所调用的API也开源。

本轮不是按星数排名，而是按“符合项目约束程度、能复用什么、引入何种部署和许可责任”筛选。

## 2. 证据等级与研究限制

### 2.1 已完成与未完成

已完成：公开项目发现、官方能力文档、部署说明、部分发布包/模型卡许可声明、实时模型和地图官方页、iOS分发说明，以及合规规则的阶段区分。

环境执行`gh --version`返回退出码127：`gh: command not found`。本轮未安装GitHub CLI，未通过CLI读取仓库默认分支README或LICENSE，也未下载/运行任何第三方项目代码。

因此所有候选的以下项目统一为**未核验**：

- 当前默认分支名称及其最近提交日期。
- 仓库是否归档、当前维护活跃度、issue响应与未修复漏洞。
- 固定提交下的LICENSE、NOTICE、依赖和子模块完整授权。
- 本项目所需功能是否在真机、户外或中国大陆网络稳定可用。

网页和搜索摘要能证明候选存在或提供线索，不能代替固定版本源码审计。下文许可证均标注证据出处，不能将搜索摘要写成“已审计通过”。

### 2.2 等级定义

| 等级 | 意义 |
| --- | --- |
| A：官方文档/模型卡/发布说明 | 能支持该页面明确陈述；页面可变化，不代表固定源码提交 |
| B：公开搜索摘要或部署索引 | 候选线索，需要读取源码和原始许可后确认 |
| C：本报告分析/工程估算 | 依据架构判断或公式，不是实际部署和性能测量 |
| 未知 | 本轮无法核实，发布前补证据 |

## 3. 直接旅行项目

### 3.1 TREK

- 仓库：[liketrek/TREK](https://github.com/liketrek/TREK)
- 公开部署线索：[TREK部署页](https://railway.com/deploy/trek-travel-planner--deploy-trek-travel-planner)
- 技术栈线索：TypeScript、NestJS、React、SQLite、Leaflet；Docker和持久化存储。
- 代码许可证线索：AGPL-3.0（B），未读当前仓库LICENSE。
- 最近默认分支提交、归档状态、实际CPU/RAM：未核验。

**可参考**

地图与行程组织、预算、多人协作、游记，以及离线PWA的业务结构。相较纯聊天Demo，其旅行数据与操作流程更值得研究。

**优点**

- 业务组织较完整，可帮助避免把旅行应用只做成一个对话框。
- 自托管和本地数据库路线可参考内容版本、持久化和行程组织。
- 可为未来行程及分享提供产品设计参考。

**局限**

- 本轮没有证据证明存在景点证据门控、实时语音、可管理人格或跨景点记忆。
- PWA不等于成熟的Android/iOS音频、后台限制和定位实现。
- 地图及外部Places服务涉及额外数据条款，不能直接替换成国内服务而忽略权利。
- 若许可确为AGPL，修改后提供网络服务可能有相应源码提供义务，须按实际组合方式复核。

**建议：**研究业务流程和数据关系；V1不直接fork作为Flutter客户端底座。

### 3.2 AI-TripPlanner

- 仓库：[ladHarsh/AI-TripPlanner](https://github.com/ladHarsh/AI-TripPlanner)
- 技术栈线索：MERN，即MongoDB、Express、React、Node.js；Gemini、OpenStreetMap、OSRM。
- 代码许可证线索：MIT（B），未读当前仓库LICENSE。
- 默认分支、最近提交、维护状态、最低资源：未核验。

**可参考**

偏好采集 → 行程生成 → 地图/路线展示的轻量流程，适合V2行程能力的参考。

**优点**

- 生成和地图连接清晰，容易形成短路径演示。
- 常见Web技术生态，团队有TypeScript/JavaScript经验可理解其结构。

**局限**

- 本轮未证实地点与路线经过可信校验，模型生成的POI可能不存在或不可达。
- 未证实实时语音、人格持续性、原生客户端与生产鉴权。
- 依赖Gemini的可用性与服务条款，不符合默认国内服务路线就不能照搬。
- 代码MIT不覆盖OSM数据、公开瓦片、OSRM服务或模型API。OSM数据许可与瓦片服务政策是不同层次。

**建议：**作为行程生成原型比较项，不作为V1语音导游核心。

## 4. 语音、人格与记忆项目

### 4.1 小智：xiaozhi-esp32 / xiaozhi-esp32-server

- 固件：[78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32)
- 服务端：[xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server)
- 部署线索：[全模块部署说明](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/main/docs/Deployment_all.md)
- 技术栈线索：固件C++，服务端生态包括Python、Java、Vue；完整部署可能含MySQL、Redis。
- 许可线索：两个仓库MIT（B），未读当前原始许可证。
- 当前维护和最低资源：未知；API推理和本地推理的资源需求不同。

**优点：**中文语音交互、供应商适配、设备协议与工具链适合快速理解实时对话；可研究声音输入、响应、取消及断线逻辑。

**缺点：**固件面向ESP32，不是Flutter手机App。服务端引入设备协议、鉴权与部署门槛，整库接入会违背“装APK、填API即可用”。开源设备Demo不能直接承担多租户密钥和位置数据管理。

**建议：**协议与交互参考；如另做语音实验可临时研究服务端，不作为V1必需服务。

### 4.2 Pipecat

- 仓库：[pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)
- [官方概览](https://docs.pipecat.ai/overview/introduction)
- [生产运行说明](https://docs.pipecat.ai/pipecat/deployment/running-bots-in-production)
- 主体：Python实时音频流水线，官方生态含移动端SDK。
- 官方文档声明BSD-2-Clause（A）；当前源码与依赖仍未审计。
- API模式不必自行跑GPU；本地模型、媒体连接及多会话增加独立资源。

**优点**

- 音频流水线、打断、供应商适配和可观察处理便于语音实验。
- 适合显式串联ASR、LLM、TTS，或管理复杂实时会话。
- 开放框架与多个服务适配，可减少未来自建后端时的重复工作。

**缺点**

- 通常包含服务端机器人运行假设，不是纯Flutter客户端库。
- 不自带旅行内容、位置消歧和长期人格记忆。
- 生产仍需鉴权、调度、TLS、限流、扩容和媒体网络；官方开发runner不能裸露当生产服务。

**建议：**V1做方案对照和音频逻辑参考；若未来明确采用后端，再评估正式依赖。

### 4.3 LiveKit Agents

- 仓库：[livekit/agents](https://github.com/livekit/agents)
- [官方Agents概览](https://docs.livekit.io/agents/)
- [回合检测与模型许可](https://docs.livekit.io/agents/logic/turns/turn-detector/)
- 主体：Python/Node Agent、WebRTC与移动客户端生态。
- 官方框架声明Apache-2.0（A）；回合检测模型和部分插件有独立许可/计费条件。
- 自托管需要LiveKit媒体服务、Agent worker，可能还需TURN；本项目资源基线未测。

**优点：**实时媒体、音频路由和会话基础设施成熟度值得研究；适合重视实时通话质量并愿意部署服务的一类产品。

**缺点：**比直接供应商WebSocket更多基础设施。需要核实中国大陆网络、TURN带宽、房间Token与权限；不能把Agent框架Apache许可延伸给检测模型、降噪插件或云服务。

**建议：**V2以后若引入后台媒体服务，与Pipecat做有依据的对比；不为未来需求提前加入V1。

### 4.4 Open-LLM-VTuber

- 仓库：[Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)
- [v1.2.0许可发布说明](https://docs.llmvtuber.com/en/blog/v1.2.0-release/)
- [前端许可候选路径](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web/blob/main/LICENSE)
- 技术栈线索：Python后端、Web/桌面前端、语音与Live2D角色。
- 发布说明证据（A）：v1.2.0后端MIT，前端Open-LLM-VTuber License 1.0；说明还提到后续统一许可方向。当前默认分支许可未核验。

**优点：**人设、声音、角色表现和插话很贴近“搭子”气质，适合研究如何让交互不只是单调朗读。

**缺点**

- 发布说明对收费SaaS、转售、商业集成等存在独立授权要求，不能把项目整体写成宽松MIT。
- Live2D样例、SDK、角色、声音与模型权重各有权利边界。
- 桌面/网页表现不是移动旅游中的地图、相机、耳机和定位能力。
- 若以人格效果为中心，容易挤占V1景点可信度和实用流程投入。

**建议：**以交互和人设研究为主，复用任何前端代码前核实固定版本许可证；V1像素角色可独立设计。

### 4.5 Mem0

- 仓库：[mem0ai/mem0](https://github.com/mem0ai/mem0)
- [官方自托管概览](https://docs.mem0.ai/open-source/overview)
- 技术：Python/Node SDK，可作为库或自托管服务；涉及LLM、embedding和存储。
- 许可线索：Apache-2.0（B），未读当前仓库原始许可证；云平台服务条款独立。

**优点：**记忆筛选、关联、更新和召回是本项目长期价值点，可研究如何避免把全部聊天反复送入上下文。

**缺点**

- 不是景点知识库，也不是自动正确的用户画像。
- 默认配置可能调用外部LLM/embedding；“自托管”不等于数据不外发。
- 需要防误记、记忆注入、串用户、过度收集及删除后索引仍可召回。
- V1少量确认记忆用SQLite即可，引入库/服务反而增加费用与部署复杂度。

**建议：**研究记忆操作原则；先不依赖服务，V2出现真实召回需求后再评估。

## 5. 候选比较与复用决策

| 候选 | 主要参考价值 | 不直接符合纯客户端的原因 | V1建议 |
| --- | --- | --- | --- |
| TREK | 行程、地图、预算、协作 | Web/自托管架构；许可待核 | 参考业务，不整库fork |
| AI-TripPlanner | 偏好生成行程并显示路线 | Web后端、模型与地图服务差异 | V2行程参考 |
| 小智 | 中文语音协议、工具适配 | ESP32/服务端，不是手机客户端 | 语音状态与协议参考 |
| Pipecat | 音频流水线、打断、多供应商 | Python运行与生产服务责任 | 对照实验，不必需部署 |
| LiveKit Agents | 实时媒体与会话 | 媒体服务器、worker、网络成本 | 后端路线候选 |
| Open-LLM-VTuber | 人设与角色表现 | 桌面/Web与前端独立许可 | 交互参考，先不复制前端 |
| Mem0 | 长期记忆操作 | 额外模型/存储与隐私链路 | 用本地确认记忆替代 |

复用前须回答：复用的是设计思路、代码、网络服务还是数据？四者的许可与部署责任不同。参考思路不等于可以复制实现、角色和语料。

## 6. 模型与实时API事实

### 6.1 Earshot核实

至少有两个明确同名对象：

1. [pykeio/earshot发布文档](https://docs.rs/crate/earshot/latest)：Rust流式语音活动检测器（VAD），发布文档提到约40KB模型、`no_std`；包声明MIT OR Apache-2.0。它判断是否有人说话，不是中文ASR、TTS或导游模型；独立权重授权未完全核验。
2. [EARSHOT学术论文](https://pubmed.ncbi.nlm.nih.gov/32274861/)：2020年的增量语音识别认知研究，不是可直接用于旅行App的现代实时语音服务。

会议到底指哪一个仍未知，也可能存在听写误差。不能没有证据就替换成Whisper，或把Earshot作为已选完整语音模型。

### 6.2 首测候选：百炼实时Omni

- [中国站模型与价格页](https://help.aliyun.com/zh/model-studio/qwen3-8-omni-flash-realtime)
- [国际站模型页](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-omni-flash-realtime)
- [客户端事件](https://www.alibabacloud.com/help/en/model-studio/client-events)
- [实时接口总览](https://www.alibabacloud.com/help/en/model-studio/realtime-api-overview)
- [临时API Key](https://www.alibabacloud.com/help/en/model-studio/application-obtain-temporary-authentication-token)

**已从官方页核实**

- 模型ID：`qwen3.8-omni-flash-realtime`。
- 地域：华北2（北京）、新加坡；账号凭据与接入地域需匹配。
- 总览列文本、流式音频、视频/连续图像帧输入和文本/音频输出。
- 支持自定义工具调用；页面还列远程MCP，但V1不开放任意远程工具。
- 客户端可接收工具请求，执行本地知识查询，回传`function_call_output`，随后请求继续回答。
- WebSocket使用Bearer API Key鉴权。

**必须继续验证**

- Function Calling不证明模型自带联网搜索；已读模型页没有确认内置搜索能力。
- 客户端事件页出现`input_image_buffer.append`、Base64 JPG/JPEG及尺寸/编码限制，并有先音频的协议说明；不能据总览就保证“任意单图随时输入”已打通。
- 总览支持文本，不等于本轮已核实普通用户文本输入与图片、音频输出在同一会话的全部事件组合。
- 临时Key文档有时效机制，但该实时WebSocket对其兼容范围本轮未完整核实。客户端保存长期Key的风险不因临时Key消失。
- 服务端VAD和打断事件不能替客户端清空播放队列；WebSocket路线仍需客户端AEC和音频路由。
- 端到端模型的语音转述也可能超出工具证据，必须验证无结果、矛盾来源及未知景点。

**选型建议**

先把该供应商作为技术实验候选，而不是最终承诺。默认服务必须通过语音/文字/拍照/本地检索/联网来源/停止与权限全链路。其它供应商入口保留，但能力不够时明确禁用对应功能。

### 6.3 开源权重与自托管备选

| 对象 | 权重/包声明 | 能力与限制 |
| --- | --- | --- |
| Qwen3-ASR-0.6B | 官方模型卡Apache-2.0；qwen-asr包同声明 | 中文/方言识别；官方流式路径涉及vLLM，不是已验证手机SDK |
| Qwen3-TTS-12Hz-0.6B-Base | 模型及独立Tokenizer卡Apache-2.0；qwen-tts包同声明 | 中文声音合成；宣称流式不等于已核实现成增量SDK闭环 |
| Qwen3-4B | 模型LICENSE Apache-2.0 | 文本推理候选，不直接具备完整实时音频与联网工具 |
| Qwen3-Omni-30B-A3B-Instruct | 官方模型卡Apache-2.0 | 音频理解/语音输出；A3B是激活参数，不是只加载3B |

这几项模型卡/包声明属于A等级证据，但训练数据、角色音色与完整推理依赖未全部审计。Apache-2.0不自动授权真人声线、商标或未授权语料。

云API `qwen3.8-omni-flash-realtime` 与开源 `Qwen3-Omni-30B-A3B-Instruct` 不是同一交付物，不能把开源模型许可套用在云服务上。

**体积估算**

仅权重约为“参数量×位宽÷8”：0.6B FP16约1.2GB，4B FP16约8GB；INT4理论分别0.3GB、2GB，不代表已有可用、正确且许可明确的移动量化方案。还需计算编码器、声码器、运行时、KV缓存和峰值内存。

Omni官方模型卡针对BF16和15秒视频条件列约68.74GB GPU显存，不能把它外推为纯语音最小要求，更不能按“只激活3B”估算手机包体。

因此V1不捆绑模型权重，采用云API符合150MB目标与三人团队资源约束；不宣称手机绝对不能跑任何小模型。

### 6.4 串联与端到端比较

| 维度 | ASR + 文本LLM + TTS | 端到端实时语音 |
| --- | --- | --- |
| 知识与文本审计 | 模块分明，较易检查生成文字 | 需要工具证据和输出转录联动 |
| 自然语调 | 依赖TTS表现与分句 | 可保留更多音频交互特征，实际效果须测 |
| 调试 | 逐段测，但步骤与服务较多 | 单模型会话，但事件与音频状态复杂 |
| 配置 | 通常多种API角色 | 不保证一个模型包办视觉与联网 |
| 延迟 | 多段累加，缓存和流式能优化 | 端到端不自动等于低延迟或成熟全双工 |
| 手机实现 | 原生音频仍需要 | AEC、播放取消、耳机切换仍需要 |

用户选择端到端实时语音，所以串联仅作为备选研究，不在文档中擅自改成V1已选方案。

## 7. 地图、定位与国内移动集成

### 7.1 高德许可与费用

- [许可FAQ](https://lbs.amap.com/faq/advisory/authorization/43168)
- [升级与技术许可](https://lbs.amap.com/upgrade)
- [调用计价](https://lbs.amap.com/pages/base_service_price)
- [技术许可协议](https://lbs.amap.com/pages/authorization)

官方页面区分自然人研究学习用途与其他用途。**有个人账号、API Key或没有向用户收费，都不自动等于可免费商用。**V1内部研究实际用途与后续公开分发要分别确认。

升级页挂牌技术许可基础5万元/年、高级10万元/年；授权费与调用费是两层，实际是否适用以及导航等独立产品是否包含，以场景和合同为准。

本轮查到符合条件的个人月度分类额度线索：基础LBS15万、定位150万、搜索5000；超额分类价线索为每万次30元、3元、30元。额度、分类和账户条件可能变化，后续要从控制台与合同复核，不能拿它承诺所有用户免费。

### 7.2 Flutter与原生桥接

- [高德Flutter官方文档](https://lbs.amap.com/api/flutter/summary)
- [amap_flutter_map许可页](https://pub.dev/packages/amap_flutter_map/license)
- [React Native社区封装例](https://uiwjs.github.io/react-native-amap-geolocation/)

高德有Flutter地图/定位/搜索文档，但文档与包发布状态较旧，发布者标识及当前兼容保证须核实。Flutter包BSD声明不覆盖原生SDK与地图数据。

本轮没有核实到高德官方React Native SDK；社区封装不等于官方支持。

推荐先做两端原生SDK + Flutter封装的薄验证，重点测隐私初始化、包名/签名、定位和音频共存；失败时才写有限原生桥接，不先自己重做整个地图层。

### 7.3 Key回填并非任意Key通用

V1团队自备配置。后续注册指引必须区分模型与地图：

- 模型Key通常对应账号、地域、权限和消费上限。
- 原生地图Key可能绑定包名、Android签名摘要、iOS Bundle ID等；发布包和自构建包需要正确匹配。
- 可保留运行时输入接口，但只有SDK支持且绑定合法正确时才启用；部分变更可能需要重新初始化或重新构建。
- 不宣传“填任何Key就能使用”；不把客户端地图标识当作无法被提取的秘密。

### 7.4 数据、坐标和像素风

- [坐标FAQ](https://lbs.amap.com/faq/advisory/others/39838)
- [服务协议](https://lbs.amap.com/home/terms/)
- [自定义地图协议](https://lbs.amap.com/home/customize-map-terms/)
- [SDK合规参考](https://lbs.amap.com/compliance-center/check-and-reference/sdkhgsy)

高德使用GCJ-02，GPS常为WGS-84。每条数据带坐标系，避免错误转换与重复偏移。

官方样式自定义不等于许可抓取、修改、托管和再分发瓦片。高德POI、图片、评分也不能默认长期入库、向量化或用于公开景点包。

V1把像素风放在角色、标记与卡片，保留底图归属和真实道路/设施可读性，是比“把地图变成游戏瓦片”更稳妥的路线。

路径规划API、完整导航SDK、外部跳转是不同能力；本轮未取得导航SDK统一公开报价。V1外部导航并不代表可复制地图平台全部功能。

开放地图备选需分别审查MapLibre代码、底图/瓦片服务、OSM数据及国内数据/可用性；公共OSM瓦片不是无限免费的生产后端。

## 8. 隐私、生成式AI与分发边界

### 8.1 个人信息

- [个人信息保护法](https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm)
- [深度合成规定](https://www.cac.gov.cn/2022-12/11/c_1672221949354811.htm)

持续定位形成的行踪轨迹属于敏感个人信息，需按特定目的、充分必要性、单独同意、保护与影响评估等实际义务处理。单次坐标、图片和对话组合也可能暴露行程。

录音关联个人时可能是个人信息，但不是所有录音都属于身份识别声纹；真人仿声、识别身份或涉及敏感内容时需另外评估。

BYOK客户端仍会把信息传给供应商。自托管、端侧、本地SQLite和无团队后端均不自动豁免告知、最小必要、删除或跨境要求。

SDK初始化必须基于真实同意，不能硬编码隐私已同意。委托处理与向独立接收方提供信息不同，不能仅列一个SDK名单就认为全部合规。

### 8.2 公众生成式与拟人化服务

- [生成式AI服务暂行办法](https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm)
- [2026备案/登记公告](https://www.cac.gov.cn/2026-09/14/c_1791136833136332.htm)
- [生成合成内容标识办法](https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm)
- [拟人化互动服务管理暂行办法](https://www.cac.gov.cn/2026-04/10/c_1777558395078289.htm)
- [APP备案通知政府转载](https://www.hunan.gov.cn/zqt/zcsd/202308/t20230809_29456035.html)

内部未向公众开放的研究与面向中国境内公众提供服务适用范围不同；开源不是自动豁免理由。

公众服务需按具体功能和主体评估上游备案、应用登记、安全评估、APP备案等要求，不能说使用已备案模型就自动完成应用合规。

标识办法自2025-09-01实施，涉及文本/音频显式标识及文件隐式标识；未来导出旅行卡片、音频和社群内容需单独实现。不能通过“去掉标识”提升真人感。

拟人化互动办法公布于2026-04-10，自2026-07-15实施。范围取决于是否模拟人格并持续情感互动；没有持续情感互动的知识问答/工作助手被排除。像素角色本身不是唯一判据；旅行后长期陪聊可能使功能落入另一范围。

本报告只列上线前评估事项，不替实际运营主体出具法律判断。

### 8.3 iOS分发

- [Apple开发者账号](https://developer.apple.com/help/account/basics/about-your-developer-account/)
- [Apple测试和正式分发](https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases)
- [Ad Hoc配置](https://developer.apple.com/help/account/provisioning-profiles/create-an-ad-hoc-provisioning-profile/)
- [TestFlight](https://testflight.apple.com/)

DMG是macOS交付，不是iPhone交付。用户已修正需求：V1提供APK与iOS源码构建方式。

Apple免费Personal Team可用于Xcode个人真机开发，相关配置存在7天有效期等限制，不是公众IPA分发渠道。TestFlight需相应开发者计划，构建测试最长90天；Ad Hoc需要注册设备及对应签名配置，App Store另有提交审核。

GitHub Release挂一个IPA，不意味着所有iPhone可安装。iOS源码交付也不等于iOS所有能力已通过真机验证。

## 9. 费用与资源估算

### 9.1 已核实的实时候选价目快照

来源为模型专页，不把未包含该型号的总价格表摘要当作证据。

| 地域 | 输入音频 | 输出音频 | 输入文本/图片/视频 | 输出文本 |
| --- | --- | --- | --- | --- |
| 华北2（北京） | 6元/百万Token | 12元/百万Token | 1.5元/百万Token | 4.5元/百万Token |
| 新加坡 | 6.781元/百万Token | 13.636元/百万Token | 1.677元/百万Token | 5.104元/百万Token |

语音输出及对应文本分别计费。日期、地域、模型快照、免费额和账户条款变化均可能改变最终账单。

没有核实该型号“音频秒→计费Token”的正式换算，不能直接据这些单价计算旅行一小时费用。优先实测单次会话的用量事件和实际账单。

### 9.2 串联方案参考价

[百炼官方价格](https://help.aliyun.com/zh/model-studio/model-pricing)、[Paraformer realtime-v2](https://help.aliyun.com/en/model-studio/paraformer-realtime-v2)、[CosyVoice-v2](https://help.aliyun.com/zh/model-studio/cosyvoice-v2)。

本轮官方资料中查到中国北京地域参考：

- Paraformer realtime-v2：0.00024元/音频秒。
- CosyVoice-v2：2元/万计费字符。
- Qwen-plus非思考、输入≤128K：输入0.8元/百万Token、输出2元/百万Token。

仅为备选串联路线估算，不是本项目当前已选账单。字符、Token、音频秒互不等价，免费额和取整规则按实际服务处理。

```text
串联费用 = 音频计费秒×ASR单价
         + 输入Token×LLM输入价 + 输出Token×LLM输出价
         + TTS计费字符×字符单价
         + 检索/图片/地图/网络等独立成本
```

“每月100次调用足够”缺少每轮时长、响应长度、听说比例、搜索、缓存与上下文增长数据，不能作为可行性结论。

### 9.3 自托管与包体

API模式：无需团队常驻GPU，但需要网络，供应商处理音频与图片，费用由用户账号产生。

自托管模式：模型权重、GPU开机时长、媒体服务、存储、运维与并发均计成本，不能只算下载免费。V1不采用必需自托管后端。

150MB是Android单架构发行APK工程目标，不是实测值。Flutter、原生地图、音频和素材的实际依赖体积必须构建后记录；安装占用、内容包和临时缓存单独算。

## 10. 研究到开发的验证清单

### 10.1 四个优先技术实验

| 实验 | 做什么 | 通过条件 |
| --- | --- | --- |
| 原生能力与包体 | 两端地图、权限、录音播放、相机、干净构建 | Flutter桥接可用、拒绝权限不崩、包体可解释 |
| 实时知识闭环 | 用户问景点→本地工具→事实与来源→语音→打断 | 真正使用工具，无资料时不编，播放可停止 |
| 位置与拍照 | 位置候选＋临时照片辅助，多候选与冲突样本 | 自动讲解不把最近POI当必然答案，如实说明依据 |
| 网络热点 | 实际搜索、返回来源、超时/注入/无结果 | 不是模型自称联网；来源可核、权限与费用可控 |

这些实验无需先做社群、角色养成、分布式服务或大规模内容覆盖。

### 10.2 开源仓库后续核验

由具备GitHub CLI的环境完成，固定每个候选的提交与许可文件：

```bash
gh repo view OWNER/REPO --json nameWithOwner,url,isArchived,defaultBranchRef,licenseInfo
gh api repos/OWNER/REPO/commits --method GET -f sha=DEFAULT_BRANCH -f per_page=1
gh api repos/OWNER/REPO/contents/LICENSE --method GET -f ref=COMMIT_SHA
```

`OWNER/REPO`、默认分支、提交SHA必须用真实查询结果替换。LICENSE可能另有文件名或子目录，`licenseInfo`不是完整审计，也不能只读取主仓库而忽略前端、模型、依赖和素材。

核验记录至少包括：仓库、固定提交、日期、源码LICENSE/NOTICE、子模块、依赖、模型权重、角色/声线/数据、所需API、维护情况和安全问题。不使用星数代替维护与适配判断。

### 10.3 发布前阻断项

- 忽略仓库现有Apache-2.0许可，或把它误用于第三方模型、地图、声线和受限授权内容。
- 授权渠道存在，但授权范围不包含传云、改写、音频或App分发。
- 搜索摘要许可证未核验就整库复制，或将VTuber前端错误标为MIT。
- 地图Key与包名/签名不匹配，或实际用途没有相应服务许可。
- 任意端点回填泄露Key，或未告知图片/录音/位置送往何处。
- 没有真实搜索结果却宣称联网查证，或把网页指令当工具权限。
- 没有实测照片识别、iOS、打断、包体，却把目标宣传成能力事实。
- V1内部原型未经阶段复核直接变公众服务。

## 11. 最终建议

**独立Flutter客户端 + Kotlin/Swift薄桥接 + 本地SQLite知识/确认记忆 + 一个经验证的国内实时语音供应商**最符合已确认需求。开源项目用于减少试错，不作为绕过移动工程、许可证或可信内容工作的捷径。

最先验证实时工具、位置候选、图片辅助、联网出处与音频取消能否在真机共同成立；这比选择更大的模型、更多Agent或更复杂数据库更影响立项成败。

## 12. 补充模型与数据来源

- [Qwen3-ASR-0.6B模型卡](https://huggingface.co/Qwen/Qwen3-ASR-0.6B)
- [qwen-asr发布包](https://pypi.org/project/qwen-asr/)
- [Qwen3-TTS-12Hz-0.6B-Base模型卡](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base)
- [Qwen3-TTS-Tokenizer-12Hz](https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz)
- [qwen-tts发布包](https://pypi.org/project/qwen-tts/)
- [Qwen3-4B模型LICENSE](https://huggingface.co/Qwen/Qwen3-4B/blob/main/LICENSE)
- [Transformers发布包](https://pypi.org/project/transformers/)
- [Qwen3-Omni官方模型卡与资源表](https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct)
- [OSM官方版权索引](https://www.openstreetmap.org/copyright/attribution-guide/)

所有链接为本轮已发现的候选或官方资料；GitHub仓库固定提交审计与生产性能测试仍未完成。网页更新后应重新核对模型、收费与授权条件。
