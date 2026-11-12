"""Degree Heating Week (DHW) reimplementado a partir da temperatura diária.

O DHW é o índice de estresse térmico acumulado da NOAA Coral Reef Watch (Liu et al. 2014; Skirving et al. 2020):

1. climatologia mensal: a média de cada mês do calendário em 1985-2012, recentrada pela tendência linear para o
   meio do período de referência (1988,286), que é 1985-1990 mais 1993;
2. MMM (maximum monthly mean): a média do mês mais quente dessa climatologia;
3. HotSpot do dia: temperatura do dia menos o MMM;
4. DHW do dia: soma, nos 84 dias (12 semanas) que terminam nele, dos HotSpots iguais ou maiores que 1 °C,
   dividida por 7. A unidade é °C-semana.

Todas as funções recebem vetores NumPy; as datas são `datetime64[D]`.
"""

from __future__ import annotations

import numpy as np

ANO_INICIAL_CLIMA = 1985
ANO_FINAL_CLIMA = 2012
CENTRO_DA_REFERENCIA = 1988.286  # meio de 1985-1990 mais 1993, como na metodologia da NOAA
JANELA_DIAS = 84
LIMIAR_HOTSPOT = 1.0
LIMIAR_ALERTA_1 = 4.0  # °C-semana: risco de branqueamento no recife inteiro
LIMIAR_ALERTA_2 = 8.0  # °C-semana: branqueamento com mortalidade


def ano_e_mes(datas: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ano e mês (1 a 12) de cada data."""
    datas = np.asarray(datas, dtype="datetime64[D]")
    meses_desde_1970 = datas.astype("datetime64[M]").astype(int)
    return 1970 + meses_desde_1970 // 12, meses_desde_1970 % 12 + 1


def medias_mensais(datas: np.ndarray, sst: np.ndarray, ano_inicial: int, ano_final: int) -> np.ndarray:
    """Matriz (anos, 12) com a média de cada mês; NaN onde o mês não tem dado."""
    anos, meses = ano_e_mes(datas)
    sst = np.asarray(sst, dtype=float)
    n_anos = ano_final - ano_inicial + 1
    soma = np.zeros((n_anos, 12))
    conta = np.zeros((n_anos, 12))
    valido = (anos >= ano_inicial) & (anos <= ano_final) & np.isfinite(sst)
    np.add.at(soma, (anos[valido] - ano_inicial, meses[valido] - 1), sst[valido])
    np.add.at(conta, (anos[valido] - ano_inicial, meses[valido] - 1), 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(conta > 0, soma / conta, np.nan)


def climatologia_mensal(
    datas: np.ndarray,
    sst: np.ndarray,
    ano_inicial: int = ANO_INICIAL_CLIMA,
    ano_final: int = ANO_FINAL_CLIMA,
    centro: float | None = CENTRO_DA_REFERENCIA,
) -> np.ndarray:
    """Média de cada mês do calendário (12 valores), recentrada pela tendência linear.

    Para cada mês, ajusta uma reta às médias daquele mês ao longo dos anos e lê a reta em `centro`. Como a reta de
    mínimos quadrados passa pela média no meio do período, isso equivale a tirar da média simples a tendência
    acumulada entre o meio do período e `centro`. Com `centro=None`, devolve a média simples.
    """
    medias = medias_mensais(datas, sst, ano_inicial, ano_final)
    # Anos inteiros, como na NOAA: o meio de 1985-2012 é 1998,5 e o de (1985-1990, 1993) é 1988,286.
    anos = np.arange(ano_inicial, ano_final + 1, dtype=float)
    clima = np.full(12, np.nan)
    for m in range(12):
        y = medias[:, m]
        ok = np.isfinite(y)
        if ok.sum() < 2:
            continue
        if centro is None:
            clima[m] = y[ok].mean()
            continue
        inclinacao, intercepto = np.polyfit(anos[ok], y[ok], 1)
        clima[m] = intercepto + inclinacao * centro
    return clima


def mmm(clima_mensal: np.ndarray) -> float:
    """Maximum monthly mean: a média do mês mais quente da climatologia."""
    return float(np.nanmax(clima_mensal))


def hotspot(sst: np.ndarray, valor_mmm: float) -> np.ndarray:
    """Quanto a temperatura do dia passa do MMM (zero quando não passa)."""
    return np.maximum(np.asarray(sst, dtype=float) - valor_mmm, 0.0)


def dhw(
    sst: np.ndarray, valor_mmm: float, janela: int = JANELA_DIAS, limiar: float = LIMIAR_HOTSPOT, passo_dias: int = 1
) -> np.ndarray:
    """DHW em °C-semana. Os primeiros `janela - 1` valores usam a janela parcial disponível.

    Com a série diária, a janela é de 84 dias e `passo_dias` é 1 (o produto atual da NOAA). Com uma temperatura a
    cada 7 dias, use `janela=12` e `passo_dias=7`: cada valor representa a semana inteira, uma aproximação que
    lembra o produto original, calculado com duas temperaturas por semana.

    Dia sem temperatura (NaN) conta como HotSpot zero.
    """
    hs = hotspot(sst, valor_mmm)
    conta = np.where(np.isfinite(hs) & (hs >= limiar), hs, 0.0)
    acumulado = np.concatenate([[0.0], np.cumsum(conta)])
    fim = np.arange(1, len(conta) + 1)
    inicio = np.maximum(fim - janela, 0)
    return (acumulado[fim] - acumulado[inicio]) * passo_dias / 7.0


def mes_mais_quente(clima_mensal: np.ndarray) -> int:
    """Mês (1 a 12) do MMM."""
    return int(np.nanargmax(clima_mensal)) + 1


def ano_de_estresse(datas: np.ndarray, mes_pico: int) -> np.ndarray:
    """Ano a que cada dia pertence para contar o estresse de uma estação quente sem cortá-la em duas.

    O ano de estresse é a janela de 12 meses que começa seis meses antes do mês mais quente do recife e leva o
    nome do ano civil em que esse mês cai. Com pico em agosto, vai de fevereiro a janeiro; com pico em março, de
    setembro a agosto (e o verão de 2015-2016 conta como 2016).
    """
    anos, meses = ano_e_mes(datas)
    inicio = (mes_pico + 5) % 12 + 1
    comeco = np.where(meses >= inicio, anos, anos - 1)
    return comeco + (1 if inicio + 6 > 12 else 0)


def maximo_anual(datas: np.ndarray, valores: np.ndarray, mes_pico: int, cobertura_minima: int = 240):
    """Máximo de `valores` em cada ano de estresse. Devolve (anos, máximos); ano com poucos dias fica de fora."""
    rotulo = ano_de_estresse(datas, mes_pico)
    valores = np.asarray(valores, dtype=float)
    anos = np.unique(rotulo)
    maximos, guardados = [], []
    for a in anos:
        v = valores[rotulo == a]
        if np.isfinite(v).sum() < cobertura_minima:
            continue
        guardados.append(int(a))
        maximos.append(float(np.nanmax(v)))
    return np.array(guardados, dtype=int), np.array(maximos, dtype=float)
