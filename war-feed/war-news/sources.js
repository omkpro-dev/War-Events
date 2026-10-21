// War news sources and the list of conflicts the page tracks.
// Feeds tested and returning items on 16 Oct 2026.

const gnews = (q) =>
  `https://news.google.com/rss/search?q=${encodeURIComponent(q + ' when:1d')}&hl=en-US&gl=US&ceid=US:en`;

export const WAR_FEEDS = [
  // General world news (filtered down to conflict stories by the tagger)
  { id: 'aljazeera', name: 'Al Jazeera', url: 'https://www.aljazeera.com/xml/rss/all.xml' },
  { id: 'bbc-world', name: 'BBC', url: 'https://feeds.bbci.co.uk/news/world/rss.xml' },
  { id: 'guardian-world', name: 'The Guardian', url: 'https://www.theguardian.com/world/rss' },
  { id: 'france24', name: 'France 24', url: 'https://www.france24.com/en/rss' },
  { id: 'dw-world', name: 'DW', url: 'https://rss.dw.com/rdf/rss-en-world' },
  { id: 'mee', name: 'Middle East Eye', url: 'https://www.middleeasteye.net/rss' },
  { id: 'kyiv-independent', name: 'Kyiv Independent', url: 'https://kyivindependent.com/news-archive/rss/' },
  { id: 'crisisgroup', name: 'Crisis Group', url: 'https://www.crisisgroup.org/rss' },

  // One Google News search per conflict: pulls Reuters, AP and local outlets
  { id: 'gn-yemen', name: 'Google News', url: gnews('Yemen OR Houthi OR Houthis'), conflict: 'yemen' },
  { id: 'gn-sudan', name: 'Google News', url: gnews('Sudan RSF OR "Rapid Support Forces" OR "Sudanese army"'), conflict: 'sudan' },
  { id: 'gn-ukraine', name: 'Google News', url: gnews('Ukraine front OR Russian forces OR Ukrainian forces'), conflict: 'ukraine' },
  { id: 'gn-israel', name: 'Google News', url: gnews('Gaza OR "West Bank" OR Hezbollah OR "Israeli military"'), conflict: 'israel' },
  { id: 'gn-syria', name: 'Google News', url: gnews('Syria clashes OR SDF OR Sweida'), conflict: 'syria' },
  { id: 'gn-myanmar', name: 'Google News', url: gnews('Myanmar junta OR "Arakan Army" OR resistance forces Myanmar'), conflict: 'myanmar' },
  { id: 'gn-drc', name: 'Google News', url: gnews('M23 OR "eastern Congo" OR FARDC'), conflict: 'drc' },
  { id: 'gn-sahel', name: 'Google News', url: gnews('JNIM OR Mali jihadists OR Burkina Faso attack OR Niger attack'), conflict: 'sahel' },
  { id: 'gn-somalia', name: 'Google News', url: gnews('al-Shabaab OR Somalia army'), conflict: 'somalia' },
  { id: 'gn-afpak', name: 'Google News', url: gnews('Pakistan Afghanistan strikes OR TTP OR "Durand Line" OR Balochistan attack'), conflict: 'afpak' },
  { id: 'gn-ethiopia', name: 'Google News', url: gnews('Tigray OR TPLF OR Fano OR "Ethiopian army"'), conflict: 'ethiopia' },
  { id: 'gn-lakechad', name: 'Google News', url: gnews('ISWAP OR "Boko Haram" OR Borno attack'), conflict: 'lakechad' },
  { id: 'gn-iran', name: 'Google News', url: gnews('Iran war OR IRGC strike OR Hormuz OR "Kurdish fighters" Iran'), conflict: 'iran' },
];

// Optional GDELT searches (free, no key, one request per 5 s).
// Focused on control changes, which is what the Active Wars map needs.
export const WAR_GDELT_QUERIES = [
  { id: 'gdelt-yemen', conflict: 'yemen', q: '(Houthi OR Houthis OR Yemen) (captured OR seized OR "took control" OR recaptured OR advance)' },
  { id: 'gdelt-sudan', conflict: 'sudan', q: '(RSF OR "Rapid Support Forces" OR "Sudanese army") (captured OR seized OR "took control" OR recaptured)' },
  { id: 'gdelt-ukraine', conflict: 'ukraine', q: '(Russian OR Ukrainian) (captured OR liberated OR "took control" OR withdrew) village' },
];

