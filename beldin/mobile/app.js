const $=id=>document.getElementById(id),state={messages:[],busy:false,sending:false,refreshing:false};
function auth(){return sessionStorage.getItem('beldin_token')||''}
function notice(s){$('notice').textContent=s}
async function api(path,options={}){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),path==='/v1/chat'?55000:8000);
 try{const r=await fetch(path,{...options,signal:controller.signal,cache:'no-store',headers:{...(options.headers||{}),Authorization:'Bearer '+auth()}}),j=await r.json().catch(()=>({}));
 if(!r.ok){const e=Error(j.reason||j.error||('HTTP '+r.status));e.status=r.status;throw e}return j}finally{clearTimeout(timer)}
}
function post(body){return api('/v2/control-center/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
function bubble(role,content){const el=document.createElement('div');el.className='bubble '+role;el.textContent=content;$('messages').append(el);$('messages').scrollTop=$('messages').scrollHeight}
function row(parent,label,value){const el=document.createElement('div');el.className='row';const a=document.createElement('span'),b=document.createElement('span');a.textContent=label;b.textContent=value;el.append(a,b);parent.append(el)}
function showDetails(title,data){$('detailTitle').textContent=title;$('detailBody').textContent=JSON.stringify(data,null,2);$('details').classList.remove('hidden');$('details').scrollIntoView({block:'nearest'})}
function lockButtons(){document.querySelectorAll('#controls button').forEach(b=>{b.disabled=state.busy||b.dataset.available!=='true'||(state.sending&&b.dataset.id==='reload_beldin')});$('send').disabled=state.sending||state.busy}
async function reconnect(expected){
 const until=Date.now()+90000;
 while(Date.now()<until){
  try{const r=await api('/v2/control-center/reload'),op=r.operation;
   if(op&&(!expected||op.id===expected)){
    if(op.status==='failed')throw Object.assign(Error(op.error||'Reload failed'),{terminal:true});
    if(op.status==='completed'){
     if(r.instance_id===state.reloadInstance)throw Object.assign(Error('No new service instance verified'),{terminal:true});
     await refresh();notice('Beldin reload verified. Reconnected; chat is ready.');return;
    }
   }
  }catch(e){if(e.status===401||e.terminal)throw e}
  await new Promise(resolve=>setTimeout(resolve,1500));
 }
 throw Error('Reload could not be verified within 90 seconds. Use Refresh status to check recovery.');
}
async function runControl(x){
 if(state.busy)return;state.busy=true;lockButtons();
 try{
  if(x.id==='view_logs'||x.id==='view_activity'){showDetails(x.label,await api(x.endpoint));notice(x.label+' loaded.');return}
  if(x.id==='reload_beldin'){
   const p=await post({action:x.id,op:'propose'});
   if(!window.confirm(p.summary+' Continue?')){await post({action:x.id,op:'cancel',confirmation_id:p.confirmation_id});notice('Reload cancelled.');return}
   state.reloadInstance=state.instance;notice('Waiting for verified restart and reconnect…');let accepted;
   try{accepted=await post({action:x.id,op:'confirm',confirmation_id:p.confirmation_id})}catch(e){if(e.status)throw e;notice('Reload response interrupted; checking recorded outcome…')}
   await reconnect(accepted&&accepted.operation_id);return;
  }
  const r=await post({action:x.id});
  if(x.id==='rescan_models'){const models=(r.models.data||{}).models||[];showDetails('Installed models — fresh Ollama scan',models);notice('Model scan completed: '+models.length+' installed models.')}
  else{await refresh();notice('Status refreshed from live providers.')}
 }catch(e){notice(e.message);if(e.status===401)$('setup').classList.remove('hidden')}
 finally{state.busy=false;lockButtons()}
}
function renderCenter(c){
 const s=c.status||{};state.instance=s.instance_id;$('status').textContent='Connected';$('status').className='ok';
 $('detail').textContent='Beldin service • sample age '+(s.age_seconds==null?'unknown':Math.round(s.age_seconds)+'s');
 const o=s.observed||{},cpu=(o.cpu||{}).data,ram=(o.ram||{}).data;
 $('sample').textContent=cpu&&ram?'CPU '+cpu.used_percent+'% • RAM '+ram.used_percent+'%':s.observed?'Live observations available':'Observations unavailable';
 const activity=$('activity');activity.textContent='';const a=c.activity||{};
 if(a.active_chat_requests)row(activity,'Current','Chat requests: '+a.active_chat_requests);
 [...(a.events||[]),...(a.actions||[])].sort((x,y)=>(y.at_unix||0)-(x.at_unix||0)).slice(0,12).forEach(x=>row(activity,x.action||x.type||x.event,x.status||x.state||x.event||'recorded'));
 if(!activity.children.length)activity.textContent='No activity recorded.';
 const tasks=$('tasks');tasks.textContent='Task runner unavailable. Failed action records are history, not retryable jobs.';
 ((c.tasks||{}).failed||[]).forEach(x=>row(tasks,x.action||'action',x.status||'failed'));
 if(c.coding&&c.coding.enabled){
  tasks.textContent='Start in chat: /code PROJECT your request. Edits stay in a development copy until you review and approve.';
  (c.coding.tasks||[]).forEach(t=>{
   row(tasks,t.id+' • '+t.project,t.status+' • '+(t.current_action||''));
   const details=document.createElement('button');details.textContent='Task details / diff';details.onclick=()=>showDetails('Coding task '+t.id,t);tasks.append(details);
   if(t.proposal&&['approval_needed','ready','approved'].includes(t.status)){
    const approve=document.createElement('button');approve.textContent='Review and approve apply';approve.onclick=async()=>{
     showDetails('Review exact patch — '+t.id,t.proposal);
     if(!window.confirm('Apply these reviewed changes to '+t.proposal.target+'?\n\n'+t.proposal.patch))return;
     try{await codingPost({op:'approve',id:t.id,digest:t.proposal.digest});await codingPost({op:'apply',id:t.id});await refresh()}catch(e){notice(e.message)}
    };tasks.append(approve);
   }
   if(!['applied','rolled_back','cancelled'].includes(t.status)){
    const cancel=document.createElement('button');cancel.textContent='Cancel coding task';cancel.onclick=async()=>{try{await codingPost({op:'cancel',id:t.id});await refresh()}catch(e){notice(e.message)}};tasks.append(cancel);
   }
  });
 }
 const controls=$('controls');controls.textContent='';
 (c.controls||[]).forEach(x=>{
  const wrap=document.createElement('div'),b=document.createElement('button'),reason=document.createElement('div');
  const supported=['refresh_status','rescan_models','reload_beldin','view_logs','view_activity'].includes(x.id)&&Boolean(x.endpoint);
  b.textContent=x.label+(!x.available||!supported?' — unavailable':'');b.dataset.available=String(Boolean(x.available&&supported));b.dataset.id=x.id;b.onclick=()=>runControl(x);wrap.append(b);
  if(!x.available||!supported){reason.className='muted';reason.textContent=x.reason||'Updated backend required';wrap.append(reason)}controls.append(wrap);
 });
 $('logs').textContent=(c.logs||{}).reason||'Raw process logs unavailable.';lockButtons();
}
async function refresh(){
 if(state.refreshing)return false;state.refreshing=true;
 try{renderCenter(await api('/v2/control-center'));$('setup').classList.add('hidden');$('dashboard').classList.remove('hidden');return true}
 catch(e){$('status').textContent=e.status===401?'Token rejected':'Disconnected';$('status').className='warn';$('detail').textContent=e.message;if(e.status===401||$('dashboard').classList.contains('hidden')){$('setup').classList.remove('hidden');notice(e.message)}return false}
 finally{state.refreshing=false}
}
$('save').onclick=async()=>{const token=$('token').value.trim();if(token){sessionStorage.setItem('beldin_token',token);$('token').value='';if(await refresh())notice('Connected.')}};
$('closeDetails').onclick=()=>$('details').classList.add('hidden');
$('form').onsubmit=async e=>{
 e.preventDefault();if(state.sending||state.busy)return;const text=$('input').value.trim();if(!text)return;
 if(text.length>4000){notice('Please keep each message under 4,000 characters.');return}
 $('input').value='';state.messages.push({role:'user',content:text});bubble('user',text);state.sending=true;lockButtons();
 let messages=state.messages.slice(-23);while(messages.reduce((n,m)=>n+m.content.length,0)>11500&&messages.length>1)messages.shift();
 try{const j=await api('/v1/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages})});state.messages.push(j.message);bubble('assistant',j.message.content)}
 catch(err){bubble('assistant','Gateway error: '+err.message)}
 finally{state.sending=false;lockButtons();$('input').focus();refresh()}
};
const Speech=window.SpeechRecognition||window.webkitSpeechRecognition;
if(Speech&&window.isSecureContext){
 $('mic').onclick=()=>{try{const r=new Speech();r.lang='en-US';r.onresult=e=>{$('input').value=e.results[0][0].transcript};r.onerror=e=>notice('Microphone: '+e.error);r.onend=()=>{$('mic').disabled=false};$('mic').disabled=true;r.start()}catch(e){$('mic').disabled=false;notice('Microphone unavailable: '+e.message)}};
}else{$('mic').disabled=true;$('mic').textContent='Microphone — unavailable';$('micReason').textContent='Requires browser speech recognition and a secure connection. LAN HTTP does not provide that.'}
if('serviceWorker'in navigator&&window.isSecureContext)navigator.serviceWorker.register('/app/sw.js').catch(()=>{});
if(auth())refresh();
setInterval(()=>{if(auth()&&!state.busy)refresh()},15000);
function codingPost(body){return api('/v2/coding',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
