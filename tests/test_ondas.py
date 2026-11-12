"""Ondas de calor marinhas conferidas em séries sintéticas com eventos plantados."""

import numpy as np
import pytest

from corais_calor import ondas


def _serie(semente: int = 0, ruido: float | None = None):
    """42 anos de temperatura com ciclo sazonal.

    Sem `ruido`, a variação do dia a dia é um padrão fixo de três dias (+0,3, -0,15, -0,15): há dias acima do
    normal, mas nunca dois seguidos, então nenhuma onda de calor aparece sem ser plantada e o teste é exato.
    Com `ruido`, a variação é ruído branco com esse desvio-padrão.
    """
    datas = np.arange(np.datetime64("1982-01-01"), np.datetime64("2023-12-31") + 1, dtype="datetime64[D]")
    dia = ondas.dia_do_ano_365(datas)
    sazonal = 25.0 + 3.0 * np.sin(2 * np.pi * (np.where(dia < 0, 58.5, dia) - 80) / 365.0)
    if ruido is None:
        variacao = np.array([0.3, -0.15, -0.15])[np.arange(len(datas)) % 3]
    else:
        variacao = np.random.default_rng(semente).normal(0, ruido, len(datas))
    return datas, sazonal + variacao


def _indice(datas, dia: str) -> int:
    return int(np.flatnonzero(datas == np.datetime64(dia))[0])


def test_dia_do_ano_trata_ano_bissexto():
    datas = np.array(["2020-02-28", "2020-02-29", "2020-03-01", "2020-12-31", "2021-03-01", "2021-12-31"], dtype="datetime64[D]")
    assert ondas.dia_do_ano_365(datas).tolist() == [58, -1, 59, 364, 59, 364]


def test_blocos_verdadeiros():
    mascara = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1], dtype=bool)
    assert ondas.blocos_verdadeiros(mascara) == [(1, 2), (5, 5), (7, 9)]


def test_media_movel_circular_preserva_constante_e_media():
    assert ondas.media_movel_circular(np.full(365, 2.0), 31) == pytest.approx(np.full(365, 2.0))
    x = np.arange(365, dtype=float)
    assert ondas.media_movel_circular(x, 31).mean() == pytest.approx(x.mean())


def test_climatologia_recupera_o_ciclo_sazonal():
    datas, sst = _serie(ruido=1e-9)
    media, limiar = ondas.climatologia_diaria(datas, sst)
    esperado = 25.0 + 3.0 * np.sin(2 * np.pi * (np.arange(365) - 80) / 365.0)
    # Sem ruído, a média alisada acompanha a senóide (o alisamento achata os extremos em poucos centésimos).
    assert np.abs(media - esperado).max() < 0.08
    assert np.all(limiar >= media - 1e-9)


def test_encontra_os_eventos_plantados_com_duracao_e_intensidade():
    datas, sst = _serie()
    plantados = [("2015-02-10", 12, 2.5), ("2016-08-01", 30, 3.0), ("2019-11-05", 5, 2.0)]
    for dia, duracao, intensidade in plantados:
        i = _indice(datas, dia)
        sst[i : i + duracao] += intensidade
    encontradas = ondas.detectar(datas, sst)
    assert len(encontradas) == 3
    for onda, (dia, duracao, intensidade) in zip(encontradas, plantados):
        assert onda.inicio == _indice(datas, dia)
        assert onda.duracao == duracao
        assert onda.intensidade_maxima == pytest.approx(intensidade, abs=0.35)
        assert onda.intensidade_acumulada == pytest.approx(intensidade * duracao, rel=0.05)


def test_evento_de_quatro_dias_nao_conta():
    datas, sst = _serie()
    i = _indice(datas, "2015-02-10")
    sst[i : i + 4] += 3.0
    assert ondas.detectar(datas, sst) == []


def test_lacuna_de_dois_dias_une_e_de_tres_separa():
    datas, sst = _serie()
    i = _indice(datas, "2015-02-10")
    sst[i : i + 6] += 3.0
    sst[i + 8 : i + 14] += 3.0  # lacuna de 2 dias
    unida = ondas.detectar(datas, sst)
    assert len(unida) == 1 and unida[0].duracao == 14

    datas, sst = _serie()
    sst[i : i + 6] += 3.0
    sst[i + 9 : i + 15] += 3.0  # lacuna de 3 dias
    assert [o.duracao for o in ondas.detectar(datas, sst)] == [6, 6]


def test_ruido_branco_fica_perto_de_dez_por_cento_dos_dias_acima_do_limiar():
    # Por construção, cerca de 10% dos dias da referência ficam acima do percentil 90.
    datas, sst = _serie(semente=1, ruido=0.5)
    _, limiar = ondas.climatologia_diaria(datas, sst)
    acima = sst > ondas.espalhar_no_tempo(limiar, datas)
    assert 0.07 < acima.mean() < 0.13
    # Mas, sem persistência, quase nenhum trecho chega a cinco dias seguidos: 0,1^5 por início de sequência.
    por_ano = len(ondas.detectar(datas, sst)) / 42
    assert por_ano < 0.5


def test_resumo_por_periodo_conta_frequencia_e_dias():
    datas, sst = _serie()
    for dia in ("2005-03-01", "2006-03-01", "2015-03-01"):
        i = _indice(datas, dia)
        sst[i : i + 10] += 3.0
    encontradas = ondas.detectar(datas, sst)
    resumo = ondas.resumo_por_periodo(datas, encontradas, [(2000, 2009), (2010, 2019)])
    assert resumo[0]["eventos_por_ano"] == pytest.approx(0.2)
    assert resumo[0]["dias_por_ano"] == pytest.approx(2.0)
    assert resumo[1]["eventos_por_ano"] == pytest.approx(0.1)
    anos, dias = ondas.dias_em_onda_por_ano(datas, encontradas)
    assert dias[anos == 2005][0] == 10 and dias[anos == 2007][0] == 0