// Words that make a story about armed conflict (a country name alone isn't enough).
export const WAR_CONTEXT = [
  'attack', 'strike', 'airstrike', 'air strike', 'drone', 'missile', 'rocket', 'shelling', 'shelled', 'bomb',
  'killed', 'casualties', 'troops', 'soldiers', 'militia', 'militants', 'fighters', 'rebels', 'forces',
  'clashes', 'fighting', 'offensive', 'frontline', 'front line', 'battle', 'siege', 'besieged', 'ceasefire',
  'truce', 'captured', 'seized', 'recaptured', 'retook', 'withdrew', 'advance', 'invasion', 'occupied',
  'hostage', 'artillery', 'military', 'war ', 'warplane', 'air defence', 'air defense', 'intercepted',
];

// Each conflict: words that tag a story to it, its sides (for the claim
// extractor), and a centre point for stories with no known place.
export const CONFLICTS = [
  {
    id: 'yemen', name: 'Yemen', center: [15.4, 45.0], zoom: 6,
    keywords: ['yemen', 'houthi', 'ansar allah', 'sanaa', "sana'a", 'aden', 'taiz', "ta'izz", 'hodeidah', 'marib', 'red sea shipping', 'bab el-mandeb', 'southern transitional council'],
    actors: [
      { id: 'houthis', name: 'Houthis', aliases: ['houthi', 'houthis', 'ansar allah', 'ansarallah'], colour: '#2e7d32' },
      { id: 'govt', name: 'Government (PLC)', aliases: ['yemeni government', 'government forces', 'presidential leadership council', 'national resistance', 'giants brigades', 'national army'], colour: '#c62828' },
      { id: 'stc', name: 'Southern Transitional Council', aliases: ['stc', 'southern transitional council', 'southern forces', 'security belt'], colour: '#1565c0' },
      { id: 'aqap', name: 'AQAP', aliases: ['aqap', 'al-qaeda in the arabian peninsula'], colour: '#424242' },
    ],
  },
  {
    id: 'sudan', name: 'Sudan', center: [14.0, 30.0], zoom: 5,
    keywords: ['sudan', 'rapid support forces', 'rsf', 'khartoum', 'omdurman', 'darfur', 'el fasher', 'al-fashir', 'kordofan', 'el obeid', 'burhan', 'hemedti', 'dagalo'],
    actors: [
      { id: 'saf', name: 'Sudanese Armed Forces', aliases: ['saf', 'sudanese army', 'sudanese armed forces', 'army'], colour: '#1565c0' },
      { id: 'rsf', name: 'Rapid Support Forces', aliases: ['rsf', 'rapid support forces', 'paramilitary'], colour: '#ef6c00' },
      { id: 'splm-n', name: 'SPLM-N (al-Hilu)', aliases: ['splm-n', 'sudan people\'s liberation movement-north'], colour: '#6a1b9a' },
    ],
  },
  {
    id: 'ukraine', name: 'Russia–Ukraine', center: [48.6, 35.5], zoom: 6,
    keywords: ['ukraine', 'ukrainian', 'kyiv', 'kharkiv', 'donetsk', 'donbas', 'zaporizhzhia', 'kherson', 'pokrovsk', 'kostiantynivka', 'kupiansk', 'zelensky', 'shahed', 'russian forces', 'russian army'],
    actors: [
      { id: 'russia', name: 'Russia', aliases: ['russia', 'russian forces', 'russian troops', 'russian army', 'moscow'], colour: '#c62828' },
      { id: 'ukraine', name: 'Ukraine', aliases: ['ukraine', 'ukrainian forces', 'ukrainian troops', 'ukrainian army', 'kyiv', 'afu'], colour: '#1565c0' },
    ],
  },
  {
    id: 'israel', name: 'Israel, Gaza & Lebanon', center: [32.0, 35.0], zoom: 7,
    keywords: ['gaza', 'hamas', 'west bank', 'hezbollah', 'idf', 'israeli military', 'israeli army', 'israeli strike', 'khan younis', 'rafah', 'jenin', 'south lebanon', 'southern lebanon'],
    actors: [
      { id: 'israel', name: 'Israel (IDF)', aliases: ['idf', 'israeli forces', 'israeli army', 'israeli military', 'israel'], colour: '#1565c0' },
      { id: 'hamas', name: 'Hamas', aliases: ['hamas', 'qassam'], colour: '#2e7d32' },
      { id: 'hezbollah', name: 'Hezbollah', aliases: ['hezbollah'], colour: '#f9a825' },
    ],
  },
  {
    id: 'syria', name: 'Syria', center: [35.0, 38.5], zoom: 6,
    keywords: ['syria', 'syrian', 'damascus', 'aleppo', 'idlib', 'sdf', 'syrian democratic forces', 'sweida', 'suwayda', 'deir ez-zor', 'raqqa', 'latakia'],
    actors: [
      { id: 'govt', name: 'Syrian government', aliases: ['syrian government', 'government forces', 'syrian army', 'damascus'], colour: '#2e7d32' },
      { id: 'sdf', name: 'SDF', aliases: ['sdf', 'syrian democratic forces', 'kurdish-led'], colour: '#f9a825' },
      { id: 'druze', name: 'Druze factions', aliases: ['druze fighters', 'druze factions'], colour: '#6a1b9a' },
      { id: 'is', name: 'Islamic State', aliases: ['islamic state', 'isis', 'isil', 'daesh'], colour: '#424242' },
    ],
  },
  {
    id: 'myanmar', name: 'Myanmar', center: [21.0, 96.0], zoom: 5,
    keywords: ['myanmar', 'burma', 'junta', 'tatmadaw', 'arakan army', 'rakhine', 'kachin', 'shan state', 'people\'s defence force', 'naypyidaw', 'mandalay'],
    actors: [
      { id: 'junta', name: 'Military junta', aliases: ['junta', 'military', 'tatmadaw', 'regime forces'], colour: '#c62828' },
      { id: 'resistance', name: 'Resistance forces', aliases: ['resistance', 'pdf', 'people\'s defence force', 'arakan army', 'kachin independence army', 'kia', 'tnla', 'mndaa'], colour: '#2e7d32' },
    ],
  },
  {
    id: 'drc', name: 'DR Congo (east)', center: [-1.5, 29.0], zoom: 7,
    keywords: ['m23', 'congo', 'drc', 'goma', 'bukavu', 'uvira', 'north kivu', 'south kivu', 'fardc', 'afc/m23', 'ituri'],
    actors: [
      { id: 'm23', name: 'M23 / AFC', aliases: ['m23', 'afc', 'congo river alliance', 'rebels'], colour: '#ef6c00' },
      { id: 'fardc', name: 'Congolese army', aliases: ['fardc', 'congolese army', 'government forces', 'wazalendo'], colour: '#1565c0' },
    ],
  },
  {
    id: 'sahel', name: 'Sahel (Mali, Burkina Faso, Niger)', center: [14.5, -2.0], zoom: 5,
    keywords: ['mali', 'burkina faso', 'niger', 'jnim', 'sahel', 'bamako', 'ouagadougou', 'niamey', 'islamic state sahel', 'wagner', 'africa corps'],
    actors: [
      { id: 'jnim', name: 'JNIM', aliases: ['jnim', 'al-qaeda affiliate', 'jihadists'], colour: '#424242' },
      { id: 'govt', name: 'Juntas & allies', aliases: ['army', 'government forces', 'africa corps', 'wagner'], colour: '#1565c0' },
    ],
  },
  {
    id: 'somalia', name: 'Somalia', center: [3.5, 45.5], zoom: 6,
    keywords: ['somalia', 'al-shabaab', 'al shabaab', 'mogadishu', 'kismayo', 'puntland', 'jubaland'],
    actors: [
      { id: 'shabaab', name: 'al-Shabaab', aliases: ['al-shabaab', 'al shabaab', 'shabaab'], colour: '#424242' },
      { id: 'govt', name: 'Somali government', aliases: ['somali army', 'government forces', 'snaf'], colour: '#1565c0' },
    ],
  },
  {
    id: 'afpak', name: 'Afghanistan–Pakistan', center: [33.0, 70.0], zoom: 6,
    keywords: ['durand line', 'ttp', 'tehrik-i-taliban', 'pakistani taliban', 'khyber pakhtunkhwa', 'waziristan', 'bajaur', 'kunar', 'khost', 'paktika', 'nangarhar', 'balochistan', 'baloch liberation army', 'bla', 'quetta', 'peshawar', 'isis-k', 'islamic state khorasan'],
    actors: [
      { id: 'pakistan', name: 'Pakistan', aliases: ['pakistan army', 'pakistani forces', 'pakistani military', 'islamabad'], colour: '#2e7d32' },
      { id: 'taliban', name: 'Afghan Taliban', aliases: ['taliban', 'afghan forces', 'islamic emirate'], colour: '#424242' },
      { id: 'ttp', name: 'TTP', aliases: ['ttp', 'pakistani taliban', 'tehrik-i-taliban pakistan'], colour: '#6d4c41' },
      { id: 'bla', name: 'Baloch Liberation Army', aliases: ['bla', 'baloch liberation army', 'baloch separatists'], colour: '#ef6c00' },
    ],
  },
  {
    id: 'ethiopia', name: 'Ethiopia', center: [12.5, 38.5], zoom: 6,
    keywords: ['tigray', 'tplf', 'mekelle', 'fano', 'amhara', 'afar', 'ethiopian army', 'endf', 'eritrea'],
    actors: [
      { id: 'endf', name: 'Ethiopian army', aliases: ['ethiopian army', 'endf', 'federal forces', 'ethiopian forces'], colour: '#1565c0' },
      { id: 'tplf', name: 'TPLF', aliases: ['tplf', 'tigrayan forces', 'tigray defence forces'], colour: '#c62828' },
      { id: 'fano', name: 'Fano', aliases: ['fano', 'amhara militia'], colour: '#6a1b9a' },
    ],
  },
  {
    id: 'lakechad', name: 'Lake Chad (ISWAP / Boko Haram)', center: [12.5, 13.5], zoom: 6,
    keywords: ['iswap', 'boko haram', 'borno', 'maiduguri', 'lake chad', 'islamic state west africa'],
    actors: [
      { id: 'iswap', name: 'ISWAP', aliases: ['iswap', 'islamic state west africa'], colour: '#424242' },
      { id: 'bokoharam', name: 'Boko Haram (JAS)', aliases: ['boko haram', 'jas'], colour: '#6d4c41' },
      { id: 'nigeria', name: 'Nigerian army', aliases: ['nigerian army', 'nigerian troops', 'mnjtf'], colour: '#2e7d32' },
    ],
  },
  {
    id: 'iran', name: 'Iran war', center: [32.0, 53.0], zoom: 5,
    keywords: ['iran war', 'irgc', 'hormuz', 'tehran', 'isfahan', 'bandar abbas', 'kurdish fighters', 'pjak', 'jaish al-adl', 'sistan'],
    actors: [
      { id: 'iran', name: 'Iran (IRGC)', aliases: ['irgc', 'iranian forces', 'iran'], colour: '#2e7d32' },
      { id: 'kurds', name: 'Kurdish groups', aliases: ['pjak', 'kurdish fighters', 'kurdish groups'], colour: '#f9a825' },
      { id: 'us-israel', name: 'US / Israel', aliases: ['us forces', 'israeli air force', 'us navy'], colour: '#1565c0' },
    ],
  },
];

