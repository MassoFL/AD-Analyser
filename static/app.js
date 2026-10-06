const $=s=>document.querySelector(s), token=$('meta[name=pipeline-token]').content;
const stages={inbox:'À analyser',review:'À examiner',kept:'Retenue',rejected:'Écartée'};
const descriptions={inbox:'Les nouvelles annonces arrivent ici.',review:'Les analyses attendent ta décision.',kept:'Tes opportunités à approfondir.',rejected:'Les annonces que tu écartes.'};
let board, selected, initialAnalysis, limit=25, timer, loading=false;
const pendingMoves=new Map();
let boardVersion=0, refreshAgain=false, moveRefreshTimer;
let offsets={inbox:0,review:0,kept:0,rejected:0}, cloudJob=null, stopCloud=false;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(timer);timer=setTimeout(()=>$('#toast').hidden=true,6500);}
async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Pipeline-Token':token},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.error||'Opération impossible.');return result;}
const options=current=>Object.entries(stages).map(([key,label])=>`<option value="${key}" ${current===key?'selected':''}>${label}</option>`).join('');
function visual(row,detail=false){return row.has_image?`<img src="${esc(row.display_image||'/images/'+row.id)}" referrerpolicy="no-referrer" alt="Visuel de l’annonce" loading="lazy">`:`<div class="no-image"><span>▧</span>Image non disponible${detail?'<br>Les anciens exports ne conservaient pas les images.':''}</div>`;}
function card(row){const pending=pendingMoves.has(row.id);const a=row.analysis;const title=a?.micro_niche&&a.micro_niche!=='indéterminée'?a.micro_niche:(a?.texte_nettoye||row.raw||'Texte non reconnu').split('\n')[0];return `<article class="card" draggable="${!pending}" aria-busy="${pending}" data-id="${esc(row.id)}" tabindex="0" role="button" aria-label="Ouvrir ${esc(title)}"><div class="visual">${visual(row)}<span class="reach">Portée ${esc(row.reach||'—')}</span></div><div class="card-content"><h3>${esc(title)}</h3><p class="snippet">${esc(a?.texte_nettoye||row.raw||'Aucun texte détecté')}</p><div class="tags">${a?`<span class="tag ${a.potentiel_ecommerce==='oui'?'good':''}">E-commerce ${esc(a.potentiel_ecommerce)}</span>${a.a_verifier?'<span class="tag warn">À vérifier</span>':''}`:'<span class="tag">Analyse en attente</span>'}${row.error?'<span class="tag warn">Analyse à relancer</span>':''}</div><div class="card-foot"><span>${a?esc(row.analyst.startsWith('Codex')?'Analyse importée':'Analysée'):'Collectée'}</span>${pending?'<span class="saving">Enregistrement…</span>':''}<select ${pending?'disabled':''} aria-label="Étape de cette annonce" data-move="${esc(row.id)}">${options(row.stage)}</select></div>${row.stage==='review'?`<div class="decision-actions"><button type="button" class="keep" data-decision="kept" data-ad="${esc(row.id)}" ${pending?'disabled':''}>Retenir</button><button type="button" class="reject" data-decision="rejected" data-ad="${esc(row.id)}" ${pending?'disabled':''}>Écarter</button></div>`:''}${row.stage==='kept'?`<div class="decision-actions"><button type="button" class="reject" data-decision="rejected" data-ad="${esc(row.id)}" ${pending?'disabled':''}>Écarter</button></div><div class="keyword-tags">${(row.search_keywords||[]).map(k=>`<span class="tag">${esc(k)}</span>`).join('')}</div>`:''}</div></article>`;}
async function refresh(){
 if(loading||pendingMoves.size){refreshAgain=true;return;}
 loading=true;refreshAgain=false;const version=boardVersion;
 try{
  const query=new URLSearchParams({q:$('#search').value,potential:$('#potential').value,limit});
  for(const [stage,offset] of Object.entries(offsets))query.set('offset_'+stage,offset);
  const incoming=await api('/api/board?'+query);
  if(version!==boardVersion||pendingMoves.size){refreshAgain=true;return;}
  board=incoming;if(board.settings.cloud&&cloudJob)board.job=cloudJob;renderBoard();
 }catch(e){toast(e.message);}
 finally{loading=false;if(refreshAgain&&!pendingMoves.size){refreshAgain=false;queueMicrotask(refresh);}}
}
function renderBoard(){
const total=Object.values(board.totals).reduce((a,b)=>a+b,0);$('#summary').textContent=`${total.toLocaleString('fr-FR')} annonces · ${board.totals.review} à examiner · ${board.totals.kept} retenues`;
const scrolls={};document.querySelectorAll('.cards').forEach(el=>scrolls[el.dataset.stage]=el.scrollTop);
$('#board').innerHTML=Object.entries(stages).map(([key,label])=>`<section class="column" data-stage="${key}" aria-label="${label}"><div class="column-head">${label}<span class="count">${board.counts[key]}</span></div><div class="cards" data-stage="${key}">${board.columns[key].map(card).join('')||`<div class="empty"><b>Aucune annonce</b>${esc(descriptions[key])}</div>`}</div>${board.settings.cloud?`<div class="cloud-pages"><button data-page="${key}" data-delta="-25" ${offsets[key]===0?'disabled':''}>←</button><span>${offsets[key]+board.columns[key].length}/${board.counts[key]}</span><button data-page="${key}" data-delta="25" ${offsets[key]+25>=board.counts[key]?'disabled':''}>→</button></div>`:(board.counts[key]>board.columns[key].length?`<button class="more" data-more="true">Voir davantage (${board.columns[key].length}/${board.counts[key]})</button>`:'')}</section>`).join('');
document.querySelectorAll('.cards').forEach(el=>el.scrollTop=scrolls[el.dataset.stage]||0);
$('#notice').hidden=board.settings.has_key&&!board.import.error;$('#notice').textContent=board.import.error||(board.settings.cloud?'Ajoute MISTRAL_API_KEY dans les variables Vercel puis redéploie.':'Ajoute ta clé Mistral dans Réglages pour analyser les prochaines annonces. Les 100 premières analyses ont été reprises si elles étaient disponibles.');
$('#analyze').disabled=board.job.running;$('#stop').hidden=!board.job.running;$('#batch').disabled=board.job.running;
$('#job').hidden=!(board.job.running||board.job.total);$('#job').textContent=`${board.job.running?'Analyse en cours':'Dernier lot'} : ${board.job.done}/${board.job.total} analysées${board.job.skipped?' · '+board.job.skipped+' ignorée(s)':''}${board.job.failed?' · '+board.job.failed+' échec(s)':''}${board.job.error?' — '+board.job.error:''}`;
$('#sync-text').textContent=(board.settings.database||'SQLite')+' · '+(board.import.last?'Synchronisé à '+new Date(board.import.last*1000).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})+' · auto 10 s':'Import en cours…');
if(board.settings.cloud){$('.local').textContent='Pipeline en ligne';$('#sync-text').textContent='Supabase · collecte depuis ton Mac';}
}

