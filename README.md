# ETH Whale Watcher

Watches Ethereum for "whale" USDT transfers, stores them in Postgres, and alerts Telegram subscribers.

## How it works

1. Polls `eth_getLogs` over explicit block ranges, lagging `CONFIRMATION_BLOCKS` behind head.
   Not `create_filter` — a server-side filter keeps its cursor on the node, so there is
   nothing to persist and nothing to resume from.
2. Keeps `Transfer` events at or above `WHALE_THRESHOLD_TOKENS`. `value` is not indexed and
   log filters only match topics by equality, so the threshold has to be applied client-side.
3. Writes them deduplicated by `(tx_hash, log_index)`. One transaction emits many `Transfer`
   logs, so `tx_hash` alone is not unique.
4. Scan position lives in `scan_state`, not in `MAX(block_number)` — most ranges contain no
   whales, but having scanned them is still progress.

Inserts and the scan-position update share one transaction, so a crash mid-scan re-scans
that range on the next poll and `ON CONFLICT DO NOTHING` makes the retry a no-op.

## Notifications

The bot is a separate process. It shares Postgres with the scanner and nothing
else — no shared event loop, so the scanner stays synchronous.

1. `/start` records a subscriber with a cursor at the current scan head, so new
   subscribers get no backlog.
2. Each subscriber carries their own `last_notified_block`. A "notified" flag on
   `transfer` would not work — delivery is a property of the (transfer, subscriber)
   pair, not of the transfer.
3. Cursors advance only after a successful send. A duplicate alert is noise; a
   missed transfer defeats the product.

Alerts arrive roughly 3 minutes after the transfer: `CONFIRMATION_BLOCKS` costs
~2.4 min, the poll interval up to 1 more. That latency is deliberate — it buys
not alerting on transfers that get reorganized away.

## Stack

- **Web3** — Python API for talking to Ethereum nodes
- **SQLAlchemy + Alembic** — ORM + migration system
- **pydantic-settings** — config, .env management
- **aiogram** — Telegram bot framework
- **uv** — dependency management
- **ruff** - linter and code formatter
- **Docker Compose** — local infrastructure in one command
- **pytest** - test framework

## Configuration

| Variable                 | Default         | Notes                                                       |
|--------------------------|-----------------|-------------------------------------------------------------|
| `WHALE_THRESHOLD_TOKENS` | `1000000`       | whole USDT, not raw units                                   |
| `CONFIRMATION_BLOCKS`    | `12`            | reorg buffer, ~2.4 min                                      |
| `MAX_BLOCKS_PER_SCAN`    | `10`            | capped by the RPC provider, see below                       |
| `ETH_RPC_URL`            |                 | Ethereum node url                                           |
| `SQL_ECHO`               | `false`         | log every SQL statement                                     |
| `BOT_TOKEN`              |                 | telegram bot token from [BotFather](https://t.me/BotFather) |
| `POSTGRES_DB`            | `whale_watcher` | PostgreSQL database name                                    |
| `POSTGRES_USER`          | `whale`         | PostgreSQL user                                             |
| `POSTGRES_PASSWORD`      | `whale`         | PostgreSQL password                                         |
| `POSTGRES_PORT`          | `5435`          | PostgreSQL port                                             |

## Running locally

One-time setup:

```bash
uv sync
cp .env.example .env        # fill in ETH_RPC_URL
docker compose up -d
uv run alembic upgrade head
uv run pre-commit install
```

Running:

```bash
uv run python -m app.main        # scanner
uv run python -m app.bot        # telegram bot
```

Integration tests need a `whale_watcher_test` database on the configured Postgres instance:

```bash
docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "CREATE DATABASE whale_watcher_test"
```

Running tests:

```bash
uv run pytest tests/unit        # no DB or network
uv run pytest        # needs docker compose up -d db
```

## Provider limits

- Alchemy free tier caps `eth_getLogs` at a 10-block range. At 60s polling that covers 10 blocks/min against ~5
  produced, so there is headroom to catch up after downtime.
- publicnode allows 100-block ranges but keeps only ~50 blocks of log history and returns a bare HTTP 403 for anything
  older, so it can't be used to backfill.

## Status

Working: scanning, whale filtering, reorg handling, storage, and Telegram
notifications with per-subscriber cursors and at-least-once delivery.

Limitations: one token (USDT), one global threshold shared by all subscribers,
and a 50-transfer batch cap that could skip a transfer if a single block ever
held more than 50 whales.

Plan: label known addresses (exchanges, bridges, treasuries) instead of raw hex,
and classify transfers as exchange in/out — a 5M USDT move means nothing without
knowing whether it left Binance. Then per-user thresholds and multiple tokens.
