import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const html=readFileSync(new URL('../web/matrix.html',import.meta.url),'utf8');
for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
for(const a of ['codex','claude','opencode','cline']){
  for(const prefix of ['state-','hold-','sessions-']){
    if(!html.includes(`id="${prefix}${a}"`))throw Error(`Missing ${prefix}${a}`);
  }
}
console.log('Dashboard scripts and all four agent controls validated.');
