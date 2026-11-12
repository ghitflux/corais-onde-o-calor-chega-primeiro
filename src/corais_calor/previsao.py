"""Previsão do alerta de estresse térmico com semanas de antecedência, e as linhas de base.

O alvo: na data t + L semanas, o DHW do recife estará em 4 °C-semana ou mais (alerta nível 1 da NOAA)?

Três jeitos de responder, do mais simples ao menos simples:

- persistência da anomalia: supõe que a anomalia de hoje (em relação à média do dia do ano) continua igual até a
  data-alvo, projeta a temperatura e calcula o DHW que isso daria;
- climatologia: a frequência com que o alerta ocorreu naquele recife e naquela época do ano, no período de treino;
- modelo: regressão logística com a anomalia local, a tendência das últimas semanas, o DHW de hoje, a posição da
  data-alvo na estação e o índice Niño 3.4.

Tudo é avaliado com separação no tempo, por Brier, curva de confiabilidade e AUC.
"""

from __future__ import annotations

import numpy as np

from corais_calor.dhw import JANELA_DIAS, LIMIAR_HOTSPOT
from corais_calor.tendencia import ajustar_glm, sigmoide


def media_movel_passada(valores: np.ndarray, janela: int) -> np.ndarray:
    """Média dos `janela` valores que terminam em cada posição (só olha para trás). NaN no começo."""
    valores = np.asarray(valores, dtype=float)
    acumulado = np.concatenate([[0.0], np.cumsum(valores)])
    saida = np.full(len(valores), np.nan)
    saida[janela - 1 :] = (acumulado[janela:] - acumulado[:-janela]) / janela
    return saida


def ajustar_ciclo_sazonal(dia_do_ano: np.ndarray, valores: np.ndarray, harmonicos: int = 3) -> np.ndarray:
    """Coeficientes de um ciclo anual suave (média mais `harmonicos` pares de seno e cosseno), por mínimos quadrados."""
    return np.linalg.lstsq(_base_sazonal(dia_do_ano, harmonicos), np.asarray(valores, dtype=float), rcond=None)[0]


