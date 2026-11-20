# Flutter 核心导游代码骨架计划

## Context

仓库目前只有 `DESIGN.MD`、`RESEARCH.MD` 等规划资料，没有 Flutter 工程。目标是把文档中的核心导游链路落成可运行、可测试、便于后续接入真实服务的企业级骨架，而不是用静态假数据伪装完整功能。

已确认的技术与范围：

- **架构**：feature-based Clean Architecture，依赖方向为 `Presentation → Domain ← Data`。
- **状态管理 / DI**：Riverpod 手写 Provider，不引入 GetIt 或代码生成。
- **路由**：go_router。
- **范围**：地图选点、本地知识查询、实时导游会话；不包含完整 V1 的其他模块。
- **工程**：完整 Flutter 工程，含 `lib/`、`test/`、Android/Kotlin、iOS/Swift。
- **外部能力**：SQLite、高德地图、实时 WebSocket、音频和权限仅保留必要边界，本轮不真实集成。

依据：`DESIGN.MD:74-123`（核心交互）、`DESIGN.MD:154-198`（知识与实时会话）、`DESIGN.MD:204-238`（技术与模块边界）、`DESIGN.MD:276-300`（内容包与坐标）、`DESIGN.MD:526-540`（测试要求）。

## 1. 创建完整 Flutter 工程

1. 检查 Flutter stable 与设备工具链，在仓库根目录生成 Android/iOS 工程：
   ```bash
   flutter create --platforms=android,ios --android-language=kotlin --ios-language=swift --project-name=eou_yo_letsgo --org=com.example .
   ```
2. `com.example.eou_yo_letsgo` 仅作为本地骨架的临时 applicationId / Bundle ID；不得用于地图 Key、签名或正式发布，正式集成前替换为团队确认的反向域名。
3. 保留现有 `DESIGN.MD`、`RESEARCH.MD`、空的 `JOURNAL.MD`、`LICENSE`；检查 `flutter create` 的 diff，合并而不是丢失 `.gitignore` 中现有凭据、数据库与构建产物规则。
4. 通过 `flutter pub add flutter_riverpod go_router` 解析当前 Flutter 环境兼容的稳定版本，使用 `flutter_lints`，提交应用工程的 `pubspec.lock`。
5. 暂不加入 Freezed、Riverpod Generator、build_runner、json_serializable、mockito/mocktail、sqflite、WebSocket、地图、音频或权限插件；当前实体和测试 Fake 均手写。

## 2. 建立目录与文件骨架

只创建有真实职责的文件，不为目录对称增加空模型、空仓储或通用工具类。

```text
lib/
├── main.dart
├── app/
│   ├── app.dart
│   └── router.dart
├── core/
│   ├── domain/
│   │   ├── poi.dart
│   │   └── knowledge.dart
│   └── platform/
│       ├── audio_session_gateway.dart
│       └── permission_gateway.dart
└── features/
    ├── map_selection/
    │   └── presentation/
    │       ├── pages/map_selection_page.dart
    │       ├── providers/map_selection_provider.dart
    │       └── widgets/
    │           ├── map_surface.dart
    │           └── poi_selection_list.dart
    ├── local_knowledge/
    │   ├── knowledge_providers.dart
    │   ├── data/
    │   │   ├── datasources/
    │   │   │   ├── local_knowledge_data_source.dart
    │   │   │   └── asset_knowledge_data_source.dart
    │   │   └── repositories/knowledge_repository_impl.dart
    │   ├── domain/
    │   │   ├── repositories/knowledge_repository.dart
    │   │   └── usecases/query_local_knowledge.dart
    │   └── presentation/
    │       ├── pages/poi_detail_page.dart
    │       ├── providers/knowledge_query_notifier.dart
    │       └── widgets/knowledge_content_view.dart
    └── guide_session/
        ├── guide_session_providers.dart
        ├── data/
        │   ├── datasources/realtime_guide_client.dart
        │   ├── gateways/local_guide_knowledge_gateway.dart
        │   └── repositories/unimplemented_guide_session_repository.dart
        ├── domain/
        │   ├── entities/guide_session.dart
        │   ├── repositories/guide_session_repository.dart
        │   └── usecases/handle_knowledge_tool_call.dart
        └── presentation/
            ├── pages/guide_session_page.dart
            ├── providers/
            │   ├── guide_session_notifier.dart
            │   └── guide_session_state.dart
            └── widgets/guide_transcript_view.dart

assets/content/public_example.json

test/
├── app/core_flow_widget_test.dart
├── features/guide_session/guide_session_notifier_test.dart
├── features/local_knowledge/
│   ├── asset_knowledge_data_source_test.dart
│   └── query_local_knowledge_test.dart
└── helpers/test_app.dart
```

