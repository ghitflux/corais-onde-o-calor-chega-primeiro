"""Download das bases públicas (sem chave) para data/brutos/ e montagem do extrato versionado em data/.

Fontes:
- NOAA Coral Reef Watch v3.1 (5 km): temperatura CoralTemp, HotSpot e Degree Heating Week diários e a média
  mensal do CoralTemp, no ERDDAP do OceanWatch (NOAA PIFSC);
- OISST v2.1 (NOAA, 0,25°), temperatura diária, no ERDDAP do CoastWatch (NOAA SWFSC);
- índice Niño 3.4 semanal do Climate Prediction Center da NOAA (calculado por eles a partir do OISST);
- branqueamento observado: van Woesik e Burkepile (2022), BCO-DMO, CC BY 4.0;
- linha de costa Natural Earth 1:110m, domínio público.

O ERDDAP lê um arquivo por dia de dado, e uma série diária de 40 anos num ponto leva de 8 a 20 minutos. Por isso
a coleta tem duas resoluções:

- todos os recifes: DHW oficial e CoralTemp numa data a cada 7 dias (1985 em diante), a média mensal do CoralTemp
  e o MMM oficial (lido como temperatura menos HotSpot);
- recifes de referência (um por bacia): as séries diárias completas do DHW oficial, do CoralTemp e do OISST.

Regras: uma requisição por vez em cada servidor, pausa entre elas, repetição com espera crescente, e nada é
baixado duas vezes (cada bloco fica num arquivo em data/brutos/).
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from corais_calor.recifes import RECIFES, REFERENCIA, Recife

AGENTE = "portfolio-estudos/1.0"
PAUSA = 1.5

ERDDAP_OISST = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg_LonPM180"
ERDDAP_CRW = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap"
CRW_SST = (f"{ERDDAP_CRW}/CRW_sst_v3_1", "analysed_sst")
CRW_DHW = (f"{ERDDAP_CRW}/CRW_dhw_v1_0", "degree_heating_week")
CRW_HOTSPOT = (f"{ERDDAP_CRW}/CRW_hs_v1_0", "hotspot")
CRW_MENSAL = (f"{ERDDAP_CRW}/CRW_sst_v3_1_monthly", "sea_surface_temperature")
URL_BRANQUEAMENTO = "https://datadocs.bco-dmo.org/dataset/773466/file/B11vA82u7y2Owp/global_bleaching_environmental.csv"
URL_COSTA = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_coastline.geojson"
URL_NINO_CPC = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"

INICIO_OISST = "1981-09-01"
INICIO_SST = "1985-01-01"
INICIO_DHW = "1985-04-01"
PRIMEIRA_SEMANA_SST = "1985-01-06"  # as datas semanais são 1985-01-06 mais múltiplos de 7 dias
PRIMEIRA_SEMANA_DHW = "1985-04-07"
RAIO_BRANQUEAMENTO_KM = 100.0


class Faltando(Exception):
    """O arquivo bruto ainda não foi baixado e o modo é só de leitura."""


def pedir(url: str, tentativas: int = 6, limite: int = 900) -> bytes:
    """GET com User-Agent genérico, repetição com espera crescente e pausa no fim."""
    url = url.replace("[", "%5B").replace("]", "%5D").replace(" ", "%20")
    espera = 20.0
    for tentativa in range(1, tentativas + 1):
        try:
            requisicao = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(requisicao, timeout=limite) as resposta:
                corpo = resposta.read()
            time.sleep(PAUSA)
            return corpo
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as erro:
            if tentativa == tentativas:
                raise
            print(f"    falhou ({erro}); nova tentativa em {espera:.0f} s", flush=True)
            time.sleep(espera)
            espera *= 2
    raise RuntimeError("sem resposta")


def _csv_do_erddap(corpo: bytes) -> pd.DataFrame:
    """Lê o CSV do ERDDAP, que traz uma segunda linha com as unidades."""
    return pd.read_csv(io.BytesIO(corpo), skiprows=[1])


def _serie(corpo: bytes, variavel: str) -> pd.Series:
    tabela = _csv_do_erddap(corpo)
    tabela["data"] = pd.to_datetime(tabela["time"]).dt.tz_localize(None).dt.normalize()
    return tabela.drop_duplicates("data").set_index("data")[variavel].astype(float)


def _arquivo(caminho: Path, url: str, baixar: bool, rotulo: str) -> bytes:
    """Devolve o conteúdo do arquivo bruto, baixando-o se ainda não existir."""
    if not caminho.exists():
        if not baixar:
            raise Faltando(str(caminho))
        caminho.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        corpo = pedir(url)
        caminho.write_bytes(corpo)
        print(f"    {rotulo}: {time.time() - t0:.0f} s", flush=True)
    return caminho.read_bytes()


def _trecho(lat: float, lon: float, zlev: bool, lon_360: bool) -> str:
    return ("[(0.0)]" if zlev else "") + f"[({lat})][({lon % 360 if lon_360 else lon})]"


def ponto_de_mar(base: str, variavel: str, lat: float, lon: float, raio: float, dia: str, zlev: bool, lon_360: bool) -> tuple[float, float, float]:
    """Ponto de grade com dado (mar) mais próximo da coordenada de referência. Devolve (lat, lon, distância em km)."""
    lon_pedido = lon % 360 if lon_360 else lon
    extra = "[(0.0)]" if zlev else ""
    url = f"{base}.csv?{variavel}[({dia})]{extra}[({lat - raio:.3f}):({lat + raio:.3f})][({lon_pedido - raio:.3f}):({lon_pedido + raio:.3f})]"
    tabela = _csv_do_erddap(pedir(url)).dropna(subset=[variavel])
    if tabela.empty:
        raise RuntimeError(f"nenhum ponto de mar a {raio}° de ({lat}, {lon}) em {base}")
    dlat = np.radians(tabela["latitude"].to_numpy() - lat)
    dlon = np.radians((tabela["longitude"].to_numpy() - lon_pedido + 180) % 360 - 180) * np.cos(np.radians(lat))
    km = 6371.0 * np.hypot(dlat, dlon)
    i = int(np.argmin(km))
    lon_achado = float(tabela["longitude"].iloc[i])
    if lon_achado > 180:
        lon_achado -= 360
    return round(float(tabela["latitude"].iloc[i]), 3), round(lon_achado, 3), round(float(km[i]), 1)


def _pontos(pasta: Path, recifes: list[Recife], base: str, variavel: str, raio: float, zlev: bool, lon_360: bool, baixar: bool) -> dict:
    """Ponto de grade de cada recife, guardado em pontos.json para não ser procurado de novo."""
    arquivo = pasta / "pontos.json"
    pontos = {k: tuple(v) for k, v in json.loads(arquivo.read_text(encoding="utf-8")).items()} if arquivo.exists() else {}
    for r in recifes:
        if r.slug not in pontos and baixar:
            pontos[r.slug] = ponto_de_mar(base, variavel, r.lat, r.lon, raio, "2020-01-15", zlev, lon_360)
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(json.dumps(pontos, indent=1), encoding="utf-8")
            print(f"  {r.slug}: ponto de grade {pontos[r.slug][:2]}, a {pontos[r.slug][2]} km da referência", flush=True)
    return pontos


def serie_diaria(base: str, variavel: str, lat: float, lon: float, inicio: str, fim: str, pasta: Path, zlev: bool, lon_360: bool, baixar: bool, bloco_anos: int = 5) -> pd.Series:
    """Série diária de um ponto de grade, pedida em blocos de anos; cada bloco fica num arquivo em `pasta`."""
    partes = []
    for a0 in range(int(inicio[:4]), int(fim[:4]) + 1, bloco_anos):
        a1 = min(a0 + bloco_anos - 1, int(fim[:4]))
        d0, d1 = max(f"{a0}-01-01", inicio), min(f"{a1}-12-31", fim)
        url = f"{base}.csv?{variavel}[({d0}):1:({d1})]{_trecho(lat, lon, zlev, lon_360)}"
        partes.append(_serie(_arquivo(pasta / f"{d0}_{d1}.csv", url, baixar, f"{pasta.name} {a0}-{a1}"), variavel))
    return pd.concat(partes).sort_index()


def serie_semanal(base: str, variavel: str, lat: float, lon: float, primeira: str, fim: str, arquivo: Path, baixar: bool) -> pd.Series:
    """Uma data a cada 7 dias, numa requisição só."""
    url = f"{base}.csv?{variavel}[({primeira}):7:({fim})]{_trecho(lat, lon, False, True)}"
    return _serie(_arquivo(arquivo, url, baixar, f"semanal {arquivo.stem}"), variavel)


def mmm_oficial(lat: float, lon: float, arquivo: Path, baixar: bool) -> tuple[float, float]:
    """MMM do produto oficial no pixel: temperatura menos HotSpot, em cinco dias. Devolve (mediana, amplitude)."""
    partes = []
    for (base, variavel), nome in ((CRW_SST, "sst"), (CRW_HOTSPOT, "hs")):
        url = f"{base}.csv?{variavel}[(2020-01-01):1:(2020-01-05)]{_trecho(lat, lon, False, True)}"
        partes.append(_serie(_arquivo(arquivo.with_name(f"{arquivo.stem}_{nome}.csv"), url, baixar, f"MMM {arquivo.stem} {nome}"), variavel))
    diferenca = (partes[0] - partes[1]).dropna()
    return round(float(diferenca.median()), 2), round(float(diferenca.max() - diferenca.min()), 3)


def baixar_crw(brutos: Path, fim: str, recifes: list[Recife], baixar: bool) -> dict:
    """Produtos do Coral Reef Watch no pixel de 5 km de mar mais próximo de cada recife."""
    pasta = brutos / "crw"
    pontos = _pontos(pasta, recifes, CRW_SST[0], CRW_SST[1], 0.2, zlev=False, lon_360=True, baixar=baixar)
    saida = {"pontos": {}, "mmm": {}, "mensal": {}, "semanal_sst": {}, "semanal_dhw": {}, "diario_sst": {}, "diario_dhw": {}}
    # Primeiro o que é rápido e vale para todos; depois as séries diárias dos recifes de referência e as semanais.
    for etapa in ("leve", "diario", "semanal"):
        for r in recifes:
            if r.slug not in pontos:
                continue
            lat, lon, _ = pontos[r.slug]
            try:
                if etapa == "leve":
                    saida["mmm"][r.slug] = mmm_oficial(lat, lon, pasta / "mmm" / f"{r.slug}.csv", baixar)
                    url = f"{CRW_MENSAL[0]}.csv?{CRW_MENSAL[1]}[(1985-01-31):1:(2013-01-31)]{_trecho(lat, lon, False, True)}"
                    saida["mensal"][r.slug] = _serie(_arquivo(pasta / "mensal" / f"{r.slug}.csv", url, baixar, f"mensal {r.slug}"), CRW_MENSAL[1])
                elif etapa == "semanal" and r.slug not in REFERENCIA:
                    saida["semanal_sst"][r.slug] = serie_semanal(*CRW_SST, lat, lon, PRIMEIRA_SEMANA_SST, fim, pasta / "semanal" / f"{r.slug}_sst.csv", baixar)
                    saida["semanal_dhw"][r.slug] = serie_semanal(*CRW_DHW, lat, lon, PRIMEIRA_SEMANA_DHW, fim, pasta / "semanal" / f"{r.slug}_dhw.csv", baixar)
                elif etapa == "diario" and r.slug in REFERENCIA:
                    sst = serie_diaria(*CRW_SST, lat, lon, INICIO_SST, fim, pasta / "diario" / f"{r.slug}_sst", False, True, baixar)
                    dhw = serie_diaria(*CRW_DHW, lat, lon, INICIO_DHW, fim, pasta / "diario" / f"{r.slug}_dhw", False, True, baixar)
                    saida["diario_sst"][r.slug], saida["diario_dhw"][r.slug] = sst, dhw
                    # A série semanal dos recifes de referência sai da diária (ver `na_grade_semanal`).
                    saida["semanal_sst"][r.slug], saida["semanal_dhw"][r.slug] = sst, dhw
            except Faltando:
                continue
    saida["pontos"] = pontos
    return saida


def baixar_oisst(brutos: Path, fim: str, recifes: list[Recife], baixar: bool) -> dict:
    """OISST diário dos recifes de referência, na célula de 0,25° de mar mais próxima."""
    pasta = brutos / "oisst"
    referencia = [r for r in recifes if r.slug in REFERENCIA]
    pontos = _pontos(pasta, referencia, ERDDAP_OISST, "sst", 0.6, zlev=True, lon_360=False, baixar=baixar)
    series = {}
    for r in referencia:
        if r.slug not in pontos:
            continue
        lat, lon, _ = pontos[r.slug]
        try:
            series[r.slug] = serie_diaria(ERDDAP_OISST, "sst", lat, lon, INICIO_OISST, fim, pasta / "diario" / r.slug, True, False, baixar)
        except Faltando:
            continue
    return {"pontos": pontos, "diario": series}


def nino_da_caixa(brutos: Path, fim: str, baixar: bool) -> pd.Series:
    """Temperatura média da caixa Niño 3.4 (5°S-5°N, 170°O-120°O) calculada do OISST, para conferir o índice do CPC.

    Para caber numa requisição, usa um dia a cada 28 do eixo de tempo do servidor e um ponto a cada 1° de latitude
    e 2° de longitude (286 pontos). A média é ponderada pelo cosseno da latitude.
    """
    url = f"{ERDDAP_OISST}.csv?sst[(1981-09-06):28:({fim})][(0.0)][(-4.875):4:(4.875)][(-169.875):8:(-120.125)]"
    tabela = _csv_do_erddap(_arquivo(brutos / "nino34" / "caixa_oisst.csv", url, baixar, "caixa Niño 3.4 do OISST"))
    tabela["peso"] = np.cos(np.radians(tabela["latitude"]))
    tabela["ponderado"] = tabela["sst"] * tabela["peso"]
    soma = tabela.groupby("time")[["ponderado", "peso"]].sum()
    serie = soma["ponderado"] / soma["peso"]
    serie.index = pd.to_datetime(serie.index).tz_localize(None).normalize()
    return serie.rename_axis("data").rename("sst_caixa_oisst").sort_index()


def ler_nino_cpc(texto: str) -> pd.DataFrame:
    """Lê o arquivo semanal do CPC (largura fixa): temperatura e anomalia da região Niño 3.4."""
    datas, sst, anomalia = [], [], []
    for linha in texto.splitlines():
        campos = linha.split()
        if not campos or len(campos[0]) != 9:
            continue
        try:
            dia = pd.to_datetime(campos[0], format="%d%b%Y")
        except ValueError:
            continue
        # Depois da data, quatro regiões em blocos de 13 caracteres: Niño 1+2, Niño 3, Niño 3.4 e Niño 4.
        bloco = linha[10:][26:39]
        datas.append(dia)
        sst.append(float(bloco[:9]))
        anomalia.append(float(bloco[9:]))
    return pd.DataFrame({"sst_nino34": sst, "anomalia_cpc": anomalia}, index=pd.DatetimeIndex(datas, name="data"))


def baixar_arquivo(url: str, destino: Path, baixar: bool = True) -> dict:
    """Baixa um arquivo se ainda não existir e devolve tamanho e SHA-256."""
    conteudo = _arquivo(destino, url, baixar, destino.name)
    return {"arquivo": destino.name, "bytes": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}


def baixar_apoio(brutos: Path, baixar: bool) -> tuple[dict, dict, dict]:
    """Os três arquivos pequenos: índice Niño 3.4 do CPC, base de branqueamento e linha de costa."""
    return (
        baixar_arquivo(URL_NINO_CPC, brutos / "nino34" / "wksst9120.for", baixar),
        baixar_arquivo(URL_BRANQUEAMENTO, brutos / "branqueamento" / "global_bleaching_environmental.csv", baixar),
        baixar_arquivo(URL_COSTA, brutos / "costa" / "ne_110m_coastline.geojson", baixar),
    )


def distancia_km(lat1, lon1, lat2: float, lon2: float) -> np.ndarray:
    """Distância de círculo máximo (haversine), em km."""
    lat1, lon1 = np.radians(np.asarray(lat1, dtype=float)), np.radians(np.asarray(lon1, dtype=float))
    lat2, lon2 = np.radians(lat2), np.radians(lon2)
    a = np.sin((lat1 - lat2) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon1 - lon2) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def extrato_de_branqueamento(bruto: pd.DataFrame, recifes: list[Recife] = RECIFES, raio_km: float = RAIO_BRANQUEAMENTO_KM) -> tuple[pd.DataFrame, dict]:
    """Agrega os levantamentos de branqueamento a até `raio_km` de cada recife.

    A base repete o mesmo levantamento em várias linhas (uma por substrato). Aqui cada levantamento (fonte, local
    e data) vira uma linha, e o extrato versionado guarda uma linha por recife, data e fonte, com o número de
    levantamentos e a média do percentual de coral branqueado.
    """
    funil = {"linhas_na_base": int(len(bruto))}
    bruto = bruto.assign(percentual=pd.to_numeric(bruto["Percent_Bleaching"], errors="coerce"), data=pd.to_datetime(bruto["Date"], errors="coerce"))
    bruto = bruto.dropna(subset=["percentual", "data", "Latitude_Degrees", "Longitude_Degrees"])
    funil["com_percentual_e_data"] = int(len(bruto))
    levantamentos = bruto.groupby(["Data_Source", "Latitude_Degrees", "Longitude_Degrees", "data"], as_index=False)["percentual"].mean()
    funil["levantamentos_unicos"] = int(len(levantamentos))
    partes = []
    for r in recifes:
        km = distancia_km(levantamentos["Latitude_Degrees"], levantamentos["Longitude_Degrees"], r.lat, r.lon)
        partes.append(levantamentos[km <= raio_km].assign(slug=r.slug, km=km[km <= raio_km]))
    perto = pd.concat(partes, ignore_index=True)
    funil["levantamentos_perto_dos_recifes"] = int(len(perto))
    extrato = (
        perto.groupby(["slug", "data", "Data_Source"])
        .agg(levantamentos=("percentual", "size"), percentual_medio=("percentual", "mean"), km_medio=("km", "mean"))
        .reset_index()
        .rename(columns={"Data_Source": "fonte"})
    )
    extrato["percentual_medio"] = extrato["percentual_medio"].round(2)
    extrato["km_medio"] = extrato["km_medio"].round(1)
    funil["linhas_do_extrato"] = int(len(extrato))
    funil["recifes_com_levantamento"] = int(extrato["slug"].nunique())
    return extrato, funil


def na_grade_semanal(serie: pd.Series, fim: str, tolerancia_dias: int = 3) -> pd.Series:
    """Leva uma série para a grade semanal comum (1985-01-06 mais múltiplos de 7 dias).

    O ERDDAP conta "uma data a cada 7" pela posição no eixo de tempo, não pelo calendário. Como o produto tem
    alguns dias faltando, depois de cada falta as datas devolvidas escorregam um dia. Aqui cada data da grade
    recebe a leitura mais próxima, a no máximo `tolerancia_dias` de distância; sem leitura por perto, fica vazia.
    """
    grade = pd.date_range(PRIMEIRA_SEMANA_SST, fim, freq="7D", name="data")
    serie = serie[~serie.index.duplicated()].sort_index()
    return serie.reindex(grade, method="nearest", tolerance=pd.Timedelta(days=tolerancia_dias))


def _larga(series: dict, casas: int = 2) -> pd.DataFrame:
    return pd.DataFrame(series).sort_index().rename_axis("data").round(casas)


def montar_extrato(raiz: Path, fim_oisst: str, fim_crw: str, baixar: bool = True) -> dict:
    """Baixa o que faltar em data/brutos/ e grava o extrato versionado em data/.

    Com `baixar=False`, monta o extrato só com o que já está em data/brutos/ (útil se o download foi interrompido):
    entram os recifes que já têm a série semanal completa.
    """
    brutos = raiz / "data" / "brutos"
    saida = raiz / "data"
    crw = baixar_crw(brutos, fim_crw, RECIFES, baixar)
    oisst = baixar_oisst(brutos, fim_oisst, RECIFES, baixar)
    info_nino, info_branq, info_costa = baixar_apoio(brutos, baixar)

    completos = [r for r in RECIFES if r.slug in crw["semanal_dhw"] and r.slug in crw["mensal"] and (r.slug not in REFERENCIA or r.slug in oisst["diario"])]
    slugs = [r.slug for r in completos]
    referencia = [s for s in slugs if s in REFERENCIA]
    tabela = pd.DataFrame([r.__dict__ for r in completos]).set_index("slug")
    tabela["referencia"] = [s in REFERENCIA for s in slugs]
    tabela["lat_crw"] = [crw["pontos"][s][0] for s in slugs]
    tabela["lon_crw"] = [crw["pontos"][s][1] for s in slugs]
    tabela["km_crw"] = [crw["pontos"][s][2] for s in slugs]
    tabela["mmm_noaa"] = [crw["mmm"][s][0] for s in slugs]
    for coluna, i in (("lat_oisst", 0), ("lon_oisst", 1), ("km_oisst", 2)):
        tabela[coluna] = [oisst["pontos"][s][i] if s in referencia else None for s in slugs]
    tabela.to_csv(saida / "recifes.csv", encoding="utf-8", lineterminator="\n")

    opcoes = {"float_format": "%.2f", "date_format": "%Y-%m-%d", "lineterminator": "\n"}
    desvio = 0
    for s in slugs:
        if s not in referencia:
            resto = np.asarray((crw["semanal_sst"][s].index - pd.Timestamp(PRIMEIRA_SEMANA_SST)).days % 7)
            desvio = max(desvio, int(np.minimum(resto, 7 - resto).max()))
    semanal_sst = _larga({s: na_grade_semanal(crw["semanal_sst"][s], fim_crw) for s in slugs})
    semanal_dhw = _larga({s: na_grade_semanal(crw["semanal_dhw"][s], fim_crw) for s in slugs})
    semanal_dhw = semanal_dhw[semanal_dhw.index >= PRIMEIRA_SEMANA_DHW]
    mensal = _larga({s: crw["mensal"][s] for s in slugs})
    semanal_sst.to_csv(saida / "sst_semanal_coraltemp.csv", **opcoes)
    semanal_dhw.to_csv(saida / "dhw_semanal_noaa.csv", **opcoes)
    mensal.to_csv(saida / "sst_mensal_coraltemp.csv", **opcoes)
    diario_sst = _larga({s: crw["diario_sst"][s] for s in referencia})
    diario_dhw = _larga({s: crw["diario_dhw"][s] for s in referencia})
    diario_oisst = _larga({s: oisst["diario"][s] for s in referencia})
    diario_sst.to_csv(saida / "referencia_sst_diaria_coraltemp.csv", **opcoes)
    diario_dhw.to_csv(saida / "referencia_dhw_diario_noaa.csv", **opcoes)
    diario_oisst.to_csv(saida / "referencia_sst_diaria_oisst.csv", **opcoes)

    nino = ler_nino_cpc((brutos / "nino34" / "wksst9120.for").read_text(encoding="latin-1"))
    nino.to_csv(saida / "nino34_semanal.csv", float_format="%.1f", date_format="%Y-%m-%d", lineterminator="\n")
    try:
        caixa = nino_da_caixa(brutos, fim_oisst, baixar)
        caixa.to_frame().to_csv(saida / "nino34_caixa_oisst.csv", float_format="%.3f", date_format="%Y-%m-%d", lineterminator="\n")
    except Faltando:
        caixa = None
    bruto = pd.read_csv(brutos / "branqueamento" / "global_bleaching_environmental.csv", low_memory=False)
    branqueamento, funil = extrato_de_branqueamento(bruto, completos)
    branqueamento.to_csv(saida / "branqueamento_perto_dos_recifes.csv", index=False, date_format="%Y-%m-%d", lineterminator="\n")
    (saida / "costa_110m.geojson").write_bytes((brutos / "costa" / "ne_110m_coastline.geojson").read_bytes())

    def periodo(t: pd.DataFrame) -> dict:
        return {"inicio": str(t.index.min().date()), "fim": str(t.index.max().date()), "datas": int(len(t)), "lacunas": int(t.isna().sum().sum())}

    coleta = {
        "coletado_em": date.today().isoformat(),
        "recifes": len(slugs),
        "recifes_de_referencia": referencia,
        "crw": {
            "servidor": ERDDAP_CRW,
            "conjuntos": [CRW_SST[0].rsplit("/", 1)[1], CRW_DHW[0].rsplit("/", 1)[1], CRW_HOTSPOT[0].rsplit("/", 1)[1], CRW_MENSAL[0].rsplit("/", 1)[1]],
            "semanal_sst": periodo(semanal_sst),
            "semanal_dhw": periodo(semanal_dhw),
            "mensal": periodo(mensal),
            "diario_sst": periodo(diario_sst),
            "diario_dhw": periodo(diario_dhw),
            "amplitude_maxima_do_mmm_lido": max(crw["mmm"][s][1] for s in slugs),
            "dias_faltando_no_eixo_de_tempo": int(len(pd.date_range(diario_sst.index.min(), diario_sst.index.max(), freq="D")) - len(diario_sst)) if len(diario_sst) else None,
            "maior_desvio_da_grade_semanal_dias": desvio,
        },
        "oisst": {"servidor": ERDDAP_OISST, "diario": periodo(diario_oisst)},
        "nino34": {**info_nino, "url": URL_NINO_CPC, "semanas": int(len(nino)), "inicio": str(nino.index.min().date()), "fim": str(nino.index.max().date()), "datas_da_caixa_do_oisst": 0 if caixa is None else int(len(caixa))},
        "branqueamento": {**info_branq, "url": URL_BRANQUEAMENTO, "raio_km": RAIO_BRANQUEAMENTO_KM, "funil": funil},
        "costa": {**info_costa, "url": URL_COSTA},
    }
    (saida / "coleta.json").write_text(json.dumps(coleta, indent=2, ensure_ascii=False), encoding="utf-8")
    return coleta
