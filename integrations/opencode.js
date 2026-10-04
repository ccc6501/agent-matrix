import { reporter } from './transport.js';

export function eventMapper(report) {
  const states=new Map(), pending=new Map();
  function set(sid,state,event){states.set(sid,state);report(sid,state,event);}
  return ({event})=>{
    const p=event.properties||{},type=event.type;
    if(type==='server.instance.disposed'||type==='global.disposed'){
      for(const sid of states.keys())report(sid,'ended',type);
      states.clear();pending.clear();return;
    }
    const sid=p.sessionID||p.info?.sessionID||(type.startsWith('session.')?p.info?.id:null);
    if(!sid)return;
    const wait=pending.get(sid)||new Set();pending.set(sid,wait);
    const normalized=type.replace('.v2.','.');
    if(['permission.asked','question.asked'].includes(normalized)){
      wait.add(p.id);set(sid,'needs_input',type);
    }else if(['permission.replied','question.replied','question.rejected'].includes(normalized)){
      wait.delete(p.requestID);set(sid,wait.size?'needs_input':'working',type);
    }else if(type==='session.deleted'){
      set(sid,'ended',type);states.delete(sid);pending.delete(sid);
    }else if(type==='session.error'){
      wait.clear();set(sid,p.error?.name==='MessageAbortedError'?'idle':'error',type);
    }else if(type==='session.created')set(sid,'idle',type);
    else if(type==='session.status'&&['busy','retry'].includes(p.status?.type)){
      set(sid,wait.size?'needs_input':'working',type);
    }else if(type==='session.idle'||(type==='session.status'&&p.status?.type==='idle')){
      if(!['error','idle','completed'].includes(states.get(sid))&&!wait.size)set(sid,'completed',type);
    }
  };
}

export default async function AgentMatrix({directory}) {
  const report=reporter('opencode',directory);
  return {event:eventMapper(report)};
}
