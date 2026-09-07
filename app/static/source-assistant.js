'use strict';
const assistantDialog = node('dialog', 'connector-dialog assistant-dialog');
assistantDialog.setAttribute('aria-labelledby', 'assistant-title');
document.body.append(assistantDialog);
let assistantTimer, assistantJob, assistantSource = '';
const assistantStatuses = {queued:'En attente',running:'Découverte en cours',choice:'Site à choisir',added:'Source ajoutée',ready:'Mise à jour proposée',updated:'Mise à jour appliquée',unresolved:'Découverte non résolue',access_required:'Accès nécessaire',timeout:'Délai dépassé',cancelled:'Arrêtée',interrupted:'Interrompue'};
assistantStatuses.needs_input='Proposition à préciser';
function assistantHeader(title) {
  assistantDialog.replaceChildren();
  const header=node('div','dialog-header'), heading=node('h2','',title);
  heading.id='assistant-title';
  const close=button('✕','icon-button',()=>assistantDialog.close());close.setAttribute('aria-label','Fermer');
  header.append(heading,close);assistantDialog.append(header);
}
function assistantField(parent,label,value='',type='text') {
  const wrapper=node('label','connector-field',label),input=node('input');
  input.type=type;input.value=value;wrapper.append(input);parent.append(wrapper);return input;
}
function assistantSelect(parent,label,options,value) {
  const wrapper=node('label','connector-field',label),input=node('select');
  for(const [key,text] of options) {const option=node('option','',text);option.value=key;input.append(option);}
  input.value=value;wrapper.append(input);parent.append(wrapper);return input;
}
function assistantError(error) {toast(error.message || 'Opération impossible.');}
async function openSourceAssistant(source='') {
  clearTimeout(assistantTimer);assistantJob=null;assistantSource=source;
  assistantHeader('Configurer automatiquement une source');
  if(!assistantDialog.open)assistantDialog.showModal();
  try {
    const listing=await api('/api/source-assistant/jobs');
    const form=node('form'),target=assistantField(form,'Adresse du site ou nom de la plateforme');
    target.required=true;target.maxLength=2000;
    const minutes=assistantField(form,'Durée maximale (minutes)',String(listing.default_minutes),'number');minutes.min=1;minutes.max=60;minutes.required=true;
    const details=node('details');details.append(node('summary','','Recherches de contrôle'));
    const first=assistantField(details,'Première recherche','science'),second=assistantField(details,'Deuxième recherche','music');
    first.maxLength=100;second.maxLength=100;form.append(details);
    form.append(node('p','hint',source?'La mise à jour sera présentée avant application.':'Les nouvelles sources sont ajoutées automatiquement après contrôle de la recherche. La lecture vidéo reste à vérifier.'));
    const submit=node('button','primary','Découvrir la source');submit.type='submit';form.append(submit);
    form.addEventListener('submit',async event=>{event.preventDefault();submit.disabled=true;try {
      const job=await api('/api/source-assistant/jobs',{method:'POST',body:JSON.stringify({target:target.value,minutes:Number(minutes.value),queries:[first.value,second.value],source_id:assistantSource})});
      await showAssistantJob(job.id);
    }catch(error){assistantError(error);submit.disabled=false;}});
    assistantDialog.append(form);
    if(state.account?.admin)assistantDialog.append(button('Paramètres de découverte','secondary',()=>openAssistantSettings().catch(assistantError)));
    if(listing.items.length) {
      assistantDialog.append(node('h3','','Découvertes récentes'));
      for(const job of listing.items)assistantDialog.append(button(`${job.target} — ${assistantStatuses[job.status]||job.status}`,'secondary full',()=>showAssistantJob(job.id).catch(assistantError)));
    }
  }catch(error){assistantDialog.append(node('p','danger',error.message));}
}
async function showAssistantJob(id) {
  clearTimeout(assistantTimer);assistantJob=id;
  assistantHeader('Découverte de la source');
  const status=node('p','notice','Chargement du bilan…');status.setAttribute('aria-live','polite');
  const progress=node('ol','assistant-steps'),result=node('div'),actions=node('div','dialog-actions');
  assistantDialog.append(status,progress,result,actions);
  const stop=button('Arrêter','secondary',async()=>{try {await api(`/api/source-assistant/jobs/${id}/cancel`,{method:'POST'});await refresh();}catch(e){assistantError(e);}});
  stop.hidden=true;
  const back=button('Toutes les découvertes','secondary',()=>openSourceAssistant().catch(assistantError));actions.append(stop,back);
  let terminalRendered=false;
  async function refresh() {
    if(!assistantDialog.open||assistantJob!==id)return;
    try {
      const job=await api(`/api/source-assistant/jobs/${id}`);
      if(assistantJob!==id||!assistantDialog.open)return;
      const active=['queued','running'].includes(job.status);
      status.textContent=`${assistantStatuses[job.status]||job.status} — ${job.target}${active&&job.deadline?' · '+Math.max(0,Math.ceil(job.deadline-Date.now()/1000))+' s restantes':''}`;
      stop.hidden=!active;
      progress.replaceChildren(...(job.steps||[]).map(step=>node('li','',step.message)));
      if(!active&&!terminalRendered) {
        terminalRendered=true;result.append(node('p','',job.message||''));
        if(job.elapsed_seconds!==undefined)result.append(node('p','hint',`Durée : ${job.elapsed_seconds} s · ${job.metrics?.search_checks||0} contrôles de recherche · ${job.metrics?.ai_calls||0} appels IA`));
        if(job.status==='choice') for(const choice of job.choices||[]) result.append(button(choice.url,'secondary full',async()=>{try {const next=await api(`/api/source-assistant/jobs/${id}/choose`,{method:'POST',body:JSON.stringify({url:choice.url})});await showAssistantJob(next.id);}catch(e){assistantError(e);}}));
        if(job.candidate||job.evidence) {const details=node('details');details.append(node('summary','','Configuration et preuves'),node('pre','connector-json',JSON.stringify({candidate:job.candidate,evidence:job.evidence,changes:job.changes},null,2)));result.append(details);}
        if(job.status==='ready')result.append(button('Appliquer la mise à jour','primary',async()=>{try {await api(`/api/source-assistant/jobs/${id}/apply`,{method:'POST'});await loadSources();await showAssistantJob(id);}catch(e){assistantError(e);}}));
        if(job.status==='needs_input'&&job.candidate)result.append(button('Préciser la configuration','secondary',()=>{assistantDialog.close();openSourceEditor(null,job.candidate).catch(assistantError);}));
        if(['added','updated'].includes(job.status))await loadSources();
        if(!['choice','ready'].includes(job.status))result.append(button('Relancer','secondary',async()=>{try {const next=await api('/api/source-assistant/jobs',{method:'POST',body:JSON.stringify({target:job.resolved_target||job.target,minutes:job.minutes,queries:job.queries,source_id:job.source_id})});await showAssistantJob(next.id);}catch(e){assistantError(e);}}));
      }
      if(active)assistantTimer=setTimeout(refresh,2000);
    }catch(e){status.textContent=e.message;}
  }
  await refresh();
}
assistantDialog.addEventListener('close',()=>{clearTimeout(assistantTimer);assistantJob=null;});

