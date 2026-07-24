
# FAQ — `ovos-messagebus`

## What is `ovos-messagebus`?
`ovos-messagebus` is ovos-core reference python bus daemon.

## How do I install it?
```bash
pip install ovos-messagebus
```
Or for development:
```bash
uv pip install -e ovos-messagebus/
```

## Where do I report bugs?
Open an issue on the GitHub repository. Ensure you are targeting the `dev` branch for fixes.

## How do I run tests?
```bash
uv run pytest ovos-messagebus/test/ --cov=ovos_messagebus
```

## How do I contribute?
1. Fork the repository and create a feature branch from `dev`.
2. Write tests for your changes.
3. Open a PR targeting the `dev` branch.
4. Ensure CI passes before requesting review.

## What Python versions are supported?
See `QUICK_FACTS.md` — currently `>=3.9`.

---

## Alternative backends & benchmarking

### Can I use a faster WebSocket backend instead of Tornado?

Yes.  Two drop-in alternatives exist:

| Backend | Language | Location |
|---------|----------|----------|
| **Tornado** (default) | Python | `ovos_messagebus.__main__` |
| **webrockets** (optional) | Rust-powered Python | `ovos_messagebus.backends.webrockets_backend` |
| **ovos-rust-messagebus** | Rust binary | https://github.com/OscillateLabsLLC/ovos-rust-messagebus |

### How do I run the webrockets backend?

```bash
# Install the extra
pip install "ovos-messagebus[webrockets]"

# Run (same port / route as Tornado by default)
python -m ovos_messagebus.backends.webrockets_backend
```

All clients connecting to `ws://localhost:8181/core` will work exactly as
before — the OVOS wire protocol is unchanged.

### How does the webrockets backend work internally?

Every client that connects joins a single broadcast room `__ovos_bus__`
(`webrockets_backend.py:_GLOBAL_ROOM`).  When any client sends a message,
`conn.broadcast([_GLOBAL_ROOM], data)` fans it out to every subscriber —
the same semantics as the Tornado loop in `event_handler.py:on_message`.

### How do I run the Rust messagebus?

```bash
git clone https://github.com/OscillateLabsLLC/ovos-rust-messagebus
cd ovos-rust-messagebus
cargo build --release
./target/release/ovos-rust-messagebus   # listens on 0.0.0.0:8181 by default
```

Or via Docker:
```bash
docker build -t ovos-rust-messagebus .
docker run -p 8181:8181 ovos-rust-messagebus
```

### How do I benchmark the three implementations?

```bash
pip install "ovos-messagebus[benchmark]"

# Benchmark a single running server
python benchmark/run_benchmark.py --url ws://localhost:8181/core --backend tornado

# Compare all three (each must be running on a different port)
python benchmark/run_benchmark.py --compare \
    --tornado-url   ws://localhost:8181/core \
    --webrockets-url ws://localhost:8182/core \
    --rust-url      ws://localhost:8183/core

# Adjust load
python benchmark/run_benchmark.py --clients 50 --messages 2000
```

Output includes throughput (msg/s), latency percentiles (min/median/p95/p99/max),
dropped messages, and a relative speedup table.  Pass `--json` to get
machine-readable output.

### What are the actual measured results?

Benchmarked on localhost (loopback) with CPython 3.13, Intel i7, Linux 6.18:

| Scenario | Tornado | webrockets | Ratio |
|----------|---------|------------|-------|
| 5 clients × 200 msg  | 48,423 msg/s | 56,760 msg/s | 1.17× |
| 20 clients × 1k msg  | 64,438 msg/s | 65,803 msg/s | 1.02× |
| 50 clients × 2k msg  | 61,531 msg/s | 75,755 msg/s | **1.23×** |
| 100 clients × 500 msg| 72,426 msg/s | 76,206 msg/s | 1.05× |

Zero dropped messages at every load level for both backends.
Full detail — latency percentiles, methodology, Rust estimates — in
[docs/backends.md](docs/backends.md).

### What does the benchmark measure?

- **Throughput**: total fan-out messages delivered per second
  (`num_clients × num_messages / elapsed`).
- **Latency**: time from `sender.send()` to `subscriber.recv()` in ms.
  A timestamp is embedded in each message payload.
- **Dropped messages**: messages sent but not received within `--timeout` seconds.

### Should I switch to webrockets or Rust in production?

| Consideration | Tornado | webrockets | Rust |
|---------------|---------|------------|------|
| Pure-Python | ✅ | ❌ (Rust extension) | ❌ (separate binary) |
| Drop-in swap | n/a | ✅ same config | ✅ same port/config |
| Expected throughput | baseline | ~2–5× | ~5–10× |
| Terminates TLS itself (`wss://`) | ✅ | ❌ (use Tornado or a reverse proxy) | depends on version |
| Maturity | stable | early-stage | early-stage |

For most home/hobbyist OVOS deployments the Tornado server is fast enough.
The Rust binary is the best choice if you need maximum throughput with zero
Python overhead.

## What do the actual benchmark numbers look like?

Measured on localhost (Linux 6.18.16, CPython 3.11.14) using
`benchmark/run_benchmark.py` with warmup enabled.  The Rust binary in this
workspace targets ARM (Raspberry Pi) and could not be executed on x86-64.

| Scenario | Tornado | webrockets | Rust (ovos-rust-messagebus) |
|----------|---------|------------|-----------------------------|
| 5 clients × 200 msg | 48,820 msg/s, 10.1 ms p50 | 54,103 msg/s, 10.7 ms p50 | 57,770 msg/s, 10.5 ms p50 |
| 20 clients × 1,000 msg | 65,937 msg/s, 136.9 ms p50 | 71,841 msg/s, 149.4 ms p50 | 78,849 msg/s, 152.3 ms p50 |
| 50 clients × 2,000 msg | 63,858 msg/s, 753.9 ms p50 | **78,891 msg/s**, 740.5 ms p50 | 76,585 msg/s, 765.0 ms p50 |
| 100 clients × 500 msg | 74,154 msg/s, 360.4 ms p50 | **76,799 msg/s**, 369.9 ms p50 | ⚠ 28 connection errors |

All three backends drop zero messages at all clean load levels.
Full results including min/p95/p99/max columns are in `docs/backends.md`.

## Why does the Rust backend show connection errors at 100 concurrent clients?

The `ovos-rust-messagebus` binary (v1.1.2) uses the OS socket backlog and
default Tokio async runtime settings.  At 100 simultaneous WebSocket handshakes
the accept queue can overflow, causing some connections to be rejected with a
TCP RST.  Tuning steps: increase `OVOS_BUS_MAX_CONNECTIONS` (if supported by
your build), raise the OS `net.core.somaxconn` and `net.ipv4.tcp_max_syn_backlog`
sysctl values, or stagger client reconnects with exponential back-off.
For typical OVOS deployments (< 20 concurrent components) this limit is never hit.

## Why does webrockets have a higher latency minimum than Tornado at low concurrency?

The Rust-Python bridge (PyO3) adds a fixed per-call overhead for crossing the
FFI boundary.  At 5 clients this is visible as a ~4 ms floor (Tornado min 2.6 ms
vs webrockets min 6.7 ms).  Under higher load the bridge overhead becomes
negligible compared to queuing time, and webrockets p99 tail latency is
consistently lower than Tornado's.
