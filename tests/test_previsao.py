"""Linhas de base e métricas de previsão conferidas contra respostas conhecidas."""

import numpy as np
import pytest

from corais_calor import dhw, previsao


def test_media_movel_passada_so_olha_para_tras():
    x = np.arange(10, dtype=float)
    m = previsao.media_movel_passada(x, 3)
    assert np.isnan(m[:2]).all()
    assert m[2:] == pytest.approx(np.arange(1.0, 9.0))


def test_dhw_projetado_com_anomalia_constante_e_o_dhw_real():
    # Se a anomalia realmente persiste, a projeção acerta o DHW futuro em qualquer antecedência.
    n = 400
    clima = np.full(n, 28.0)
    sst = clima + 1.5
    real = dhw.dhw(sst, 27.5)  # HotSpot de 2,0 todos os dias
    anomalia = sst - clima
    for dias in (28, 56, 84, 120):
        proj = previsao.dhw_projetado(sst, clima, anomalia, 27.5, dias)
        t = np.arange(100, 200)
        assert proj[t] == pytest.approx(real[t + dias])
        assert np.isnan(proj[n - dias :]).all()


def test_dhw_projetado_mistura_passado_observado_e_futuro_projetado():
    # 20 dias observados a 2 °C acima do MMM, depois a anomalia cai a zero: com 28 dias de antecedência, a
    # janela de 84 dias guarda os 20 dias quentes (40 °C-dia) e o futuro projetado não soma nada.
    n = 300
    clima = np.full(n, 27.0)
    sst = clima.copy()
    sst[100:120] = 30.0
    anomalia = sst - clima
    proj = previsao.dhw_projetado(sst, clima, anomalia, 28.0, 28)
    assert proj[125] == pytest.approx(40.0 / 7.0)
    # Emitida durante o calor (dia 110, 11 dias quentes vistos), a persistência projeta mais 28 dias quentes.
    assert proj[110] == pytest.approx((11 + 28) * 2.0 / 7.0)


def test_dhw_projetado_semanal_equivale_ao_dhw_semanal():
    # Com uma leitura a cada 7 dias (janela de 12 leituras), a projeção com anomalia persistente também acerta.
    n = 120
    clima = 27.0 + np.sin(np.arange(n) / 8.0)
    sst = clima + 1.2
    real = dhw.dhw(sst, 27.0, janela=12, passo_dias=7)
    for semanas in (4, 8, 12):
        proj = previsao.dhw_projetado(sst, clima, sst - clima, 27.0, semanas, janela=12, passo_dias=7)
        t = np.arange(20, 100)
        assert proj[t] == pytest.approx(real[t + semanas])


def test_dhw_projetado_so_nas_posicoes_pedidas():
    n = 60
    clima = np.full(n, 28.0)
    sst = clima + 1.5
    proj = previsao.dhw_projetado(sst, clima, sst - clima, 27.5, 4, janela=12, passo_dias=7, posicoes=np.array([20, 30, 58]))
    assert np.isfinite(proj[[20, 30]]).all()
    assert np.isnan(proj[58]) and np.isnan(proj[21])  # 58 não tem futuro na série; 21 não foi pedido


def test_ciclo_sazonal_recupera_senoide_e_ignora_o_que_nao_e_sazonal():
    dia = np.tile(np.arange(1, 366), 6)
    verdadeiro = 26.0 + 2.5 * np.sin(2 * np.pi * (dia - 1) / 365.25) - 0.8 * np.cos(4 * np.pi * (dia - 1) / 365.25)
    coeficientes = previsao.ajustar_ciclo_sazonal(dia, verdadeiro, harmonicos=3)
    assert previsao.ciclo_sazonal(coeficientes, dia) == pytest.approx(verdadeiro, abs=1e-8)
    assert coeficientes[0] == pytest.approx(26.0)
    # Só a constante: devolve a média.
    assert previsao.ajustar_ciclo_sazonal(dia, verdadeiro, harmonicos=0)[0] == pytest.approx(verdadeiro.mean())


def test_frequencia_por_semana_usa_so_o_treino():
    semana = np.array([0, 0, 0, 0, 10, 10, 10, 10])
    evento = np.array([1, 0, 1, 1, 0, 0, 1, 1], dtype=float)
    treino = np.array([1, 1, 0, 0, 1, 1, 0, 0], dtype=bool)
    freq = previsao.frequencia_por_semana(semana, evento, treino, meia_largura=0)
    assert freq.tolist() == [0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0]


def test_brier_e_ganho():
    evento = np.array([1, 0, 0, 1], dtype=float)
    assert previsao.brier(evento, evento) == 0.0
    assert previsao.brier(np.full(4, 0.5), evento) == pytest.approx(0.25)
    assert previsao.brier_skill(evento, np.full(4, 0.5), evento) == pytest.approx(1.0)
    assert previsao.brier_skill(np.full(4, 0.5), np.full(4, 0.5), evento) == pytest.approx(0.0)


def test_auc_casos_extremos_e_empates():
    evento = np.array([0, 0, 1, 1])
    assert previsao.auc(np.array([0.1, 0.2, 0.8, 0.9]), evento) == 1.0
    assert previsao.auc(np.array([0.9, 0.8, 0.2, 0.1]), evento) == 0.0
    assert previsao.auc(np.full(4, 0.5), evento) == 0.5
    # Um par invertido em quatro pares: 3/4.
    assert previsao.auc(np.array([0.1, 0.6, 0.5, 0.9]), evento) == pytest.approx(0.75)


def test_confiabilidade_de_previsao_perfeitamente_calibrada():
    rng = np.random.default_rng(0)
    prob = rng.random(50000)
    evento = (rng.random(50000) < prob).astype(float)
    curva = previsao.confiabilidade(prob, evento, [0.0, 0.25, 0.5, 0.75, 1.0])
    assert sum(f["n"] for f in curva) == 50000
    for faixa in curva:
        assert faixa["observado"] == pytest.approx(faixa["previsto"], abs=0.02)


def test_logistica_recupera_probabilidades_simuladas():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(6000, 2))
    p = 1 / (1 + np.exp(-(-1.0 + 2.0 * X[:, 0] - 1.0 * X[:, 1])))
    y = (rng.random(6000) < p).astype(float)
    modelo = previsao.Logistica(ridge=0.01).ajustar(X[:4000], y[:4000])
    previsto = modelo.prever(X[4000:])
    assert np.abs(previsto - p[4000:]).mean() < 0.03
    assert previsao.auc(previsto, y[4000:]) > 0.85


def test_bootstrap_por_grupo_reamostra_grupos_inteiros():
    grupos = np.repeat([2011, 2012, 2013], 4)
    tamanhos = previsao.bootstrap_por_grupo(grupos, lambda idx: len(idx), n_boot=20)
    assert np.all(tamanhos == 12)
    medias = previsao.bootstrap_por_grupo(grupos, lambda idx: len(np.unique(grupos[idx])), n_boot=200, semente=1)
    assert medias.min() >= 1 and medias.max() <= 3 and medias.mean() < 3