同时生成标准 `android/`、`ios/`、`pubspec.yaml`、`analysis_options.yaml`；本轮不添加自定义 Kotlin/Swift MethodChannel。

## 3. 实现应用组合与最小路由

- `lib/main.dart`：仅安装 `ProviderScope` 并启动 `EouApp`，不 eager 初始化地图、定位、麦克风或实时连接。
- `lib/app/app.dart`：`MaterialApp.router`、中文开发期标题和基础 Material 主题。
- `lib/app/router.dart`：
  - `/` → `MapSelectionPage`
  - `/poi/:poiId` → `PoiDetailPage`
  - `/poi/:poiId/guide` → `GuideSessionPage`
- 路由只传 `poiId`，不通过 `extra` 传仓储、凭据、Notifier 或大型领域对象；不存在的 POI 显示明确空状态。

## 4. 实现共享领域契约与本地知识链路

### 共享实体

- `lib/core/domain/poi.dart`：`Poi`、`GeoPoint`、`CoordinateSystem`，保留 POI ID、原始坐标与坐标系，避免未来重复转换。
- `lib/core/domain/knowledge.dart`：`KnowledgePack`、`KnowledgeFragment`、`KnowledgeSource`、`PoiDetail`、`KnowledgeQueryResult`；来源保留真实 ID、标题、可选链接/授权编号、来源类型和审核信息，片段区分事实、传说与观点。

### 本地知识

- `KnowledgeRepository`：`listPois()`、`getPoi(poiId)`、按当前 `poiId` 和文本 `query()`。
- `LocalKnowledgeDataSource`：`loadPack()` 与 `searchFragments()`；未来 SQLite 实现同一端口。
- `AssetKnowledgeDataSource`：
  - 真实实现 Asset JSON 读取、必填字段/schema 版本检查、POI/片段/来源解析及来源引用完整性检查。
  - `searchFragments()` 保留 `TODO(search)` 并抛 `UnimplementedError`，不把简单字符串过滤或空数组冒充已完成检索。
- `KnowledgeRepositoryImpl`：组合 POI 详情、片段及其真实来源；检索委托 datasource。
- `QueryLocalKnowledge`：trim 查询文本、拒绝空查询、强制携带当前 `poiId`。
- `assets/content/public_example.json`：提供合法的空内容包元数据及空 `pois/fragments/sources`，不编造景点或来源；测试所需 POI 只放在 `test/` Fixture。
- `PoiDetailPage` / `KnowledgeContentView`：展示加载、空、错误和内容状态；使用 `SelectionArea` 支持复制，展示来源及事实类型；检索未接入与“未查到”必须区分。
- `KnowledgeQueryNotifier`：用可空 `AsyncValue<KnowledgeQueryResult>` 表达未查询、加载、成功、失败；单独处理 `UnimplementedError`。

## 5. 实现地图选点入口

- `MapSurface` 定义当前 UI 所需地图适配边界，默认 `PlaceholderMapAdapter` 只显示“地图 SDK 未接入”，不模拟定位、地图标记或授权成功。
- `PoiSelectionList` 消费本地知识的只读 POI 目录，在真实地图接入前提供可访问的选点回退；空内容包显示空状态。
- `MapSelectionProvider` 只保存 `selectedPoiId`，选点后进入 `/poi/:poiId`。
- 不为一次 UI 选中状态额外创建 `MapRepository` 或 `SelectPoiUseCase`；真实定位、附近候选与导航接入时再扩展 domain/data。

## 6. 实现实时导游会话骨架

### 领域契约

- `GuideSessionState` 字段：`poiId`、可空 `sessionId`、可空 `activeResponseId`、状态、能力集、消息、打断状态、安全用户提示。
- 状态枚举覆盖：`disconnected`、`connecting`、`listening`、`retrieving`、`generating`、`playing`、`paused`、`offline`、`unavailable`、`error`。
- 手写 sealed `GuideSessionEvent`：连接、响应开始、文本增量、音频输出、知识工具请求、响应完成、断开、失败；事件按类型携带 `sessionId/poiId/responseId`。
- `GuideSessionRepository`：
  - `open(poiId)` 返回 `Stream<GuideSessionEvent>`；
  - `sendText()`、`sendAudio()`、`sendToolResult()`、`interrupt()`、`close()`；
  - 真实收到连接/响应事件前，ID 保持 null，能力默认全部 false。
- `GuideKnowledgeGateway` 是只读知识工具的小端口；`LocalGuideKnowledgeGateway` 适配 `QueryLocalKnowledge`，避免会话 domain 依赖知识 data 实现。
- `HandleKnowledgeToolCall` 校验工具白名单、参数和 session/POI/response ID，查询后再次检查是否已过期，再允许回传工具结果。

