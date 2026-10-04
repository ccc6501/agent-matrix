import http.client
import json
import threading
import time
import unittest
from unittest.mock import Mock
import bridge


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.board=bridge.Board()
        self.sessions=bridge.Sessions()
        self.driver=bridge.Driver(self.board,self.sessions)
        self.server=bridge.Server(('127.0.0.1',0),bridge.make_handler(self.board,self.sessions,self.driver))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,body,headers=None,path='/api/session'):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2)
        h={'Content-Type':'application/json'};h.update(headers or {})
        conn.request('POST',path,body=body,headers=h)
        response=conn.getresponse();result=(response.status,json.loads(response.read()));conn.close();return result

    def test_bad_payloads_do_not_poison_sessions(self):
        base={'agent':'codex','session':'test','state':'working'}
        for body in ('[]','null','{',json.dumps(dict(base,ts=float('nan'))),json.dumps(dict(base,ts=float('inf'))),
                     json.dumps(dict(base,ts=10**400)), json.dumps(dict(base,ts=time.time()+9999)),json.dumps(dict(base,pid=True)),json.dumps(dict(base,session='x'*257))):
            self.assertEqual(self.request(body)[0],400)
        self.assertEqual(self.sessions.snapshot(time.time())['codex'],[])
        self.assertEqual(self.request(json.dumps(base))[0],200)
        self.assertEqual(self.sessions.aggregate('codex',time.time()),'working')

    def test_cross_origin_host_and_body_limit(self):
        self.assertEqual(self.request('{}',{'Origin':'https://example.com'})[0],403)
        self.assertEqual(self.request('{}',{'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('{}',{'Content-Type':'text/plain'})[0],400)
        self.assertEqual(self.request(' '*16385)[0],400)

    def test_bool_is_not_display_command_number(self):
        self.assertEqual(self.request('{"command":"demo","value":true}',path='/api/display')[0],400)
        self.assertEqual(self.request('{"command":"rotate","value":false}',path='/api/display')[0],400)

    def test_stale_event_and_success_expiry(self):
        now=time.time()
        base={'agent':'opencode','session':'test','state':'completed','ts':now-31}
        self.assertTrue(self.request(json.dumps(base))[1]['applied'])
        self.assertEqual(self.sessions.aggregate('opencode',now),'idle')
        self.assertFalse(self.request(json.dumps(dict(base,ts=now-32,state='working')))[1]['applied'])


if __name__=='__main__':unittest.main()
