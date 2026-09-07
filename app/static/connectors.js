'use strict';
let editedSource = null;
let editorVersion = 0;
let editorBaseConfig = {};
const editor = node('dialog', 'connector-dialog'); editor.id = 'connector-dialog'; editor.setAttribute('aria-labelledby', 'connector-title');
const editorHeader = node('div', 'dialog-header'); const editorTitle = node('h2', '', 'Configurer une source'); editorTitle.id = 'connector-title';
const closeEditor = button('✕', 'icon-button', () => editor.close()); closeEditor.setAttribute('aria-label', 'Fermer la configuration'); editorHeader.append(editorTitle, closeEditor);
const editorForm = node('form'); const editorFields = node('fieldset'); editorFields.className = 'connector-fields';
const editorError = node('p', 'danger'); editorError.setAttribute('aria-live', 'polite');
const inputs = {};
function field(parent, key, title, placeholder = '', tag = 'input') {
  const label = node('label', 'connector-field', title); const input = node(tag); input.id = `connector-${key}`;
  if (tag === 'input') { input.type = 'text'; input.placeholder = placeholder; input.maxLength = 2000; }
  inputs[key] = input; label.append(input); parent.append(label); return input;
}
function option(select, value, text) { const el = node('option', '', text); el.value = value; select.append(el); }
const general = node('div', 'connector-grid');
field(general, 'name', 'Nom de la source', 'Ma plateforme').required = true;
const kind = field(general, 'kind', 'Type de recherche', '', 'select');
option(kind, 'json', 'API JSON'); option(kind, 'ytdlp', 'Recherche intégrée à yt-dlp'); option(kind, 'url', 'URL vidéo uniquement');
editorFields.append(general);
const credentialSelect = field(editorFields, 'credential_id', 'Accès privé à utiliser', '', 'select');
const mediaCredentialSelect = field(editorFields, 'media_credential_id', 'Cookies pour la lecture (facultatif)', '', 'select');
editorFields.append(node('p', 'hint', 'Créez un accès dans Mes accès aux plateformes. API JSON : clé, jeton ou cookies ; yt-dlp : cookies importés. Les valeurs restent dans le coffre.'));
const extractor = field(editorFields, 'extractor', 'Extracteur de lecture yt-dlp (facultatif)', 'Dailymotion, Youtube, Vimeo…');
extractor.setAttribute('list', 'extractor-options'); const extractorOptions = node('datalist'); extractorOptions.id = 'extractor-options'; editorFields.append(extractorOptions);
editorFields.append(node('p', 'hint', 'L’extracteur permet à AnyTube de reconnaître les liens pour la lecture. Sans extracteur, la recherche reste disponible, mais la lecture doit être couverte par une autre source activée.'));
const ytFields = node('div'); const prefix = field(ytFields, 'prefix', 'Préfixe de recherche yt-dlp', '', 'select');
ytFields.append(node('p', 'hint', 'yt-dlp gère les appels au site et ses métadonnées dans son propre code. Pour définir toi-même une URL et ses champs, choisis API JSON.'));
editorFields.append(ytFields);
const jsonFields = node('div');
const searchUrlFields = node('div');
field(searchUrlFields, 'search_url', 'URL de recherche (facultative avec yt-dlp)', 'https://exemple.org/api/videos?q={query}&limit={limit}');
searchUrlFields.append(node('p', 'hint', 'Avec yt-dlp, une URL de recherche reconnue par son extracteur remplace le préfixe. Les vignettes et métadonnées sont extraites automatiquement.'));
editorFields.append(searchUrlFields);
jsonFields.append(node('p', 'hint', '{query} est remplacé par la recherche ; {limit} par le nombre de résultats. Les identifiants sont transmis uniquement aux domaines exacts autorisés.'));
const methodSelect = field(jsonFields, 'method', 'Méthode HTTP', '', 'select'); option(methodSelect, 'GET', 'GET'); option(methodSelect, 'POST', 'POST avec corps JSON');
const bodyInput = field(jsonFields, 'body', 'Corps JSON pour POST (champs simples)', '', 'textarea'); bodyInput.rows = 3; bodyInput.placeholder = '{"query":"{query}","limit":"{limit}"}';
const pageSelect = field(jsonFields, 'pagination_mode', 'Pagination', '', 'select');
option(pageSelect, 'single', 'Première page uniquement (pagination non vérifiée)');
option(pageSelect, 'prefix', 'Rechargement limité à 100 résultats'); option(pageSelect, 'page', 'Numéro de page (première page : 1)'); option(pageSelect, 'offset', 'Position dans les résultats (première position : 0)');
field(jsonFields, 'pagination_parameter', 'Paramètre de page ou de position', 'page');
field(jsonFields, 'pagination_more', 'Chemin du booléen « page suivante » (facultatif)', '/has_more');
field(jsonFields, 'results_path', 'Chemin de la liste des résultats', '/list');
field(jsonFields, 'results_total_path', 'Chemin du nombre total de résultats (facultatif)', '/count');
field(jsonFields, 'result_base_url', 'Adresse de base des liens relatifs (facultatif)', 'https://exemple.org/');
const durationUnit = field(jsonFields, 'duration_unit', 'Unité des durées renvoyées', '', 'select');
option(durationUnit, 'seconds', 'Secondes'); option(durationUnit, 'milliseconds', 'Millisecondes');
jsonFields.append(node('p', 'hint', 'Chemins JSON Pointer : /data/videos pour un tableau imbriqué ; vide si la réponse est directement un tableau. /owner.screenname désigne une clé contenant un point. Utilise ~1 pour un / dans une clé, ~0 pour un ~.'));
field(jsonFields, 'video_url', 'Modèle d’URL vidéo (facultatif)', 'https://exemple.org/video/{id}');
field(jsonFields, 'thumbnail_url', 'Modèle d’URL vignette (facultatif)', 'https://exemple.org/image/{id}');
jsonFields.append(node('p', 'hint', 'Si renseigné, ce modèle utilise l’identifiant et remplace le champ URL vidéo ci-dessous.'));
const mappingFields = node('div', 'connector-grid');
const mappingLabels = {id:'Identifiant', title:'Titre', url:'URL vidéo', thumbnail:'Vignette', description:'Description', channel:'Auteur / chaîne', duration:'Durée', views:'Nombre de vues', published:'Date de publication (ISO ou secondes Unix)'};
for (const [key, label] of Object.entries(mappingLabels)) field(mappingFields, `map-${key}`, label, `/${key}`);
jsonFields.append(node('h3', '', 'Champs dans chaque résultat'), mappingFields, node('p', 'hint', 'Laisse vide un champ facultatif absent de l’API. Le titre et une URL vidéo sont obligatoires.')); editorFields.append(jsonFields);
const homeFields = node('div'); homeFields.append(node('h3', '', 'Vidéos de la page d’accueil'));
field(homeFields, 'home_query', 'Recherche utilisée à l’accueil', 'vidéos');
const homeUrlField = field(homeFields, 'home_url', 'URL du flux d’accueil (facultatif)', 'https://exemple.org/api/videos?limit={limit}');
const rankingFields = node('div');
for (const [key, label] of Object.entries({trending:'Tendances', views:'Plus vues', recent:'Nouveautés'})) field(rankingFields, `home_${key}_url`, `Flux — ${label} (facultatif)`, 'https://exemple.org/api/videos?limit={limit}');
rankingFields.append(node('p', 'hint', 'Avec une API JSON, ces flux réutilisent les champs ci-dessous. Avec yt-dlp, utilisez une page de résultats ou une playlist reconnue. Une URL renseignée prend la priorité sur le classement intégré.'));
homeFields.append(rankingFields);
homeFields.append(node('p', 'hint', 'L’accueil affiche les 10 premiers résultats de cette recherche. Une URL de flux, si renseignée, prend la priorité. Ce n’est pas une sélection personnalisée par la plateforme.')); editorFields.append(homeFields);
const rawDetails = node('details'); rawDetails.append(node('summary', '', 'Voir la configuration JSON')); const rawConfig = node('pre', 'connector-json'); rawDetails.append(rawConfig); editorFields.append(rawDetails);
const testRow = node('div', 'connector-test'); field(testRow, 'query', 'Recherche de test', 'chat');
const testButton = button('Tester sans enregistrer', 'secondary', testDraft); testRow.append(testButton); editorFields.append(testRow);
const testStatus = node('p', 'hint'); testStatus.setAttribute('aria-live', 'polite');
const testPreview = node('pre', 'connector-json'); testPreview.hidden = true;
editorFields.append(testStatus, testPreview);
const editorActions = node('div', 'dialog-actions'); const duplicate = button('Enregistrer une copie', 'secondary', () => saveDraft(true));
const cancel = button('Annuler', 'secondary', () => editor.close()); const save = node('button', 'primary', 'Enregistrer'); save.type = 'submit';
editorActions.append(duplicate, cancel, save); editorFields.append(editorActions); editorForm.append(editorFields, editorError); editor.append(editorHeader, editorForm); document.body.append(editor);
const manual = button('Créer manuellement', 'secondary', () => openSourceEditor()); manual.id = 'manual-source'; $('add-source').after(manual);
const manualCatalog = button('Créer une source manuellement', 'secondary full', () => { $('catalog-dialog').close(); openSourceEditor(); }); $('catalog-query').before(manualCatalog);

