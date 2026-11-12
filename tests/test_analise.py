"""A análise inteira roda sobre uma base sintética em memória, com respostas conhecidas onde dá."""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from corais_calor import analise, dhw, site
from corais_calor.dados import Base

GRUPOS = ["Pacífico oeste", "Índico", "Atlântico Sul"]


def _base_sintetica(n_recifes: int = 9, semente: int = 0) -> Base:
    """Recifes inventados: ciclo sazonal, aquecimento lento, ruído com memória e um ano quente comum (2016)."""
    rng = np.random.default_rng(semente)
    dias = pd.date_range("1985-01-01", "2026-11-10", freq="D")
    anos = dias.year.to_numpy()
    fase = 2 * np.pi * (dias.day_of_year.to_numpy() - 1) / 365.25
    recifes, sst, oficial, mensal = [], {}, {}, {}
    for i in range(n_recifes):
        slug = f"r{i}"
        sul = i % 2 == 0
        ruido = np.zeros(len(dias))
        choque = rng.normal(0, 0.12, len(dias))
        for t in range(1, len(dias)):
            ruido[t] = 0.97 * ruido[t - 1] + choque[t]
        serie = 27.0 + (1.5 if sul else -1.5) * np.cos(fase) + 0.02 * (i + 1) / n_recifes * (anos - 1985) + ruido
        serie[anos == 2016] += 0.8
        serie = np.round(serie, 2)
        meses = pd.Series(serie, index=dias).resample("ME").mean().loc[:"2012-12-31"]
        clima = dhw.climatologia_mensal(meses.index.to_numpy().astype("datetime64[D]"), meses.to_numpy())
        mmm = round(dhw.mmm(clima), 2)
        sst[slug], mensal[slug] = serie, meses
        oficial[slug] = np.round(dhw.dhw(serie, mmm), 2)
        recifes.append({"slug": slug, "nome": f"Recife {i}", "regiao": "Lugar", "grupo": GRUPOS[i % 3], "lat": -10.0 if sul else 10.0, "lon": 10.0 * i, "fonte": "teste", "referencia": i < 3, "lat_crw": -10.0, "lon_crw": 10.0 * i, "km_crw": 1.0, "mmm_noaa": mmm})
    tabela = pd.DataFrame(recifes).set_index("slug")
    diario_sst = pd.DataFrame(sst, index=dias.rename("data"))
    diario_dhw = pd.DataFrame(oficial, index=dias.rename("data"))
    diario_dhw[diario_dhw.index < "1985-04-01"] = np.nan
    semanas = dias[(dias - pd.Timestamp("1985-01-06")).days % 7 == 0]
    semanas = semanas[semanas >= "1985-01-06"]
    ref = list(tabela.index[tabela["referencia"]])
    oisst_dias = pd.date_range("1981-09-01", "2026-10-27", freq="D", name="data")
    oisst = diario_sst[ref].reindex(oisst_dias).bfill() + rng.normal(0, 0.05, (len(oisst_dias), len(ref)))
    nino_datas = pd.date_range("1981-09-02", "2026-11-04", freq="7D", name="data")
    nino = pd.DataFrame({"sst_nino34": 27.0 + np.sin(2 * np.pi * nino_datas.day_of_year / 365.25) + rng.normal(0, 0.5, len(nino_datas))}, index=nino_datas)
    nino["anomalia_cpc"] = nino["sst_nino34"] - 27.0 - np.sin(2 * np.pi * nino_datas.day_of_year / 365.25)
    # Levantamentos de campo inventados: o percentual branqueado cresce com o DHW do dia.
    linhas = []
    for slug in tabela.index[:4]:
        for dia in pd.date_range("2000-03-01", "2019-03-01", freq="182D"):
            estresse = float(diario_dhw.loc[dia, slug])
            linhas.append({"slug": slug, "data": dia, "fonte": "Reef_Check", "levantamentos": 2, "percentual_medio": min(100.0, 6.0 * estresse + rng.uniform(0, 4)), "km_medio": 5.0})
    return Base(
        recifes=tabela,
        sst_semanal=diario_sst.loc[semanas],
        dhw_semanal=diario_dhw.loc[semanas],
        sst_mensal=pd.DataFrame(mensal).rename_axis("data"),
        ref_sst=diario_sst[ref],
        ref_dhw=diario_dhw[ref],
        ref_oisst=oisst,
        nino34=nino,
        branqueamento=pd.DataFrame(linhas),
        costa=[np.array([[0.0, 0.0], [1.0, 1.0]])],
        coleta={"coletado_em": "2026-11-12"},
    )


