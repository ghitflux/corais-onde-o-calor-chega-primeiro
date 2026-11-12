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
        "graficos_extras": graficos_extras(r),
    }


REGIOES = {
    "Pacífico oeste": {"pt": "Pacífico oeste", "en": "Western Pacific", "es": "Pacífico occidental"},
    "Índico": {"pt": "Índico", "en": "Indian Ocean", "es": "Índico"},
    "Mar Vermelho e golfo Pérsico": {"pt": "Mar Vermelho e golfo Pérsico", "en": "Red Sea and Persian Gulf", "es": "Mar Rojo y golfo Pérsico"},
    "Pacífico central e leste": {"pt": "Pacífico central e leste", "en": "Central and eastern Pacific", "es": "Pacífico central y oriental"},
    "Caribe e Atlântico Norte": {"pt": "Caribe e Atlântico Norte", "en": "Caribbean and North Atlantic", "es": "Caribe y Atlántico Norte"},
    "Atlântico Sul": {"pt": "Atlântico Sul", "en": "South Atlantic", "es": "Atlántico Sur"},
    "todos": {"pt": "Todos os recifes", "en": "All reefs", "es": "Todos los arrecifes"},
}


def _finito(valor) -> bool:
    return valor is not None and valor == valor and abs(valor) != float("inf")


