"""Orquestra cada tabela do estudo. Cada função devolve estruturas simples, prontas para o JSON."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from corais_calor import dhw, ondas, previsao, tendencia
from corais_calor.dados import Base, dias

SEMENTE = 20261112
LIMIARES = {"dhw4": dhw.LIMIAR_ALERTA_1, "dhw8": dhw.LIMIAR_ALERTA_2}
DECADAS = [(1985, 1994), (1995, 2004), (2005, 2014), (2015, 2024)]
PERIODOS = [(1985, 2004), (2005, 2024)]
# Eventos globais de branqueamento declarados pela NOAA Coral Reef Watch (o quarto vai de 2023 a 2025).
EVENTOS_GLOBAIS = {"1998": [1998], "2010": [2010], "2014-2017": [2014, 2015, 2016, 2017], "2023-2025": [2023, 2024, 2025]}
ANTECEDENCIAS = [4, 8, 12]  # semanas
ULTIMO_ANO_DE_TREINO = 2010
BLOCO_ANOS = 4
ATRASO_NINO_SEMANAS = 1  # o índice semanal do CPC sai na semana seguinte
SEMANAS_MINIMAS_NO_ANO = 34
# Ondas de calor: 30 anos de referência no CoralTemp, que começa em 1985 e não tem lacunas. (O OISST do servidor
# tem cerca de metade dos dias faltando entre 1992 e 1998, o que impede usá-lo para contar dias seguidos.)
REFERENCIA_DAS_ONDAS = (1985, 2014)
FAIXAS_CONFIABILIDADE = [0.0, 0.05, 0.15, 0.3, 0.5, 0.7, 0.85, 1.0]


@dataclass
class Serie:
    """Um recife, com uma data a cada 7 dias (todos os recifes têm)."""

    slug: str
    nome: str
    grupo: str
    datas: np.ndarray
    sst: np.ndarray  # CoralTemp
    dhw_noaa: np.ndarray  # produto oficial
    clima: np.ndarray  # climatologia mensal recentrada, calculada aqui a partir da média mensal do CoralTemp
    mmm: float  # MMM calculado aqui
    mmm_simples: float  # o mesmo sem recentrar (média simples de 1985-2012)
    mmm_noaa: float  # MMM do produto oficial (temperatura menos HotSpot)
    mes_pico: int


@dataclass
class Diaria:
    """Um recife de referência, com as séries diárias."""

    slug: str
    nome: str
    datas: np.ndarray
    sst: np.ndarray  # CoralTemp
    dhw_noaa: np.ndarray
    datas_oisst: np.ndarray
    sst_oisst: np.ndarray
    serie: Serie


def preparar(base: Base) -> tuple[list[Serie], list[Diaria]]:
    """Climatologia e MMM de cada recife, e as séries diárias dos recifes de referência."""
    semanas = dias(base.sst_semanal.index)
    meses = dias(base.sst_mensal.index)
    series = []
    for slug, linha in base.recifes.iterrows():
        mensal = base.sst_mensal[slug].to_numpy(float)
        clima = dhw.climatologia_mensal(meses, mensal)
        series.append(
            Serie(
                slug=slug,
                nome=linha["nome"],
                grupo=linha["grupo"],
                datas=semanas,
                sst=base.sst_semanal[slug].to_numpy(float),
                dhw_noaa=base.dhw_semanal[slug].to_numpy(float),
                clima=clima,
                mmm=dhw.mmm(clima),
                mmm_simples=dhw.mmm(dhw.climatologia_mensal(meses, mensal, centro=None)),
                mmm_noaa=float(linha["mmm_noaa"]),
                mes_pico=dhw.mes_mais_quente(clima),
            )
        )
    por_slug = {s.slug: s for s in series}
    oficial = base.ref_dhw.reindex(base.ref_sst.index)
    diarias = [
        Diaria(
            slug=slug,
            nome=por_slug[slug].nome,
            datas=dias(base.ref_sst.index),
            sst=base.ref_sst[slug].to_numpy(float),
            dhw_noaa=oficial[slug].to_numpy(float),
            datas_oisst=dias(base.ref_oisst.index),
            sst_oisst=base.ref_oisst[slug].to_numpy(float),
            serie=por_slug[slug],
        )
        for slug in base.referencia
    ]
    return series, diarias


def matriz_anual(series: list[Serie]) -> pd.DataFrame:
    """Máximo do DHW oficial em cada ano de estresse (linhas) e recife (colunas), a partir das datas semanais."""
    colunas = {}
    for s in series:
        anos, maximos = dhw.maximo_anual(s.datas, s.dhw_noaa, s.mes_pico, cobertura_minima=SEMANAS_MINIMAS_NO_ANO)
        colunas[s.slug] = pd.Series(maximos, index=anos)
    return pd.DataFrame(colunas).sort_index().rename_axis("ano")


# ---------------------------------------------------------------------------------------------------------------
# 1. O DHW reimplementado confere com o oficial?
# ---------------------------------------------------------------------------------------------------------------


def _concordancia(a: np.ndarray, b: np.ndarray) -> dict:
    """Concordância entre duas classificações binárias: tabela 2x2 e kappa de Cohen."""
    a, b = np.asarray(a, dtype=bool), np.asarray(b, dtype=bool)
    n = len(a)
    ambos, nenhum = int((a & b).sum()), int((~a & ~b).sum())
    so_a, so_b = int((a & ~b).sum()), int((~a & b).sum())
    observado = (ambos + nenhum) / n
    esperado = (a.mean() * b.mean()) + ((1 - a.mean()) * (1 - b.mean()))
    kappa = (observado - esperado) / (1 - esperado) if esperado < 1 else float("nan")
    return {"ambos": ambos, "nenhum": nenhum, "so_reimplementado": so_a, "so_oficial": so_b, "concordancia": observado, "kappa": float(kappa)}


def _comparar_anual(pares: list[tuple[float, float]]) -> dict:
    """Resumo da comparação entre máximos anuais (oficial, reimplementado)."""
    oficial, refeito = np.array(pares).T
    dif = refeito - oficial
    return {
        "recifes_ano": int(len(dif)),
        "correlacao_do_maximo_anual": float(np.corrcoef(refeito, oficial)[0, 1]),
        "vies_do_maximo_anual": float(dif.mean()),
        "erro_absoluto_do_maximo_anual": float(np.abs(dif).mean()),
        "erro_maximo_do_maximo_anual": float(np.abs(dif).max()),
        "dhw4": _concordancia(refeito >= 4, oficial >= 4),
        "dhw8": _concordancia(refeito >= 8, oficial >= 8),
    }


def _pares_anuais(datas_a, oficial, datas_b, refeito, mes_pico: int, cobertura: int) -> list[tuple[float, float]]:
    anos_a, max_a = dhw.maximo_anual(datas_a, oficial, mes_pico, cobertura)
    anos_b, max_b = dhw.maximo_anual(datas_b, refeito, mes_pico, cobertura)
    b = dict(zip(anos_b.tolist(), max_b.tolist()))
    return [(float(m), float(b[a])) for a, m in zip(anos_a.tolist(), max_a.tolist()) if a in b]


def conferir_dhw(series: list[Serie], diarias: list[Diaria]) -> dict:
    """Compara o DHW reimplementado com o produto oficial.

    Quatro degraus, do mais controlado ao menos:
    - algoritmo: temperatura diária oficial (CoralTemp) e MMM oficial; só a acumulação é minha;
    - climatologia: a mesma temperatura, com o MMM calculado aqui;
    - outro_produto: temperatura diária do OISST (0,25°) e MMM calculado no próprio OISST;
    - semanal: uma temperatura a cada 7 dias (CoralTemp) e MMM oficial, em todos os recifes.
    """
    pares = {"algoritmo": [], "climatologia": [], "outro_produto": [], "semanal": [], "amostragem_semanal": []}
    por_recife = []
    for d in diarias:
        s = d.serie
        valido = np.isfinite(d.dhw_noaa)
        a = dhw.dhw(d.sst, s.mmm_noaa)
        b = dhw.dhw(d.sst, s.mmm)
        clima_oisst = dhw.climatologia_mensal(d.datas_oisst, d.sst_oisst)
        mmm_oisst = dhw.mmm(clima_oisst)
        # O OISST do servidor tem dias faltando (sobretudo de 1992 a 1998). Para acumular, as lacunas são
        # interpoladas; para comparar, só valem os dias que existem, e ano com menos de 240 dias fica de fora.
        preenchida = pd.Series(d.sst_oisst).interpolate(limit_direction="both").to_numpy()
        c = np.where(np.isfinite(d.sst_oisst), dhw.dhw(preenchida, mmm_oisst), np.nan)
        c_no_dia = pd.Series(c, index=d.datas_oisst).reindex(d.datas).to_numpy()
        ambos = valido & np.isfinite(c_no_dia)
        oficial_valido = np.where(valido, d.dhw_noaa, np.nan)
        pares["algoritmo"] += _pares_anuais(d.datas, oficial_valido, d.datas, np.where(valido, a, np.nan), s.mes_pico, 240)
        pares["climatologia"] += _pares_anuais(d.datas, oficial_valido, d.datas, np.where(valido, b, np.nan), s.mes_pico, 240)
        pares["outro_produto"] += _pares_anuais(d.datas, np.where(ambos, d.dhw_noaa, np.nan), d.datas, np.where(ambos, c_no_dia, np.nan), s.mes_pico, 240)
        # O máximo anual lido numa data a cada 7 dias contra o lido todos os dias, no produto oficial.
        pares["amostragem_semanal"] += _pares_anuais(d.datas, oficial_valido, s.datas, s.dhw_noaa, s.mes_pico, SEMANAS_MINIMAS_NO_ANO)
        por_recife.append(
            {
                "slug": d.slug,
                "nome": d.nome,
                "dias": int(valido.sum()),
                "erro_diario_algoritmo": float(np.mean(np.abs(a[valido] - d.dhw_noaa[valido]))),
                "erro_diario_maximo_algoritmo": float(np.max(np.abs(a[valido] - d.dhw_noaa[valido]))),
                "erro_diario_climatologia": float(np.mean(np.abs(b[valido] - d.dhw_noaa[valido]))),
                "erro_diario_outro_produto": float(np.mean(np.abs(c_no_dia[ambos] - d.dhw_noaa[ambos]))),
                "correlacao_diaria_outro_produto": float(np.corrcoef(c_no_dia[ambos], d.dhw_noaa[ambos])[0, 1]),
                "mmm_noaa": s.mmm_noaa,
                "mmm_coraltemp": round(s.mmm, 3),
                "mmm_oisst": round(mmm_oisst, 3),
                "dhw_maximo_noaa": float(np.nanmax(d.dhw_noaa)),
                "dhw_maximo_algoritmo": float(np.max(a[valido])),
                "dhw_maximo_outro_produto": float(np.nanmax(c_no_dia[ambos])),
                "sst_oisst_menos_coraltemp": float(np.nanmean(pd.Series(d.sst_oisst, index=d.datas_oisst).reindex(d.datas).to_numpy() - d.sst)),
            }
        )
    for s in series:
        semanal = dhw.dhw(s.sst, s.mmm_noaa, janela=12, passo_dias=7)
        valido = np.isfinite(s.dhw_noaa)
        pares["semanal"] += _pares_anuais(s.datas, s.dhw_noaa, s.datas, np.where(valido, semanal, np.nan), s.mes_pico, SEMANAS_MINIMAS_NO_ANO)

    mmm = pd.DataFrame(
        [{"slug": s.slug, "nome": s.nome, "mes_pico": s.mes_pico, "mmm_noaa": s.mmm_noaa, "mmm_calculado": round(s.mmm, 3), "mmm_sem_recentrar": round(s.mmm_simples, 3)} for s in series]
    )
    dif = mmm["mmm_calculado"] - mmm["mmm_noaa"]
    dif_simples = mmm["mmm_sem_recentrar"] - mmm["mmm_noaa"]
    d0 = diarias[0]
    falta = pd.Series(~np.isfinite(d0.sst_oisst), index=pd.DatetimeIndex(d0.datas_oisst))
    buraco = falta.loc["1992-10-01":"1998-07-31"]
    return {
        "recifes_de_referencia": [d.slug for d in diarias],
        "lacunas_do_oisst": {
            "dias_esperados": int(len(falta)),
            "dias_faltando": int(falta.sum()),
            "fracao_faltando_de_out_1992_a_jul_1998": float(buraco.mean()),
            "dias_faltando_fora_desse_trecho": int(falta.sum() - buraco.sum()),
            "maior_lacuna_dias": int(max((b - a + 1 for a, b in ondas.blocos_verdadeiros(falta.to_numpy())), default=0)),
        },
        "resumo": {chave: _comparar_anual(lista) for chave, lista in pares.items()},
        "erro_diario_medio": {
            chave: float(np.mean([r[f"erro_diario_{chave}"] for r in por_recife])) for chave in ("algoritmo", "climatologia", "outro_produto")
        },
        "erro_diario_maximo_algoritmo": float(max(r["erro_diario_maximo_algoritmo"] for r in por_recife)),
        "mmm": {
            "recifes": int(len(mmm)),
            "diferenca_media": float(dif.mean()),
            "diferenca_absoluta_media": float(dif.abs().mean()),
            "diferenca_absoluta_maxima": float(dif.abs().max()),
            "dentro_de_0_05": int((dif.abs() <= 0.05).sum()),
            "sem_recentrar_diferenca_media": float(dif_simples.mean()),
            "sem_recentrar_diferenca_absoluta_media": float(dif_simples.abs().mean()),
            "por_recife": mmm.to_dict(orient="records"),
        },
        "por_recife": por_recife,
        "pares_do_maximo_anual": {chave: np.round(np.array(lista), 2).tolist() for chave, lista in pares.items() if chave in ("algoritmo", "climatologia", "outro_produto")},
    }


# ---------------------------------------------------------------------------------------------------------------
# 2. Ondas de calor marinhas (Hobday et al. 2016), no OISST diário dos recifes de referência
# ---------------------------------------------------------------------------------------------------------------


def ondas_de_calor(diarias: list[Diaria]) -> dict:
    """Frequência, duração e intensidade das ondas de calor marinhas por recife de referência e por década."""
    por_recife = []
    for d in diarias:
        encontradas = ondas.detectar(d.datas, d.sst, referencia=REFERENCIA_DAS_ONDAS)
        decadas = ondas.resumo_por_periodo(d.datas, encontradas, DECADAS)
        maior = max(encontradas, key=lambda o: o.intensidade_acumulada) if encontradas else None
        anos, dias_em_onda = ondas.dias_em_onda_por_ano(d.datas, encontradas)
        completos = (anos >= 1985) & (anos <= 2025)
        x = (anos[completos] - 2005) / 10.0
        inclinacao = float(np.polyfit(x, dias_em_onda[completos], 1)[0])
        por_recife.append(
            {
                "slug": d.slug,
                "nome": d.nome,
                "eventos": len(encontradas),
                "decadas": decadas,
                "dias_a_mais_por_decada": inclinacao,
                "maior_evento": None
                if maior is None
                else {
                    "inicio": str(d.datas[maior.inicio]),
                    "duracao": maior.duracao,
                    "intensidade_maxima": maior.intensidade_maxima,
                    "intensidade_acumulada": maior.intensidade_acumulada,
                },
            }
        )
    resumo = []
    for i, (a, b) in enumerate(DECADAS):
        linha = {"periodo": f"{a}-{b}"}
        for chave in ("eventos_por_ano", "dias_por_ano", "duracao_media", "intensidade_maxima_media"):
            valores = np.array([r["decadas"][i][chave] for r in por_recife])
            linha[chave] = float(valores.mean())
            linha[f"{chave}_min_max"] = [float(valores.min()), float(valores.max())]
        resumo.append(linha)
    primeira = np.array([r["decadas"][0]["dias_por_ano"] for r in por_recife])
    ultima = np.array([r["decadas"][-1]["dias_por_ano"] for r in por_recife])
    return {
        "referencia": list(REFERENCIA_DAS_ONDAS),
        "recifes": len(por_recife),
        "por_recife": por_recife,
        "por_decada": resumo,
        "razao_dias_ultima_sobre_primeira": float(ultima.mean() / primeira.mean()),
        "razao_por_recife": {r["slug"]: float(u / p) if p > 0 else None for r, u, p in zip(por_recife, ultima, primeira)},
        "recifes_com_mais_dias_na_ultima_decada": int((ultima > primeira).sum()),
    }


# ---------------------------------------------------------------------------------------------------------------
# 3. Tendência dos anos de estresse severo e intervalo de retorno
# ---------------------------------------------------------------------------------------------------------------


def _retorno_agrupado(eventos: pd.DataFrame, periodo: tuple[int, int], rng: np.random.Generator, n_boot: int) -> dict:
    """Intervalo de retorno de um conjunto de recifes num período, com IC por bootstrap em blocos de anos."""
    recorte = eventos.loc[(eventos.index >= periodo[0]) & (eventos.index <= periodo[1])]
    valores = recorte.to_numpy(float)
    soma, total = np.nansum(valores), int(np.isfinite(valores).sum())
    prob = soma / total
    n = len(recorte)
    probs = np.empty(n_boot)
    for i in range(n_boot):
        idx = tendencia.indices_em_blocos(n, BLOCO_ANOS, rng)
        probs[i] = np.nansum(valores[idx]) / np.isfinite(valores[idx]).sum()
    inf, sup = np.percentile(probs, [2.5, 97.5])
    return {
        "eventos": int(soma),
        "recifes_ano": total,
        "prob_anual": float(prob),
        "prob_anual_ic": [float(inf), float(sup)],
        "retorno": float(1 / prob) if prob > 0 else float("inf"),
        "retorno_ic": [float(1 / sup) if sup > 0 else float("inf"), float(1 / inf) if inf > 0 else float("inf")],
        "_probs": probs,
    }


def tendencias(series: list[Serie], n_boot: int = 2000, n_perm: int = 5000) -> dict:
    """Frequência dos anos com DHW de 4 e de 8 °C-semana: por recife, por década, por região e no conjunto."""
    anual = matriz_anual(series)
    anos = anual.index.to_numpy()
    grupos = {s.slug: s.grupo for s in series}
    rng = np.random.default_rng(SEMENTE)
    saida = {"anos": anos.tolist(), "maximo_anual": {s: [None if np.isnan(v) else round(float(v), 2) for v in anual[s]] for s in anual.columns}}

    for chave, limiar in LIMIARES.items():
        eventos = (anual >= limiar).astype(float).where(anual.notna())
        # Por recife: tendência logística, valor-p por permutação em blocos e correção para múltiplas comparações.
        linhas = []
        for i, s in enumerate(series):
            y = eventos[s.slug].dropna()
            t = tendencia.tendencia_logistica(y.index.to_numpy(), y.to_numpy(), bloco=BLOCO_ANOS, n_boot=n_boot, n_perm=n_perm, semente=SEMENTE + i)
            linha = {"slug": s.slug, "nome": s.nome, "grupo": s.grupo, "anos_observados": int(len(y)), **t}
            linha["primeiro_ano"] = int(y.index[y.to_numpy() == 1][0]) if y.sum() else None
            linha["por_decada"] = [int(y[(y.index >= a) & (y.index <= b)].sum()) for a, b in DECADAS]
            linha["depois_de_2024"] = int(y[y.index > 2024].sum())
            for (a, b), nome in zip(PERIODOS, ("antes", "depois")):
                recorte = y[(y.index >= a) & (y.index <= b)]
                linha[f"retorno_{nome}"] = tendencia.intervalo_de_retorno(int(recorte.sum()), int(len(recorte)))
            linhas.append(linha)
        testaveis = [linha for linha in linhas if linha["eventos"] > 0]
        p = np.array([linha["p"] for linha in testaveis])
        for linha, bh, hm in zip(testaveis, tendencia.benjamini_hochberg(p), tendencia.holm(p)):
            linha["p_bh"], linha["p_holm"] = float(bh), float(hm)
        for linha in linhas:
            linha.setdefault("p_bh", None)
            linha.setdefault("p_holm", None)

        # Todos os recifes juntos: a fração atingida por ano.
        conjunto = tendencia.tendencia_da_contagem(anos, eventos.to_numpy(), bloco=BLOCO_ANOS, n_boot=4000, semente=SEMENTE)
        conjunto["fracao_por_ano"] = (eventos.sum(axis=1) / eventos.notna().sum(axis=1)).round(4).tolist()
        conjunto["recifes_observados_por_ano"] = eventos.notna().sum(axis=1).astype(int).tolist()

        # Intervalo de retorno antes e depois de 2005, no conjunto e por região.
        retorno = {}
        recortes = {"todos": list(eventos.columns), **{g: [s for s in eventos.columns if grupos[s] == g] for g in dict.fromkeys(grupos.values())}}
        for nome, colunas in recortes.items():
            antes = _retorno_agrupado(eventos[colunas], PERIODOS[0], rng, 4000)
            depois = _retorno_agrupado(eventos[colunas], PERIODOS[1], rng, 4000)
            with np.errstate(divide="ignore", invalid="ignore"):
                razoes = depois["_probs"] / antes["_probs"]
            razoes = razoes[np.isfinite(razoes)]
            retorno[nome] = {
                "recifes": len(colunas),
                "antes": {k: v for k, v in antes.items() if k != "_probs"},
                "depois": {k: v for k, v in depois.items() if k != "_probs"},
                "razao_de_frequencia": float(depois["prob_anual"] / antes["prob_anual"]) if antes["prob_anual"] > 0 else None,
                "razao_ic": [float(np.percentile(razoes, 2.5)), float(np.percentile(razoes, 97.5))] if len(razoes) > 100 and antes["prob_anual"] > 0 else None,
            }

        def significativos(campo: str, linhas=linhas) -> int:
            return int(sum(1 for linha in linhas if linha[campo] is not None and linha[campo] < 0.05 and linha["inclinacao"] > 0))

        saida[chave] = {
            "limiar": limiar,
            "por_recife": linhas,
            "conjunto": conjunto,
            "retorno": retorno,
            "contagem": {
                "recifes": len(linhas),
                "com_algum_evento": len(testaveis),
                "inclinacao_positiva": int(sum(1 for linha in linhas if linha["inclinacao"] > 0)),
                "p_bruto_menor_que_5": significativos("p"),
                "p_bh_menor_que_5": significativos("p_bh"),
                "p_holm_menor_que_5": significativos("p_holm"),
                "piorou_de_antes_para_depois": int(sum(1 for linha in linhas if linha["retorno_depois"]["eventos"] > linha["retorno_antes"]["eventos"])),
                "melhorou_de_antes_para_depois": int(sum(1 for linha in linhas if linha["retorno_depois"]["eventos"] < linha["retorno_antes"]["eventos"])),
                "sem_evento_antes_e_com_evento_depois": int(sum(1 for linha in linhas if linha["retorno_antes"]["eventos"] == 0 and linha["retorno_depois"]["eventos"] > 0)),
                "sem_evento_em_toda_a_serie": len(linhas) - len(testaveis),
            },
        }
    return saida


def eventos_globais(tend: dict) -> dict:
    """Os eventos globais de branqueamento registrados pela NOAA aparecem nas séries?"""
    anos = np.array(tend["anos"])
    saida = {}
    for chave in LIMIARES:
        fracao = np.array(tend[chave]["conjunto"]["fracao_por_ano"])
        marcados = np.isin(anos, [a for lista in EVENTOS_GLOBAIS.values() for a in lista])
        ordem = np.argsort(-fracao, kind="mergesort")
        saida[chave] = {
            "por_evento": {
                nome: {"anos": lista, "fracao_maxima": float(fracao[np.isin(anos, lista)].max()), "fracao_media": float(fracao[np.isin(anos, lista)].mean())}
                for nome, lista in EVENTOS_GLOBAIS.items()
            },
            "media_nos_anos_de_evento": float(fracao[marcados].mean()),
            "media_nos_outros_anos": float(fracao[~marcados].mean()),
            "dez_piores_anos": [{"ano": int(anos[i]), "fracao": float(fracao[i]), "evento_global": bool(marcados[i])} for i in ordem[:10]],
            "anos_fora_dos_eventos_acima_de_20": [int(a) for a, f, m in zip(anos, fracao, marcados) if not m and f >= 0.2],
        }
    return saida


# ---------------------------------------------------------------------------------------------------------------
# 4. Previsão com 4, 8 e 12 semanas de antecedência
# ---------------------------------------------------------------------------------------------------------------


def anomalia_do_nino(nino: pd.DataFrame, ultimo_ano: int = ULTIMO_ANO_DE_TREINO) -> pd.Series:
    """Anomalia semanal do Niño 3.4: temperatura menos um ciclo sazonal ajustado só até o fim do treino.

    O arquivo do CPC já traz uma anomalia, mas em relação a uma média que inclui anos do período de teste.
    """
    serie = nino["sst_nino34"].dropna()
    dia = serie.index.day_of_year.to_numpy()
    treino = serie.index.year <= ultimo_ano
    coeficientes = previsao.ajustar_ciclo_sazonal(dia[treino], serie.to_numpy()[treino], harmonicos=2)
    return pd.Series(serie.to_numpy() - previsao.ciclo_sazonal(coeficientes, dia), index=serie.index, name="anomalia_nino34")


def amostras_de_previsao(series: list[Serie], nino_anom: pd.Series, semanas: int) -> pd.DataFrame:
    """Uma linha por recife e data de emissão, com o que se sabia no dia e o que aconteceu `semanas` depois."""
    datas_nino = dias(nino_anom.index)
    valores_nino = nino_anom.to_numpy()
    partes = []
    for s in series:
        n = len(s.datas)
        indice = pd.DatetimeIndex(s.datas)
        dia = indice.day_of_year.to_numpy()
        treino = (indice.year <= ULTIMO_ANO_DE_TREINO) & np.isfinite(s.sst)
        clima = previsao.ciclo_sazonal(previsao.ajustar_ciclo_sazonal(dia[treino], s.sst[treino]), dia)
        anomalia = previsao.media_movel_passada(s.sst - clima, 2)  # média das duas últimas leituras semanais
        tend = np.full(n, np.nan)
        tend[4:] = anomalia[4:] - anomalia[:-4]
        emissao = np.arange(5, n - semanas)
        alvo = emissao + semanas
        proj = previsao.dhw_projetado(s.sst, clima, anomalia, s.mmm_noaa, semanas, janela=12, passo_dias=7, posicoes=emissao)
        _, mes_alvo = dhw.ano_e_mes(s.datas[alvo])
        na_estacao = (mes_alvo - s.mes_pico + 2) % 12 <= 5  # de dois meses antes a três meses depois do mês mais quente
        posicao_nino = np.searchsorted(datas_nino, s.datas[emissao], side="right") - 1 - ATRASO_NINO_SEMANAS
        tabela = pd.DataFrame(
            {
                "slug": s.slug,
                "grupo": s.grupo,
                "emissao": s.datas[emissao],
                "alvo": s.datas[alvo],
                "ano": dhw.ano_de_estresse(s.datas[alvo], s.mes_pico),
                "semana": (dia[alvo] - 1) // 7,
                "evento": (s.dhw_noaa[alvo] >= dhw.LIMIAR_ALERTA_1).astype(float),
                "dhw_alvo": s.dhw_noaa[alvo],
                "dhw_atual": s.dhw_noaa[emissao],
                "anomalia": anomalia[emissao],
                "tendencia": tend[emissao],
                "sazonal": clima[alvo] - s.mmm_noaa,
                "projecao": proj[emissao],
                "nino": np.where(posicao_nino >= 0, valores_nino[np.clip(posicao_nino, 0, None)], np.nan),
            }
        )
        partes.append(tabela[na_estacao].dropna(subset=["dhw_alvo", "dhw_atual", "anomalia", "tendencia", "projecao", "nino"]))
    return pd.concat(partes, ignore_index=True)


def _variaveis(amostra: pd.DataFrame, grupos: list[str], com_nino: bool, com_projecao: bool) -> np.ndarray:
    colunas = [amostra["anomalia"], amostra["tendencia"], amostra["dhw_atual"], amostra["sazonal"]]
    if com_nino:
        colunas += [amostra["nino"] * (amostra["grupo"] == g) for g in grupos]
    if com_projecao:
        colunas.append(np.minimum(amostra["projecao"], 24.0))
    return np.column_stack(colunas)


def _alerta(prob: np.ndarray, evento: np.ndarray, corte: float = 0.5) -> dict:
    """Se o alerta for dado quando a probabilidade passa de `corte`: quantos alertas se confirmam e quantos eventos são avisados."""
    alerta = prob >= corte
    confirmados = int((alerta & (evento == 1)).sum())
    return {
        "alertas": int(alerta.sum()),
        "confirmados": confirmados,
        "precisao": confirmados / int(alerta.sum()) if alerta.any() else None,
        "eventos": int(evento.sum()),
        "avisados": confirmados / int(evento.sum()) if evento.sum() else None,
    }


METODOS = {
    "persistencia": "Persistência da anomalia (sim ou não)",
    "persistencia_calibrada": "Persistência da anomalia, calibrada",
    "climatologia": "Climatologia do recife e da época",
    "modelo": "Modelo: anomalia, tendência, DHW atual, estação e Niño 3.4",
    "modelo_com_projecao": "Modelo mais a projeção de persistência",
    "modelo_sem_nino": "Modelo sem o Niño 3.4",
}


def avaliar_previsao(amostra: pd.DataFrame, grupos: list[str], n_boot: int = 2000) -> dict:
    """Treina até 2010, testa depois, e compara os métodos por Brier, AUC e confiabilidade."""
    treino = (amostra["ano"] <= ULTIMO_ANO_DE_TREINO).to_numpy()
    teste = ~treino
    y = amostra["evento"].to_numpy()
    prob = {}
    prob["persistencia"] = (amostra["projecao"].to_numpy() >= dhw.LIMIAR_ALERTA_1).astype(float)
    x_proj = np.minimum(amostra[["projecao"]].to_numpy(), 24.0)
    prob["persistencia_calibrada"] = previsao.Logistica(ridge=0.01).ajustar(x_proj[treino], y[treino]).prever(x_proj)
    clima = np.zeros(len(amostra))
    for _, posicoes in amostra.groupby("slug").indices.items():
        clima[posicoes] = previsao.frequencia_por_semana(amostra["semana"].to_numpy()[posicoes], y[posicoes], treino[posicoes])
    prob["climatologia"] = clima
    coeficientes = {}
    for nome, com_nino, com_proj in (("modelo", True, False), ("modelo_com_projecao", True, True), ("modelo_sem_nino", False, False)):
        X = _variaveis(amostra, grupos, com_nino, com_proj)
        modelo = previsao.Logistica(ridge=1.0).ajustar(X[treino], y[treino])
        prob[nome] = modelo.prever(X)
        nomes = ["constante", "anomalia", "tendencia", "dhw_atual", "sazonal"] + ([f"nino: {g}" for g in grupos] if com_nino else []) + (["projecao"] if com_proj else [])
        coeficientes[nome] = dict(zip(nomes, [round(float(b), 3) for b in modelo.beta]))

    anos_teste = amostra["ano"].to_numpy()[teste]
    y_t = y[teste]
    p_t = {nome: p[teste] for nome, p in prob.items()}
    fora = amostra["dhw_atual"].to_numpy()[teste] < dhw.LIMIAR_ALERTA_1  # ainda fora do alerta no dia da emissão
    nomes = list(METODOS)

    def metricas(idx: np.ndarray) -> np.ndarray:
        return np.array([previsao.brier(p_t[nome][idx], y_t[idx]) for nome in nomes])

    boot = previsao.bootstrap_por_grupo(anos_teste, metricas, n_boot=n_boot, semente=SEMENTE)
    saida = {
        "treino": {"linhas": int(treino.sum()), "eventos": int(y[treino].sum()), "taxa_de_eventos": float(y[treino].mean()), "anos": [int(amostra["ano"][treino].min()), ULTIMO_ANO_DE_TREINO]},
        "teste": {
            "linhas": int(teste.sum()),
            "eventos": int(y_t.sum()),
            "taxa_de_eventos": float(y_t.mean()),
            "anos": [ULTIMO_ANO_DE_TREINO + 1, int(amostra["ano"].max())],
            "linhas_fora_do_alerta": int(fora.sum()),
            "eventos_fora_do_alerta": int(y_t[fora].sum()),
        },
        "metodos": {},
        "coeficientes": coeficientes,
    }
    for i, nome in enumerate(nomes):
        saida["metodos"][nome] = {
            "rotulo": METODOS[nome],
            "brier": previsao.brier(p_t[nome], y_t),
            "brier_ic": [float(np.percentile(boot[:, i], 2.5)), float(np.percentile(boot[:, i], 97.5))],
            "ganho_sobre_climatologia": previsao.brier_skill(p_t[nome], p_t["climatologia"], y_t),
            "auc": previsao.auc(p_t[nome], y_t),
            "brier_fora_do_alerta": previsao.brier(p_t[nome][fora], y_t[fora]),
            "auc_fora_do_alerta": previsao.auc(p_t[nome][fora], y_t[fora]),
            "alerta": _alerta(p_t[nome], y_t),
            "alerta_fora_do_alerta": _alerta(p_t[nome][fora], y_t[fora]),
            "confiabilidade": previsao.confiabilidade(p_t[nome], y_t, FAIXAS_CONFIABILIDADE),
        }
    # Diferenças de Brier (negativo: o primeiro é melhor), com IC pelo mesmo bootstrap de anos.
    comparacoes = {}
    for a, b in (("modelo", "persistencia_calibrada"), ("modelo", "persistencia"), ("modelo_com_projecao", "persistencia_calibrada"), ("modelo", "modelo_sem_nino"), ("persistencia_calibrada", "climatologia"), ("persistencia_calibrada", "persistencia")):
        dif = boot[:, nomes.index(a)] - boot[:, nomes.index(b)]
        comparacoes[f"{a}_menos_{b}"] = {
            "diferenca": saida["metodos"][a]["brier"] - saida["metodos"][b]["brier"],
            "ic": [float(np.percentile(dif, 2.5)), float(np.percentile(dif, 97.5))],
            "prob_primeiro_melhor": float(np.mean(dif < 0)),
        }
    saida["comparacoes"] = comparacoes
    return saida


def conferir_nino(nino: pd.DataFrame, caixa: pd.Series) -> dict:
    """Compara o índice semanal do CPC com a média da caixa Niño 3.4 calculada aqui a partir do OISST."""
    cpc = nino["sst_nino34"].rename("cpc").reset_index()
    nossa = caixa.rename("caixa").reset_index()
    juntos = pd.merge_asof(nossa.sort_values("data"), cpc.sort_values("data"), on="data", direction="nearest", tolerance=pd.Timedelta(days=3)).dropna()
    dif = juntos["caixa"] - juntos["cpc"]
    return {
        "datas_comparadas": int(len(juntos)),
        "correlacao": float(np.corrcoef(juntos["caixa"], juntos["cpc"])[0, 1]),
        "diferenca_media": float(dif.mean()),
        "diferenca_absoluta_media": float(dif.abs().mean()),
    }


def previsoes(series: list[Serie], nino: pd.DataFrame) -> dict:
    grupos = list(dict.fromkeys(s.grupo for s in series))
    nino_anom = anomalia_do_nino(nino)
    com_cpc = pd.concat([nino_anom, nino["anomalia_cpc"]], axis=1).dropna()
    saida = {
        "nino": {
            "semanas": int(len(nino_anom)),
            "correlacao_com_a_anomalia_do_cpc": float(np.corrcoef(com_cpc["anomalia_nino34"], com_cpc["anomalia_cpc"])[0, 1]),
            "atraso_semanas": ATRASO_NINO_SEMANAS,
        },
        "antecedencias": {},
    }
    for semanas in ANTECEDENCIAS:
        amostra = amostras_de_previsao(series, nino_anom, semanas)
        saida["antecedencias"][str(semanas)] = avaliar_previsao(amostra, grupos)
    return saida


# ---------------------------------------------------------------------------------------------------------------
# 5. Ranking de exposição, com a incerteza do ranking
# ---------------------------------------------------------------------------------------------------------------


def ranking(series: list[Serie], periodo: tuple[int, int] = PERIODOS[1], n_boot: int = 10000) -> dict:
    """Ordena os recifes pela exposição recente e mede a incerteza do posto.

    Exposição = fração de anos com DHW de 4 ou mais, somada à fração de anos com DHW de 8 ou mais (um ano severo
    conta em dobro), no período. Os empates são desfeitos pela média do DHW máximo anual. A incerteza vem de um
    bootstrap em blocos dos anos, com os mesmos anos sorteados para todos os recifes: responde "se a história
    recente tivesse sido outra amostra dos mesmos anos, o posto mudaria?".
    """
    anual = matriz_anual(series)
    recorte = anual.loc[(anual.index >= periodo[0]) & (anual.index <= periodo[1])]
    valores = recorte.to_numpy(float)
    n_anos, n_recifes = valores.shape
    terco = int(np.ceil(n_recifes / 3))

    def nota(v: np.ndarray) -> np.ndarray:
        return np.nanmean(v >= 4, axis=0) + np.nanmean(v >= 8, axis=0) + 1e-3 * np.nanmean(v, axis=0)

    def postos(notas: np.ndarray) -> np.ndarray:
        ordem = np.argsort(-notas, kind="mergesort")
        p = np.empty(len(notas), dtype=int)
        p[ordem] = np.arange(1, len(notas) + 1)
        return p

    observado = nota(valores)
    posto = postos(observado)
    rng = np.random.default_rng(SEMENTE)
    sorteados = np.empty((n_boot, n_recifes), dtype=int)
    for i in range(n_boot):
        sorteados[i] = postos(nota(valores[tendencia.indices_em_blocos(n_anos, BLOCO_ANOS, rng)]))
    linhas = []
    for j, s in enumerate(series):
        linhas.append(
            {
                "slug": s.slug,
                "nome": s.nome,
                "grupo": s.grupo,
                "posto": int(posto[j]),
                "posto_ic": [int(np.percentile(sorteados[:, j], 5)), int(np.percentile(sorteados[:, j], 95))],
                "prob_terco_mais_exposto": float(np.mean(sorteados[:, j] <= terco)),
                "nota": float(observado[j]),
                "anos_dhw4": int(np.nansum(valores[:, j] >= 4)),
                "anos_dhw8": int(np.nansum(valores[:, j] >= 8)),
                "dhw_maximo_medio": float(np.nanmean(valores[:, j])),
                "dhw_maximo": float(np.nanmax(valores[:, j])),
            }
        )
    linhas.sort(key=lambda linha: linha["posto"])
    prob = np.array([linha["prob_terco_mais_exposto"] for linha in linhas])
    return {
        "periodo": list(periodo),
        "anos": int(n_anos),
        "tamanho_do_terco": terco,
        "por_recife": linhas,
        "certos_no_terco": int((prob >= 0.9).sum()),
        "certos_fora_do_terco": int((prob <= 0.1).sum()),
        "indefinidos": int(((prob > 0.1) & (prob < 0.9)).sum()),
    }


# ---------------------------------------------------------------------------------------------------------------
# 6. Validação contra branqueamento observado
# ---------------------------------------------------------------------------------------------------------------

FAIXAS_DHW = [("0", 0.0, 1e-9), ("0 a 4", 1e-9, 4.0), ("4 a 8", 4.0, 8.0), ("8 ou mais", 8.0, np.inf)]


def validar_com_branqueamento(series: list[Serie], branqueamento: pd.DataFrame, n_boot: int = 2000) -> dict:
    """O estresse térmico do satélite separa os levantamentos com e sem branqueamento?

    Cada linha é um conjunto de levantamentos de campo a até 100 km do ponto do recife, numa data e de uma fonte.
    O estresse é o maior DHW oficial do ponto do recife nas 12 leituras semanais até a data do levantamento.
    """
    por_slug = {s.slug: s for s in series}
    partes = []
    for slug, grupo in branqueamento.groupby("slug"):
        s = por_slug[slug]
        posicao = np.searchsorted(s.datas, grupo["data"].to_numpy().astype("datetime64[D]"), side="right") - 1
        dentro = posicao >= 11
        grupo = grupo[dentro].copy()
        estresse = []
        for p in posicao[dentro]:
            janela = s.dhw_noaa[p - 11 : p + 1]
            estresse.append(np.nanmax(janela) if np.isfinite(janela).sum() >= 10 else np.nan)
        grupo["dhw_recente"] = estresse
        partes.append(grupo)
    dados = pd.concat(partes, ignore_index=True).dropna(subset=["dhw_recente"])
    dados["ano"] = dados["data"].dt.year
    grupo_boot = (dados["slug"] + "_" + dados["ano"].astype(str)).to_numpy()
    estresse = dados["dhw_recente"].to_numpy()
    percentual = dados["percentual_medio"].to_numpy()
    saida = {
        "linhas": int(len(dados)),
        "levantamentos": int(dados["levantamentos"].sum()),
        "recifes": int(dados["slug"].nunique()),
        "recifes_ano": int(len(np.unique(grupo_boot))),
        "anos": [int(dados["ano"].min()), int(dados["ano"].max())],
        "por_fonte": dados.groupby("fonte")["levantamentos"].sum().astype(int).to_dict(),
        "por_recife": dados.groupby("slug")["levantamentos"].sum().astype(int).to_dict(),
        "por_faixa": [],
        "limiares": {},
    }
    for nome, a, b in FAIXAS_DHW:
        m = (estresse >= a) & (estresse < b)
        saida["por_faixa"].append(
            {
                "faixa_dhw": nome,
                "linhas": int(m.sum()),
                "percentual_medio": float(percentual[m].mean()) if m.any() else None,
                "fracao_com_10_ou_mais": float((percentual[m] >= 10).mean()) if m.any() else None,
                "fracao_com_30_ou_mais": float((percentual[m] >= 30).mean()) if m.any() else None,
            }
        )
    for corte in (10, 30):
        evento = (percentual >= corte).astype(float)
        alerta = estresse >= dhw.LIMIAR_ALERTA_1
        boot = previsao.bootstrap_por_grupo(grupo_boot, lambda idx, evento=evento: previsao.auc(estresse[idx], evento[idx]), n_boot=n_boot, semente=SEMENTE)
        boot = boot[np.isfinite(boot)]
        saida["limiares"][str(corte)] = {
            "com_branqueamento": int(evento.sum()),
            "auc": previsao.auc(estresse, evento),
            "auc_ic": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "sensibilidade_dhw4": float(alerta[evento == 1].mean()),
            "especificidade_dhw4": float((~alerta)[evento == 0].mean()),
            "branqueamento_sem_estresse": float((estresse[evento == 1] == 0).mean()),
        }
    # Só o Reef Check, que usa o mesmo protocolo em todo lugar e também registra quando não há branqueamento.
    rc = (dados["fonte"] == "Reef_Check").to_numpy()
    if rc.sum() > 50 and 0 < (percentual[rc] >= 10).sum() < rc.sum():
        e_rc, p_rc = estresse[rc], (percentual[rc] >= 10).astype(float)
        boot = previsao.bootstrap_por_grupo(grupo_boot[rc], lambda idx: previsao.auc(e_rc[idx], p_rc[idx]), n_boot=n_boot, semente=SEMENTE)
        boot = boot[np.isfinite(boot)]
        saida["so_reef_check"] = {
            "linhas": int(rc.sum()),
            "com_10_ou_mais": int(p_rc.sum()),
            "auc_10": previsao.auc(e_rc, p_rc),
            "auc_10_ic": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        }
    # Recife a recife: o que o campo viu e o que o satélite marcou (só onde há pelo menos 10 linhas).
    saida["resumo_por_recife"] = []
    for slug, g in dados.groupby("slug"):
        if len(g) < 10:
            continue
        com = g["percentual_medio"] >= 10
        saida["resumo_por_recife"].append(
            {
                "slug": slug,
                "nome": por_slug[slug].nome,
                "linhas": int(len(g)),
                "anos_com_levantamento": int(g["ano"].nunique()),
                "com_10_ou_mais": int(com.sum()),
                "dessas_com_dhw_abaixo_de_4": int((com & (g["dhw_recente"] < dhw.LIMIAR_ALERTA_1)).sum()),
                "dhw_maximo_nos_levantamentos": float(g["dhw_recente"].max()),
            }
        )
    return saida


# ---------------------------------------------------------------------------------------------------------------
# Arquivo reutilizável
# ---------------------------------------------------------------------------------------------------------------


def tabela_de_exposicao(base: Base, tend: dict, rank: dict) -> pd.DataFrame:
    """Uma linha por recife: coordenadas, anos de estresse por década, tendência, intervalo de retorno e posto."""
    por_rank = {linha["slug"]: linha for linha in rank["por_recife"]}
    t4 = {linha["slug"]: linha for linha in tend["dhw4"]["por_recife"]}
    t8 = {linha["slug"]: linha for linha in tend["dhw8"]["por_recife"]}
    linhas = []
    for slug, r in base.recifes.iterrows():
        a, b, k = t4[slug], t8[slug], por_rank[slug]
        linha = {
            "recife": r["nome"],
            "slug": slug,
            "regiao": r["regiao"],
            "grupo": r["grupo"],
            "lat_referencia": r["lat"],
            "lon_referencia": r["lon"],
            "lat_pixel_noaa": r["lat_crw"],
            "lon_pixel_noaa": r["lon_crw"],
            "mmm_noaa_c": r["mmm_noaa"],
            "anos_observados": a["anos_observados"],
        }
        for (ini, fim), n4, n8 in zip(DECADAS, a["por_decada"], b["por_decada"]):
            linha[f"anos_dhw4_{ini}_{fim}"] = n4
            linha[f"anos_dhw8_{ini}_{fim}"] = n8
        linha["anos_dhw4_depois_de_2024"] = a["depois_de_2024"]
        linha["anos_dhw8_depois_de_2024"] = b["depois_de_2024"]
        linha["primeiro_ano_dhw4"] = a["primeiro_ano"]
        linha["primeiro_ano_dhw8"] = b["primeiro_ano"]
        for chave, t in (("dhw4", a), ("dhw8", b)):
            linha[f"tendencia_{chave}_log_chances_por_decada"] = round(t["inclinacao"], 3)
            linha[f"tendencia_{chave}_inf"] = None if np.isnan(t["ic"][0]) else round(t["ic"][0], 3)
            linha[f"tendencia_{chave}_sup"] = None if np.isnan(t["ic"][1]) else round(t["ic"][1], 3)
            linha[f"tendencia_{chave}_p"] = round(t["p"], 4)
            linha[f"tendencia_{chave}_p_bh"] = None if t["p_bh"] is None else round(t["p_bh"], 4)
            for nome in ("antes", "depois"):
                ret = t[f"retorno_{nome}"]
                periodo = "1985_2004" if nome == "antes" else "2005_2024"
                linha[f"retorno_{chave}_{periodo}_anos"] = None if np.isinf(ret["retorno"]) else round(ret["retorno"], 1)
                linha[f"retorno_{chave}_{periodo}_inf"] = round(ret["retorno_ic"][0], 1)
                linha[f"retorno_{chave}_{periodo}_sup"] = None if np.isinf(ret["retorno_ic"][1]) else round(ret["retorno_ic"][1], 1)
        linha["posto_exposicao_2005_2024"] = k["posto"]
        linha["posto_inf_90"] = k["posto_ic"][0]
        linha["posto_sup_90"] = k["posto_ic"][1]
        linha["prob_terco_mais_exposto"] = round(k["prob_terco_mais_exposto"], 3)
        linha["dhw_maximo_2005_2024"] = round(k["dhw_maximo"], 2)
        linhas.append(linha)
    return pd.DataFrame(linhas).sort_values("posto_exposicao_2005_2024")
