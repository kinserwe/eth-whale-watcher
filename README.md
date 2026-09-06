# ETH Whale Watcher

Watches Ethereum for "whale" USDT transfers, stores them in Postgres, and alerts Telegram
subscribers — filtered so that what arrives is worth reading.

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

## Filtering

Raw whale transfers are mostly noise. Four layers sit between a stored transfer and a
notification, and the storage floor stays low on purpose — `eth_getLogs` returns every
`Transfer` regardless, so filtering costs nothing extra and a lower floor only means more
rows to reconsider later.

**Flash-loan round trips.** A transfer is dropped when the same transaction contains its
mirror — same token, `from` and `to` swapped. A bot borrows 57M USDT from a lending
protocol, arbitrages a few hundred dollars across pools, and repays in the same
transaction: two alerts for zero net movement. Matching on the address pair alone would
also eat legitimate two-way traffic, so `tx_hash` is the load-bearing part of the
predicate. Fee-charging protocols return slightly different amounts, so value is
deliberately not compared.

**Same-entity movement.** `Binance 14 → Binance 17` is an internal rebalance. Comparing
labels cannot see this — exchanges run dozens of wallets — which is why `entity` is stored
separately from `label`.

**Per-subscriber thresholds and category exclusions.** Each subscriber sets their own
minimum and can hide categories independently by direction. `treasury → exchange` (new
supply) and `exchange → treasury` (redemption) are opposite events, so one symmetric list
could not express the difference.

**Ordering.** Rows come back ordered by `(block_number, log_index)`. Block number alone
leaves same-block rows unordered, which once rendered a flash-loan repayment before the
borrow that caused it.

## Notifications

The bot is a separate process. It shares Postgres with the scanner and nothing
else — no shared event loop, so the scanner stays synchronous.

1. `/start` records a subscriber with a cursor at the current scan head, so new
   subscribers get no backlog.
2. Each subscriber carries their own `last_notified_block`. A "notified" flag on
   `transfer` would not work — delivery is a property of the (transfer, subscriber)
   pair, not of the transfer.
3. The cursor means "everything up to here has been considered", not "everything up to
   here has been sent". A subscriber whose filters exclude everything still advances;
   otherwise a quiet stretch looks indistinguishable from downtime.
4. Cursors advance only after a successful send, and only for subscribers where *every*
   message in the batch was delivered. A duplicate alert is noise; a missed transfer
   defeats the product.

One message per transfer, not a joined batch — fifty transfers exceeded Telegram's
4096-character limit and failed as a unit. The etherscan link is an HTML anchor, so the
66-character transaction hash lives in a message entity rather than counting toward that
limit.

Alerts arrive roughly 3 minutes after the transfer: `CONFIRMATION_BLOCKS` costs
~2.4 min, the poll interval up to 1 more. That latency is deliberate — it buys
not alerting on transfers that get reorganized away.

## Labels

`address_label` maps addresses to an entity, a display label, a category and a source.
Seeded from a hand-curated `labels.json` via `app/load_labels.py`, which is idempotent and
checksum-normalises every address — `transfer` stores checksummed addresses, and a
mixed-case join silently matches nothing.

`entity` and `label` are separate fields because they fail differently: a wrong `label`
shows a wrong name, which is visible and correctable, while a wrong `entity` *hides*
transfers through same-entity suppression and fails silently. Entities are only shared
between addresses when the relationship is certain.

Labelled category pairs are mapped to event names — `Exchange inflow`, `Redemption`,
`New supply` — so a message says what happened rather than leaving the reader to interpret
two hex strings.

## What the data shows

Measured over a 30-day backfill and several days of live operation:

| Threshold | Raw / day | After flash-loan filter |
|-----------|-----------|-------------------------|
| 1M        | 1135      | 985                     |
| 5M        | 270       | 188                     |
| 10M       | 150       | 71                      |
| 20M       | 112       | 34                      |
| 50M       | 31        | 8                       |

**74.7% of transfers above 50M are flash-loan legs.** One overnight sample ran 42 noise
messages out of 43. Raising the threshold to cut volume actually *concentrates* the noise,
which is why filtering rather than thresholds does the work here.

