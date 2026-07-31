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

Every message is a JSON-serialized `Message(type, data, context)` object. The bus does not filter or route messages. It broadcasts each message to every connected client.

---

## Running the server

Start the server from the installed entry point:

```bash
ovos-messagebus
```

Or run it as a module:

```bash
python -m ovos_messagebus
```

The server reads its connection settings from `mycroft.conf` (the `websocket` section), then starts listening. It blocks until it receives a shutdown signal.

---

## Configuration

The server reads its configuration from `mycroft.conf` under the `websocket` key:

| Key | Default | Description |
|---|---|---|
| `host` | `0.0.0.0` | Bind address |
| `port` | `8181` | TCP port |
| `route` | `/core` | WebSocket URL path |
| `ssl` | `False` | Enable SSL/TLS (the Tornado backend serves `wss://` directly) |
| `ssl_cert` / `ssl_key` | unset | PEM cert/key paths. The server generates a self-signed pair when unset (`ssl` extra) |
| `max_msg_size` | `10` | Maximum message size in MB |

Example `mycroft.conf` section:

```json
{
  "websocket": {
    "host": "0.0.0.0",
    "port": 8181,
    "route": "/core",
    "ssl": false,
    "ssl_cert": "",
    "ssl_key": "",
    "max_msg_size": 10
  }
}
```

---

## Package layout

```
ovos_messagebus/
├── __init__.py
├── __main__.py              # Entry point: main(), the Tornado backend
├── event_handler.py         # MessageBusEventHandler (Tornado WebSocketHandler)
├── load_config.py           # load_message_bus_config() → MessageBusConfig
└── backends/
    ├── __init__.py
    └── webrockets_backend.py  # Optional Rust-powered backend (pip install ovos-messagebus[webrockets])

benchmark/
└── run_benchmark.py         # Throughput & latency benchmark (pip install ovos-messagebus[benchmark])
```

---

## Further reading

- [Server](server.md): `MessageBusEventHandler`, `load_message_bus_config`, `main()`
- [Configuration](configuration.md): full `mycroft.conf["websocket"]` reference: host, port, route, ssl, ssl_cert, ssl_key, max_msg_size, filter, filter_logs
- [Events](events.md): message types that flow through the bus and which services publish and consume them
- [Backends & Benchmarks](backends.md): the webrockets and Rust backends, measured throughput and latency results, and how to run comparisons

---

## Services that connect to the bus

Every OVOS service connects to the bus as a client through [ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client). The bus itself does not know about these services. It just broadcasts every message to every connected client.

| Service | Role |
|---|---|
| [ovos-core](https://github.com/OpenVoiceOS/ovos-core) | Intent pipeline, skill orchestration |
| [ovos-audio](https://github.com/OpenVoiceOS/ovos-audio) | TTS rendering and audio playback |
| [ovos-gui](https://github.com/OpenVoiceOS/ovos-gui) | GUI namespace management. It bridges skills to GUI clients |
| [ovos-dinkum-listener](https://github.com/OpenVoiceOS/ovos-dinkum-listener) | Wake word detection and STT transcription |
| [ovos-PHAL](https://github.com/OpenVoiceOS/ovos-PHAL) | Hardware abstraction layer (connectivity, audio hardware, etc.) |
| [ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client) | Client library used by all services and skills |
| [ovos-workshop](https://github.com/OpenVoiceOS/ovos-workshop) | Skill base classes (indirectly through ovos-bus-client) |

GUI clients (for example `ovos-shell`, `pyhtmx-gui-client`) connect to `ovos-gui`'s own WebSocket (`ws://localhost:18181/gui`), not directly to the messagebus.
