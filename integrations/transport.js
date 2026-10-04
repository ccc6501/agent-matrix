// Loopback only. Heartbeats retain event time so success expires normally.
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
let config={};
try { config=JSON.parse(readFileSync(process.env.AGENT_MATRIX_CONFIG||new URL('../.local/config.json',import.meta.url),'utf8')); } catch {}
const python = process.env.AGENT_MATRIX_PYTHON || config.python || 'python';
const port=Number.isInteger(config.http_port)&&config.http_port>=1024&&config.http_port<=65535?config.http_port:8765;
const endpoint=`http://127.0.0.1:${port}/api/session`;
const hook = fileURLToPath(new URL('../host/agent_hook.py', import.meta.url));
export function reporter(agent, cwd, pid = process.pid) {
  const latest = new Map();
  let fallbackAt = 0, inflight = false;
  async function send(payload) {
    try {
      const r = await fetch(endpoint, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify(payload), signal:AbortSignal.timeout(800)
      });
      if (!r.ok) throw Error('bridge unavailable');
    } catch {
      if (Date.now()-fallbackAt < 30000 || payload.state==='ended') return;
      fallbackAt=Date.now();
      try {
        const child=spawn(python,[hook,'--forward'],{windowsHide:true,detached:true,stdio:['pipe','ignore','ignore']});
        child.on('error',()=>{});child.stdin.on('error',()=>{});
        child.stdin.end(JSON.stringify(payload));child.unref();
      } catch { /* A display failure must never break an agent. */ }
    }
  }
  const timer=setInterval(async()=>{
    if(inflight)return;inflight=true;
    try {
      await Promise.all([...latest.values()].map(payload=>{
        if(['working','needs_input','idle'].includes(payload.state))payload.ts=Date.now()/1000;
        return send(payload);
      }));
    } finally { inflight=false; }
  },5000);timer.unref?.();
  function report(session,state,event) {
    if(!session)return;
    const prior=latest.get(session);
    if(prior?.state===state)return;
    const payload={agent,session,state,event,cwd,pid,ts:Date.now()/1000};
    if(state==='ended')latest.delete(session);else latest.set(session,payload);
    void send(payload);
  }
  report.close=()=>{clearInterval(timer);for(const sid of latest.keys())report(sid,'ended','SessionEnd');};
  return report;
}