// Incident types (same idea as War Map Live's). First match wins.
export const INCIDENT_TYPES = [
  { id: 'territorial', label: 'Territory change', words: ['captured', 'captures', 'seized', 'seizes', 'took control', 'takes control', 'taken control', 'recaptured', 'retook', 'liberated', 'overran', 'fell to', 'falls to', 'withdrew from', 'withdraws from', 'pulled out of'] },
  { id: 'drone_strike', label: 'Drone strike', words: ['drone', 'shahed', 'uav', 'fpv'] },
  { id: 'missile_attack', label: 'Missile attack', words: ['missile', 'ballistic', 'cruise missile', 'rocket'] },
  { id: 'airstrike', label: 'Airstrike', words: ['airstrike', 'air strike', 'strike', 'warplane', 'bombed', 'bombing raid'] },
  { id: 'naval', label: 'Naval incident', words: ['ship', 'tanker', 'vessel', 'navy', 'naval', 'red sea', 'black sea'] },
  { id: 'air_defense', label: 'Air defence', words: ['air defence', 'air defense', 'intercepted', 'shot down'] },
  { id: 'ground_combat', label: 'Ground combat', words: ['clashes', 'fighting', 'offensive', 'battle', 'assault', 'gunfire', 'shelling', 'artillery', 'ambush'] },
  { id: 'explosion', label: 'Explosion', words: ['explosion', 'blast', 'ied', 'car bomb', 'suicide bomb'] },
  { id: 'diplomacy', label: 'Ceasefire & talks', words: ['ceasefire', 'truce', 'peace talks', 'negotiations', 'peace deal', 'agreement'] },
  { id: 'humanitarian', label: 'Humanitarian', words: ['famine', 'aid', 'displaced', 'refugees', 'cholera', 'humanitarian'] },
];

// Wording that suggests a change of control. Only stories that match go to
// the (paid) AI claim extractor, which keeps cost low.
export const CAPTURE_RE = /\b(captur(e|ed|es|ing)|seiz(e|ed|es|ing)|took control|take[sn]? control|taking control|retak(e|en|es|ing)|retook|recaptur\w*|liberat\w*|overr(a|u)n|fell to|falls? to|withdr(ew|aw|awn|aws)|pull(ed|s)? out of|entered|advanc(e|ed|es|ing) (in|on|into|toward)|encircl\w*|control of)\b/i;
