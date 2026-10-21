"""Places the news fetcher can pin a story to.

Countries pin to their capital. A city, waterway or region named in a headline
beats the country it sits in ("Russian drones hit Kharkiv" -> KHARKIV, UKRAINE),
and the United States ranks lowest so "US sanctions Iran" lands in Iran.
Add places freely: (alias text is matched case-sensitively, whole words only).
"""
import re

EU, AS, ME, AF, SA, NA, OC = "EUROPE", "ASIA", "MIDDLE EAST", "AFRICA", "SOUTH AMERICA", "NORTH AMERICA", "OCEANIA"

# (COUNTRY LABEL, region, [aliases], [(city, lat, lon[, [aliases]]), ...])  first city = capital
COUNTRIES = [
    # Europe
    ("UKRAINE", EU, ["Ukraine", "Ukrainian", "Ukrainians"], [("Kyiv", 50.45, 30.52, ["Kiev"]), ("Kharkiv", 49.99, 36.23), ("Odesa", 46.48, 30.72, ["Odessa"]), ("Zaporizhzhia", 47.84, 35.14), ("Dnipro", 48.46, 35.05), ("Kherson", 46.64, 32.61), ("Lviv", 49.84, 24.03), ("Donetsk", 48.02, 37.80), ("Luhansk", 48.57, 39.31), ("Pokrovsk", 48.28, 37.18)]),
    ("RUSSIA", EU, ["Russia", "Russian", "Russians", "Kremlin"], [("Moscow", 55.76, 37.62), ("St Petersburg", 59.93, 30.34, ["St. Petersburg", "Saint Petersburg"]), ("Kursk", 51.73, 36.19), ("Belgorod", 50.60, 36.59), ("Kaliningrad", 54.71, 20.51)]),
    ("BELARUS", EU, ["Belarus", "Belarusian"], [("Minsk", 53.90, 27.56)]),
    ("POLAND", EU, ["Poland"], [("Warsaw", 52.23, 21.01)]),
    ("GERMANY", EU, ["Germany", "German", "Germans"], [("Berlin", 52.52, 13.40)]),
    ("FRANCE", EU, ["France", "French"], [("Paris", 48.86, 2.35)]),
    ("UNITED KINGDOM", EU, ["United Kingdom", "UK", "Britain", "British", "Downing Street"], [("London", 51.51, -0.13)]),
    ("IRELAND", EU, ["Ireland", "Irish"], [("Dublin", 53.35, -6.26)]),
    ("ITALY", EU, ["Italy", "Italian"], [("Rome", 41.90, 12.50)]),
    ("SPAIN", EU, ["Spain", "Spanish"], [("Madrid", 40.42, -3.70)]),
    ("PORTUGAL", EU, ["Portugal", "Portuguese"], [("Lisbon", 38.72, -9.14)]),
    ("NETHERLANDS", EU, ["Netherlands", "Dutch"], [("Amsterdam", 52.37, 4.90), ("The Hague", 52.08, 4.30)]),
    ("BELGIUM", EU, ["Belgium", "Belgian"], [("Brussels", 50.85, 4.35)]),
    ("SWITZERLAND", EU, ["Switzerland", "Swiss"], [("Bern", 46.95, 7.45), ("Geneva", 46.20, 6.14), ("Davos", 46.80, 9.84)]),
    ("AUSTRIA", EU, ["Austria", "Austrian"], [("Vienna", 48.21, 16.37)]),
    ("CZECHIA", EU, ["Czech Republic", "Czechia", "Czech"], [("Prague", 50.08, 14.44)]),
    ("SLOVAKIA", EU, ["Slovakia", "Slovak"], [("Bratislava", 48.15, 17.11)]),
    ("HUNGARY", EU, ["Hungary", "Hungarian"], [("Budapest", 47.50, 19.04)]),
    ("ROMANIA", EU, ["Romania", "Romanian"], [("Bucharest", 44.43, 26.10)]),
    ("MOLDOVA", EU, ["Moldova", "Moldovan", "Transnistria"], [("Chisinau", 47.01, 28.86)]),
    ("BULGARIA", EU, ["Bulgaria", "Bulgarian"], [("Sofia", 42.70, 23.32)]),
    ("SERBIA", EU, ["Serbia", "Serbian"], [("Belgrade", 44.79, 20.45)]),
    ("KOSOVO", EU, ["Kosovo"], [("Pristina", 42.66, 21.17)]),
    ("BOSNIA", EU, ["Bosnia", "Bosnian", "Republika Srpska"], [("Sarajevo", 43.86, 18.41)]),
    ("GREECE", EU, ["Greece", "Greek"], [("Athens", 37.98, 23.73)]),
    ("CYPRUS", EU, ["Cyprus", "Cypriot"], [("Nicosia", 35.19, 33.38)]),
    ("TURKEY", EU, ["Turkey", "Turkish", "Türkiye", "Turkiye"], [("Ankara", 39.93, 32.86), ("Istanbul", 41.01, 28.98)]),
    ("GEORGIA", EU, [], [("Tbilisi", 41.72, 44.79)]),
    ("ARMENIA", EU, ["Armenia", "Armenian"], [("Yerevan", 40.18, 44.51)]),
    ("AZERBAIJAN", EU, ["Azerbaijan", "Azerbaijani"], [("Baku", 40.41, 49.87)]),
    ("SWEDEN", EU, ["Sweden", "Swedish"], [("Stockholm", 59.33, 18.07)]),
    ("FINLAND", EU, ["Finland", "Finnish"], [("Helsinki", 60.17, 24.94)]),
    ("NORWAY", EU, ["Norway", "Norwegian"], [("Oslo", 59.91, 10.75)]),
    ("DENMARK", EU, ["Denmark", "Danish"], [("Copenhagen", 55.68, 12.57)]),
    ("ESTONIA", EU, ["Estonia", "Estonian"], [("Tallinn", 59.44, 24.75)]),
    ("LATVIA", EU, ["Latvia", "Latvian"], [("Riga", 56.95, 24.11)]),
    ("LITHUANIA", EU, ["Lithuania", "Lithuanian"], [("Vilnius", 54.69, 25.28)]),
    # Middle East
    ("ISRAEL", ME, ["Israel", "Israeli", "Israelis", "IDF"], [("Jerusalem", 31.78, 35.22), ("Tel Aviv", 32.09, 34.78), ("Haifa", 32.79, 34.99)]),
    ("LEBANON", ME, ["Lebanon", "Lebanese", "Hezbollah"], [("Beirut", 33.89, 35.50)]),
    ("SYRIA", ME, ["Syria", "Syrian"], [("Damascus", 33.51, 36.29), ("Aleppo", 36.20, 37.13), ("Idlib", 35.93, 36.63)]),
    ("JORDAN", ME, ["Jordan", "Jordanian"], [("Amman", 31.95, 35.93)]),
    ("IRAQ", ME, ["Iraq", "Iraqi"], [("Baghdad", 33.31, 44.36), ("Erbil", 36.19, 44.01), ("Basra", 30.51, 47.81)]),
    ("IRAN", ME, ["Iran", "Iranian", "Iranians", "Tehran's"], [("Tehran", 35.69, 51.39), ("Isfahan", 32.65, 51.67), ("Natanz", 33.72, 51.73), ("Fordow", 34.88, 50.99)]),
    ("SAUDI ARABIA", ME, ["Saudi Arabia", "Saudi"], [("Riyadh", 24.71, 46.68), ("Jeddah", 21.49, 39.19)]),
    ("UNITED ARAB EMIRATES", ME, ["United Arab Emirates", "UAE", "Emirati"], [("Abu Dhabi", 24.45, 54.38), ("Dubai", 25.20, 55.27)]),
    ("QATAR", ME, ["Qatar", "Qatari"], [("Doha", 25.29, 51.53)]),
    ("KUWAIT", ME, ["Kuwait", "Kuwaiti"], [("Kuwait City", 29.38, 47.99)]),
    ("BAHRAIN", ME, ["Bahrain", "Bahraini"], [("Manama", 26.23, 50.59)]),
    ("OMAN", ME, ["Oman", "Omani"], [("Muscat", 23.59, 58.41)]),
    ("YEMEN", ME, ["Yemen", "Yemeni", "Houthi", "Houthis"], [("Sanaa", 15.37, 44.19, ["Sana'a"]), ("Aden", 12.79, 45.04), ("Hodeidah", 14.80, 42.95)]),
    ("EGYPT", ME, ["Egypt", "Egyptian"], [("Cairo", 30.04, 31.24)]),
    # Asia
    ("CHINA", AS, ["China", "Chinese"], [("Beijing", 39.90, 116.41), ("Shanghai", 31.23, 121.47), ("Hong Kong", 22.32, 114.17), ("Xinjiang", 41.75, 86.15)]),
    ("TAIWAN", AS, ["Taiwan", "Taiwanese"], [("Taipei", 25.03, 121.56), ("Kinmen", 24.45, 118.38)]),
    ("JAPAN", AS, ["Japan", "Japanese"], [("Tokyo", 35.68, 139.69), ("Okinawa", 26.21, 127.68)]),
    ("SOUTH KOREA", AS, ["South Korea", "South Korean", "South Koreans"], [("Seoul", 37.57, 126.98)]),
    ("NORTH KOREA", AS, ["North Korea", "North Korean", "North Koreans"], [("Pyongyang", 39.04, 125.76)]),
    ("MONGOLIA", AS, ["Mongolia", "Mongolian"], [("Ulaanbaatar", 47.89, 106.91)]),
    ("INDIA", AS, ["India", "Indian"], [("New Delhi", 28.61, 77.21, ["Delhi"]), ("Mumbai", 19.08, 72.88)]),
    ("PAKISTAN", AS, ["Pakistan", "Pakistani"], [("Islamabad", 33.68, 73.05), ("Karachi", 24.86, 67.01), ("Lahore", 31.55, 74.34)]),
    ("AFGHANISTAN", AS, ["Afghanistan", "Afghan", "Taliban"], [("Kabul", 34.56, 69.21)]),
    ("BANGLADESH", AS, ["Bangladesh", "Bangladeshi"], [("Dhaka", 23.81, 90.41)]),
    ("SRI LANKA", AS, ["Sri Lanka", "Sri Lankan"], [("Colombo", 6.93, 79.86)]),
    ("NEPAL", AS, ["Nepal", "Nepali", "Nepalese"], [("Kathmandu", 27.72, 85.32)]),
    ("MYANMAR", AS, ["Myanmar", "Burma", "Burmese"], [("Naypyidaw", 19.76, 96.08), ("Yangon", 16.84, 96.17)]),
    ("THAILAND", AS, ["Thailand", "Thai"], [("Bangkok", 13.76, 100.50)]),
    ("CAMBODIA", AS, ["Cambodia", "Cambodian"], [("Phnom Penh", 11.56, 104.92)]),
    ("VIETNAM", AS, ["Vietnam", "Vietnamese", "Viet Nam"], [("Hanoi", 21.03, 105.85)]),
    ("PHILIPPINES", AS, ["Philippines", "Philippine", "Filipino"], [("Manila", 14.60, 120.98)]),
    ("MALAYSIA", AS, ["Malaysia", "Malaysian"], [("Kuala Lumpur", 3.14, 101.69)]),
    ("SINGAPORE", AS, ["Singapore", "Singaporean"], [("Singapore City", 1.35, 103.82)]),
    ("INDONESIA", AS, ["Indonesia", "Indonesian"], [("Jakarta", -6.20, 106.85)]),
    ("KAZAKHSTAN", AS, ["Kazakhstan", "Kazakh"], [("Astana", 51.17, 71.45)]),
    ("UZBEKISTAN", AS, ["Uzbekistan", "Uzbek"], [("Tashkent", 41.30, 69.24)]),
    # Africa
    ("SUDAN", AF, ["Sudan", "Sudanese"], [("Khartoum", 15.50, 32.56), ("El Fasher", 13.63, 25.35, ["El-Fasher"]), ("Darfur", 13.50, 24.00)]),
    ("SOUTH SUDAN", AF, ["South Sudan", "South Sudanese"], [("Juba", 4.85, 31.58)]),
    ("ETHIOPIA", AF, ["Ethiopia", "Ethiopian"], [("Addis Ababa", 9.03, 38.74), ("Tigray", 13.50, 39.47)]),
    ("ERITREA", AF, ["Eritrea", "Eritrean"], [("Asmara", 15.32, 38.93)]),
    ("SOMALIA", AF, ["Somalia", "Somali", "al-Shabaab", "Al-Shabaab"], [("Mogadishu", 2.05, 45.32)]),
    ("KENYA", AF, ["Kenya", "Kenyan"], [("Nairobi", -1.29, 36.82)]),
    ("UGANDA", AF, ["Uganda", "Ugandan"], [("Kampala", 0.35, 32.58)]),
    ("RWANDA", AF, ["Rwanda", "Rwandan"], [("Kigali", -1.94, 30.06)]),
    ("DR CONGO", AF, ["Democratic Republic of Congo", "Democratic Republic of the Congo", "DR Congo", "DRC", "Congo", "Congolese", "M23"], [("Kinshasa", -4.32, 15.31), ("Goma", -1.68, 29.22)]),
    ("NIGERIA", AF, ["Nigeria", "Nigerian"], [("Abuja", 9.08, 7.40), ("Lagos", 6.52, 3.38)]),
    ("NIGER", AF, ["Niger"], [("Niamey", 13.51, 2.11)]),
    ("MALI", AF, ["Mali", "Malian"], [("Bamako", 12.64, -8.00)]),
    ("BURKINA FASO", AF, ["Burkina Faso", "Burkinabe"], [("Ouagadougou", 12.37, -1.52)]),
    ("CHAD", AF, ["Chad", "Chadian"], [("N'Djamena", 12.13, 15.06)]),
    ("CAMEROON", AF, ["Cameroon", "Cameroonian"], [("Yaounde", 3.85, 11.50, ["Yaoundé"])]),
    ("GHANA", AF, ["Ghana", "Ghanaian"], [("Accra", 5.60, -0.19)]),
    ("SENEGAL", AF, ["Senegal", "Senegalese"], [("Dakar", 14.72, -17.47)]),
    ("LIBYA", AF, ["Libya", "Libyan"], [("Tripoli", 32.89, 13.19), ("Benghazi", 32.12, 20.07)]),
    ("TUNISIA", AF, ["Tunisia", "Tunisian"], [("Tunis", 36.81, 10.18)]),
    ("ALGERIA", AF, ["Algeria", "Algerian"], [("Algiers", 36.75, 3.06)]),
    ("MOROCCO", AF, ["Morocco", "Moroccan"], [("Rabat", 34.02, -6.84)]),
    ("MOZAMBIQUE", AF, ["Mozambique", "Mozambican"], [("Maputo", -25.97, 32.57)]),
    ("ZIMBABWE", AF, ["Zimbabwe", "Zimbabwean"], [("Harare", -17.83, 31.05)]),
    ("SOUTH AFRICA", AF, ["South Africa", "South African"], [("Pretoria", -25.75, 28.19), ("Johannesburg", -26.20, 28.05), ("Cape Town", -33.92, 18.42)]),
    # Americas
    ("UNITED STATES", NA, ["United States", "US", "U.S.", "USA", "White House", "Pentagon"], [("Washington", 38.90, -77.04), ("New York", 40.71, -74.01)]),
    ("CANADA", NA, ["Canada", "Canadian"], [("Ottawa", 45.42, -75.70)]),
    ("MEXICO", NA, ["Mexico", "Mexican"], [("Mexico City", 19.43, -99.13)]),
    ("CUBA", NA, ["Cuba", "Cuban"], [("Havana", 23.11, -82.37)]),
    ("HAITI", NA, ["Haiti", "Haitian"], [("Port-au-Prince", 18.54, -72.34)]),
    ("PANAMA", NA, ["Panama", "Panamanian"], [("Panama City", 8.98, -79.52)]),
    ("GREENLAND", NA, ["Greenland"], [("Nuuk", 64.18, -51.69)]),
    ("VENEZUELA", SA, ["Venezuela", "Venezuelan"], [("Caracas", 10.49, -66.88)]),
    ("COLOMBIA", SA, ["Colombia", "Colombian"], [("Bogota", 4.71, -74.07, ["Bogotá"])]),
    ("ECUADOR", SA, ["Ecuador", "Ecuadorian"], [("Quito", -0.18, -78.47)]),
    ("PERU", SA, ["Peru", "Peruvian"], [("Lima", -12.05, -77.04)]),
    ("BOLIVIA", SA, ["Bolivia", "Bolivian"], [("La Paz", -16.49, -68.12)]),
    ("BRAZIL", SA, ["Brazil", "Brazilian"], [("Brasilia", -15.79, -47.88, ["Brasília"]), ("Sao Paulo", -23.55, -46.63, ["São Paulo"]), ("Rio de Janeiro", -22.91, -43.17)]),
    ("CHILE", SA, ["Chile", "Chilean"], [("Santiago", -33.45, -70.67)]),
    ("ARGENTINA", SA, ["Argentina", "Argentine", "Argentinian"], [("Buenos Aires", -34.60, -58.38)]),
    # Oceania
    ("AUSTRALIA", OC, ["Australia", "Australian"], [("Canberra", -35.28, 149.13), ("Sydney", -33.87, 151.21)]),
    ("NEW ZEALAND", OC, ["New Zealand"], [("Wellington", -41.29, 174.78)]),
    ("PAPUA NEW GUINEA", OC, ["Papua New Guinea"], [("Port Moresby", -9.44, 147.18)]),
    ("SOLOMON ISLANDS", OC, ["Solomon Islands"], [("Honiara", -9.43, 159.95)]),
    ("FIJI", OC, ["Fiji", "Fijian"], [("Suva", -18.14, 178.44)]),
]

