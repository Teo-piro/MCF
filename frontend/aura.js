/* ============================================================
   AURA — script condiviso
   Shell (topbar + sidebar) iniettata via JS per coerenza DRY.
   ============================================================ */

// Icone outline SVG (24px grid) — niente emoji nella UI (regola brand)
const AURA_ICONS = {
  fornitori: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="M16 5.5a3 3 0 0 1 0 5.5"/><path d="M18 14c2.2.6 3.8 2.5 3.8 4.8"/></svg>',
  attrezzatura: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8h3l1.5-2h9L18 8h3a0 0 0 0 1 0 0v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8z"/><circle cx="12" cy="13" r="3.2"/></svg>',
  prenotazioni: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/></svg>',
  progetti: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h6a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>',
  menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="9" r="3.4"/><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
};

// Voci di navigazione (label + href + chiave icona)
const AURA_NAV = [
  { key:'fornitori',    label:'Fornitori',    href:'/fornitori.html' },
  { key:'attrezzatura', label:'Attrezzatura', href:'/magazzino.html' },
  { key:'prenotazioni', label:'Prenotazione Studio', href:'/studio.html' },
];

/**
 * Chat finte realistiche per i "Recenti"
 */
const CHAT_FINTE = [
  "Prenota 2 fotocamere per il 15 luglio",
  "Quanti softbox abbiamo disponibili?",
  "Mi serve un setup completo per un podcast",
  "Cercami un fonico a Milano",
  "Quanto costa affittare lo studio domani?",
  "Prenota 1 videocamera e 3 batterie",
  "Chi può montare il video entro giovedì?",
  "Familiarizza con i nuovi tool Llama",
  "Verifica disponibilità microfoni per lunedì",
  "Setup consigliato per TikTok/Reels",
  "Fammi un'offerta per un progetto corporate",
];

/**
 * Costruisce topbar + sidebar dentro #aura-shell.
 * @param {Object} opts
 * @param {string} opts.active  chiave nav attiva (fornitori|attrezzatura|prenotazioni|progetti)
 * @param {string[]} opts.recenti  voci "Recenti" — se omesso, genera chat finte
 */
function auraShell(opts = {}){
  const active = opts.active || '';
  const recenti = opts.recenti || CHAT_FINTE.slice(0, 11).map(c => c);

  const navHtml = AURA_NAV.map(n =>
    `<a class="nav-item ${n.key===active?'active':''}" href="${n.href}">${AURA_ICONS[n.key]}<span>${n.label}</span></a>`
  ).join('');

  const recentiHtml = recenti.map(r => `<div class="recente">${r}</div>`).join('');

  const shell = document.getElementById('aura-shell');
  if(!shell) return;
  shell.innerHTML = `
    <header class="topbar">
      <button class="icon-circle menu-toggle" onclick="auraToggleSidebar()" aria-label="Menu">${AURA_ICONS.menu}</button>
      <a class="logo" href="/"><span class="star">✦</span> Aura <span class="star">✦</span></a>
      <div class="topbar-right">
        <div class="icon-circle avatar" title="Profilo">${AURA_ICONS.user}</div>
      </div>
    </header>

    <div class="layout">
      <aside class="sidebar" id="aura-sidebar">
        <nav class="glass nav-panel">${navHtml}</nav>
        <div class="glass recenti-panel">
          <div class="recenti-label">Recenti</div>
          <div class="recenti-list">${recentiHtml}</div>
        </div>
      </aside>
      <main class="main glass" id="aura-main"></main>
    </div>
    <div class="sidebar-backdrop" id="aura-backdrop" onclick="auraToggleSidebar()"></div>
  `;
}

function auraToggleSidebar(){
  document.getElementById('aura-sidebar')?.classList.toggle('open');
  document.getElementById('aura-backdrop')?.classList.toggle('show');
}

// Chiudi drawer con Esc
document.addEventListener('keydown', e => {
  if(e.key === 'Escape'){
    document.getElementById('aura-sidebar')?.classList.remove('open');
    document.getElementById('aura-backdrop')?.classList.remove('show');
  }
});
