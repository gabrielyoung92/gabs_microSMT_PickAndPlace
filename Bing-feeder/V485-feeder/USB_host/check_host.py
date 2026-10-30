#!/usr/bin/env python3
"""Offline checks: real host TCP/HTTP/SQLite, simulated serial, and actual STM32 C.

Requires Python and native gcc. Opens only temporary loopback listeners/files;
no hardware serial port, machine profile, installed service or real database.
"""
from collections import deque
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import signal
import struct
import subprocess
import tempfile
import threading
import time

import host_service as host
from simulated_bus import SimulatedBus


def expect_error(call, types=(host.ServiceError, host.UpdateError, ValueError)):
    try:
        call()
    except types:
        return
    raise AssertionError("Operation unexpectedly succeeded")


def newest(stock):
    return next(row for row in stock.rows() if row["address"] == 1)


def sample_image():
    image = bytearray(1024)
    struct.pack_into("<II", image, 0, 0x20005000, 0x08002241)
    struct.pack_into("<8sII", image, 512, b"V485APP\0", 3, 0x08002000)
    return bytes(image)


def upload_progress_checks():
    """Run the maintained transfer loop, including lost final acknowledgement."""
    from rs485_upload import APP_START, crc32
    image = sample_image()
    class Loader:
        address = 1
        def request(self, body, accepted, **kwargs):
            command = body.split()[0]
            if command == "HELLO":
                return f"READY 00000003 {APP_START:08X} {host.APP_MAX:08X}"
            if command == "BEGIN":
                return "OK 00000000"
            if command == "DATA":
                return kwargs["expected"]
            if command == "END":
                raise TimeoutError("Lost DONE")
            assert command == "INFO"
            return f"APP 00000003 {len(image):08X} {crc32(image):08X}"
    progress = []
    host.upload(Loader(), image, progress=lambda *args: progress.append(args))
    assert [p[0] for p in progress[:3]] == ["connecting", "erasing", "transferring"]
    assert progress[-2:] == [("verifying", 1024, 1024), ("complete", 1024, 1024)]
    assert [p[1] for p in progress if p[0] == "transferring"] == list(range(0, 1025, 32))


def network_checks(service):
    tcp = host.GcodeServer(0, service)
    web = host.WebServer(0, service, demo=True, tcp_port=tcp.server_address[1])
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (tcp, web)]
    for thread in threads:
        thread.start()
    try:
        with socket.create_connection(tcp.server_address, timeout=2) as client:
            client.settimeout(2)
            stream = client.makefile("rb")
            client.sendall(b"M115\n")
            assert stream.readline().startswith(b"FIRMWARE_NAME:V485_USB_HOST")
            assert stream.readline() == b"ok\n"
            with socket.create_connection(tcp.server_address, timeout=2) as second:
                assert second.recv(256).startswith(b"error: another OpenPnP")
            client.sendall(b"M600 N1 ")
            client.sendall(b"F0\r\n")
            assert stream.readline() == b"ok N1 F0\n"
            before = service.port.feeds
            for bad in (b"M600 N0 F1\n", b"N1 F-1\n", b"N1F1\n", b"M600 N1 F1 extra\n"):
                client.sendall(bad)
                assert stream.readline().startswith(b"error:")
            assert service.port.feeds == before
            service.set_maintenance(True)
            client.sendall(b"M600 N1 F4\n")
            assert stream.readline().startswith(b"error: Maintenance")
            assert service.port.feeds == before
            service.set_maintenance(False)
            client.sendall(b"M400\n")
            assert stream.readline() == b"ok\n"
            stream.close()
        connection = http.client.HTTPConnection(*web.server_address, timeout=3)

        def request(path, body=None, origin=None, content_type="application/json", hostname=None):
            headers = {"Content-Type": content_type}
            if hostname:
                headers["Host"] = hostname
            if origin:
                headers["Origin"] = origin
            data = json.dumps(body).encode() if body is not None and content_type == "application/json" else body
            connection.request("GET" if data is None else "POST", path, data, headers)
            response = connection.getresponse()
            return response.status, response.read()

        status, page = request("/")
        assert status == 200 and b'Powered feeders' in page and b'camera-top' not in page and b'data-motion' not in page
        status, data = request("/api/status")
        assert status == 200 and json.loads(data)["demo"] and json.loads(data)["tcp_port"] == tcp.server_address[1]
        assert request("/api/maintenance", {"enabled": True}, origin="http://unrelated.example")[0] == 403
        assert not service.maintenance
        # Requests from the machine name or LAN IP work with implicit port 80,
        # explicit ports and case-insensitive hostnames.
        for hostname, origin in (("openpnp", "http://openpnp"),
                                 ("openpnp.local", "http://openpnp.local:80"),
                                 ("OPENPNP:15502", "http://openpnp:15502"),
                                 ("198.51.100.27", "http://198.51.100.27")):
            assert request("/api/maintenance", {"enabled": False}, origin=origin, hostname=hostname)[0] == 200
        assert request("/api/maintenance", {"enabled": True}, origin="http://openpnp:5002", hostname="openpnp")[0] == 403
        assert not service.maintenance
        assert request("/api/maintenance", {"enabled": True})[0] == 200
        assert service.maintenance
        assert request("/api/polling", {"ids": [1, 2]})[0] == 400
        assert request("/api/stock", {"address": 1, "label": "10k", "quantity": 0, "pulses_per_part": 4})[0] == 200
        assert request("/api/refresh", {"address": 1})[0] == 200
        info = next(r["firmware_info"] for r in service.stock.rows() if r["uid"]==newest(service.stock)["uid"])
        assert info["size"] == 1024 and info["crc32"] == "12345678"
        before = len(service.port.frames)
        status, data = request("/api/image", sample_image(), content_type="application/octet-stream")
        assert status == 200 and json.loads(data)["size"] == 1024
        assert len(service.port.frames) == before  # Image inspection never touches hardware.
        assert request("/api/image", b"invalid", content_type="application/octet-stream")[0] == 400
        assert request("/api/update?address=1", sample_image(), content_type="application/octet-stream")[0] == 409
        assert len(service.port.frames) == before  # Demo refuses even valid uploads.
        assert request("/api/assign", {"address": 1, "new_id": 0})[0] == 400
        assert request("/api/update?address=1", b"wrong image", content_type="application/octet-stream")[0] == 409
        assert request("/api/maintenance", {"enabled": False})[0] == 200
        connection.close()
    finally:
        for server in (tcp, web):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()


