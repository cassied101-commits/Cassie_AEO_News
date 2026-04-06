/* ============================================================
   Cassie AEO News — frontend JS
   ============================================================ */

const REFRESH_INTERVAL_MS = 60 * 60 * 1000; // auto-reload summaries every hour

// ── Toast ──────────────────────────────────────────────────────────────────

function showToast(msg, duration = 3500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add('hidden'), duration);
}

// ── Status check ───────────────────────────────────────────────────────────

async function checkStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    const badge = document.getElementById('api-key-badge');
    if (!data.api_key_set) {
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
    if (data.latest_date) {
      document.getElementById('last-updated').textContent =
        'Last brief: ' + formatDate(data.latest_date);
    }
  } catch (_) { /* ignore */ }
}

// ── Fetch & render summaries ───────────────────────────────────────────────

async function loadSummaries() {
  try {
    const res = await fetch('/api/summaries');
    if (!res.ok) throw new Error('Failed to load');
    const summaries = await res.json();
    renderFeed(summaries);
  } catch (err) {
    showToast('Could not load summaries: ' + err.message);
  }
}

// ── Trigger refresh (generate new brief) ──────────────────────────────────

async function triggerRefresh() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true;
  document.getElementById('loading-overlay').classList.remove('hidden');
  try {
    const res = await fetch('/api/refresh', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Unknown error');
    showToast('Brief generated for ' + data.date);
    await loadSummaries();
    await checkStatus();
  } catch (err) {
    showToast('Error: ' + err.message, 6000);
  } finally {
    btn.disabled = false;
    document.getElementById('loading-overlay').classList.add('hidden');
  }
}

// ── Rendering ─────────────────────────────────────────────────────────────

function renderFeed(summaries) {
  const feed   = document.getElementById('feed');
  const empty  = document.getElementById('empty-state');
  feed.innerHTML = '';

  if (!summaries || summaries.length === 0) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  summaries.forEach((s, idx) => {
    const card = buildCard(s, idx === 0);
    feed.appendChild(card);
  });
}

function buildCard(s, isLatest) {
  const tpl  = document.getElementById('brief-card-tpl');
  const card = tpl.content.cloneNode(true).querySelector('.brief-card');

  // Date / time
  card.querySelector('.card-date').textContent = formatDateFull(s.date);
  card.querySelector('.card-time').textContent =
    'Generated ' + formatTimestamp(s.timestamp) + ' UTC';

  // Sentiment
  if (s.sentiment) {
    card.querySelector('.card-sentiment').textContent = s.sentiment;
  }

  // TL;DR
  card.querySelector('.tldr-text').textContent = s.tldr || 'No summary available.';

  // Highlights
  const hlContainer = card.querySelector('.card-highlights');
  if (s.highlights && s.highlights.length > 0) {
    s.highlights.forEach(h => {
      const row = document.createElement('div');
      row.className = 'highlight-row';
      const cat = (h.category || 'news').toLowerCase();
      const badgeClass = cat === 'trends' ? 'badge-trend'
                       : cat === 'social' ? 'badge-social'
                       : 'badge-news';
      row.innerHTML = `<span class="badge ${badgeClass}">${escHtml(h.category || 'News')}</span>
                       <span>${escHtml(h.point)}</span>`;
      hlContainer.appendChild(row);
    });
  } else {
    hlContainer.remove();
  }

  // Watch list
  const watchTags = card.querySelector('.watch-tags');
  if (s.watch_list && s.watch_list.length > 0) {
    s.watch_list.forEach(kw => {
      const tag = document.createElement('span');
      tag.className = 'watch-tag';
      tag.textContent = kw;
      watchTags.appendChild(tag);
    });
  } else {
    card.querySelector('.card-watch').remove();
  }

  // Source counts
  const ac = s.article_count    ?? (s.articles?.length ?? 0);
  const tc = s.trend_count      ?? (s.trends?.length ?? 0);
  const sc = s.social_count     ?? (s.linkedin_posts?.length ?? 0);
  const ic = s.influencer_count ?? (s.influencer_posts?.length ?? 0);
  const pc = s.platform_count   ?? (s.platform_posts?.length ?? 0);
  card.querySelector('.card-counts').textContent =
    `${ac} news · ${pc} platform · ${ic} influencer · ${tc} trends · ${sc} social`;

  // Sources — populated lazily when user expands
  card.dataset.date = s.date;

  // Tab switching inside this card
  card.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn));
  });

  // If this is the latest, pre-fetch full data so sources are ready
  if (isLatest) loadFullBrief(card, s.date);

  return card;
}

