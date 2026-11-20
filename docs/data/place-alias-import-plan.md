# place_alias 导入方案（杭州包 V1）

## 1. 语义与约束

- `place_alias` 是语音/文字「名字 → 点位」的反向索引，主键 `(place_id, alias)`，并有全局唯一索引 `ux_place_alias(alias)`：**一个别名只能指向一个点位**。
- 每个点位必须写入**官方名本身**作为别名，保证只查别名表也能命中；其他变体是补充。
- 别名只指向 `place_id`，不建别名链、不建父子关系。
- 库内存储别名原文（官方名保持原样，便于与 `place.name` 精确对照）；查询侧加载别名表时统一归一化（NFKC、拉丁字母转小写、去首尾空白）后建内存索引，用户输入走同一归一化，避免全角/半角与空格差异。SQLite 无内置 Unicode 归一化函数，不做 SQL 侧归一化匹配。
- 别名是地名/景点名，不构成作品；来自高德的名称仅作索引，不复制其描述文本。

## 2. 候选来源与规则

| 规则 | 来源 | 示例 | 数量（干跑） | 处理 |
|---|---|---|---|---|
| S0 | 官方名 | 杭州西湖风景名胜区 | 102 | 全部直接写入 |
| S1 | 去行政区前缀（浙江省/杭州市/区县） | 临安区青山湖景区 → 青山湖景区 | 34 | 自动 |
| S2 | 去景区类后缀 | 杭州雷峰塔景区 → 杭州雷峰塔 | 52（1 条被覆盖表拒绝） | 自动 |
| S3 | 同时去前缀和后缀 | 杭州市千岛湖风景名胜区 → 千岛湖 | 22 | 自动 |
| S4 | 按 `·`、括号拆分 | 运河·塘栖古镇景区 → 塘栖古镇 | 21 | 人工复核 |
| S5 | 高德名称（与官方名相似度 ≥0.75，且无子 POI 标记） | 西溪国家湿地公园、严州古城 | 17 | 人工复核 |
| S6 | 策展库 lemma_title | 千岛湖、文渊狮城 | 0（首轮未启用） | 后续按需补 |
| S7 | 人工覆盖表 | 大运河 → 京杭大运河·杭州景区 | 6（已应用） | 人工维护 |
| S8 | 拼音/英文（如 leifengta） | — | 0 | 暂缓，需新增 pypinyin 依赖并获批 |

## 3. 过滤与校验

别名必须同时满足：

1. 长度 2–20，含中文或拉丁字母；纯数字、纯标点拒绝。
2. 不含 `·（）()` 等分隔符（官方名 S0 例外，按原文保留）；拆分类别名只保留拆出的片段。
3. 不在泛化停用词表：`景区/风景区/旅游区/公园/乐园/小镇/博物馆/美术馆/纪念馆/图书馆/古城/古街/湿地/运河/杭州/浙江/杭州段/杭州景区`。
4. 不含子 POI 或代理点标记：`游客中心/服务中心/停车场/码头/会客厅/设计中心/文创馆/咖啡馆/民宿/饭店/酒店/公交站/地铁站/放映点/售票处/入口/出口/水上乐园/越野车/暂停开放`。
5. 不是占位文本：`高德地理编码`、`用户手填`。
6. 高德名称与官方核心名的 `SequenceMatcher` 相似度 ≥0.75；不满足的进入人工复核，不自动写入。
7. 归一化后不得与任何官方名或其他别名重复。

干跑中因此被拒绝的典型噪声：`市千岛湖风景名胜区`（前缀重复剥离）、`临安大明山风景`、`大奇山国家森林`（后缀重复剥离）、`杭州段`、`径山古道`（子景点）、`杭州京杭大运河博物馆文创馆`（子馆）、`钓鱼岛水上乐园`（代理点）、`高德地理编码`（占位）。

## 4. 冲突处理

| 类型 | 规则 | 示例 |
|---|---|---|
| 字符串冲突 | 同一别名指向 ≥2 个点位：整条丢弃，写入冲突报告，不自动择一 | 干跑未发现 |
| 与官方名冲突 | 别名等于另一个点位的官方名：丢弃 | 干跑未发现 |
| 语义歧义 | 人工指定归属或直接禁用，记录在覆盖表 | 见下 |
| 同一实体双条目 | 短名归主景区；遗产条目只用全名 | 西湖 → 杭州西湖风景名胜区；西湖文化景观不加「西湖」 |
| 易误识别 | 直接禁用，不因「听起来像」而保留 | 钓鱼岛（千岛湖内部景点，与真实地名冲突） |

干跑需人工确认的语义项：

- `西湖` → 杭州西湖风景名胜区（西湖文化景观只保留全名）
- `大运河` / `京杭大运河` → 京杭大运河·杭州景区；`中国大运河` → 中国大运河（杭州段）
- `千岛湖` → 杭州市千岛湖风景名胜区
- `雷峰塔` → 杭州雷峰塔景区（不得指向西湖）
- `钓鱼岛` → 禁用
- `小营.江南红巷景区`（高德半角点）→ 归一化为 `小营·江南红巷景区` 或跳过

