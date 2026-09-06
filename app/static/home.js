'use strict';
const homeFeed = $('home-feed');
const resultHeading = $('results-title').parentElement;
let homeRanking = 'default';
const rankingControls = node('div', 'filters'); rankingControls.setAttribute('aria-label', 'Classement des vidéos');
homeFeed.before(rankingControls);
for (const [value, label] of Object.entries({default:'Sélection', trending:'Tendances', views:'Plus vues', recent:'Nouveautés'})) {
  const control = button(label, 'chip', () => {
    homeRanking = value;
    if(typeof persistPreferences==='function')persistPreferences();
    for (const item of rankingControls.children) item.setAttribute('aria-pressed', String(item === control));
    loadHome();
  });
  control.dataset.ranking=value;control.setAttribute('aria-pressed', String(value === homeRanking)); rankingControls.append(control);
}
const homeBack = button('← Revenir aux vidéos de mes sources', 'secondary', showHome);
homeBack.id = 'home-back'; homeBack.hidden = true; resultHeading.before(homeBack);

function showSearchResults() {
  searchControls.hidden=false;
  state.homeMode = false; state.homeVersion++;
  rankingControls.hidden = true;
  renderFilters();
  homeFeed.hidden = true; homeBack.hidden = false; resultHeading.hidden = false; $('results').hidden = false;
}
function showHome() {
  searchControls.hidden=true;searchMore.hidden=true;
  state.homeMode = true; state.searchId++; $('search-button').disabled = false;
  rankingControls.hidden = false;
  $('query').value = ''; renderFilters();
  $('search-notices').replaceChildren(); homeBack.hidden = true;
  resultHeading.hidden = true; $('results').hidden = true; $('empty').hidden = true; homeFeed.hidden = false;
  loadHome();
}
async function loadHome() {
  const version = ++state.homeVersion;
  const ranking = homeRanking;
  resultHeading.hidden = true; $('results').hidden = true; $('empty').hidden = true; homeFeed.hidden = false; homeBack.hidden = true;
  homeFeed.replaceChildren();
  const active = state.sources.filter(source => source.enabled);
  if (!active.length) { homeFeed.append(node('div', 'empty', 'Aucune source active. Ajoutez ou activez une source dans Mes sources.')); return; }
  const sections = active.map(source => {
    const section = node('section', 'home-section'); section.setAttribute('aria-label', `Vidéos de ${source.name}`);
    section.dataset.sourceId = source.id;
    section.hidden = state.selected !== null && !state.selected.includes(source.id);
    const heading = node('div', 'results-header'); heading.append(node('h2', '', source.name));
    const status = node('span', 'count', 'Chargement…'); status.setAttribute('aria-live', 'polite'); heading.append(status);
    const note = node('p', 'hint', '10 premières vidéos · cache de 5 minutes');
    const grid = node('div', 'grid'); const message = node('div');
    const entry={source,status,note,grid,message,cursor:null,seen:new Set()};
    const more=button('Charger davantage','secondary',()=>populate(entry,true));more.hidden=true;entry.more=more;
    section.append(heading, note, message, grid,more); homeFeed.append(section);
    return entry;
  });
  async function populate(entry,append=false) {
    entry.more.disabled=true;
    entry.status.textContent = 'Chargement…'; entry.message.replaceChildren();
    try {
      const response = await api(`/api/home/${encodeURIComponent(entry.source.id)}?ranking=${ranking}${append&&entry.cursor?'&cursor='+encodeURIComponent(entry.cursor):''}`, {signal:AbortSignal.timeout(125000)});
      if (version !== state.homeVersion || !state.homeMode) return;
      entry.note.textContent = response.label ? `${response.label} · 10 premières vidéos · cache de 5 minutes` : 'Aucun flux d’accueil configuré';
      if(!append){entry.grid.replaceChildren();entry.seen.clear();}
      const fresh=response.items.filter(item=>{if(entry.seen.has(item.url))return false;entry.seen.add(item.url);return true;});entry.grid.append(...fresh.map(renderCard));
      entry.status.textContent=`${entry.seen.size} vidéo(s)`;entry.cursor=response.next_cursor;entry.more.hidden=!entry.cursor;
      if (response.error) throw new Error(response.error);
      if (!response.items.length) entry.message.append(node('p', 'notice', response.message || 'Cette source ne renvoie aucune vidéo pour sa sélection d’accueil.'));
    } catch (error) {
      if (version !== state.homeVersion || !state.homeMode) return;
      entry.status.textContent = 'Indisponible'; entry.message.replaceChildren(node('p', 'notice', error.message));
      const retry = button('Réessayer', 'secondary', () => { retry.disabled = true; populate(entry,append); }); entry.message.append(retry);
    }finally{
      entry.more.disabled=false;
    }
  }
  let next = 0;
  await Promise.all(Array.from({length:Math.min(3, sections.length)}, async () => {
    while (next < sections.length && version === state.homeVersion && state.homeMode) await populate(sections[next++]);
  }));
}
resultHeading.hidden = true; $('empty').hidden = true;
