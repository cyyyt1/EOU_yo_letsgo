# Fragment 导入方案（杭州包 V1）

## 1. 现状与输入

| 项 | 值 |
|---|---|
| 目标表 | `fragment`（14 字段，见 `schema-dist.sql`） |
| 内容源 | `scenic(1).xlsx` → 工作表「景点总表」 |
| 内容行数 | 109（唯一名称 109） |
| 可对应点位 | 102（已入库 `place` 102 行） |
| 发行库现状 | `fragment` 204 行（fact 103 / highlight 31 / trivia 49 / spatial 18 / legend 3），覆盖 102 个点位；159 条团队原创 + 45 条引用官网/官方媒体 |
| 源表结构 | 34 列，含 `official_name`/`url`/`summary`/`intro`/`tour_info`/`attractions`/`culture`/`body`/`toc`/`open_time`/`ticket` 等 |
| 未覆盖点位 | 已删除 11 个无可用内容点位（10 个无内容 3A/2A 小镇 + 桐庐江南古村落风景区源数据错配），决策见 `place-exclusions.csv` |
| 应排除 | 千岛湖森林氢吧、海上丝绸之路杭州段、桐庐天子地生态风景旅游区、古韵河桥景区、千岛湖玖玖花海景区、钱塘江古海塘潮文化景观（6 条对应已清空点位，FK 无法落库） |

源字段填充率（109 行）：`summary`/`intro` 100%，`body` 108，`tour_info` 57，`open_time` 53，`culture` 44，`ticket` 35，`attractions` 16，`tel` 0。

## 2. 来源与授权（前置红线）

- `source` 列写的是「杭州A级景区名录(2024-07)」，但 `url`/`lemma_id` 指向百度百科，`body` 为百科正文。**这两者不能混写**。
- 计划：`source_title` 按实际段落来源填写，百科段落写「百度百科 · <lemma_title>」，`source_url` 用 `url`，`attribution` 写 `百度百科 lemma <lemma_id>`；名录只用于 grade/地址等事实字段。
- 百科正文受著作权保护，**不得原样复制进发行包**。导入流程只做「参考底稿 + 人工改写/校验」，`allow_cloud_llm` 一律默认 `0`。
- 「图片清单」553 条为 `bkimg.cdn.bcebos.com` 外链，涉及版权与热链，**不导入**。
- 古诗文、地名沿革等公有领域内容可整理后入库，仍需标注出处。

## 3. 字段映射

| fragment 字段 | 来源 | 规则 |
|---|---|---|
| `fragment_id` | 生成 | `f-<place_id>-<type>-<nn>`，如 `f-hz-b023b13l9m-fact-01` |
| `place_id` | `official_name` 对 `place.name` | 精确匹配；匹配不上进入待办，不猜 |
| `title` | `toc` 章节名 / 固定名 | fact 用「概览」，highlight 用「主要看点」，practical 用「实用信息」 |
| `fragment_type` | 按来源字段/章节判定 | 见第 4 节 |
| `content` | `summary`/`intro`/`body` 对应章节 | 改写后 80–400 字，保留事实不保留原文句式 |
| `content_short` | `content` 前两句 | ≤80 字，导出时自动抽取，人工复核 |
| `key_points` | `famous_for`/`attractions` 拆分 | JSON 数组，3–5 条，每条 ≤20 字 |
| `keywords` | 名称 + 章节名 + 类型 | JSON 数组，3–8 个 |
| `valid_to` | 仅 practical | 首次核验后 +180 天 |
| `verified_at` | 仅 practical | 写入核验日期，未核验不填 |
| `source_title` | 段落实际来源 | 见第 2 节 |
| `source_url` | `url` | 古籍类可为 NULL |
| `attribution` | 来源编号 | `百度百科 lemma <lemma_id>` / 名录批次 |
| `allow_cloud_llm` | 人工判定 | 默认 0；改写完成且无版权风险才可置 1 |

## 4. 类型判定与切片规则

