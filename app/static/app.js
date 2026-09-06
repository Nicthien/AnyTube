'use strict';
const $ = (id) => document.getElementById(id);
const state = { sources: [], catalog: [], selected: null, deleting: null, page: 'explore', searchId: 0, playerId: 0, segments: [], homeMode: true, homeVersion: 0 };
const icons = { Youtube: '▶', Dailymotion: 'd', Soundcloud: '☁' };
const searchControls=node('div','filters');searchControls.hidden=true;$('filter-hint').after(searchControls);
function searchSelect(label,choices){const holder=node('label','connector-field',label),select=node('select');for(const [value,text] of choices){const opt=node('option','',text);opt.value=value;select.append(opt);}holder.append(select);searchControls.append(holder);select.addEventListener('change',()=>{if(state.searchQuery)runSearch(state.searchQuery);});return select;}
const searchRanking=searchSelect('Classement',[['default','Pertinence'],['views','Plus vues'],['recent','Nouveautés'],['trending','Tendances']]);
const searchDuration=searchSelect('Durée',[['any','Toutes'],['short','Moins de 4 minutes'],['long','Plus de 20 minutes']]);
const searchDays=searchSelect('Publication',[['0','Toutes les dates'],['1','24 heures'],['7','7 jours'],['30','30 jours']]);
const searchMore=button('Charger davantage','secondary',()=>runSearch(state.searchQuery,true));searchMore.hidden=true;$('results').after(searchMore);
function readPref(key, fallback) { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } }
function savePref(key, value) { try { localStorage.setItem(key, value); } catch { /* Private browser storage may be unavailable. */ } }
document.documentElement.dataset.theme = readPref('anytube-theme', matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
$('sponsor-setting').checked = readPref('anytube-sponsor', 'true') === 'true';
function node(tag, className, text) { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = text; return el; }
function button(text, className, action) { const el = node('button', className, text); el.type = 'button'; el.addEventListener('click', action); return el; }
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { signal: AbortSignal.timeout(path === '/api/search' ? 125000 : 20000), ...options, headers: { 'Content-Type': 'application/json', 'X-AnyTube': '1', ...options.headers } });
  } catch (error) {
    throw new Error(error.name === 'TimeoutError' ? 'Le serveur met trop de temps à répondre. Réessayez dans un instant.' : 'Connexion au serveur interrompue. Vérifiez votre connexion.');
  }
  const body = await response.json();
  if(response.status===401)window.dispatchEvent(new Event('anytube-session-expired'));
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'La requête est invalide. Vérifiez les champs.');
  return body;
}
let toastTimer;
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5500); }
function showPage(page, searching = false) {
  state.page = page;
  document.querySelectorAll('.page').forEach(el => { el.hidden = el.id !== `page-${page}`; });
  document.querySelectorAll('[data-page]').forEach(el => { el.classList.toggle('active', el.dataset.page === page); if (el.dataset.page === page) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current'); });
  if (page === 'downloads') loadDownloads();
  if (page === 'explore' && !searching) { state.searchId++; $('search-button').disabled = false; showHome(); }
}
document.querySelectorAll('[data-page]').forEach(el => el.addEventListener('click', () => showPage(el.dataset.page)));
document.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', () => el.closest('dialog').close()));
$('theme').addEventListener('click', () => { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; savePref('anytube-theme', theme); });
$('sponsor-setting').addEventListener('change', () => savePref('anytube-sponsor', String($('sponsor-setting').checked)));
async function loadSources() {
  state.sources = (await api('/api/sources')).items;
  if (state.selected !== null) state.selected = state.selected.filter(id => state.sources.some(s => s.id === id && s.enabled && s.search));
  if (state.selected?.length === 0) state.selected = null;
  renderSources(); renderFilters();
  if (state.homeMode) loadHome();
}
function applySourceFilter() {
  if (state.selected?.length === 0) state.selected = null;
  renderFilters();
  if(typeof persistPreferences==='function')persistPreferences();
  if (state.homeMode) {
    document.querySelectorAll('.home-section').forEach(section => {
      section.hidden = state.selected !== null && !state.selected.includes(section.dataset.sourceId);
    });
  } else if (state.searchQuery) runSearch(state.searchQuery);
}
function renderFilters() {
  const chosen=state.sources.filter(s=>s.enabled&&s.search&&(state.selected===null||state.selected.includes(s.id)));
  for(const opt of searchRanking.options){opt.disabled=chosen.some(s=>!s.capabilities?.search_rankings.includes(opt.value));}
  if(searchRanking.selectedOptions[0]?.disabled)searchRanking.value='default';
  searchDuration.disabled=!chosen.length||chosen.some(s=>!s.capabilities?.duration);if(searchDuration.disabled)searchDuration.value='any';
  searchDays.disabled=!chosen.length||chosen.some(s=>!s.capabilities?.date);if(searchDays.disabled)searchDays.value='0';
  searchDuration.title=searchDays.title='Ces filtres nécessitent leur prise en charge par toutes les sources sélectionnées.';
  const all = button('Toutes les sources', 'chip', () => { state.selected = null; applySourceFilter(); });
  all.setAttribute('aria-pressed', String(state.selected === null));
  $('filters').replaceChildren(all);
  state.sources.filter(s => s.enabled && s.search).forEach(source => {
    const chip = button(source.name, 'chip', () => {
      if (state.selected === null) state.selected = [source.id];
      else if (state.selected.includes(source.id)) state.selected = state.selected.filter(id => id !== source.id);
      else state.selected.push(source.id);
      applySourceFilter();
    });
    chip.setAttribute('aria-pressed', String(state.selected?.includes(source.id) ?? false)); $('filters').append(chip);
  });
  const count = state.sources.filter(s => s.enabled && s.search).length;
  $('filter-hint').textContent = state.selected === null ? `${count} source(s) avec recherche · Choisissez plusieurs sources pour affiner.` : `${state.selected.length} source(s) sélectionnée(s) · Filtrage automatique.`;
}
function renderSources() {
  $('source-list').replaceChildren();
  if (!state.sources.length) { $('source-list').append(node('div', 'empty', 'Aucune source. Ajoutez votre première plateforme.')); return; }
  for (const source of state.sources) {
    const row = node('div', 'source-row'); const details = node('div', 'source-detail');
    details.append(node('h3', '', source.name), node('p', '', source.search ? (source.connector.extractor ? 'Recherche de vidéos + ouverture par URL' : 'Recherche · aucun extracteur de lecture associé') : 'URL uniquement · pas de recherche intégrée'));
    const check=source.verifications?.filter(entry=>entry.feature==='search').at(-1);
    const labels={verified:'Recherche vérifiée',empty:'Résultat vide',temporarily_unavailable:'Temporairement indisponible',authentication_required:'Authentification requise',not_exposed:'Fonctionnalité non exposée',to_develop:'À développer'};
    details.append(node('p','hint',check?`${labels[check.status]||check.status} · ${new Date(check.date).toLocaleString('fr')} · yt-dlp ${check.yt_dlp}`:'Aucune vérification actuelle pour cette configuration.'));
    const proofDetails=node('details');proofDetails.append(node('summary','','Vérifications par fonction'));
    const proofList=node('div');proofDetails.append(proofList);details.append(proofDetails);
    proofDetails.addEventListener('toggle',async()=>{if(!proofDetails.open||proofList.childElementCount)return;try{const result=await api(`/api/sources/${encodeURIComponent(source.id)}/evidence`);for(const proof of result.items){proofList.append(node('p','hint',`${proof.feature} · ${labels[proof.status]||proof.status} · ${proof.obsolete?'historique, à revérifier':'révision actuelle'} · ${new Date(proof.date).toLocaleString('fr')} · ${proof.environment||'environnement non renseigné'}`));}if(!result.items.length)proofList.append(node('p','hint','Aucun essai enregistré.'));}catch(e){proofList.append(node('p','danger',e.message));}});
    const toggle = button(source.enabled ? 'Activée' : 'Désactivée', 'switch', async () => {
      toggle.disabled = true;
      try { await api(`/api/sources/${encodeURIComponent(source.id)}`, { method: 'PATCH', body: JSON.stringify({ enabled: !source.enabled }) }); await loadSources(); }
      catch (e) { toast(e.message); toggle.disabled = false; }
    });
    toggle.setAttribute('role', 'switch'); toggle.setAttribute('aria-checked', String(source.enabled)); toggle.setAttribute('aria-label', `Activer ${source.name}`);
    const remove = button('✕', 'icon-button danger', () => { state.deleting = source; $('delete-text').textContent = `${source.name} et sa configuration seront retirées de vos sources. Les paramètres personnalisés ne seront pas conservés.`; $('delete-error').textContent = ''; $('delete-dialog').showModal(); });
    remove.setAttribute('aria-label', `Supprimer ${source.name}`);
    const edit = button('Configurer', 'secondary', () => openSourceEditor(source));
    edit.setAttribute('aria-label', `Configurer ${source.name}`);
    row.append(node('div', 'source-avatar', icons[source.id] || source.name[0].toUpperCase()), details, edit, toggle, remove); $('source-list').append(row);
  }
}
$('delete-source').addEventListener('click', async () => {
  $('delete-source').disabled = true;
  try { await api(`/api/sources/${encodeURIComponent(state.deleting.id)}`, { method: 'DELETE' }); await loadSources(); $('delete-dialog').close(); toast('Source supprimée.'); }
  catch (e) { $('delete-error').textContent = e.message; }
  finally { $('delete-source').disabled = false; }
});
$('add-source').addEventListener('click', async () => {
  $('catalog-dialog').showModal(); $('catalog-status').textContent = 'Chargement du catalogue…'; $('catalog-query').value = '';
  try { state.catalog = (await api('/api/catalog')).items; renderCatalog(); } catch (e) { $('catalog-status').textContent = e.message; }
});
$('catalog-query').addEventListener('input', renderCatalog);
function renderCatalog() {
  const query = $('catalog-query').value.toLocaleLowerCase();
  const items = state.catalog.filter(s => s.name.toLocaleLowerCase().includes(query));
  $('catalog-status').textContent = `${items.length} extracteur(s) · ${Math.min(items.length, 80)} affiché(s). Affinez avec un nom.`;
  $('catalog-results').replaceChildren(...items.slice(0, 80).map(source => {
    const row = node('div', 'catalog-row'); const detail = node('div');
    detail.append(node('strong', '', source.name), node('small', '', source.search ? 'Modèle de recherche prérempli' : 'Modèle URL uniquement · recherche non configurée'));
    if (source.last_check) {
      const labels = {results_received:'résultats reçus', empty:'aucun résultat', failed:'échec de connexion ou d’extraction',
        authentication_required:'authentification requise', rate_limited:'quota ou filtrage de la plateforme',
        geo_restricted:'restriction géographique', drm_protected:'protégé par DRM',
        timeout:'délai dépassé', invalid_response:'réponse invalide',
        temporarily_unavailable:'indisponible au moment de l’essai'};
      detail.append(node('small', '', `Essai historique (à revérifier) du ${new Date(source.last_check.date).toLocaleDateString('fr')} : ${labels[source.last_check.status] || 'non testé'}.`));
    }
    const preview = node('details'); preview.append(node('summary', '', 'Voir le modèle'));
    const model = node('pre', 'connector-json'); preview.append(model); detail.append(preview);
    preview.addEventListener('toggle', async () => {
      if (!preview.open || model.textContent) return;
      model.textContent = 'Chargement…';
      try { model.textContent = JSON.stringify((await api(`/api/templates/${encodeURIComponent(source.id)}`)).connector, null, 2); }
      catch (e) { model.textContent = e.message; }
    });
    const exists = state.sources.some(s => s.id === source.id);
    const add = button(exists ? 'Ajoutée' : 'Ajouter', 'secondary', async () => {
      add.disabled = true;
      try { await api('/api/sources', { method: 'POST', body: JSON.stringify({ id: source.id }) }); await loadSources(); renderCatalog(); toast(`${source.name} ajoutée.`); }
      catch (e) { $('catalog-status').textContent = e.message; add.disabled = false; }
    }); add.disabled = exists; row.append(detail, add); return row;
  }));
}
function duration(value) { if (!Number.isFinite(value)) return ''; const seconds = Math.floor(value); return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`; }
function safeUrl(value) { try { const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) ? u.href : null; } catch { return null; } }
function renderCard(item) {
  const card = node('article', 'card'); const thumb = button('', 'thumbnail', () => streamVideo(item.url, item.title, item.source_id)); thumb.setAttribute('aria-label', `Regarder ${item.title}`);
  const placeholder = node('span', 'placeholder', '▷'); thumb.append(placeholder);
  if (safeUrl(item.thumbnail)) { const img = node('img'); img.src = item.thumbnail; img.alt = ''; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer'; img.addEventListener('error', () => img.remove()); thumb.append(img); placeholder.hidden = true; img.addEventListener('error', () => { placeholder.hidden = false; }); }
  if (duration(item.duration)) thumb.append(node('span', 'duration', duration(item.duration)));
  const content = node('div', 'card-content'); const title = node('h3'); title.append(button(item.title, 'title-button', () => streamVideo(item.url, item.title, item.source_id)));
  content.append(node('span', 'source-badge', item.source), title, node('div', 'metadata', [item.channel, item.published ? new Date(item.published).toLocaleDateString('fr') : '', Number.isFinite(item.views) ? `${new Intl.NumberFormat('fr', { notation: 'compact' }).format(item.views)} vues` : ''].filter(Boolean).join(' · ')), node('p', 'description', item.description || 'Description non fournie par cette source.'));
  const actions=node('div','dialog-actions');
  actions.append(button('Conserver','secondary',async()=>{try{await api('/api/media',{method:'POST',body:JSON.stringify({url:item.url,source_id:item.source_id,destination:'library'})});toast('Préparation dans votre bibliothèque.');}catch(e){toast(e.message);}}),button('☆ Favori','secondary',async()=>{try{await api('/api/personal',{method:'PUT',body:JSON.stringify({url:item.url,title:item.title,favorite:true})});toast('Ajouté à vos favoris.');}catch(e){toast(e.message);}}));
  content.append(actions);card.append(thumb, content); return card;
}
$('search-form').addEventListener('submit', event => {
  event.preventDefault();
  const query = $('query').value.trim();
  if (query) runSearch(query);
});
async function runSearch(query,append=false) {
  showPage('explore', true);
  if (state.selected?.length === 0) { toast('Sélectionnez au moins une source.'); return; }
  state.searchQuery = query;
  showSearchResults();
  const id = ++state.searchId; $('search-button').disabled = true;searchMore.disabled=true;if(!append){state.searchItems=[];state.searchCursors=null;$('results').replaceChildren();} $('empty').hidden = true; $('search-notices').replaceChildren(); $('result-count').textContent = ''; $('results-title').textContent = 'Recherche en cours…';
  $('search-notices').append(node('div', 'notice', 'Les sources sont interrogées en parallèle. Certaines peuvent prendre jusqu’à une minute.'));
  try {
    const result = await api('/api/search', { method: 'POST', body: JSON.stringify({ query, sources: state.selected,cursors:append?state.searchCursors:null,ranking:searchRanking.value,duration:searchDuration.value,days:Number(searchDays.value) }) }); if (id !== state.searchId) return;
    $('search-notices').replaceChildren();
    for (const error of result.errors) $('search-notices').append(node('div', 'notice', `${error.source} : ${error.message}`));
    if (result.skipped.length) $('search-notices').append(node('div', 'notice', `Sources URL uniquement non interrogées : ${result.skipped.join(', ')}.`));
    const seen=new Set(state.searchItems.map(item=>item.url));const fresh=result.items.filter(item=>{if(seen.has(item.url))return false;seen.add(item.url);return true;});state.searchItems.push(...fresh);
    state.searchCursors=result.next_cursors;searchMore.hidden=!Object.keys(result.next_cursors||{}).length;
    $('results-title').textContent = `Résultats pour « ${query} »`; $('result-count').textContent = `${state.searchItems.length} média(s)`;
    $('results').append(...fresh.map(renderCard));
    if (!state.searchItems.length) $('search-notices').append(node('div', 'empty', result.errors.length ? 'Aucune vidéo reçue. Consultez les erreurs des sources ci-dessus, puis réessayez.' : 'Aucun résultat. Essayez d’autres mots-clés ou ajoutez des sources.'));
  } catch (e) { if (id === state.searchId) { $('results-title').textContent = 'Recherche interrompue'; $('search-notices').replaceChildren(node('div', 'notice', e.message)); } }
  finally { if (id === state.searchId){ $('search-button').disabled = false;searchMore.disabled=false;} }
}
document.querySelectorAll('[data-query]').forEach(el => el.addEventListener('click', () => { $('query').value = el.dataset.query; $('search-form').requestSubmit(); }));
$('open-url').addEventListener('click', () => $('url-dialog').showModal());
$('url-form').addEventListener('submit', event => { event.preventDefault(); $('url-dialog').close(); streamVideo($('video-url').value.trim(), 'Votre média'); });
function resetPlayer() { state.playing=null; $('keep-video').hidden=true; const video = $('player'); video.pause(); video.removeAttribute('src'); video.load(); video.hidden = true; $('download-file').hidden = true; $('player-description').textContent = ''; $('sponsor-status').textContent = ''; state.segments = []; }
$('player-dialog').addEventListener('close', () => { state.playerId++; resetPlayer(); });
async function prepareVideo(url, title, sourceId = null) {
  await closeStream();
  resetPlayer(); const run = ++state.playerId; $('player-title').textContent = title; $('player-status').textContent = 'Préparation sur le serveur… La lecture sera disponible une fois le fichier chargé (10 minutes maximum).'; if (!$('player-dialog').open) $('player-dialog').showModal();
  try {
    const job = await api('/api/media', { method: 'POST', body: JSON.stringify({ url, source_id:sourceId }) });
    let result = job;
    while (result.status === 'preparing') {
      await new Promise(resolve => setTimeout(resolve, 1600)); if (run !== state.playerId) return;
      result = await api(`/api/media/${job.id}`);
      $('player-status').textContent=`Préparation : ${result.progress||0} %`;
    }
    if (run !== state.playerId) return;
    if (result.status !== 'ready') throw new Error(result.error || 'Préparation annulée.');
    await showVideo(result, run);
  } catch (e) { if (run === state.playerId) $('player-status').textContent = e.message; }
}
async function showVideo(job, run) {
  await closeStream();
  if(run!==state.playerId)return;
  state.playing=job;
  $('player-title').textContent = job.video.title; $('player-status').textContent = 'Lecture locale · aucun lecteur publicitaire tiers';
  $('player').src = `/api/media/${job.id}/file`; $('player').hidden = false;
  try{const saved=(await api('/api/personal')).items.find(item=>item.url===job.url);if(run!==state.playerId)return;const position=saved?.position||0;const resume=()=>{if(run===state.playerId&&position<$('player').duration-5)$('player').currentTime=position;};if($('player').readyState>=1)resume();else $('player').addEventListener('loadedmetadata',resume,{once:true});}catch{}
  $('keep-video').hidden=job.destination==='library';
  $('player-description').textContent = job.video.description;
  $('download-file').href = `/api/media/${job.id}/file?download=true`; $('download-file').hidden = false;
  if ($('sponsor-setting').checked && /(?:youtube\.com|youtu\.be)/.test(job.url)) {
    $('sponsor-status').textContent = 'Recherche des segments SponsorBlock…';
    try {
      const result = await api(`/api/sponsors/${encodeURIComponent(job.video.id)}`); if (run !== state.playerId) return;
      state.segments = result.segments;
      $('sponsor-status').textContent = result.status === 'unavailable' ? 'SponsorBlock indisponible. La vidéo reste lisible.' : `${result.segments.length} segment(s) sponsorisé(s) signalé(s) · SponsorBlock`;
    } catch { if (run === state.playerId) $('sponsor-status').textContent = 'SponsorBlock indisponible.'; }
  }
}
$('player').addEventListener('timeupdate', () => {
  if (!$('sponsor-setting').checked) return;
  const video = $('player');
  const skip = state.segments.find(s => s.actionType === 'skip' && Array.isArray(s.segment) && Number.isFinite(s.segment[0]) && Number.isFinite(s.segment[1]) && s.segment[1] > s.segment[0] && video.currentTime >= s.segment[0] && video.currentTime < s.segment[1] && s.segment[1] <= video.duration && (!s.videoDuration || Math.abs(s.videoDuration - video.duration) <= 2));
  if (skip) { video.currentTime = skip.segment[1]; $('sponsor-status').textContent = 'Segment sponsorisé passé · SponsorBlock'; }
});
$('player').addEventListener('error', () => { if ($('player').getAttribute('src')) $('player-status').textContent = 'Ce fichier ne peut pas être lu par votre navigateur. Vous pouvez le télécharger.'; });
async function loadDownloads() {
  try {
    const { items } = await api('/api/media'); $('download-list').replaceChildren();
    if (!items.length) $('download-list').append(node('div', 'empty', 'Aucune vidéo préparée. Ouvrez une vidéo depuis les résultats ou collez son URL.'));
    for (const job of items) {
      const row = node('div', 'download-row'); const detail = node('div'); detail.append(node('h3', '', job.video?.title || job.url), node('p', '', `${job.destination==='library'?'Bibliothèque conservée':'Cache temporaire'} · ${job.status === 'ready' ? 'Prête · MP4' : ['error','cancelled'].includes(job.status) ? job.error : `Préparation : ${job.progress||0} %`}`)); row.append(detail);
      if (job.status === 'ready') {
        row.append(button('Lire', 'secondary', async () => { resetPlayer(); const run = ++state.playerId; $('player-dialog').showModal(); await showVideo(job, run); }));
        const link = node('a', 'primary', 'Télécharger'); link.href = `/api/media/${job.id}/file?download=true`; row.append(link);
        if(job.destination!=='library')row.append(button('Conserver','secondary',async()=>{try{await api(`/api/media/${job.id}/keep`,{method:'POST'});await loadDownloads();}catch(e){toast(e.message);}}));
      }
      if(['error','cancelled'].includes(job.status))row.append(button('Réessayer','secondary',async()=>{try{await api('/api/media',{method:'POST',body:JSON.stringify({url:job.url,destination:job.destination||'cache'})});await loadDownloads();}catch(e){toast(e.message);}}));
      row.append(button(job.status==='preparing'?'Annuler':job.destination==='library'?'Supprimer de la bibliothèque':'Retirer du cache','secondary', async () => { try { if(job.destination==='library'&&job.status==='ready'&&!await demanderSuppression('Supprimer définitivement cette vidéo de votre bibliothèque ?'))return;await api(`/api/media/${job.id}`, { method: 'DELETE' }); await loadDownloads(); } catch (e) { toast(e.message); } }));
      $('download-list').append(row);
    }
  } catch (e) { $('download-list').replaceChildren(node('div', 'notice', e.message)); }
}
$('refresh-downloads').addEventListener('click', loadDownloads);
let lastHistorySave=0;
$('player').addEventListener('timeupdate',()=>{if(state.playing&&Date.now()-lastHistorySave>10000){lastHistorySave=Date.now();api('/api/personal',{method:'PUT',body:JSON.stringify({url:state.playing.url,title:state.playing.video.title,position:$('player').currentTime})}).catch(()=>{});}});
const keepVideo=button('Conserver dans ma bibliothèque','secondary',async()=>{try{await api(`/api/media/${state.playing.id}/keep`,{method:'POST'});keepVideo.hidden=true;toast('Vidéo conservée.');}catch(e){toast(e.message);}});keepVideo.id='keep-video';keepVideo.hidden=true;$('player-dialog').append(keepVideo);
function demanderSuppression(message){return new Promise(resolve=>{const dialog=node('dialog'),title=node('h2','',message);title.id='delete-media-title';dialog.setAttribute('aria-labelledby',title.id);dialog.append(title);let result=false;const actions=node('div','dialog-actions');actions.append(button('Annuler','secondary',()=>dialog.close()),button('Supprimer','primary',()=>{result=true;dialog.close();}));dialog.append(actions);dialog.addEventListener('close',()=>{dialog.remove();resolve(result);},{once:true});document.body.append(dialog);dialog.showModal();});}
