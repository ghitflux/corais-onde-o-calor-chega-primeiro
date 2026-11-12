"""Carga do extrato versionado em data/ (a análise roda sem rede a partir dele)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "data"


@dataclass
class Base:
    recifes: pd.DataFrame  # índice: slug; inclui o pixel usado, o MMM oficial e a marca de recife de referência
    sst_semanal: pd.DataFrame  # CoralTemp, uma data a cada 7 dias x recife, °C
    dhw_semanal: pd.DataFrame  # DHW oficial, nas mesmas datas, °C-semana
    sst_mensal: pd.DataFrame  # média mensal do CoralTemp, 1985 a 2012 (para a climatologia)
    ref_sst: pd.DataFrame  # recifes de referência: CoralTemp diário
    ref_dhw: pd.DataFrame  # recifes de referência: DHW oficial diário
    ref_oisst: pd.DataFrame  # recifes de referência: OISST diário
    nino34: pd.DataFrame  # semanal, do CPC: sst_nino34 e anomalia_cpc
    branqueamento: pd.DataFrame  # levantamentos de campo perto dos recifes
    costa: list[np.ndarray]  # linhas de costa (lon, lat)
    coleta: dict
    nino_caixa: pd.Series | None = None  # média da caixa Niño 3.4 calculada do OISST, para conferir o índice do CPC

    @property
    def referencia(self) -> list[str]:
        return list(self.recifes.index[self.recifes["referencia"]])


def _larga(arquivo: Path, diaria: bool = False) -> pd.DataFrame:
    tabela = pd.read_csv(arquivo, index_col="data", parse_dates=["data"])
    if diaria:  # grade diária completa: dia que faltar no produto vira NaN, em vez de sumir
        tabela = tabela.reindex(pd.date_range(tabela.index.min(), tabela.index.max(), freq="D", name="data"))
    return tabela


def carregar_costa(arquivo: Path) -> list[np.ndarray]:
    geo = json.loads(arquivo.read_text(encoding="utf-8"))
    linhas = []
    for feicao in geo["features"]:
        geometria = feicao["geometry"]
        partes = [geometria["coordinates"]] if geometria["type"] == "LineString" else geometria["coordinates"]
        linhas.extend(np.asarray(parte, dtype=float) for parte in partes)
    return linhas


def carregar(pasta: Path = DATA) -> Base:
    recifes = pd.read_csv(pasta / "recifes.csv", index_col="slug")
    slugs = list(recifes.index)
    semanal = _larga(pasta / "sst_semanal_coraltemp.csv")[slugs]
    caixa = pasta / "nino34_caixa_oisst.csv"
    return Base(
        recifes=recifes,
        sst_semanal=semanal,
        dhw_semanal=_larga(pasta / "dhw_semanal_noaa.csv")[slugs].reindex(semanal.index),
        sst_mensal=_larga(pasta / "sst_mensal_coraltemp.csv")[slugs],
        ref_sst=_larga(pasta / "referencia_sst_diaria_coraltemp.csv", diaria=True),
        ref_dhw=_larga(pasta / "referencia_dhw_diario_noaa.csv", diaria=True),
        ref_oisst=_larga(pasta / "referencia_sst_diaria_oisst.csv", diaria=True),
        nino34=pd.read_csv(pasta / "nino34_semanal.csv", index_col="data", parse_dates=["data"]),
        branqueamento=pd.read_csv(pasta / "branqueamento_perto_dos_recifes.csv", parse_dates=["data"]),
        costa=carregar_costa(pasta / "costa_110m.geojson"),
        coleta=json.loads((pasta / "coleta.json").read_text(encoding="utf-8")),
        nino_caixa=pd.read_csv(caixa, index_col="data", parse_dates=["data"])["sst_caixa_oisst"] if caixa.exists() else None,
    )


def dias(indice: pd.DatetimeIndex) -> np.ndarray:
    return indice.to_numpy().astype("datetime64[D]")
