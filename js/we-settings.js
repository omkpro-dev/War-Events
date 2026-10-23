/* Settings button + sheet for the phone banner (every page that has the banner).
   Button: far right of the banner, same size and shape as the day/night and map buttons.
   Sheet: Appearance (Night / Day), Show map (map pages), Breaking-news alerts (iPhone app), legal and contact links. */
(function(){
  var root = document.documentElement;
  var base = root.classList.contains('we-app') ? '/index.html' : '';
  function link(p){ return p + (base ? '/index.html' : ''); }

  var css = '' +
  '.we-setbtn{ display:none; }' +
  'html.we-phone .we-setbtn{ display:inline-flex; }' +
  '@media (max-width:820px){ .we-setbtn{ display:inline-flex; } }' +
  '.we-setbtn{ align-items:center; justify-content:center; width:30px; height:30px; padding:0; margin-left:auto; border-radius:5px; cursor:pointer; flex:0 0 auto; order:9;' +
  '  background:var(--pn-bg, rgba(18,30,52,0.3)); color:var(--t1, #f0e9da); border:1px solid var(--pn-line, rgba(255,255,255,0.28)); }' +
  '.we-setbtn svg{ width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:1.5; stroke-linecap:round; stroke-linejoin:round; }' +
  ':root[data-theme="light"] .we-setbtn{ color:#0f2044; border-color:rgba(15,32,68,0.28); background:rgba(15,32,68,0.05); }' +
  '.we-set-back{ position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5); opacity:0; pointer-events:none; transition:opacity .2s ease; }' +
  '.we-set-back.open{ opacity:1; pointer-events:auto; }' +
  '.we-set{ position:fixed; left:0; right:0; bottom:0; z-index:201; max-height:88vh; max-height:88dvh; overflow-y:auto; border-radius:16px 16px 0 0; padding:6px 18px calc(20px + env(safe-area-inset-bottom));' +
  '  background:#121b2c; color:#f0e9da; border:1px solid rgba(255,255,255,0.22); border-bottom:0; box-shadow:0 -14px 40px rgba(0,0,0,0.45); transform:translateY(105%); transition:transform .26s ease; font-family:"Barlow",sans-serif; }' +
  '.we-set.open{ transform:none; }' +
  ':root[data-theme="light"] .we-set{ background:#eeeeee; color:#17233f; border-color:rgba(15,32,68,0.2); box-shadow:0 -14px 40px rgba(15,32,68,0.2); }' +
  '.we-set-grab{ width:38px; height:4px; border-radius:2px; background:currentColor; opacity:.28; margin:6px auto 10px; }' +
  '.we-set-hd{ display:flex; align-items:center; justify-content:space-between; margin:0 0 6px; }' +
  '.we-set-hd b{ font-size:20px; font-weight:700; }' +
  '.we-set-x{ width:32px; height:32px; border-radius:5px; border:1px solid currentColor; border-color:rgba(255,255,255,0.28); background:transparent; color:inherit; font-size:18px; line-height:1; cursor:pointer; }' +
  ':root[data-theme="light"] .we-set-x{ border-color:rgba(15,32,68,0.28); }' +
  '.we-set-sec{ margin:16px 0 6px; font-size:12px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; opacity:.65; }' +
  '.we-set-row{ display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:46px; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.12); font-size:16px; }' +
  ':root[data-theme="light"] .we-set-row{ border-bottom-color:rgba(15,32,68,0.14); }' +
  '.we-set-row small{ display:block; font-size:12.5px; opacity:.65; margin-top:2px; }' +
  '.we-set-row a{ color:inherit; text-decoration:none; display:flex; width:100%; justify-content:space-between; }' +
  '.we-seg{ display:inline-flex; padding:2px; border-radius:8px; border:1px solid rgba(255,255,255,0.28); }' +
  ':root[data-theme="light"] .we-seg{ border-color:rgba(15,32,68,0.28); }' +
  '.we-seg button{ border:0; background:transparent; color:inherit; font:600 14px "Barlow",sans-serif; padding:7px 14px; border-radius:6px; cursor:pointer; }' +
  '.we-seg button.on{ background:#f0e9da; color:#0b1628; }' +
  ':root[data-theme="light"] .we-seg button.on{ background:#0f2044; color:#fff; }' +
  '.we-sw{ position:relative; width:46px; height:28px; border-radius:14px; border:0; cursor:pointer; background:rgba(255,255,255,0.22); flex:0 0 auto; transition:background .2s; }' +
  ':root[data-theme="light"] .we-sw{ background:rgba(15,32,68,0.2); }' +
  '.we-sw::after{ content:""; position:absolute; top:3px; left:3px; width:22px; height:22px; border-radius:50%; background:#fff; transition:transform .2s; box-shadow:0 1px 3px rgba(0,0,0,.3); }' +
  '.we-sw[aria-checked="true"], :root[data-theme="light"] .we-sw[aria-checked="true"]{ background:#3fb68b; } .we-sw[aria-checked="true"]::after{ transform:translateX(18px); }' +
  '.we-set-foot{ margin-top:18px; text-align:center; font-size:12.5px; opacity:.6; }';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  var ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4.5h6.2M11.4 4.5H14M2 11.5h2.6M7.8 11.5H14"/><circle cx="9.8" cy="4.5" r="1.6"/><circle cx="6.2" cy="11.5" r="1.6"/></svg>';
  var btn, back, sheet, built = false;

  function isLight(){ return root.getAttribute('data-theme') === 'light'; }
  function setLight(want){ if(isLight() === want) return; var t = document.getElementById('themeToggle'); if(t) t.click(); }
  function nomap(){ return root.classList.contains('we-nomap'); }

  function build(){
    sheet.innerHTML = '';
    var h = '<div class="we-set-grab"></div><div class="we-set-hd"><b>Settings</b><button type="button" class="we-set-x" aria-label="Close">&times;</button></div>' +
      '<div class="we-set-sec">Appearance</div><div class="we-set-row"><span>Colours</span><span class="we-seg" role="group" aria-label="Colours"><button type="button" data-th="dark">Night</button><button type="button" data-th="light">Day</button></span></div>';
    var mapBtn = document.querySelector('.we-mapbtn');
    if(mapBtn) h += '<div class="we-set-sec">Map</div><div class="we-set-row"><span>Show the map<small>Off turns the page into a plain news reader</small></span><button type="button" class="we-sw" role="switch" data-map aria-label="Show the map"></button></div>';
    if(window.WENative && window.WENative.alerts) h += '<div class="we-set-sec">Alerts</div><div class="we-set-row"><span>Breaking-news alerts<small data-alerts-note>A few a day at most, only major developments</small></span><button type="button" class="we-sw" role="switch" data-alerts aria-label="Breaking-news alerts"></button></div>';
    h += '<div class="we-set-sec">About</div>' +
      '<div class="we-set-row"><a href="' + link('/privacy') + '"><span>Privacy</span><span>&rsaquo;</span></a></div>' +
      '<div class="we-set-row"><a href="' + link('/takedown') + '"><span>Copyright &amp; takedown</span><span>&rsaquo;</span></a></div>' +
      '<div class="we-set-row"><a href="mailto:admin@entropyadvisory.com"><span>Contact<small>admin@entropyadvisory.com</small></span><span>&rsaquo;</span></a></div>' +
      '<div class="we-set-foot">War Events &middot; &copy; ' + new Date().getFullYear() + ' Omar Kharoti</div>';
    sheet.innerHTML = h;
    sheet.querySelector('.we-set-x').addEventListener('click', close);
    [].forEach.call(sheet.querySelectorAll('[data-th]'), function(b){ b.addEventListener('click', function(){ setLight(b.getAttribute('data-th') === 'light'); sync(); }); });
    var mw = sheet.querySelector('[data-map]'); if(mw) mw.addEventListener('click', function(){ var m = document.querySelector('.we-mapbtn'); if(m) m.click(); setTimeout(sync, 80); });
    var aw = sheet.querySelector('[data-alerts]');
    if(aw) aw.addEventListener('click', function(){
      var on = aw.getAttribute('aria-checked') === 'true';
      (on ? window.WENative.alerts.disable() : window.WENative.alerts.enable()).then(syncAlerts, syncAlerts);
    });
    built = true; sync(); syncAlerts();
  }
  function sync(){
    if(!built) return;
    [].forEach.call(sheet.querySelectorAll('[data-th]'), function(b){ b.classList.toggle('on', (b.getAttribute('data-th') === 'light') === isLight()); });
    var mw = sheet.querySelector('[data-map]'); if(mw) mw.setAttribute('aria-checked', String(!nomap()));
  }
  function syncAlerts(){
    var aw = sheet && sheet.querySelector('[data-alerts]'); if(!aw || !window.WENative) return;
    window.WENative.alerts.state().then(function(s){
      aw.setAttribute('aria-checked', String(s === 'on'));
      var n = sheet.querySelector('[data-alerts-note]'); if(n) n.textContent = s === 'denied' ? 'Turned off in iPhone Settings: allow notifications for War Events there' : 'A few a day at most, only major developments';
    }).catch(function(){});
  }
  function open(){ if(!built) build(); else { sync(); syncAlerts(); } back.classList.add('open'); sheet.classList.add('open'); }
  function close(){ back.classList.remove('open'); sheet.classList.remove('open'); }

  function init(){
    var hd = document.querySelector('header'); if(!hd || document.querySelector('.we-setbtn')) return;
    btn = document.createElement('button'); btn.type = 'button'; btn.className = 'we-setbtn'; btn.setAttribute('aria-label', 'Settings'); btn.innerHTML = ICON;
    hd.appendChild(btn);
    back = document.createElement('div'); back.className = 'we-set-back'; document.body.appendChild(back);
    sheet = document.createElement('div'); sheet.className = 'we-set'; sheet.setAttribute('role', 'dialog'); sheet.setAttribute('aria-label', 'Settings'); document.body.appendChild(sheet);
    btn.addEventListener('click', open); back.addEventListener('click', close);
    window.addEventListener('we-theme', sync);
    new MutationObserver(sync).observe(root, { attributes:true, attributeFilter:['data-theme', 'class'] });
    document.addEventListener('keydown', function(e){ if(e.key === 'Escape') close(); });
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