function connectorDraft() {
  const mapping = {}; for (const key of Object.keys(mappingLabels)) mapping[key] = inputs[`map-${key}`].value.trim();
  let body = {}; if(kind.value === 'json' && methodSelect.value === 'POST') body = JSON.parse(bodyInput.value || '{}');
  return {...editorBaseConfig, kind:kind.value, extractor:extractor.value.trim(), prefix:prefix.value || 'ytsearch', credential_id:credentialSelect.value, media_credential_id:mediaCredentialSelect.value,
    method:kind.value === 'json' ? methodSelect.value : 'GET', body,
    pagination:kind.value === 'json' ? {...editorBaseConfig.pagination,mode:pageSelect.value,parameter:inputs.pagination_parameter.value.trim() || 'page',has_more_path:inputs.pagination_more.value.trim()} : {mode:'prefix'},
    results_total_path:inputs.results_total_path.value.trim(), result_base_url:inputs.result_base_url.value.trim(), duration_unit:durationUnit.value || 'seconds',
    search_url:inputs.search_url.value.trim(), results_path:inputs.results_path.value.trim(), video_url:inputs.video_url.value.trim(), thumbnail_url:inputs.thumbnail_url.value.trim(), home_query:inputs.home_query.value.trim(), home_url:kind.value !== 'url' ? inputs.home_url.value.trim() : '',
    ...Object.fromEntries(['trending','views','recent'].map(key => [`home_${key}_url`, kind.value !== 'url' ? inputs[`home_${key}_url`].value.trim() : ''])), mapping};
}
function editorChanged() {
  ytFields.hidden = kind.value !== 'ytdlp'; jsonFields.hidden = kind.value !== 'json'; testRow.hidden = kind.value === 'url';
  homeFields.hidden = kind.value === 'url'; searchUrlFields.hidden = kind.value === 'url';
  try { rawConfig.textContent = JSON.stringify(connectorDraft(), null, 2); editorError.textContent = ''; }
  catch { rawConfig.textContent = 'Le corps JSON est incomplet ou invalide.'; }
  bodyInput.parentElement.hidden = methodSelect.value !== 'POST';
  testPreview.hidden = true; testStatus.textContent = '';
}
editorForm.addEventListener('input', editorChanged); editorForm.addEventListener('change', editorChanged);
editorForm.addEventListener('submit', event => { event.preventDefault(); saveDraft(false); });
editor.addEventListener('close', () => { editorVersion++; });
const loadDefault = button('Charger le modèle par défaut', 'secondary', async () => {
  try {
    const model = await api(`/api/templates/${encodeURIComponent(editedSource?.id?.startsWith('custom-') ? extractor.value.trim() : editedSource?.id || extractor.value.trim())}`);
    const changes = [];
    function compare(before, after, path = '') {
      for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
        const a = before[key], b = after[key];
        if (a && b && typeof a === 'object' && typeof b === 'object') compare(a, b, `${path}${key}.`);
        else if (a !== b) changes.push(`${path}${key}\n  Actuel : ${JSON.stringify(a ?? null)}\n  Modèle : ${JSON.stringify(b ?? null)}`);
      }
    }
    compare(connectorDraft(), model.connector);
    const preview = node('dialog', 'connector-dialog');
    const title = node('h2', '', 'Comparer au modèle livré'); title.id = 'template-comparison-title';
    preview.setAttribute('aria-labelledby', title.id);
    preview.append(title, node('p', 'hint', `yt-dlp ${model.yt_dlp} · connecteur ${model.connector_version}`),
      node('pre', 'connector-json', changes.join('\n\n') || 'Aucune différence.'));
    preview.append(button('Annuler', 'secondary', () => preview.close()),
      button('Charger ces modifications dans le formulaire', 'primary', async () => {
        preview.close(); await openSourceEditor(editedSource, model.connector);
        toast('Modèle chargé. Enregistrez pour appliquer.');
      }));
    preview.addEventListener('close', () => preview.remove()); document.body.append(preview); preview.showModal();
  } catch (e) { editorError.textContent = e.message; }
});
editorFields.prepend(loadDefault);
async function openSourceEditor(source = null, preset = null) {
  editedSource = source; const version = ++editorVersion; editorFields.disabled = true;
  editorTitle.textContent = source ? `Configurer ${source.name}` : 'Créer une source'; duplicate.hidden = !source; editorError.textContent = ''; testPreview.hidden = true; testStatus.textContent = '';
  editor.showModal();
  try {
    const [options, available, accesses] = await Promise.all([api('/api/connectors/options'), api('/api/catalog'), api('/api/credentials')]);
    if (version !== editorVersion) return;
    prefix.replaceChildren(); options.prefixes.forEach(value => option(prefix, value, value));
    extractorOptions.replaceChildren(...available.items.map(item => { const opt=node('option'); opt.value=item.id; opt.label=item.name; return opt; }));
    const config = preset || source?.connector || {kind:'json', extractor:'', prefix:'ytsearch', search_url:'', results_path:'/list', video_url:'', mapping:{}};
    editorBaseConfig = structuredClone(config);
    credentialSelect.replaceChildren(); option(credentialSelect, '', 'Aucun — accès public');
    for(const access of accesses.items) option(credentialSelect,access.id,`${access.name} · ${access.kind}`);
    if(config.credential_id && !accesses.items.some(a=>a.id===config.credential_id)) option(credentialSelect,config.credential_id,'Accès supprimé — choisissez un remplacement');
    credentialSelect.value = config.credential_id || '';
    mediaCredentialSelect.replaceChildren();option(mediaCredentialSelect,'','Cookies de la recherche si disponibles, sinon accès public');
    for(const access of accesses.items.filter(a=>a.kind==='cookies'))option(mediaCredentialSelect,access.id,access.name);
    if(config.media_credential_id && !accesses.items.some(a=>a.id===config.media_credential_id))option(mediaCredentialSelect,config.media_credential_id,'Accès supprimé — choisissez un remplacement');
    mediaCredentialSelect.value=config.media_credential_id||'';
    methodSelect.value = config.method || 'GET'; bodyInput.value = JSON.stringify(config.body || {},null,2);
    pageSelect.value = config.pagination?.mode || 'prefix'; inputs.pagination_parameter.value = config.pagination?.parameter || 'page'; inputs.pagination_more.value = config.pagination?.has_more_path || '';
    inputs.name.value = source?.name || ''; kind.value = config.kind; extractor.value = config.extractor; prefix.value = config.prefix;
    for (const key of ['search_url','results_path','results_total_path','result_base_url','video_url','thumbnail_url']) inputs[key].value = config[key] || '';
    durationUnit.value = config.duration_unit || 'seconds';
    inputs.home_query.value = config.home_query ?? 'vidéos'; inputs.home_url.value = config.home_url || '';
    for (const key of ['trending','views','recent']) inputs[`home_${key}_url`].value = config[`home_${key}_url`] || '';
    for (const key of Object.keys(mappingLabels)) inputs[`map-${key}`].value = config.mapping[key] ?? `/${key}`;
    inputs.query.value='chat'; editorChanged(); editorFields.disabled=false; inputs.name.focus();
  } catch (e) { if (version === editorVersion) editorError.textContent = e.message; }
}
async function testDraft() {
  const version = editorVersion; let config;
  try {config=connectorDraft();} catch {editorError.textContent='Corrigez le corps JSON avant de tester.';return;}
  editorFields.disabled = true; testStatus.textContent = 'Test en cours…'; editorError.textContent = ''; testPreview.hidden = true;
  try {
    const response = await api('/api/connectors/test', {method:'POST', signal:AbortSignal.timeout(70000), body:JSON.stringify({connector:config, query:inputs.query.value.trim()})});
    if (version !== editorVersion) return;
    testStatus.textContent = `${response.items.length} résultat(s). Voici les données qui seront utilisées pour les cartes. Le résultat du test est enregistré ; la configuration reste un brouillon.`;
    testPreview.textContent=JSON.stringify(response.items, null, 2); testPreview.hidden=false;
  } catch (e) { if (version === editorVersion) { testStatus.textContent='Test échoué.'; editorError.textContent=e.message; } }
  finally { if (version === editorVersion) editorFields.disabled=false; }
}
async function saveDraft(copy) {
  if (!editorForm.reportValidity()) return;
  const version = editorVersion; editorFields.disabled=true; editorError.textContent='';
  try {
    const update = editedSource && !copy;
    await api(update ? `/api/sources/${encodeURIComponent(editedSource.id)}` : '/api/sources', {method:update?'PATCH':'POST', body:JSON.stringify({name:inputs.name.value.trim() + (copy?' (copie)':''), connector:connectorDraft()})});
    await loadSources(); if (version === editorVersion) { editor.close(); toast(copy?'Copie enregistrée.':'Configuration enregistrée.'); }
  } catch (e) { if (version === editorVersion) editorError.textContent=e.message; }
  finally { if (version === editorVersion) editorFields.disabled=false; }
}

const exportReport=node('a','secondary','Exporter le rapport du catalogue');exportReport.href='/api/catalog/report';exportReport.download='anytube-catalogue.json';$('add-source').after(exportReport);