def graficos_extras(r: dict) -> list[dict]:
    """Os outros achados do estudo como dados, para o site desenhar: as figuras do README menos a principal.

    Ordem: intervalo de retorno por região, previsão por antecedência, DHW refeito contra o oficial, ranking de
    exposição e curva de confiabilidade. O mapa não entra; as barras por região e o ranking resumem o mesmo achado.
    """
    tend, prev, conf, rank = r["tendencias"], r["previsao"]["antecedencias"], r["conferencia_do_dhw"], r["ranking"]

    # 1. Intervalo de retorno do ano de alerta, antes e depois de 2005, por região.
    retorno = tend["dhw4"]["retorno"]
    nomes = [k for k in retorno if k != "todos"] + ["todos"]
    rotulos = {idioma: [REGIOES.get(k, {}).get(idioma, k) for k in nomes] for idioma in ("pt", "en", "es")}

    def anos(bloco: dict) -> float:
        # Sem nenhum evento no período o intervalo é infinito; entra o tamanho do período, que é o mínimo que os
        # dados permitem afirmar.
        return round(bloco["retorno"], 1) if _finito(bloco["retorno"]) else float(bloco["recifes_ano"])

    todos_antes, todos_depois = anos(retorno["todos"]["antes"]), anos(retorno["todos"]["depois"])
    encolheu = sum(1 for k in nomes[:-1] if anos(retorno[k]["depois"]) < anos(retorno[k]["antes"]))
    n_regioes = len(nomes) - 1
    todas = encolheu == n_regioes
    g_retorno = {
        "tipo": "barras",
        "titulo": {
            "pt": f"O intervalo entre anos de alerta encolheu nas {n_regioes} regiões" if todas else f"O intervalo entre anos de alerta encolheu em {encolheu} das {n_regioes} regiões",
            "en": f"The gap between alert years shrank in all {n_regioes} regions" if todas else f"The gap between alert years shrank in {encolheu} of {n_regioes} regions",
            "es": f"El intervalo entre años de alerta se acortó en las {n_regioes} regiones" if todas else f"El intervalo entre años de alerta se acortó en {encolheu} de {n_regioes} regiones",
        },
        "eixo_x": {"pt": "Região", "en": "Region", "es": "Región"},
        "eixo_y": {"pt": "Anos entre dois anos de alerta", "en": "Years between two alert years", "es": "Años entre dos años de alerta"},
        "formato_x": "numero",
        "formato_y": "numero",
        "series": [
            {"nome": {"pt": "1985-2004", "en": "1985-2004", "es": "1985-2004"}, "papel": "base", "pontos": [[k, anos(retorno[k]["antes"])] for k in nomes], "rotulos": rotulos},
            {"nome": {"pt": "2005-2024", "en": "2005-2024", "es": "2005-2024"}, "papel": "principal", "pontos": [[k, anos(retorno[k]["depois"])] for k in nomes], "rotulos": rotulos},
        ],
        "leitura": {
            "pt": f"Anos, em média, entre dois anos com DHW de 4 °C-semana ou mais por recife: no conjunto, de {_pt(todos_antes)} para {_pt(todos_depois)}; barra menor é alerta mais frequente.",
            "en": f"Average years between two years with DHW of 4 °C-weeks or more per reef: overall, from {_en(todos_antes)} to {_en(todos_depois)}; a shorter bar means more frequent alerts.",
            "es": f"Años, en promedio, entre dos años con DHW de 4 °C-semana o más por arrecife: en conjunto, de {_pt(todos_antes)} a {_pt(todos_depois)}; una barra más corta es alerta más frecuente.",
        },
    }

    # 2. Erro de previsão (Brier) por antecedência, contra as linhas de base.
    semanas = list(prev)
    rot_sem = {"pt": [f"{s} semanas" for s in semanas], "en": [f"{s} weeks" for s in semanas], "es": [f"{s} semanas" for s in semanas]}

    def brier(metodo: str) -> list[list]:
        return [[f"{s} semanas", round(prev[s]["metodos"][metodo]["brier"], 4)] for s in semanas]

    def veredito(s: str) -> dict:
        inf, sup = prev[s]["comparacoes"]["modelo_menos_persistencia_calibrada"]["ic"]
        if sup < 0:
            return {"pt": "ganha", "en": "wins", "es": "gana"}
        if inf > 0:
            return {"pt": "perde", "en": "loses", "es": "pierde"}
        return {"pt": "empata", "en": "ties", "es": "empata"}

    v = [veredito(s) for s in semanas]
    g_previsao = {
        "tipo": "barras",
        "titulo": {
            "pt": "Contra a persistência, o modelo " + ", ".join(f"{x['pt']} com {s}" for x, s in zip(v, semanas)) + " semanas",
            "en": "Against persistence, the model " + ", ".join(f"{x['en']} at {s}" for x, s in zip(v, semanas)) + " weeks",
            "es": "Frente a la persistencia, el modelo " + ", ".join(f"{x['es']} con {s}" for x, s in zip(v, semanas)) + " semanas",
        },
        "eixo_x": {"pt": "Antecedência", "en": "Lead time", "es": "Antelación"},
        "eixo_y": {"pt": "Erro de Brier no teste (menor é melhor)", "en": "Brier score on the test set (lower is better)", "es": "Error de Brier en la prueba (menor es mejor)"},
        "formato_x": "numero",
        "formato_y": "numero",
        "series": [
            {"nome": {"pt": "Climatologia", "en": "Climatology", "es": "Climatología"}, "papel": "neutro", "pontos": brier("climatologia"), "rotulos": rot_sem},
            {"nome": {"pt": "Persistência calibrada", "en": "Calibrated persistence", "es": "Persistencia calibrada"}, "papel": "base", "pontos": brier("persistencia_calibrada"), "rotulos": rot_sem},
            {"nome": {"pt": "Modelo simples", "en": "Simple model", "es": "Modelo simple"}, "papel": "principal", "pontos": brier("modelo"), "rotulos": rot_sem},
            {"nome": {"pt": "Modelo + projeção", "en": "Model + projection", "es": "Modelo + proyección"}, "papel": "alternativa", "pontos": brier("modelo_com_projecao"), "rotulos": rot_sem},
        ],
        "leitura": {
            "pt": "Erro ao prever se o DHW estará em 4 ou mais na data-alvo, com treino até 2010 e teste depois: quanto mais longe, menos o modelo se distingue de supor que a anomalia de hoje continua.",
            "en": "Error when predicting whether DHW will be at 4 or more on the target date, trained to 2010 and tested afterwards: the longer the lead, the less the model differs from assuming today's anomaly persists.",
            "es": "Error al predecir si el DHW estará en 4 o más en la fecha objetivo, con entrenamiento hasta 2010 y prueba después: cuanto más lejos, menos se distingue el modelo de suponer que la anomalía de hoy continúa.",
        },
    }

    # 3. DHW máximo do ano: refeito contra oficial, com a mesma temperatura e com outra.
    def nuvem(chave: str) -> list[list]:
        pares = conf["pares_do_maximo_anual"][chave]
        passo = max(1, -(-len(pares) // 300))
        return [[round(float(a), 2), round(float(b), 2)] for a, b in pares[::passo]]

    erro_mesmo = conf["resumo"]["climatologia"]["erro_absoluto_do_maximo_anual"]
    erro_outro = conf["resumo"]["outro_produto"]["erro_absoluto_do_maximo_anual"]
    g_dhw = {
        "tipo": "pontos",
        "titulo": {
            "pt": f"O DHW refeito bate com o oficial (erro de {_pt(erro_mesmo, 2)}); com outra temperatura, {_pt(erro_outro, 2)}",
            "en": f"The rebuilt DHW matches the official one (error {_en(erro_mesmo, 2)}); with other SST data, {_en(erro_outro, 2)}",
            "es": f"El DHW rehecho coincide con el oficial (error de {_pt(erro_mesmo, 2)}); con otra temperatura, {_pt(erro_outro, 2)}",
        },
        "eixo_x": {"pt": "DHW máximo do ano, oficial (°C-semana)", "en": "Annual maximum DHW, official (°C-weeks)", "es": "DHW máximo del año, oficial (°C-semana)"},
        "eixo_y": {"pt": "DHW máximo do ano, refeito (°C-semana)", "en": "Annual maximum DHW, rebuilt (°C-weeks)", "es": "DHW máximo del año, rehecho (°C-semana)"},
        "formato_x": "numero",
        "formato_y": "numero",
        "series": [
            {"nome": {"pt": "Mesma temperatura (CoralTemp, 5 km)", "en": "Same temperature (CoralTemp, 5 km)", "es": "Misma temperatura (CoralTemp, 5 km)"}, "papel": "principal", "pontos": nuvem("climatologia")},
            {"nome": {"pt": "Outra temperatura (OISST, 0,25°)", "en": "Other temperature (OISST, 0.25°)", "es": "Otra temperatura (OISST, 0,25°)"}, "papel": "alternativa", "pontos": nuvem("outro_produto")},
        ],
        "leitura": {
            "pt": f"Cada ponto é um ano num dos {len(conf['recifes_de_referencia'])} recifes de referência: com a temperatura oficial os pontos caem na diagonal; trocando o produto de temperatura, espalham-se.",
            "en": f"Each dot is one year at one of the {len(conf['recifes_de_referencia'])} reference reefs: with the official temperature the dots sit on the diagonal; swap the temperature product and they scatter.",
            "es": f"Cada punto es un año en uno de los {len(conf['recifes_de_referencia'])} arrecifes de referencia: con la temperatura oficial los puntos caen en la diagonal; al cambiar el producto de temperatura, se dispersan.",
        },
    }

    # 4. Ranking de exposição: probabilidade de cada recife estar no terço mais exposto.
    linhas = rank["por_recife"][:80]
    g_ranking = {
        "tipo": "barras",
        "titulo": {
            "pt": f"{rank['certos_no_terco']} recifes estão no terço mais exposto com 90% de certeza; {rank['indefinidos']} ficam indefinidos",
            "en": f"{rank['certos_no_terco']} reefs are in the most exposed third with 90% certainty; {rank['indefinidos']} are undetermined",
            "es": f"{rank['certos_no_terco']} arrecifes están en el tercio más expuesto con 90% de certeza; {rank['indefinidos']} quedan indefinidos",
        },
        "eixo_x": {"pt": "Recife, na ordem do ranking", "en": "Reef, in ranking order", "es": "Arrecife, en el orden del ranking"},
        "eixo_y": {"pt": "Probabilidade de estar no terço mais exposto", "en": "Probability of being in the most exposed third", "es": "Probabilidad de estar en el tercio más expuesto"},
        "formato_x": "numero",
        "formato_y": "percentual",
        "series": [
            {"nome": {"pt": "Probabilidade (bootstrap de anos)", "en": "Probability (bootstrap over years)", "es": "Probabilidad (bootstrap de años)"}, "papel": "principal", "pontos": [[x["nome"], round(x["prob_terco_mais_exposto"], 3)] for x in linhas]},
        ],
        "leitura": {
            "pt": f"Exposição em {rank['periodo'][0]}-{rank['periodo'][1]} pelos anos com DHW de 4 e de 8 ou mais; o topo e o fundo são firmes, o meio não, e exposição térmica não é branqueamento.",
            "en": f"Exposure in {rank['periodo'][0]}-{rank['periodo'][1]} from years with DHW of 4 and of 8 or more; the top and bottom are firm, the middle is not, and thermal exposure is not bleaching.",
            "es": f"Exposición en {rank['periodo'][0]}-{rank['periodo'][1]} según los años con DHW de 4 y de 8 o más; la cima y el fondo son firmes, el medio no, y exposición térmica no es blanqueamiento.",
        },
    }

    # 5. Curva de confiabilidade a 8 semanas.
    metodos = prev["8"]["metodos"]

    def curva(metodo: str) -> list[list]:
        return [[round(f["previsto"], 4), round(f["observado"], 4)] for f in metodos[metodo]["confiabilidade"] if f["n"] >= 20]

    g_confiabilidade = {
        "tipo": "linhas",
        "titulo": {
            "pt": "A 8 semanas, as previsões subestimam: o alerta vem mais vezes do que elas dizem",
            "en": "At 8 weeks the forecasts run low: alerts come more often than predicted",
            "es": "A 8 semanas, las previsiones se quedan cortas: la alerta llega más veces de lo que dicen",
        },
        "eixo_x": {"pt": "Probabilidade prevista", "en": "Predicted probability", "es": "Probabilidad prevista"},
        "eixo_y": {"pt": "Frequência observada", "en": "Observed frequency", "es": "Frecuencia observada"},
        "formato_x": "percentual",
        "formato_y": "percentual",
        "series": [
            {"nome": {"pt": "Modelo simples", "en": "Simple model", "es": "Modelo simple"}, "papel": "principal", "pontos": curva("modelo")},
            {"nome": {"pt": "Persistência calibrada", "en": "Calibrated persistence", "es": "Persistencia calibrada"}, "papel": "base", "pontos": curva("persistencia_calibrada")},
            {"nome": {"pt": "Calibração perfeita", "en": "Perfect calibration", "es": "Calibración perfecta"}, "papel": "neutro", "pontos": [[0.0, 0.0], [1.0, 1.0]]},
        ],
        "leitura": {
            "pt": f"Acima da diagonal, o evento acontece mais do que o previsto: a frequência do alerta foi de {_pt(prev['8']['treino']['taxa_de_eventos'] * 100)}% no treino e de {_pt(prev['8']['teste']['taxa_de_eventos'] * 100)}% no teste.",
            "en": f"Above the diagonal the event happens more often than predicted: the alert rate was {_en(prev['8']['treino']['taxa_de_eventos'] * 100)}% in training and {_en(prev['8']['teste']['taxa_de_eventos'] * 100)}% in the test period.",
            "es": f"Por encima de la diagonal, el evento ocurre más de lo previsto: la frecuencia de la alerta fue del {_pt(prev['8']['treino']['taxa_de_eventos'] * 100)}% en el entrenamiento y del {_pt(prev['8']['teste']['taxa_de_eventos'] * 100)}% en la prueba.",
        },
    }
    return [g_retorno, g_previsao, g_dhw, g_ranking, g_confiabilidade]
