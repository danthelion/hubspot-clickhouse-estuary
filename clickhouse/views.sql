-- Views and materialized views for the demo dashboard.
-- Run once via: docker exec -i ch-demo clickhouse-client --user estuary --password '<pw>' --database demo --multiquery < views.sql

-- ============================================================================
-- VIEW: deal aggregates by stage (computed at query time)
-- ============================================================================
DROP VIEW IF EXISTS deals_by_stage;
CREATE VIEW deals_by_stage AS
SELECT
    JSONExtractString(flow_document, 'properties', 'dealstage') AS stage,
    count() AS deal_count,
    sum(toFloat64OrZero(JSONExtractString(flow_document, 'properties', 'amount'))) AS total_value
FROM deals FINAL
WHERE assumeNotNull(`_meta/op`) != 'd'
GROUP BY stage;

-- ============================================================================
-- VIEW: top-level KPIs across the pipeline
-- ============================================================================
DROP VIEW IF EXISTS pipeline_kpis;
CREATE VIEW pipeline_kpis AS
SELECT
    (SELECT count() FROM contacts FINAL WHERE assumeNotNull(`_meta/op`) != 'd') AS contacts,
    (SELECT count() FROM companies FINAL WHERE assumeNotNull(`_meta/op`) != 'd') AS companies,
    (SELECT count() FROM deals FINAL WHERE assumeNotNull(`_meta/op`) != 'd') AS deals,
    (SELECT sum(toFloat64OrZero(JSONExtractString(flow_document, 'properties', 'amount')))
     FROM deals FINAL WHERE assumeNotNull(`_meta/op`) != 'd') AS deal_value;

-- ============================================================================
-- REFRESHABLE MATERIALIZED VIEW: real-time event feed
--
-- WHY REFRESHABLE (not the classic INSERT-trigger MV):
--   The Estuary materialize-clickhouse connector loads data via a
--   staging table + `ALTER TABLE flow_temp_store_0_<table>
--   MOVE PARTITION ID 'all' TO TABLE <table>`. MOVE PARTITION is a
--   metadata-only operation — it does NOT fire MVs subscribed to the
--   destination. An MV like `CREATE MV events_feed_mv TO events_feed
--   AS SELECT ... FROM deals` will only ever capture the rows that
--   existed at MV creation time (plus any direct inserts you make
--   yourself), and silently stay frozen as new connector batches land.
--
--   REFRESHABLE MVs solve this by re-running the SELECT on a schedule
--   and atomically replacing the target table's contents.
--   Available since ClickHouse 23.12.
-- ============================================================================
DROP TABLE IF EXISTS events_feed;
DROP VIEW IF EXISTS events_from_contacts;
DROP VIEW IF EXISTS events_from_companies;
DROP VIEW IF EXISTS events_from_deals;

CREATE MATERIALIZED VIEW events_feed
REFRESH EVERY 2 SECOND
ENGINE = MergeTree
ORDER BY (event_time, object_type, object_id)
AS
SELECT
    flow_published_at AS event_time,
    'contact'         AS object_type,
    JSONExtractString(flow_document, 'id') AS object_id,
    concat(
        JSONExtractString(flow_document, 'properties', 'firstname'), ' ',
        JSONExtractString(flow_document, 'properties', 'lastname')
    ) AS label,
    JSONExtractString(flow_document, 'properties', 'email') AS detail,
    assumeNotNull(`_meta/op`) AS op
FROM contacts FINAL
WHERE assumeNotNull(`_meta/op`) != 'd'
UNION ALL
SELECT
    flow_published_at,
    'company',
    JSONExtractString(flow_document, 'id'),
    JSONExtractString(flow_document, 'properties', 'name'),
    JSONExtractString(flow_document, 'properties', 'industry'),
    assumeNotNull(`_meta/op`)
FROM companies FINAL
WHERE assumeNotNull(`_meta/op`) != 'd'
UNION ALL
SELECT
    flow_published_at,
    'deal',
    JSONExtractString(flow_document, 'id'),
    JSONExtractString(flow_document, 'properties', 'dealname'),
    concat(
        '$',
        formatReadableQuantity(toFloat64OrZero(JSONExtractString(flow_document, 'properties', 'amount'))),
        ' · ',
        JSONExtractString(flow_document, 'properties', 'dealstage')
    ),
    assumeNotNull(`_meta/op`)
FROM deals FINAL
WHERE assumeNotNull(`_meta/op`) != 'd';
