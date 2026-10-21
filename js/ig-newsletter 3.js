/* Inside Geopolitics: newsletter signup.

   1. Any [data-nl-open] button opens a small signup panel below it. The
      address is posted to the WordPress endpoint
      (wp-mu-plugin-newsletter-signup.php), which adds it to the MailPoet list;
      MailPoet then emails a confirmation link -- nobody is subscribed until
      they click it.
   2. Links in those emails (confirm, unsubscribe) are handled on the CMS and
      bounced straight back here with ?newsletter=... (see
      wp-mu-plugin-redirect-public-frontend.php), so readers only ever see
      this site. This script shows the matching message.

   Header markup:
     <button type="button" class="nl-open" data-nl-open aria-haspopup="dialog">
       <svg ...></svg><span>Newsletter</span>
     </button>
   Styles live here, so every page's button and panel are identical. */
(function(){
  var ENDPOINT = 'https://cms.insidegeopolitics.com/wp-json/igp/v1/subscribe';
  var CMS = 'https://cms.insidegeopolitics.com/';
  var ENVELOPE = '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="3.5" width="13" height="9"/><path d="M1.5 4l6.5 5 6.5-5"/></svg>';

  var css = ''
    /* header button */
    /* Fixed height + flex centring with every child a block at line-height 1
       (same fix as the reticle readout), so the icon and the text sit dead
       centre in every browser instead of riding on the font's baseline. */
    /* Built exactly like the FPS box beside it -- 26px tall, border-box, a
       1px border -- so the two always come out the same height. */
    + '.nl-open{appearance:none;-webkit-appearance:none;margin:0;cursor:pointer;flex-shrink:0;align-self:center;'
    +   'height:26px;min-height:26px;max-height:26px;box-sizing:border-box;'
    +   'display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 13px;line-height:1;'
    +   'background:var(--accent,#fff000);border:1px solid var(--accent,#fff000);color:#0a0a0a;'
    +   'font-family:Poppins,sans-serif;font-weight:700;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;white-space:nowrap;'
    +   'transition:opacity .2s ease}'
    + '.nl-open:hover,.nl-open[aria-expanded="true"]{opacity:0.85}'
    + '.nl-open span{display:block;line-height:1}'
    + '.nl-open svg{display:block;flex-shrink:0;width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.5}'
    /* panel (signup) and card (messages) share a look */
    /* Same see-through, blurred background as the header and footer bars. */
    + '.nl-panel,.nl-card{box-sizing:border-box;background:rgba(8,8,8,0.82);border:1px solid rgba(255,255,255,0.14);'
    +   'box-shadow:0 12px 44px rgba(0,0,0,0.6);color:#f2f2f2;font-family:Poppins,sans-serif;'
    +   'backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px)}'
    + '.nl-panel{position:fixed;z-index:1000;width:340px;max-width:calc(100vw - 32px);padding:20px 20px 16px;'
    +   'opacity:0;transform:translateY(-6px);pointer-events:none;transition:opacity .18s ease,transform .18s ease}'
    + '.nl-panel.open{opacity:1;transform:none;pointer-events:auto}'
    + '.nl-panel.docked{border-top:0;box-shadow:-10px 14px 40px rgba(0,0,0,0.55)}'
    /* Homepage video mode (phones): full width under the top bar. */
    + 'html.m-ui .nl-panel{left:14px!important;right:14px!important;width:auto!important;max-width:none!important}'
    + '.nl-x{position:absolute;top:8px;right:8px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;'
    +   'appearance:none;border:0;background:none;color:#6d6d6d;cursor:pointer;font-size:16px;line-height:1}'
    + '.nl-x:hover{color:#f2f2f2}'
    + '.nl-kicker{font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--accent,#fff000);margin:0 0 7px}'
    + '.nl-title{font-weight:600;font-size:17px;line-height:1.3;margin:0 0 7px;padding-right:14px}'
    + '.nl-sub{font-size:12px;line-height:1.55;color:#a0a0a0;margin:0 0 14px}'
    + '.nl-fine{font-family:"IBM Plex Mono",monospace;font-size:9.5px;color:#6d6d6d;letter-spacing:0.03em;margin:9px 0 0}'
    /* the field */
    + '.nl-form{position:relative;height:36px;display:flex;align-items:stretch;box-sizing:border-box;margin:0;'
    +   'background:rgba(255,255,255,0.03);border:1px solid #333}'
    + '.nl-form:focus-within{border-color:rgba(255,240,0,0.55)}'
    /* iPhone zooms the page into any field under 16px; keep it at 16 on phones. */
    + '@media (pointer:coarse) and (max-width:899px){.nl-form input[type=email]{font-size:16px!important}}'
    + '.nl-form input[type=email]{flex:1;min-width:0;background:none;border:0;outline:0;box-sizing:border-box;padding:0 11px;'
    +   'color:#f2f2f2;font-family:"IBM Plex Mono",monospace;font-size:11.5px;letter-spacing:0.02em}'
    + '.nl-form input[type=email]::placeholder{color:#6d6d6d;opacity:1}'
    + '.nl-hp{position:absolute!important;left:-9999px!important;width:1px;height:1px;opacity:0}'
    + '.nl-form button{appearance:none;-webkit-appearance:none;border:0;margin:0;cursor:pointer;flex-shrink:0;padding:0 14px;'
    +   'background:var(--accent,#fff000);color:#0a0a0a;font-family:Poppins,sans-serif;font-weight:700;font-size:10px;'
    +   'letter-spacing:0.14em;text-transform:uppercase;transition:opacity .2s ease}'
    + '.nl-form button:hover{opacity:0.85}'
    + '.nl-form.sending button{opacity:0.5;cursor:default}'
    + '.nl-err{font-family:"IBM Plex Mono",monospace;font-size:10px;color:#ff6b5a;margin:7px 0 0;min-height:0}'
    + '.nl-err:empty{display:none}'
    + '.nl-done .nl-form,.nl-done .nl-fine,.nl-done .nl-err,.nl-done .nl-sub{display:none}'
    + '.nl-ok{display:none;font-size:12.5px;line-height:1.55;color:#cfcfcf;margin:0}'
    + '.nl-done .nl-ok{display:block}'
    /* return-from-email message */
    + '.nl-back{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;'
    +   'background:rgba(0,0,0,0.55);opacity:0;transition:opacity .2s ease}'
    + '.nl-back.open{opacity:1}'
    + '.nl-card{position:relative;width:380px;max-width:calc(100vw - 32px);padding:24px 24px 20px}'
    + '.nl-actions{display:flex;gap:10px;margin-top:16px}'
    + '.nl-btn{appearance:none;cursor:pointer;height:32px;padding:0 14px;display:flex;align-items:center;text-decoration:none;'
    +   'font-family:Poppins,sans-serif;font-weight:700;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;'
    +   'background:var(--accent,#fff000);color:#0a0a0a;border:1px solid var(--accent,#fff000)}'
    + '.nl-btn.ghost{background:none;color:#a0a0a0;border-color:#333}'
    + '.nl-btn.ghost:hover{color:#f2f2f2;border-color:#555}';
  var st = document.createElement('style');
  st.textContent = css;
  (document.head || document.documentElement).appendChild(st);

  // ---------- remembering subscribers (this browser) ----------
  // 'pending' once they submit the form, 'subscribed' once they confirm (or
  // arrive from a link in one of our emails), 'unsubscribed' if they leave.
  // Anything set here means: never prompt this reader to sign up.
  var STORE = 'igNewsletter';
  function setStatus(v){ try { localStorage.setItem(STORE, JSON.stringify({ s:v, t:Date.now() })); } catch(e){} }
  function getStatus(){ try { var o = JSON.parse(localStorage.getItem(STORE) || 'null'); return o && o.s || null; } catch(e){ return null; } }
  window.IGNewsletter = { status:getStatus };
  (function(){
    // Clicks from our newsletters carry utm_source=newsletter (or
    // utm_medium=email) -- MailPoet adds these when Google Analytics
    // campaign tracking is set on the newsletter.
    var q = new URLSearchParams(location.search);
    if(/newsletter/i.test(q.get('utm_source') || '') || /^e-?mail$/i.test(q.get('utm_medium') || '')) setStatus('subscribed');
  })();

  // ---------- signup panel ----------
  var panel = null, anchor = null, opened = 0;

  function buildPanel(){
    panel = document.createElement('div');
    panel.className = 'nl-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Subscribe to the Inside Geopolitics newsletter');
    panel.innerHTML = ''
      + '<button type="button" class="nl-x" aria-label="Close">&times;</button>'
      + '<p class="nl-kicker">Free newsletter</p>'
      + '<p class="nl-title">The key developments, in your inbox.</p>'
      + '<p class="nl-sub">Key developments and updates from the globe, in one short email. No spam, unsubscribe anytime.</p>'
      + '<form class="nl-form" novalidate>'
      +   '<input type="email" name="email" placeholder="Your email address" aria-label="Email address" autocomplete="email" required>'
      +   '<input type="text" name="website" class="nl-hp" tabindex="-1" autocomplete="off" aria-hidden="true">'
      +   '<button type="submit">Subscribe</button>'
      + '</form>'
      + '<p class="nl-err" role="alert"></p>'
      + '<p class="nl-fine">We’ll email you a link to confirm.</p>'
      + '<p class="nl-ok" role="status">Almost there: check your inbox and click the link we sent to confirm your subscription.</p>';
    document.body.appendChild(panel);

    var form = panel.querySelector('form'), input = form.querySelector('input[type=email]');
    var hp = form.querySelector('.nl-hp'), err = panel.querySelector('.nl-err');
    panel.querySelector('.nl-x').addEventListener('click', closePanel);
    input.addEventListener('input', function(){ err.textContent = ''; });

    form.addEventListener('submit', function(e){
      e.preventDefault();
      if(form.classList.contains('sending')) return;
      var email = input.value.trim();
      if(!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){ err.textContent = 'Please enter a valid email address.'; input.focus(); return; }
      err.textContent = '';
      form.classList.add('sending');
      // A plain form post: no CORS preflight, so it's one quick request.
      var body = 'email=' + encodeURIComponent(email)
        + '&website=' + encodeURIComponent(hp.value)
        + '&t=' + (Date.now() - opened);
      fetch(ENDPOINT, { method:'POST', body:body, credentials:'omit',
                        headers:{ 'Content-Type':'application/x-www-form-urlencoded' } })
        .then(function(r){ return r.json().catch(function(){ return { ok:false }; }); })
        .then(function(d){
          if(d && d.ok){ panel.classList.add('nl-done'); if(getStatus() !== 'subscribed') setStatus('pending'); }
          else err.textContent = (d && d.message) || 'Something went wrong. Please try again.';
        })
        .catch(function(){ err.textContent = 'Couldn’t connect. Please try again.'; })
        .then(function(){ form.classList.remove('sending'); });
    });
  }

  function place(){
    if(!panel || !anchor) return;
    // Homepage: dock into the corner formed by the header's bottom edge and
    // the right sidebar's vertical divider line, so the Latest Events feed
    // stays clear (covering the globe's edge is fine).
    var line = document.querySelector('.rail-divider-line'), header = document.querySelector('header');
    if(line && line.offsetParent && header){
      var lb = line.getBoundingClientRect(), hb = header.getBoundingClientRect();
      if(lb.height){
        panel.classList.add('docked');
        panel.style.top = Math.round(hb.bottom) + 'px';
        // Its right border sits exactly on the divider line, in the line's
        // own colour, so the line reads as running unbroken up to the header.
        panel.style.right = Math.round(window.innerWidth - lb.right) + 'px';
        panel.style.borderRightColor = getComputedStyle(line).backgroundColor || '';
        return;
      }
    }
    // Elsewhere: just under the button.
    panel.classList.remove('docked');
    panel.style.borderRightColor = '';
    var r = anchor.getBoundingClientRect();
    panel.style.top = Math.round(r.bottom + 10) + 'px';
    panel.style.right = Math.max(16, Math.round(window.innerWidth - r.right)) + 'px';
  }
  function openPanel(btn){
    if(!panel) buildPanel();
    anchor = btn;
    place();
    if(!opened) opened = Date.now();
    panel.classList.add('open');
    btn.setAttribute('aria-expanded', 'true');
    var input = panel.querySelector('input[type=email]');
    if(!panel.classList.contains('nl-done')) setTimeout(function(){ input.focus(); }, 60);
  }
  function closePanel(){
    if(!panel) return;
    panel.classList.remove('open');
    if(anchor) anchor.setAttribute('aria-expanded', 'false');
  }

  document.addEventListener('click', function(e){
    var btn = e.target.closest && e.target.closest('[data-nl-open]');
    if(btn){
      e.preventDefault();
      if(panel && panel.classList.contains('open') && anchor === btn) closePanel();
      else openPanel(btn);
      return;
    }
    if(panel && panel.classList.contains('open') && !panel.contains(e.target)) closePanel();
  });
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape' && panel && panel.classList.contains('open')){ closePanel(); if(anchor) anchor.focus(); }
  });
  window.addEventListener('resize', place);

  // ---------- back from an email link ----------
  function card(html){
    var back = document.createElement('div');
    back.className = 'nl-back';
    back.innerHTML = '<div class="nl-card" role="dialog" aria-modal="true">'
      + '<button type="button" class="nl-x" aria-label="Close">&times;</button>' + html + '</div>';
    function close(){ back.classList.remove('open'); setTimeout(function(){ back.remove(); }, 220); }
    back.addEventListener('click', function(e){
      if(e.target === back || (e.target.closest && e.target.closest('.nl-x, [data-nl-close]'))) close();
    });
    document.addEventListener('keydown', function esc(e){ if(e.key === 'Escape'){ close(); document.removeEventListener('keydown', esc); } });
    document.body.appendChild(back);
    requestAnimationFrame(function(){ back.classList.add('open'); });
  }

  function landing(){
    var params = new URLSearchParams(location.search);
    var state = params.get('newsletter');
    if(!state) return;
    var unsubUrl = params.get('u') || '';
    // Tidy the address bar: the message shows once, not on every reload.
    params.delete('newsletter'); params.delete('u');
    var q = params.toString();
    history.replaceState(null, '', location.pathname + (q ? '?' + q : '') + location.hash);

    if(state === 'confirmed') setStatus('subscribed');
    else if(state === 'unsubscribed') setStatus('unsubscribed');
    var show = function(){
      if(state === 'confirmed'){
        card('<p class="nl-kicker">Subscribed</p><p class="nl-title">You’re on the list.</p>'
          + '<p class="nl-sub" style="margin:0">Thanks for confirming. The next Inside Geopolitics newsletter will land in your inbox.</p>'
          + '<div class="nl-actions"><button type="button" class="nl-btn" data-nl-close>Explore the globe</button></div>');
      } else if(state === 'unsubscribed'){
        card('<p class="nl-kicker">Unsubscribed</p><p class="nl-title">You won’t get any more emails.</p>'
          + '<p class="nl-sub" style="margin:0">Changed your mind? Use “Newsletter” at the top of the page any time.</p>'
          + '<div class="nl-actions"><button type="button" class="nl-btn ghost" data-nl-close>Close</button></div>');
      } else if(state === 'leave' && unsubUrl.indexOf(CMS) === 0){
        // The real unsubscribe needs a deliberate click: email security
        // scanners open every link in a message, and would otherwise
        // unsubscribe people on delivery.
        card('<p class="nl-kicker">Newsletter</p><p class="nl-title">Unsubscribe from Inside Geopolitics?</p>'
          + '<p class="nl-sub" style="margin:0">You’ll stop receiving the newsletter. You can sign up again any time.</p>'
          + '<div class="nl-actions"><a class="nl-btn" href="' + unsubUrl.replace(/"/g, '&quot;') + '">Yes, unsubscribe</a>'
          + '<button type="button" class="nl-btn ghost" data-nl-close>Keep me subscribed</button></div>');
      }
    };
    // The homepage opens behind its loading screen -- wait for that to clear.
    var waited = 0;
    (function when(){
      if(!document.getElementById('loader') || waited > 12000) show();
      else { waited += 200; setTimeout(when, 200); }
    })();
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', landing);
  else landing();
})();