@pytest.fixture(scope="module")
def base() -> Base:
    return _base_sintetica()


@pytest.fixture(scope="module")
def preparado(base):
    return analise.preparar(base)


def test_preparar_recupera_o_mmm_e_o_mes_mais_quente(base, preparado):
    series, diarias = preparado
    assert len(series) == 9 and len(diarias) == 3
    for s in series:
        assert s.mmm == pytest.approx(s.mmm_noaa, abs=0.006)  # o "oficial" sintético foi feito pela mesma conta
        assert s.mes_pico in ((12, 1, 2) if base.recifes.loc[s.slug, "lat"] < 0 else (6, 7, 8))


def test_conferencia_do_dhw_fecha_quando_o_oficial_vem_da_mesma_conta(preparado):
    series, diarias = preparado
    conf = analise.conferir_dhw(series, diarias)
    assert conf["erro_diario_maximo_algoritmo"] < 0.006  # só o arredondamento de duas casas
    assert conf["resumo"]["algoritmo"]["erro_absoluto_do_maximo_anual"] < 0.006
    assert conf["resumo"]["algoritmo"]["dhw4"]["concordancia"] == 1.0
    assert conf["resumo"]["amostragem_semanal"]["vies_do_maximo_anual"] <= 0  # ler um dia por semana só pode perder o pico
    assert conf["resumo"]["outro_produto"]["correlacao_do_maximo_anual"] > 0.9
    assert conf["mmm"]["diferenca_absoluta_maxima"] < 0.006
    assert conf["mmm"]["sem_recentrar_diferenca_media"] > 0


def test_matriz_anual_cobre_os_anos_e_marca_o_ano_quente(preparado):
    series, _ = preparado
    anual = analise.matriz_anual(series)
    assert anual.index.min() in (1985, 1986) and anual.index.max() == 2026
    assert (anual.loc[2016] > anual.drop(index=2016).median()).all()


def test_tendencias_e_eventos_globais(preparado):
    series, _ = preparado
    tend = analise.tendencias(series, n_boot=60, n_perm=100)
    c = tend["dhw4"]["conjunto"]
    assert len(c["fracao_por_ano"]) == len(tend["anos"])
    assert c["razao_de_chances_ic"][0] <= c["razao_de_chances_por_decada"] <= c["razao_de_chances_ic"][1]
    for linha in tend["dhw4"]["por_recife"]:
        assert sum(linha["por_decada"]) + linha["depois_de_2024"] <= linha["eventos"]
        assert linha["retorno_antes"]["anos"] + linha["retorno_depois"]["anos"] <= linha["anos_observados"]
        if linha["p_bh"] is not None:
            assert linha["p_bh"] >= linha["p"] - 1e-12 and linha["p_holm"] >= linha["p_bh"] - 1e-12
    todos = tend["dhw4"]["retorno"]["todos"]
    assert todos["antes"]["eventos"] == sum(linha["retorno_antes"]["eventos"] for linha in tend["dhw4"]["por_recife"])
    globais = analise.eventos_globais(tend)
    assert globais["dhw4"]["por_evento"]["2014-2017"]["fracao_maxima"] == pytest.approx(max(c["fracao_por_ano"]))
    assert globais["dhw4"]["dez_piores_anos"][0]["ano"] == 2016


