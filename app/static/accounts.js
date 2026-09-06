'use strict';
const accountDialog = node('dialog', 'connector-dialog');
accountDialog.setAttribute('aria-labelledby','account-heading');
document.body.append(accountDialog);
let signedIn = false;
let preferenceTimer;
const accountButton = button('Mon compte','secondary',openAccount);
document.querySelector('.topbar').append(accountButton);
function labeled(parent,text,type='text',value='') {
  const label = node('label','connector-field',text), input=node('input');
  input.type=type; input.value=value; label.append(input); parent.append(label); return input;
}
function persistPreferences() {
  if (!signedIn) return;
  clearTimeout(preferenceTimer);
  preferenceTimer=setTimeout(() => api('/api/account/preferences',{method:'PUT',body:JSON.stringify({theme:document.documentElement.dataset.theme,sponsor:$('sponsor-setting').checked,selected:state.selected,ranking:homeRanking})}).catch(e=>toast(e.message)),350);
}
$('theme').addEventListener('click',persistPreferences);
$('sponsor-setting').addEventListener('change',persistPreferences);
accountDialog.addEventListener('cancel',event=>{if(!signedIn)event.preventDefault();});
window.addEventListener('anytube-session-expired',()=>{if(signedIn){signedIn=false;location.reload();}});

