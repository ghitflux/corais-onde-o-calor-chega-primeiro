"""Modelos de contagem, bootstrap em blocos e correções conferidos contra respostas conhecidas."""

import numpy as np
import pytest
from scipy import stats

from corais_calor import tendencia


def test_poisson_so_com_constante_devolve_o_log_da_media():
    y = np.array([0, 2, 1, 5, 3, 1], dtype=float)
    beta = tendencia.ajustar_glm(np.ones((6, 1)), y, "poisson")
    assert beta[0] == pytest.approx(np.log(y.mean()))


def test_logistica_de_dois_grupos_devolve_o_log_da_razao_de_chances():
    # Grupo 0: 2 em 10. Grupo 1: 6 em 10. Razão de chances = (6/4) / (2/8) = 6.
    x = np.repeat([0.0, 1.0], 10)
    y = np.concatenate([np.repeat([1.0, 0.0], [2, 8]), np.repeat([1.0, 0.0], [6, 4])])
    beta = tendencia.ajustar_glm(np.column_stack([np.ones(20), x]), y, "binomial")
    assert beta[0] == pytest.approx(np.log(2 / 8))
    assert beta[1] == pytest.approx(np.log(6.0))


def test_poisson_recupera_tendencia_simulada():
    rng = np.random.default_rng(3)
    x = np.linspace(-2, 2, 4000)
    y = rng.poisson(np.exp(0.5 + 0.4 * x))
    beta = tendencia.ajustar_glm(np.column_stack([np.ones_like(x), x]), y, "poisson")
    assert beta == pytest.approx([0.5, 0.4], abs=0.05)


def test_binomial_com_pesos_equivale_a_repetir_as_linhas():
    X = np.column_stack([np.ones(3), [0.0, 1.0, 2.0]])
    fracao = np.array([0.1, 0.3, 0.6])
    n = np.array([10.0, 20.0, 10.0])
    com_pesos = tendencia.ajustar_glm(X, fracao, "binomial", pesos=n)
    linhas_x, linhas_y = [], []
    for xi, f, ni in zip(X, fracao, n):
        k = int(round(f * ni))
        linhas_x += [xi] * int(ni)
        linhas_y += [1.0] * k + [0.0] * (int(ni) - k)
    repetido = tendencia.ajustar_glm(np.array(linhas_x), np.array(linhas_y), "binomial")
    assert com_pesos == pytest.approx(repetido, abs=1e-6)


def test_ridge_segura_a_separacao_perfeita():
    # Todos os eventos no fim: sem penalização a inclinação iria para o infinito.
    x = np.linspace(-2, 2, 40)
    y = (x > 1.5).astype(float)
    beta = tendencia.ajustar_glm(np.column_stack([np.ones(40), x]), y, "binomial", ridge=0.05)
    assert np.isfinite(beta).all() and 0 < beta[1] < 20


def test_ajuste_nao_diverge_com_evento_raro_e_quase_separavel():
    # Caso que derrubou a primeira versão do ajuste: evento raro (2%), variável muito assimétrica e quase
    # separável. O passo de Newton sem controle passava do ponto e terminava com a inclinação de sinal trocado.
    rng = np.random.default_rng(11)
    x = np.where(rng.random(5000) < 0.03, rng.uniform(3, 20, 5000), 0.0)
    y = ((x + rng.normal(0, 0.8, 5000)) > 4).astype(float)
    X = np.column_stack([np.ones(5000), (x - x.mean()) / x.std()])
    beta = tendencia.ajustar_glm(X, y, "binomial", ridge=0.01)
    previsto = tendencia.sigmoide(X @ beta)
    assert beta[1] > 0
    assert previsto[y == 1].mean() > 0.7 and previsto[y == 0].mean() < 0.02


def test_logistica_em_lote_da_o_mesmo_que_o_ajuste_um_a_um():
    rng = np.random.default_rng(4)
    x = np.linspace(-2, 2, 40)
    y = (rng.random((25, 40)) < tendencia.sigmoide(-1.5 + 0.8 * x)).astype(float)
    y[0] = 0.0  # linha sem evento
    y[1] = (x > 1.5).astype(float)  # separação perfeita
    em_lote = tendencia.logistica_em_lote(np.broadcast_to(x, y.shape), y, ridge=0.05)
    X = np.column_stack([np.ones(40), x])
    um_a_um = [0.0 if linha.sum() == 0 else tendencia.ajustar_glm(X, linha, "binomial", ridge=0.05)[1] for linha in y]
    assert em_lote == pytest.approx(um_a_um, abs=1e-4)


def test_indices_em_blocos_sao_consecutivos_dentro_do_bloco():
    rng = np.random.default_rng(0)
    idx = tendencia.indices_em_blocos(40, 4, rng)
    assert len(idx) == 40 and idx.min() >= 0 and idx.max() < 40
    assert np.all(np.diff(idx.reshape(10, 4), axis=1) == 1)


