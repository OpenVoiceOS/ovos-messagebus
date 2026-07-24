# Alternative Backends & Benchmarks

`ovos-messagebus` ships a pure-Python Tornado server by default.  Two
additional backends are available for deployments that need higher throughput
or lower latency.

---

## Backend overview

| Backend | Language | Entry point | Install |
|---------|----------|-------------|---------|
| **Tornado** (default) | Python 3 | `ovos-messagebus` / `python -m ovos_messagebus` | `pip install ovos-messagebus` |
| **webrockets** (optional) | Rust + PyO3 | `python -m ovos_messagebus.backends.webrockets_backend` | `pip install "ovos-messagebus[webrockets]"` |
| **ovos-rust-messagebus** (external) | Pure Rust binary | `./ovos-rust-messagebus` | build from [source](https://github.com/OscillateLabsLLC/ovos-rust-messagebus) |

All three backends expose the same OVOS wire protocol:

* WebSocket endpoint at `ws://<host>:<port>/<route>` (default `ws://0.0.0.0:8181/core`)
* First message after connect is a JSON `{"msg_type": "connected", ...}` greeting
* Every subsequent message is fan-out broadcast to **all** connected clients, including the sender

---

## Tornado backend

The reference implementation.  `MessageBusEventHandler`
(`ovos_messagebus/event_handler.py:30`) is a `tornado.websocket.WebSocketHandler`
subclass.  Fan-out is an explicit Python loop:

```python
# ovos_messagebus/event_handler.py:77
for client in client_connections:
    client.write_message(message)
```

Started via `ovos_messagebus.__main__.main` (`__main__.py:43`).

**Configuration** is read from `mycroft.conf["websocket"]` by
`load_message_bus_config()` (`load_config.py:31`).

---

## webrockets backend

A Rust-powered Python WebSocket server
([ploMP4/webrockets](https://github.com/ploMP4/webrockets), v0.1.5+).

### Install

```bash
pip install "ovos-messagebus[webrockets]"
```

### Run

```bash
python -m ovos_messagebus.backends.webrockets_backend
```

Reads the exact same `mycroft.conf["websocket"]` configuration as Tornado
(`host`, `port`, `route`, `filter`, `filter_logs`).

### Architecture

The backend (`ovos_messagebus/backends/webrockets_backend.py`) creates a
`WebsocketServer` with the OVOS route registered via `create_route()`:

```python
# webrockets_backend.py:75
route = server.create_route(route_path, default_group=_GLOBAL_ROOM)
```

`default_group=_GLOBAL_ROOM` means every connecting client is automatically
placed in the broadcast room `__ovos_bus__`.  The receive handler then fans
out to everyone:

```python
# webrockets_backend.py:100
conn.broadcast([_GLOBAL_ROOM], data, exclude_self=False)
```

`exclude_self=False` (the webrockets default) ensures the sender also receives
its own message — identical to the Tornado loop behaviour.

### Backwards-compatibility matrix

| Feature | Tornado | webrockets |
|---------|---------|------------|
| Port / route | configurable | configurable (same config) |
| Initial `"connected"` message | ✓ | ✓ |
| Fan-out to all clients (incl. sender) | ✓ | ✓ |
| Optional message filtering / logging | ✓ | ✓ |
| `max_msg_size` enforcement | ✓ | ✗ (not exposed in Python API) |
| SSL / TLS (server-terminated) | ✓ (serves `wss://` directly) | ✗ (use Tornado or a reverse proxy) |
| `MessageBusEventHandler.on()` emitter | ✓ | ✗ (Tornado-internal; not used externally) |
| Same `main()` hook signatures | ✓ | ✓ (drop-in) |

### Known limitations

* **`max_msg_size`** — the `websocket.max_msg_size` config key is silently
  ignored.  Use a reverse proxy (nginx, caddy) to enforce payload size limits
  if this matters in your deployment.
* **SSL** — this backend does not terminate TLS at the Python layer. To serve
  `wss://`, run the Tornado backend instead — it terminates TLS directly using
  the `websocket.ssl`, `websocket.ssl_cert`, and `websocket.ssl_key` config
  keys (generating a self-signed certificate under the XDG data directory
  when the cert/key are unset). Alternatively, terminate TLS at a reverse
  proxy (nginx, caddy) in front of this backend and forward plain WebSocket
  traffic.
* **`MessageBusEventHandler.on()` / `emitter`** — this Tornado-specific API
  allows other in-process code to subscribe to bus messages via the handler
  object.  It is not replicated by the webrockets backend because no external
  OVOS code calls it.

---

## ovos-rust-messagebus

A standalone Rust binary with zero Python overhead, developed by Oscillate
Labs.  It speaks the same OVOS WebSocket protocol on port 8181.

### Build

```bash
git clone https://github.com/OscillateLabsLLC/ovos-rust-messagebus
cd ovos-rust-messagebus
cargo build --release
./target/release/ovos-rust-messagebus
```

### Docker

```bash
docker build -t ovos-rust-messagebus .
docker run -p 8181:8181 ovos-rust-messagebus
```

### Configuration

Via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OVOS_BUS_HOST` | `0.0.0.0` | Bind address |
| `OVOS_BUS_PORT` | `8181` | TCP port |
| `OVOS_BUS_MAX_MSG_SIZE` | `25` MB | Maximum message payload size |

Or via a YAML/JSON config file pointed to by `OVOS_BUS_CONFIG_FILE`.

---

## Benchmark results

Measured on **localhost** (loopback, no network overhead) using
`benchmark/run_benchmark.py`.  A single sender publishes N messages; M
subscriber clients each receive every broadcast.  Throughput is total fan-out
deliveries per second (`N × M / elapsed`).  Latency is measured by embedding
a timestamp in each message and recording it at the receiver.

Machine: Linux 6.18.16-1-lts, Intel i7, CPython 3.11.14
Rust binary: `ovos-rust-messagebus` v1.1.2, compiled from source with `cargo build --release`

> **Methodology note**: Errors in the Rust results at 100 clients are WebSocket
> connection rejections at connect time (not delivery failures).  They affect the
> connection count but not the per-message latency of connections that succeeded.
> Results with ≥ 10 errors should be read with caution.

### 5 clients × 200 messages

| Backend | Throughput | Latency min | Latency median | p95 | p99 | Latency max | Dropped | Errors |
|---------|-----------|-------------|----------------|-----|-----|-------------|---------|--------|
| Tornado | 48,820 msg/s | 2.6 ms | 10.1 ms | 17.9 ms | 18.4 ms | 18.4 ms | 0 | 0 |
| webrockets | 54,103 msg/s | 6.7 ms | 10.7 ms | 14.7 ms | 15.1 ms | 15.2 ms | 0 | 0 |
| **Rust** | **57,770 msg/s** | 5.7 ms | **10.5 ms** | **14.5 ms** | **14.9 ms** | 14.9 ms | 0 | 0 |

### 20 clients × 1,000 messages

| Backend | Throughput | Latency min | Latency median | p95 | p99 | Latency max | Dropped | Errors |
|---------|-----------|-------------|----------------|-----|-----|-------------|---------|--------|
| Tornado | 65,937 msg/s | 12.9 ms | 136.9 ms | 280.9 ms | 291.3 ms | 293.4 ms | 0 | 0 |
| webrockets | 71,841 msg/s | 45.9 ms | 149.4 ms | 252.6 ms | 259.8 ms | 261.7 ms | 0 | 0 |
| **Rust** | **78,849 msg/s** | **31.1 ms** | **152.3 ms** | **230.4 ms** | **237.7 ms** | **239.4 ms** | 0 | 0 |

### 50 clients × 2,000 messages

| Backend | Throughput | Latency min | Latency median | p95 | p99 | Latency max | Dropped | Errors |
|---------|-----------|-------------|----------------|-----|-----|-------------|---------|--------|
| Tornado | 63,858 msg/s | 23.8 ms | 753.9 ms | 1430.3 ms | 1535.5 ms | 1548.6 ms | 0 | 0 |
| **webrockets** | **78,891 msg/s** | 143.3 ms | **740.5 ms** | **1196.4 ms** | **1236.3 ms** | **1245.9 ms** | 0 | 0 |
| Rust | 76,585 msg/s | 158.3 ms | 765.0 ms | 1228.5 ms | 1267.5 ms | 1276.0 ms | 0 | 0 |

### 100 clients × 500 messages

| Backend | Throughput | Latency min | Latency median | p95 | p99 | Latency max | Dropped | Errors |
|---------|-----------|-------------|----------------|-----|-----|-------------|---------|--------|
| Tornado | 74,154 msg/s | 11.1 ms | 360.4 ms | 640.5 ms | 666.0 ms | 670.0 ms | 0 | 0 |
| **webrockets** | **76,799 msg/s** | 120.3 ms | **369.9 ms** | **618.2 ms** | **639.6 ms** | **643.9 ms** | 0 | 0 |
| Rust ⚠ | 128,588 msg/s† | 21.2 ms | 31,562 ms | 31,765 ms | 31,785 ms | 31,792 ms | 0 | 28 |

† Throughput is inflated because 28 subscriber connections were rejected at
connect time, so denominator is over-counted.  Median latency of 31 s for
the 72 successful connections shows server saturation.

### Summary — Throughput vs Tornado baseline

```
  Scenario          Tornado       webrockets    Rust            Winner
  ─────────────────────────────────────────────────────────────────────
  5c × 200m       48,820/s      54,103/s      57,770/s        Rust  (+18%)
  20c × 1,000m    65,937/s      71,841/s      78,849/s        Rust  (+20%)
  50c × 2,000m    63,858/s      78,891/s      76,585/s        webrockets (+24%)
  100c × 500m     74,154/s      76,799/s      ⚠ 28 errors     webrockets (+4%)
```

### Summary — p99 latency (lower is better)

```
  Scenario          Tornado       webrockets    Rust
  ──────────────────────────────────────────────────────
  5c × 200m         18.4 ms       15.1 ms      14.9 ms  ← Rust best
  20c × 1,000m     291.3 ms      259.8 ms     237.7 ms  ← Rust best
  50c × 2,000m   1,535.5 ms    1,236.3 ms   1,267.5 ms  ← webrockets best
  100c × 500m      666.0 ms      639.6 ms     (unreliable)
```

### Observations

1. **Rust wins at low-to-medium concurrency** (5–20 clients): +18–20%
   throughput vs Tornado and +7–10% vs webrockets, with the lowest p99
   latency at every measured load in this range.

2. **webrockets wins at high concurrency** (50+ clients): +24% throughput
   vs Tornado at 50 clients, and best p99 tail latency.  The Rust binary
   begins to show connection-level saturation above ~50 simultaneous clients
   under the default configuration.

3. **Tornado's latency minimum is lowest** at low concurrency (2.6 ms at
   5 clients) — the pure-Python asyncio path has no FFI overhead.

4. **Rust connection saturation at 100 clients**: 28 out of 100 subscriber
   connections were rejected, causing 31-second median latency for survivors.
   The Rust server likely needs tuning (`--max-connections` or OS socket
   backlog) for > 50 concurrent clients.

5. **Zero message drops for Tornado and webrockets** at all tested loads.

6. **The Rust binary is the best choice** for typical OVOS deployments
   (1–20 concurrent components on a single host) where connections are
   long-lived.  For HiveMind satellite hubs with 50+ concurrent nodes,
   webrockets is currently more stable.

7. **Tornado remains a solid default**: pure-Python, no native extensions,
   well-understood asyncio scheduling, and lowest setup friction.

---

## Running the benchmark yourself

```bash
pip install "ovos-messagebus[benchmark]"

# 1. Start the server under test (one terminal):
ovos-messagebus                                         # Tornado
python -m ovos_messagebus.backends.webrockets_backend  # webrockets

# 2. Run the benchmark (another terminal):
python benchmark/run_benchmark.py --backend tornado --clients 20 --messages 1000

# Adjust load:
python benchmark/run_benchmark.py --clients 100 --messages 500

# Machine-readable output:
python benchmark/run_benchmark.py --json > results.json

# Compare all three (each must be on a different port):
python benchmark/run_benchmark.py --compare \
    --tornado-url    ws://localhost:8181/core \
    --webrockets-url ws://localhost:8182/core \
    --rust-url       ws://localhost:8183/core
```

### Benchmark methodology

* **Warmup phase**: `--warmup` messages (default 10) sent and received before
  measurement begins, ensuring JIT warm-up and connection pool readiness.
* **Timestamp embedding**: each message carries a `_bench_ts` float (Unix
  seconds from `time.perf_counter()`); latency = receive time − send time.
* **Fan-out accounting**: throughput counts every (sender → subscriber) pair
  delivery, not just messages sent.
* **Backpressure**: the sender sends all messages without waiting; the
  receivers drain concurrently.  Messages not received within `--timeout`
  seconds are counted as dropped.
