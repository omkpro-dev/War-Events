"""Native spellings for names the elections data was first written without accents.

The model copies the spelling already in elections.json, so "Pedro Sanchez" stayed unaccented on every refresh.
Only display text is touched (names, leaders, winners, notes, stakes). Never `short` or `id`: poll history and
trends are keyed by them. Matching is whole-phrase, so a name that is already correct is left alone.
Add names freely: "plain spelling": "native spelling".
"""
import re

SPELLING = {
    # Spain, Portugal, Latin America
    "Pedro Sanchez": "Pedro Sánchez", "Alberto Nunez Feijoo": "Alberto Núñez Feijóo",
    "Luiz Inacio Lula da Silva": "Luiz Inácio Lula da Silva", "Flavio Bolsonaro": "Flávio Bolsonaro",
    "Tarcisio de Freitas": "Tarcísio de Freitas", "Ratinho Junior": "Ratinho Júnior", "Missao": "Missão",
    "Jorge Maynez": "Jorge Máynez", "Karen Castrejon Trujillo": "Karen Castrejón Trujillo",
    "Ivan Cepeda": "Iván Cepeda", "Vicky Davila": "Vicky Dávila", "Rafael Lopez Aliaga": "Rafael López Aliaga",
    "Jose Antonio Kast": "José Antonio Kast", "Luisa Gonzalez": "Luisa González", "Laura Fernandez": "Laura Fernández",
    "Sao Paulo": "São Paulo", "Bogota": "Bogotá", "Brasilia": "Brasília",
    # France, Switzerland
    "Jean-Luc Melenchon": "Jean-Luc Mélenchon", "Edouard Philippe": "Édouard Philippe",
    "Raphael Glucksmann": "Raphaël Glucksmann", "Cedric Wermuth": "Cédric Wermuth",
    "Jurg Grossen": "Jürg Grossen", "Benjamin Muhlemann": "Benjamin Mühlemann",
    # Nordics
    "Jimmie Akesson": "Jimmie Åkesson", "Kristrun Frostadottir": "Kristrún Frostadóttir",
    # Poland
    "Jaroslaw Kaczynski": "Jarosław Kaczyński", "Slawomir Mentzen": "Sławomir Mentzen",
    "Wlodzimierz Czarzasty": "Włodzimierz Czarzasty", "Rafal Trzaskowski": "Rafał Trzaskowski",
    "Szymon Holownia": "Szymon Hołownia",
    # Czechia, Slovakia, Hungary
    "Andrej Babis": "Andrej Babiš", "Michal Simecka": "Michal Šimečka", "Igor Matovic": "Igor Matovič",
    "Milan Uhrik": "Milan Uhrík", "Matus Sutaj Estok": "Matúš Šutaj Eštok", "Branislav Grohling": "Branislav Gröhling",
    "Viktor Orban": "Viktor Orbán", "Peter Magyar": "Péter Magyar",
    # Baltics
    "Ainars Slesers": "Ainārs Šlesers", "Arvils Aseradens": "Arvils Ašeradens",
    # Balkans
    "Aleksandar Vucic": "Aleksandar Vučić", "Ivica Dacic": "Ivica Dačić", "Marinika Tepic": "Marinika Tepić",
    "Zdravko Ponos": "Zdravko Ponoš", "Aleksa Becic": "Aleksa Bečić", "Milojko Spajic": "Milojko Spajić",
    "Andrija Mandic": "Andrija Mandić", "Danijel Zivkovic": "Danijel Živković", "Ervin Ibrahimovic": "Ervin Ibrahimović",
    "Bakir Izetbegovic": "Bakir Izetbegović", "Dragan Covic": "Dragan Čović", "Nermin Niksic": "Nermin Nikšić",
    "Denis Becirovic": "Denis Bećirović", "Zeljka Cvijanovic": "Željka Cvijanović", "Natasa Pirc Musar": "Nataša Pirc Musar",
    "Andrej Plenkovic": "Andrej Plenković", "Zoran Milanovic": "Zoran Milanović", "Nicusor Dan": "Nicușor Dan",
    # Turkey
    "Recep Tayyip Erdogan": "Recep Tayyip Erdoğan", "Ozgur Ozel": "Özgür Özel", "Ekrem Imamoglu": "Ekrem İmamoğlu",
}

_RX = re.compile(r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted(SPELLING, key=len, reverse=True)) + r")(?!\w)")
TEXT_FIELDS = ("dateNote", "stakes", "winner")
CONTENDER_FIELDS = ("name", "leader")


def spell(text):
    if not isinstance(text, str) or not text:
        return text
    return _RX.sub(lambda m: SPELLING[m.group(1)], text)


def spell_entry(e):
    """Fix spellings in one election entry, in place. `short`, `id`, `code` and sources are never touched."""
    for k in TEXT_FIELDS:
        if e.get(k):
            e[k] = spell(e[k])
    for c in e.get("contenders") or []:
        for k in CONTENDER_FIELDS:
            if c.get(k):
                c[k] = spell(c[k])
    return e
