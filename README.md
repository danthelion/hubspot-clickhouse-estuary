# HubSpot → Estuary → ClickHouse: real-time CRM analytics demo

End-to-end reference implementation for streaming HubSpot CRM data into
ClickHouse with [Estuary](https://estuary.dev), plus a single-page real-time
dashboard.

📖 **Read the blog post:** [Title TBD](https://example.com/blog-post-link)

---

## Layout

```
.
├── hubspot-oauth/                # HubSpot OAuth helper + app manifest template
├── hubspot-capture/              # Estuary capture spec (template)
├── hubspot-seeder/               # CRM data seeder
├── clickhouse/                   # docker-compose stack + CH config + views.sql
├── clickhouse-materialization/   # Estuary materialization spec (template)
└── webapp/                       # FastAPI + Chart.js dashboard
```

## Quickstart

```bash
# 1. ClickHouse + ngrok + webapp
cd clickhouse
cp .env.example .env             # fill in NGROK_AUTHTOKEN + a CH password
docker compose up -d

# 2. HubSpot capture
cd ../hubspot-capture
cp flow.yaml.example flow.yaml   # fill in client_id / client_secret / refresh_token
flowctl raw discover --source flow.yaml
flowctl catalog publish --source flow.yaml \
  --init-data-plane ops/dp/public/<region> --auto-approve

# 3. ClickHouse materialization
cd ../clickhouse-materialization
cp flow.yaml.example flow.yaml   # fill in ngrok URL + CH password
flowctl catalog publish --source flow.yaml \
  --init-data-plane ops/dp/public/<region> --auto-approve

# 4. Dashboard views
cd ../clickhouse
docker exec -i ch-demo clickhouse-client \
  --user "$(grep CLICKHOUSE_USER .env | cut -d= -f2)" \
  --password "$(grep CLICKHOUSE_PASSWORD .env | cut -d= -f2)" \
  --database demo --multiquery < views.sql

# 5. Open the dashboard
open http://localhost:8080
```

See the blog post for the full setup story, design notes, and gotchas.

## License

MIT — see [LICENSE](./LICENSE).
