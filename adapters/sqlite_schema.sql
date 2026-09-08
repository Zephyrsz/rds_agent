-- RDS Agent SQLite Metadata Schema
-- Version: 1.0
-- Created: 2026-09-02
-- Description: SQLite schema for storing RDS Agent metadata

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- ============================================================================
-- 1. Tables - 表定义
-- ============================================================================

CREATE TABLE IF NOT EXISTS tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- 表名（唯一）
    description TEXT NOT NULL,          -- 描述
    tags TEXT,                          -- 标签（JSON 数组）
    grain TEXT,                         -- 数据粒度描述
    entities TEXT,                      -- 业务实体（JSON 数组）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,          -- 版本号
    active BOOLEAN DEFAULT TRUE         -- 是否激活
);

CREATE INDEX IF NOT EXISTS idx_tables_name ON tables(name);
CREATE INDEX IF NOT EXISTS idx_tables_active ON tables(active);

-- ============================================================================
-- 2. Columns - 列定义
-- ============================================================================

CREATE TABLE IF NOT EXISTS columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL,          -- 外键到 tables
    name TEXT NOT NULL,                 -- 列名
    type TEXT NOT NULL,                 -- 数据类型（INTEGER, VARCHAR 等）
    description TEXT,                   -- 描述
    is_primary_key BOOLEAN DEFAULT FALSE,
    is_foreign_key BOOLEAN DEFAULT FALSE,
    foreign_key_table TEXT,             -- 外键引用的表
    foreign_key_column TEXT,            -- 外键引用的列
    enum_values TEXT,                   -- 枚举值（JSON 数组）
    nullable BOOLEAN DEFAULT TRUE,
    default_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE,
    UNIQUE(table_id, name)              -- 同一表内列名唯一
);

CREATE INDEX IF NOT EXISTS idx_columns_table_id ON columns(table_id);
CREATE INDEX IF NOT EXISTS idx_columns_name ON columns(name);
CREATE INDEX IF NOT EXISTS idx_columns_foreign_key ON columns(foreign_key_table, foreign_key_column);

-- ============================================================================
-- 3. Joins - Join 关系
-- ============================================================================

CREATE TABLE IF NOT EXISTS joins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    left_table TEXT NOT NULL,
    left_column TEXT NOT NULL,
    right_table TEXT NOT NULL,
    right_column TEXT NOT NULL,
    join_type TEXT DEFAULT 'INNER',     -- INNER, LEFT, RIGHT, FULL
    cardinality TEXT,                   -- one_to_one, one_to_many, many_to_one
    description TEXT,
    name TEXT,
    auto_join BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 100,
    fan_out_risk BOOLEAN DEFAULT FALSE,
    temporal_validity TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(left_table, left_column, right_table, right_column)
);

CREATE INDEX IF NOT EXISTS idx_joins_left ON joins(left_table, left_column);
CREATE INDEX IF NOT EXISTS idx_joins_right ON joins(right_table, right_column);

-- ============================================================================
-- 4. Metrics - 指标定义
-- ============================================================================

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- 指标名称（唯一）
    display_name TEXT NOT NULL,         -- 显示名称
    description TEXT NOT NULL,          -- 描述
    expression TEXT NOT NULL,           -- SQL 表达式
    tables TEXT NOT NULL,               -- 涉及的表（JSON 数组）
    filters TEXT,                       -- 过滤条件（JSON 数组）
    time_column TEXT,                   -- 时间字段
    unit TEXT,                          -- 单位（元、件等）
    data_type TEXT DEFAULT 'DECIMAL',   -- 数据类型
    min_value REAL,                     -- 最小值（用于验证）
    max_value REAL,                     -- 最大值（用于验证）
    category TEXT,                      -- 分类（销售、运营等）
    tags TEXT,                          -- 标签（JSON 数组）
    metric_type TEXT DEFAULT 'simple',
    numerator TEXT,
    denominator TEXT,
    base_measure TEXT,
    comparison TEXT,
    format TEXT,
    certification TEXT DEFAULT 'draft',
    valid_dimensions TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name);
CREATE INDEX IF NOT EXISTS idx_metrics_category ON metrics(category);
CREATE INDEX IF NOT EXISTS idx_metrics_active ON metrics(active);
CREATE INDEX IF NOT EXISTS idx_metrics_display_name ON metrics(display_name);

-- ============================================================================
-- 5. Dimensions - 维度定义
-- ============================================================================

CREATE TABLE IF NOT EXISTS dimensions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- 维度名称（唯一）
    display_name TEXT NOT NULL,         -- 显示名称
    table_name TEXT NOT NULL,           -- 表名
    column_name TEXT NOT NULL,          -- 列名
    mappings TEXT,                      -- 映射规则（JSON 对象）
    category TEXT,                      -- 分类
    tags TEXT,                          -- 标签（JSON 数组）
    dimension_type TEXT DEFAULT 'categorical',
    granularities TEXT,
    filter_column TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_dimensions_name ON dimensions(name);
CREATE INDEX IF NOT EXISTS idx_dimensions_table ON dimensions(table_name);
CREATE INDEX IF NOT EXISTS idx_dimensions_active ON dimensions(active);

-- ============================================================================
-- 6. Terms - 业务术语
-- ============================================================================

CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL,                 -- 术语（如 "华东"）
    synonyms TEXT NOT NULL,             -- 同义词（JSON 数组）
    category TEXT,                      -- 分类
    description TEXT,                   -- 说明
    standard_name TEXT,
    maps_to TEXT,
    exclusions TEXT,
    context TEXT,
    priority INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term);
