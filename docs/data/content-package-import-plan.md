# content_package 导入方案（杭州包 V1）

## 1. 语义与约束

- `content_package` 是**单行包清单**：一个发行库只有一个生效包，换包即整库替换，没有 `package_uid`、`is_active` 或多包共存（KNOWLEDGE K12）。
- 发行库随 APK 预置为 SQLite 资产，首启复制到 app data；V1 不做运行期导入 UI。
- 该行必须在其余三表定型后**最后写入**，校验值覆盖除自身以外的全部内容。
- 校验和只用于检测损坏，不代表来源可信或拥有版权（DESIGN §6.1）。

## 2. 字段规则

| 字段 | 取值规则 | 当前建议值 |
|---|---|---|
| `package_id` | `<城市前缀>-<包类型>`，固定不随版本变化；独立授权包用 `hz-<来源>` 命名，但仍整库替换 | `hz-core` |
| `version` | `MAJOR.MINOR.PATCH`；MAJOR=发行库结构或契约不兼容，MINOR=点位/片段增删或来源体系变化，PATCH=文字修正、来源补录、时效核验 | 首个内部包 `0.1.0` |
| `city_code` | GB/T 2260 行政区划码，杭州固定 | `330100` |
| `published_at` | 打包完成时刻，ISO-8601 带时区，禁止未来时间；不是资料采集日 | `2026-11-19T20:40:00+08:00` 形式 |
| `license_note` | 包级授权说明，须逐项可核验；不得写入尚未取得的授权 | 见 §3 模板 |
| `checksum_sha256` | 64 位小写十六进制，按 §4 规范计算 | 打包时生成 |

版本号由打包环节确定并记录到发布说明，不写进构建清单；同一版本对应唯一的源码提交与内容快照，已发布版本不可覆盖，只能递增。

## 3. license_note 模板

单行分号分隔，便于机器展示与人工核对：

```
hz-core 内容包 | 坐标: 高德地图 Web 服务（授权日期/编号待补） | 名录: 杭州市A级景区名录(2024-07，公开政务信息) | 讲解文本: 团队原创改写，不含百科/OTA原文 | 图片: 未收录 | 限制: 不转售、不单独再分发坐标数据
```

填写要求：

- 每一类内容都要有明确权利来源；没有证据的写「待补」，不能省略成默认授权。
- 必须与 KNOWLEDGE.MD §7 的来源清单一致：百度百科全文、马蜂窝、携程、大众点评属于**排除来源**，不得出现在包内。
- 图片、声线、角色素材分别记权利；当前包不含媒体资源。
- `license_note` 是包级摘要，逐条来源仍以 `fragment.source_title`/`source_url`/`attribution` 为准。

## 4. checksum_sha256 计算规范

对「包内容」做规范化导出后计算，避免 SQLite 文件页布局导致重建结果不一致。

**参与范围**：`place`、`place_alias`、`fragment` 三表，按 DDL 列顺序输出（含 `place_alias.confidence`）；不含 `content_package` 自身。

**规范化规则**：

1. 表顺序固定：`place` → `place_alias` → `fragment`。
2. `place` 按 `place_id` 升序；`place_alias` 按 `(place_id, alias)` 升序；`fragment` 按 `fragment_id` 升序。
3. 每行一行 JSON：首行是表头，随后每行一个对象，均使用紧凑分隔符 `(",", ":")`、`ensure_ascii=False`、NULL 输出 `null`。
4. 首行固定为：`{"format":"hz-content-package-v1","schema_user_version":2}`。
5. 每行以 `\n` 结尾，整体 UTF-8 编码，SHA-256 取小写十六进制。

```python
import hashlib, json, sqlite3

TABLES = {
    "place": ("place_id", "parent_id", "level", "name", "lat", "lon", "candidate_radius_m"),
    "place_alias": ("place_id", "alias", "confidence"),
    "fragment": ("fragment_id", "place_id", "title", "fragment_type", "content",
                 "content_short", "key_points", "keywords", "valid_to", "verified_at",
                 "source_title", "source_url", "attribution", "allow_cloud_llm"),
}

def package_checksum(db_path: str) -> str:
    """Hash the canonical dump of place, place_alias, and fragment tables."""
    lines = [json.dumps({"format": "hz-content-package-v1", "schema_user_version": 2},
                        ensure_ascii=False, separators=(",", ":"))]
    with sqlite3.connect(db_path) as connection:
        for table, columns in TABLES.items():
            order = "place_id, alias" if table == "place_alias" else columns[0]
            rows = connection.execute(
                f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order}")
            for row in rows:
                record = {"table": table, **dict(zip(columns, row))}
                lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
```

客户端收到包后重算同一校验值，与 `content_package.checksum_sha256` 比对；不一致即拒绝替换并保留旧包。

## 5. 发布门禁（当前状态）

| 门禁 | 要求 | 现状 |
|---|---|---|
| schema | `PRAGMA user_version = 2`，4 表结构与 DDL 一致 | 通过 |
| place | 全部有坐标；无缺字段行 | 102 条，通过 |
| place_alias | 至少覆盖官方名、简称、高德差异名；`review` 行须复核 | 253 条（auto 209 / manual 44）；39 条 review 已复核：38 条转 manual，1 条「杭州市运河」因语义泛化删除；无待复核，通过 |
| fragment 来源 | 本期包只含原创改写且 `approved` 的 fact/highlight/trivia/spatial/legend | 发行库 204 条（fact 103 / highlight 31 / trivia 49 / spatial 18 / legend 3）：159 条标注「团队原创改写」，45 条引官网/官方媒体并保留 `source_url`；无百科原文，通过 |
| 改写表 | 仅 `status=approved` 的行可入包 | 204 条 approved（fact 103 / highlight 31 / trivia 49 / spatial 18 / legend 3）；4 条 rejected（fact）来源不匹配已排除；发行库与改写表逐条一致，通过 |
| practical | 只含已核验条目，`verified_at`/`valid_to` 齐全 | 本期不发布 practical（官方渠道核验无法执行），已从改写范围剔除 |
| allow_cloud_llm | 按来源逐条判定 | 全 0（安全默认，待复核） |
| license_note | 每类内容有可核验授权 | 已写入「保留所有权利，仅随 App 使用」（简化版，未逐项列坐标授权日期/编号）；45 条引用来源的片段另在 `source_title/source_url/attribution` 标注 |
| 体积 | 1–10 MB 量级（DESIGN §8.2） | 0.47 MB，通过 |
| 媒体 | 不含未授权图片/音频 | 通过 |