function openSettings(){ if(board?.settings.cloud){toast('Réglages dans Vercel → Settings → Environment Variables : MISTRAL_API_KEY et MISTRAL_MODEL.');return;} $('#api-key').value='';$('#model').value=board?.settings.model||'mistral-small-latest';$('#key-status').textContent=board?.settings.has_key?'Une clé est enregistrée. Laisse le champ vide pour la conserver.':'Aucune clé enregistrée.';$('#settings').showModal();}
$('#settings-open').onclick=openSettings;
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
$('#settings-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/settings',{key:$('#api-key').value,model:$('#model').value});$('#api-key').value='';$('#settings').close();toast('Réglages enregistrés.');await refresh();}catch(e){toast(e.message);}};
$('#remove-key').onclick=async()=>{try{await api('/api/settings',{remove_key:true,model:$('#model').value});$('#settings').close();await refresh();toast('Clé retirée.');}catch(e){toast(e.message);}};
$('#analyze').onclick=async()=>{if(!board?.settings.has_key)return openSettings();if(board.settings.cloud)return runCloudBatch();try{await api('/api/analyze',{limit:Number($('#batch').value)});await refresh();}catch(e){toast(e.message);}};
$('#stop').onclick=async()=>{if(board?.settings.cloud){stopCloud=true;toast('Arrêt après l’annonce en cours.');return;}try{await api('/api/stop',{});toast('Arrêt demandé après l’annonce en cours.');}catch(e){toast(e.message);}};
$('#sync').onclick=async()=>{try{await api('/api/sync',{});await refresh();toast('Imports actualisés.');}catch(e){toast(e.message);}};
let searchTimer;$('#search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{offsets={inbox:0,review:0,kept:0,rejected:0};refresh();},250);};$('#potential').onchange=()=>{offsets={inbox:0,review:0,kept:0,rejected:0};refresh();};
function formAnalysis(){return {texte_nettoye:$('#clean').value,micro_niche:$('#niche').value||'indéterminée',consommable:$('#consumable').value,service:$('#service').value,niche_claire:$('#clear').checked,a_verifier:$('#verify').checked,commentaire:$('#reason').value};}
function eligibility(){const a=formAnalysis();$('#potential-preview').textContent='Potentiel e-commerce : '+(a.consommable==='non'&&a.service==='non'&&a.niche_claire&&a.micro_niche!=='indéterminée'?'oui':'non');}
$('#detail-form').oninput=eligibility;
async function openDetail(id){if(pendingMoves.has(id)){toast('Enregistrement en cours…');return;}try{selected=await api('/api/ad/'+id);const a=selected.analysis||{};$('#detail-title').textContent=a.micro_niche||'Annonce à analyser';$('#detail-image').innerHTML=visual(selected,true);$('#detail-reach').textContent='Portée : '+(selected.reach||'—');$('#detail-analyst').textContent=selected.analyst||'Pas encore analysée';$('#raw').textContent=selected.raw;$('#stage').value=selected.stage;$('#clean').value=a.texte_nettoye||'';$('#niche').value=a.micro_niche||'';$('#consumable').value=a.consommable||'indéterminé';$('#service').value=a.service||'indéterminé';$('#clear').checked=!!a.niche_claire;$('#verify').checked=!!a.a_verifier;$('#reason').value=a.commentaire||'';$('#detail-error').textContent=selected.error;initialAnalysis=JSON.stringify(formAnalysis());eligibility();$('#detail').showModal();}catch(e){toast(e.message);}}
$('#detail-form').onsubmit=async e=>{e.preventDefault();try{const body={stage:$('#stage').value,revision:selected.revision};const a=formAnalysis();if(JSON.stringify(a)!==initialAnalysis)body.analysis=a;await api('/api/ad/'+selected.id,body);$('#detail').close();toast('Annonce enregistrée.');await refresh();}catch(e){$('#detail-error').textContent=e.message;}};
$('#board').onclick=e=>{if(e.target.closest('select'))return;const decision=e.target.closest('[data-decision]');if(decision){move(decision.dataset.ad,decision.dataset.decision);return;}const page=e.target.closest('[data-page]');if(page){offsets[page.dataset.page]=Math.max(0,offsets[page.dataset.page]+Number(page.dataset.delta));refresh();return;}if(e.target.closest('[data-more]')){limit=Math.min(10000,limit+25);refresh();return;}const card=e.target.closest('[data-id]');if(card)openDetail(card.dataset.id);};
$('#board').onkeydown=e=>{if(e.target.matches('.card')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();openDetail(e.target.dataset.id);}};
function relocate(row,from,to,index=0){
 board.columns[from]=board.columns[from].filter(r=>r.id!==row.id);
 row.stage=to;board.columns[to].splice(Math.min(index,board.columns[to].length),0,row);
 board.counts[from]--;board.counts[to]++;board.totals[from]--;board.totals[to]++;
}
async function move(id,stage){
 if(!board||pendingMoves.has(id)||!Object.hasOwn(stages,stage))return;
 const row=Object.values(board.columns).flat().find(r=>r.id===id);
 if(!row||row.stage===stage)return;
 const from=row.stage,index=board.columns[from].findIndex(r=>r.id===id),revision=row.revision;
 pendingMoves.set(id,true);boardVersion++;relocate(row,from,stage);renderBoard();
 try{
  await api('/api/ad/'+id,{stage,revision});row.revision=revision+1;
 }catch(e){
  relocate(row,stage,from,index);toast('Déplacement non confirmé : '+e.message);
 }finally{
  pendingMoves.delete(id);boardVersion++;renderBoard();
  clearTimeout(moveRefreshTimer);moveRefreshTimer=setTimeout(refresh,250);
 }
}

$('#board').onchange=e=>{if(e.target.dataset.move)move(e.target.dataset.move,e.target.value);};
$('#board').ondragstart=e=>{const el=e.target.closest('.card');if(el){if(pendingMoves.has(el.dataset.id)){e.preventDefault();return;}e.dataTransfer.setData('text/plain',el.dataset.id);}};
$('#board').ondragover=e=>{const el=e.target.closest('.column');if(el){e.preventDefault();el.classList.add('dragover');}};
$('#board').ondragleave=e=>e.target.closest('.column')?.classList.remove('dragover');
$('#board').ondrop=e=>{e.preventDefault();const el=e.target.closest('.column');document.querySelectorAll('.dragover').forEach(x=>x.classList.remove('dragover'));if(el)move(e.dataTransfer.getData('text/plain'),el.dataset.stage);};
refresh();setInterval(()=>{if(!document.hidden&&!$('dialog[open]')&&!document.querySelector('select:focus'))refresh();},5000);

async function runCloudBatch(){
 if(cloudJob?.running)return;
 stopCloud=false;cloudJob={running:true,total:0,done:0,skipped:0,failed:0,error:''};
 try{
  const result=await api('/api/candidates',{limit:Number($('#batch').value)});
  cloudJob.total=result.rows.length;await refresh();
  if(!result.rows.length)toast('Aucune annonce avec du texte OCR en attente. Les annonces sans texte restent disponibles.');
  for(const row of result.rows){
   if(stopCloud)break;
   try{const result=await api('/api/analyze',row);cloudJob.done+=result.done;if(!result.done)cloudJob.skipped++;}
   catch(e){cloudJob.failed++;cloudJob.error=e.message;break;}
   await refresh();
  }
 }catch(e){cloudJob.error=e.message;toast(e.message);}
 finally{cloudJob.running=false;await refresh();}
}
window.addEventListener('beforeunload',e=>{if(cloudJob?.running){e.preventDefault();e.returnValue='';}});
document.querySelector('a[href="/api/export"]').onclick=async e=>{
 if(!board?.settings.cloud)return;
 e.preventDefault();const button=e.currentTarget;if(button.dataset.busy)return;
 button.dataset.busy='1';button.textContent='Export en cours…';
 try{
  let cursor={},parts=['\ufeff'];
  do{const page=await api('/api/export-page?'+new URLSearchParams(cursor));parts.push(page.csv);cursor=page.next;}while(cursor);
  const url=URL.createObjectURL(new Blob(parts,{type:'text/csv;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download='pipeline.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(e){toast(e.message);}
 finally{delete button.dataset.busy;button.textContent='Exporter CSV';}
};