CREATE INDEX IF NOT EXISTS idx_terms_category ON terms(category);
CREATE INDEX IF NOT EXISTS idx_terms_active ON terms(active);

-- ============================================================================
-- 7b. Domains, entities, measures and reusable filters
-- ============================================================================

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    allowed_tables TEXT,
    allowed_metrics TEXT,
    default_timezone TEXT DEFAULT 'Asia/Shanghai',
    default_currency TEXT DEFAULT 'CNY',
    active BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'primary',
    keys TEXT,
    expr TEXT,
    references_entity TEXT,
    active BOOLEAN DEFAULT TRUE,
    UNIQUE(name, table_name)
);

CREATE TABLE IF NOT EXISTS measures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    expression TEXT NOT NULL,
    table_name TEXT,
    aggregation TEXT,
    data_type TEXT DEFAULT 'DECIMAL',
    unit TEXT,
    additive BOOLEAN,
    time_additive BOOLEAN,
    active BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    expression TEXT NOT NULL,
    description TEXT,
    applies_to TEXT,
    synonyms TEXT,
    active BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_domains_active ON domains(active);
CREATE INDEX IF NOT EXISTS idx_entities_table ON entities(table_name);
CREATE INDEX IF NOT EXISTS idx_measures_active ON measures(active);
CREATE INDEX IF NOT EXISTS idx_filters_active ON filters(active);

-- 全文搜索索引
CREATE VIRTUAL TABLE IF NOT EXISTS terms_fts USING fts5(
    term,
    synonyms,
    description,
    content=terms,
    content_rowid=id
);

-- 自动同步 FTS 索引的触发器
CREATE TRIGGER IF NOT EXISTS terms_ai AFTER INSERT ON terms BEGIN
    INSERT INTO terms_fts(rowid, term, synonyms, description)
    VALUES (new.id, new.term, new.synonyms, new.description);
END;

CREATE TRIGGER IF NOT EXISTS terms_ad AFTER DELETE ON terms BEGIN
    DELETE FROM terms_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS terms_au AFTER UPDATE ON terms BEGIN
    DELETE FROM terms_fts WHERE rowid = old.id;
    INSERT INTO terms_fts(rowid, term, synonyms, description)
    VALUES (new.id, new.term, new.synonyms, new.description);
END;

-- ============================================================================
-- 7. Examples - 示例 SQL
-- ============================================================================

CREATE TABLE IF NOT EXISTS examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,             -- 问题
    sql TEXT NOT NULL,                  -- SQL 语句
    question_type TEXT,                 -- 问题类型
    tags TEXT,                          -- 标签（JSON 数组）
    description TEXT,                   -- 说明
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_examples_question_type ON examples(question_type);
CREATE INDEX IF NOT EXISTS idx_examples_active ON examples(active);

-- 全文搜索索引
CREATE VIRTUAL TABLE IF NOT EXISTS examples_fts USING fts5(
    question,
    sql,
    description,
    content=examples,
    content_rowid=id
);

-- 自动同步 FTS 索引的触发器
CREATE TRIGGER IF NOT EXISTS examples_ai AFTER INSERT ON examples BEGIN
    INSERT INTO examples_fts(rowid, question, sql, description)
    VALUES (new.id, new.question, new.sql, new.description);
END;

CREATE TRIGGER IF NOT EXISTS examples_ad AFTER DELETE ON examples BEGIN
    DELETE FROM examples_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS examples_au AFTER UPDATE ON examples BEGIN
    DELETE FROM examples_fts WHERE rowid = old.id;
    INSERT INTO examples_fts(rowid, question, sql, description)
    VALUES (new.id, new.question, new.sql, new.description);
END;

-- ============================================================================
-- 8. Metadata Versions - 版本管理（可选）
-- ============================================================================

CREATE TABLE IF NOT EXISTS metadata_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,          -- 实体类型（metric, dimension, table）
    entity_id INTEGER NOT NULL,         -- 实体 ID
    version INTEGER NOT NULL,           -- 版本号
    data TEXT NOT NULL,                 -- 完整数据（JSON）
    change_description TEXT,            -- 变更说明
    changed_by TEXT,                    -- 变更人
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_versions_entity ON metadata_versions(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_versions_created_at ON metadata_versions(created_at);

-- ============================================================================
-- 自动更新 updated_at 的触发器
-- ============================================================================

-- Tables
CREATE TRIGGER IF NOT EXISTS tables_updated_at AFTER UPDATE ON tables BEGIN
    UPDATE tables SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Columns
CREATE TRIGGER IF NOT EXISTS columns_updated_at AFTER UPDATE ON columns BEGIN
    UPDATE columns SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Joins
CREATE TRIGGER IF NOT EXISTS joins_updated_at AFTER UPDATE ON joins BEGIN
    UPDATE joins SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Metrics
CREATE TRIGGER IF NOT EXISTS metrics_updated_at AFTER UPDATE ON metrics BEGIN
    UPDATE metrics SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Dimensions
CREATE TRIGGER IF NOT EXISTS dimensions_updated_at AFTER UPDATE ON dimensions BEGIN
    UPDATE dimensions SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Terms
CREATE TRIGGER IF NOT EXISTS terms_updated_at AFTER UPDATE ON terms BEGIN
    UPDATE terms SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Examples
CREATE TRIGGER IF NOT EXISTS examples_updated_at AFTER UPDATE ON examples BEGIN
    UPDATE examples SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
