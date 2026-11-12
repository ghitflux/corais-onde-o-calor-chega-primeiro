"""Ondas de calor marinhas pela definição de Hobday et al. (2016).

Uma onda de calor marinha é um período de cinco dias ou mais em que a temperatura fica acima do percentil 90 do
dia do ano, medido num período de referência de 30 anos. Os detalhes seguem a implementação de referência da
definição (o módulo `marineHeatWaves`, de E. Oliver):

- o percentil e a média de cada dia do ano juntam todos os valores a até 5 dias de distância (janela de 11 dias)
  em todos os anos da referência;
- as duas curvas são alisadas por média móvel circular de 31 dias;
- 29 de fevereiro fica fora da conta e recebe a média de 28 de fevereiro e 1º de março;
- eventos separados por 2 dias ou menos são unidos.

A intensidade é medida em relação à média do dia do ano (a climatologia sazonal), não ao limiar.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from corais_calor.dhw import ano_e_mes

PERCENTIL = 90.0
MEIA_JANELA = 5
LARGURA_ALISAMENTO = 31
DURACAO_MINIMA = 5
LACUNA_MAXIMA = 2
REFERENCIA = (1983, 2012)  # 30 anos


def dia_do_ano_365(datas: np.ndarray) -> np.ndarray:
    """Dia do ano num calendário de 365 dias (0 a 364). 29 de fevereiro devolve -1."""
    datas = np.asarray(datas, dtype="datetime64[D]")
    anos, meses = ano_e_mes(datas)
    inicio = (anos - 1970).astype("datetime64[Y]").astype("datetime64[D]")
    dia = (datas - inicio).astype(int)  # 0 = 1º de janeiro
    bissexto = ((anos % 4 == 0) & (anos % 100 != 0)) | (anos % 400 == 0)
    e_29_fev = bissexto & (dia == 59)
    dia = np.where(bissexto & (dia > 59), dia - 1, dia)
    return np.where(e_29_fev, -1, dia)


def media_movel_circular(valores: np.ndarray, largura: int) -> np.ndarray:
    """Média móvel centrada em que o fim do ano emenda no começo."""
    meia = largura // 2
    estendido = np.concatenate([valores[-meia:], valores, valores[:meia]])
    return np.convolve(estendido, np.ones(largura) / largura, mode="valid")


def climatologia_diaria(
    datas: np.ndarray,
    sst: np.ndarray,
    referencia: tuple[int, int] = REFERENCIA,
    percentil: float = PERCENTIL,
    meia_janela: int = MEIA_JANELA,
    largura_alisamento: int = LARGURA_ALISAMENTO,
) -> tuple[np.ndarray, np.ndarray]:
    """Média e limiar (percentil) de cada um dos 365 dias do ano, calculados só com os anos da referência."""
    sst = np.asarray(sst, dtype=float)
    anos, _ = ano_e_mes(datas)
    dia = dia_do_ano_365(datas)
    usa = (anos >= referencia[0]) & (anos <= referencia[1]) & (dia >= 0) & np.isfinite(sst)
    dia_ref, sst_ref = dia[usa], sst[usa]
    media = np.full(365, np.nan)
    limiar = np.full(365, np.nan)
    for d in range(365):
        distancia = np.abs(dia_ref - d)
        distancia = np.minimum(distancia, 365 - distancia)  # a janela dá a volta no ano
        valores = sst_ref[distancia <= meia_janela]
        if valores.size:
            media[d] = valores.mean()
            limiar[d] = np.percentile(valores, percentil)
    if largura_alisamento > 1:
        media = media_movel_circular(media, largura_alisamento)
        limiar = media_movel_circular(limiar, largura_alisamento)
    return media, limiar


def espalhar_no_tempo(curva_365: np.ndarray, datas: np.ndarray) -> np.ndarray:
    """Leva uma curva de 365 dias para cada data da série; 29 de fevereiro recebe a média dos dois vizinhos."""
    dia = dia_do_ano_365(datas)
    valores = curva_365[np.where(dia >= 0, dia, 58)]
    return np.where(dia >= 0, valores, 0.5 * (curva_365[58] + curva_365[59]))


@dataclass(frozen=True)
class Onda:
    inicio: int  # índice do primeiro dia na série
    fim: int  # índice do último dia (inclusive)
    duracao: int
    intensidade_maxima: float
    intensidade_media: float
    intensidade_acumulada: float  # °C-dia


def blocos_verdadeiros(mascara: np.ndarray) -> list[tuple[int, int]]:
    """Lista de (início, fim inclusive) de cada sequência de valores verdadeiros."""
    m = np.concatenate([[False], np.asarray(mascara, dtype=bool), [False]])
    mudanca = np.flatnonzero(m[1:] != m[:-1])
    return [(int(a), int(b) - 1) for a, b in zip(mudanca[::2], mudanca[1::2])]


def detectar(
    datas: np.ndarray,
    sst: np.ndarray,
    referencia: tuple[int, int] = REFERENCIA,
    percentil: float = PERCENTIL,
    duracao_minima: int = DURACAO_MINIMA,
    lacuna_maxima: int = LACUNA_MAXIMA,
    meia_janela: int = MEIA_JANELA,
    largura_alisamento: int = LARGURA_ALISAMENTO,
) -> list[Onda]:
    """Ondas de calor marinhas da série, em ordem cronológica."""
    sst = np.asarray(sst, dtype=float)
    media, limiar = climatologia_diaria(datas, sst, referencia, percentil, meia_janela, largura_alisamento)
    media_t = espalhar_no_tempo(media, datas)
    limiar_t = espalhar_no_tempo(limiar, datas)
    acima = np.isfinite(sst) & (sst > limiar_t)
    eventos = [(a, b) for a, b in blocos_verdadeiros(acima) if b - a + 1 >= duracao_minima]
    unidos: list[tuple[int, int]] = []
    for a, b in eventos:
        if unidos and a - unidos[-1][1] - 1 <= lacuna_maxima:
            unidos[-1] = (unidos[-1][0], b)
        else:
            unidos.append((a, b))
    ondas = []
    for a, b in unidos:
        anomalia = sst[a : b + 1] - media_t[a : b + 1]
        ondas.append(
            Onda(a, b, b - a + 1, float(np.nanmax(anomalia)), float(np.nanmean(anomalia)), float(np.nansum(anomalia)))
        )
    return ondas


def resumo_por_periodo(datas: np.ndarray, ondas: list[Onda], periodos: list[tuple[int, int]]) -> list[dict]:
    """Frequência, duração e intensidade das ondas em cada período (anos civis, pelo dia de início)."""
    anos, _ = ano_e_mes(datas)
    saida = []
    for inicio, fim in periodos:
        anos_cobertos = np.unique(anos[(anos >= inicio) & (anos <= fim)]).size
        do_periodo = [o for o in ondas if inicio <= anos[o.inicio] <= fim]
        dias = sum(o.duracao for o in do_periodo)
        saida.append(
            {
                "periodo": f"{inicio}-{fim}",
                "anos": int(anos_cobertos),
                "eventos_por_ano": len(do_periodo) / anos_cobertos if anos_cobertos else float("nan"),
                "dias_por_ano": dias / anos_cobertos if anos_cobertos else float("nan"),
                "duracao_media": float(np.mean([o.duracao for o in do_periodo])) if do_periodo else 0.0,
                "intensidade_maxima_media": float(np.mean([o.intensidade_maxima for o in do_periodo])) if do_periodo else 0.0,
                "intensidade_acumulada_por_ano": sum(o.intensidade_acumulada for o in do_periodo) / anos_cobertos
                if anos_cobertos
                else float("nan"),
            }
        )
    return saida


def dias_em_onda_por_ano(datas: np.ndarray, ondas: list[Onda]) -> tuple[np.ndarray, np.ndarray]:
    """Número de dias em onda de calor em cada ano civil."""
    anos, _ = ano_e_mes(datas)
    em_onda = np.zeros(len(anos), dtype=bool)
    for o in ondas:
        em_onda[o.inicio : o.fim + 1] = True
    unicos = np.unique(anos)
    return unicos, np.array([int(em_onda[anos == a].sum()) for a in unicos])