def test_amostras_de_previsao_nao_olham_para_o_futuro(base, preparado):
    series, _ = preparado
    nino = analise.anomalia_do_nino(base.nino34)
    amostra = analise.amostras_de_previsao(series, nino, 8)
    assert ((amostra["alvo"] - amostra["emissao"]).dt.days == 56).all()
    # Mudar a temperatura depois da emissão não pode mudar nenhuma variável explicativa.
    s = series[0]
    corte = np.searchsorted(s.datas, np.datetime64("2015-01-01"))
    alterada = analise.Serie(**{**s.__dict__, "sst": np.where(np.arange(len(s.sst)) > corte, s.sst + 3.0, s.sst)})
    antes = analise.amostras_de_previsao([s], nino, 8)
    depois = analise.amostras_de_previsao([alterada], nino, 8)
    colunas = ["emissao", "dhw_atual", "anomalia", "tendencia", "sazonal", "projecao", "nino"]
    limite = pd.Timestamp("2015-01-01") - pd.Timedelta(days=56)  # a variável "sazonal" olha o calendário da data-alvo
    a = antes.loc[antes["emissao"] <= limite, colunas].reset_index(drop=True)
    d = depois.loc[depois["emissao"] <= limite, colunas].reset_index(drop=True)
    assert len(a) > 500
    pd.testing.assert_frame_equal(a, d)
    # E depois do corte a anomalia tem de mudar, senão o teste não estaria testando nada.
    assert not np.allclose(antes["anomalia"].to_numpy()[-50:], depois["anomalia"].to_numpy()[-50:])


def test_previsao_separa_treino_e_teste_e_devolve_todos_os_metodos(base, preparado):
    series, _ = preparado
    prev = analise.previsoes(series, base.nino34)
    assert list(prev["antecedencias"]) == ["4", "8", "12"]
    for r in prev["antecedencias"].values():
        assert r["treino"]["anos"][1] == 2010 and r["teste"]["anos"][0] == 2011
        assert set(r["metodos"]) == set(analise.METODOS)
        for m in r["metodos"].values():
            assert 0 <= m["brier"] <= 1 and m["brier_ic"][0] <= m["brier_ic"][1]
            assert sum(f["n"] for f in m["confiabilidade"]) == r["teste"]["linhas"]
    # A quatro semanas, a persistência calibrada tem de ganhar da climatologia: a anomalia de hoje informa.
    quatro = prev["antecedencias"]["4"]["metodos"]
    assert quatro["persistencia_calibrada"]["brier"] < quatro["climatologia"]["brier"]


def test_conferencia_do_nino_casa_as_datas_mais_proximas(base):
    # Uma "caixa" igual ao índice mais 0,2 °C, lida um dia depois de cada semana do índice, de quatro em quatro.
    caixa = (base.nino34["sst_nino34"].iloc[::4] + 0.2).rename("sst_caixa_oisst")
    caixa.index = caixa.index + pd.Timedelta(days=1)
    r = analise.conferir_nino(base.nino34, caixa)
    assert r["datas_comparadas"] == len(caixa)
    assert r["correlacao"] == pytest.approx(1.0)
    assert r["diferenca_media"] == pytest.approx(0.2)


def test_ranking_e_tabela_de_exposicao(base, preparado):
    series, _ = preparado
    rank = analise.ranking(series, n_boot=200)
    postos = [linha["posto"] for linha in rank["por_recife"]]
    assert postos == list(range(1, 10))
    assert rank["tamanho_do_terco"] == 3
    assert sum(linha["prob_terco_mais_exposto"] for linha in rank["por_recife"]) == pytest.approx(3.0)
    assert rank["certos_no_terco"] + rank["certos_fora_do_terco"] + rank["indefinidos"] == 9
    tend = analise.tendencias(series, n_boot=30, n_perm=50)
    tabela = analise.tabela_de_exposicao(base, tend, rank)
    assert len(tabela) == 9 and tabela["posto_exposicao_2005_2024"].tolist() == list(range(1, 10))
    assert {"recife", "lat_referencia", "anos_dhw4_2015_2024", "retorno_dhw4_2005_2024_anos", "prob_terco_mais_exposto"} <= set(tabela.columns)


def test_validacao_com_branqueamento_acha_a_relacao_plantada(base, preparado):
    series, _ = preparado
    v = analise.validar_com_branqueamento(series, base.branqueamento, n_boot=100)
    assert v["recifes"] == 4 and v["linhas"] == len(base.branqueamento)
    assert v["limiares"]["10"]["auc"] > 0.9  # o percentual foi gerado a partir do DHW
    medias = [f["percentual_medio"] for f in v["por_faixa"] if f["linhas"]]
    assert medias == sorted(medias)