async function loadFullBrief(card, date) {
  try {
    const res = await fetch('/api/summaries/' + date);
    if (!res.ok) return;
    const full = await res.json();
    populateSources(card, full);
  } catch (_) { /* ignore */ }
}

function populateSources(card, full) {
  // News
  const newsList = card.querySelector('.news-list');
  (full.articles || []).forEach(a => newsList.appendChild(buildNewsItem(a)));

  // Platforms
  const platformsList = card.querySelector('.platforms-list');
  (full.platform_posts || []).forEach(p => platformsList.appendChild(buildNewsItem(p)));
  if (!full.platform_posts?.length) {
    platformsList.innerHTML = '<li class="source-meta" style="padding:8px 0">No platform announcements in this period.</li>';
  }

  // Influencers
  const influencersList = card.querySelector('.influencers-list');
  (full.influencer_posts || []).forEach(p => influencersList.appendChild(buildNewsItem(p)));
  if (!full.influencer_posts?.length) {
    influencersList.innerHTML = '<li class="source-meta" style="padding:8px 0">No influencer content indexed in this period.</li>';
  }

  // Trends
  const trendsList = card.querySelector('.trends-list');
  (full.trends || []).forEach(t => trendsList.appendChild(buildTrendItem(t)));

  // Social / LinkedIn
  const socialList = card.querySelector('.social-list');
  (full.linkedin_posts || []).forEach(p => socialList.appendChild(buildNewsItem(p)));

  card.dataset.sourcesLoaded = 'true';
}

function buildNewsItem(item) {
  const li = document.createElement('li');
  li.className = 'source-item';
  const excerpt = item.excerpt ? `<p class="source-excerpt">${escHtml(item.excerpt.slice(0, 200))}</p>` : '';
  li.innerHTML = `
    <a href="${escAttr(item.url)}" target="_blank" rel="noopener noreferrer">${escHtml(item.title)}</a>
    <span class="source-meta">${escHtml(item.source)} · ${escHtml(item.published || '')}</span>
    ${excerpt}
  `;
  return li;
}

function buildTrendItem(t) {
  const li = document.createElement('li');
  li.className = 'trend-item';
  const arrowClass = t.trend === 'rising' ? 'up' : t.trend === 'falling' ? 'down' : 'flat';
  const arrowChar  = t.trend === 'rising' ? '↑' : t.trend === 'falling' ? '↓' : '→';
  const barWidth   = Math.max(4, (t.interest || 0)) + 'px';
  li.innerHTML = `
    <span class="trend-arrow ${arrowClass}">${arrowChar}</span>
    <span style="flex:1">${escHtml(t.keyword)}</span>
    <span class="trend-bar" style="width:${barWidth}"></span>
    <span class="source-meta" style="min-width:36px;text-align:right">${t.interest}/100</span>
  `;
  return li;
}

// ── Source drawer toggle ───────────────────────────────────────────────────

async function toggleSources(btn) {
  const card    = btn.closest('.brief-card');
  const drawer  = card.querySelector('.card-sources');
  const isOpen  = !drawer.classList.contains('hidden');

  if (isOpen) {
    drawer.classList.add('hidden');
    btn.classList.remove('open');
    btn.querySelector('span') && (btn.querySelector('span').textContent = 'Show sources');
    btn.childNodes.forEach(n => { if (n.nodeType === 3) n.textContent = ' Show sources'; });
    btn.lastChild.textContent = ' Show sources';
    return;
  }

  // Load sources if not yet done
  if (!card.dataset.sourcesLoaded) {
    await loadFullBrief(card, card.dataset.date);
  }

  drawer.classList.remove('hidden');
  btn.classList.add('open');
  btn.lastChild.textContent = ' Hide sources';
}

function switchTab(activeBtn) {
  const card = activeBtn.closest('.brief-card');
  const tab  = activeBtn.dataset.tab;
  card.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === activeBtn));
  card.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.panel === tab));
}

// ── Date helpers ──────────────────────────────────────────────────────────

function formatDate(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatDateFull(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'short', month: 'long', day: 'numeric', year: 'numeric' });
}

function formatTimestamp(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' });
  } catch (_) { return iso; }
}

// ── Security helpers ───────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(str) {
  // Only allow http/https URLs
  const s = String(str).trim();
  if (!/^https?:\/\//i.test(s)) return '#';
  return escHtml(s);
}

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  await checkStatus();
  await loadSummaries();
  // Periodically reload
  setInterval(loadSummaries, REFRESH_INTERVAL_MS);
}

document.addEventListener('DOMContentLoaded', init);