| 类型 | 优先级 | 来源 | 单点数量 | 说明 |
|---|---|---|---|---|
| `fact` | P0 | `summary`/`intro` | 1 | 必须生成，缺内容则点位标记「内容缺口」 |
| `highlight` | P0 | `attractions` + `famous_for` | 0–2 | 至少 3 个要点才生成 |
| `spatial` | P1 | `body` 中「方位布局/地理环境/景区布局」章节 | 0–1 | 只写方位与到达关系，不写路线攻略 |
| `trivia` | P1 | 「命名/相关文化/历史沿革」章节 | 0–1 | 容易与 fact 重复，需查重 |
| `legend` | P2 | `body` 含「传说/故事」的段落（17 个点位） | 0–2 | 必须人工核实，标注传说属性，不得当史实 |
| `poetry` | P2 | `body` 含诗文引用的段落（34 个点位） | 0–2 | 只收公有领域原文，附作者/篇名 |
| `practical` | P0（核验后） | `open_time`/`ticket`/`tour_info` | 0–1 | 未核验不进发行包；`tel` 全空，不生成电话条目 |

约束：
- `valid_to`/`verified_at` 仅 `practical` 可非空，与表 CHECK 一致。
- 同一点位片段总数目标 2–5 条；不足 2 条记入内容缺口清单。
- 每段 `content` 不得与百科原文连续重合超过 20 字（人工抽查 + 脚本 n-gram 检查）。

## 5. 执行流程

1. **抽取**：脚本读 xlsx，按 `official_name` 关联 `place.place_id`，输出 `docs/data/fragment-staging.csv`，列含所有 fragment 字段 + `source_field`、`review_status`、`risk_note`。
2. **自动生成 P0**：fact/highlight 先出机器草稿，`review_status=draft`。
3. **人工改写与核验**：逐条过 `content`、`key_points`、来源标注；practical 对照官网/公众号核验门票与开放时间，填 `verified_at`、`valid_to`。
4. **QA 门禁**：类型合法、practical 时效字段唯一、place_id 存在、JSON 合法、长度合规、重复与原文重合检查、每点位片段数统计。
5. **落库**：`docs/data/fragment-rewrite.csv` 中 `approved` 行经 `scripts/build_rewrite_sql.py` 生成 `docs/data/fragment-import.sql`（先清空 `fragment` 再写入，草稿与 rejected 不会残留），随后事务写入 `schema-dist.sqlite`；`validate_dist.py` 校验发行库与 approved 行逐条一致。
6. **打包**：填写 `content_package`（package_id、version、city_code=330100、published_at、license_note、checksum_sha256），checksum 由导出文件计算。

## 6. 验收指标（V1 首版）

- 点位覆盖：102/102 有点位至少 1 条 `fact`（当前内容源可支撑 102）。
- 片段总量：预计 250–400 条（109 点位 × 2–5 条）；本期可行性版本实际发布 204 条（fact 103 / highlight 31 / trivia 49 / spatial 18 / legend 3，102 个点位），其余类型保留草稿不入包。
- practical：只收录已核验条目，未核验清单单独输出。
- 版权：无整段百科原文入库；无图片外链；`allow_cloud_llm=1` 的条目需逐条审批。
- 缺口披露：10 个无内容点位、6 个已清空点位、`tel` 全空，均写入导入报告。

## 7. 样例

```sql
INSERT INTO fragment (
  fragment_id, place_id, title, fragment_type, content, content_short,
  key_points, keywords, source_title, source_url, attribution, allow_cloud_llm
) VALUES (
  'f-hz-b023b13l9m-fact-01', 'hz-b023b13l9m', '概览', 'fact',
  '西湖位于杭州市西湖区，三面环山、一面临城，湖面约6.38平方公里，以「一山二塔三岛三堤五湖」的格局闻名。',
  '西湖位于杭州市西湖区，湖面约6.38平方公里，以「一山二塔三岛三堤五湖」的格局闻名。',
  '["湖面约6.38平方公里","三面环山一面临城","一山二塔三岛三堤五湖"]',
  '["西湖","世界文化遗产","湖泊"]',
  '百度百科 · 杭州西湖风景区', 'https://wapbaike.baidu.com/item/65000333',
  '百度百科 lemma 65000333', 0
);
```

