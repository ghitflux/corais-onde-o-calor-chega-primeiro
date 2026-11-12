"""Leitura e agregação dos dados brutos, sem rede e sem arquivo temporário."""

import pandas as pd
import pytest

from corais_calor import coleta
from corais_calor.recifes import RECIFES, REFERENCIA, Recife


def test_le_o_arquivo_semanal_do_cpc():
    texto = "\n".join(
        [
            " Weekly SST data starts week centered on 2Sept1981",
            "",
            "                Nino1+2      Nino3        Nino34        Nino4",
            " Week          SST SSTA     SST SSTA     SST SSTA     SST SSTA",
            " 02SEP1981     20.6-0.1     24.8-0.1     26.5-0.2     28.3-0.3",
            " 30DEC2015     25.2 1.7     27.9 2.6     29.5 2.8     30.1 1.6",
        ]
    )
    tabela = coleta.ler_nino_cpc(texto)
    assert list(tabela.index) == [pd.Timestamp("1981-09-02"), pd.Timestamp("2015-12-30")]
    assert tabela["sst_nino34"].tolist() == [26.5, 29.5]
    assert tabela["anomalia_cpc"].tolist() == [-0.2, 2.8]


def test_grade_semanal_absorve_o_escorregao_das_datas():
    # Leituras que escorregam dois dias a partir da quarta semana (como acontece depois de dias faltando no
    # servidor), e uma semana inteira sem leitura.
    datas = pd.to_datetime(["1985-01-06", "1985-01-13", "1985-01-20", "1985-01-29", "1985-02-05", "1985-02-19"])
    serie = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 7.0], index=datas)
    grade = coleta.na_grade_semanal(serie, "1985-02-20")
    assert list(grade.index.strftime("%m-%d")) == ["01-06", "01-13", "01-20", "01-27", "02-03", "02-10", "02-17"]
    assert grade.tolist()[:5] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert pd.isna(grade.iloc[5])  # a leitura mais próxima de 10/02 está a 5 dias: fica vazia
    assert grade.iloc[6] == 7.0


def test_distancia_de_um_grau_no_equador():
    assert coleta.distancia_km([0.0], [0.0], 0.0, 1.0)[0] == pytest.approx(111.19, abs=0.05)
    assert coleta.distancia_km([10.0], [20.0], 10.0, 20.0)[0] == 0.0
    # Atravessar a linha de data: 179,5°L e 179,5°O ficam a 1° um do outro.
    assert coleta.distancia_km([0.0], [179.5], 0.0, -179.5)[0] == pytest.approx(111.19, abs=0.05)


def test_extrato_de_branqueamento_une_linhas_repetidas_e_filtra_pela_distancia():
    recife = Recife("teste", "Teste", "Lugar", "Grupo", 0.0, 0.0, "fonte")
    bruto = pd.DataFrame(
        {
            # O mesmo levantamento em duas linhas (dois substratos), um segundo levantamento perto, um longe e um sem dado.
            "Data_Source": ["Reef_Check", "Reef_Check", "Reef_Check", "Donner", "Donner"],
            "Latitude_Degrees": [0.1, 0.1, 0.2, 5.0, 0.1],
            "Longitude_Degrees": [0.1, 0.1, 0.2, 5.0, 0.1],
            "Date": ["2016-03-10", "2016-03-10", "2016-03-10", "2016-03-10", "2016-03-11"],
            "Percent_Bleaching": ["20", "40", "60", "90", "nd"],
        }
    )
    extrato, funil = coleta.extrato_de_branqueamento(bruto, [recife], raio_km=100.0)
    assert funil["linhas_na_base"] == 5
    assert funil["com_percentual_e_data"] == 4
    assert funil["levantamentos_unicos"] == 3
    assert funil["levantamentos_perto_dos_recifes"] == 2
    assert len(extrato) == 1
    linha = extrato.iloc[0]
    assert linha["levantamentos"] == 2 and linha["percentual_medio"] == pytest.approx(45.0)  # média de 30 e 60


def test_lista_de_recifes_e_coerente():
    slugs = [r.slug for r in RECIFES]
    assert len(slugs) == len(set(slugs))
    assert 20 <= len(RECIFES) <= 40
    assert all(-35 < r.lat < 35 and -180 <= r.lon <= 180 for r in RECIFES)
    assert set(REFERENCIA) <= set(slugs)
    grupos = {r.grupo for r in RECIFES}
    assert {r.grupo for r in RECIFES if r.slug in REFERENCIA} == grupos  # um recife de referência por bacia
