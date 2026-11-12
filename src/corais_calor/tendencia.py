"""Tendência de eventos raros com incerteza honesta.

- modelos lineares generalizados (Poisson com ligação log, binomial com ligação logit) ajustados por mínimos
  quadrados reponderados (IRLS), com penalização ridge opcional para lidar com separação perfeita;
- bootstrap em blocos móveis de anos, que preserva a dependência entre anos vizinhos e, quando os anos são
  reamostrados inteiros, a dependência entre recifes no mesmo ano;
- teste de permutação em blocos para a hipótese de ausência de tendência;
- intervalo de retorno com intervalo de Jeffreys;
- correção para múltiplas comparações (Benjamini-Hochberg e Holm).
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def sigmoide(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35.0, 35.0)))


def ajustar_glm(
    X: np.ndarray,
    y: np.ndarray,
    familia: str,
    ridge: float = 0.0,
    penaliza_intercepto: bool = False,
    pesos: np.ndarray | None = None,
    iteracoes: int = 100,
    tolerancia: float = 1e-9,
) -> np.ndarray:
    """Coeficientes de um GLM por IRLS. `familia` é "poisson" (log) ou "binomial" (logit, y entre 0 e 1).

    A primeira coluna de X deve ser a constante. `ridge` soma ridge * beta² à log-verossimilhança negativa
    (sem penalizar a constante, a menos que `penaliza_intercepto`).
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = X.shape
    w_obs = np.ones(n) if pesos is None else np.asarray(pesos, dtype=float)
    penal = np.full(p, 2.0 * ridge)
    if not penaliza_intercepto:
        penal[0] = 0.0
    beta = np.zeros(p)
    if familia == "poisson":
        beta[0] = np.log(max(np.average(y, weights=w_obs), 1e-8))
    elif familia == "binomial":
        media = min(max(np.average(y, weights=w_obs), 1e-6), 1 - 1e-6)
        beta[0] = np.log(media / (1 - media))
    else:
        raise ValueError(f"família desconhecida: {familia}")

    def media_e_perda(b: np.ndarray) -> tuple[np.ndarray, float]:
        """Média prevista e log-verossimilhança negativa penalizada (o que o ajuste minimiza)."""
        eta = X @ b
        if familia == "poisson":
            eta = np.clip(eta, -30.0, 30.0)
            mu = np.exp(eta)
            logver = y * eta - mu
        else:
            mu = sigmoide(eta)
            logver = y * eta - np.logaddexp(0.0, eta)
        return mu, float(-(w_obs * logver).sum() + 0.5 * (penal * b * b).sum())

    mu, perda = media_e_perda(beta)
    for _ in range(iteracoes):
        variancia = mu if familia == "poisson" else mu * (1.0 - mu)
        w = w_obs * np.maximum(variancia, 1e-10)
        gradiente = X.T @ (w_obs * (y - mu)) - penal * beta
        hessiana = (X * w[:, None]).T @ X + np.diag(penal) + 1e-10 * np.eye(p)
        passo = np.linalg.solve(hessiana, gradiente)
        # O passo de Newton pode passar do ponto quando os dados são quase separáveis: corta pela metade até
        # a perda cair.
        for _ in range(40):
            mu_novo, perda_nova = media_e_perda(beta + passo)
            if perda_nova <= perda + 1e-12:
                break
            passo = passo / 2.0
        else:
            break
        beta = beta + passo
        melhora = perda - perda_nova
        mu, perda = mu_novo, perda_nova
        if np.abs(passo).max() < tolerancia or melhora < 1e-12:
            break
    return beta


def indices_em_blocos(n: int, bloco: int, rng: np.random.Generator) -> np.ndarray:
    """Índices de um bootstrap em blocos móveis: blocos de `bloco` posições consecutivas, sorteados com reposição."""
    bloco = max(1, min(bloco, n))
    n_blocos = int(np.ceil(n / bloco))
    inicios = rng.integers(0, n - bloco + 1, size=n_blocos)
    return (inicios[:, None] + np.arange(bloco)[None, :]).ravel()[:n]


def permutacao_em_blocos(n: int, bloco: int, rng: np.random.Generator) -> np.ndarray:
    """Permutação que embaralha a ordem de blocos consecutivos, com início circular sorteado.

    Mantém os vizinhos de cada ano juntos (a autocorrelação de curto prazo) e destrói a relação com o tempo.
    """
    desloc = int(rng.integers(0, n))
    ordem = np.roll(np.arange(n), -desloc)
    blocos = [ordem[i : i + bloco] for i in range(0, n, bloco)]
    return np.concatenate([blocos[i] for i in rng.permutation(len(blocos))])


