# OVOS MessageBus

`ovos-messagebus` is the WebSocket message bus server for OpenVoiceOS. Every OVOS service connects to this bus and exchanges `Message` objects with it. The bus does not route or filter messages. It broadcasts each message to every connected client.

## Install

```bash
pip install ovos-messagebus
```

## Usage

Start the server from the command line:

```bash
ovos-messagebus
```

Or run it as a module:

```bash
python -m ovos_messagebus
```

The server reads its connection settings from `mycroft.conf` under the `websocket` key:

```javascript
{
  // The mycroft-core messagebus websocket
  "websocket": {
    "host": "0.0.0.0",
    "port": 8181,
    "route": "/core",
    "ssl": false,
    // in mycroft-core all skills share a bus, this allows malicious skills
    // to manipulate it and affect other skills, this option ensures each skill
    // gets its own websocket connection
    "shared_connection": true,
    // filter out messages of certain types from the bus logs
    "filter": false,
    // which messages to filter if filter is enabled
    "filter_logs": ["gui.status.request", "gui.page.upload"]
  }
}
```

See [docs/configuration.md](docs/configuration.md) for the full list of options, [docs/server.md](docs/server.md) for the server internals, and [docs/events.md](docs/events.md) for the message types that flow through the bus.

## Alternative implementations

- [ovos-rust-messagebus](https://github.com/OscillateLabsLLC/ovos-rust-messagebus): alternative Rust messagebus server implementation.
- [ovos-messagebus-cpp](https://github.com/OpenVoiceOS/ovos-messagebus-cpp): alternative C++ messagebus server implementation using WebSocket++ (archived).

`ovos-messagebus` also ships an optional Rust-powered backend (`webrockets`) alongside its default Tornado backend. See [docs/backends.md](docs/backends.md) for setup and benchmark results.

## Related projects

- [ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client): the client library all services and skills use to connect to this bus.
- [ovos-core](https://github.com/OpenVoiceOS/ovos-core): intent pipeline and skill orchestration. It connects to this bus as a client.
- [ovos-audio](https://github.com/OpenVoiceOS/ovos-audio): TTS rendering and audio playback. It connects to this bus as a client.
- [ovos-gui](https://github.com/OpenVoiceOS/ovos-gui): GUI namespace management. It bridges skills to GUI clients over this bus.
- [ovos-dinkum-listener](https://github.com/OpenVoiceOS/ovos-dinkum-listener): wake word detection and STT transcription. It connects to this bus as a client.
- [ovos-PHAL](https://github.com/OpenVoiceOS/ovos-PHAL): the hardware abstraction layer. It connects to this bus as a client.

## License

Apache-2.0. See [LICENSE](LICENSE).