覆盖表 `docs/data/place-alias-overrides.csv`，列：`alias,place_id,action,note`；`action ∈ assign/reject`，优先级高于自动规则。

## 5. 干跑结果（2026-11-19）

| 指标 | 结果 |
|---|---|
| 官方名别名 | 102 |
| 变体别名 | 153 条候选，1 条被拒绝，152 条入库（S1 34 / S2 52 / S3 22 / S4 21 / S5 17 / S7 6） |
| 候选总数 | 255（首轮 proposed 254 / rejected 1；复核后 proposed 253 / rejected 2） |
| 有额外别名的点位 | 79 |
| 仅官方名的点位 | 23（博物馆、部分小镇） |
| 字符串冲突 / 官方名冲突 | 0 / 0 |
| 2 字别名 | 6：宋城（官方名）、鹳山、径山、西湖、五杭、超山（除宋城外均为 review/manual） |
| 待人工确认 | 45 = review 39（S4 21 / S5 17 / 2 字 S3 1）+ manual 6；2026-11-19 已复核：38 条转 manual，1 条删除 |

23 个仅官方名的点位不需要强行造别名；官方名已可被完整说中。2 字别名逐个确认，避免与区县、道路、子景点重名。

## 6. Staging CSV

`docs/data/place-alias-staging.csv`（gitignore），列：

```
alias,alias_norm,place_id,official_name,source_rule,confidence,status,note
```

- `source_rule`：S0–S5、S7。
- `confidence`：`auto` / `review` / `manual`，随行写入发行库 `place_alias.confidence`（schema v2，K18），端上只读。
- `status`：`proposed` / `rejected` / `conflict`；`rejected` 与 `conflict` 不生成 INSERT。
- `alias_norm`：归一化结果，用于模拟 `ux_place_alias` 唯一性检查。
- 冲突与拒绝原因写入 `note`，不静默丢弃。

## 7. 导入流程

1. 从 `place` 表取官方名，从 `coord-reviewed.csv` 取高德名称，生成候选。
2. 归一化、过滤、冲突检查，输出 staging 与冲突报告。
3. 人工确认 39 条 `review`（S4/S5 与 2 字超山）和 6 条 `manual`；语义项（S7 / reject）已确认，结论固化在覆盖表。复核结果：38 条以 `assign` 写入 `place-alias-overrides.csv` 并转为 `manual`，「杭州市运河」以 `reject` 删除（截断后语义泛化，易与京杭大运河·杭州景区混淆）。
4. 按 place_id 排序生成 SQL，整表重建：

```sql
BEGIN;
DELETE FROM place_alias;
INSERT INTO place_alias (place_id, alias, confidence) VALUES ('hz-b023b13l9m', '杭州西湖风景名胜区', 'auto');
INSERT INTO place_alias (place_id, alias, confidence) VALUES ('hz-b023b13l9m', '西湖', 'manual');
COMMIT;
```

使用普通 `INSERT` 而非 `INSERT OR REPLACE`：唯一索引冲突时应失败回滚，不能悄悄覆盖另一个点位的别名。

5. 验证：

```sql
SELECT COUNT(*) FROM place_alias;                       -- 预期 253
SELECT COUNT(DISTINCT place_id) FROM place_alias;       -- 预期 102
SELECT confidence, COUNT(*) FROM place_alias GROUP BY confidence;  -- auto 209 / manual 44
SELECT alias, COUNT(*) c FROM place_alias GROUP BY alias HAVING c > 1;  -- 预期空
SELECT COUNT(*) FROM place p WHERE NOT EXISTS (
  SELECT 1 FROM place_alias a WHERE a.place_id = p.place_id AND a.alias = p.name
);                                                       -- 预期 0
PRAGMA foreign_key_check;
PRAGMA user_version;                                    -- 预期 2
```

6. 别名表变更后重算 `content_package.checksum_sha256`（方案见 content-package-import-plan §4）。

## 8. 验收标准

- 102/102 点位都有官方名别名。
- 无未批准的字符串冲突；`ux_place_alias` 正常建立。
- 西湖、千岛湖、大运河、雷峰塔、良渚古城等高频说法能命中唯一点位。
- 子景点、代理点、占位文本、易误会地名（钓鱼岛）不进入别名表。
- 拼音别名暂不纳入验收；启用前需确认依赖与生成来源。

## 9. 当前状态

2026-11-19 已完成复核并落库：`place_alias` **253 行 / 102 点位**，`confidence` 分布 auto 209 / manual 44，无 `review` 行；schema 为 `user_version = 2`。删除了 11 个无内容点位后，其 23 条别名随外键级联清除。39 条 review 中 38 条转 `manual`，1 条「杭州市运河」经复核删除；复核结论固化在 `place-alias-overrides.csv`，重建 staging 与 SQL 后校验 0 失败。包清单校验值随后续内容变更重算，当前为 `83fe4ee1b8b517602da743c8fc688e8111b36b7f3b7ed0d46d05efcc3960cd2b`（hz-core 0.8.0）。