def logistica_em_lote(
    x: np.ndarray, y: np.ndarray, ridge: float = 0.0, pesos: np.ndarray | None = None, iteracoes: int = 80, com_constante: bool = False
):
    """Inclinação de muitas regressões logísticas simples de uma vez (uma por linha de `x` e `y`).

    É o mesmo ajuste de `ajustar_glm` com constante e uma variável (ridge só na inclinação), com o passo de
    Newton e o corte do passo escritos para todas as linhas ao mesmo tempo. `y` pode ser uma fração, com `pesos`
    dizendo de quantas observações ela veio. Linha sem evento, ou só com evento, devolve inclinação zero. Com
    `com_constante`, devolve o par (constantes, inclinações).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    q = np.ones_like(y) if pesos is None else np.asarray(pesos, dtype=float)
    media = np.clip((q * y).sum(axis=1) / q.sum(axis=1), 1e-6, 1 - 1e-6)
    a = np.log(media / (1 - media))
    b = np.zeros(len(y))

    def perda(a_: np.ndarray, b_: np.ndarray) -> np.ndarray:
        eta = a_[:, None] + b_[:, None] * x
        return -(q * (y * eta - np.logaddexp(0.0, eta))).sum(axis=1) + ridge * b_ * b_

    atual = perda(a, b)
    for _ in range(iteracoes):
        mu = sigmoide(a[:, None] + b[:, None] * x)
        w = q * np.maximum(mu * (1 - mu), 1e-10)
        g0 = (q * (y - mu)).sum(axis=1)
        g1 = (q * (y - mu) * x).sum(axis=1) - 2 * ridge * b
        h00 = w.sum(axis=1) + 1e-10
        h01 = (w * x).sum(axis=1)
        h11 = (w * x * x).sum(axis=1) + 2 * ridge + 1e-10
        det = h00 * h11 - h01 * h01
        da = (h11 * g0 - h01 * g1) / det
        db = (h00 * g1 - h01 * g0) / det
        fator = np.ones(len(y))
        for _ in range(40):
            nova = perda(a + fator * da, b + fator * db)
            ruim = nova > atual + 1e-12
            if not ruim.any():
                break
            fator = np.where(ruim, fator / 2.0, fator)
        fator = np.where(nova > atual + 1e-12, 0.0, fator)
        a, b = a + fator * da, b + fator * db
        melhora = atual - perda(a, b)
        atual = atual - melhora
        if melhora.max() < 1e-12:
            break
    sem_variacao = ((q * y).sum(axis=1) == 0) | ((q * y).sum(axis=1) == q.sum(axis=1))
    b = np.where(sem_variacao, 0.0, b)
    return (a, b) if com_constante else b


def tendencia_logistica(
    anos: np.ndarray,
    evento: np.ndarray,
    ano_central: float = 2005.0,
    ridge: float = 0.05,
    bloco: int = 4,
    n_boot: int = 1000,
    n_perm: int = 2000,
    semente: int = 0,
) -> dict:
    """Tendência da probabilidade anual de um evento (0 ou 1 por ano) num recife.

    Ajusta logit P = a + b * (ano - ano_central) / 10. Devolve a inclinação b (log da razão de chances por
    década), o intervalo de 95% por bootstrap em blocos de anos e o valor-p bilateral por permutação em blocos.
    O ridge fraco na inclinação evita inclinação infinita quando todos os eventos estão no fim da série.
    """
    anos = np.asarray(anos, dtype=float)
    evento = np.asarray(evento, dtype=float)
    n = len(anos)
    x = (anos - ano_central) / 10.0
    X = np.column_stack([np.ones(n), x])
    if evento.sum() == 0 or evento.sum() == n:
        return {"inclinacao": 0.0, "ic": [float("nan"), float("nan")], "p": 1.0, "eventos": int(evento.sum())}
    rng = np.random.default_rng(semente)
    b = float(ajustar_glm(X, evento, "binomial", ridge=ridge)[1])
    # As réplicas são ajustadas todas de uma vez (um ajuste por linha), o que é centenas de vezes mais rápido.
    sorteios = np.array([indices_em_blocos(n, bloco, rng) for _ in range(n_boot)])
    boot = logistica_em_lote(x[sorteios], evento[sorteios], ridge)
    permutacoes = np.array([permutacao_em_blocos(n, bloco, rng) for _ in range(n_perm)])
    perm = logistica_em_lote(np.broadcast_to(x, (n_perm, n)), evento[permutacoes], ridge)
    p = (1 + np.sum(np.abs(perm) >= abs(b) - 1e-9)) / (n_perm + 1)
    return {
        "inclinacao": b,
        "ic": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        "p": float(p),
        "eventos": int(evento.sum()),
    }


def tendencia_da_contagem(
    anos: np.ndarray,
    eventos: np.ndarray,
    ano_central: float = 2005.0,
    bloco: int = 4,
    n_boot: int = 2000,
    semente: int = 0,
) -> dict:
    """Tendência do número de recifes em estresse por ano, com todos os recifes juntos.

    `eventos` é a matriz (anos, recifes) de 0 e 1 (NaN onde não há dado). Ajusta uma regressão binomial da fração
    de recifes atingidos sobre o ano e uma de Poisson da contagem. O intervalo vem de um bootstrap que reamostra
    anos inteiros em blocos: como a linha do ano leva todos os recifes juntos, a dependência entre recifes no mesmo
    ano (um El Niño atinge muitos de uma vez) fica preservada, e a superdispersão entra no intervalo.
    """
    anos = np.asarray(anos, dtype=float)
    eventos = np.asarray(eventos, dtype=float)
    n = len(anos)
    atingidos = np.nansum(eventos, axis=1)
    observados = np.isfinite(eventos).sum(axis=1).astype(float)
    x = (anos - ano_central) / 10.0
    X = np.column_stack([np.ones(n), x])

    fracao = atingidos / observados
    b_bin = ajustar_glm(X, fracao, "binomial", pesos=observados)
    b_poi = ajustar_glm(X, atingidos, "poisson")
    rng = np.random.default_rng(semente)
    sorteios = np.array([indices_em_blocos(n, bloco, rng) for _ in range(n_boot)])
    # Binomial: todas as réplicas de uma vez. Poisson: uma a uma, nas 300 primeiras (é só uma conferência).
    boot_bin = np.column_stack(logistica_em_lote(x[sorteios], fracao[sorteios], pesos=observados[sorteios], com_constante=True))
    boot_poi = np.array([ajustar_glm(X[idx], atingidos[idx], "poisson") for idx in sorteios[:300]])
    curva = sigmoide(X @ b_bin)
    curvas_boot = sigmoide(boot_bin @ X.T)
    # Superdispersão: variância observada da contagem sobre a variância binomial esperada.
    esperado = observados * curva
    pearson = np.sum((atingidos - esperado) ** 2 / np.maximum(observados * curva * (1 - curva), 1e-9)) / (n - 2)
    return {
        "razao_de_chances_por_decada": float(np.exp(b_bin[1])),
        "razao_de_chances_ic": [float(np.exp(np.percentile(boot_bin[:, 1], 2.5))), float(np.exp(np.percentile(boot_bin[:, 1], 97.5)))],
        "fator_poisson_por_decada": float(np.exp(b_poi[1])),
        "fator_poisson_ic": [float(np.exp(np.percentile(boot_poi[:, 1], 2.5))), float(np.exp(np.percentile(boot_poi[:, 1], 97.5)))],
        "prob_inclinacao_positiva": float(np.mean(boot_bin[:, 1] > 0)),
        "superdispersao": float(pearson),
        "curva": curva.tolist(),
        "curva_inf": np.percentile(curvas_boot, 2.5, axis=0).tolist(),
        "curva_sup": np.percentile(curvas_boot, 97.5, axis=0).tolist(),
    }


def intervalo_de_retorno(n_eventos: int, n_anos: int, confianca: float = 0.95) -> dict:
    """Intervalo de retorno (anos entre eventos) e a sua faixa, pelo intervalo de Jeffreys da probabilidade anual.

    O intervalo de retorno é 1 / p. Sem nenhum evento, a estimativa pontual é infinita e o limite inferior do
    intervalo diz o que os dados ainda permitem afirmar ("pelo menos tantos anos").
    """
    alfa = 1.0 - confianca
    p = n_eventos / n_anos if n_anos else float("nan")
    p_inf = 0.0 if n_eventos == 0 else float(stats.beta.ppf(alfa / 2, n_eventos + 0.5, n_anos - n_eventos + 0.5))
    p_sup = 1.0 if n_eventos == n_anos else float(stats.beta.ppf(1 - alfa / 2, n_eventos + 0.5, n_anos - n_eventos + 0.5))
    return {
        "eventos": int(n_eventos),
        "anos": int(n_anos),
        "prob_anual": p,
        "prob_anual_ic": [p_inf, p_sup],
        "retorno": (1.0 / p) if p > 0 else float("inf"),
        "retorno_ic": [1.0 / p_sup, (1.0 / p_inf) if p_inf > 0 else float("inf")],
    }


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """Valores-p ajustados pelo método de Benjamini-Hochberg, que controla a taxa de descobertas falsas."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    ordem = np.argsort(p)
    ajustado = p[ordem] * m / np.arange(1, m + 1)
    ajustado = np.minimum.accumulate(ajustado[::-1])[::-1]
    saida = np.empty(m)
    saida[ordem] = np.minimum(ajustado, 1.0)
    return saida


def holm(p: np.ndarray) -> np.ndarray:
    """Valores-p ajustados pelo método de Holm, que controla a chance de qualquer falso positivo."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    ordem = np.argsort(p)
    ajustado = p[ordem] * (m - np.arange(m))
    ajustado = np.maximum.accumulate(ajustado)
    saida = np.empty(m)
    saida[ordem] = np.minimum(ajustado, 1.0)
    return saida