# Waterways, contested regions and blocs: (LABEL, region, lat, lon, specificity, [aliases])
SPOTS = [
    ("STRAIT OF HORMUZ", ME, 26.57, 56.25, 3, ["Strait of Hormuz", "Hormuz"]),
    ("RED SEA", ME, 20.00, 38.50, 3, ["Red Sea"]),
    ("BAB EL-MANDEB", ME, 12.58, 43.33, 3, ["Bab el-Mandeb", "Bab al-Mandab"]),
    ("SUEZ CANAL", ME, 30.58, 32.27, 3, ["Suez Canal", "Suez"]),
    ("PERSIAN GULF", ME, 27.00, 51.00, 3, ["Persian Gulf", "Gulf of Oman"]),
    ("GAZA", ME, 31.50, 34.47, 2, ["Gaza", "Gaza Strip", "Gazan", "Gazans", "Hamas", "Rafah", "Khan Younis"]),
    ("WEST BANK", ME, 31.95, 35.30, 2, ["West Bank", "Ramallah", "Jenin", "Palestinian Authority"]),
    ("GOLAN HEIGHTS", ME, 33.00, 35.75, 3, ["Golan Heights", "Golan"]),
    ("TAIWAN STRAIT", AS, 24.50, 119.50, 3, ["Taiwan Strait"]),
    ("SOUTH CHINA SEA", AS, 12.00, 114.00, 3, ["South China Sea", "Spratly Islands", "Spratlys", "Scarborough Shoal", "Second Thomas Shoal"]),
    ("EAST CHINA SEA", AS, 28.00, 125.00, 3, ["East China Sea", "Senkaku Islands", "Senkakus"]),
    ("STRAIT OF MALACCA", AS, 2.50, 101.00, 3, ["Strait of Malacca", "Malacca Strait"]),
    ("KASHMIR", AS, 34.08, 74.80, 3, ["Kashmir", "Line of Control"]),
    ("INDIAN OCEAN", AS, -10.00, 75.00, 3, ["Indian Ocean"]),
    ("BLACK SEA", EU, 43.40, 34.00, 3, ["Black Sea"]),
    ("BALTIC SEA", EU, 58.00, 20.00, 3, ["Baltic Sea"]),
    ("CRIMEA", EU, 44.95, 34.10, 3, ["Crimea", "Crimean", "Sevastopol"]),
    ("DONBAS", EU, 48.00, 38.00, 2, ["Donbas", "Donbass"]),
    ("NAGORNO-KARABAKH", EU, 39.82, 46.75, 3, ["Nagorno-Karabakh", "Karabakh"]),
    ("ARCTIC", EU, 78.00, 15.00, 2, ["Arctic"]),
    ("SAHEL", AF, 15.00, 0.00, 2, ["Sahel"]),
    ("HORN OF AFRICA", AF, 8.00, 46.00, 2, ["Horn of Africa"]),
    ("PANAMA CANAL", NA, 9.08, -79.68, 3, ["Panama Canal"]),
    ("EUROPEAN UNION", EU, 50.84, 4.38, 1, ["European Union", "EU", "European Commission", "Brussels'"]),
]