### Data 与 Presentation

- `RealtimeGuideClient` 只定义默认供应商实时协议边界，不宣称通用兼容所有供应商。
- `UnimplementedGuideSessionRepository` 的所有外部业务动作使用邻近的 `TODO(realtime)` 和 `UnimplementedError('实时导游服务尚未接入')`；不得返回空 Stream 或随机 session ID 假装成功。
- `GuideSessionNotifier`：
  - 管理 Stream 订阅、状态迁移、开始、发送、打断与关闭；
  - 用本地递增 `operationEpoch` 加 session/POI/response ID 丢弃迟到事件和工具结果；
  - 打断先使旧响应失效，再调用远端取消及音频清理边界；
  - auto-dispose 时取消订阅并关闭会话，不留下后台录音或连接；
  - 将 `UnimplementedError` 映射为 `unavailable`，其他异常映射为安全提示，不直接显示可能含凭据的异常原文。
- `GuideSessionPage` / `GuideTranscriptView`：提供状态、文字输入、开始/停止、可复制消息和来源展开；无真实能力时禁用操作，不生成演示回答。

### 平台边界

- `AudioSessionGateway`：定义停止采集、音频播放、打断和清空待播队列等文档明确要求的能力。
- `PermissionGateway`：定义麦克风/使用中定位的权限状态与请求接口；本轮不创建权限实现、不添加运行时权限声明、启动时不弹权限。
- 暂无不用的 `DatabaseHelper`、migration 框架、空 SQLite 实现、通用多供应商插件或完整设置中心。

## 7. Riverpod 组合规则

- `knowledge_providers.dart` 和 `guide_session_providers.dart` 是 feature 组合根，允许装配 data/domain/presentation；domain 不导入 Flutter、Riverpod、go_router 或 data。
- POI 目录使用 `FutureProvider<List<Poi>>`，详情使用 `FutureProvider.family<PoiDetail, String>`。
- 地图选中使用手写 `NotifierProvider`；知识查询使用 family NotifierProvider。
- 会话使用 `autoDispose.family`，参数为 `poiId`；测试通过 `ProviderScope.overrides` 注入 Fake。
- 页面和 Notifier 不直接实例化 datasource/repository；跨 feature 知识调用通过只读 Provider/gateway，不暴露具体 SQLite 或 Asset 实现。

## 8. 测试与端到端验证

### 自动化测试

- `query_local_knowledge_test.dart`：空文本拒绝、trim、POI 透传、未实现异常不会变成空结果。
- `asset_knowledge_data_source_test.dart`：合法空包、缺字段、未知 schema、失效 source 引用、坐标系保留。
- `guide_session_notifier_test.dart`：未接入状态、默认无能力、旧 session/response 事件隔离、换 POI 后旧工具结果丢弃、打断后迟到事件丢弃、dispose 取消订阅。
- `core_flow_widget_test.dart`：目录 loading/error/empty/data、地图未接入提示、POI 路由、文本/来源展示、会话未接入状态、无活动会话不能发送、浏览不请求权限。

### 执行验证

```bash
flutter doctor -v
flutter pub get
flutter analyze
flutter test
flutter devices
flutter run -d <可用的 Android 设备或模拟器>
flutter build apk --debug
```

- 必须在可用 Android 设备/模拟器实际走查：启动 → 地图占位/POI 空状态；用测试 Fixture 验证 POI → 详情/来源 → 会话未接入；返回页面后无活动订阅。
- 当前 Windows 环境不能验证 iOS 真机；只检查生成的 Swift/Xcode 骨架，明确说明需在 macOS 后续执行 `flutter build ios --no-codesign`。
- 若没有任何可用移动设备，不声称 UI 已真体验证；只报告 analyze/test 结果及未完成的运行验证，不为了验证而额外把 Windows 桌面纳入支持平台。

## 非目标

本轮不实现拍照、记忆、热点搜索、账号/后端、完整 BYOK 设置中心、真实地图/定位/导航、SQLite/FTS、真实供应商 WebSocket、录音/播放/AEC、权限申请、多供应商系统、Release 签名或 CI/CD；也不添加伪造连接、假搜索、假来源或演示导游答案。

## 关键实施文件

- `lib/app/router.dart`
- `lib/core/domain/knowledge.dart`
- `lib/features/local_knowledge/data/datasources/asset_knowledge_data_source.dart`
- `lib/features/local_knowledge/knowledge_providers.dart`
- `lib/features/guide_session/domain/repositories/guide_session_repository.dart`
- `lib/features/guide_session/domain/usecases/handle_knowledge_tool_call.dart`
- `lib/features/guide_session/presentation/providers/guide_session_notifier.dart`
- `lib/features/guide_session/guide_session_providers.dart`