def startup_checks(directory):
    def free_port():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]
    tcp, web = free_port(), free_port()
    while len({tcp, web}) != 2:
        tcp, web = free_port(), free_port()
    blocked = directory / "not-a-directory"
    blocked.write_text("Temporary test file")
    process = subprocess.Popen([host.sys.executable, str(Path(host.__file__)), "--demo", "--ids", "1",
                                "--database", str(blocked / "stock.sqlite3"),
                                "--web-host", "127.0.0.1",
                                "--tcp-port", str(tcp), "--web-port", str(web)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                connection = http.client.HTTPConnection("127.0.0.1", web, timeout=0.2)
                connection.request("GET", "/api/status")
                response = connection.getresponse()
                value = json.loads(response.read())
                assert response.status == 200 and value["demo"] and not value["inventory_persistent"]
                connection.close()
                break
            except OSError:
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
    finally:
        if host.os.name == "posix":
            process.send_signal(signal.SIGINT)
            process.communicate(timeout=3)
            assert process.returncode == 0
        else:
            process.terminate()
            process.communicate(timeout=3)


def firmware_checks(directory):
    """Use the existing temporary HAL harness with the actual production C."""
    check = host.TOOLS / "check_feeder.py"
    spec = importlib.util.spec_from_file_location("feeder_check", check)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = directory / "stm32"
    folder.mkdir()
    (folder / "stm32f1xx_hal.h").write_text(module.hal)
    prefix = module.app.split("int main(int argc,char** argv){", 1)[0]
    peer = r'''
int main(void){
 testA.levels=testB.levels=0xffff;Feeder_Init();
 char line[256];
 while(fgets(line,sizeof(line),stdin)){
  if(!Stock_Flush())return 2;
  line[strcspn(line,"\r\n")]=0;response[0]=0;
  updateLine=line;ProcessRS485();
  if(feedState==FEED_RUNNING)pulse();
  fputs(response,stdout);fputs("END\n",stdout);fflush(stdout);
 }
 return 0;
}
'''
    source = folder / "peer.c"
    source.write_text(prefix + peer)
    for wide in (0, 1):
        exe = folder / f"peer{wide}"
        subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                        "-Wno-misleading-indentation", "-fsanitize=address,undefined", "-g",
                        "-I", str(folder), "-I", str(check.parents[1] / "src"),
                        f"-DFEEDER_WIDE={wide}", str(source), "-o", str(exe)], check=True)
        process = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        class Port:
            def __init__(self):
                self.rx, self.moves = deque(), 0

            def write(self, raw):
                if b" FEED " in raw:
                    self.moves += 1
                process.stdin.write(raw)
                process.stdin.flush()
                while True:
                    reply = process.stdout.readline()
                    if reply == b"END\n":
                        break
                    if not reply:
                        raise AssertionError("STM32 peer stopped")
                    self.rx.append(reply)

            def flush(self):
                pass

            def read_until(self, *args):
                if self.rx:
                    return self.rx.popleft()
                time.sleep(0.001)
                return b""

        port = Port()
        stock = host.Stock(":memory:")
        service = host.Feeders(port, stock, [7], reply_timeout=0.01, poll_interval=0.001)
        tcp = host.GcodeServer(0, service)
        thread = threading.Thread(target=tcp.serve_forever, daemon=True)
        thread.start()
        try:
            service.load_stock(7, "Actual firmware", 0, 3)
            with socket.create_connection(tcp.server_address, timeout=3) as client:
                client.settimeout(3)
                with client.makefile("rb") as replies:
                    client.sendall(b"M600 N7 F0\n")
                    assert replies.readline() == b"ok N7 F0\n"
                    row = stock.rows()[0]
                    assert row["used_pulses"] == 3 and row["remaining"] == 0 and row["variant"] == ("12mm" if wide else "8mm")
                    client.sendall(b"M600 N7 F2\n")
                    assert replies.readline() == b"ok N7 F2\n"
            assert stock.rows()[0]["used_pulses"] == 5 and port.moves == 2
            assert stock.rows()[0]["uid"] == "111111112222222233333333"
        finally:
            tcp.shutdown();tcp.server_close();thread.join()
            process.stdin.close()
            assert process.wait(timeout=3) == 0
            stock.close()


