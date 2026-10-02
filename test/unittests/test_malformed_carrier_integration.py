# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Integration test for OVOS-SESSION-1 §2.5: the messagebus server drops a
Message whose `context.session` is a malformed carrier (present but not a
JSON object) instead of relaying it, and broadcasts a single
`ovos.session.rejected` Message in its place."""
import json
import socket
import threading
import time
import unittest
from collections import namedtuple

import websocket
from ovos_bus_client.client import MessageBusClient
from ovos_bus_client.message import Message

from ovos_messagebus.__main__ import _run_bus
from ovos_messagebus.event_handler import MessageBusEventHandler

FakeConfig = namedtuple('FakeConfig', ['host', 'port', 'route', 'ssl'])

# valid JSON whose top level is not an object, so json.loads does not
# return a dict for any of them
NON_OBJECT_JSON_FRAMES = ["[1, 2]", '"hello"', "42", "true", "null"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestMalformedCarrierIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        cls.config = FakeConfig(host="127.0.0.1", port=cls.port,
                                 route="/core", ssl=False)
        cls.server_thread = threading.Thread(
            target=_run_bus, args=(cls.config,), daemon=True)
        cls.server_thread.start()
        # wait for the server to accept connections
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("messagebus server did not start")

    def _new_client(self) -> MessageBusClient:
        client = MessageBusClient(host=self.config.host, port=self.port,
                                   route=self.config.route, ssl=False)
        client.run_in_thread()
        client.connected_event.wait(10)
        return client

    def _new_raw_ws(self) -> websocket.WebSocket:
        ws = websocket.WebSocket()
        ws.connect(f"ws://{self.config.host}:{self.port}{self.config.route}")
        return ws

    def test_single_malformed_frame_yields_one_rejection(self):
        client_b = self._new_client()
        received = []
        rejections = []
        client_b.on("ovos.utterance.handle", lambda m: received.append(m))
        client_b.on("ovos.session.rejected", lambda m: rejections.append(m))
        try:
            ws_a = self._new_raw_ws()
            try:
                payload = json.dumps({
                    "type": "ovos.utterance.handle",
                    "data": {"utterances": ["hello"]},
                    "context": {"session": "not-an-object",
                                "utterance_id": "u-1"}
                })
                ws_a.send(payload)
                time.sleep(1)

                self.assertEqual(len(rejections), 1)
                rejected = rejections[0]
                self.assertEqual(rejected.data["msg_type"], "ovos.utterance.handle")
                self.assertEqual(rejected.data["reason"], "malformed_carrier")
                self.assertEqual(rejected.context.get("utterance_id"), "u-1")
                self.assertNotIn("session", rejected.context)
                self.assertEqual(len(received), 0)

                # both connections remain usable after the drop
                self.assertTrue(ws_a.connected)
                ws_a.send(Message("ping").serialize())
            finally:
                ws_a.close()
        finally:
            client_b.close()

    def test_hundred_malformed_frames_no_crash(self):
        client_b = self._new_client()
        rejections = []
        client_b.on("ovos.session.rejected", lambda m: rejections.append(m))
        try:
            ws_a = self._new_raw_ws()
            try:
                for i in range(100):
                    payload = json.dumps({
                        "type": "test.malformed",
                        "data": {},
                        "context": {"session": i}
                    })
                    ws_a.send(payload)
                time.sleep(2)
                self.assertEqual(len(rejections), 100)
                self.assertTrue(ws_a.connected)
            finally:
                ws_a.close()
        finally:
            client_b.close()


    def _assert_not_session_rejection(self, raw_frame):
        parsed = json.loads(raw_frame)
        if isinstance(parsed, dict) and \
                parsed.get("type") == "ovos.session.rejected":
            self.fail(f"unexpected ovos.session.rejected frame: {raw_frame}")

    def test_non_object_json_frames_relay_and_connection_survives(self):
        ws_b = self._new_raw_ws()
        ws_b.settimeout(5)
        self.assertEqual(json.loads(ws_b.recv())["type"], "connected")
        ws_a = self._new_raw_ws()
        ws_a.settimeout(5)
        self.assertEqual(json.loads(ws_a.recv())["type"], "connected")
        try:
            for i, frame in enumerate(NON_OBJECT_JSON_FRAMES):
                with self.subTest(frame=frame):
                    ws_a.send(frame)
                    relayed_to_b = ws_b.recv()
                    relayed_to_a = ws_a.recv()
                    self.assertEqual(relayed_to_b, frame)
                    self.assertEqual(relayed_to_a, frame)
                    self._assert_not_session_rejection(relayed_to_b)
                    self._assert_not_session_rejection(relayed_to_a)
                    # a well-formed frame on the same socket still relays
                    followup = Message(f"nonobject.roundtrip.{i}",
                                       data={"n": i}).serialize()
                    ws_a.send(followup)
                    self.assertEqual(ws_b.recv(), followup)
                    self.assertEqual(ws_a.recv(), followup)
        finally:
            ws_a.close()
            ws_b.close()


class TestNonObjectCarrierGuard(unittest.TestCase):
    """The carrier guard treats valid non-object JSON as not rejected."""

    def test_guard_returns_false_for_non_object_json(self):
        for frame in NON_OBJECT_JSON_FRAMES:
            with self.subTest(frame=frame):
                rejected = MessageBusEventHandler._reject_malformed_carrier(
                    None, frame)
                self.assertFalse(rejected)


if __name__ == '__main__':
    unittest.main()