async function openAssistantSettings() {
  clearTimeout(assistantTimer);assistantJob=null;
  const config=await api('/api/source-assistant/settings');
  assistantHeader('Paramètres de découverte');
  if(!assistantDialog.open)assistantDialog.showModal();
  const form=node('form'),minutes=assistantField(form,'Durée par défaut (minutes)',config.minutes,'number');minutes.min=1;minutes.max=60;
  const fields={};
  for(const [name,title] of [['search','Recherche web'],['ai','Intelligence artificielle'],['browser','Navigateur public']]) {
    const section=node('fieldset');section.append(node('legend','',title));const s=config[name],f={};fields[name]=f;
    if(name==='search')f.kind=assistantSelect(section,'Protocole',[['searxng','SearXNG JSON'],['json','HTTP JSON adaptable']],s.kind);
    if(name==='ai')f.kind=assistantSelect(section,'Fournisseur',[['none','Sans IA'],['ollama','Ollama'],['openai','API compatible OpenAI']],s.kind);
    f.url=assistantField(section,name==='ai'?'URL du serveur (API compatible : inclure /v1)':'URL du service',s.url,'url');
    if(name==='ai') {f.model=assistantField(section,'Modèle',s.model);section.append(node('p','hint','Le fournisseur choisi est le seul utilisé. Aucun plafond financier ni basculement automatique.'));}
    if(name==='search') {
      f.method=assistantSelect(section,'Méthode',[['GET','GET'],['POST','POST']],s.method);
      for(const [key,label] of [['parameter','Paramètre de recherche'],['results','Chemin de la liste'],['title','Chemin du titre'],['link','Chemin de l’URL'],['description','Chemin de description']])f[key]=assistantField(section,label,s[key]);
    }
    f.secret=assistantField(section,name==='search'?'En-têtes secrets (objet JSON)':'Jeton du service', '', 'password');
    f.secret.autocomplete='new-password';f.secret.placeholder=s.has_secret?'Secret conservé si ce champ reste vide':'Facultatif';
    f.clear_secret=assistantField(section,'Effacer le secret enregistré','','checkbox');
    const preview=node('pre','connector-json');preview.hidden=true;
    section.append(button('Enregistrer et tester','secondary',async()=>{try {await save();const response=await api(`/api/source-assistant/settings/test/${name}`,{method:'POST'});preview.hidden=false;preview.textContent=JSON.stringify(response,null,2);}catch(e){preview.hidden=false;preview.textContent=e.message;}}),preview);
    form.append(section);
  }
  async function save() {
    const body={minutes:Number(minutes.value)};
    for(const name of ['search','ai','browser']) {const {has_secret,...base}=config[name];body[name]={...base};for(const [key,input] of Object.entries(fields[name]))body[name][key]=key==='clear_secret'?input.checked:input.value;}
    const saved=await api('/api/source-assistant/settings',{method:'PUT',body:JSON.stringify(body)});
    for(const name of ['search','ai','browser']) {config[name]=saved[name];fields[name].secret.value='';fields[name].clear_secret.checked=false;}
  }
  const submit=node('button','primary','Enregistrer');submit.type='submit';form.append(submit);
  form.addEventListener('submit',async event=>{event.preventDefault();try {await save();toast('Paramètres enregistrés.');}catch(e){assistantError(e);}});
  assistantDialog.append(form,button('Retour','secondary',()=>openSourceAssistant().catch(assistantError)));
}
const launchAssistant=()=>openSourceAssistant().catch(assistantError);
$('add-source').after(button('Découvrir une source','secondary',launchAssistant));
$('catalog-query').before(button('Découvrir automatiquement','secondary full',()=>{$('catalog-dialog').close();launchAssistant();}));
editorActions.prepend(button('Analyser cette source','secondary',()=>{const id=editedSource?.id||'';editor.close();openSourceAssistant(id).catch(assistantError);}));
