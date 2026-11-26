"""Offline unit tests for strictly read-only SSDP LAN printer discovery."""
import socket
import unittest

from kobra_lan import discovery as d


def _reply(
    *,
    status="HTTP/1.1 200 OK",
    st="ac:3dprinter:fdm",
    usn="uuid:fdm:02-00-00-00-00-01",
    host="192.0.2.10",
    port=18910,
    path="/info",
    query=None,
    location=None,
):
    if location is None:
        if query is None:
            query = (
                f"cn=SYNTHETIC-CN-SECRET&ctrlType=lan&deviceName=Anycubic Kobra X"
                f"&ip={host}&modelId=20030&modelName=Anycubic Kobra X&zone=global"
            )
        location = f"http://{host}:{port}{path}?{query}" if query else f"http://{host}:{port}{path}"
    lines = [status, "CACHE-CONTROL: max-age=1800"]
    if st is not None:
        lines.append(f"ST: {st}")
    if usn is not None:
        lines.append(f"USN: {usn}")
    if location is not None:
        lines.append(f"LOCATION: {location}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


class FakeClock:
    def __init__(self, steps):
        self._steps = list(steps)
        self._last = self._steps[-1] if self._steps else 0.0

    def __call__(self):
        if self._steps:
            self._last = self._steps.pop(0)
        return self._last


class FakeUDPSocket:
    def __init__(self, packets=None, *, send_error=None, bind_error=None, recv_error=None):
        self.packets = list(packets or [])
        self.send_error = send_error
        self.bind_error = bind_error
        self.recv_error = recv_error
        self.bound = None
        self.sockopts = []
        self.sent = []
        self.blocking = True
        self.closed = False

    def setblocking(self, flag):
        self.blocking = flag

    def setsockopt(self, level, optname, value):
        self.sockopts.append((level, optname, value))

    def bind(self, address):
        if self.bind_error is not None:
            raise self.bind_error
        self.bound = address

    def sendto(self, data, address):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append((data, address))
        return len(data)

    def recvfrom(self, bufsize):
        if self.recv_error is not None:
            raise self.recv_error
        if not self.packets:
            raise BlockingIOError
        return self.packets.pop(0)

    def close(self):
        self.closed = True


class ParseSSDPResponseTests(unittest.TestCase):
    def test_valid_qualified_kobra_x_reply(self):
        raw = _reply(
            host="192.0.2.10",
            usn="uuid:fdm:AA-BB-CC-DD-EE-01",
            query=(
                "cn=PRIVATE-CLOUD-CODE&ctrlType=lan&deviceName=Anycubic Kobra X"
                "&ip=192.0.2.10&modelId=20030&modelName=Anycubic Kobra X&zone=global"
            ),
        )
        parsed = d.parse_ssdp_response(raw, "192.0.2.10")
        self.assertEqual(
            parsed,
            {
                "host": "192.0.2.10",
                "port": 18910,
                "model_id": 20030,
                "model_name": "Anycubic Kobra X",
                "device_name": "Anycubic Kobra X",
                "mac": "aa:bb:cc:dd:ee:01",
                "ctrl_type": "lan",
                "qualified_model": True,
                "firmware_verified": False,
                "unauthenticated": True,
            },
        )
        rendered = repr(parsed)
        self.assertNotIn("PRIVATE-CLOUD-CODE", rendered)
        self.assertNotIn("http://", rendered)

    def test_valid_unqualified_model_reply_and_sanitized_names(self):
        raw = _reply(
            status="http/1.1 200 ok",
            st="AC:3DPRINTER:FDM",
            usn="uuid:fdm:not-a-mac",
            host="192.0.2.25",
            query=(
                "cn=SECRET-CN&ctrlType=lan&deviceName=Bench%20https://evil.test/secret%20Printer"
                "&ip=192.0.2.25&modelId=20025&modelName=Other%20Model"
            ),
        )
        parsed = d.parse_ssdp_response(raw, "192.0.2.25")
        self.assertEqual(parsed["host"], "192.0.2.25")
        self.assertEqual(parsed["model_id"], 20025)
        self.assertFalse(parsed["qualified_model"])
        self.assertFalse(parsed["firmware_verified"])
        self.assertTrue(parsed["unauthenticated"])
        self.assertIsNone(parsed["mac"])
        self.assertNotIn("evil.test", parsed["device_name"])
        self.assertIn("[redacted URL]", parsed["device_name"])
        self.assertNotIn("SECRET-CN", repr(parsed))

    def test_rejects_spoofed_non_lan_wrong_st_and_malformed_replies(self):
        cases = (
            ("cross-host LOCATION", _reply(host="192.0.2.99"), "192.0.2.20"),
            (
                "query ip mismatch",
                _reply(
                    host="192.0.2.20",
                    query="ctrlType=lan&ip=192.0.2.99&modelId=20030",
                ),
                "192.0.2.20",
            ),
            (
                "duplicate query ip",
                _reply(
                    host="192.0.2.20",
                    query="ctrlType=lan&ip=192.0.2.20&ip=192.0.2.99&modelId=20030",
                ),
                "192.0.2.20",
            ),
            ("wrong port", _reply(host="192.0.2.20", port=18088), "192.0.2.20"),
            ("wrong path", _reply(host="192.0.2.20", path="/ctrl"), "192.0.2.20"),
            (
                "https scheme",
                _reply(location="https://192.0.2.20:18910/info?ctrlType=lan&ip=192.0.2.20&modelId=20030"),
                "192.0.2.20",
            ),
            (
                "userinfo in LOCATION",
                _reply(location="http://u@192.0.2.20:18910/info?ctrlType=lan&ip=192.0.2.20&modelId=20030"),
                "192.0.2.20",
            ),
            (
                "fragment in LOCATION",
                _reply(location="http://192.0.2.20:18910/info?ctrlType=lan&ip=192.0.2.20&modelId=20030#frag"),
                "192.0.2.20",
            ),
            (
                "control char in LOCATION",
                _reply(location="http://192.0.2.20:18910/info?ctrlType=lan&ip=192.0.2.20&deviceName=a\x1bb"),
                "192.0.2.20",
            ),
            (
                "cloud ctrlType",
                _reply(host="192.0.2.20", query="ctrlType=cloud&ip=192.0.2.20&modelId=20030"),
                "192.0.2.20",
            ),
            ("non-matching ST", _reply(st="ssdp:all", host="192.0.2.20"), "192.0.2.20"),
            ("missing ST", _reply(st=None, host="192.0.2.20"), "192.0.2.20"),
            ("non-200 status", _reply(status="HTTP/1.1 404 Not Found", host="192.0.2.20"), "192.0.2.20"),
            (
                "non-integer modelId",
                _reply(host="192.0.2.20", query="ctrlType=lan&ip=192.0.2.20&modelId=abc"),
                "192.0.2.20",
            ),
            ("malformed utf-8 bytes", b"\xff\xfe\x00bad", "192.0.2.20"),
            ("malformed header line", b"HTTP/1.1 200 OK\r\nNO_COLON_HEADER\r\n\r\n", "192.0.2.20"),
            ("empty bytes", b"", "192.0.2.20"),
            ("invalid sender IP", _reply(host="192.0.2.20"), "not-an-ip"),
        )
        for label, raw, sender in cases:
            with self.subTest(case=label):
                self.assertIsNone(d.parse_ssdp_response(raw, sender))


class DiscoverPrintersTests(unittest.TestCase):
    def test_valid_dedup_sort_and_two_msearch_probes(self):
        packets = [
            (_reply(host="192.0.2.20", usn="uuid:fdm:02:00:00:00:00:20", query="cn=CN2&ctrlType=lan&deviceName=Other&ip=192.0.2.20&modelId=20025&modelName=Other"), ("192.0.2.20", 1900)),
            (_reply(host="192.0.2.99"), ("192.0.2.20", 1900)),  # spoofed, ignored
            (b"\xffbad", ("192.0.2.30", 1900)),  # malformed, ignored
            (_reply(host="192.0.2.10", usn="uuid:fdm:02-00-00-00-00-10"), ("192.0.2.10", 1900)),
            (_reply(host="192.0.2.10", usn="uuid:fdm:02:00:00:00:00:10"), ("192.0.2.10", 1900)),  # duplicate
        ]
        sock = FakeUDPSocket(packets)
        clock = FakeClock([0.0, 0.0, 0.2, 0.4, 1.0, 1.5, 5.1])

        def fake_select(rlist, wlist, xlist, timeout):
            return (rlist, [], []) if sock.packets else ([], [], [])

        result = d.discover_printers(
            timeout=5,
            socket_factory=lambda *args: sock,
            select_fn=fake_select,
            monotonic=clock,
        )
        self.assertTrue(sock.closed)
        self.assertFalse(sock.blocking)
        self.assertIsNone(sock.bound)
        self.assertEqual(len(sock.sent), 2)
        expected_payload = d.build_msearch_payload()
        self.assertEqual(sock.sent[0], (expected_payload, ("239.255.255.250", 1900)))
        self.assertEqual(sock.sent[1], (expected_payload, ("239.255.255.250", 1900)))

        self.assertEqual(result["protocol"], "ssdp")
        self.assertEqual(result["search_target"], "ac:3dprinter:fdm")
        self.assertEqual(result["timeout_seconds"], 5)
        self.assertIsNone(result["interface"])
        self.assertTrue(result["hardware_discovery_validated"])
        self.assertTrue(result["unauthenticated_lan_advertisement"])
        self.assertFalse(result["firmware_verified"])
        self.assertEqual(len(result["limitations"]), 2)
        self.assertEqual([p["host"] for p in result["printers"]], ["192.0.2.10", "192.0.2.20"])
        self.assertTrue(result["printers"][0]["qualified_model"])
        self.assertFalse(result["printers"][1]["qualified_model"])
        self.assertNotIn("SYNTHETIC-CN-SECRET", repr(result))
        self.assertNotIn("http://", repr(result))

    def test_zero_replies_returns_empty_list_with_limitations(self):
        sock = FakeUDPSocket([])
        clock = FakeClock([0.0, 0.0, 1.1, 2.0])
        result = d.discover_printers(
            timeout=2,
            socket_factory=lambda *args: sock,
            select_fn=lambda r, w, x, t: ([], [], []),
            monotonic=clock,
        )
        self.assertTrue(sock.closed)
        self.assertEqual(result["printers"], [])
        self.assertTrue(result["limitations"])
        self.assertTrue(any("printer pair" in item for item in result["limitations"]))

    def test_explicit_interface_binds_and_sets_multicast_if(self):
        sock = FakeUDPSocket([])
        clock = FakeClock([0.0, 1.5])
        result = d.discover_printers(
            timeout=1,
            interface="192.0.2.5",
            socket_factory=lambda *args: sock,
            select_fn=lambda r, w, x, t: ([], [], []),
            monotonic=clock,
        )
        self.assertEqual(sock.bound, ("192.0.2.5", 0))
        self.assertIn(
            (socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("192.0.2.5")),
            sock.sockopts,
        )
        self.assertEqual(result["interface"], "192.0.2.5")

    def test_invalid_options_raise_before_socket_creation(self):
        created = []

        def fail_factory(*args):
            created.append(args)
            raise AssertionError("socket must not be created")

        for bad_timeout in (0, 16, -1, True, "5", 5.0):
            with self.subTest(timeout=bad_timeout):
                with self.assertRaises(d.DiscoveryArgumentError):
                    d.discover_printers(timeout=bad_timeout, socket_factory=fail_factory)
        for bad_iface in ("not-an-ip", "192.0.2.010", "::1", "http://192.0.2.1", 123):
            with self.subTest(interface=bad_iface):
                with self.assertRaises(d.DiscoveryArgumentError):
                    d.discover_printers(interface=bad_iface, socket_factory=fail_factory)
        self.assertEqual(created, [])

    def test_socket_errors_map_to_safe_discovery_error_and_close_socket(self):
        sock = FakeUDPSocket(send_error=OSError("sensitive-internal-net-detail"))
        with self.assertRaises(d.DiscoveryError) as ctx:
            d.discover_printers(timeout=1, socket_factory=lambda *args: sock)
        self.assertTrue(sock.closed)
        self.assertNotIn("sensitive-internal-net-detail", str(ctx.exception))

        sock2 = FakeUDPSocket(bind_error=PermissionError("secret-bind-failure"))
        with self.assertRaises(d.DiscoveryError) as ctx2:
            d.discover_printers(timeout=1, interface="192.0.2.5", socket_factory=lambda *args: sock2)
        self.assertTrue(sock2.closed)
        self.assertNotIn("secret-bind-failure", str(ctx2.exception))

    def test_keyboard_interrupt_propagates_and_closes_socket(self):
        sock = FakeUDPSocket([])
        clock = FakeClock([0.0, 0.0])

        def interrupt_select(*args):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            d.discover_printers(
                timeout=5,
                socket_factory=lambda *args: sock,
                select_fn=interrupt_select,
                monotonic=clock,
            )
        self.assertTrue(sock.closed)


if __name__ == "__main__":
    unittest.main()
