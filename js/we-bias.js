/* Coverage & Bias: reads a story's `coverage` list (outlet, time, headline for every article in its cluster; written by
   news-feed/fetch_news.py) and draws the Coverage & Bias tab. Where an older story has no `coverage` yet, it falls back to
   the `outlets` list (counts and regions only, no headlines).
   Region and ownership ratings below are DRAFT editorial ratings: change a row to change how an outlet is counted. */
(function(){
  var REGIONS = {
    west:['US, UK and Europe', '#5fb4ff'], ua:['Ukraine', '#f2d04c'], ru:['Russia', '#d98c5f'], mideast:['Middle East', '#4fd1c5'],
    sasia:['South Asia', '#a99bff'], easia:['East and SE Asia', '#ff8fb1'], china:['China', '#c58cff'],
    africa:['Africa', '#a3b86c'], latam:['Latin America', '#ffb37a']
  };
  var OWN = { ind:['Independent', '#d9d2c3'], pub:['Public service', '#7fd6a6'], govt:['Government-linked', '#c58cff'] };
  // outlet: [country, region, ownership, note]
  var M = {
    'Reuters':['United Kingdom','west','ind'], 'AP':['United States','west','ind'], 'BBC News':['United Kingdom','west','pub'],
    'The Guardian':['United Kingdom','west','ind'], 'Sky News':['United Kingdom','west','ind'], 'NPR':['United States','west','pub'],
    'DW':['Germany','west','pub'], 'France 24':['France','west','pub'], 'Le Monde':['France','west','ind'], 'Euronews':['France','west','ind'],
    'Politico Europe':['Belgium','west','ind'], 'El País':['Spain','west','ind'], 'Al-Monitor':['United States','west','ind'],
    'NK News':['United States','west','ind'], 'The Diplomat':['United States','west','ind'], 'Balkan Insight':['Serbia','west','ind'],
    'Notes from Poland':['Poland','west','ind'], 'OC Media':['Georgia','west','ind'],
    'Kyiv Independent':['Ukraine','ua','ind'], 'Ukrainska Pravda':['Ukraine','ua','ind'],
    'Meduza':['Russia','ru','ind','in exile, Latvia'], 'The Moscow Times':['Russia','ru','ind','in exile, Netherlands'],
    'Al Jazeera':['Qatar','mideast','govt'], 'The New Arab':['Qatar','mideast','govt','London, Qatar-funded'],
    'Arab News':['Saudi Arabia','mideast','govt'], 'Asharq Al-Awsat':['Saudi Arabia','mideast','govt'], 'The National':['UAE','mideast','govt'],
    'Middle East Eye':['United Kingdom','mideast','ind','London'], 'Times of Israel':['Israel','mideast','ind'], 'Jerusalem Post':['Israel','mideast','ind'],
    'Daily Sabah':['Turkey','mideast','govt'], 'Iran International':['United Kingdom','mideast','ind','London, Persian-language exile outlet'],
    'Press TV':['Iran','mideast','govt'], 'Fars':['Iran','mideast','govt'], 'Mehr News':['Iran','mideast','govt'],
    'Dawn':['Pakistan','sasia','ind'], 'The Hindu':['India','sasia','ind'],
    'Yonhap':['South Korea','easia','pub'], 'Japan Times':['Japan','easia','ind'], 'CNA':['Singapore','easia','govt'],
    'Taipei Times':['Taiwan','easia','ind'], 'The Irrawaddy':['Myanmar','easia','ind','in exile, Thailand'], 'Rappler':['Philippines','easia','ind'],
    'SCMP':['Hong Kong','china','ind'], 'Xinhua':['China','china','govt'], "People's Daily":['China','china','govt'],
    'China Daily':['China','china','govt'], 'CGTN':['China','china','govt'],
    'RFI Africa':['France','africa','pub'], 'France 24 Africa':['France','africa','pub'], 'Africanews':['Republic of the Congo','africa','ind'],
    'Radio Dabanga':['Sudan','africa','ind','in exile, Netherlands'], 'Premium Times':['Nigeria','africa','ind'], 'Daily Maverick':['South Africa','africa','ind'],
    'Mexico News Daily':['Mexico','latam','ind'], 'Buenos Aires Times':['Argentina','latam','ind']
  };
  // regions we read at least one outlet from, so "not covered" only names places we actually looked
  var READ = {}; Object.keys(M).forEach(function(k){ READ[M[k][1]] = 1; });

  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c]; }); }
  function when(t){ var d = new Date(t); if(isNaN(d)) return ''; return d.getUTCDate() + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getUTCMonth()] + ', ' + d.toISOString().slice(11, 16); }
  function words(t){ return String(t).toLowerCase().replace(/[’‘]/g, "'").replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean); }
  function sharedRun(a, b){ var best = 0; for(var i = 0; i < a.length; i++) for(var j = 0; j < b.length; j++){ var k = 0; while(a[i + k] && a[i + k] === b[j + k]) k++; if(k > best) best = k; } return best; }
  function quotes(t){ var out = [], m, re = /(?:^|\s)['‘]([^'‘’]{3,40})['’](?=$|[\s,.:;])/g; while((m = re.exec(t))) out.push(m[1].toLowerCase()); return out; }
  // Same quoted phrase plus a shared 4-word run = the same wire story, counted as one report.
  function wireGroups(arts){
    var p = arts.map(function(_, i){ return i; }), W = arts.map(function(a){ return words(a.title); }), Q = arts.map(function(a){ return quotes(a.title); });
    function find(i){ return p[i] === i ? i : (p[i] = find(p[i])); }
    for(var i = 0; i < arts.length; i++) for(var j = i + 1; j < arts.length; j++)
      if(Q[i].some(function(q){ return Q[j].indexOf(q) >= 0; }) && sharedRun(W[i], W[j]) >= 4) p[find(j)] = find(i);
    var g = {}; arts.forEach(function(a, i){ (g[find(i)] = g[find(i)] || []).push(a); }); return Object.keys(g).map(function(k){ return g[k]; });
  }
  function articles(story){
    var src = Array.isArray(story.coverage) && story.coverage.length ? story.coverage.map(function(c){ return { outlet:c.o, time:c.t, title:c.h || '' }; })
      : (story.outlets || []).map(function(o){ return { outlet:o, time:story.time, title:'' }; });
    var seen = {}, out = [];
    src.forEach(function(a){ var m = M[a.outlet]; if(!m || seen[a.outlet]) return; seen[a.outlet] = 1;   // one row per outlet, unknown outlets are left out of the counts
      out.push({ outlet:a.outlet, time:a.time, title:a.title, country:m[0], region:m[1], own:m[2], where:m[3] || m[0] }); });
    return out;
  }
  function tally(arts, key){ var c = {}; arts.forEach(function(a){ c[a[key]] = (c[a[key]] || 0) + 1; }); return c; }

  function build(story){
    var arts = articles(story), hasHeads = arts.some(function(a){ return a.title; });
    if(!arts.length) return { html:'<p class="bias-note">No outlet details for this story yet.</p>', count:0 };
    var groups = wireGroups(arts), n = groups.length, share = {}, h = 0, nReg = Object.keys(REGIONS).length;
    groups.forEach(function(g){ g.forEach(function(a){ share[a.region] = (share[a.region] || 0) + 1 / g.length; }); });
    Object.keys(share).forEach(function(k){ var q = share[k] / n; h -= q * Math.log(q); });
    var score = n > 1 ? Math.round(100 * h / Math.log(nReg)) : 0;
    var byRegion = tally(arts, 'region'), byOwn = tally(arts, 'own');
    var top = Object.keys(share).sort(function(a, b){ return share[b] - share[a]; })[0], topPct = Math.round(100 * share[top] / n);
    var covered = Object.keys(byRegion).length;
    var missing = Object.keys(REGIONS).filter(function(r){ return READ[r] && !byRegion[r]; });
    var copies = groups.filter(function(g){ return g.length > 1; }).reduce(function(s, g){ return s + g.length; }, 0);
    var html = '';
    if(arts.length === 1){
      html += '<h3 class="bias-take">Only one outlet has reported this</h3>';
    } else {
      html += '<h3 class="bias-take">Mostly reported from ' + esc(top === 'west' ? 'the West' : top === 'mideast' ? 'the Middle East' : REGIONS[top][0]) + '</h3>';
    }
    html += '<div class="bias-facts"><div><b>' + arts.length + '</b><span>outlet' + (arts.length > 1 ? 's' : '') + '</span></div><div><b>' + n + '</b><span>separate report' + (n > 1 ? 's' : '') + '</span></div><div><b>' + covered + ' of ' + nReg + '</b><span>world regions</span></div></div>';
    if(arts.length > 1){
      var label = score >= 80 ? 'Very broad' : score >= 60 ? 'Broad, but uneven' : score >= 35 ? 'Limited' : 'Narrow';
      html += '<section class="bias-sec"><div class="bias-h">Perspective balance</div><div class="bias-balance"><div class="bias-score" style="--v:' + score + '"><span>' + score + '</span></div>' +
        '<p><b>' + label + '</b>' + (covered === 1 ? 'Only one region has covered it.' : covered + ' regions covered it' + (topPct >= 40 ? ', but one of them did ' + topPct + '% of the reporting.' : ', with the reporting spread fairly evenly.')) + '</p></div></section>';
    }
    var regs = Object.keys(REGIONS).filter(function(r){ return byRegion[r]; }).sort(function(a, b){ return byRegion[b] - byRegion[a]; });
    // One slim bar, split by region in proportion to how many outlets each contributed (same weight as the Potential Impact scale).
    html += '<section class="bias-sec bias-who"><div class="bias-h">Who reported it' + '' + '</div>' +
      '<div class="bias-split">' + regs.map(function(r){ return '<button type="button" class="bias-seg bias-row" data-r="' + r + '" style="--c:' + REGIONS[r][1] + ';flex:' + byRegion[r] + '" aria-label="' + esc(REGIONS[r][0]) + ': ' + byRegion[r] + '"></button>'; }).join('') + '</div>' +
      '<div class="bias-leg">' + regs.map(function(r){ return '<button type="button" class="bias-lg bias-row" data-r="' + r + '" style="--c:' + REGIONS[r][1] + '"><i></i>' + esc(REGIONS[r][0]) + ' <b>' + byRegion[r] + '</b></button>'; }).join('') + '</div></section>';
    if(hasHeads){
      html += '<section class="bias-sec bias-hl"><div class="bias-h">Same story, different headlines <span class="bias-pill" hidden></span><span class="bias-nav"><button type="button" class="bias-prev" aria-label="Previous headline">\u2039</button><span class="bias-pos"></span><button type="button" class="bias-next" aria-label="Next headline">\u203a</button></span></div><div class="bias-heads"></div></section>';
    }
    html += '<section class="bias-sec"><div class="bias-h">Who owns the outlets</div><div class="bias-own">' +
      Object.keys(OWN).map(function(k){ return '<span style="--c:' + OWN[k][1] + ';flex:' + (byOwn[k] || 0) + '"></span>'; }).join('') + '</div><div class="bias-key">' +
      Object.keys(OWN).map(function(k){ return '<span><i style="--c:' + OWN[k][1] + '"></i>' + OWN[k][0] + ' ' + (byOwn[k] || 0) + '</span>'; }).join('') + '</div>' +
      (copies ? '<p class="bias-note">' + copies + ' outlets ran the same wire story, word for word. We count them as one report.</p>' : '') +
      '<p class="bias-note">Regions and ownership are draft ratings by War Events, based on where an outlet is based and who funds it.</p></section>';
    return { html:html, count:arts.length, arts:arts, groups:groups };
  }

  var cache = new WeakMap();
  function heads(pane, state){
    var box = pane.querySelector('.bias-heads'); if(!box) return;
    var list = state.arts.filter(function(a){ return a.title && (!state.filter || a.region === state.filter); });
    var wireSize = new Map(); state.groups.forEach(function(g){ if(g.length > 1) g.forEach(function(a){ wireSize.set(a, g.length); }); });
    box.innerHTML = list.map(function(a){
      var chips = (a.own === 'govt' ? '<span class="bias-chip">Government-linked</span>' : '') + (wireSize.get(a) ? '<span class="bias-chip">Shared wire story</span>' : '');
      return '<div class="bias-hcard" style="--c:' + REGIONS[a.region][1] + '"><div class="o">' + esc(a.outlet) + ' <em>\u00b7 ' + esc(a.where) + ' \u00b7 ' + esc(when(a.time)) + '</em>' + chips + '</div><div class="t">' + esc(a.title) + '</div></div>';
    }).join('');
    box.scrollLeft = 0;
    var pill = pane.querySelector('.bias-pill'); pill.hidden = !state.filter;
    pill.innerHTML = state.filter ? esc(REGIONS[state.filter][0]) + ' <button type="button" class="bias-x" aria-label="Clear filter">\u00d7</button>' : '';
    pane.querySelector('.bias-nav').style.display = list.length > 1 ? '' : 'none';
    [].forEach.call(pane.querySelectorAll('.bias-row[data-r]'), function(b){ b.classList.toggle('on', b.dataset.r === state.filter); });
    pos(pane);
  }
  function pos(pane){
    var box = pane.querySelector('.bias-heads'), el = pane.querySelector('.bias-pos'); if(!box || !el) return;
    var n = box.children.length, w = box.firstElementChild ? box.firstElementChild.offsetWidth + 8 : 1;
    el.textContent = n ? (Math.min(n, Math.round(box.scrollLeft / w) + 1)) + ' / ' + n : '';
  }

  window.WEBias = {
    // Fills a card's Coverage & Bias pane; returns the number of outlets (for the tab badge).
    fill: function(pane, story){
      var r = build(story); pane.innerHTML = r.html; cache.set(pane, { arts:r.arts || [], groups:r.groups || [], filter:null, all:false });
      if(r.arts) heads(pane, cache.get(pane));
      var hb = pane.querySelector('.bias-heads');
      if(hb){
        hb.addEventListener('scroll', function(){ pos(pane); }, { passive:true });
        // sideways scrolling belongs to the headlines, so it must not turn the page to the next story
        hb.addEventListener('wheel', function(e){ if(Math.abs(e.deltaX) > Math.abs(e.deltaY)) e.stopPropagation(); }, { passive:true });
      }
      return r.count;
    }
  };

  document.addEventListener('click', function(e){
    var t = e.target; if(!t.closest) return;
    var tab = t.closest('.rc-tab');
    if(tab){
      var rc = tab.closest('.rc'); if(!rc) return;
      var bias = tab.dataset.t === 'bias';
      [].forEach.call(rc.querySelectorAll('.rc-tab'), function(b){ var on = b === tab; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); });
      var sp = rc.querySelector('.rc-pane.story'), bp = rc.querySelector('.rc-pane.bias');
      if(sp) sp.hidden = bias; if(bp) bp.hidden = !bias;
      rc.classList.toggle('bias-on', bias);
      return;
    }
    var pane = t.closest('.rc-pane.bias'); if(!pane) return;
    var st = cache.get(pane); if(!st) return;
    var row = t.closest('.bias-row[data-r]');
    if(row){ st.filter = st.filter === row.dataset.r ? null : row.dataset.r; heads(pane, st); return; }
    if(t.closest('.bias-x')){ st.filter = null; heads(pane, st); return; }
    var dir = t.closest('.bias-next') ? 1 : t.closest('.bias-prev') ? -1 : 0;
    if(dir){ var hb = pane.querySelector('.bias-heads'), c = hb.firstElementChild; if(c) hb.scrollBy({ left:dir * (c.offsetWidth + 8), behavior:'smooth' }); }
  });
})();