def main():
    host.logging.basicConfig(level=host.logging.ERROR)
    with tempfile.TemporaryDirectory(prefix="v485-host-check-") as tmp:
        folder = Path(tmp)
        db = folder / "stock.sqlite3"
        stock = host.Stock(db)
        port = SimulatedBus()
        port.echo = True
        service = host.Feeders(port, stock, [1], reply_timeout=0.01, feed_timeout=0.3, poll_interval=0.001)
        service.load_stock(1, "Resistors", 2, 4, 1)
        port.nodes[1]["counter"] += 1  # Hand movement is telemetry, not a completed part feed.
        with service.bus:
            service.observe(1)
        assert newest(stock)["used"] == 0
        assert service.feed(1, 0) == "ok N1 F0"
        assert newest(stock)["remaining"] == 1
        assert service.feed(1, 8) == "ok N1 F8"
        assert newest(stock)["remaining"] == 0
        assert service.feed(1, 4) == "ok N1 F4"  # Zero stock never gates feeding.
        before = port.feeds
        expect_error(lambda: service.feed(0, 1))
        service.set_maintenance(True)
        expect_error(lambda: service.feed(1, 1))
        assert port.feeds == before
        service.set_maintenance(False)
        # Reject maintenance commands promptly even if an upload owns the bus.
        held, release = threading.Event(), threading.Event()
        def hold_bus():
            with service.bus:
                held.set();release.wait(3)
        holder = threading.Thread(target=hold_bus)
        holder.start();assert held.wait(1)
        try:
            service.set_maintenance(True)
            started = time.monotonic();expect_error(lambda: service.feed(1, 1))
            assert time.monotonic()-started < 0.2 and port.feeds == before
            started = time.monotonic();expect_error(lambda: service.update(1, sample_image()))
            assert time.monotonic()-started < 0.2 and service.update_status is None
            service.set_maintenance(False)
            expect_error(lambda: service.feed(1, 1))
            assert port.feeds == before
        finally:
            release.set();holder.join()
        port.lose_accept, port.drop_status = True, 2
        assert service.feed(1, 1) == "ok N1 F1" and port.feeds == before + 1
        port.lose_accept = False
        port.rx.append(host.packet(1, "DONE FFFFFFFF FFFFFFFF"))
        port.rx.append(b"corrupted\n")
        assert service.feed(1, 1) == "ok N1 F1"
        # Missing telemetry and a broken database cannot override confirmed DONE.
        port.fail_diag = True
        assert service.feed(1, 1) == "ok N1 F1"
        port.fail_diag = False
        real_observe = stock.observe
        stock.observe = lambda *args: (_ for _ in ()).throw(RuntimeError("inventory unavailable"))
        assert service.feed(1, 1) == "ok N1 F1"
        stock.observe = real_observe
        service.observe(1)
        # A valid wrap accumulates movement; an ambiguous gap is marked uncertain.
        wrap = host.Stock(":memory:")
        wrap.observe(1, "wrap", "0000000000000001", 0xFFFFFFFE, 4)
        wrap.load("wrap", "Wrap test", 100, 4, 10)
        wrap.observe(1, "wrap", "0000000000000001", 1, 4)
        assert wrap.rows()[0]["used_pulses"] == 3 and not wrap.rows()[0]["uncertain"]
        wrap.observe(1, "wrap", "0000000000000001", 0x80000002, 4)
        assert wrap.rows()[0]["uncertain"]
        wrap.close()
        # Restarting the PC preserves the MCU token and catches up missed movement.
        previous = newest(stock)["used_pulses"]
        stock.close()
        stock = host.Stock(db)
        service.stock = stock
        port.nodes[1]["counter"] += 4
        service.observe(1)
        assert newest(stock)["used_pulses"] == previous + 4 and not newest(stock)["uncertain"]
        # An MCU reset restores feeder-owned stock from its persistent record.
        port.nodes[1]["token"], port.nodes[1]["counter"] = (0, 0), 2
        service.observe(1)
        assert not newest(stock)["uncertain"] and newest(stock)["used_pulses"] == previous + 6
        assert service.feed(1, 1) == "ok N1 F1"  # Uncertain stock also never gates it.
        service.load_stock(1, "New reel", 100, 4)
        assert not newest(stock)["uncertain"] and newest(stock)["used"] == 0
        # Two requested feeds serialize as complete transactions.
        results = []
        threads = [threading.Thread(target=lambda: results.append(service.feed(1, 1))) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert results == ["ok N1 F1", "ok N1 F1"]
        for failure in ("unknown", "stall"):
            setattr(port, failure, True)
            before = port.feeds
            expect_error(lambda: service.feed(1, 1))
            assert port.feeds == before + 1
            setattr(port, failure, False)
        port.nodes[1]["fault"] = 2
        expect_error(lambda: service.feed(1, 1))
        assert newest(stock)["fault"] == "peel_timeout"
        port.nodes[1]["fault"] = 0
        service.set_maintenance(True)
        expect_error(lambda: service.assign_id(0, 0))
        port.nodes[0]["armed"] = False
        service.load_stock(0, "Commissioning reel", 20, 4)
        port.nodes[0]["armed"] = True
        service.assign_id(0, 7)
        assert 7 in port.nodes and 0 not in port.nodes
        assert next(r for r in stock.rows() if r["address"] == 7)["label"] == "Commissioning reel"
        # Validation precedes update; maintenance is required and stays enabled.
        expect_error(lambda: service.update(1, b"invalid"))
        service.set_maintenance(False)
        expect_error(lambda: service.update(1, sample_image()))
        service.set_maintenance(True)
        real_upload, called = host.upload, []

        def fake_upload(link, image, progress=None):
            assert service.updating and service.maintenance and image == sample_image()
            expect_error(lambda: service.set_maintenance(False))
            expect_error(lambda: service.feed(1, 1))
            progress("transferring", 512, len(image))
            assert service.snapshot()["update"]["sent"] == 512
            progress("complete", len(image), len(image))
            called.append(link.address)

        try:
            host.upload = fake_upload
            service.update(1, sample_image())
            assert called == [1] and service.maintenance and not service.updating
            assert service.snapshot()["update"]["stage"] == "complete"
            def failed_upload(link, image, progress=None):
                raise host.UpdateError("Test transfer failure")
            host.upload = failed_upload
            expect_error(lambda: service.update(1, sample_image()))
            result = service.snapshot()["update"]
            assert result["stage"] == "failed" and result["error"] == "Test transfer failure"
            assert service.maintenance and not service.updating
        finally:
            host.upload = real_upload
        service.set_maintenance(False)
        network_checks(service)
        stock.close()
        firmware_checks(folder)
        startup_checks(folder)
        upload_progress_checks()
    print("Host checks passed: actual STM32 C -> serial -> TCP DONE; HTTP, stock, resets, no-replay and maintenance")


if __name__ == "__main__":
    main()