注：上例 content 已改写，非百科原文；`allow_cloud_llm=0` 为默认值。

## 8. 首轮抽取结果（2026-11-19）

脚本：`scripts/build_fragments.py`；源文件已复制到 `datasets/raw/scenic.xlsx`（gitignore）。

| 指标 | 结果 |
|---|---|
| 匹配点位 | 102 |
| 片段总数（抽取草稿） | 328 |
| 发行库片段（approved） | 204（fact 103 / highlight 31 / trivia 49 / spatial 18 / legend 3，102 个点位） |
| 类型分布 | fact 103 / practical 70 / trivia 60 / spatial 34 / legend 25 / highlight 31 / poetry 7 |
| 审核状态 | draft 223 / needs_verification 105（legend、poetry、practical 及试点 fact 补注） |
| ID 与 JSON 校验 | 无重复 ID，key_points/keywords 均可解析 |
| 内容缺口 | 11 个无可用内容点位已删除；8 个无坐标点位排除；102 个入库点位均有 fact |
| 内容偏薄 | 无；第六批为 10 个单条点位各补 1 条，第七批为原本 0 片段的 4 个点位各补 2 条，102 个点位均有至少 2 条片段 |
| 改写缺口 | 4 条 fact 因来源与点位不匹配标记 `rejected`（雷峰塔、钓鱼岛、富春大岭图、文武上田）；第七批已改用官方来源重新补写，rejected 行保留作审计记录，不进入发行包 |

抽取规则补充：
- 解析前保留换行，只在中文之间去除空格，避免标题与正文粘连。
- poetry 只收「引号内 ≥10 字且邻近出现诗句/题诗/绝句等上下文」的引文，首轮 7 条仍需核对作者与出处。
- practical 不写 `verified_at`/`valid_to`，核验通过后再补。
- 百度百科正文含 UI 残留（查看更多、合并图册）已清理；staging 与 coverage 均为本地 CSV，不随仓库提交。
- 本期可行性版本的改写范围定为 `fact` + `highlight` + `trivia` + `spatial` + `legend`，`practical` 因官方核验无法执行暂不发布，`poetry` 因作者与出处无法核实暂不发布；其余草稿留待后续版本。
- 改写进度：204 条已完成原创改写并审核通过（approved，fact 103 / highlight 31 / trivia 49 / spatial 18 / legend 3），已通过 `scripts/build_rewrite_sql.py` 导入发行库；4 条 rejected 未入包。其中 45 条引用官方来源并保留 `source_url`：3 条 highlight 来自 2026-11-19 联网来源试点（中国丝绸博物馆、太湖源、艺创小镇），7 条来自第四批按「官方源 + Wikidata」策略的补写（浙江美术馆、良渚古城遗址、中国江南水乡文化博物馆、杭州京杭大运河博物馆、中国大运河（杭州段）、新登古城墙、下姜村，含文化和旅游部、中国世界文化遗产中心等来源），17 条来自第五批官方来源补写（临安新闻网、浙江宣传、杭州网、央视网、新华网、浙江省政协、杭州日报、浙江在线、滨江新闻网、人民日报海外版、中国新闻网、杭州市政协），10 条来自第六批（潮新闻、杭州网、人民日报海外版、浙江在线、浙江大学官网、千岛湖新闻网），8 条来自第七批（杭州网 2 条、千岛湖新闻网 2 条、杭州在线 2 条、人民日报 2 条）。第二批补齐 14 条 trivia 与 6 条 spatial，第三批补齐 11 条 trivia、5 条 spatial 与 3 条 legend，第六批补齐 4 条 trivia、3 条 spatial、2 条 highlight 与 1 条 fact，第七批为 4 个零片段点位各补 fact 与 highlight/trivia。328 条抽取草稿仅作本地参考，不进入发行库。