At the 20M threshold, 141 alerts over 3.5 days involved only 72 distinct addresses. Label
coverage is bounded and small, not an endless problem.

## Stack

- **Web3** — Python API for talking to Ethereum nodes
- **SQLAlchemy + Alembic** — ORM + migration system
- **pydantic-settings** — config, .env management
- **aiogram** — Telegram bot framework
- **uv** — dependency management
- **ruff** — linter and code formatter
- **Docker Compose** — the whole stack in one command
- **pytest** — test framework

## Configuration

| Variable                 | Default         | Notes                                                       |
|--------------------------|-----------------|-------------------------------------------------------------|
| `WHALE_THRESHOLD_TOKENS` | `1000000`       | storage floor in whole USDT; the alert threshold is per-subscriber |
| `CONFIRMATION_BLOCKS`    | `12`            | reorg buffer, ~2.4 min                                      |
| `MAX_BLOCKS_PER_SCAN`    | `10`            | capped by the RPC provider, see below                       |
| `ETH_RPC_URL`            |                 | Ethereum node url                                           |
| `SQL_ECHO`               | `false`         | log every SQL statement                                     |
| `BOT_TOKEN`              |                 | telegram bot token from [BotFather](https://t.me/BotFather) |
| `POSTGRES_DB`            | `whale_watcher` | PostgreSQL database name                                    |
| `POSTGRES_USER`          | `whale`         | PostgreSQL user                                             |
| `POSTGRES_PASSWORD`      | `whale`         | PostgreSQL password                                         |
| `POSTGRES_HOST`          | `127.0.0.1`     | `db` inside compose, overridden per service                 |
| `POSTGRES_PORT`          | `5435`          | published on loopback only                                  |

## Running

The whole stack:

```bash
cp .env.example .env        # fill in ETH_RPC_URL and BOT_TOKEN
docker compose up -d --build
```

`migrate` runs `alembic upgrade head` and must exit 0 before `scanner` and `bot` start, so
neither can come up against a stale schema. Postgres publishes on `127.0.0.1` only —
Docker writes its own iptables rules ahead of UFW, so a plain port mapping would expose
the database on a public host regardless of firewall rules.

Seed the labels once the database exists:

```bash
docker compose run --rm scanner python -m app.load_labels
```

For development against the host Python:

```bash
uv sync
uv run pre-commit install
docker compose up -d db
uv run alembic upgrade head
uv run python -m app.main        # scanner
uv run python -m app.bot         # telegram bot
```

Use `127.0.0.1` rather than `localhost` for `POSTGRES_HOST` — `localhost` resolves to IPv6
first and the published port is IPv4 only, costing a ~2s fallback on every connection.

Integration tests need a `whale_watcher_test` database:

```bash
docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "CREATE DATABASE whale_watcher_test"

uv run pytest tests/unit        # no DB or network
uv run pytest                   # needs docker compose up -d db
```

## Provider limits

- Alchemy free tier caps `eth_getLogs` at a 10-block range. At 60s polling that covers 10 blocks/min against ~5
  produced, so there is headroom to catch up after downtime.
- publicnode allows 100-block ranges but keeps only ~50 blocks of log history and returns a bare HTTP 403 for anything
  older, so it can't be used to backfill.

## Status

Working: scanning, reorg handling, storage, address labels, flash-loan and same-entity
suppression, per-subscriber thresholds and category filters, event annotation, and Telegram
notifications with at-least-once delivery. Deployed and running continuously.

Known gaps:

- One token (USDT). Per-token threshold ladders would be needed first — "5M" is a sensible
  floor for a stablecoin and nonsense for WETH.
- A multi-hop transfer produces one alert per hop. Chains span up to ~50 minutes, so
  grouping them means either delaying alerts or editing sent messages.
- `/settings` before `/start` raises `NoResultFound` — the settings queries assume a
  subscriber row exists.
- `_skip_stale` counts missed transfers without applying the flash-loan and category
  filters, so it overstates.
- The cursor advance for caught-up subscribers is covered at the `_fetch` level but not
  through `_send_batch`.
- A 50-transfer batch cap could skip a transfer if a single block ever held more than 50
  whales.
