'use strict';
// Screen pixels and user input are transient; never put them in application state.
async function openBrowserSession(url, source = '', existing = '', onValidated = null) {
  const dialog = node('dialog', 'connector-dialog browser-session-dialog');
  dialog.setAttribute('aria-labelledby', 'browser-session-title');
  const title = node('h2', '', 'Session du site'); title.id = 'browser-session-title';
  const header = node('div', 'dialog-header');
  const message = node('p', 'notice', 'Ouverture de Chromium…'); message.setAttribute('aria-live', 'polite');
  const address = node('p', 'browser-session-address', url);
  const canvas = node('canvas', 'browser-session-screen'); canvas.width = 1280; canvas.height = 800;
  canvas.tabIndex = 0; canvas.setAttribute('aria-label', 'Navigateur distant. Échap rend le clavier à AnyTube.');
  const input = node('input'); input.type = 'file'; input.accept = '.pdf,.jpg,.jpeg,.png';
  const fileLabel = node('label', 'connector-field', 'Envoyer un fichier au champ sélectionné (PDF, JPEG, PNG, 20 Mo)');
  fileLabel.append(input); input.disabled = true;
  const controls = node('div', 'dialog-actions');
  const textLabel=node('label','connector-field','Saisie dans le site (clavier mobile)'),textInput=node('input');
  textInput.type='password';textInput.autocomplete='off';textInput.maxLength=4000;textLabel.append(textInput);
  const sendText=button('Envoyer le texte','secondary',()=>{send({type:'text',text:textInput.value});textInput.value='';});
  let socket, identifier, completed = false;
  header.append(title, button('✕', 'icon-button', () => dialog.close()));
  dialog.append(header, address, message,
    node('p', 'hint', 'Effectuez vous-même les vérifications du site. Caméra et microphone indisponibles. Le site reçoit les informations que vous saisissez ou envoyez.'),
    canvas, textLabel, sendText, fileLabel, controls);
  document.body.append(dialog); dialog.showModal();
  const send = value => { if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(value)); };
  const resizeScreen = () => {
    const mobile=window.innerWidth<600;
    const width=mobile?Math.max(320,window.innerWidth-64):1280,height=mobile?600:800;
    if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
    send({type:'resize',width,height});
  };
  window.addEventListener('resize',resizeScreen);
  const finish = button('Enregistrer la session et reprendre', 'primary', async () => {
    finish.disabled = true;
    try {
      await api(`/api/browser-sessions/${identifier}/validate`, {method: 'POST'});
      completed = true; dialog.close();
      if (onValidated) await onValidated(identifier);
    } catch (error) { message.textContent = error.message; finish.disabled = false; }
  });
  finish.disabled = true;
  controls.append(finish, button('Fermer', 'secondary', () => dialog.close()));
  dialog.addEventListener('close', () => {
    socket?.close();
    window.removeEventListener('resize',resizeScreen);
    if (identifier && !completed) api(`/api/browser-sessions/${identifier}/close`, {method:'POST'}).catch(() => {});
    input.value = ''; textInput.value=''; canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height); dialog.remove();
  }, {once: true});
  canvas.addEventListener('pointerdown', event => {
    canvas.focus(); canvas.setPointerCapture(event.pointerId);
    mouse(event, 'mousePressed'); event.preventDefault();
  });
  canvas.addEventListener('pointerup', event => mouse(event, 'mouseReleased'));
  function mouse(event, kind) {
    const rect = canvas.getBoundingClientRect();
    send({type:'mouse', event:kind, x:Math.max(0,Math.min(canvas.width,(event.clientX-rect.left)*canvas.width/rect.width)),
      y:Math.max(0,Math.min(canvas.height,(event.clientY-rect.top)*canvas.height/rect.height)), dx:event.deltaX||0, dy:event.deltaY||0});
  }
  canvas.addEventListener('wheel', event => { mouse(event, 'mouseWheel'); event.preventDefault(); }, {passive:false});
  canvas.addEventListener('keydown', event => {
    if (event.key === 'Escape') { finish.focus(); event.preventDefault(); return; }
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    event.preventDefault();
    send(event.key.length === 1 ? {type:'text',text:event.key} : {type:'key',key:event.key,shift:event.shiftKey});
  });
  canvas.addEventListener('paste', event => { event.preventDefault(); send({type:'text',text:event.clipboardData.getData('text').slice(0,4000)}); });
  input.addEventListener('change', async () => {
    const file = input.files[0]; if (!file) return;
    input.disabled = true;
    try {
      if (file.size > 20*1024*1024) throw new Error('Fichier limité à 20 Mo.');
      const response = await fetch(`/api/browser-sessions/${identifier}/file`, {method:'POST',headers:{'X-AnyTube':'1','Content-Type':'application/octet-stream'},body:file});
      if (!response.ok) throw new Error((await response.json()).detail || 'Envoi impossible.');
      message.textContent = 'Fichier transmis au champ du site.';
    } catch (error) { message.textContent = error.message; }
    finally { input.value = ''; }
  });
  try {
    const session = existing ? await api(`/api/browser-sessions/${existing}`) : await api('/api/browser-sessions', {method:'POST',body:JSON.stringify({url,source})});
    identifier = session.id;
    await api(`/api/browser-sessions/${identifier}/open`, {method:'POST'});
    if (!dialog.open) { await api(`/api/browser-sessions/${identifier}/close`, {method:'POST'}); return; }
    socket = new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/browser-sessions/${identifier}/screen`);
    socket.addEventListener('open', () => { resizeScreen(); finish.disabled=false; message.textContent='Session ouverte. Conservation maximale : 30 jours après votre validation explicite.'; canvas.focus(); });
    socket.addEventListener('message', async event => {
      const value = JSON.parse(event.data);
      address.textContent = value.url; input.disabled = !value.file_requested;
      if (value.type !== 'frame') return;
      const bytes = Uint8Array.from(atob(value.image), c => c.charCodeAt(0));
      const image = await createImageBitmap(new Blob([bytes], {type:'image/jpeg'}));
      if (dialog.open) canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
      image.close();
    });
    socket.addEventListener('close', event => { if (!completed) message.textContent=`Connexion à la session fermée (${event.code}). Rouvrez-la pour continuer.`; });
    socket.addEventListener('error', () => { message.textContent='Connexion interactive impossible.'; });
  } catch (error) { message.textContent=error.message; }
}

async function showBrowserSessions() {
  const dialog=node('dialog','connector-dialog');
  const title=node('h2','','Sessions des sites');title.id='browser-sessions-title';dialog.setAttribute('aria-labelledby',title.id);
  dialog.append(title,button('Fermer','secondary',()=>dialog.close()));
  document.body.append(dialog);dialog.showModal();dialog.addEventListener('close',()=>dialog.remove(),{once:true});
  try {
    const listing=await api('/api/browser-sessions');
    if(!listing.items.length)dialog.append(node('p','','Aucune session enregistrée.'));
    for(const session of listing.items) {
      const row=node('section');row.append(node('h3','',session.site),node('p','hint',`Expiration : ${new Date(session.expires*1000).toLocaleString()}`));
      row.append(button('Ouvrir la session','secondary',()=>openBrowserSession(session.site,session.source,session.id).catch(assistantError)),
        button('Renouveler la session','secondary',()=>openBrowserSession(session.site,session.source).catch(assistantError)),
        button('Supprimer la session','secondary',async()=>{try{await api(`/api/browser-sessions/${session.id}`,{method:'DELETE'});row.remove();}catch(error){assistantError(error);}}));
      dialog.append(row);
    }
  }catch(error){dialog.append(node('p','danger',error.message));}
}

async function openNetworkSettings() {
  const config=await api('/api/network/settings');
  const dialog=node('dialog','connector-dialog');const heading=node('h2','','Réseau sortant');heading.id='network-heading';dialog.setAttribute('aria-labelledby',heading.id);
  dialog.append(heading,button('Fermer','secondary',()=>dialog.close()));
  const form=node('form');
  const mode=assistantSelect(form,'Trajet des flux publics',[['direct','Direct'],['proxy','Proxy HTTP/HTTPS'],['vpn','VPN intégré']],config.mode);
  const address=assistantField(form,'Adresse IP et port du proxy',config.proxy_url,'url');
  address.placeholder='http://192.168.0.5:8888';
  const tls=assistantField(form,'Nom du certificat pour un proxy HTTPS (facultatif)',config.tls_name);
  const protocol=assistantSelect(form,'Protocole VPN',[['wireguard','WireGuard'],['openvpn','OpenVPN']],config.vpn_protocol);
  const username=assistantField(form,'Utilisateur du proxy (facultatif)');username.autocomplete='off';
  const password=assistantField(form,'Mot de passe du proxy (facultatif)','','password');password.autocomplete='new-password';
  password.placeholder=config.has_credentials?'Identifiants conservés si les deux champs restent vides':'';
  const clear=assistantField(form,'Effacer les identifiants enregistrés','','checkbox');
  form.append(node('p','hint','Le service VPN Compose doit être configuré et démarré sur le serveur. Le changement de trajet ferme les connexions en cours et impose de recontrôler les sessions. Aucun retour automatique vers Direct.'));
  const result=node('p','notice');result.setAttribute('aria-live','polite');
  const save=node('button','primary','Appliquer le trajet');save.type='submit';
  form.append(save,button('Tester le trajet actuel','secondary',async()=>{try{const value=await api('/api/network/test',{method:'POST'});result.textContent=value.message+(value.public_ip?' Adresse publique : '+value.public_ip:'');}catch(error){result.textContent=error.message;}}));
  form.addEventListener('submit',async event=>{
    event.preventDefault();save.disabled=true;
    try {
      await api('/api/network/settings',{method:'PUT',body:JSON.stringify({mode:mode.value,proxy_url:address.value,tls_name:tls.value,vpn_protocol:protocol.value,username:username.value,password:password.value,clear_credentials:clear.checked})});
      username.value='';password.value='';clear.checked=false;result.textContent='Trajet enregistré. Testez sa disponibilité avant de reprendre les sources.';
    }catch(error){result.textContent=error.message;}finally{save.disabled=false;}
  });
  dialog.append(form,result);document.body.append(dialog);dialog.showModal();dialog.addEventListener('close',()=>dialog.remove(),{once:true});
}
