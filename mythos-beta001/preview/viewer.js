/* MYTHOS — Card Viewer (Beta 0.01 prototype).
 * Standalone browse/detail/filter over the game's own embedded data
 * (window.MYTHOS_DATA from data.js). No engine, no backend, no network
 * calls except card art images. See PREP.md section 4 for the design. */
(function () {
'use strict';

var DATA = window.MYTHOS_DATA;
var CARDS = (DATA && DATA.cards) || [];
var ART_BASE = 'https://justwiggleit.github.io/sturdy-eureka/' + (DATA.imgDir || 'assets/cards') + '/';
var BACK_URL = 'https://justwiggleit.github.io/sturdy-eureka/' + (DATA.cardBack || 'assets/card-back.webp');
var TYPES = ['Character', 'Abomination', 'Ritual', 'Location', 'Action', 'Trap', 'Artifact', 'Effect'];

var activeType = 'All';
var query = '';
var currentList = CARDS.slice();
var detailIdx = -1;
var detailFlipped = false;

function el(id) { return document.getElementById(id); }
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* Same stat-line format the game's ui.js statLine() produces, minus the
 * live-instance values (personal sanity, effective stats) that only exist
 * inside a match. Null stats are skipped; Layoff Swarm's variable
 * Power/Flesh show as a dash. */
function statLine(d) {
  var parts = [];
  if (d.type === 'Character') {
    parts.push('Cost ' + d.cost, 'Ctl ' + d.control, 'San ' + d.sanity);
  } else if (d.type === 'Abomination') {
    parts.push('Cost ' + d.cost,
      'P ' + (d.power == null ? '—' : d.power),
      'F ' + (d.flesh == null ? '—' : d.flesh),
      'Upk ' + d.upkeep);
  } else if (d.cost != null) {
    parts.push('Cost ' + d.cost);
  }
  return parts.join(' · ');
}

function fullStats(d) {
  var rows = [['Cost', d.cost], ['Control', d.control], ['Sanity', d.sanity],
    ['Power', d.power], ['Flesh', d.flesh], ['Leash', d.leash], ['Upkeep', d.upkeep]];
  return rows.filter(function (r) { return r[1] != null; })
    .map(function (r) { return '<b>' + r[0] + '</b> ' + r[1]; }).join(' · ');
}

function renderFilters() {
  var counts = { All: CARDS.length };
  CARDS.forEach(function (d) { counts[d.type] = (counts[d.type] || 0) + 1; });
  var names = ['All'].concat(TYPES.filter(function (t) { return counts[t]; }));
  el('viewer-filters').innerHTML = names.map(function (t) {
    return '<button data-type="' + esc(t) + '"' +
      (t === activeType ? ' class="active"' : '') + '>' +
      esc(t) + ' (' + counts[t] + ')</button>';
  }).join('');
  el('viewer-filters').querySelectorAll('button').forEach(function (b) {
    b.onclick = function () { activeType = b.getAttribute('data-type'); render(); };
  });
}

function applyFilter() {
  currentList = CARDS.filter(function (d) {
    if (activeType !== 'All' && d.type !== activeType) return false;
    if (query && d.name.toLowerCase().indexOf(query) < 0) return false;
    return true;
  });
}

function cardTile(d) {
  var tile = document.createElement('div');
  tile.className = 'bcard';
  tile.setAttribute('data-id', d.id);
  tile.innerHTML =
    '<img src="' + ART_BASE + esc(d.img) + '" alt="' + esc(d.name) + '">' +
    '<div class="bstats">' + esc(statLine(d)) + '</div>' +
    '<div class="vname">' + esc(d.name) + '</div>';
  var img = tile.querySelector('img');
  img.onerror = function () {
    tile.classList.add('noart');
    img.remove();
    var face = document.createElement('div');
    face.className = 'vtextface';
    face.innerHTML = '<div class="vt-name">' + esc(d.name) + '</div>' +
      '<div class="vt-type">' + esc(d.type) + ' · ' + esc(statLine(d)) + '</div>' +
      '<div class="vt-rules">' + esc(d.rules || '') + '</div>';
    tile.insertBefore(face, tile.firstChild);
  };
  tile.onclick = function () { openDetail(currentList.indexOf(d)); };
  return tile;
}

function renderGrid() {
  var grid = el('viewer-grid');
  grid.innerHTML = '';
  currentList.forEach(function (d) { grid.appendChild(cardTile(d)); });
  el('viewer-count').textContent =
    'Showing ' + currentList.length + ' of ' + CARDS.length + ' cards' +
    (activeType !== 'All' ? ' · type: ' + activeType : '') +
    (query ? ' · search: "' + query + '"' : '');
}

function render() { renderFilters(); applyFilter(); renderGrid(); }

function openDetail(idx) {
  if (idx < 0 || idx >= currentList.length) return;
  detailIdx = idx;
  detailFlipped = false;
  var d = currentList[idx];
  el('vd-body').innerHTML =
    '<div id="detail-body">' +
      '<img class="vart zoomable" id="vd-img" src="' + ART_BASE + esc(d.img) + '" alt="' + esc(d.name) + '">' +
      '<div class="dinfo">' +
        '<h3>' + esc(d.name) + '</h3>' +
        (d.title ? '<div class="dtitle">' + esc(d.title) + '</div>' : '') +
        '<div class="dtype">' + esc(d.type) + ' · ' + esc(statLine(d)) + ' · #' + esc(d.num) + '</div>' +
        '<div class="vstats">' + fullStats(d) + '</div>' +
        '<p class="drules">' + esc(d.rules || '—') + '</p>' +
        (d.flavor ? '<p class="dflavor">' + esc(d.flavor) + '</p>' : '') +
        '<div class="dbtns">' +
          '<button id="vd-prev">← Prev</button>' +
          '<button id="vd-flip">Flip</button>' +
          '<button id="vd-next">Next →</button>' +
          '<button id="vd-done">Close</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  var img = el('vd-img');
  img.onerror = function () { img.style.display = 'none'; };
  img.ondblclick = function () {
    el('vz-img').setAttribute('src', detailFlipped ? BACK_URL : ART_BASE + d.img);
    el('viewer-zoom').style.display = 'flex';
  };
  el('vd-prev').onclick = function () { openDetail((detailIdx - 1 + currentList.length) % currentList.length); };
  el('vd-next').onclick = function () { openDetail((detailIdx + 1) % currentList.length); };
  el('vd-done').onclick = closeDetail;
  el('vd-flip').onclick = function () {
    detailFlipped = !detailFlipped;
    img.src = detailFlipped ? BACK_URL : ART_BASE + d.img;
    img.style.display = '';
  };
  el('viewer-detail').style.display = 'flex';
}

function closeDetail() { el('viewer-detail').style.display = 'none'; }

el('vd-close').onclick = closeDetail;
el('viewer-detail').addEventListener('click', function (e) {
  if (e.target === el('viewer-detail')) closeDetail();
});
el('viewer-zoom').onclick = function () { el('viewer-zoom').style.display = 'none'; };
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { closeDetail(); el('viewer-zoom').style.display = 'none'; }
  if (el('viewer-detail').style.display === 'flex') {
    if (e.key === 'ArrowLeft') el('vd-prev').click();
    if (e.key === 'ArrowRight') el('vd-next').click();
  }
});
el('viewer-search').addEventListener('input', function (e) {
  query = e.target.value.trim().toLowerCase();
  applyFilter(); renderGrid();
});

render();
})();
