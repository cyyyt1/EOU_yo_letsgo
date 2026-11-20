PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;
-- user_version 2：place_alias 增加 confidence（auto/review/manual）

-- 1. 包清单：单行，换包即整库替换
CREATE TABLE content_package (
  package_id      TEXT PRIMARY KEY,      -- 包标识 hz-core
  version         TEXT NOT NULL,         -- 包版本 1.2.0
  city_code       TEXT NOT NULL,         -- 城市行政区划码 330100
  published_at    TEXT NOT NULL,         -- 内容发布日期 ISO-8601
  license_note    TEXT NOT NULL,         -- 包级授权说明
  checksum_sha256 TEXT NOT NULL          -- 包完整性校验值
);

-- 2. 点位：自引用三层 景区→景点→点位
CREATE TABLE place (
  place_id           TEXT PRIMARY KEY,   -- 点位ID leifeng-pagoda
  parent_id          TEXT REFERENCES place(place_id) ON DELETE CASCADE,
                                         -- 上级点位ID，顶层为 NULL
  level              TEXT NOT NULL
                       CHECK (level IN ('area','site','point')),
                                         -- area 景区 / site 景点 / point 具体点位
  name               TEXT NOT NULL,      -- 名称
  lat                REAL NOT NULL,      -- 纬度（已归一为 GCJ-02）
  lon                REAL NOT NULL,      -- 经度（已归一为 GCJ-02）
  candidate_radius_m INTEGER NOT NULL
                       CHECK (candidate_radius_m >= 0)
                                         -- 候选判定半径（米）
);

-- 3. 别名：语音「名字→点位」的反向索引
CREATE TABLE place_alias (
  place_id   TEXT NOT NULL REFERENCES place(place_id) ON DELETE CASCADE,
                                         -- 点位ID
  alias      TEXT NOT NULL,              -- 别名 黄妃塔 / leifengta
  confidence TEXT NOT NULL DEFAULT 'auto'
               CHECK (confidence IN ('auto','review','manual')),
                                         -- auto 自动生成 / review 待复核 / manual 人工指定
  PRIMARY KEY (place_id, alias)
);
CREATE UNIQUE INDEX ux_place_alias ON place_alias(alias);
                                         -- 全局唯一：导入期暴露「一词多指」冲突

-- 4. 讲解条目：讲稿 + 要点 + 来源 + 时效
CREATE TABLE fragment (
  fragment_id     TEXT PRIMARY KEY,      -- 条目ID f-leifeng-legend-001
  place_id        TEXT NOT NULL REFERENCES place(place_id) ON DELETE CASCADE,
                                         -- 所属点位ID
  title           TEXT NOT NULL,         -- 标题 白蛇传说
  fragment_type   TEXT NOT NULL
                    CHECK (fragment_type IN
                      ('fact','legend','poetry','highlight','trivia','practical','spatial')),
                                         -- 史实/传说/诗文/看点/冷知识/实用/方位
  content         TEXT NOT NULL,         -- 标准讲解词
  content_short   TEXT,                  -- 精简讲解词（导出时抽取首两句）
  key_points      TEXT,                  -- 关键知识点 JSON 数组，联网时唯一事实输入
  keywords        TEXT,                  -- 关键词标签 JSON 数组
  valid_to        TEXT,                  -- 有效期截止，仅 practical 有值
  verified_at     TEXT,                  -- 最近核验日，仅 practical 有值
  source_title    TEXT NOT NULL,         -- 来源名称
  source_url      TEXT,                  -- 来源链接（古籍可为 NULL）
  attribution     TEXT NOT NULL,         -- 署名或授权编号
  allow_cloud_llm INTEGER NOT NULL DEFAULT 0
                    CHECK (allow_cloud_llm IN (0,1)),
                                         -- 是否允许把本条发给云端模型
  CHECK (fragment_type = 'practical'
         OR (valid_to IS NULL AND verified_at IS NULL))
);
CREATE INDEX idx_fragment_place ON fragment(place_id);