**阻断项**：无。包清单已写入，`validate_dist.py` 全部通过。2026-11-19 联网来源试点新增 3 条官方来源片段（中国丝绸博物馆、太湖源、艺创小镇），包版本升至 0.2.0；同日第二批单条点位补齐 20 条（14 trivia + 6 spatial），包版本升至 0.3.0；第三批再补 19 条（11 trivia + 5 spatial + 3 legend），包版本升至 0.4.0；第四批按「官方源 + Wikidata」策略补写 7 条官方来源片段（浙江美术馆、良渚古城遗址、中国江南水乡文化博物馆、杭州京杭大运河博物馆、中国大运河（杭州段）、新登古城墙、下姜村），包版本升至 0.5.0；第五批再补 17 条官方来源片段（临安博物馆、小营·江南红巷、郊坛下与老虎洞窑址、龙坞茶镇、画外桐坞、白云间、鹳山、塘栖、临安云制造小镇、物联网小镇、梦栖小镇、信息港小镇、大创小镇、图灵小镇、人工智能小镇、航空小镇、机器人小镇），包版本升至 0.6.0；第六批为最后 10 个单条点位各补 1 条（九咆界、垂云通天河、七里扬帆、山沟沟、千岛湖天屿、红色茶山、运河财富·智慧网谷、浙大紫金科创、医药港、玉皇山南），包版本升至 0.7.0；第六批入包后按高德校准红色茶山坐标，由 118.45/29.50 修正为厦山村村委会 118.440861/29.501812（原坐标偏东约 900 米），包版本升至 0.7.1；第七批为原本 0 片段的 4 个点位各补 2 条官方来源片段（杭州雷峰塔、钓鱼岛、富春大岭图、文武上田），包版本升至 0.8.0。遗留风险：`license_note` 为简化版权声明，未记录高德坐标授权的日期/编号。若后续对外分发，建议补齐坐标授权凭证并按 §3 模板重写 `license_note`。

## 6. 打包流程

1. 冻结数据库：停止写入，确认 `schema-dist.sqlite` 为最新一次导入结果。
2. 跑门禁查询（§7），全部通过才继续。
3. 按 §4 计算 `checksum_sha256`。
4. 写入单行包清单（先删后插，保持单行）：

```sql
DELETE FROM content_package;
INSERT INTO content_package
  (package_id, version, city_code, published_at, license_note, checksum_sha256)
VALUES
  ('hz-core', '0.1.0', '330100', '2026-11-19T20:40:00+08:00',
   '待按 §3 模板填写并核对授权', '<64位小写sha256>');
```

5. 复验：`PRAGMA integrity_check`、`PRAGMA foreign_key_check`、三表计数、重算 checksum 与写入值一致。
6. 导出包文件 `hz-core-<version>.sqlite`，同时记录源码提交、`user_version`、包版本、校验值到发布说明。
7. 替换失败时保留旧包；不做合并、不自动修复。

## 7. 门禁查询

```sql
SELECT COUNT(*) FROM place;
SELECT COUNT(*) FROM place_alias;
SELECT confidence, COUNT(*) FROM place_alias GROUP BY confidence;
SELECT COUNT(*) FROM fragment;
SELECT COUNT(*) FROM fragment WHERE fragment_type = 'practical'
  AND (valid_to IS NULL OR verified_at IS NULL);
SELECT COUNT(*) FROM content_package;
PRAGMA user_version;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

## 8. 当前结论

方案已执行完毕：`content_package` 单行已写入（`hz-core` 0.8.0，`published_at` 2026-11-20T09:11:45+08:00），`license_note` 采用「保留所有权利，仅随 App 使用」，校验值 `83fe4ee1b8b517602da743c8fc688e8111b36b7f3b7ed0d46d05efcc3960cd2b`，`validate_dist.py` 0 失败。本期可行性版本的范围：practical 暂不发布（官方渠道核验无法执行），做 fact 103 条 + highlight 31 条 + trivia 49 条 + spatial 18 条 + legend 3 条的原创改写，工作放在独立表 `docs/data/fragment-rewrite.csv`，只有 `approved` 行进入发行库；其中 45 条引用官网/官方媒体来源并保留链接，其余 159 条标注团队原创。4 条因来源与点位不匹配标记为 `rejected`（雷峰塔、钓鱼岛、富春大岭图、文武上田），第七批已用官方来源重写补入，rejected 行仅作审计记录。第六批 10 条全部有官方来源，10 个单条点位已各补 1 条；运河财富·智慧网谷因合并了两个小镇，保留 2 条 fact（fact-01 讲运河财富、fact-02 讲智慧网谷）。第七批为 4 个零片段点位各补 2 条，102 个点位均至少有 2 条片段。遗留事项：坐标授权凭证与逐项 `license_note` 待补；红色茶山坐标已按高德厦山村村委会校准（118.440861/29.501812，候选半径 800 米）；如需发布新版本，按 §6 递增版本并重算校验值。
