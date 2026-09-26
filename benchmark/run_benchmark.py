"""Benchmark script for OVOS messagebus implementations.

Measures throughput (messages/second) and latency (ms) for:
  - ovos-messagebus  Tornado/Python  (default)
  - ovos-messagebus  webrockets       (--backend webrockets)
  - ovos-rust-messagebus  Rust        (--backend rust, or any --url)

Usage
-----
# 1. Start the server under test first (in a separate terminal), e.g.:
#    ovos-messagebus                          # Tornado
#    python -m ovos_messagebus.backends.webrockets_backend
#    ./ovos-rust-messagebus                   # Rust binary

# 2. Run the benchmark:
    python benchmark/run_benchmark.py
    python benchmark/run_benchmark.py --clients 50 --messages 1000
    python benchmark/run_benchmark.py --url ws://localhost:8181/core --backend rust

# 3. Compare all three (servers must already be running on different ports):
    python benchmark/run_benchmark.py --compare \\
        --tornado-url  ws://localhost:8181/core \\
        --webrockets-url ws://localhost:8182/core \\
        --rust-url     ws://localhost:8183/core

Arguments
---------
--url        WebSocket URL to benchmark  [default: ws://localhost:8181/core]
--clients    Number of concurrent subscriber clients  [default: 20]
--messages   Number of messages to send in each test  [default: 500]
--warmup     Warmup messages sent before measurement  [default: 10]
--backend    Label for the server under test  [default: tornado]
--compare    Run comparison across --tornado-url, --webrockets-url, --rust-url
--timeout    Per-message receive timeout in seconds  [default: 5.0]
--json       Emit results as JSON (stdout)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from typing import List, Optional

import websockets  # pip install websockets


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkResult:
    backend: str
    url: str
    num_clients: int
    num_messages: int
    total_time_s: float
    throughput_msg_per_s: float
    latency_min_ms: float
    latency_median_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_max_ms: float
    dropped_messages: int
    errors: int


# ---------------------------------------------------------------------------
# Benchmark logic
# ---------------------------------------------------------------------------

async def _connect_subscriber(url: str, timeout: float) -> websockets.WebSocketClientProtocol:
    """Open a WebSocket connection and discard the initial 'connected' greeting."""
    ws = await asyncio.wait_for(websockets.connect(url), timeout=timeout)
    try:
        await asyncio.wait_for(ws.recv(), timeout=timeout)  # 'connected' msg
    except asyncio.TimeoutError:
        pass
    return ws


async def _receive_all(
    ws: websockets.WebSocketClientProtocol,
    expected: int,
    timeout: float,
    latencies: list,
) -> int:
    """Receive *expected* messages and record per-message latencies (ms)."""
    received = 0
    while received < expected:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            break
        try:
            data = json.loads(raw)
            sent_at = data.get("data", {}).get("_bench_ts")
            if sent_at is not None:
                latencies.append((time.perf_counter() - sent_at) * 1000)
        except Exception:
            pass
        received += 1
    return received


async def run_benchmark(
    url: str,
    backend: str,
    num_clients: int,
    num_messages: int,
    warmup: int,
    timeout: float,
) -> BenchmarkResult:
    """Run a single benchmark pass and return a :class:`BenchmarkResult`."""
    errors = 0

    # ---- connect all subscribers ----------------------------------------
    subscribers: List[websockets.WebSocketClientProtocol] = []
    for _ in range(num_clients):
        try:
            ws = await _connect_subscriber(url, timeout)
            subscribers.append(ws)
        except Exception as exc:
            print(f"  [WARN] subscriber connect failed: {exc}", file=sys.stderr)
            errors += 1

    if not subscribers:
        raise RuntimeError("No subscriber connections established.")

    # ---- connect sender -------------------------------------------------
    sender = await _connect_subscriber(url, timeout)

    # ---- warmup ---------------------------------------------------------
    for _ in range(warmup):
        msg = json.dumps({"msg_type": "bench.warmup", "data": {}, "context": {}})
        await sender.send(msg)
    # drain warmup messages from subscribers
    warmup_tasks = [
        asyncio.create_task(_receive_all(s, warmup, timeout, []))
        for s in subscribers
    ]
    await asyncio.gather(*warmup_tasks, return_exceptions=True)

    # ---- measured run ---------------------------------------------------
    latencies: list = []
    dropped = 0

    async def _receive_measured(ws):
        lats: list = []
        r = await _receive_all(ws, num_messages, timeout, lats)
        return r, lats

    receive_tasks = [
        asyncio.create_task(_receive_measured(s))
        for s in subscribers
    ]

    t_start = time.perf_counter()
    for i in range(num_messages):
        ts = time.perf_counter()
        msg = json.dumps({
            "msg_type": "bench.ping",
            "data": {"_bench_ts": ts, "seq": i},
            "context": {"source": ["benchmark"]},
        })
        await sender.send(msg)

    results = await asyncio.gather(*receive_tasks, return_exceptions=True)
    t_end = time.perf_counter()

    for res in results:
        if isinstance(res, Exception):
            errors += 1
        else:
            received_count, lats = res
            dropped += num_messages - received_count
            latencies.extend(lats)

    # ---- cleanup --------------------------------------------------------
    await sender.close()
    for ws in subscribers:
        try:
            await ws.close()
        except Exception:
            pass

    # ---- compute stats --------------------------------------------------
    total_time = t_end - t_start
    total_expected = num_messages * num_clients
    throughput = (total_expected - dropped) / total_time if total_time > 0 else 0.0

    if latencies:
        lat_sorted = sorted(latencies)
        n = len(lat_sorted)
        p95_idx = int(0.95 * n)
        p99_idx = int(0.99 * n)
        return BenchmarkResult(
            backend=backend,
            url=url,
            num_clients=num_clients,
            num_messages=num_messages,
            total_time_s=round(total_time, 3),
            throughput_msg_per_s=round(throughput, 1),
            latency_min_ms=round(min(lat_sorted), 3),
            latency_median_ms=round(statistics.median(lat_sorted), 3),
            latency_p95_ms=round(lat_sorted[p95_idx], 3),
            latency_p99_ms=round(lat_sorted[p99_idx], 3),
            latency_max_ms=round(max(lat_sorted), 3),
            dropped_messages=dropped,
            errors=errors,
        )
    else:
        return BenchmarkResult(
            backend=backend,
            url=url,
            num_clients=num_clients,
            num_messages=num_messages,
            total_time_s=round(total_time, 3),
            throughput_msg_per_s=round(throughput, 1),
            latency_min_ms=0.0,
            latency_median_ms=0.0,
            latency_p95_ms=0.0,
            latency_p99_ms=0.0,
            latency_max_ms=0.0,
            dropped_messages=dropped,
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_result(r: BenchmarkResult) -> None:
    bar = "─" * 60
    print(f"\n{bar}")
    print(f"  Backend  : {r.backend}")
    print(f"  URL      : {r.url}")
    print(f"  Clients  : {r.num_clients}  |  Messages : {r.num_messages}")
    print(f"{bar}")
    print(f"  Throughput      : {r.throughput_msg_per_s:>10,.1f} msg/s")
    print(f"  Total time      : {r.total_time_s:>10.3f} s")
    print(f"  Latency min     : {r.latency_min_ms:>10.3f} ms")
    print(f"  Latency median  : {r.latency_median_ms:>10.3f} ms")
    print(f"  Latency p95     : {r.latency_p95_ms:>10.3f} ms")
    print(f"  Latency p99     : {r.latency_p99_ms:>10.3f} ms")
    print(f"  Latency max     : {r.latency_max_ms:>10.3f} ms")
    print(f"  Dropped msgs    : {r.dropped_messages:>10}")
    print(f"  Errors          : {r.errors:>10}")
    print(f"{bar}")


def _print_comparison(results: list[BenchmarkResult]) -> None:
    if len(results) < 2:
        return
    print("\n" + "═" * 80)
    print("  COMPARISON SUMMARY")
    print("═" * 80)
    header = f"  {'Backend':<18} {'Throughput':>14} {'Median lat':>12} {'p99 lat':>10} {'Dropped':>10}"
    print(header)
    print("  " + "─" * 66)
    for r in results:
        print(
            f"  {r.backend:<18} "
            f"{r.throughput_msg_per_s:>12,.1f}/s "
            f"{r.latency_median_ms:>11.3f}ms "
            f"{r.latency_p99_ms:>9.3f}ms "
            f"{r.dropped_messages:>10}"
        )

    # relative speedup vs first result (Tornado baseline)
    baseline = results[0]
    if baseline.throughput_msg_per_s > 0:
        print()
        print(f"  Speedup relative to {baseline.backend}:")
        for r in results[1:]:
            ratio = r.throughput_msg_per_s / baseline.throughput_msg_per_s
            print(f"    {r.backend}: {ratio:.2f}×")
    print("═" * 80)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Benchmark OVOS messagebus implementations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--url", default="ws://localhost:8181/core",
                   help="WebSocket URL to benchmark")
    p.add_argument("--backend", default="tornado",
                   help="Label for the server under test")
    p.add_argument("--clients", type=int, default=20,
                   help="Number of concurrent subscriber clients")
    p.add_argument("--messages", type=int, default=500,
                   help="Number of messages to send per test run")
    p.add_argument("--warmup", type=int, default=10,
                   help="Warmup messages (not measured)")
    p.add_argument("--timeout", type=float, default=5.0,
                   help="Per-message receive timeout (seconds)")
    p.add_argument("--json", action="store_true",
                   help="Emit results as JSON on stdout")
    p.add_argument("--compare", action="store_true",
                   help="Run comparison across all three backends")
    p.add_argument("--tornado-url",   default="ws://localhost:8181/core")
    p.add_argument("--webrockets-url", default="ws://localhost:8182/core")
    p.add_argument("--rust-url",      default="ws://localhost:8183/core")
    return p.parse_args()


async def _async_main(args: argparse.Namespace) -> None:
    all_results: list[BenchmarkResult] = []

    if args.compare:
        targets = [
            ("tornado",    args.tornado_url),
            ("webrockets", args.webrockets_url),
            ("rust",       args.rust_url),
        ]
        for backend, url in targets:
            print(f"\n→ Benchmarking {backend} at {url} …")
            try:
                r = await run_benchmark(
                    url=url,
                    backend=backend,
                    num_clients=args.clients,
                    num_messages=args.messages,
                    warmup=args.warmup,
                    timeout=args.timeout,
                )
                _print_result(r)
                all_results.append(r)
            except Exception as exc:
                print(f"  [ERROR] {backend}: {exc}", file=sys.stderr)
        _print_comparison(all_results)
    else:
        r = await run_benchmark(
            url=args.url,
            backend=args.backend,
            num_clients=args.clients,
            num_messages=args.messages,
            warmup=args.warmup,
            timeout=args.timeout,
        )
        _print_result(r)
        all_results.append(r)

    if args.json:
        print(json.dumps([asdict(r) for r in all_results], indent=2))


def main() -> None:
    args = _parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