def test_bloco_do_site_segue_o_formato(base, preparado):
    series, diarias = preparado
    tend = analise.tendencias(series, n_boot=30, n_perm=50)
    r = {
        "coleta": base.coleta,
        "recifes": [{}] * len(series),
        "conferencia_do_dhw": analise.conferir_dhw(series, diarias),
        "tendencias": tend,
        "eventos_globais": analise.eventos_globais(tend),
        "previsao": analise.previsoes(series, base.nino34),
        "ranking": analise.ranking(series, n_boot=100),
        "branqueamento_observado": analise.validar_com_branqueamento(series, base.branqueamento, n_boot=20),
    }
    bloco = site.montar(r)
    assert "12/11/2026" in bloco["dados"]["pt"] and "12 Nov 2026" in bloco["dados"]["en"]
    for chave in ("numero_chave", "pergunta", "resultado", "detalhe", "dados"):
        assert set(bloco[chave]) == {"pt", "en", "es"}
    assert len(bloco["numero_chave"]["pt"]) <= 12 and len(bloco["numero_chave"]["en"]) <= 12
    grafico = bloco["grafico"]
    assert grafico["tipo"] == "linhas" and len(grafico["series"]) <= 4
    for serie in grafico["series"]:
        assert len(serie["pontos"]) <= 80 and serie["papel"] in ("principal", "base", "alternativa", "neutro")
        assert all(0 <= y <= 1 for _, y in serie["pontos"])
    assert len(grafico["faixa"]["inferior"]) == len(grafico["series"][grafico["faixa"]["serie"]]["pontos"])
    _conferir_graficos_extras(bloco["graficos_extras"])


def _conferir_graficos_extras(extras: list[dict]) -> None:
    """Forma que o site espera de cada gráfico extra: tipo, limites, três idiomas e a frase de leitura."""
    idiomas = {"pt", "en", "es"}
    assert 3 <= len(extras) <= 5
    assert {g["tipo"] for g in extras} <= {"linhas", "barras", "pontos"}
    for g in extras:
        for chave in ("titulo", "eixo_x", "eixo_y", "leitura"):
            assert set(g[chave]) == idiomas and all(isinstance(t, str) and t for t in g[chave].values())
        assert all(len(t) <= 90 for t in g["titulo"].values())
        assert g["formato_x"] in ("numero", "percentual", "data") and g["formato_y"] in ("numero", "percentual", "moeda")
        assert 1 <= len(g["series"]) <= 4
        assert "faixa" not in g or g["tipo"] == "linhas"
        for serie in g["series"]:
            assert set(serie["nome"]) == idiomas and serie["papel"] in ("principal", "base", "alternativa", "neutro")
            pontos = serie["pontos"]
            assert 1 <= len(pontos) <= (300 if g["tipo"] == "pontos" else 80)
            assert all(len(p) == 2 and isinstance(p[1], (int, float)) and math.isfinite(p[1]) for p in pontos)
            if g["tipo"] == "barras":
                assert all(isinstance(p[0], str) for p in pontos)
                if "rotulos" in serie:
                    assert set(serie["rotulos"]) == idiomas and all(len(v) == len(pontos) for v in serie["rotulos"].values())
            else:
                assert all(isinstance(p[0], (int, float)) and math.isfinite(p[0]) for p in pontos)
            if g["formato_y"] == "percentual":
                assert all(0 <= p[1] <= 1 for p in pontos)


def test_graficos_extras_do_resultado_gravado_seguem_o_formato():
    """O bloco gravado em reports/resultados.json (o que o site lê) passa pela mesma conferência."""
    arquivo = Path(__file__).resolve().parents[1] / "reports" / "resultados.json"
    if not arquivo.exists():
        pytest.skip("reports/resultados.json ainda não foi gerado")
    bloco = json.loads(arquivo.read_text(encoding="utf-8"))["para_o_site"]
    _conferir_graficos_extras(bloco["graficos_extras"])
    assert [g["tipo"] for g in bloco["graficos_extras"]].count("pontos") == 1
