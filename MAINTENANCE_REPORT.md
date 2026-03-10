
# Maintenance Report — `ovos-messagebus`

## [2026-03-10] — webrockets backend + benchmark tooling

### Transparency Report (AI-assisted)
- **Model**: claude-sonnet-4-6
- **Actions taken**:
  1. Created `ovos_messagebus/backends/__init__.py` — package marker.
  2. Created `ovos_messagebus/backends/webrockets_backend.py` — optional
     Rust-powered WebSocket backend using the `webrockets` library.  Implements
     identical OVOS fan-out semantics via a single broadcast room.
  3. Created `benchmark/run_benchmark.py` — asyncio benchmark script measuring
     throughput and latency against any WebSocket server; supports `--compare`
     mode to test Tornado, webrockets, and ovos-rust-messagebus side by side.
  4. Updated `pyproject.toml` — added `[webrockets]` and `[benchmark]` optional
     dependency groups.
  5. Updated `FAQ.md` — "Alternative backends & benchmarking" section with
     setup instructions, architecture notes, and comparison table.
- **Human oversight level**: full review required before merging; no tests were
  written for the new backend because `webrockets` is not installed in the dev
  environment — integration tests should be added after install is confirmed.

---

## [2026-03-08] — Initial compliance scaffold

### Changes
- Created `QUICK_FACTS.md` with machine-readable package metadata.
- Created `FAQ.md` with common Q&A.
- Created `MAINTENANCE_REPORT.md` (this file) as the change log.
- Created `SUGGESTIONS.md` with initial improvement proposals.
- Created `docs/index.md` as the documentation entry point (if missing).

### Rationale
Establishing the required file set mandated by `AGENTS.md` for all active workspace repositories.

### Verification
- All required files exist at repo root and `docs/` folder.
- No existing content was overwritten.

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Generated boilerplate compliance scaffold (QUICK_FACTS, FAQ, MAINTENANCE_REPORT, SUGGESTIONS, docs/index).
- **Oversight**: Files are stubs — human review and enrichment required before treating as authoritative.

---

## 2026-03-10 — Benchmark run: Tornado vs webrockets

### Summary
Executed live benchmarks for both available backends (Tornado and webrockets)
at four load levels.  Updated `docs/backends.md` with fresh measurements and
expanded `FAQ.md` with a benchmark Q&A section.

### Results
| Scenario | Tornado | webrockets | Δ throughput |
|----------|---------|------------|--------------|
| 5c × 200m | 48,820 msg/s | 54,103 msg/s | +11% |
| 20c × 1,000m | 65,937 msg/s | 71,841 msg/s | +9% |
| 50c × 2,000m | 63,858 msg/s | 78,891 msg/s | +24% |
| 100c × 500m | 74,154 msg/s | 76,799 msg/s | +4% |

Zero message drops at all load levels.

### Files changed
- `docs/backends.md` — updated benchmark tables with min/p95/p99/max columns
- `FAQ.md` — added "What do the actual benchmark numbers look like?" and
  "Why does webrockets have a higher latency minimum?" Q&As

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Started Tornado and webrockets servers, ran `benchmark/run_benchmark.py` at four load levels for each backend, updated docs with measured results and analysis.
- **Oversight**: All numbers are from live benchmark runs on this machine (Linux 6.18.16-1-lts, Intel i7, CPython 3.11.14).  The Rust binary (ARM target) was identified but could not execute on x86-64.

---

## 2026-03-10 (2) — Rust backend benchmarked: compiled from source

### Summary
Installed Rust toolchain via rustup, cloned OscillateLabsLLC/ovos-rust-messagebus,
compiled with `cargo build --release`, started on port 8183, and ran the same
four benchmark scenarios.

### Results (all three backends)

| Scenario | Tornado | webrockets | Rust |
|----------|---------|------------|------|
| 5c × 200m throughput | 48,820/s | 54,103/s | **57,770/s** (+18%) |
| 20c × 1000m throughput | 65,937/s | 71,841/s | **78,849/s** (+20%) |
| 50c × 2000m throughput | 63,858/s | **78,891/s** | 76,585/s |
| 100c × 500m | 74,154/s | **76,799/s** | ⚠ 28 conn errors |
| 20c p99 latency | 291.3 ms | 259.8 ms | **237.7 ms** |

### Key findings
- Rust wins at 5–20 clients; webrockets wins at 50+ clients
- Rust shows TCP accept-queue saturation at 100 concurrent WS connections
- Zero drops for Tornado and webrockets at all load levels

### Files changed
- `docs/backends.md` — added Rust column to all tables, updated summary and observations
- `FAQ.md` — added Rust connection saturation FAQ
- `MAINTENANCE_REPORT.md` — this entry

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Installed rustup, cloned and compiled ovos-rust-messagebus v1.1.2, ran benchmark at 4 scenarios, updated docs with live measurements.
- **Oversight**: All numbers are live measurements on this machine. Rust binary source: github.com/OscillateLabsLLC/ovos-rust-messagebus.
