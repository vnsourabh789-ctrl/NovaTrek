/* NovaTrek front-end — vanilla JS, no build step.
 * All dynamic text goes through text nodes (never innerHTML) so model output cannot inject markup. */
(() => {
  'use strict';

  const SVGNS = 'http://www.w3.org/2000/svg';
  const $ = (s, r = document) => r.querySelector(s);
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
    'September', 'October', 'November', 'December'];
  const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /** Tiny hyperscript helper. Prefix tag with "svg:" for SVG elements. */
  function h(tag, props, ...kids) {
    const isSvg = tag.startsWith('svg:');
    const el = isSvg ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.setAttribute('class', v);
      else if (k === 'style') Object.assign(el.style, v);
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  const state = { abort: null, activeId: null, timer: null };
  const els = {
    home: $('#home'), pipeline: $('#pipeline'), trip: $('#trip'), form: $('#planForm'),
    prompt: $('#prompt'), launch: $('#launchBtn'), error: $('#formError'), nodes: $('#nodes'),
    bar: $('#pipeBar'), timer: $('#pipeTimer'), title: $('#pipeTitle'), live: $('#pipeLive'),
    list: $('#tripList'), led: $('#engineLed'), engineText: $('#engineText'),
  };

  /* ───────────── starfield (cheap: ~140 dots, paused when hidden) ───────────── */
  function starfield() {
    const cv = $('#stars'); const ctx = cv.getContext('2d');
    let w, h2, stars = [], mx = 0, my = 0, raf = 0;
    const resize = () => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      w = cv.width = innerWidth * dpr; h2 = cv.height = innerHeight * dpr;
      stars = Array.from({ length: Math.round(Math.min(160, innerWidth / 9)) }, () => ({
        x: Math.random() * w, y: Math.random() * h2, z: Math.random() * 0.9 + 0.1,
        r: (Math.random() * 1.3 + 0.3) * dpr, p: Math.random() * 6.28,
      }));
    };
    const draw = (t) => {
      ctx.clearRect(0, 0, w, h2);
      for (const s of stars) {
        const tw = reduceMotion ? 0.8 : 0.55 + 0.45 * Math.sin(t / 900 + s.p);
        if (!reduceMotion) { s.y += s.z * 0.12; if (s.y > h2) { s.y = 0; s.x = Math.random() * w; } }
        const x = s.x + mx * s.z * 20, y = s.y + my * s.z * 20;
        ctx.globalAlpha = tw * s.z;
        ctx.fillStyle = s.z > 0.75 ? '#a5f3fc' : '#c7d2fe';
        ctx.beginPath(); ctx.arc(x, y, s.r, 0, 6.283); ctx.fill();
      }
      if (!reduceMotion) raf = requestAnimationFrame(draw);
    };
    addEventListener('resize', () => { resize(); if (reduceMotion) draw(0); });
    addEventListener('pointermove', (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });
    document.addEventListener('visibilitychange', () => {
      cancelAnimationFrame(raf);
      if (!document.hidden && !reduceMotion) raf = requestAnimationFrame(draw);
    });
    resize(); raf = requestAnimationFrame(draw);
  }

  /* ───────────── helpers ───────────── */
  const sourceLabel = { ai: 'AI', live: 'Live data', model: 'Route model', offline: 'Offline sim', calc: 'Calc', skipped: 'Skipped', error: 'Degraded' };
  const warnSources = new Set(['offline', 'skipped', 'error']);
  const wxIcon = (c) => {
    c = (c || '').toLowerCase();
    if (/thunder/.test(c)) return '⛈️'; if (/snow/.test(c)) return '❄️';
    if (/rain|shower|drizzle/.test(c)) return '🌧️'; if (/fog/.test(c)) return '🌫️';
    if (/overcast/.test(c)) return '☁️'; if (/partly/.test(c)) return '⛅';
    if (/clear|mostly|dry/.test(c)) return '☀️'; return '🌡️';
  };
  const fmtDate = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const dayName = (iso) => { const d = new Date(iso + 'T12:00:00'); return isNaN(d) ? '—' : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' }); };

  function countUp(el, to, format) {
    if (reduceMotion) { el.textContent = format(to); return; }
    const t0 = performance.now(), dur = 900;
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = format(to * e);
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function show(view) {
    els.home.hidden = view !== 'home';
    els.pipeline.hidden = view !== 'pipeline';
    els.trip.hidden = view !== 'trip';
    scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
  }

  function setError(msg) { els.error.hidden = !msg; els.error.textContent = msg || ''; }

  /* ───────────── health + mission log ───────────── */
  async function loadHealth() {
    try {
      const j = await (await fetch('/api/health')).json();
      els.led.className = 'led ' + j.engine;
      els.engineText.textContent = j.engine === 'ai' ? `AI online · ${j.model}` : 'Offline sim · set LLM_API_KEY';
    } catch {
      els.led.className = 'led down'; els.engineText.textContent = 'API unreachable';
    }
  }

  async function loadTrips() {
    let trips = [];
    try { trips = await (await fetch('/api/trips')).json(); } catch { /* keep empty */ }
    els.list.replaceChildren(...(trips.length ? trips.map(tripItem) : [h('li', { class: 'empty' }, 'No missions yet — launch your first.')]));
  }

  function tripItem(t) {
    return h('li', { class: 'trip-item' + (t.id === state.activeId ? ' active' : '') },
      h('button', { class: 'trip-open', type: 'button', onclick: () => openTrip(t.id) },
        h('strong', null, t.title), h('small', null, `${fmtDate(t.created_at)} · ${money.format(t.total_cost)}`)),
      h('button', {
        class: 'trip-del', type: 'button', 'aria-label': `Delete ${t.title}`,
        onclick: async () => {
          if (!confirm(`Delete mission "${t.title}"?`)) return;
          await fetch(`/api/trips/${t.id}`, { method: 'DELETE' });
          if (state.activeId === t.id) newMission();
          loadTrips();
        },
      }, '✕'));
  }

  async function openTrip(id) {
    document.body.classList.remove('rail-open');
    try {
      const res = await fetch(`/api/trips/${id}`);
      if (!res.ok) throw new Error('not found');
      renderTrip(await res.json());
    } catch { setError('Could not load that mission.'); newMission(); }
  }

  /* ───────────── planning (SSE over fetch) ───────────── */
  async function streamPlan(message, onEvent, signal) {
    const res = await fetch('/api/plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }), signal,
    });
    if (!res.ok) {
      let msg = `Request failed (${res.status})`;
      try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : (j.detail?.[0]?.msg || msg); } catch { /* ignore */ }
      throw new Error(msg);
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const line = buf.slice(0, i).split('\n').find((l) => l.startsWith('data: '));
        buf = buf.slice(i + 2);
        if (line) onEvent(JSON.parse(line.slice(6)));
      }
    }
  }

  const NODE_LAYOUT = { intent: ['1', '🧭'], flights: ['2', '✈️'], weather: ['2', '🌦️'], hotels: ['2', '🏨'], itinerary: ['3', '🗺️'], budget: ['4', '💠'] };

  function buildNodes(stages) {
    els.nodes.replaceChildren(...stages.map((s) => h('div', { class: 'node', 'data-id': s.id, 'data-col': NODE_LAYOUT[s.id]?.[0] || '2', 'data-state': 'idle' },
      h('div', { class: 'node-ico', 'aria-hidden': 'true' }, NODE_LAYOUT[s.id]?.[1] || '◈'),
      h('div', { class: 'node-label' }, s.label),
      h('div', { class: 'node-desc' }, s.desc),
      h('div', { class: 'node-stat' }, 'Queued'))));
  }

  function updateNode(ev, doneCount, total) {
    const node = els.nodes.querySelector(`[data-id="${ev.id}"]`);
    if (!node) return;
    node.dataset.state = ev.status;
    const stat = node.querySelector('.node-stat');
    stat.replaceChildren();
    if (ev.status === 'running') stat.append('Running…');
    else {
      stat.append(`${ev.ms} ms`);
      if (ev.source) stat.append(h('span', { class: 'badge' + (warnSources.has(ev.source) ? ' warn' : '') }, sourceLabel[ev.source] || ev.source));
      if (ev.summary) stat.append(h('span', null, ev.summary));
    }
    els.bar.style.width = `${Math.round((doneCount / total) * 100)}%`;
    els.live.textContent = `${node.querySelector('.node-label').textContent}: ${ev.status}`;
  }

  async function launch(message) {
    message = message.trim();
    if (message.length < 3) { setError('Tell me a little more about the trip you want.'); return; }
    setError('');
    state.abort?.abort();
    const ctrl = state.abort = new AbortController();
    els.launch.disabled = true;
    els.title.textContent = 'Agents deploying…';
    els.bar.style.width = '0%';
    els.nodes.replaceChildren();
    show('pipeline');

    const t0 = performance.now();
    clearInterval(state.timer);
    state.timer = setInterval(() => { els.timer.textContent = ((performance.now() - t0) / 1000).toFixed(1) + 's'; }, 100);

    let stages = [], done = 0, result = null, failure = null;
    try {
      await streamPlan(message, (ev) => {
        if (ev.type === 'start') { stages = ev.stages; buildNodes(stages); }
        else if (ev.type === 'stage') {
          if (ev.status === 'done') done++;
          if (ev.id === 'itinerary' && ev.status === 'running') els.title.textContent = 'Composing your itinerary…';
          updateNode(ev, done, stages.length || 6);
        } else if (ev.type === 'result') result = ev.trip;
        else if (ev.type === 'error') failure = ev.message;
      }, ctrl.signal);
      if (!result && !failure) failure = 'The mission ended unexpectedly. Please try again.';
    } catch (e) {
      if (e.name === 'AbortError') failure = 'Mission aborted.';
      else if (e instanceof TypeError) failure = 'Cannot reach the NovaTrek server. Make sure it is running (start.bat / python -m novatrek), then reload this page. This is not an API-key problem.';
      else failure = e.message || 'Something went wrong. Please try again.';
    } finally {
      clearInterval(state.timer);
      els.launch.disabled = false;
      if (state.abort === ctrl) state.abort = null;
    }

    if (result) { els.bar.style.width = '100%'; renderTrip(result); loadTrips(); }
    else { show('home'); setError(failure); }
  }

  /* ───────────── dashboard rendering ───────────── */
  function panel(cls, id, title, ...body) {
    return h('section', { class: `panel ${cls}`, id }, h('h3', null, title), ...body);
  }

  function renderTrip(t) {
    state.activeId = t.id;
    location.hash = `trip=${t.id}`;
    const root = els.trip;
    const i = t.intent, it = t.itinerary, f = t.flights, w = t.weather, b = t.budget;
    const sections = [['sec-route', 'Route'], ['sec-budget', 'Budget'], ['sec-weather', 'Weather'], ['sec-stays', 'Stays'], ['sec-plan', 'Itinerary'], ['sec-copilot', 'Copilot']];

    const totalEl = h('strong', null, '$0');
    const nodes = [
      h('div', { class: 'trip-head' },
        h('div', null,
          h('p', { class: 'eyebrow' }, `Mission report · ${fmtDate(t.created_at)}`),
          h('h2', null, t.title),
          h('p', { class: 'trip-sum' }, it.summary || `A ${i.days}-day ${i.budget} trip to ${t.title.split(' · ')[0]}.`)),
        h('div', { class: 'actions' },
          h('a', { class: 'btn', href: `/api/trips/${t.id}/export.md`, download: `novatrek-${t.id}.md` }, '⬇ Markdown'),
          h('button', { class: 'btn', type: 'button', onclick: () => print() }, '🖨 Print'),
          h('button', { class: 'btn btn-primary', type: 'button', onclick: newMission }, '＋ New mission'))),
      t.engine !== 'ai' && h('p', { class: 'notice' }, t.engine === 'offline'
        ? '⚠ Offline simulation: itinerary and hotels are generic templates. Set LLM_API_KEY in .env for destination-specific plans.'
        : '⚠ Some agents ran in offline mode — results are partly generic.'),
      h('nav', { class: 'subnav', 'aria-label': 'Sections' }, sections.map(([id, label]) =>
        h('button', { type: 'button', onclick: () => document.getElementById(id)?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' }) }, label))),

      h('div', { class: 'stats' },
        stat('Duration', h('strong', null, String(i.days), h('i', null, i.days === 1 ? 'day' : 'days'))),
        stat('Travellers', h('strong', null, String(i.travelers), h('i', null, i.budget))),
        stat('Estimated total', totalEl),
        stat(f.available ? 'Flight time' : 'Month', f.available
          ? h('strong', null, `${f.duration_h}`, h('i', null, `h · ${f.stops ? f.stops + ' stop' + (f.stops > 1 ? 's' : '') : 'non-stop'}`))
          : h('strong', null, i.month || 'Flexible'))),

      h('div', { class: 'grid' },
        panel('span-8', 'sec-route', '◈ Flight vector', routeSvg(t), routeMeta(f, i)),
        panel('span-4', 'sec-budget', '◈ Budget engine', donut(b)),
        panel('span-12', 'sec-weather', `◈ Atmos scan${w.available ? ' · ' + w.label : ''}`, weatherBody(w)),
        panel('span-12', 'sec-stays', '◈ Stay finder', hotelsBody(t.hotels)),
        panel('span-8', 'sec-plan', '◈ Itinerary composer', timeline(it)),
        h('div', { class: 'span-4', style: { display: 'flex', flexDirection: 'column', gap: '16px' } },
          panel('', 'sec-pack', '◈ Pack list', bullets(it.packing)),
          panel('', 'sec-tips', '◈ Field notes', bullets(it.tips), (it.highlights?.length ? [h('h3', { style: { marginTop: '18px' } }, '◈ Highlights'), bullets(it.highlights)] : null)),
        ),
        panel('span-12', 'sec-copilot', '◈ Mission copilot', copilot(t))),

      h('p', { class: 'perf' }, h('span', null, 'Completed in ', h('b', null, `${(t.total_ms / 1000).toFixed(1)}s`)),
        Object.entries(t.timings).map(([k, v]) => h('span', null, `${k} ${v}ms`))),
    ];
    root.replaceChildren(...nodes.filter(Boolean));
    show('trip');
    countUp(totalEl, b.total, (v) => money.format(v));
    // the sidebar list may already contain this trip; refresh highlight
    els.list.querySelectorAll('.trip-item').forEach((li) => li.classList.remove('active'));
    loadTrips();
  }

  function stat(label, value) { return h('div', { class: 'panel stat' }, h('small', null, label), value); }
  function bullets(items) { return h('ul', { class: 'bul' }, (items || []).map((x) => h('li', null, x))); }

  /* route visual: auto-zoomed graticule + animated great-circle-style arc */
  function routeSvg(t) {
    const W = 800, H = 400, o = t.origin, d = t.destination;
    const svg = h('svg:svg', { viewBox: `0 0 ${W} ${H}`, class: 'route-svg', role: 'img', 'aria-label': o ? `Route from ${o.name} to ${d?.name}` : `Destination ${d?.name || ''}` });
    svg.append(h('svg:defs', null, h('svg:linearGradient', { id: 'arcg', x1: '0', x2: '1' },
      h('svg:stop', { offset: '0', 'stop-color': '#22d3ee' }), h('svg:stop', { offset: '1', 'stop-color': '#f472b6' }))));
    if (!d) { svg.append(h('svg:text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', class: 'grat-t' }, 'Location unavailable')); return svg; }

    const cLat = o ? (o.lat + d.lat) / 2 : d.lat, cLon = o ? (o.lon + d.lon) / 2 : d.lon;
    const dLat = o ? Math.abs(o.lat - d.lat) : 0, dLon = o ? Math.abs(o.lon - d.lon) : 0;
    const span = Math.min(180, Math.max(dLat * 1.8, (dLon * 1.8) / 2, 14));
    const lonSpan = span * 2;
    const X = (lon) => ((lon - (cLon - lonSpan / 2)) / lonSpan) * W;
    const Y = (lat) => (((cLat + span / 2) - lat) / span) * H;
    const step = [1, 2, 5, 10, 15, 30, 45].find((s) => lonSpan / s <= 10) || 45;

    for (let lon = Math.ceil((cLon - lonSpan / 2) / step) * step; lon <= cLon + lonSpan / 2; lon += step) {
      svg.append(h('svg:line', { class: 'grat', x1: X(lon), y1: 0, x2: X(lon), y2: H }), h('svg:text', { class: 'grat-t', x: X(lon) + 4, y: H - 6 }, `${lon}°`));
    }
    for (let lat = Math.ceil((cLat - span / 2) / step) * step; lat <= cLat + span / 2; lat += step) {
      svg.append(h('svg:line', { class: 'grat', x1: 0, y1: Y(lat), x2: W, y2: Y(lat) }), h('svg:text', { class: 'grat-t', x: 6, y: Y(lat) - 4 }, `${lat}°`));
    }

    const pin = (p, cls, code) => {
      const x = X(p.lon), y = Y(p.lat), anchor = x > W * 0.68 ? 'end' : 'start', dx = anchor === 'end' ? -14 : 14;
      svg.append(h('svg:circle', { class: `pin-halo ${cls}`, cx: x, cy: y, r: 7 }), h('svg:circle', { class: `pin ${cls}`, cx: x, cy: y, r: 6 }),
        h('svg:text', { class: 'pin-t', x: x + dx, y: y - 4, 'text-anchor': anchor }, p.name),
        code && h('svg:text', { class: 'pin-s', x: x + dx, y: y + 13, 'text-anchor': anchor }, code));
    };

    if (o) {
      const x1 = X(o.lon), y1 = Y(o.lat), x2 = X(d.lon), y2 = Y(d.lat);
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, len = Math.hypot(x2 - x1, y2 - y1) || 1;
      let nx = -(y2 - y1) / len, ny = (x2 - x1) / len;
      if (ny > 0) { nx = -nx; ny = -ny; }   // bow upward
      const path = `M${x1} ${y1} Q${mx + nx * len * 0.28} ${my + ny * len * 0.28} ${x2} ${y2}`;
      svg.append(h('svg:path', { class: 'arc', d: path }));
      const ship = h('svg:circle', { class: 'ship', r: 4 });
      ship.append(h('svg:animateMotion', { dur: '4s', repeatCount: 'indefinite', path }));
      if (!reduceMotion) svg.append(ship);
      pin(o, '', t.flights?.origin_airport?.iata);
    }
    pin(d, 'dest', t.flights?.dest_airport?.iata);
    return svg;
  }

  function routeMeta(f, i) {
    if (!f.available) return h('p', { class: 'note' }, f.note || 'Flight data unavailable.');
    const lo = f.fare_low, hi = f.fare_high, pct = Math.round(((f.fare_mid - lo) / Math.max(1, hi - lo)) * 100);
    return h('div', null,
      h('div', { class: 'route-meta' },
        kv('Distance', `${f.distance_km.toLocaleString()} km`), kv('Duration', `~${f.duration_h} h`),
        kv('Cabin', f.cabin), kv('Round trip', `${money.format(f.round_trip_pp)} pp`)),
      h('div', { class: 'fare', role: 'img', 'aria-label': `One-way fare ${lo} to ${hi} dollars` }, h('i', { style: { left: `${pct}%` } })),
      h('div', { class: 'fare-labels' }, h('span', null, money.format(lo)), h('span', null, 'one-way / person'), h('span', null, money.format(hi))),
      bullets(f.advice), h('p', { class: 'note' }, f.basis));
  }
  const kv = (k, v) => h('div', { class: 'kv' }, h('small', null, k), h('strong', null, v));

  function weatherBody(w) {
    if (!w.available) return h('p', { class: 'muted' }, w.note || 'Weather unavailable.');
    return h('div', null,
      h('div', { class: 'now' },
        w.current && h('div', { class: 'big' }, `${Math.round(w.current.temp)}°`),
        w.current && h('div', null, h('div', null, `${wxIcon(w.current.cond)} ${w.current.cond} now`), h('small', { class: 'muted' }, `Humidity ${w.current.humidity}% · wind ${w.current.wind} km/h`)),
        h('div', null, kv('Typical range', `${w.avg_lo}° – ${w.avg_hi}°C`)), h('div', null, kv('Wet days', `${w.rain_days} / ${w.sample_days}`))),
      h('div', { class: 'wx' }, w.daily.map((d) => h('div', { class: 'wx-day' }, h('b', null, dayName(d.date)), h('span', { class: 'ico', title: d.cond }, wxIcon(d.cond)),
        h('span', { class: 'hi' }, `${Math.round(d.hi)}°`), h('span', { class: 'lo' }, `${Math.round(d.lo)}°`), (d.rain >= 1) && h('span', { class: 'rain' }, `${d.rain}mm`)))),
      bullets(w.advice), h('p', { class: 'note' }, `Source: ${w.provider}`));
  }

  function hotelsBody(hs) {
    if (!hs.available || !hs.hotels.length) return h('p', { class: 'muted' }, 'No stay suggestions available.');
    return h('div', null, h('div', { class: 'hotels' }, hs.hotels.map((x) => h('article', { class: 'hotel' },
      h('span', { class: `tier ${x.tier}` }, x.tier), h('h4', null, x.name), h('small', { class: 'muted' }, `📍 ${x.area}`),
      h('p', { class: 'muted' }, x.why), h('div', { class: 'price' }, money.format(x.price_per_night), h('small', null, ' / night'))))),
      h('p', { class: 'note' }, hs.disclaimer));
  }

  function timeline(it) {
    return h('div', { class: 'timeline' }, it.days.map((d, idx) => h('details', { class: 'day', open: idx < 2 },
      h('summary', null, h('span', { class: 'day-n' }, `DAY ${String(d.day).padStart(2, '0')}`), h('span', { class: 'day-t' }, d.title), h('span', { class: 'day-th' }, d.theme)),
      h('div', { class: 'day-body' },
        slot('Morning', d.morning), slot('Afternoon', d.afternoon), slot('Evening', d.evening),
        d.tip && h('p', { class: 'day-tip' }, `💡 ${d.tip}`),
        d.est_cost > 0 && h('p', { class: 'day-cost' }, `≈ ${money.format(d.est_cost)} per person (excl. hotel & flights)`)))));
  }
  const slot = (k, v) => v && h('div', { class: 'slot' }, h('b', null, k), h('span', null, v));

  function donut(b) {
    const R = 78, C = 2 * Math.PI * R, total = b.items.reduce((s, x) => s + x.amount, 0) || 1;
    let off = 0;
    const svg = h('svg:svg', { viewBox: '0 0 200 200', class: 'donut', role: 'img', 'aria-label': `Budget total ${b.total} dollars` },
      h('svg:circle', { cx: 100, cy: 100, r: R, fill: 'none', stroke: 'rgba(255,255,255,.06)', 'stroke-width': 22 }),
      b.items.map((x) => {
        const len = (x.amount / total) * C, seg = h('svg:circle', { class: 'seg', cx: 100, cy: 100, r: R, stroke: x.color, 'stroke-dasharray': `${Math.max(0, len - 2)} ${C}`, 'stroke-dashoffset': -off });
        off += len; return seg;
      }),
      h('svg:text', { x: 100, y: 96, style: { font: '700 24px var(--mono)' } }, money.format(b.total)),
      h('svg:text', { x: 100, y: 118, style: { font: '11px var(--mono)', fill: 'var(--muted)' } }, `${money.format(b.per_person)} / person`));
    return h('div', null,
      h('div', { class: 'donut-wrap' }, svg,
        h('ul', { class: 'legend' }, b.items.map((x) => h('li', null, h('i', { style: { background: x.color } }), h('span', null, x.label), h('b', null, money.format(x.amount)))))),
      h('p', { class: 'note' }, b.assumptions), !b.flights_included && h('p', { class: 'note' }, 'Flights are excluded — add a departure city to include them.'));
  }

  /* ───────────── copilot chat ───────────── */
  function copilot(t) {
    const log = h('div', { class: 'chat', role: 'log', 'aria-live': 'polite' });
    const add = (role, text) => { const m = h('div', { class: `msg ${role}` }, text); log.append(m); log.scrollTop = log.scrollHeight; return m; };
    (t.chat || []).forEach((m) => add(m.role === 'user' ? 'user' : 'bot', m.text));
    if (!log.children.length) add('bot', `Ask me anything about this trip — budget tweaks, what to pack, whether ${i18n(t)} is doable in the time.`);
    const input = h('input', { type: 'text', maxlength: '600', placeholder: 'Ask a follow-up… e.g. "How can I cut the cost?"', 'aria-label': 'Ask the copilot' });
    const btn = h('button', { class: 'btn btn-primary', type: 'submit' }, 'Send');
    const form = h('form', {
      class: 'chat-form', onsubmit: async (e) => {
        e.preventDefault();
        const q = input.value.trim(); if (!q) return;
        input.value = ''; btn.disabled = true; add('user', q);
        const typing = add('bot typing', 'Copilot is thinking…');
        try {
          const res = await fetch(`/api/trips/${t.id}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: q }) });
          const j = await res.json();
          typing.remove(); add('bot', res.ok ? j.reply : (typeof j.detail === 'string' ? j.detail : 'Copilot hit turbulence — try again.'));
        } catch { typing.remove(); add('bot', 'Network error — please retry.'); }
        btn.disabled = false; input.focus();
      },
    }, input, btn);
    return h('div', null, log, form);
  }
  const i18n = (t) => t.title.split(' · ')[0];

  /* ───────────── wiring ───────────── */
  function newMission() {
    state.abort?.abort(); state.activeId = null; history.replaceState(null, '', location.pathname);
    document.body.classList.remove('rail-open');
    setError(''); show('home'); els.prompt.focus(); loadTrips();
  }

  function buildPrompt() {
    const v = (id) => $(id).value.trim();
    const parts = [`${v('#bDays') || 5} days`, `in ${v('#bTo') || 'a destination you recommend'}`];
    if (v('#bFrom')) parts.push(`from ${v('#bFrom')}`);
    if (v('#bMonth')) parts.push(`in ${v('#bMonth')}`);
    parts.push(`for ${v('#bPax') || 1} ${+v('#bPax') === 1 ? 'person' : 'people'}`, `${$('#bTier').value} budget`);
    if (v('#bInterests')) parts.push(`interests: ${v('#bInterests')}`);
    return parts.join(', ');
  }

  function init() {
    starfield();
    $('#bMonth').append(...MONTHS.map((m) => h('option', { value: m }, m)));
    els.form.addEventListener('submit', (e) => { e.preventDefault(); launch(els.prompt.value); });
    els.prompt.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); els.form.requestSubmit(); } });
    $('#chips').addEventListener('click', (e) => { const c = e.target.closest('.chip'); if (c) { els.prompt.value = c.dataset.p; els.prompt.focus(); } });
    $('#builderBtn').addEventListener('click', (e) => { const b = $('#builder'); b.hidden = !b.hidden; e.currentTarget.setAttribute('aria-expanded', String(!b.hidden)); });
    $('#composeBtn').addEventListener('click', () => { els.prompt.value = buildPrompt(); els.prompt.focus(); });
    $('#cancelBtn').addEventListener('click', () => state.abort?.abort());
    $('#newBtn').addEventListener('click', newMission);
    $('#burger').addEventListener('click', () => document.body.classList.add('rail-open'));
    $('#scrim').addEventListener('click', () => document.body.classList.remove('rail-open'));
    addEventListener('keydown', (e) => { if (e.key === 'Escape') document.body.classList.remove('rail-open'); });

    loadHealth(); loadTrips();
    const m = location.hash.match(/^#trip=([a-f0-9]{12})$/);
    if (m) openTrip(m[1]);
  }

  init();
})();
