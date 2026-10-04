import { reporter } from './transport.js';

// Runtime emits tool-started after permission resolution. A short debounce
// avoids flashing attention for tools that are immediately auto-approved.
export function makeHooks(report, root, waitMs=750) {
  const toolsBySession=new Map();
  const sid=c=>root?(root+':'+(c?.snapshot?.agentId||'main')):c?.snapshot?.agentId;
  function tools(id){if(!toolsBySession.has(id))toolsBySession.set(id,new Map());return toolsBySession.get(id);}
  const question=name=>['ask_followup_question','ask_question','plan_mode_respond'].includes(name);
  function clear(id){for(const v of tools(id).values())clearTimeout(v.timer);tools(id).clear();}
  function status(id,event){report(id,[...tools(id).values()].some(v=>v.waiting)?'needs_input':'working',event);}
  return {
    beforeRun(c){clear(sid(c));report(sid(c),'working','RunStart');},
    beforeTool(c){
      const key=c.toolCall.toolCallId||c.toolCall.id,id=sid(c),v={waiting:false,timer:null};
      tools(id).set(key,v);
      v.timer=setTimeout(()=>{v.waiting=true;status(id,'ToolApprovalPending');},waitMs);
      v.timer.unref?.();
    },
    onEvent(e){
      const id=sid(e),key=e.toolCall?.toolCallId||e.toolCall?.id,pending=tools(id);
      if(e.type==='tool-started'){
        const v=pending.get(key);if(v)clearTimeout(v.timer);
        if(question(e.toolCall?.toolName))pending.set(key,{waiting:true});else pending.delete(key);
        status(id,'ToolStarted');
      }else if(e.type==='tool-finished'){
        const v=pending.get(key);if(v)clearTimeout(v.timer);pending.delete(key);status(id,'ToolFinished');
      }else if(e.type==='run-failed'){clear(id);report(id,'error','RunFailed');}
    },
    afterRun(c){clear(sid(c));report(sid(c),c.result.status==='completed'?'completed':c.result.status==='failed'?'error':'idle','RunEnd');}
  };
}

let hooks;
export default {
  name:'agent-matrix', manifest:{capabilities:['hooks']},
  setup(api,ctx){
    hooks=makeHooks(reporter('cline',ctx.workspaceInfo?.rootPath||process.cwd(),process.ppid),ctx.session?.sessionId);
  },
  hooks:Object.fromEntries(['beforeRun','beforeTool','onEvent','afterRun'].map(name=>[name,c=>hooks?.[name](c)]))
};
