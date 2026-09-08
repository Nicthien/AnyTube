'use strict';
const assistantDialog = node('dialog', 'connector-dialog assistant-dialog');
assistantDialog.setAttribute('aria-labelledby', 'assistant-title');
document.body.append(assistantDialog);
let assistantTimer, assistantJob, assistantSource = '';
const assistantStatuses = {queued:'En attente',running:'Découverte en cours',choice:'Site à choisir',added:'Source ajoutée',ready:'Mise à jour proposée',updated:'Mise à jour appliquée',unresolved:'Découverte non résolue',access_required:'Accès nécessaire',timeout:'Délai dépassé',cancelled:'Arrêtée',interrupted:'Interrompue'};
assistantStatuses.needs_input='Proposition à préciser';
const diagnosticPhases={endpoint:'Endpoint',search:'Recherche',repeat:'Répétition de contrôle',inference:'Extraction des cartes',witness:'Recherche témoin',pagination:'Pagination',video:'Page vidéo',candidate:'Candidat',ai:'IA',task:'Découverte'};
const diagnosticOutcomes={extracted:'Résultats extraits',started:'En cours',observed:'Observé',hypothesis:'Hypothèse',confirmed:'Confirmé',accepted:'Accepté',retained:'Conservé sans ajout',passed:'Contrôle réussi',failed:'Échec',skipped:'Tentative ignorée',inconclusive:'Non concluant',unsupported:'Non pris en charge',interrupted:'Interrompu'};
const diagnosticOrigins={model:'Modèle existant',example:'Exemple fourni',form:'Formulaire GET',documentation:'Documentation',ai:'Proposition IA',browser_request:'Requête navigateur',browser_form:'Formulaire observé dans le navigateur'};
function diagnosticItem(row) {
  const item=node('li','assistant-diagnostic');
  item.append(node('strong','',`${diagnosticPhases[row.phase]||'Contrôle'} · ${diagnosticOutcomes[row.outcome]||row.outcome||''}${row.query?' · '+row.query:''}`));
  if(row.message)item.append(node('p','',row.message));
  const details=node('details');details.append(node('summary','','Données du contrôle'));
  if(row.code)details.append(node('p','hint',row.code));
  for(const [label,value] of [['Candidat',row.candidate_id],['Origine',diagnosticOrigins[row.provenance]],['URL demandée',row.requested_url],['URL finale',row.final_url],['HTTP',row.http_status],['Type de contenu',row.content_type],['Durée (s)',row.duration],['Classification',row.classification],['Raison',row.classification_reason],['Éléments inspectés',row.inspected_count],['Carte',row.card_index],['Champ manquant',row.missing_field],['Sélecteur',row.selector],['Stabilité',row.stability],['Résultats sélectionnés',row.selected_count],['Résultats valides',row.valid_count]]) {
    if(value!==undefined&&value!==null&&value!=='')details.append(node('p','',`${label} : ${value}`));
  }
  for(const example of row.examples||[])details.append(node('p','',`${example.title} — ${example.url}`));
  item.append(details);return item;
}
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
async function openSourceAssistant(source='',previous=null) {
  clearTimeout(assistantTimer);assistantJob=null;assistantSource=source;
  assistantHeader('Configurer automatiquement une source');
  if(!assistantDialog.open)assistantDialog.showModal();
  try {
    const listing=await api('/api/source-assistant/jobs');
    const form=node('form'),target=assistantField(form,'Adresse du site ou nom de la plateforme');
    target.required=true;target.maxLength=2000;
    if(previous)target.value=previous.resolved_target||previous.target;
    const minutes=assistantField(form,'Durée maximale (minutes)',String(listing.default_minutes),'number');minutes.min=1;minutes.max=60;minutes.required=true;
    const details=node('details');details.append(node('summary','','Recherches de contrôle'));
    const first=assistantField(details,'Première recherche','science'),second=assistantField(details,'Deuxième recherche','music');
    first.maxLength=100;second.maxLength=100;form.append(details);
    if(previous){first.value=previous.queries[0];second.value=previous.queries[1];minutes.value=previous.minutes;}
    const help=node('details');help.append(node('summary','','Aider la détection'));
    const videoLabel=node('label','connector-field','Liens de vidéos (un par ligne, cinq maximum)'),examples=node('textarea');
    examples.rows=3;examples.maxLength=10004;examples.value=(previous?.video_examples||[]).join('\n');videoLabel.append(examples);help.append(videoLabel);
    help.append(node('p','hint','Deux ou trois vidéos du même site aident à reconnaître les résultats.'));
    const searchExample=assistantField(help,'URL d’une recherche',previous?.search_example_url||'','url');searchExample.maxLength=2000;
    const searchTerm=assistantField(help,'Terme utilisé dans cette recherche',previous?.search_example_query||'');searchTerm.maxLength=100;
    form.append(help);if(previous)help.open=true;
    form.append(node('p','hint',source?'La mise à jour sera présentée avant application.':'Les nouvelles sources sont ajoutées automatiquement après contrôle de la recherche. La lecture vidéo reste à vérifier.'));
    const submit=node('button','primary','Découvrir la source');submit.type='submit';form.append(submit);
    form.addEventListener('submit',async event=>{event.preventDefault();submit.disabled=true;try {
      const hints={queries:[first.value,second.value],video_examples:examples.value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean),search_example_url:searchExample.value.trim(),search_example_query:searchTerm.value.trim(),minutes:Number(minutes.value)};
      const job=await api(previous?`/api/source-assistant/jobs/${previous.id}/resume`:'/api/source-assistant/jobs',{method:'POST',body:JSON.stringify(previous?hints:{...hints,target:target.value,queries:[first.value,second.value],source_id:assistantSource})});
      await showAssistantJob(job.id);
    }catch(error){assistantError(error);submit.disabled=false;}});
    assistantDialog.append(form);
    if(previous){target.readOnly=true;submit.textContent='Reprendre avec ces paramètres';}
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
  const diagnosisSummary=node('div');
  const progress=node('ol','assistant-steps'),result=node('div'),actions=node('div','dialog-actions');
  const diagnostics=node('details','assistant-diagnostics'),diagnosticRows=node('ol');
  diagnostics.append(node('summary','','Détail des contrôles'),diagnosticRows);
  assistantDialog.append(status,diagnosisSummary,progress,diagnostics,result,actions);
  let diagnosticCount=-1;
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
      status.textContent=`${assistantStatuses[job.status]||job.status} — ${job.target}${active&&job.deadline?' · Budget restant : '+Math.max(0,Math.ceil(job.deadline-Date.now()/1000))+' s':''}`;
      stop.hidden=!active;
      progress.replaceChildren(...(job.steps||[]).map(step=>node('li','',step.message)));
      if((job.diagnostics||[]).length!==diagnosticCount) {
        diagnosticCount=(job.diagnostics||[]).length;
        diagnosticRows.replaceChildren(...(job.diagnostics||[]).map(diagnosticItem));
        if(!diagnosticCount&&!job.diagnostics_version)diagnosticRows.append(node('li','','Diagnostic détaillé indisponible pour cette tentative.'));
      }
      if(!active&&!terminalRendered) {
        terminalRendered=true;diagnosisSummary.append(node('p','',job.message||''));
        if(job.next_action)diagnosisSummary.append(node('p','notice',job.next_action));
        if(job.parent_job)result.append(button('Voir la tentative précédente','secondary',()=>showAssistantJob(job.parent_job).catch(assistantError)));
        if(job.candidate?.html?.rendering==='chromium')result.append(node('p','notice','Navigateur requis pour utiliser cette source.'));
        if(job.elapsed_seconds!==undefined)result.append(node('p','hint',`Durée : ${job.elapsed_seconds} s · ${job.metrics?.search_checks||0} contrôles de recherche · ${job.metrics?.ai_calls||0} appels IA · ${job.metrics?.skipped_attempts||0} tentatives identiques évitées`));
        if(job.status==='choice') for(const choice of job.choices||[]) result.append(button(choice.url,'secondary full',async()=>{try {const next=await api(`/api/source-assistant/jobs/${id}/choose`,{method:'POST',body:JSON.stringify({url:choice.url})});await showAssistantJob(next.id);}catch(e){assistantError(e);}}));
        if(job.candidate||job.evidence) {const details=node('details');details.append(node('summary','','Configuration et preuves'),node('pre','connector-json',JSON.stringify({candidate:job.candidate,evidence:job.evidence,changes:job.changes},null,2)));result.append(details);}
        if(job.status==='ready')result.append(button('Appliquer la mise à jour','primary',async()=>{try {await api(`/api/source-assistant/jobs/${id}/apply`,{method:'POST'});await loadSources();await showAssistantJob(id);}catch(e){assistantError(e);}}));
        if(job.status==='needs_input'&&job.candidate)result.append(button('Préciser la configuration','secondary',()=>{assistantDialog.close();openSourceEditor(null,job.candidate).catch(assistantError);}));
        if(['added','updated'].includes(job.status))await loadSources();
        if(job.status!=='choice')result.append(button('Ajouter des exemples et reprendre','secondary',()=>openSourceAssistant(job.source_id,job).catch(assistantError)));
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
    if(name==='browser')section.append(node('p','hint','URL de la passerelle AnyTube (port 8010), pas celle de Browserless. La passerelle peut utiliser Chromium ou votre serveur Browserless v2 et contrôle les accès réseau.'));
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
