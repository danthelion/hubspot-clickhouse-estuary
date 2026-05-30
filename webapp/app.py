"""Real-time dashboard backend.

Streams a JSON snapshot of the HubSpot → ClickHouse pipeline state via
Server-Sent Events. Pure read-only queries against views defined in
clickhouse/views.sql.
"""
import asyncio
import json
import os
from pathlib import Path

import clickhouse_connect
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

CH_HOST = os.environ.get("CH_HOST", "clickhouse")
CH_PORT = int(os.environ.get("CH_PORT", "8123"))
CH_USER = os.environ.get("CH_USER", "estuary")
CH_PASSWORD = os.environ["CH_PASSWORD"]
CH_DATABASE = os.environ.get("CH_DATABASE", "demo")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "2.0"))

app = FastAPI()
HERE = Path(__file__).parent


def client():
    return clickhouse_connect.get_client(
        host=CH_HOST, port=CH_PORT, username=CH_USER,
        password=CH_PASSWORD, database=CH_DATABASE,
    )


def snapshot():
    c = client()
    kpis_row = c.query("SELECT contacts, companies, deals, deal_value FROM pipeline_kpis").result_rows[0]
    kpis = {"contacts": kpis_row[0], "companies": kpis_row[1],
            "deals": kpis_row[2], "deal_value": float(kpis_row[3] or 0)}

    stage_rows = c.query("SELECT stage, deal_count, total_value FROM deals_by_stage ORDER BY total_value DESC").result_rows
    stages = [{"stage": r[0] or "(unknown)", "count": r[1], "value": float(r[2] or 0)} for r in stage_rows]

    industry_rows = c.query("""
        SELECT JSONExtractString(flow_document, 'properties', 'industry') AS industry, count() AS n
        FROM companies FINAL
        WHERE assumeNotNull(`_meta/op`) != 'd'
        GROUP BY industry ORDER BY n DESC LIMIT 8
    """).result_rows
    industries = [{"industry": r[0] or "(unset)", "count": r[1]} for r in industry_rows]

    timeline_rows = c.query("""
        SELECT toStartOfMinute(event_time) AS m, object_type, count() AS n
        FROM events_feed
        WHERE event_time >= now() - INTERVAL 30 MINUTE
        GROUP BY m, object_type ORDER BY m
    """).result_rows
    timeline = [{"minute": r[0].isoformat(), "type": r[1], "count": r[2]} for r in timeline_rows]

    events = c.query("""
        SELECT event_time, object_type, label, detail, op
        FROM events_feed
        ORDER BY event_time DESC LIMIT 25
    """).result_rows
    events = [{"time": r[0].isoformat(), "type": r[1], "label": r[2], "detail": r[3], "op": r[4]} for r in events]

    c.close()
    return {"kpis": kpis, "stages": stages, "industries": industries,
            "timeline": timeline, "events": events}


@app.get("/api/snapshot")
def api_snapshot():
    return snapshot()


@app.get("/api/stream")
async def api_stream():
    async def gen():
        loop = asyncio.get_event_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, snapshot)
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(POLL_INTERVAL)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
def index():
    return FileResponse(HERE / "index.html")
