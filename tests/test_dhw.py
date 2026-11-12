"""DHW conferido contra casos de resposta conhecida."""

import numpy as np
import pytest

from corais_calor import dhw


def _datas(inicio: str, fim: str) -> np.ndarray:
    return np.arange(np.datetime64(inicio), np.datetime64(fim) + 1, dtype="datetime64[D]")


def test_exemplo_da_metodologia_da_noaa():
    # HotSpots de 1,0, 2,0 e 1,2 contam; o de 0,8 não. Soma 4,2 °C-dia = 0,6 °C-semana.
    sst = 28.0 + np.array([0.0, 1.0, 2.0, 0.8, 1.2, 0.0])
    assert dhw.dhw(sst, 28.0)[-1] == pytest.approx(0.6)


def test_calor_constante_enche_a_janela():
    # 2 °C acima do MMM por 84 dias ou mais: 2 * 84 / 7 = 24 °C-semana, e não passa disso.
    sst = np.full(200, 30.0)
    valores = dhw.dhw(sst, 28.0)
    assert valores[83] == pytest.approx(24.0)
    assert valores[-1] == pytest.approx(24.0)
    assert valores[6] == pytest.approx(2.0)  # uma semana a 2 °C


def test_abaixo_de_um_grau_nao_acumula():
    assert dhw.dhw(np.full(120, 28.99), 28.0).max() == 0.0


def test_o_estresse_sai_da_janela_depois_de_84_dias():
    sst = np.full(300, 27.0)
    sst[10:17] = 30.0  # uma semana a 2 °C acima
    valores = dhw.dhw(sst, 28.0)
    assert valores[16] == pytest.approx(2.0)
    assert valores[10 + 83] == pytest.approx(2.0)  # último dia em que o primeiro dia quente ainda conta
    assert valores[16 + 84] == pytest.approx(0.0)


def test_versao_semanal_iguala_a_diaria_quando_a_temperatura_nao_muda_dentro_da_semana():
    # Temperatura constante em cada semana: ler um dia por semana e fazer cada leitura valer 7 dias dá o mesmo DHW.
    semanal = 28.0 + np.array([0.0, 1.5, 2.0, 0.5, 1.0, 3.0] * 5)
    diaria = np.repeat(semanal, 7)
    pela_diaria = dhw.dhw(diaria, 28.0)[6::7]  # último dia de cada semana
    pela_semanal = dhw.dhw(semanal, 28.0, janela=12, passo_dias=7)
    assert pela_semanal == pytest.approx(pela_diaria)


def test_dia_sem_dado_conta_como_zero():
    sst = np.array([30.0, np.nan, 30.0])
    assert dhw.dhw(sst, 28.0)[-1] == pytest.approx(4.0 / 7.0)


def test_climatologia_sem_tendencia_e_a_media_do_mes():
    datas = _datas("1985-01-01", "2012-12-31")
    _, meses = dhw.ano_e_mes(datas)
    sst = 20.0 + meses.astype(float)  # janeiro = 21, ..., dezembro = 32
    clima = dhw.climatologia_mensal(datas, sst)
    assert clima == pytest.approx(np.arange(21.0, 33.0))
    assert dhw.mmm(clima) == pytest.approx(32.0)


def test_climatologia_recentrada_le_a_reta_em_1988():
    # Aquecimento de 0,02 °C por ano: a média simples de 1985-2012 fica no nível de 1998,5;
    # a recentrada fica no nível de 1988,286, ou seja, 0,02 * (1998,5 - 1988,286) mais fria.
    datas = _datas("1985-01-01", "2012-12-31")
    anos, _ = dhw.ano_e_mes(datas)
    sst = 25.0 + 0.02 * (anos - 1985)
    simples = dhw.climatologia_mensal(datas, sst, centro=None)
    recentrada = dhw.climatologia_mensal(datas, sst)
    assert simples == pytest.approx(np.full(12, 25.0 + 0.02 * 13.5))
    assert recentrada == pytest.approx(np.full(12, 25.0 + 0.02 * (1988.286 - 1985)))
    assert (simples - recentrada) == pytest.approx(np.full(12, 0.02 * (1998.5 - 1988.286)))


def test_ano_de_estresse_gira_em_torno_do_mes_mais_quente():
    datas = np.array(["2015-08-31", "2015-09-01", "2015-12-31", "2016-02-15", "2016-08-31", "2016-09-01"], dtype="datetime64[D]")
    # Pico em março (sul): a janela vai de setembro a agosto e leva o nome do ano em que março cai.
    assert dhw.ano_de_estresse(datas, 3).tolist() == [2015, 2016, 2016, 2016, 2016, 2017]
    # Pico em julho: é o ano civil.
    assert dhw.ano_de_estresse(datas, 7).tolist() == [2015, 2015, 2015, 2016, 2016, 2016]
    # Pico em agosto (norte): de fevereiro a janeiro.
    datas = np.array(["2016-01-31", "2016-02-01", "2017-01-31"], dtype="datetime64[D]")
    assert dhw.ano_de_estresse(datas, 8).tolist() == [2015, 2016, 2016]


def test_mes_mais_quente():
    clima = np.array([27.0, 28.0, 29.5, 29.0, 28.0, 27.0, 26.0, 25.0, 25.0, 25.5, 26.0, 26.5])
    assert dhw.mes_mais_quente(clima) == 3


def test_maximo_anual_ignora_ano_incompleto():
    datas = _datas("2000-01-01", "2002-03-31")
    valores = np.zeros(len(datas))
    valores[400] = 5.0  # fevereiro de 2001
    anos, maximos = dhw.maximo_anual(datas, valores, mes_pico=7)
    assert anos.tolist() == [2000, 2001]  # 2002 só tem três meses
    assert maximos.tolist() == [0.0, 5.0]