PLACES = {}
_ALIASES = []


def _add(label, cat, lat, lon, spec, aliases):
    PLACES[label] = {"label": label, "cat": cat, "lat": lat, "lon": lon, "spec": spec}
    for a in aliases:
        _ALIASES.append((a, label))


for _name, _cat, _aliases, _cities in COUNTRIES:
    _low = _name == "UNITED STATES"
    _cap = _cities[0]
    _add(_name, _cat, _cap[1], _cap[2], 0 if _low else 1, _aliases)
    for _c in _cities:
        _add(f"{_c[0].upper()}, {_name}", _cat, _c[1], _c[2], 0 if _low else 2, [_c[0]] + (_c[3] if len(_c) > 3 else []))
for _label, _cat, _lat, _lon, _spec, _aliases in SPOTS:
    _add(_label, _cat, _lat, _lon, _spec, _aliases)

_ALIASES.sort(key=lambda x: -len(x[0]))
_RX = [(re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)"), label) for a, label in _ALIASES]


def locate(text):
    """Best place named in text: most specific wins, then earliest mention."""
    if not text:
        return None
    taken, best = [], None
    for rx, label in _RX:
        for m in rx.finditer(text):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken):
                continue
            taken.append((s, e))
            p = PLACES[label]
            key = (p["spec"], -s)
            if best is None or key > best[0]:
                best = (key, p)
    return best[1] if best else None
