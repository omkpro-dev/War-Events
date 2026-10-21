// Small gazetteer: places that come up often in war reporting, with their
// common spellings. The tagger pins a story to the first place it finds
// (title first, then summary). Add places as they appear in the news.
// Coordinates are city centres (approximate, WGS84 lat/lng).
//
// For the Active Wars control map you'll replace this with district
// polygons (geoBoundaries ADM2); keep the alias lists, they carry over.

export const PLACES = [
  // Afghanistan–Pakistan, Ethiopia, Lake Chad
  { conflict: 'afpak', name: 'Kabul', aliases: ['kabul'], lat: 34.5553, lng: 69.2075, kind: 'city' },
  { conflict: 'afpak', name: 'Khost', aliases: ['khost'], lat: 33.3395, lng: 69.9204, kind: 'city' },
  { conflict: 'afpak', name: 'Kunar', aliases: ['kunar', 'asadabad'], lat: 34.8730, lng: 71.1469, kind: 'city' },
  { conflict: 'afpak', name: 'Jalalabad', aliases: ['jalalabad', 'nangarhar'], lat: 34.4265, lng: 70.4515, kind: 'city' },
  { conflict: 'afpak', name: 'Peshawar', aliases: ['peshawar'], lat: 34.0151, lng: 71.5249, kind: 'city' },
  { conflict: 'afpak', name: 'Quetta', aliases: ['quetta'], lat: 30.1798, lng: 66.9750, kind: 'city' },
  { conflict: 'afpak', name: 'North Waziristan', aliases: ['north waziristan', 'miranshah', 'miran shah'], lat: 33.0, lng: 70.07, kind: 'city' },
  { conflict: 'afpak', name: 'South Waziristan', aliases: ['south waziristan', 'wana'], lat: 32.30, lng: 69.57, kind: 'city' },
  { conflict: 'afpak', name: 'Bajaur', aliases: ['bajaur'], lat: 34.78, lng: 71.52, kind: 'city' },
  { conflict: 'afpak', name: 'Torkham', aliases: ['torkham'], lat: 34.11, lng: 71.09, kind: 'city' },
  { conflict: 'afpak', name: 'Chaman', aliases: ['chaman', 'spin boldak'], lat: 30.92, lng: 66.45, kind: 'city' },
  { conflict: 'ethiopia', name: 'Mekelle', aliases: ['mekelle', 'mekele'], lat: 13.4967, lng: 39.4753, kind: 'city' },
  { conflict: 'ethiopia', name: 'Addis Ababa', aliases: ['addis ababa'], lat: 9.0300, lng: 38.7400, kind: 'city' },
  { conflict: 'ethiopia', name: 'Bahir Dar', aliases: ['bahir dar'], lat: 11.5936, lng: 37.3908, kind: 'city' },
  { conflict: 'ethiopia', name: 'Gondar', aliases: ['gondar', 'gonder'], lat: 12.6030, lng: 37.4521, kind: 'city' },
  { conflict: 'ethiopia', name: 'Adigrat', aliases: ['adigrat'], lat: 14.2770, lng: 39.4620, kind: 'city' },
  { conflict: 'lakechad', name: 'Maiduguri', aliases: ['maiduguri'], lat: 11.8333, lng: 13.1500, kind: 'city' },
  { conflict: 'lakechad', name: 'Monguno', aliases: ['monguno'], lat: 12.6700, lng: 13.6100, kind: 'city' },
  { conflict: 'lakechad', name: 'Baga', aliases: ['baga'], lat: 13.1100, lng: 13.8300, kind: 'city' },
  { conflict: 'lakechad', name: 'Diffa', aliases: ['diffa'], lat: 13.3150, lng: 12.6110, kind: 'city' },

  // Yemen
  { conflict: 'yemen', name: 'Sanaa', aliases: ['sanaa', "sana'a", 'sana’a'], lat: 15.3694, lng: 44.191, kind: 'city' },
  { conflict: 'yemen', name: 'Aden', aliases: ['aden'], lat: 12.7855, lng: 45.0187, kind: 'city' },
  { conflict: 'yemen', name: 'Taiz', aliases: ['taiz', "ta'izz", 'ta’izz', 'taizz', 'taez'], lat: 13.5795, lng: 44.0209, kind: 'city' },
  { conflict: 'yemen', name: 'Hodeidah', aliases: ['hodeidah', 'hudaydah', 'hodeida', 'al-hudaydah'], lat: 14.7978, lng: 42.9545, kind: 'city' },
  { conflict: 'yemen', name: 'Marib', aliases: ['marib', "ma'rib", 'ma’rib'], lat: 15.4543, lng: 45.3264, kind: 'city' },
  { conflict: 'yemen', name: 'Saada', aliases: ['saada', "sa'dah", 'sadah', 'saada province'], lat: 16.9402, lng: 43.7639, kind: 'city' },
  { conflict: 'yemen', name: 'Al Bayda', aliases: ['al bayda', 'al-bayda', 'bayda'], lat: 13.9853, lng: 45.5728, kind: 'city' },
  { conflict: 'yemen', name: 'Mokha', aliases: ['mokha', 'mocha', 'al-mukha'], lat: 13.3196, lng: 43.25, kind: 'city' },
  { conflict: 'yemen', name: 'Mukalla', aliases: ['mukalla', 'al-mukalla'], lat: 14.5425, lng: 49.1242, kind: 'city' },
  { conflict: 'yemen', name: 'Ataq (Shabwa)', aliases: ['ataq', 'shabwa', 'shabwah'], lat: 14.5377, lng: 46.8319, kind: 'city' },
  { conflict: 'yemen', name: 'Al Dhale', aliases: ['dhale', "al-dhale'e", 'al dhalea', 'dhalea'], lat: 13.6957, lng: 44.7314, kind: 'city' },
  { conflict: 'yemen', name: 'Lahij', aliases: ['lahij', 'lahj'], lat: 13.0567, lng: 44.8819, kind: 'city' },
  // Places outside Yemen that Houthi attacks target
  { conflict: 'yemen', name: 'Riyadh', aliases: ['riyadh'], lat: 24.7136, lng: 46.6753, kind: 'city' },
  { conflict: 'yemen', name: 'Jizan', aliases: ['jizan', 'jazan'], lat: 16.8892, lng: 42.5511, kind: 'city' },
  { conflict: 'yemen', name: 'Eilat', aliases: ['eilat'], lat: 29.5577, lng: 34.9519, kind: 'city' },
  { conflict: 'yemen', name: 'Bab el-Mandeb', aliases: ['bab el-mandeb', 'bab al-mandab', 'bab-el-mandeb'], lat: 12.6, lng: 43.33, kind: 'sea' },

  // Sudan
  { conflict: 'sudan', name: 'Khartoum', aliases: ['khartoum'], lat: 15.5007, lng: 32.5599, kind: 'city' },
  { conflict: 'sudan', name: 'Omdurman', aliases: ['omdurman'], lat: 15.6445, lng: 32.4777, kind: 'city' },
  { conflict: 'sudan', name: 'Bahri', aliases: ['bahri', 'khartoum north'], lat: 15.641, lng: 32.532, kind: 'city' },
  { conflict: 'sudan', name: 'El Fasher', aliases: ['el fasher', 'el-fasher', 'al-fashir', 'al fashir', 'elfasher'], lat: 13.6279, lng: 25.3494, kind: 'city' },
  { conflict: 'sudan', name: 'Nyala', aliases: ['nyala'], lat: 12.0489, lng: 24.8807, kind: 'city' },
  { conflict: 'sudan', name: 'El Obeid', aliases: ['el obeid', 'el-obeid', 'al-ubayyid'], lat: 13.1843, lng: 30.2167, kind: 'city' },
  { conflict: 'sudan', name: 'Kadugli', aliases: ['kadugli'], lat: 11.0108, lng: 29.7181, kind: 'city' },
  { conflict: 'sudan', name: 'Dilling', aliases: ['dilling', 'dalang'], lat: 12.05, lng: 29.65, kind: 'city' },
  { conflict: 'sudan', name: 'Babanusa', aliases: ['babanusa'], lat: 11.333, lng: 27.8, kind: 'city' },
  { conflict: 'sudan', name: 'Port Sudan', aliases: ['port sudan'], lat: 19.6158, lng: 37.2164, kind: 'city' },
  { conflict: 'sudan', name: 'Wad Madani', aliases: ['wad madani', 'wad medani'], lat: 14.4012, lng: 33.5199, kind: 'city' },
  { conflict: 'sudan', name: 'El Geneina', aliases: ['geneina', 'el geneina', 'el-geneina'], lat: 13.4527, lng: 22.4472, kind: 'city' },

  // Russia–Ukraine
  { conflict: 'ukraine', name: 'Kyiv', aliases: ['kyiv', 'kiev'], lat: 50.4501, lng: 30.5234, kind: 'city' },
  { conflict: 'ukraine', name: 'Kharkiv', aliases: ['kharkiv', 'kharkov'], lat: 49.9935, lng: 36.2304, kind: 'city' },
  { conflict: 'ukraine', name: 'Pokrovsk', aliases: ['pokrovsk'], lat: 48.2824, lng: 37.1757, kind: 'city' },
  { conflict: 'ukraine', name: 'Myrnohrad', aliases: ['myrnohrad'], lat: 48.3022, lng: 37.2659, kind: 'city' },
  { conflict: 'ukraine', name: 'Kostiantynivka', aliases: ['kostiantynivka', 'konstantinovka'], lat: 48.5277, lng: 37.7069, kind: 'city' },
  { conflict: 'ukraine', name: 'Kramatorsk', aliases: ['kramatorsk'], lat: 48.7389, lng: 37.5848, kind: 'city' },
  { conflict: 'ukraine', name: 'Sloviansk', aliases: ['sloviansk', 'slavyansk'], lat: 48.8526, lng: 37.605, kind: 'city' },
  { conflict: 'ukraine', name: 'Lyman', aliases: ['lyman'], lat: 48.9886, lng: 37.8027, kind: 'city' },
  { conflict: 'ukraine', name: 'Kupiansk', aliases: ['kupiansk', 'kupyansk'], lat: 49.7106, lng: 37.6157, kind: 'city' },
  { conflict: 'ukraine', name: 'Huliaipole', aliases: ['huliaipole', 'hulyaipole'], lat: 47.6633, lng: 36.2564, kind: 'city' },
  { conflict: 'ukraine', name: 'Zaporizhzhia', aliases: ['zaporizhzhia', 'zaporizhia', 'zaporozhye'], lat: 47.8388, lng: 35.1396, kind: 'city' },
  { conflict: 'ukraine', name: 'Kherson', aliases: ['kherson'], lat: 46.6354, lng: 32.6169, kind: 'city' },
  { conflict: 'ukraine', name: 'Odesa', aliases: ['odesa', 'odessa'], lat: 46.4825, lng: 30.7233, kind: 'city' },
  { conflict: 'ukraine', name: 'Dnipro', aliases: ['dnipro', 'dnipropetrovsk'], lat: 48.4647, lng: 35.0462, kind: 'city' },
  { conflict: 'ukraine', name: 'Sumy', aliases: ['sumy'], lat: 50.9077, lng: 34.7981, kind: 'city' },
  { conflict: 'ukraine', name: 'Donetsk', aliases: ['donetsk city'], lat: 48.0159, lng: 37.8028, kind: 'city' },
  { conflict: 'ukraine', name: 'Lviv', aliases: ['lviv'], lat: 49.8397, lng: 24.0297, kind: 'city' },
  { conflict: 'ukraine', name: 'Lutsk (Volyn)', aliases: ['lutsk', 'volyn'], lat: 50.7472, lng: 25.3254, kind: 'city' },
  { conflict: 'ukraine', name: 'Kursk', aliases: ['kursk'], lat: 51.7304, lng: 36.1926, kind: 'city' },
  { conflict: 'ukraine', name: 'Belgorod', aliases: ['belgorod'], lat: 50.5954, lng: 36.5873, kind: 'city' },
  { conflict: 'ukraine', name: 'Sevastopol', aliases: ['sevastopol', 'crimea'], lat: 44.6166, lng: 33.5254, kind: 'city' },

  // Israel, Gaza & Lebanon
  { conflict: 'israel', name: 'Gaza City', aliases: ['gaza city'], lat: 31.5017, lng: 34.4668, kind: 'city' },
  { conflict: 'israel', name: 'Jabalia', aliases: ['jabalia', 'jabaliya'], lat: 31.5272, lng: 34.4831, kind: 'city' },
  { conflict: 'israel', name: 'Khan Younis', aliases: ['khan younis', 'khan yunis'], lat: 31.3462, lng: 34.3063, kind: 'city' },
  { conflict: 'israel', name: 'Rafah', aliases: ['rafah'], lat: 31.2969, lng: 34.2455, kind: 'city' },
  { conflict: 'israel', name: 'Deir al-Balah', aliases: ['deir al-balah', 'deir el-balah'], lat: 31.4181, lng: 34.3517, kind: 'city' },
  { conflict: 'israel', name: 'Al-Maghazi', aliases: ['maghazi', 'al-maghazi'], lat: 31.42, lng: 34.383, kind: 'city' },
  { conflict: 'israel', name: 'Jenin', aliases: ['jenin'], lat: 32.4597, lng: 35.295, kind: 'city' },
  { conflict: 'israel', name: 'Nablus', aliases: ['nablus'], lat: 32.2211, lng: 35.2544, kind: 'city' },
  { conflict: 'israel', name: 'Tulkarm', aliases: ['tulkarm', 'tulkarem'], lat: 32.3104, lng: 35.0286, kind: 'city' },
  { conflict: 'israel', name: 'Hebron', aliases: ['hebron'], lat: 31.5326, lng: 35.0998, kind: 'city' },
  { conflict: 'israel', name: 'Jerusalem', aliases: ['jerusalem'], lat: 31.7683, lng: 35.2137, kind: 'city' },
  { conflict: 'israel', name: 'Tel Aviv', aliases: ['tel aviv'], lat: 32.0853, lng: 34.7818, kind: 'city' },
  { conflict: 'israel', name: 'Beirut', aliases: ['beirut'], lat: 33.8938, lng: 35.5018, kind: 'city' },
  { conflict: 'israel', name: 'Nabatieh', aliases: ['nabatieh', 'nabatiyeh'], lat: 33.3779, lng: 35.4838, kind: 'city' },
  { conflict: 'israel', name: 'Tyre', aliases: ['tyre'], lat: 33.2705, lng: 35.2038, kind: 'city' },

  // Syria
  { conflict: 'syria', name: 'Damascus', aliases: ['damascus'], lat: 33.5138, lng: 36.2765, kind: 'city' },
  { conflict: 'syria', name: 'Aleppo', aliases: ['aleppo'], lat: 36.2021, lng: 37.1343, kind: 'city' },
  { conflict: 'syria', name: 'Idlib', aliases: ['idlib'], lat: 35.9306, lng: 36.6339, kind: 'city' },
  { conflict: 'syria', name: 'Homs', aliases: ['homs'], lat: 34.7324, lng: 36.7137, kind: 'city' },
  { conflict: 'syria', name: 'Latakia', aliases: ['latakia'], lat: 35.5317, lng: 35.7915, kind: 'city' },
  { conflict: 'syria', name: 'Sweida', aliases: ['sweida', 'suwayda', 'as-suwayda'], lat: 32.709, lng: 36.5695, kind: 'city' },
  { conflict: 'syria', name: 'Deir ez-Zor', aliases: ['deir ez-zor', 'deir ezzor', 'deir al-zor'], lat: 35.3359, lng: 40.1408, kind: 'city' },
  { conflict: 'syria', name: 'Raqqa', aliases: ['raqqa'], lat: 35.9594, lng: 39.0079, kind: 'city' },

  // Myanmar
  { conflict: 'myanmar', name: 'Naypyidaw', aliases: ['naypyidaw', 'nay pyi taw'], lat: 19.7633, lng: 96.0785, kind: 'city' },
  { conflict: 'myanmar', name: 'Mandalay', aliases: ['mandalay'], lat: 21.9588, lng: 96.0891, kind: 'city' },
  { conflict: 'myanmar', name: 'Yangon', aliases: ['yangon', 'rangoon'], lat: 16.8409, lng: 96.1735, kind: 'city' },
  { conflict: 'myanmar', name: 'Lashio', aliases: ['lashio'], lat: 22.9359, lng: 97.7498, kind: 'city' },
  { conflict: 'myanmar', name: 'Myitkyina', aliases: ['myitkyina'], lat: 25.3833, lng: 97.3964, kind: 'city' },
  { conflict: 'myanmar', name: 'Bhamo', aliases: ['bhamo'], lat: 24.2667, lng: 97.2333, kind: 'city' },
  { conflict: 'myanmar', name: 'Sittwe', aliases: ['sittwe'], lat: 20.1462, lng: 92.8983, kind: 'city' },

  // DR Congo
  { conflict: 'drc', name: 'Goma', aliases: ['goma'], lat: -1.6792, lng: 29.2228, kind: 'city' },
  { conflict: 'drc', name: 'Bukavu', aliases: ['bukavu'], lat: -2.5083, lng: 28.8608, kind: 'city' },
  { conflict: 'drc', name: 'Uvira', aliases: ['uvira'], lat: -3.3953, lng: 29.1378, kind: 'city' },
  { conflict: 'drc', name: 'Beni', aliases: ['beni'], lat: 0.4911, lng: 29.4731, kind: 'city' },
  { conflict: 'drc', name: 'Bunia', aliases: ['bunia'], lat: 1.5594, lng: 30.2522, kind: 'city' },

  // Sahel
  { conflict: 'sahel', name: 'Bamako', aliases: ['bamako'], lat: 12.6392, lng: -8.0029, kind: 'city' },
  { conflict: 'sahel', name: 'Timbuktu', aliases: ['timbuktu', 'tombouctou'], lat: 16.7666, lng: -3.0026, kind: 'city' },
  { conflict: 'sahel', name: 'Kidal', aliases: ['kidal'], lat: 18.4411, lng: 1.4078, kind: 'city' },
  { conflict: 'sahel', name: 'Ouagadougou', aliases: ['ouagadougou'], lat: 12.3714, lng: -1.5197, kind: 'city' },
  { conflict: 'sahel', name: 'Djibo', aliases: ['djibo'], lat: 14.1022, lng: -1.6306, kind: 'city' },
  { conflict: 'sahel', name: 'Niamey', aliases: ['niamey'], lat: 13.5116, lng: 2.1254, kind: 'city' },

  // Somalia
  { conflict: 'somalia', name: 'Mogadishu', aliases: ['mogadishu'], lat: 2.0469, lng: 45.3182, kind: 'city' },
  { conflict: 'somalia', name: 'Kismayo', aliases: ['kismayo', 'kismaayo'], lat: -0.3582, lng: 42.5454, kind: 'city' },
  { conflict: 'somalia', name: 'Baidoa', aliases: ['baidoa'], lat: 3.1138, lng: 43.6498, kind: 'city' },
];
