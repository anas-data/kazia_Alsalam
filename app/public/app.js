/* =======================================================================
   ممر MAMAR — واجهة النموذج التشغيلي
   ======================================================================= */
(function () {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const S = {
    state: null,
    tab: 'pitch',
    auto: true,
    ticket: null,
    sim: null,
    formReady: false,
  };

  const STATE_LABEL = {
    booked: 'محجوز', called: 'مستدعى', fueling: 'قيد التعبئة',
    done: 'مكتمل', cancelled: 'ملغي', expired: 'منتهي الصلاحية'
  };
  const LANE_LABEL = { idle: 'شاغر', reserved: 'محجوز للاستدعاء', busy: 'تعبئة جارية' };
  const SUPPLY_LABEL = ['قيد الاعتماد', 'معتمد', 'محمّل', 'في الطريق', 'واصل'];

  /* ----------------------------- أدوات ----------------------------- */
  const nf = new Intl.NumberFormat('en-US');
  const fmt = n => nf.format(Math.round(Number(n) || 0));
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const hhmm = isoStr => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    } catch (e) { return '--:--'; }
  };
  const agoMin = isoStr => {
    try { return Math.max(0, Math.round((Date.now() - new Date(isoStr).getTime()) / 60000)); }
    catch (e) { return 0; }
  };
  const hoursLeft = isoStr => {
    try { return Math.max(0, Math.round((new Date(isoStr).getTime() - Date.now()) / 3600000)); }
    catch (e) { return 0; }
  };
  const pct = (a, b) => Math.max(0, Math.min(100, Math.round(100 * (a / (b || 1)))));

  let toastTimer;
  function toast(msg, err) {
    const el = $('#toast');
    el.textContent = msg;
    el.className = 'toast show' + (err ? ' err' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.className = 'toast', 3200);
  }

  async function api(path, body) {
    const opt = body === undefined
      ? { method: 'GET' }
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    const r = await fetch(path, opt);
    return r.json();
  }

  function applyResult(res, okMsg) {
    if (res && res.state) S.state = res.state;
    if (res && res.ok === false) { toast(res.error || 'تعذّر تنفيذ العملية', true); return false; }
    if (okMsg) toast(okMsg);
    render();
    return true;
  }

  function makeQR(text) {
    try {
      const qr = qrcode(0, 'M');
      qr.addData(text);
      qr.make();
      return qr.createSvgTag(4, 2);
    } catch (e) { return '<div style="color:#111;font-size:12px">QR</div>'; }
  }

  /* ----------------------------- التبويبات ----------------------------- */
  function switchTab(tab) {
    S.tab = tab;
    $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    $$('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + tab));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  $$('.tab').forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));
  $$('[data-go]').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.go)));
  $('#doc1').addEventListener('click', e => { e.preventDefault(); window.open('/docs/01', '_blank'); });
  $('#doc2').addEventListener('click', e => { e.preventDefault(); window.open('/docs/02', '_blank'); });

  /* ----------------------------- بيانات ثابتة ----------------------------- */
  const ROADMAP = [
    { p: 'المرحلة ٠', t: 'إثبات الفكرة', d: 'أسبوعان', x: 'هذا النموذج + ٥ مقابلات مع سائقين و٣ محطات في أعزاز', g: 'هل يقبل السائق الحجز المسبق؟' },
    { p: 'المرحلة ١', t: 'الحلقة المغلقة', d: '٦–٨ أسابيع', x: 'QR + لوحة المسارات + قياس الخزانات + تسوية الوردية', g: 'خفض الانتظار ≥ ٦٠٪ في ٢٠٠ شاحنة' },
    { p: 'المرحلة ٢', t: 'التوريد والأساطيل', d: '٨–١٠ أسابيع', x: 'ربط منصة التوريد + محفظة الأسطول + فاتورة + تنبيه ٧٢ ساعة', g: '٣ عقود شركات نقل موقّعة' },
    { p: 'المرحلة ٣', t: 'الممر', d: '٣–٦ أشهر', x: 'مزامنة مواعيد العبور + بطاقة وقود واحدة + منفذ ثانٍ', g: 'عقد ترخيص ثانٍ لـ «ممر OS»' },
    { p: 'المرحلة ٤', t: 'الشبكة', d: '٩–١٨ شهراً', x: 'لوحة تدفّق للهيئة + توقّع الطلب + امتيازات المنافذ', g: 'تغطية ≥ ٤ منافذ' },
  ];

  function renderRoadmap() {
    $('#roadmap').innerHTML = ROADMAP.map(r => `
      <div class="rm-step">
        <div class="rm-phase">${r.p}</div><h4>${r.t}</h4><div class="rm-dur">${r.d}</div>
        <p>${r.x}</p><div class="rm-gate">بوابة القرار: ${r.g}</div>
      </div>`).join('');
  }

  /* ----------------------------- النبض والمؤشرات ----------------------------- */
  function renderPulse() {
    const m = S.state.metrics;
    $('#pulseKpis').innerHTML = `
      <div class="mini-kpi"><b>${fmt(m.liters_today)} <small>لتر</small></b><small>لترات الوردية</small></div>
      <div class="mini-kpi"><b>${m.avg_wait_min} <small>د</small></b><small>متوسط الانتظار</small></div>
      <div class="mini-kpi"><b>${fmt(m.active)}</b><small>في الطابور الذكي</small></div>
      <div class="mini-kpi"><b>${fmt(m.served)}</b><small>مركبة مُخدَّمة</small></div>`;
  }

  function renderKpis() {
    const m = S.state.metrics;
    const cards = [
      { l: 'متوسط زمن الانتظار', v: m.avg_wait_min, u: 'دقيقة', s: `خط الأساس: ${m.baseline_wait_min} دقيقة`, c: '#46d6b0' },
      { l: 'خفض زمن الانتظار', v: m.wait_reduction_pct + '%', s: 'مقابل الطابور التقليدي', c: '#f6a623' },
      { l: 'لترات الوردية', v: fmt(m.liters_today), u: 'لتر', s: `الخزانات: ${fmt(m.tank_total)} / ${fmt(m.tank_capacity)} لتر`, c: '#5aa6e8' },
      { l: 'إيراد الوردية', v: fmt(m.revenue_today), u: 'ل.س', s: 'من معاملات مُثبتة بالعداد', c: '#a991f5' },
      { l: 'نسبة الوفاء بالحجوزات', v: m.fulfilment_pct + '%', s: `${m.cancelled} حالات إلغاء/انتهاء`, c: '#46d6b0' },
      { l: 'استغلال المسارات', v: m.utilization_pct + '%', s: '٦ مسارات نشطة', c: '#f6a623' },
      { l: 'مركبات مُخدَّمة', v: fmt(m.served), s: `عدم حضور: ${m.no_show_pct}%`, c: '#5aa6e8' },
      { l: 'لترات بعقود أساطيل', v: m.contracted_liters_pct + '%', s: 'الطلب المتكرر هو الخندق', c: '#f6a623' },
    ];
    $('#kpiGrid').innerHTML = cards.map(c => `
      <div class="kpi" style="--k:${c.c}">
        <div class="kpi-label">${c.l}</div>
        <div class="kpi-val">${c.v}${c.u ? `<small>${c.u}</small>` : ''}</div>
        <div class="kpi-sub">${c.s}</div>
      </div>`).join('');
  }

  function renderCharts() {
    const h = S.state.hourly || [];
    const max = Math.max(...h, 1);
    const nowH = new Date().getHours();
    $('#hourlyChart').innerHTML = `
      <div style="display:flex;align-items:flex-end;gap:10px;height:180px;padding:8px 4px 0;border-bottom:1px solid var(--line)">
        ${h.map((v, i) => `
          <div style="flex:1;text-align:center;display:flex;flex-direction:column;justify-content:flex-end;height:100%">
            <div style="font-size:10px;color:var(--muted);margin-bottom:4px">${v}</div>
            <div style="height:${Math.max(4, Math.round(140 * v / max))}px;border-radius:7px 7px 0 0;background:linear-gradient(180deg,var(--amber),rgba(246,166,35,.25));transition:.5s"></div>
          </div>`).join('')}
      </div>
      <div style="display:flex;gap:10px;padding:6px 4px 0">
        ${h.map((v, i) => `<div style="flex:1;text-align:center;font-size:10px;color:var(--dim)">${((nowH - h.length + 1 + i + 24) % 24).toString().padStart(2, '0')}:00</div>`).join('')}
      </div>
      <div style="font-size:11px;color:var(--dim);margin-top:12px">الذروة تتوقعها المنصة من مواعيد عبور الشاحنات، فيُولّد أمر التوريد قبلها لا بعدها.</div>`;

    const tx = S.state.transactions || [];
    const byProduct = {};
    tx.forEach(t => byProduct[t.product_id] = (byProduct[t.product_id] || 0) + t.liters);
    const total = Object.values(byProduct).reduce((a, b) => a + b, 0) || 1;
    $('#mixChart').innerHTML = S.state.products.map(p => {
      const v = byProduct[p.id] || 0;
      const w = pct(v, total);
      return `<div style="margin-bottom:13px">
        <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:5px">
          <span>${esc(p.name)}</span><b style="color:${p.color};font-variant-numeric:tabular-nums">${fmt(v)} لتر · ${w}%</b>
        </div>
        <div class="gauge"><i style="width:${w}%;background:${p.color}"></i></div>
      </div>`;
    }).join('') + `<div style="font-size:11px;color:var(--dim);margin-top:6px">المازوت بأنواعه يستحوذ على الحصة الأكبر — لذلك يُبنى التوقّع حول الشاحنات أولاً.</div>`;
  }

  /* ----------------------------- السائق ----------------------------- */
  function initForm() {
    if (S.formReady) return;
    const p = $('#productSelect');
    p.innerHTML = S.state.products.map(x =>
      `<option value="${x.id}">${esc(x.name)} — ${fmt(x.price)} ل.س/لتر</option>`).join('');
    $('#fleetSelect').innerHTML = `<option value="">سائق فردي (نقد / حوالة)</option>` +
      S.state.fleets.map(f => `<option value="${f.id}">${esc(f.name)} · ${f.tier}</option>`).join('');
    S.formReady = true;
  }

  function renderAvail() {
    const s = S.state;
    $('#availGrid').innerHTML = s.products.map(p => {
      const av = s.availability[p.id];
      const tpct = pct(p.tank, p.capacity);
      const low = tpct < 30;
      return `<div class="avail-card" style="--c:${p.color}">
        <div class="avail-top">
          <div><div class="avail-name">${esc(p.name)}</div><div class="avail-grade">${esc(p.grade)}</div></div>
          <div class="avail-price">${fmt(p.price)}<small>ل.س / لتر</small></div>
        </div>
        <div class="avail-meta"><span>مستوى الخزان</span><span class="num">${fmt(p.tank)} / ${fmt(p.capacity)} لتر</span></div>
        <div class="gauge"><i style="width:${tpct}%"></i></div>
        <div class="avail-foot">
          <span>المضمون المتاح للحجز</span>
          <b class="${low ? 'low' : ''}">${fmt(av)} لتر</b>
        </div>
      </div>`;
    }).join('');
    $('#bulletinNo').textContent = s.meta.bulletin;
    // حدّث أسعار الخيارات دون فقدان اختيار المستخدم
    $$('#productSelect option').forEach(o => {
      const pr = s.products.find(x => x.id === o.value);
      if (pr) o.textContent = `${pr.name} — ${fmt(pr.price)} ل.س/لتر`;
    });
  }

  function updateEstimate() {
    const f = $('#bookingForm');
    const p = S.state.products.find(x => x.id === f.elements.product_id.value);
    const liters = Number(f.elements.liters.value) || 0;
    const fee = f.elements.priority.checked ? S.state.settings.priority_fee : 0;
    $('#estimate').innerHTML = `<span>${esc(p ? p.name : '')} · ${fmt(liters)} لتر × ${fmt(p ? p.price : 0)} ل.س ${fee ? '+ رسوم أولوية' : ''}</span>
      <b>${fmt(liters * (p ? p.price : 0) + fee)} ل.س</b>`;
  }

  function renderTicket() {
    const box = $('#ticketBody');
    if (!S.ticket) {
      box.className = 'ticket-empty';
      box.innerHTML = `<div class="ticket-empty-ico">▦</div><p>لم يُصدر حجز بعد.<br><small>أكمل النموذج لتظهر التذكرة ورمز QR هنا.</small></p>`;
      return;
    }
    const live = (S.state.bookings || []).find(b => b.id === S.ticket.id) || S.ticket;
    const queue = S.state.bookings.filter(b => ['booked', 'called', 'fueling'].includes(b.state));
    const pos = queue.findIndex(b => b.id === live.id) + 1;
    box.className = '';
    box.innerHTML = `
      <div class="ticket">
        <div class="ticket-head"><span>ممر · كازية السلام</span><span>${esc(S.state.meta.bulletin)}</span></div>
        <div class="ticket-qr">${makeQR(live.qr)}</div>
        <div class="ticket-id">${esc(live.id)}</div>
        <div class="ticket-plate">${esc(live.plate)} · ${esc(live.driver)}</div>
        <div class="ticket-details">
          <div><small>المحروقات</small><b>${esc(live.product)}</b></div>
          <div><small>الكمية المضمونة</small><b>${fmt(live.liters)} لتر</b></div>
          <div><small>الحالة</small><b class="chip ${live.state}" style="border:0;padding:0;background:none">${STATE_LABEL[live.state]}</b></div>
          <div><small>المسار / الدور</small><b>${live.lane_id ? esc(live.lane_id) : (pos ? '#' + pos : '—')}</b></div>
          <div><small>اتجاه الرحلة</small><b>${esc(live.direction)}</b></div>
          <div><small>سعر اللتر المثبّت</small><b>${fmt(live.price)} ل.س</b></div>
        </div>
        <div class="ticket-total"><span>الإجمالي المستحق</span><b>${fmt(live.amount)} ل.س</b></div>
        <div class="ticket-note">الكمية محجوبة من الخزان لحظة الحجز · الرمز صالح لاستخدام واحد وعند المسار المخصص فقط · السعر مثبّت برقم النشرة أعلاه.</div>
      </div>`;
  }

  function renderDriverBookings() {
    const rows = S.state.bookings.slice(0, 14);
    $('#driverBookings').innerHTML = `
      <thead><tr><th>الحجز</th><th>اللوحة</th><th>المنتج</th><th>الكمية</th><th>الاتجاه</th><th>القناة</th><th>الحالة</th><th>الوقت</th></tr></thead>
      <tbody>${rows.map(b => `<tr>
        <td class="mono">${esc(b.id)}</td><td>${esc(b.plate)}</td><td>${esc(b.product)}</td>
        <td class="num">${fmt(b.liters)} ل</td><td>${esc(b.direction)}</td><td>${esc(b.channel)}</td>
        <td><span class="chip ${b.state}">${STATE_LABEL[b.state]}</span></td>
        <td class="num" style="direction:ltr">${hhmm(b.created_at)}</td></tr>`).join('')}</tbody>`;
  }

  /* ----------------------------- المشغّل ----------------------------- */
  function renderLanes() {
    $('#laneGrid').innerHTML = S.state.lanes.map(l => {
      const b = l.booking_id ? S.state.bookings.find(x => x.id === l.booking_id) : null;
      return `<div class="lane ${l.status === 'busy' ? 'busy-lane' : l.status === 'reserved' ? 'reserved-lane' : ''}">
        <div class="lane-name"><span>${esc(l.label)}</span><span class="mono">${esc(l.id)}</span></div>
        <div class="lane-status">${LANE_LABEL[l.status]}</div>
        <div class="lane-booking">${b ? esc(b.plate) + ' · ' + fmt(b.liters) + ' لتر' : '— في انتظار النداء —'}</div>
        <div class="lane-bar"><i></i></div>
      </div>`;
    }).join('');
  }

  function renderQueue() {
    const active = S.state.bookings.filter(b => ['booked', 'called', 'fueling'].includes(b.state));
    active.sort((a, b) => (b.priority ? 1 : 0) - (a.priority ? 1 : 0) || a.created_at.localeCompare(b.created_at));
    $('#queueCount').textContent = `${active.length} حجز نشط · ${S.state.metrics.active} في الطابور`;
    $('#queueTable').innerHTML = `
      <thead><tr><th>#</th><th>اللوحة</th><th>الحجز</th><th>المنتج / الكمية</th><th>الانتظار</th><th>المسار</th><th>الإجمالي</th><th>الحالة</th><th>إجراء</th></tr></thead>
      <tbody>${active.length ? active.map((b, i) => {
        let acts = '';
        if (b.state === 'booked') acts = `<button class="btn btn-teal btn-xs" data-act="call" data-id="${esc(b.id)}">استدعاء</button>`;
        if (b.state === 'called') acts = `<button class="btn btn-blue btn-xs" data-act="start" data-id="${esc(b.id)}">بدء التعبئة</button>`;
        if (b.state === 'fueling') acts = `<button class="btn btn-primary btn-xs" data-act="complete" data-id="${esc(b.id)}">إتمام</button>`;
        acts += `<button class="btn btn-red btn-xs" data-act="cancel" data-id="${esc(b.id)}">إلغاء</button>`;
        return `<tr>
          <td class="num">${i + 1}${b.priority ? ' ★' : ''}</td>
          <td>${esc(b.plate)}</td><td class="mono">${esc(b.id)}</td>
          <td>${esc(b.product)} · <span class="num">${fmt(b.liters)} ل</span></td>
          <td class="num">${agoMin(b.created_at)} د</td>
          <td>${b.lane_id ? `<span class="mono">${esc(b.lane_id)}</span>` : '—'}</td>
          <td class="num">${fmt(b.amount)}</td>
          <td><span class="chip ${b.state}">${STATE_LABEL[b.state]}</span></td>
          <td><div class="actions">${acts}</div></td></tr>`;
      }).join('') : `<tr><td colspan="9" style="text-align:center;color:var(--dim);padding:24px">الطابور فارغ — فعّل «المحاكاة الحيّة» أو أنشئ حجزاً من تبويب السائق.</td></tr>`}</tbody>`;
  }

  function renderTanks() {
    // احتفظ بقيمة حقل السعر الذي يحرّره المستخدم أثناء التحديث الحيّ
    const focused = document.activeElement;
    const keep = focused && focused.id && focused.id.startsWith('price-')
      ? { id: focused.id, value: focused.value } : null;
    $('#tankList').innerHTML = S.state.products.map(p => `
      <div class="tank-item">
        <div class="tank-top"><span class="tank-name" style="color:${p.color}">${esc(p.name)}</span>
          <span class="tank-val">${fmt(p.tank)} / ${fmt(p.capacity)} لتر · ${pct(p.tank, p.capacity)}%</span></div>
        <div class="gauge"><i style="width:${pct(p.tank, p.capacity)}%;background:${p.color}"></i></div>
        <div class="price-edit">
          <input type="number" id="price-${p.id}" value="${p.price}" min="1" aria-label="سعر ${esc(p.name)}">
          <button class="btn btn-ghost btn-xs" data-price="${p.id}">اعتماد السعر</button>
          <span>ل.س / لتر · النشرة ${esc(S.state.meta.bulletin)}</span>
        </div>
      </div>`).join('');
    if (keep) {
      const el = document.getElementById(keep.id);
      if (el) { el.value = keep.value; el.focus(); }
    }
  }

  function renderSupply() {
    $('#supplyTable').innerHTML = `
      <thead><tr><th>الطلب</th><th>المنتج</th><th>الكمية</th><th>الحالة</th><th>الوصول المتوقع</th><th>صلاحية الرابط</th><th>الصهريج</th></tr></thead>
      <tbody>${S.state.supply_orders.map(o => {
        const h = hoursLeft(o.valid_until);
        const warn = o.state !== 'واصل' && h < 24;
        return `<tr>
          <td class="mono">${esc(o.id)}</td><td>${esc(o.product)}</td>
          <td class="num">${fmt(o.requested_l)} ل</td>
          <td><span class="chip ${o.state === 'واصل' ? 'done' : o.state === 'قيد الاعتماد' ? 'booked' : 'called'}">${esc(o.state)}</span></td>
          <td class="num" style="direction:ltr">${hhmm(o.eta)}</td>
          <td class="num" style="color:${warn ? 'var(--red)' : 'var(--teal)'}">${o.state === 'واصل' ? 'مُفرَّغ' : h + ' ساعة'}</td>
          <td>${esc(o.tanker)}</td></tr>`;
      }).join('')}</tbody>`;
  }

  function renderEvents() {
    $('#eventLog').innerHTML = S.state.events.slice(0, 20).map(e => `
      <div class="ev-row"><span class="ev-time">${hhmm(e.at)}</span>
        <span class="ev-type">${esc(e.type)}</span>
        <span class="ev-text">${esc(e.text)} <small style="color:var(--dim)">· ${esc(e.actor)}</small></span></div>`).join('');
  }

  /* ----------------------------- الإدارة: المحاكي ----------------------------- */
  const SIM_DEFS = [
    { key: 'capture_trucks', label: 'حصة الشاحنات من المنفذ', min: 5, max: 80, step: 1, unit: '%', factor: 100 },
    { key: 'capture_cars', label: 'حصة السيارات السياحية', min: 2, max: 40, step: 1, unit: '%', factor: 100 },
    { key: 'liters_truck', label: 'متوسط لترات الشاحنة', min: 100, max: 400, step: 10, unit: 'لتر' },
    { key: 'margin', label: 'هامش اللتر', min: 4, max: 30, step: 1, unit: 'ل.س' },
    { key: 'priority_fee', label: 'رسوم النافذة / الحجز', min: 0, max: 6000, step: 250, unit: 'ل.س' },
    { key: 'saas_stations', label: 'منافذ إضافية على «ممر OS»', min: 0, max: 10, step: 1, unit: 'منفذ' },
  ];

  function initSim() {
    if (S.sim) return;
    const st = S.state.settings;
    S.sim = {
      capture_trucks: Math.round(st.capture_trucks * 100),
      capture_cars: Math.round(st.capture_cars * 100),
      liters_truck: st.liters_truck,
      margin: st.margin,
      priority_fee: st.priority_fee,
      saas_stations: 2,
    };
    $('#simControls').innerHTML = SIM_DEFS.map(d => `
      <div class="sim-ctrl">
        <div class="sim-ctrl-top"><span>${d.label}</span><b id="simv-${d.key}">${fmt(S.sim[d.key])} ${d.unit}</b></div>
        <input type="range" data-sim="${d.key}" min="${d.min}" max="${d.max}" step="${d.step}" value="${S.sim[d.key]}">
      </div>`).join('');
    $$('#simControls input').forEach(el => el.addEventListener('input', e => {
      S.sim[e.target.dataset.sim] = Number(e.target.value);
      renderSim();
    }));
  }

  function renderSim() {
    if (!S.sim) return;
    const st = S.state.settings, v = S.sim;
    SIM_DEFS.forEach(d => {
      const el = $('#simv-' + d.key);
      if (el) el.textContent = fmt(v[d.key]) + ' ' + d.unit;
    });
    const trucks = st.trucks_day * v.capture_trucks / 100;
    const cars = st.vehicles_day * v.capture_cars / 100;
    const truckL = trucks * v.liters_truck;
    const carL = cars * st.liters_car;
    const dailyL = truckL + carL;
    const monthlyL = dailyL * 30;
    const fuelMargin = monthlyL * v.margin;
    const priority = trucks * 30 * v.priority_fee;
    const services = (trucks + cars) * 30 * 0.15 * 8000;
    const saas = v.saas_stations * st.saas_fee;
    const total = fuelMargin + priority + services + saas;
    const rows = [
      { l: 'هامش بيع الوقود', v: fuelMargin, c: '#f6a623' },
      { l: 'رسوم الحجز/الأولوية B2B', v: priority, c: '#46d6b0' },
      { l: 'خدمات التوقف (تقديري)', v: services, c: '#5aa6e8' },
      { l: 'تراخيص «ممر OS»', v: saas, c: '#a991f5' },
    ];
    const maxV = Math.max(...rows.map(r => r.v), 1);
    $('#simResults').innerHTML = `
      <div class="sim-line"><span>الشاحنات يومياً</span><b>${fmt(trucks)} شاحنة</b></div>
      <div class="sim-line"><span>المركبات السياحية يومياً</span><b>${fmt(cars)} مركبة</b></div>
      <div class="sim-line"><span>اللترات يومياً</span><b>${fmt(dailyL)} لتر</b></div>
      <div class="sim-line"><span>اللترات شهرياً</span><b>${fmt(monthlyL)} لتر</b></div>
      ${rows.map(r => `<div class="sim-line"><span>${r.l}</span><b>${fmt(r.v)} ل.س</b></div>`).join('')}
      <div class="sim-line total"><span>إجمالي الإيراد الشهري التقديري</span><b>${fmt(total)} ل.س</b></div>
      <div class="sim-bars">${rows.map(r => `<div class="sim-bar-row"><span>${r.l}</span>
        <div class="sim-bar-track"><i style="width:${pct(r.v, maxV)}%;--bc:${r.c}"></i></div></div>`).join('')}</div>`;
  }

  function renderFleets() {
    $('#fleetTable').innerHTML = `
      <thead><tr><th>الشركة</th><th>الفئة</th><th>الشاحنات</th><th>رصيد المحفظة</th><th>السقف الائتماني</th><th>لترات/شهر</th><th>استخدام السقف</th></tr></thead>
      <tbody>${S.state.fleets.map(f => `<tr>
        <td><b>${esc(f.name)}</b></td><td><span class="chip called">${esc(f.tier)}</span></td>
        <td class="num">${fmt(f.trucks)}</td><td class="num">${fmt(f.balance)}</td>
        <td class="num">${fmt(f.limit)}</td><td class="num">${fmt(f.liters_month)} ل</td>
        <td style="min-width:150px"><div class="gauge"><i style="width:${pct(f.limit - f.balance, f.limit)}%;background:var(--amber)"></i></div></td>
      </tr>`).join('')}</tbody>`;
  }

  /* ----------------------------- العرض الكلي ----------------------------- */
  function render() {
    if (!S.state) return;
    renderPulse();
    renderRoadmap();
    initForm();
    renderAvail();
    updateEstimate();
    renderTicket();
    renderDriverBookings();
    renderLanes();
    renderQueue();
    renderTanks();
    renderSupply();
    renderEvents();
    renderKpis();
    renderCharts();
    initSim();
    renderSim();
    renderFleets();
  }

  /* ----------------------------- الأحداث ----------------------------- */
  $('#bookingForm').addEventListener('input', updateEstimate);
  $('#bookingForm').addEventListener('change', updateEstimate);
  $('#bookingForm').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    const body = Object.fromEntries(new FormData(f).entries());
    body.priority = f.elements.priority.checked;
    body.liters = Number(body.liters);
    const res = await api('/api/bookings', body);
    if (!res.ok) { $('#formError').textContent = res.error || 'تعذّر الحجز'; return; }
    $('#formError').textContent = '';
    S.ticket = res.booking;
    S.state = res.state;
    render();
    toast(`تم تأكيد ${res.booking.id} · ${fmt(res.booking.liters)} لتر مضمونة`);
    switchTab('driver');
  });

  document.addEventListener('click', async e => {
    const actBtn = e.target.closest('[data-act]');
    if (actBtn) {
      const { act, id } = actBtn.dataset;
      const res = await api(`/api/bookings/${encodeURIComponent(id)}/${act}`, { reason: 'من لوحة المشغّل' });
      applyResult(res, { call: 'تم الاستدعاء وتخصيص المسار', start: 'بدأت التعبئة بعد تحقق QR',
        complete: 'أُتمّت العملية وسُجّلت المعاملة', cancel: 'أُلغي الحجز' }[act]);
      return;
    }
    const priceBtn = e.target.closest('[data-price]');
    if (priceBtn) {
      const pid = priceBtn.dataset.price;
      const val = Number($('#price-' + pid).value);
      const res = await api('/api/prices', { product_id: pid, price: val });
      applyResult(res, 'اعتُمدت نشرة السعر الجديدة');
      return;
    }
  });

  $('#callNextBtn').addEventListener('click', async () => {
    const res = await api('/api/queue/call-next', {});
    applyResult(res, res.ok ? 'تم استدعاء التالي' : null);
  });
  $('#tankerBtn').addEventListener('click', async () => {
    const p = [...S.state.products].sort((a, b) => a.tank / a.capacity - b.tank / b.capacity)[0];
    const res = await api(`/api/tanks/${p.id}/refill`, { liters: 8000 });
    applyResult(res, `سُجّل وصول صهريج ${p.name} · +8,000 لتر`);
  });
  $('#orderBtn').addEventListener('click', async () => {
    const res = await api('/api/supply-orders', { product_id: 'diesel', liters: 12000 });
    applyResult(res, res.ok ? `أُنشئ ${res.order.id} · صلاحية الرابط ٧٢ ساعة` : null);
  });
  $('#resetBtn').addEventListener('click', async () => {
    if (!window.confirm('إعادة بيانات العرض إلى الحالة الأولية؟')) return;
    const res = await api('/api/reset', {});
    S.ticket = null;
    applyResult(res, 'أُعيد ضبط بيانات العرض');
  });
  $('#autoToggle').addEventListener('change', e => {
    S.auto = e.target.checked;
    toast(S.auto ? 'المحاكاة الحيّة مُفعّلة' : 'المحاكاة متوقفة — التشغيل يدوي');
  });

  /* ----------------------------- الحلقة الحيّة ----------------------------- */
  setInterval(() => {
    $('#clock').textContent = new Date().toLocaleTimeString('en-GB');
  }, 1000);

  async function loop() {
    try {
      const res = await api('/api/tick', { auto: S.auto });
      if (res && res.state) { S.state = res.state; render(); }
    } catch (e) { /* الشبكة قد تنقطع عند الحدود — الواجهة تبقى آخر حالة */ }
  }

  (async function boot() {
    renderRoadmap();
    try {
      const st = await api('/api/state');
      S.state = st;
      render();
    } catch (e) {
      toast('تعذّر الاتصال بخادم النموذج', true);
    }
    setInterval(loop, 7000);
  })();
})();
