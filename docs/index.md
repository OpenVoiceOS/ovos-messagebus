
# ovos-messagebus

`ovos-messagebus` is the WebSocket message bus server for OpenVoiceOS. All OVOS services communicate by publishing and subscribing to typed `Message` objects through this central broker.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              ovos-messagebus                │
│                                             │
│  Tornado IOLoop (daemon thread)             │
│  ┌──────────────────────────────────────┐   │
│  │  web.Application                    │   │
│  │  route: /core  (configurable)       │   │
│  │                                     │   │
│  │  MessageBusEventHandler             │   │
│  │  (WebSocketHandler)                 │   │
│  │  ┌──────────────────────────────┐   │   │
│  │  │  client_connections: set     │   │   │
│  │  │  Fan-out broadcast           │   │   │
│  │  └──────────────────────────────┘   │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
         │           │           │
    ovos-core   ovos-audio   ovos-skills
    (clients via ovos-bus-client)
```

All messages are JSON-serialized `Message(type, data, context)` objects. The bus performs no filtering or routing — every message is broadcast to every connected client.

---

## Running the Server

```bash
python -m ovos_messagebus
```

Or via the installed entry point:

```bash
ovos-messagebus
```

The server reads connection parameters from `mycroft.conf` (`websocket` section) and starts listening. It blocks until a shutdown signal is received.

---

## Configuration

Configuration is read from `mycroft.conf` under the `websocket` key:

| Key | Default | Description |
|---|---|---|
| `host` | `0.0.0.0` | Bind address |
| `port` | `8181` | TCP port |
| `route` | `/core` | WebSocket URL path |
| `ssl` | `False` | Enable SSL/TLS |
| `max_msg_size` | `10` | Maximum message size in MB |

Example `mycroft.conf` section:

```json
{
  "websocket": {
    "host": "0.0.0.0",
    "port": 8181,
    "route": "/core",
    "ssl": false,
    "max_msg_size": 10
  }
}
```

---

## Package Layout

```
ovos_messagebus/
├── __init__.py
├── __main__.py              # Entry point: main() — Tornado backend
├── event_handler.py         # MessageBusEventHandler (Tornado WebSocketHandler)
├── load_config.py           # load_message_bus_config() → MessageBusConfig
└── backends/
    ├── __init__.py
    └── webrockets_backend.py  # Optional Rust-powered backend (pip install ovos-messagebus[webrockets])

benchmark/
└── run_benchmark.py         # Throughput & latency benchmark (pip install ovos-messagebus[benchmark])
```

---

## Further Reading

- [Server](server.md) — `MessageBusEventHandler`, `load_message_bus_config`, `main()`
- [Configuration](configuration.md) — Full `mycroft.conf["websocket"]` reference: host, port, route, ssl, max_msg_size, filter, filter_logs
- [Events](events.md) — Message types that flow through the bus and which services publish/consume them
- [Backends & Benchmarks](backends.md) — webrockets and Rust backends, measured throughput/latency results, how to run comparisons

---

## Services That Connect to the Bus

Every OVOS service connects to the bus as a client via [ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client). The bus itself does not know about these services — it simply broadcasts every message to every connected client.

| Service | Role |
|---|---|
| [ovos-core](https://github.com/OpenVoiceOS/ovos-core) | Intent pipeline, skill orchestration |
| [ovos-audio](https://github.com/OpenVoiceOS/ovos-audio) | TTS rendering and audio playback |
| [ovos-gui](https://github.com/OpenVoiceOS/ovos-gui) | GUI namespace management; bridges skills to GUI clients |
| [ovos-dinkum-listener](https://github.com/OpenVoiceOS/ovos-dinkum-listener) | Wake word detection and STT transcription |
| [ovos-PHAL](https://github.com/OpenVoiceOS/ovos-PHAL) | Hardware abstraction layer (connectivity, audio hardware, etc.) |
| [ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client) | Client library used by all services and skills |
| [ovos-workshop](https://github.com/OpenVoiceOS/ovos-workshop) | Skill base classes (indirectly via ovos-bus-client) |

GUI clients (e.g. `ovos-shell`, `pyhtmx-gui-client`) connect to `ovos-gui`'s own WebSocket (`ws://localhost:18181/gui`), not directly to the messagebus.