def ciclo_sazonal(coeficientes: np.ndarray, dia_do_ano: np.ndarray) -> np.ndarray:
    """Valor do ciclo ajustado em cada dia do ano (1 a 366)."""
    return _base_sazonal(dia_do_ano, (len(coeficientes) - 1) // 2) @ coeficientes


def _base_sazonal(dia_do_ano: np.ndarray, harmonicos: int) -> np.ndarray:
    fase = 2 * np.pi * (np.asarray(dia_do_ano, dtype=float) - 1) / 365.25
    colunas = [np.ones_like(fase)]
    for k in range(1, harmonicos + 1):
        colunas += [np.sin(k * fase), np.cos(k * fase)]
    return np.column_stack(colunas)


def dhw_projetado(
    sst: np.ndarray,
    clima: np.ndarray,
    anomalia: np.ndarray,
    valor_mmm: float,
    passos_a_frente: int,
    janela: int = JANELA_DIAS,
    limiar: float = LIMIAR_HOTSPOT,
    passo_dias: int = 1,
    posicoes: np.ndarray | None = None,
) -> np.ndarray:
    """DHW previsto para t + passos_a_frente supondo que a anomalia de t persiste.

    `clima` é o ciclo sazonal já espalhado no tempo e `anomalia` é a anomalia usada em cada instante t. A parte da
    janela que já aconteceu usa a temperatura observada; a parte futura usa clima + anomalia de hoje. Vale para a
    série diária (janela de 84, passo de 1 dia) e para a semanal (janela de 12, passo de 7 dias). Com `posicoes`,
    calcula só nesses instantes de emissão. Posições sem futuro na série ficam NaN.
    """
    n = len(sst)
    hs_obs = np.asarray(sst, dtype=float) - valor_mmm
    conta_obs = np.where(np.isfinite(hs_obs) & (hs_obs >= limiar), hs_obs, 0.0)
    acumulado = np.concatenate([[0.0], np.cumsum(conta_obs)])
    saida = np.full(n, np.nan)
    passado = max(janela - passos_a_frente, 0)  # passos já observados que ainda estarão na janela
    for t in range(n - passos_a_frente) if posicoes is None else posicoes:
        if t >= n - passos_a_frente or not np.isfinite(anomalia[t]):
            continue
        soma = acumulado[t + 1] - acumulado[max(t + 1 - passado, 0)] if passado else 0.0
        inicio_futuro = t + 1 + max(passos_a_frente - janela, 0)
        futuro = clima[inicio_futuro : t + passos_a_frente + 1] + anomalia[t] - valor_mmm
        soma += futuro[futuro >= limiar].sum()
        saida[t] = soma * passo_dias / 7.0
    return saida


def frequencia_por_semana(
    semana_do_ano: np.ndarray, evento: np.ndarray, treino: np.ndarray, meia_largura: int = 2, n_semanas: int = 53
) -> np.ndarray:
    """Climatologia do evento: frequência no treino em cada semana do ano, juntando as semanas vizinhas.

    Devolve a probabilidade para cada observação (de treino ou de teste), sempre calculada só com o treino.
    """
    semana_do_ano = np.asarray(semana_do_ano, dtype=int)
    evento = np.asarray(evento, dtype=float)
    soma = np.zeros(n_semanas)
    conta = np.zeros(n_semanas)
    np.add.at(soma, semana_do_ano[treino], evento[treino])
    np.add.at(conta, semana_do_ano[treino], 1.0)
    freq = np.zeros(n_semanas)
    for s in range(n_semanas):
        vizinhas = [(s + d) % n_semanas for d in range(-meia_largura, meia_largura + 1)]
        total = conta[vizinhas].sum()
        freq[s] = soma[vizinhas].sum() / total if total else 0.0
    return freq[semana_do_ano]


class Logistica:
    """Regressão logística com padronização das variáveis e ridge, ajustada por IRLS."""

    def __init__(self, ridge: float = 1.0):
        self.ridge = ridge
        self.media: np.ndarray | None = None
        self.desvio: np.ndarray | None = None
        self.beta: np.ndarray | None = None

    def _matriz(self, X: np.ndarray) -> np.ndarray:
        Z = (np.asarray(X, dtype=float) - self.media) / self.desvio
        return np.column_stack([np.ones(len(Z)), Z])

    def ajustar(self, X: np.ndarray, y: np.ndarray) -> "Logistica":
        X = np.asarray(X, dtype=float)
        self.media = X.mean(axis=0)
        desvio = X.std(axis=0)
        self.desvio = np.where(desvio > 0, desvio, 1.0)
        self.beta = ajustar_glm(self._matriz(X), y, "binomial", ridge=self.ridge)
        return self

    def prever(self, X: np.ndarray) -> np.ndarray:
        return sigmoide(self._matriz(X) @ self.beta)


def brier(prob: np.ndarray, evento: np.ndarray) -> float:
    """Erro quadrático médio da probabilidade prevista. Zero é perfeito; menor é melhor."""
    return float(np.mean((np.asarray(prob, dtype=float) - np.asarray(evento, dtype=float)) ** 2))


def brier_skill(prob: np.ndarray, referencia: np.ndarray, evento: np.ndarray) -> float:
    """Ganho relativo sobre uma previsão de referência: 1 é perfeito, 0 empata, negativo é pior."""
    b_ref = brier(referencia, evento)
    return float(1.0 - brier(prob, evento) / b_ref) if b_ref > 0 else float("nan")


def auc(prob: np.ndarray, evento: np.ndarray) -> float:
    """Área sob a curva ROC pela estatística de postos (probabilidade de ordenar certo um par)."""
    prob = np.asarray(prob, dtype=float)
    evento = np.asarray(evento).astype(bool)
    n_pos, n_neg = int(evento.sum()), int((~evento).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ordem = np.argsort(prob, kind="mergesort")
    postos = np.empty(len(prob))
    ordenado = prob[ordem]
    # postos médios em caso de empate
    i = 0
    while i < len(prob):
        j = i
        while j + 1 < len(prob) and ordenado[j + 1] == ordenado[i]:
            j += 1
        postos[ordem[i : j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return float((postos[evento].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def confiabilidade(prob: np.ndarray, evento: np.ndarray, cortes: list[float]) -> list[dict]:
    """Curva de confiabilidade: em cada faixa de probabilidade prevista, a frequência observada do evento."""
    prob = np.asarray(prob, dtype=float)
    evento = np.asarray(evento, dtype=float)
    faixa = np.clip(np.searchsorted(cortes, prob, side="right") - 1, 0, len(cortes) - 2)
    saida = []
    for k in range(len(cortes) - 1):
        m = faixa == k
        saida.append(
            {
                "de": cortes[k],
                "ate": cortes[k + 1],
                "n": int(m.sum()),
                "previsto": float(prob[m].mean()) if m.any() else None,
                "observado": float(evento[m].mean()) if m.any() else None,
            }
        )
    return saida


def bootstrap_por_grupo(grupos: np.ndarray, funcao, n_boot: int = 500, semente: int = 0) -> np.ndarray:
    """Bootstrap que reamostra grupos inteiros (aqui, anos) e devolve a estatística de cada réplica.

    `funcao` recebe o vetor de índices das observações da réplica. Reamostrar anos inteiros respeita o fato de que
    as semanas de um mesmo ano, em todos os recifes, não são independentes.
    """
    grupos = np.asarray(grupos)
    unicos = np.unique(grupos)
    posicoes = {g: np.flatnonzero(grupos == g) for g in unicos}
    rng = np.random.default_rng(semente)
    saidas = []
    for _ in range(n_boot):
        sorteio = rng.choice(unicos, size=len(unicos), replace=True)
        saidas.append(funcao(np.concatenate([posicoes[g] for g in sorteio])))
    return np.array(saidas)
