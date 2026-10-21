/* Inside Geopolitics: "lens push" transition for the loader reveal and for
   moving between pages -- the page defocuses while pushing in slightly,
   cuts, and the next view settles back to sharp at its normal size. The
   push keeps the blurred edges off-screen.

   - Clicking Home / Developments / About defocuses (200 ms), then navigates;
     the next page settles (450 ms) as it loads.
   - window.IGTransition.run() is used by the homepage loader for its reveal.
   - Plain CSS blur + scale on the page, so it is GPU-accelerated in every
     modern browser (Safari included).
   - Skipped for prefers-reduced-motion. Back/forward restores are never
     blurred (and any leftover filter is cleared). */
(function(){
  var root = document.documentElement;
  var reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var FLAG = 'igTransitionIn';
  var PAGES = { '/':1, '/index.html':1, '/developments':1, '/inside-geopolitics-archive.html':1, '/about':1, '/about.html':1 };
  var OUT_MS = 200, IN_MS = 450;

  // Blur radii are tuned at 1920 px wide and scale with the window (never
  // below half, so phones still get a visible defocus).
  function px(v){ return v * Math.max(0.5, window.innerWidth / 1920); }
  // k runs 0..1 through each half.
  function outFx(k){ return { blur: 10 * k * k, scale: 1 + 0.04 * k * k }; }
  function inFx(k){ var r = Math.pow(1 - k, 3); return { blur: 10 * r, scale: 1 + 0.04 * r }; }

  var savedBg = null;
  function apply(fx){
    if(fx.blur < 0.05 && fx.scale < 1.0005){ clear(); return; }
    // Blurred edges sample past the page: back them with the page colour
    // instead of the browser's default white.
    if(savedBg === null){
      savedBg = root.style.backgroundColor;
      var bg = document.body && getComputedStyle(document.body).backgroundColor;
      root.style.backgroundColor = (bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) ? bg : '#0d0d0d';
      root.style.colorScheme = 'dark';   // makes the browser's own backdrop dark, not white
    }
    root.style.filter = 'blur(' + px(fx.blur).toFixed(2) + 'px)';
    // Push in around the middle of what's on screen (pages can be scrolled).
    root.style.transformOrigin = (window.innerWidth / 2) + 'px ' + ((window.pageYOffset || 0) + window.innerHeight / 2) + 'px';
    root.style.transform = 'scale(' + fx.scale.toFixed(4) + ')';
  }

  var raf = 0;
  function clear(){
    if(raf) cancelAnimationFrame(raf); raf = 0;
    root.style.filter = ''; root.style.transform = ''; root.style.transformOrigin = '';
    if(savedBg !== null){ root.style.backgroundColor = savedBg; root.style.colorScheme = ''; savedBg = null; }
  }

  // opts: outMs (defocus), inMs (refocus), onPeak (fires at the cut, between
  // the two), onDone, hold (leave the last frame applied -- used while the
  // browser loads the next page).
  function run(opts){
    opts = opts || {};
    var outMs = opts.outMs == null ? OUT_MS : opts.outMs, inMs = opts.inMs == null ? IN_MS : opts.inMs;
    var peaked = false;
    function fire(){ if(!peaked){ peaked = true; if(opts.onPeak) opts.onPeak(); } }
    if(reduce){ fire(); if(opts.onDone) opts.onDone(); return; }
    if(raf) cancelAnimationFrame(raf);
    var t0 = performance.now(), total = outMs + inMs;
    (function step(now){
      var t = now - t0;
      if(t < outMs) apply(outFx(t / outMs));
      else {
        fire();
        apply(inMs ? inFx(Math.min(1, (t - outMs) / inMs)) : outFx(1));
      }
      if(t < total){ raf = requestAnimationFrame(step); }
      else { raf = 0; if(!opts.hold) clear(); if(opts.onDone) opts.onDone(); }
    })(t0);
  }

  window.IGTransition = { run: run, clear: clear, enabled: !reduce };

  // ---- page transitions ----
  function samePage(url){
    var norm = function(p){ return p.replace(/\/index\.html$/, '/').replace(/\.html$/, '').replace(/\/inside-geopolitics-archive$/, '/developments'); };
    return norm(url.pathname) === norm(location.pathname);
  }
  document.addEventListener('click', function(e){
    if(reduce || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if(!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return;
    var url;
    try { url = new URL(a.href, location.href); } catch(err){ return; }
    if(url.origin !== location.origin || !PAGES[url.pathname] || samePage(url)) return;
    e.preventDefault();
    try { sessionStorage.setItem(FLAG, String(Date.now())); } catch(err){}
    var gone = false;
    function go(){ if(!gone){ gone = true; location.href = url.href; } }
    run({ inMs: 0, hold: true, onDone: go });
    setTimeout(go, 600);   // never let the effect hold up navigation
  });

  // Settle in when we arrived through one of the links above. Starts at the
  // blurred, pushed-in state straight away -- with the dark backdrop -- so the
  // new page never flashes sharp first or shows bright edges.
  var arrived = 0;
  try { arrived = +sessionStorage.getItem(FLAG) || 0; sessionStorage.removeItem(FLAG); } catch(err){}
  if(arrived && Date.now() - arrived < 4000 && !reduce){
    apply(inFx(0));
    var start = function(){ run({ outMs: 0 }); };
    if(document.body) start(); else document.addEventListener('DOMContentLoaded', start);
  }

  // A back/forward restore shows the page exactly as it was left -- possibly
  // mid-transition -- so always reset it.
  window.addEventListener('pageshow', function(e){ if(e.persisted) clear(); });
})();
