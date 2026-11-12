"""Bloco `para_o_site` de reports/resultados.json: os textos em três idiomas e a especificação do gráfico.

Todos os números dos textos são lidos dos resultados; nada é digitado à mão.
"""

from __future__ import annotations


def _pt(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def _en(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}"


MESES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _cento(fracao: float | None) -> int:
    """Fração em percentual inteiro; sem valor (nenhum alerta emitido) conta como zero."""
    return 0 if fracao is None else int(round(fracao * 100))


def montar(r: dict) -> dict:
    tend = r["tendencias"]
    c4 = tend["dhw4"]["conjunto"]
    ret = tend["dhw4"]["retorno"]["todos"]
    antes, depois = ret["antes"]["retorno"], ret["depois"]["retorno"]
    razao, ic = c4["razao_de_chances_por_decada"], c4["razao_de_chances_ic"]
    n = len(r["recifes"])
    cont = tend["dhw4"]["contagem"]
    prev = r["previsao"]["antecedencias"]
    b = {s: {m: prev[s]["metodos"][m]["brier"] for m in ("modelo", "persistencia_calibrada", "persistencia", "climatologia")} for s in prev}
    alerta8 = prev["8"]["metodos"]["modelo"]["alerta"]
    alerta4 = prev["4"]["metodos"]["modelo"]["alerta"]
    # O veredito a 8 semanas sai do intervalo da diferença de Brier entre o modelo e a persistência calibrada.
    inf, sup = prev["8"]["comparacoes"]["modelo_menos_persistencia_calibrada"]["ic"]
    if sup < 0:
        veredito = {"pt": "supera", "en": "beats", "es": "supera"}
    elif inf > 0:
        veredito = {"pt": "perde para", "en": "loses to", "es": "pierde frente a"}
    else:
        veredito = {"pt": "empata com", "en": "ties with", "es": "empata con"}
    anos = tend["anos"]
    ano, mes, dia = r["coleta"]["coletado_em"].split("-")
    levantamentos = r["branqueamento_observado"]["levantamentos"]
    milhar = f"{levantamentos:,}".replace(",", ".")
    f4 = c4["fracao_por_ano"]
    f8 = tend["dhw8"]["conjunto"]["fracao_por_ano"]

    def pontos(valores: list[float]) -> list[list]:
        return [[f"{a}-01-01", round(float(v), 4)] for a, v in zip(anos, valores)]

    return {
        "numero_chave": {"pt": f"{_pt(antes, 0)} → {_pt(depois, 0)} anos", "en": f"{_en(antes, 0)} → {_en(depois, 0)} yrs", "es": f"{_pt(antes, 0)} → {_pt(depois, 0)} años"},
        "pergunta": {
            "pt": "Em quais recifes o estresse térmico que branqueia corais está chegando mais cedo e mais vezes, e dá para avisar com antecedência?",
            "en": "Which coral reefs are being hit by bleaching-level heat stress sooner and more often, and can we warn ahead of time?",
            "es": "¿En qué arrecifes el estrés térmico que blanquea corales llega antes y más veces, y se puede avisar con antelación?",
        },
        "resultado": {
            "pt": f"Em {n} recifes do mundo todo, um ano de alerta de branqueamento (DHW de 4 °C-semana ou mais) vinha a cada {_pt(antes)} anos por recife em 1985-2004 e passou a vir a cada {_pt(depois)} anos em 2005-2024. As chances de um recife ter um ano assim multiplicam por {_pt(razao, 2)} a cada década (IC 95%: {_pt(ic[0], 2)} a {_pt(ic[1], 2)}).",
            "en": f"Across {n} reefs worldwide, a bleaching-alert year (DHW of 4 °C-weeks or more) came once every {_en(antes)} years per reef in 1985-2004 and once every {_en(depois)} years in 2005-2024. The odds of such a year multiply by {_en(razao, 2)} per decade (95% CI {_en(ic[0], 2)} to {_en(ic[1], 2)}).",
            "es": f"En {n} arrecifes de todo el mundo, un año de alerta de blanqueamiento (DHW de 4 °C-semana o más) llegaba cada {_pt(antes)} años por arrecife en 1985-2004 y pasó a llegar cada {_pt(depois)} años en 2005-2024. Las probabilidades relativas (odds) de un año así se multiplican por {_pt(razao, 2)} cada década (IC 95%: {_pt(ic[0], 2)} a {_pt(ic[1], 2)}).",
        },
        "detalhe": {
            "pt": f"Recife a recife a certeza é menor: corrigidas as múltiplas comparações, a tendência é significativa em {cont['p_bh_menor_que_5']} dos {n}. Um alerta simples é confiável com 4 semanas ({_cento(alerta4['precisao'])}% dos alertas se confirmam e {_cento(alerta4['avisados'])}% dos eventos são avisados); com 8 semanas o modelo {veredito['pt']} a persistência da anomalia (Brier de {_pt(b['8']['modelo'], 3)} contra {_pt(b['8']['persistencia_calibrada'], 3)}) e avisa só {_cento(alerta8['avisados'])}% dos eventos.",
            "en": f"Reef by reef the evidence is weaker: after correcting for multiple comparisons the trend is significant at {cont['p_bh_menor_que_5']} of {n}. A simple alert is dependable four weeks out ({_cento(alerta4['precisao'])}% of alerts come true and {_cento(alerta4['avisados'])}% of events are flagged); at eight weeks the model {veredito['en']} anomaly persistence (Brier {_en(b['8']['modelo'], 3)} vs {_en(b['8']['persistencia_calibrada'], 3)}) and flags only {_cento(alerta8['avisados'])}% of events.",
            "es": f"Arrecife por arrecife la certeza es menor: corregidas las comparaciones múltiples, la tendencia es significativa en {cont['p_bh_menor_que_5']} de {n}. Una alerta simple es fiable con 4 semanas (el {_cento(alerta4['precisao'])}% de las alertas se confirma y se avisa el {_cento(alerta4['avisados'])}% de los eventos); con 8 semanas el modelo {veredito['es']} la persistencia de la anomalía (Brier de {_pt(b['8']['modelo'], 3)} frente a {_pt(b['8']['persistencia_calibrada'], 3)}) y avisa solo el {_cento(alerta8['avisados'])}% de los eventos.",
        },
        "dados": {
            "pt": f"NOAA Coral Reef Watch v3.1 (DHW e CoralTemp, 5 km) em {n} pontos de recife, de {anos[0]} a {anos[-1]}, mais {milhar} levantamentos de campo de branqueamento; coleta de {dia}/{mes}/{ano}.",
            "en": f"NOAA Coral Reef Watch v3.1 (DHW and CoralTemp, 5 km) at {n} reef points, {anos[0]} to {anos[-1]}, plus {levantamentos:,} field bleaching surveys; collected {int(dia)} {MESES_EN[int(mes) - 1]} {ano}.",
            "es": f"NOAA Coral Reef Watch v3.1 (DHW y CoralTemp, 5 km) en {n} puntos de arrecife, de {anos[0]} a {anos[-1]}, más {milhar} muestreos de campo de blanqueamiento; datos recogidos el {dia}/{mes}/{ano}.",
        },
        "etiquetas": ["séries de satélite", "detecção de extremos", "bootstrap em blocos", "previsão probabilística", "ciência marinha"],
        "grafico": {
            "tipo": "linhas",
            "titulo": {
                "pt": "Fração dos recifes em estresse térmico severo, por ano",
                "en": "Share of reefs under severe heat stress, by year",
                "es": "Fracción de arrecifes con estrés térmico severo, por año",
            },
            "eixo_x": {"pt": "Ano", "en": "Year", "es": "Año"},
            "eixo_y": {"pt": "Fração dos recifes do estudo", "en": "Share of the reefs in the study", "es": "Fracción de los arrecifes del estudio"},
            "formato_x": "data",
            "formato_y": "percentual",
            "series": [
                {"nome": {"pt": "DHW ≥ 4 °C-semana (alerta nível 1)", "en": "DHW ≥ 4 °C-weeks (Alert Level 1)", "es": "DHW ≥ 4 °C-semana (alerta nivel 1)"}, "papel": "principal", "pontos": pontos(f4)},
                {"nome": {"pt": "DHW ≥ 8 °C-semana (alerta nível 2)", "en": "DHW ≥ 8 °C-weeks (Alert Level 2)", "es": "DHW ≥ 8 °C-semana (alerta nivel 2)"}, "papel": "alternativa", "pontos": pontos(f8)},
                {"nome": {"pt": "Tendência do DHW ≥ 4", "en": "Trend for DHW ≥ 4", "es": "Tendencia del DHW ≥ 4"}, "papel": "neutro", "pontos": pontos(c4["curva"])},
            ],
            "faixa": {"serie": 2, "inferior": pontos(c4["curva_inf"]), "superior": pontos(c4["curva_sup"])},
        },
    }