def test_permutacao_em_blocos_e_uma_permutacao_que_mantem_vizinhos():
    rng = np.random.default_rng(0)
    perm = tendencia.permutacao_em_blocos(40, 4, rng)
    assert sorted(perm.tolist()) == list(range(40))
    vizinhos = np.sum((np.diff(perm) % 40) == 1)
    assert vizinhos >= 30  # dentro de cada bloco de 4, os 3 passos são consecutivos


def test_tendencia_logistica_detecta_aumento_e_nao_inventa_onde_nao_ha():
    anos = np.arange(1986, 2026)
    sobe = (anos >= 2010).astype(float) * (np.arange(40) % 2 == 0)  # 8 eventos, todos depois de 2010
    r = tendencia.tendencia_logistica(anos, sobe, n_boot=300, n_perm=500, semente=1)
    assert r["inclinacao"] > 0.5 and r["p"] < 0.05 and r["eventos"] == 8
    espalhado = (np.arange(40) % 5 == 0).astype(float)  # 8 eventos, um a cada cinco anos
    r = tendencia.tendencia_logistica(anos, espalhado, n_boot=300, n_perm=500, semente=1)
    assert abs(r["inclinacao"]) < 0.3 and r["p"] > 0.2


def test_tendencia_logistica_sem_evento_nao_quebra():
    r = tendencia.tendencia_logistica(np.arange(1986, 2026), np.zeros(40))
    assert r["inclinacao"] == 0.0 and r["p"] == 1.0 and r["eventos"] == 0


def test_tendencia_da_contagem_recupera_a_razao_de_chances():
    rng = np.random.default_rng(5)
    anos = np.arange(1986, 2026)
    p = tendencia.sigmoide(-2.0 + np.log(2.0) * (anos - 2005) / 10.0)  # chances dobram por década
    eventos = (rng.random((40, 400)) < p[:, None]).astype(float)
    r = tendencia.tendencia_da_contagem(anos, eventos, n_boot=300, semente=2)
    assert r["razao_de_chances_por_decada"] == pytest.approx(2.0, rel=0.1)
    assert r["razao_de_chances_ic"][0] < 2.0 < r["razao_de_chances_ic"][1]
    assert r["superdispersao"] == pytest.approx(1.0, abs=0.6)  # recifes independentes: sem superdispersão


def test_dependencia_entre_recifes_alarga_o_intervalo():
    # Mesma probabilidade marginal, mas todos os recifes atingidos juntos: o intervalo tem de ficar mais largo.
    rng = np.random.default_rng(7)
    anos = np.arange(1986, 2026)
    p = tendencia.sigmoide(-1.5 + 0.5 * (anos - 2005) / 10.0)
    independentes = (rng.random((40, 30)) < p[:, None]).astype(float)
    juntos = np.repeat((rng.random(40) < p)[:, None], 30, axis=1).astype(float)
    a = tendencia.tendencia_da_contagem(anos, independentes, n_boot=300, semente=2)
    b = tendencia.tendencia_da_contagem(anos, juntos, n_boot=300, semente=2)
    largura = lambda r: np.log(r["razao_de_chances_ic"][1]) - np.log(r["razao_de_chances_ic"][0])  # noqa: E731
    assert largura(b) > 1.5 * largura(a)
    assert b["superdispersao"] > 5


def test_intervalo_de_retorno():
    r = tendencia.intervalo_de_retorno(4, 20)
    assert r["retorno"] == pytest.approx(5.0)
    assert r["prob_anual_ic"][0] == pytest.approx(stats.beta.ppf(0.025, 4.5, 16.5))
    assert r["retorno_ic"][0] < 5.0 < r["retorno_ic"][1]
    vazio = tendencia.intervalo_de_retorno(0, 20)
    assert vazio["retorno"] == float("inf") and vazio["retorno_ic"][1] == float("inf")
    assert vazio["retorno_ic"][0] == pytest.approx(1.0 / stats.beta.ppf(0.975, 0.5, 20.5))


def test_correcoes_para_multiplas_comparacoes():
    p = np.array([0.01, 0.04, 0.03, 0.20])
    # Benjamini-Hochberg: ordenados 0,01 0,03 0,04 0,20 -> 0,04 0,06 0,0533 0,20 -> monotônico: 0,04 0,0533 0,0533 0,20
    assert tendencia.benjamini_hochberg(p) == pytest.approx([0.04, 0.16 / 3, 0.16 / 3, 0.20])
    # Holm: 0,01*4, 0,03*3, 0,04*2, 0,20*1 -> 0,04 0,09 0,09 0,20
    assert tendencia.holm(p) == pytest.approx([0.04, 0.09, 0.09, 0.20])
