'use strict';
const accessDialog = node('dialog', 'connector-dialog');
accessDialog.setAttribute('aria-labelledby', 'access-heading'); document.body.append(accessDialog);
const manageAccess = button('Mes accès aux plateformes', 'secondary', () => openAccess());
$('add-source').after(manageAccess);

async function openAccess(selected = null) {
  accessDialog.replaceChildren();
  const heading = node('h2', '', selected ? 'Remplacer un accès' : 'Mes accès aux plateformes'); heading.id = 'access-heading';
  const top = node('div', 'dialog-header'); top.append(heading, button('Fermer', 'secondary', () => accessDialog.close())); accessDialog.append(top);
  const status = node('p', 'hint'); status.setAttribute('aria-live', 'polite'); accessDialog.append(status);
  if (!accessDialog.open) accessDialog.showModal();
  try {
    const data = await api('/api/credentials');
    for (const item of data.items) {
      const row = node('div', 'catalog-row'); row.append(node('span', '', `${item.name} · ${item.kind}`),
        button('Remplacer', 'secondary', () => openAccess(item)),
        button('Supprimer', 'secondary', async () => {
          if (!await demanderSuppression(`Supprimer l’accès « ${item.name} » ? Les sources associées demanderont un nouvel accès.`)) return;
          try { await api(`/api/credentials/${item.id}`, {method:'DELETE'}); await openAccess(); } catch(e) { status.textContent = e.message; }
        })); accessDialog.append(row);
    }
    if (!data.ready) { status.textContent = 'Le coffre doit être initialisé sur le serveur avec sa clé de chiffrement externe. Les sources publiques restent disponibles.'; return; }
    accessDialog.append(node('p', 'hint', 'Les valeurs sont chiffrées sur le serveur et ne sont jamais réaffichées. Les jetons et clés s’utilisent avec les API JSON ; les cookies importés s’utilisent aussi avec yt-dlp.'));
    const form = node('form'), fields = node('fieldset', 'connector-fields'); form.append(fields);
    function input(label, type = 'text', value = '') {
      const holder = node('label', 'connector-field', label), control = node('input'); control.type = type; control.value = value;
      control.required = true; control.autocomplete = 'off'; holder.append(control); fields.append(holder); return control;
    }
    const name = input('Nom de cet accès', 'text', selected?.name || ''); name.maxLength = 100;
    const kindLabel = node('label', 'connector-field', 'Type d’accès'), kindControl = node('select');
    for (const [value, label] of [['api_key', 'Clé API dans un en-tête'], ['bearer', 'Jeton Bearer'], ['cookies', 'Cookies Netscape importés']]) option(kindControl, value, label);
    kindControl.value = selected?.kind || 'api_key'; kindLabel.append(kindControl); fields.append(kindLabel);
    const domains = input('Domaines exacts autorisés, séparés par des virgules'); domains.placeholder = 'api.exemple.org, www.exemple.org';
    const header = input('Nom de l’en-tête de clé API', 'text', 'X-API-Key');
    const secret = input('Nouvelle valeur', 'password'); secret.maxLength = 131072;
    const file = input('Fichier de cookies Netscape', 'file'); file.accept = '.txt';
    function change() { file.parentElement.hidden = kindControl.value !== 'cookies'; file.required = kindControl.value === 'cookies'; secret.parentElement.hidden = kindControl.value === 'cookies'; secret.required = kindControl.value !== 'cookies'; header.parentElement.hidden = kindControl.value !== 'api_key'; header.required = kindControl.value === 'api_key'; }
    kindControl.addEventListener('change', change); change();
    const submit = node('button', 'primary', selected ? 'Remplacer cet accès' : 'Enregistrer cet accès'); submit.type = 'submit'; fields.append(submit); accessDialog.append(form);
    form.addEventListener('submit', async event => {
      event.preventDefault(); fields.disabled = true; status.textContent = '';
      try {
        if (file.files[0]?.size > 131072) throw new Error('Le fichier de cookies dépasse 128 Ko.');
        const value = kindControl.value === 'cookies' ? await file.files[0].text() : secret.value;
        await api(selected ? `/api/credentials/${selected.id}` : '/api/credentials', {method: selected ? 'PUT' : 'POST',
          body: JSON.stringify({name:name.value.trim(), kind:kindControl.value, domains:domains.value.split(',').map(v=>v.trim()).filter(Boolean), header:header.value, value})});
        secret.value = ''; file.value = ''; await openAccess(); toast('Accès enregistré. Associez-le dans la configuration de la source.');
      } catch(e) { status.textContent = e.message; fields.disabled = false; }
    });
  } catch(e) { status.textContent = e.message; }
}
