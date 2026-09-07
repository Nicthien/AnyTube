'use strict';
let adaptivePlayer = null;
let streamSession = null;
let streamVersion = 0;
let destroyStream = Promise.resolve();
const playbackControls = node('div', 'dialog-actions'); $('player').after(playbackControls);

function streamSelect(label) {
  const holder = node('label', 'connector-field', label), select = node('select'); holder.append(select); playbackControls.append(holder); return select;
}
async function closeStream() {
  streamVersion++;
  const previous = adaptivePlayer; adaptivePlayer = null;
  const session = streamSession; streamSession = null;
  playbackControls.replaceChildren();
  if (session) api(`/api/playback/${session.id}`, {method:'DELETE'}).catch(()=>{});
  if (previous) { destroyStream = previous.destroy().catch(()=>{}); await destroyStream; }
  for (const track of $('player').querySelectorAll('track')) track.remove();
}
$('player-dialog').addEventListener('close', closeStream);

async function streamVideo(url, title, sourceId = null) {
  await closeStream();
  await destroyStream;
  resetPlayer();
  const version = ++streamVersion, run = ++state.playerId;
  $('player-title').textContent = title; $('player-status').textContent = 'Recherche des flux disponibles…';
  if (!$('player-dialog').open) $('player-dialog').showModal();
  try {
    const result = await api('/api/playback', {method:'POST', signal:AbortSignal.timeout(70000), body:JSON.stringify({url, source_id:sourceId})});
    if (version !== streamVersion || run !== state.playerId) { api(`/api/playback/${result.id}`, {method:'DELETE'}).catch(()=>{}); return; }
    streamSession = result;
    $('player-title').textContent = result.video.title;
    $('player-description').textContent = result.video.description;
    const choiceSelect = streamSelect('Flux');
    result.choices.forEach((choice, index) => option(choiceSelect, String(index), choice.label));
    const quality = streamSelect('Qualité'), language = streamSelect('Piste audio'), subtitles = streamSelect('Sous-titres');
    const goLive = button('Revenir au direct', 'secondary', () => { if(adaptivePlayer) $('player').currentTime = adaptivePlayer.seekRange().end; });
    goLive.hidden = !result.is_live; playbackControls.append(goLive);
    playbackControls.append(button('Préparer un fichier local', 'secondary', async () => { await closeStream(); await prepareVideo(url, result.video.title, sourceId); }));
    if(!result.is_live) playbackControls.append(button('Conserver l’audio', 'secondary', async()=>{try{await api('/api/media',{method:'POST',body:JSON.stringify({url,source_id:sourceId,media_kind:'audio',destination:'library'})});toast('Préparation audio démarrée.');}catch(e){toast(e.message);}}));
    let choiceVersion = 0;
    async function loadChoice(index) {
      const selectedVersion = ++choiceVersion;
      choiceSelect.disabled = true;
      const existing = adaptivePlayer; adaptivePlayer = null;
      if(existing) await existing.destroy();
      if(version !== streamVersion || selectedVersion !== choiceVersion) return;
      const video = $('player'); video.pause(); video.removeAttribute('src'); video.load(); video.hidden = false;
      quality.replaceChildren(); language.replaceChildren(); subtitles.replaceChildren();
      const choice = result.choices[index];
      quality.parentElement.hidden = language.parentElement.hidden = !choice.adaptive;
      if (choice.adaptive) {
        shaka.polyfill.installAll();
        if(!shaka.Player.isBrowserSupported()) throw new Error('La lecture adaptative n’est pas disponible sur ce navigateur. Utilisez la préparation locale.');
        const player = new shaka.Player(); adaptivePlayer = player; await player.attach(video);
        player.configure({streaming:{retryParameters:{maxAttempts:3}}, manifest:{retryParameters:{maxAttempts:3}}});
        player.getNetworkingEngine().registerRequestFilter((type, request) => {
          for (const uri of request.uris) {
            const parsed = new URL(uri, location.href);
            if(parsed.origin !== location.origin || !parsed.pathname.startsWith(`/api/playback/${result.id}/resource/`)) throw new Error('Ressource extérieure au relais refusée.');
          }
        });
        player.addEventListener('error', () => { if(version === streamVersion) $('player-status').textContent = 'Lecture interrompue. Le flux a expiré ou la source est indisponible. Rouvrez le média ou préparez un fichier local.'; });
        await player.load(choice.url, undefined, choice.mime);
        if(version !== streamVersion || selectedVersion !== choiceVersion) return;
        for(const entry of result.subtitles) {
          try {
            await player.addTextTrackAsync(entry.url, entry.language, 'subtitles', 'text/vtt');
          } catch(error) {
            console.warn('Impossible de charger une piste de sous-titres externe.', error);
          }
          if(version !== streamVersion || selectedVersion !== choiceVersion) return;
        }
        option(quality, 'auto', 'Automatique');
        const variants = player.getVariantTracks();
        for(const track of variants) option(quality, String(track.id), `${track.height ? track.height+'p' : 'Audio'} · ${track.language || ''}`);
        quality.onchange = () => { player.configure({abr:{enabled:quality.value==='auto'}}); const selected=variants.find(t=>String(t.id)===quality.value);if(selected)player.selectVariantTrack(selected,true); };
        const languages = [...new Set(variants.map(t=>t.language).filter(Boolean))];
        for(const code of languages) option(language,code,code);
        language.onchange = () => player.selectAudioLanguage(language.value);
        option(subtitles, 'none', 'Désactivés');
        for(const track of player.getTextTracks()) option(subtitles,String(track.id),track.language||track.label||'Sous-titres');
        subtitles.onchange = () => {const selected=player.getTextTracks().find(t=>String(t.id)===subtitles.value);if(selected)player.selectTextTrack(selected);player.setTextTrackVisibility(Boolean(selected));};
      } else {
        video.src = choice.url;
        option(subtitles, 'none', 'Désactivés');
        for(const track of video.querySelectorAll('track')) track.remove();
        result.subtitles.forEach((entry,index)=>{const track=node('track');track.src=entry.url;track.kind='subtitles';track.srclang=entry.language;track.label=entry.language;video.append(track);option(subtitles,String(index),entry.language);});
        subtitles.onchange=()=>{[...video.textTracks].forEach((track,index)=>{track.mode=String(index)===subtitles.value?'showing':'disabled';});};
      }
      if(version !== streamVersion || selectedVersion !== choiceVersion) return;
      state.playing = result.is_live ? null : {url,video:result.video};
      if(!result.is_live) {
        const saved=state.personal?.find(item=>item.url===url);
        if(saved?.position) video.addEventListener('loadedmetadata',()=>{if(version===streamVersion && saved.position < video.duration-5) video.currentTime=saved.position;},{once:true});
      }
      $('player-status').textContent = result.is_live ? 'Lecture en direct via votre serveur' : 'Lecture via votre serveur';
      choiceSelect.disabled = false;
    }
    choiceSelect.addEventListener('change', () => loadChoice(Number(choiceSelect.value)).catch(e=>{$('player-status').textContent=e.message;choiceSelect.disabled=false;}));
    await loadChoice(0);
  } catch(e) {
    if(version !== streamVersion) return;
    $('player-status').textContent = e.message;
    playbackControls.append(button('Préparer un fichier local', 'secondary', async()=>{await closeStream();await prepareVideo(url,title,sourceId);}));
  }
}

