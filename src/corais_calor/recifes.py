"""Os recifes do estudo: um ponto por recife, com a coordenada de referência e a fonte dela.

A coordenada de referência é a do verbete do lugar na Wikipedia em inglês (campo de coordenadas, lido pela API
em 12/11/2026) ou, em dois casos, a do item no Wikidata. Como ela costuma cair no meio de uma ilha, a coleta
procura o ponto de grade de mar mais próximo em cada produto; os pontos efetivamente usados ficam em
`data/recifes.csv`.

`grupo` junta os recifes em seis bacias, usadas para deixar o efeito do El Niño mudar de sinal de uma região
para outra no modelo de previsão.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Recife:
    slug: str
    nome: str
    regiao: str
    grupo: str
    lat: float
    lon: float
    fonte: str


W = "Wikipedia (en)"
D = "Wikidata"

RECIFES: list[Recife] = [
    # Grande Barreira de Corais e Mar de Coral
    Recife("lizard", "Lizard Island", "Grande Barreira de Corais, norte", "Pacífico oeste", -14.669, 145.459, f"{W}: Lizard Island"),
    Recife("davies", "Davies Reef", "Grande Barreira de Corais, centro", "Pacífico oeste", -18.85, 147.65, f"{D}: Q21913661"),
    Recife("heron", "Heron Island", "Grande Barreira de Corais, sul", "Pacífico oeste", -23.442, 151.914, f"{D}: Q2719889"),
    Recife("osprey", "Osprey Reef", "Mar de Coral", "Pacífico oeste", -13.908, 146.615, f"{W}: Osprey Reef"),
    Recife("lord_howe", "Lord Howe Island", "Mar da Tasmânia (recife mais ao sul do mundo)", "Pacífico oeste", -31.554, 159.085, f"{W}: Lord Howe Island"),
    # Triângulo de Coral e Pacífico oeste
    Recife("raja_ampat", "Raja Ampat", "Triângulo de Coral, Indonésia", "Pacífico oeste", -0.233, 130.508, f"{W}: Raja Ampat Islands"),
    Recife("tubbataha", "Tubbataha", "Triângulo de Coral, Filipinas", "Pacífico oeste", 8.953, 119.868, f"{W}: Tubbataha Reef"),
    Recife("kimbe", "Kimbe Bay", "Triângulo de Coral, Papua-Nova Guiné", "Pacífico oeste", -5.167, 150.5, f"{W}: Kimbe Bay"),
    Recife("palau", "Rock Islands", "Palau", "Pacífico oeste", 7.25, 134.35, f"{W}: Rock Islands"),
    Recife("ishigaki", "Ishigaki (lagoa Sekisei)", "Japão, Ryukyu", "Pacífico oeste", 24.44, 124.22, f"{W}: Ishigaki Island"),
    Recife("fiji", "Great Astrolabe Reef", "Fiji", "Pacífico oeste", -18.862, 178.498, f"{W}: Great Astrolabe Reef"),
    # Índico
    Recife("ningaloo", "Ningaloo (Coral Bay)", "Austrália Ocidental", "Índico", -23.145, 113.776, f"{W}: Coral Bay, Western Australia"),
    Recife("scott", "Scott Reef", "Austrália Ocidental, mar aberto", "Índico", -14.05, 121.767, f"{W}: Scott and Seringapatam Reefs"),
    Recife("maldivas", "Atol de Kaafu (Malé)", "Maldivas", "Índico", 4.417, 73.5, f"{W}: Kaafu Atoll"),
    Recife("chagos", "Peros Banhos", "Arquipélago de Chagos", "Índico", -5.333, 71.85, f"{W}: Peros Banhos"),
    Recife("mafia", "Ilha de Mafia", "Leste da África, Tanzânia", "Índico", -7.85, 39.783, f"{W}: Mafia Island"),
    Recife("aldabra", "Aldabra", "Seychelles, atol remoto", "Índico", -9.417, 46.35, f"{W}: Aldabra"),
    Recife("nosy_be", "Nosy Be", "Madagascar, noroeste", "Índico", -13.315, 48.268, f"{W}: Nosy Be"),
    Recife("toliara", "Toliara", "Madagascar, sudoeste", "Índico", -23.35, 43.667, f"{W}: Toliara"),
    # Mar Vermelho e golfo Pérsico
    Recife("ras_mohammed", "Ras Mohammed", "Mar Vermelho, norte", "Mar Vermelho e golfo Pérsico", 27.769, 34.21, f"{W}: Ras Muhammad National Park"),
    Recife("farasan", "Ilhas Farasan", "Mar Vermelho, sul", "Mar Vermelho e golfo Pérsico", 16.8, 41.85, f"{W}: Farasan Islands"),
    Recife("sir_abu_nuayr", "Sir Abu Nu'ayr", "Golfo Pérsico", "Mar Vermelho e golfo Pérsico", 25.232, 54.222, f"{W}: Sir Abu Nu'ayr"),
    # Pacífico central e leste
    Recife("kaneohe", "Baía de Kāneʻohe", "Havaí", "Pacífico central e leste", 21.463, -157.81, f"{W}: Kāneʻohe Bay"),
    Recife("midway", "Atol de Midway", "Havaí, ilhas do noroeste", "Pacífico central e leste", 28.208, -177.35, f"{W}: Midway Atoll"),
    Recife("kiritimati", "Kiritimati", "Kiribati, Pacífico equatorial", "Pacífico central e leste", 1.85, -157.4, f"{W}: Kiritimati"),
    Recife("moorea", "Moorea", "Polinésia Francesa", "Pacífico central e leste", -17.535, -149.835, f"{W}: Moʼorea"),
    Recife("galapagos", "Ilha Darwin", "Galápagos", "Pacífico central e leste", 1.678, -92.003, f"{W}: Darwin Island"),
    Recife("cocos", "Ilha do Coco", "Pacífico leste, Costa Rica", "Pacífico central e leste", 5.528, -87.061, f"{W}: Cocos Island"),
    Recife("clipperton", "Clipperton", "Pacífico leste, atol remoto", "Pacífico central e leste", 10.3, -109.217, f"{W}: Clipperton Island"),
    # Caribe e Atlântico Norte
    Recife("florida_keys", "Looe Key", "Florida Keys", "Caribe e Atlântico Norte", 24.549, -81.406, f"{W}: Looe Key"),
    Recife("belize", "Glover's Reef", "Belize", "Caribe e Atlântico Norte", 16.823, -87.791, f"{W}: Glover's Reef"),
    Recife("curacao", "Curaçao", "Caribe sul", "Caribe e Atlântico Norte", 12.2, -69.0, f"{W}: Curaçao"),
    Recife("bermudas", "Bermudas", "Atlântico Norte (recife mais ao norte do Atlântico)", "Caribe e Atlântico Norte", 32.32, -64.74, f"{W}: Bermuda"),
    # Atlântico Sul
    Recife("manuel_luis", "Parcel de Manuel Luís", "Brasil, Maranhão", "Atlântico Sul", -0.913, -44.32, f"{W}: Parcel de Manuel Luís Marine State Park"),
    Recife("rocas", "Atol das Rocas", "Brasil, atol oceânico", "Atlântico Sul", -3.867, -33.817, f"{W}: Rocas Atoll"),
    Recife("noronha", "Fernando de Noronha", "Brasil, ilha oceânica", "Atlântico Sul", -3.855, -32.425, f"{W}: Fernando de Noronha"),
    Recife("abrolhos", "Abrolhos", "Brasil, Bahia", "Atlântico Sul", -17.963, -38.703, f"{W}: Abrolhos Archipelago"),
    Recife("trindade", "Trindade", "Brasil, ilha oceânica", "Atlântico Sul", -20.525, -29.325, f"{W}: Trindade and Martim Vaz"),
]

# Recifes de referência: um por bacia. Só para eles a coleta traz as séries diárias completas (DHW oficial,
# CoralTemp e OISST), porque cada série diária de 40 anos leva de 8 a 20 minutos no ERDDAP. É neles que o DHW é
# reimplementado dia a dia e que as ondas de calor marinhas são medidas.
REFERENCIA = ["lizard", "maldivas", "sir_abu_nuayr", "kiritimati", "florida_keys", "abrolhos"]

POR_SLUG = {r.slug: r for r in RECIFES}
GRUPOS = list(dict.fromkeys(r.grupo for r in RECIFES))
