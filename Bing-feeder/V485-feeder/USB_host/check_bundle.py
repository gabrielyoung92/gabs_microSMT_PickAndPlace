#!/usr/bin/env python3
"""Isolated built-firmware packaging/HTTP checks. Never opens a hardware port."""
import http.client
import json
from pathlib import Path
import tempfile
import threading

import host_service as host
from bundle_firmware import package, read_bundle
from check_host import sample_image


def main():
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        image = folder / 'firmware.bin'
        image.write_bytes(sample_image())
        bundle = folder / 'firmware.json'
        package(image, bundle)
        metadata, binary = read_bundle(bundle)
        assert binary == sample_image() and metadata['bytes'] == len(binary)
        old_path = host.BUNDLE
        host.BUNDLE = bundle
        class Feeders:
            stock = host.Stock(':memory:')
            calls = []
            def snapshot(self): return {}
            def queue_update(self, data, address=None): self.calls.append((address, data))
        feeders = Feeders()
        server = host.WebServer(0, feeders)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def request(path, body=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            connection.request('GET' if body is None else 'POST', path,
                               None if body is None else json.dumps(body), {'Content-Type':'application/json'})
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result
        try:
            state = request('/api/status')[1]['available_firmware']
            assert state['available'] and state['sha256'] == metadata['sha256']
            assert 'image_base64' not in state
            args = dict(address=7, sha256=metadata['sha256'])
            assert request('/api/update-bundled', dict(args, sha256='old-build'))[0] == 409
            assert not feeders.calls
            server.demo = True
            assert request('/api/update-bundled', args)[0] == 409
            assert not feeders.calls
            server.demo = False
            assert request('/api/update-bundled', args)[0] == 200
            assert feeders.calls == [(7, binary)]
            damaged = json.loads(bundle.read_text())
            damaged['crc32'] = '00000000'
            bundle.write_text(json.dumps(damaged))
            assert not request('/api/status')[1]['available_firmware']['available']
            assert request('/api/update-bundled', args)[0] == 400
            assert len(feeders.calls) == 1
            bundle.unlink()
            assert not request('/api/status')[1]['available_firmware']['available']
            assert request('/api/update-bundled', args)[0] == 503
            assert len(feeders.calls) == 1
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)
            host.BUNDLE = old_path
            feeders.stock.close()
    print('Built-firmware checks passed: exact bytes, changed-build rejection, corrupt/missing bundles and demo isolation.')


if __name__ == '__main__': main()
