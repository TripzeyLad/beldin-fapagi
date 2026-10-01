// Exercise actual UI handlers with deterministic HTTP and restart failures.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('beldin/mobile/app.js','utf8');
function harness(handler,confirm=true){
 let now=0;
 const nodes={};
 class Element {
  constructor(){this.children=[];this.dataset={};this.value='';this.textContent='';this.disabled=false;const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x)}}
  append(...items){this.children.push(...items)} focus(){} scrollIntoView(){}
 }
 const get=id=>nodes[id]||(nodes[id]=new Element());
 const document={getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>get('controls').children.flatMap(x=>x.children).filter(x=>x.dataset.id)};
 get('dashboard').classList.add('hidden');get('details').classList.add('hidden');
 const calls=[],storage={};
 const context=vm.createContext({document,window:{confirm:()=>confirm,prompt:()=> 'synthetic-human-credential',isSecureContext:false},navigator:{},
 sessionStorage:{getItem:k=>storage[k]||'',setItem:(k,v)=>storage[k]=v},AbortController,
 Date:{now:()=>now},setInterval:()=>0,clearTimeout:()=>{},
 setTimeout:(f,ms)=>{if(ms===1500){now+=1500;queueMicrotask(f)}return 1},
 fetch:async(path,options)=>{calls.push([path,options]);const result=await handler(path,options);return {ok:result.status<400,status:result.status,json:async()=>result.body}}});
 vm.runInContext(source,context);
 return {get,calls,run:code=>vm.runInContext(code,context)};
}
const center={status:{instance_id:'old'},controls:[],tasks:{},logs:{}};
const response=body=>({status:200,body});
const x=id=>JSON.stringify({id,label:id,endpoint:'/v2/control-center/'+(id==='view_logs'?'logs':'activity')});
(async()=>{
 let count=0;
 async function test(name,fn){await fn();count++;console.log('PASS '+name)}
 await test('Connect clears token field; failed auth remains visible',async()=>{
  const h=harness(()=>({status:401,body:{error:'unauthorized'}}));
  h.get('token').value='local-test-token';await h.get('save').onclick();
  assert.equal(h.get('token').value,'');assert.equal(h.get('setup').classList.contains('hidden'),false);
  assert.equal(h.get('notice').textContent,'unauthorized');
 });
 await test('Unsupported microphone is disabled',async()=>{assert.equal(harness(()=>response({})).get('mic').disabled,true)});
 await test('Fresh scan shows actual models and releases controls',async()=>{
  const h=harness(()=>response({models:{data:{models:[{name:'qwen3:8b'}]}}}));
  await h.run('runControl('+x('rescan_models')+')');
  assert.match(h.get('detailBody').textContent,/qwen3:8b/);assert.equal(h.run('state.busy'),false);
  assert.equal(JSON.parse(h.calls[0][1].body).action,'rescan_models');
 });
 await test('Failed model scan does not claim success',async()=>{
  const h=harness(()=>({status:503,body:{error:'upstream_unavailable'}}));
  await h.run('runControl('+x('rescan_models')+')');assert.equal(h.get('notice').textContent,'upstream_unavailable');
 });
 await test('Status refresh invokes backend and refreshes display',async()=>{
  const h=harness(p=>response(p.endsWith('/action')?{status:'completed'}:center));
  await h.run('runControl('+x('refresh_status')+')');
  assert.equal(h.calls[0][0],'/v2/control-center/action');assert.equal(h.get('status').textContent,'Connected');
 });
 await test('Log and activity controls use their read endpoints; close works',async()=>{
  for(const id of ['view_logs','view_activity']){
   const h=harness(()=>response({available:true}));await h.run('runControl('+x(id)+')');
   assert.equal(h.calls[0][1].method,undefined);assert.equal(h.get('details').classList.contains('hidden'),false);
   h.get('closeDetails').onclick();assert.equal(h.get('details').classList.contains('hidden'),true);
  }
 });
 await test('Reload cancellation consumes proposal without dispatch',async()=>{
  const h=harness(()=>response({confirmation_id:'key',summary:'Reload Beldin'}),false);
  await h.run('runControl('+x('reload_beldin')+')');
  assert.deepEqual(h.calls.map(x=>JSON.parse(x[1].body).op),['propose','cancel']);
  assert.equal(h.get('notice').textContent,'Reload cancelled.');
  assert.ok(h.calls.every(x=>!x[1].headers['X-Beldin-Approval']));
 });
 await test('Reload confirmation supplies separate approval credential',async()=>{
  const h=harness(()=>response({}));
  await h.run("post({action:'reload_beldin',op:'confirm',confirmation_id:'key'})");
  assert.equal(h.calls[0][1].headers['X-Beldin-Approval'],'synthetic-human-credential');
  assert.notEqual(h.calls[0][1].headers.Authorization,'Bearer synthetic-human-credential');
 });
 await test('Missing approval credential prevents confirmation request',async()=>{
  const h=harness(()=>response({}));h.run("window.prompt=()=>''");
  await assert.rejects(h.run("post({action:'reload_beldin',op:'confirm',confirmation_id:'key'})"),/Approval token required/);
  assert.equal(h.calls.length,0);
 });
 await test('Rejected approval credential is forgotten',async()=>{
  const h=harness(()=>({status:403,body:{error:'human_approval_required'}}));
  await assert.rejects(h.run("post({action:'reload_beldin',op:'confirm',confirmation_id:'key'})"));
  assert.equal(h.run('humanApproval'),'');
 });
 function reloadHarness(mode){
  let polls=0;
  const h=harness((p,o)=>{
   if(p.endsWith('/action')){
    const op=JSON.parse(o.body).op;
    if(op==='propose')return response({confirmation_id:'key',summary:'Reload Beldin'});
    if(mode==='lost')throw Error('connection reset');
    return {status:202,body:{operation_id:'job'}};
   }
   if(p.endsWith('/reload')){
    polls++;
    if(mode==='timeout'||polls===1)throw Error('temporarily offline');
    return response({instance_id:mode==='same'?'old':'new',operation:{id:'job',status:mode==='failed'?'failed':'completed',error:'verified_reload_failed'}});
   }
   return response({...center,status:{instance_id:'new'}});
  });
  h.run("state.instance='old'");return h;
 }
 await test('Reload tolerates downtime then verifies changed instance',async()=>{
  const h=reloadHarness('success');await h.run('runControl('+x('reload_beldin')+')');
  assert.match(h.get('notice').textContent,/reload verified/);assert.equal(h.run('state.busy'),false);
 });
 await test('Lost acceptance response is recovered from durable result',async()=>{
  const h=reloadHarness('lost');await h.run('runControl('+x('reload_beldin')+')');assert.match(h.get('notice').textContent,/reload verified/);
 });
 await test('Failed restart and unchanged instance are not success',async()=>{
  for(const mode of ['failed','same']){
   const h=reloadHarness(mode);await h.run('runControl('+x('reload_beldin')+')');
   assert.doesNotMatch(h.get('notice').textContent,/reload verified/);assert.equal(h.run('state.busy'),false);
  }
 });
 await test('Reconnect timeout unlocks controls and reports uncertainty',async()=>{
  const h=reloadHarness('timeout');await h.run('runControl('+x('reload_beldin')+')');
  assert.match(h.get('notice').textContent,/could not be verified/);assert.equal(h.run('state.busy'),false);
 });
 console.log(count+' UI behavior tests passed');
})().catch(e=>{console.error(e);process.exitCode=1});