async function bootAccount() {
  try {
    const info=await api('/api/account/me');
    if(!info.user){showLogin(info.setup_required);return;}
    state.account=info.user; signedIn=true;
    const prefs=info.preferences;
    if(prefs.theme)document.documentElement.dataset.theme=prefs.theme;
    if(typeof prefs.sponsor==='boolean')$('sponsor-setting').checked=prefs.sponsor;
    state.selected=prefs.selected??null;homeRanking=prefs.ranking||'default';
    [...rankingControls.children].forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.ranking===homeRanking)));
    document.querySelector('.shell').hidden=false;
    await loadSources();
    state.personal=(await api('/api/personal')).items;
  }catch(e){showLogin(false);accountDialog.append(node('p','notice',e.message));}
}
function showLogin(setup,invited=false) {
  const invite=new URLSearchParams(location.hash.slice(1)).get('invite');
  const joining=!setup&&(invited||!!invite);
  accountDialog.replaceChildren();
  const title=node('h2','',setup?'Installer AnyTube':joining?'Rejoindre la famille':'Connexion à AnyTube');title.id='account-heading';accountDialog.append(title);
  accountDialog.append(node('p','hint',setup?'Le jeton à usage unique figure dans les journaux du serveur.':'Chaque compte possède ses propres sources et sa bibliothèque.'));
  const form=node('form'),name=labeled(form,'Nom du compte'),password=labeled(form,'Mot de passe (12 caractères minimum)','password');
  name.required=true;name.maxLength=80;name.autocomplete='username';password.required=true;password.minLength=12;password.maxLength=200;password.autocomplete=setup||joining?'new-password':'current-password';
  const token=setup||joining?labeled(form,setup?'Jeton d’installation':'Jeton d’invitation','password',invite||''):null;
  if(token)token.required=true;
  const error=node('p','danger');error.setAttribute('aria-live','polite');
  const submit=node('button','primary',setup?'Créer le compte administrateur':joining?'Créer mon compte':'Se connecter');submit.type='submit';form.append(error,submit);
  form.addEventListener('submit',async event=>{
    event.preventDefault();submit.disabled=true;
    try{
      await api(`/api/account/${setup?'setup':joining?'join':'login'}`,{method:'POST',body:JSON.stringify({name:name.value.trim(),password:password.value,...(token?{token:token.value.trim()}:{})})});
      history.replaceState(null,'',location.pathname);accountDialog.close();await bootAccount();
    }catch(e){error.textContent=e.message;}finally{submit.disabled=false;}
  });
  accountDialog.append(form);
  if(!setup)accountDialog.append(button(joining?'J’ai déjà un compte':'J’ai une invitation','secondary',()=>{history.replaceState(null,'',location.pathname);showLogin(false,!joining);}));
  if(!accountDialog.open)accountDialog.showModal();name.focus();
}
async function openAccount() {
  accountDialog.replaceChildren();const header=node('div','dialog-header');
  const title=node('h2','',state.account.name);title.id='account-heading';
  const close=button('✕','icon-button',()=>accountDialog.close());close.setAttribute('aria-label','Fermer mon compte');header.append(title,close);accountDialog.append(header);
  const actions=node('div','dialog-actions');actions.append(button('Déconnexion','secondary',async()=>{await api('/api/account/logout',{method:'POST'});location.reload();}),button('Déconnecter tous mes appareils','secondary',async()=>{await api('/api/account/sessions',{method:'DELETE'});location.reload();}));accountDialog.append(actions);
  const form=node('form');form.append(node('h3','','Changer mon mot de passe'));
  const old=labeled(form,'Mot de passe actuel','password'),next=labeled(form,'Nouveau mot de passe','password');old.required=true;next.required=true;next.minLength=12;old.autocomplete='current-password';next.autocomplete='new-password';
  const save=node('button','primary','Enregistrer le mot de passe');form.append(save);form.addEventListener('submit',async event=>{event.preventDefault();save.disabled=true;try{await api('/api/account/password',{method:'POST',body:JSON.stringify({current_password:old.value,new_password:next.value})});old.value='';next.value='';toast('Mot de passe modifié ; les autres sessions ont été révoquées.');}catch(e){toast(e.message);}finally{save.disabled=false;}});accountDialog.append(form);
  if(state.account.admin){
    const invitation=node('div');invitation.append(node('h3','','Inviter un membre'));
    const link=labeled(invitation,'Lien privé d’invitation');link.readOnly=true;
    invitation.append(button('Créer une invitation valable 7 jours','secondary',async()=>{try{const result=await api('/api/admin/invitations',{method:'POST'});link.value=`${location.origin}/#invite=${result.token}`;link.select();}catch(e){toast(e.message);}}));accountDialog.append(invitation);
    const members=node('div');accountDialog.append(members);
    try {
      const result=await api('/api/admin/users');
      for(const user of result.items){
        const row=node('form');row.append(node('h3','',user.name));const quota=labeled(row,'Quota bibliothèque (Go)','number',String(user.quota/1024**3));quota.min='0.5';quota.step='0.5';quota.required=true;
        const enabled=labeled(row,'Compte désactivé','checkbox');enabled.checked=!!user.disabled;enabled.disabled=user.id===state.account.id;
        row.append(node('button','secondary','Enregistrer le compte'));row.addEventListener('submit',async event=>{event.preventDefault();try{await api(`/api/admin/users/${user.id}`,{method:'PATCH',body:JSON.stringify({quota:Math.round(Number(quota.value)*1024**3),disabled:enabled.checked})});toast('Compte mis à jour.');}catch(e){toast(e.message);}});members.append(row);
      }
      const diagnostic=await api('/api/admin/diagnostics');accountDialog.append(node('h3','','État du serveur'),node('p','hint',`Espace disponible : ${(diagnostic.disk.free/1024**3).toFixed(1)} Go · Préparations : ${diagnostic.jobs.preparing} · Tâches en erreur : ${diagnostic.jobs.error}`));
      const settings=await api('/api/admin/limits');const form=node('form');form.append(node('h3','','Limites du serveur'));
      const cache=labeled(form,'Cache global (Go)','number',String(settings.cache_bytes/1024**3)),hours=labeled(form,'Durée du cache (heures)','number',String(settings.cache_hours)),parallel=labeled(form,'Préparations simultanées','number',String(settings.preparations));cache.min='0.5';cache.step='0.5';hours.min='1';parallel.min='1';parallel.max='4';
      const maximum=labeled(form,'Taille maximale par média (Mo)','number',String((settings.media_bytes||500*1024**2)/1024**2)),height=labeled(form,'Résolution maximale des fichiers vidéo (p)','number',String(settings.max_height||720));maximum.min='1';maximum.max='10240';height.min='144';height.max='2160';
      form.append(node('button','secondary','Enregistrer les limites'));form.addEventListener('submit',async event=>{event.preventDefault();try{await api('/api/admin/limits',{method:'PUT',body:JSON.stringify({cache_bytes:Math.round(Number(cache.value)*1024**3),cache_hours:Number(hours.value),preparations:Number(parallel.value),media_bytes:Math.round(Number(maximum.value)*1024**2),max_height:Number(height.value)})});toast('Limites mises à jour.');}catch(e){toast(e.message);}});accountDialog.append(form);
    }catch(e){accountDialog.append(node('p','notice',e.message));}
  }
  if(!accountDialog.open)accountDialog.showModal();
}
const personalPage=node('section','page');personalPage.id='page-personal';personalPage.hidden=true;document.querySelector('main').append(personalPage);
const personalNav=button('Favoris et historique','',async()=>{showPage('personal');await loadPersonal();});personalNav.dataset.page='personal';document.querySelector('.nav').append(personalNav);
async function loadPersonal(){
  try{
    state.personal=(await api('/api/personal')).items;personalPage.replaceChildren(node('h2','','Favoris et historique'));
    const grid=node('div','grid');
    for(const item of state.personal){const card=node('article','card');card.append(node('h3','',item.title||item.url),node('p','hint',item.favorite?'Favori':`Reprise à ${duration(item.position)}`),button('Regarder','secondary',()=>prepareVideo(item.url,item.title)),button(item.favorite?'Retirer des favoris':'Ajouter aux favoris','secondary',async()=>{await api('/api/personal',{method:'PUT',body:JSON.stringify({...item,favorite:!item.favorite})});await loadPersonal();}));grid.append(card);}
    personalPage.append(grid,button('Effacer mon historique','secondary',async()=>{await api('/api/personal',{method:'DELETE'});await loadPersonal();}));
  }catch(e){toast(e.message);}
}
bootAccount();