const collectionDialog=node('dialog','connector-dialog');collectionDialog.setAttribute('aria-labelledby','collection-heading');document.body.append(collectionDialog);
function browseCollection(initialUrl = '', initialSourceId = null) {
  collectionDialog.replaceChildren();const heading=node('h2','','Chaîne ou playlist');heading.id='collection-heading';collectionDialog.append(heading,button('Fermer','secondary',()=>collectionDialog.close()));
  const form=node('form'),label=node('label','connector-field','URL de la collection'),input=node('input');input.type='url';input.required=true;label.append(input);form.append(label);
  const submit=node('button','primary','Parcourir');form.append(submit);collectionDialog.append(form);
  const status=node('p','hint');status.setAttribute('aria-live','polite');const list=node('div');collectionDialog.append(status,list);
  input.value=initialUrl;
  let cursor=null, collectionUrl='', collectionId=initialSourceId; const seen=new Set();
  const more=button('Charger davantage','secondary',()=>load(true));more.hidden=true;collectionDialog.append(more);
  async function load(append){submit.disabled=more.disabled=true;status.textContent='Chargement…';try{if(!append){cursor=null;collectionUrl=input.value.trim();seen.clear();list.replaceChildren();}
    const result=await api('/api/collections',{method:'POST',signal:AbortSignal.timeout(70000),body:JSON.stringify({url:collectionUrl,cursor,source_id:collectionId})});
    collectionId=result.source_id;cursor=result.next_cursor;more.hidden=!cursor;status.textContent=result.title;
    for(const item of result.items){if(seen.has(item.url))continue;seen.add(item.url);const row=node('div','catalog-row');if(item.non_media || item.access_required){row.append(node('span','',item.title),node('span','hint',item.non_media?'Publication sans média audio ou vidéo':'Accès requis sur Patreon'));const link=node('a','secondary','Ouvrir la publication');link.href=safeUrl(item.url)||'#';link.target='_blank';link.rel='noopener noreferrer';row.append(link);list.append(row);continue;}row.append(node('span','',item.title),button('Lire','secondary',()=>streamVideo(item.url,item.title,collectionId)),button('Ajouter à la file','secondary',()=>{playQueue.push({...item,source_id:collectionId});toast(`${playQueue.length} média(s) dans la file.`);}),button('Conserver','secondary',async()=>{try{await api('/api/media',{method:'POST',body:JSON.stringify({url:item.url,source_id:collectionId,destination:'library'})});toast('Préparation démarrée.');}catch(e){toast(e.message);}}));list.append(row);}
  }catch(e){status.textContent=e.message;}finally{submit.disabled=more.disabled=false;}}
  form.addEventListener('submit',event=>{event.preventDefault();collectionId=null;load(false);});collectionDialog.showModal();input.focus();
  if(initialUrl) load(false);
}
const openCollection=button('Parcourir une chaîne ou playlist','secondary',()=>browseCollection());$('open-url').after(openCollection);
const playQueue=[];
const nextQueued=button('Lire le prochain de la file','secondary',()=>{const item=playQueue.shift();if(item)streamVideo(item.url,item.title,item.source_id);else toast('La file de lecture est vide.');});$('open-url').after(nextQueued);
$('player').addEventListener('ended',()=>{if(playQueue.length){const item=playQueue.shift();streamVideo(item.url,item.title,item.source_id);}});
