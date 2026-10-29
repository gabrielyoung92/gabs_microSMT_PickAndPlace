#!/usr/bin/env python3
"""Isolated HTTP proxy checks; the fake companion has no hardware or profile."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import threading
import host_service as host


class FakeCompanion(BaseHTTPRequestHandler):
    calls = []
    reads = 0
    def log_message(self, *args): pass
    def reply(self, code, value):
        data = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        type(self).reads+=1;self.reply(200, {'online':True,'api_version':1,'feeders':[]})
    def do_POST(self):
        args = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(args)
        self.reply(409 if args.get('invalid') else 200,
                   {'error':'Native error'} if args.get('invalid') else {'saved':True})


class Feeders:
    stock=host.Stock(':memory:')
    def snapshot(self): return {}


def main():
    companion = ThreadingHTTPServer(('127.0.0.1',0), FakeCompanion)
    host.OPENPNP_URL = 'http://127.0.0.1:'+str(companion.server_port)
    server = host.WebServer(0,Feeders())
    threads = [threading.Thread(target=s.serve_forever,daemon=True) for s in (companion,server)]
    for thread in threads: thread.start()
    def request(path, body=None):
        c = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        c.request('GET' if body is None else 'POST',path,
                  None if body is None else json.dumps(body),{'Content-Type':'application/json'})
        r=c.getresponse();value=(r.status,json.loads(r.read()));c.close();return value
    try:
        code,state = request('/api/status')
        assert code == 200 and 'openpnp' not in state and FakeCompanion.reads==0
        assert request('/api/catalogue')[1]['api_version']==1
        assert request('/api/openpnp',{'action':'add_feeder','bus_id':7}) == (200,{'saved':True})
        assert FakeCompanion.calls == [{'action':'add_feeder','bus_id':7}]
        assert request('/api/openpnp',{'action':'edit_part','part_id':'P1','name':'Resistor','package_id':'PKG1','height_mm':1,'expected':{}})==(200,{'saved':True})
        assert request('/api/openpnp',{'action':'add_feeder','invalid':True}) == (409,{'error':'Native error'})
        for action in ('save_feeder','teach','move_camera','test_feed','test_pick','job_start'):
            assert request('/api/openpnp',{'action':action})[0] == 400
        assert 'motion' not in state and 'cameras' not in state
        assert request('/api/motion',{'action':'home'})[0] == 404
        server.demo=True
        before=len(FakeCompanion.calls)
        assert not request('/api/catalogue')[1].get('online')
        assert request('/api/openpnp',{'action':'home'})[0] == 409
        assert len(FakeCompanion.calls)==before
        server.demo=False
        companion.shutdown();companion.server_close()
        assert not request('/api/catalogue')[1].get('online')
    finally:
        server.shutdown();server.server_close()
        companion.shutdown();companion.server_close()
        for thread in threads: thread.join(2)
        Feeders.stock.close()
    print('OpenPnP proxy checks passed: status, action, native errors, offline and demo isolation.')


if __name__ == '__main__': main()
