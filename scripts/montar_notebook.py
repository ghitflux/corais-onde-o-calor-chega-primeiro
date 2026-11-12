"""Monta analise.ipynb com nbformat. Depois de montar, execute:

    uv run python scripts/montar_notebook.py
    uv run jupyter nbconvert --to notebook --execute --inplace analise.ipynb

O notebook é uma narrativa fina: lê o extrato de data/ e as tabelas de reports/resultados.json (geradas por
scripts/rodar_analise.py) e conta a história. Os bootstraps e os ajustes rodam no script, não aqui.
"""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

RAIZ = Path(__file__).resolve().parents[1]

CELULAS: list[tuple[str, str]] = [
    ("md", """# Em quais recifes o estresse térmico que branqueia corais chega mais cedo e mais vezes, e dá para avisar com antecedência?

Corais branqueiam quando a água fica quente demais por tempo demais. A NOAA Coral Reef Watch mede isso por satélite
com o **Degree Heating Week (DHW)**: quanto a temperatura passou do máximo normal do lugar, acumulado em 12 semanas.
A decisão que este estudo informa é que recifes priorizar para monitoramento e resposta, e com quantas semanas de
antecedência um alerta simples é confiável.

O caminho: (1) refazer o DHW a partir da temperatura e conferir com o produto oficial; (2) medir ondas de calor
marinhas; (3) medir a tendência dos anos de estresse severo, com incerteza honesta; (4) testar a previsão contra a
persistência; (5) ordenar os recifes e medir a incerteza da ordem; (6) conferir com branqueamento observado em campo.

É análise de dado público, feita por um profissional de dados, não por um biólogo. Os números vêm de
`reports/resultados.json`; o método está em `src/corais_calor/` e é conferido em `tests/`."""),
    ("code", """import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import display

from corais_calor import analise, dados, dhw, graficos, ondas

pd.set_option("display.float_format", lambda v: f"{v:,.3f}")
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 60)
pd.set_option("display.max_colwidth", 90)
r = json.loads(Path("reports/resultados.json").read_text(encoding="utf-8"))
base = dados.carregar()
series, diarias = analise.preparar(base)


def mostrar(figura):
    display(figura)
    plt.close(figura)


print("Coleta:", r["coleta"]["coletado_em"], "|", len(series), "recifes |", len(diarias), "recifes de referência")"""),
    ("md", """## 1. Os recifes e os dados

Um ponto por recife, em seis bacias. A coordenada de referência vem da Wikipedia ou do Wikidata; o pixel usado é o
de mar mais próximo na grade de 5 km da NOAA. Para todos os recifes há o DHW oficial e a temperatura (CoralTemp) numa
data a cada 7 dias desde 1985. Para seis **recifes de referência**, um por bacia, há também as séries diárias
completas (DHW oficial, CoralTemp e OISST): o servidor lê um arquivo por dia, e cada série diária de 40 anos leva de
8 a 20 minutos."""),
    ("code", """display(base.recifes[["nome", "regiao", "grupo", "lat", "lon", "lat_crw", "lon_crw", "km_crw", "mmm_noaa", "referencia"]])
display(pd.Series({k: v for k, v in r["coleta"]["crw"].items() if isinstance(v, dict)}).apply(pd.Series))"""),
    ("md", """## 2. O DHW foi entendido? Refazer e conferir

O DHW do dia é a soma, nos 84 dias anteriores, de quanto a temperatura passou do **MMM** (a média do mês mais quente
da climatologia), contando só os dias com 1 °C ou mais de excesso, dividida por 7. A climatologia da NOAA usa
1985-2012 e é recentrada pela tendência para 1988,286.

Quatro degraus de conferência, do mais controlado ao menos:

- **algoritmo**: temperatura e MMM oficiais; só a acumulação é refeita;
- **climatologia**: a mesma temperatura, com o MMM recalculado aqui a partir da média mensal;
- **outro produto**: temperatura do OISST (0,25°) e MMM calculado no próprio OISST;
- **semanal**: uma temperatura a cada 7 dias, em todos os recifes."""),
    ("code", """conf = r["conferencia_do_dhw"]
resumo = pd.DataFrame({k: {c: v for c, v in d.items() if not isinstance(v, dict)} for k, d in conf["resumo"].items()}).T
resumo["concordância DHW ≥ 4"] = [conf["resumo"][k]["dhw4"]["concordancia"] for k in resumo.index]
resumo["kappa DHW ≥ 4"] = [conf["resumo"][k]["dhw4"]["kappa"] for k in resumo.index]
display(resumo)
display(pd.Series({k: v for k, v in conf["mmm"].items() if k != "por_recife"}, name="MMM calculado menos MMM oficial (°C)").to_frame())
display(pd.DataFrame(conf["por_recife"]).set_index("nome"))"""),
    ("code", """rc, ro = conf["resumo"]["climatologia"], conf["resumo"]["outro_produto"]
mostrar(graficos.conferencia_do_dhw(
    conf,
    "DHW máximo do ano: refeito contra oficial",
    f"Cada ponto é um ano num dos {len(diarias)} recifes de referência. Linhas finas: os limiares de 4 e 8.",
))"""),
    ("md", """Um exemplo dia a dia: o recife de referência com o maior DHW da série. A linha do DHW refeito com a temperatura e
o MMM oficiais fica em cima da linha oficial."""),
    ("code", """d = max(diarias, key=lambda x: np.nanmax(x.dhw_noaa))
pico = int(np.nanargmax(d.dhw_noaa))
trecho = slice(max(pico - 250, 0), pico + 200)
serie_oisst = pd.Series(d.sst_oisst, index=d.datas_oisst)
mmm_oisst = dhw.mmm(dhw.climatologia_mensal(d.datas_oisst, d.sst_oisst))
comparacao = pd.DataFrame({
    "oficial (NOAA)": d.dhw_noaa,
    "refeito: CoralTemp e MMM oficial": dhw.dhw(d.sst, d.serie.mmm_noaa),
    "refeito: OISST e MMM do OISST": pd.Series(dhw.dhw(d.sst_oisst, mmm_oisst), index=d.datas_oisst).reindex(d.datas).to_numpy(),
}, index=pd.DatetimeIndex(d.datas))
eixo = comparacao.iloc[trecho].plot(figsize=(9, 3.6), title=f"{d.nome}: DHW dia a dia em torno do maior evento")
eixo.set_ylabel("°C-semana")
plt.show()"""),
    ("md", """## 3. Ondas de calor marinhas (Hobday et al. 2016)

Definição: cinco dias ou mais acima do percentil 90 do dia do ano, medido em 1983-2012 no OISST diário. Aqui só nos
recifes de referência, que são os que têm a série diária. O limiar é fixo; com o mar aquecendo, mais dias passam dele.
É o que a definição mede, e não separa tendência de variabilidade."""),
    ("code", """oc = r["ondas_de_calor"]
display(pd.DataFrame(oc["por_decada"]).set_index("periodo")[["eventos_por_ano", "dias_por_ano", "duracao_media", "intensidade_maxima_media"]])
linhas = {x["nome"]: {dec["periodo"]: dec["dias_por_ano"] for dec in x["decadas"]} | {"dias a mais por década": x["dias_a_mais_por_decada"], "maior evento": x["maior_evento"]["inicio"], "duração (dias)": x["maior_evento"]["duracao"]} for x in oc["por_recife"]}
display(pd.DataFrame(linhas).T)"""),
    ("md", """## 4. A tendência dos anos de estresse severo

Para cada recife e cada ano de estresse (a janela de 12 meses em torno do mês mais quente), o máximo do DHW oficial.
Um ano conta como "de alerta" se o máximo passa de 4 °C-semana e como "severo" se passa de 8.

No conjunto, a fração de recifes atingidos por ano entra numa regressão binomial sobre o ano. O intervalo vem de um
bootstrap que sorteia **anos inteiros em blocos de 4**: os recifes de um mesmo ano não são independentes (um El Niño
atinge muitos de uma vez), e sortear a linha do ano inteira preserva isso."""),
    ("code", """t = r["tendencias"]
mostrar(graficos.fracao_por_ano(t, analise.EVENTOS_GLOBAIS, "Fração dos recifes em estresse severo, por ano", "Em cinza, os eventos globais de branqueamento registrados pela NOAA."))
for chave in ("dhw4", "dhw8"):
    c = t[chave]["conjunto"]
    print(chave, "| razão de chances por década:", round(c["razao_de_chances_por_decada"], 2), [round(v, 2) for v in c["razao_de_chances_ic"]], "| superdispersão:", round(c["superdispersao"], 1))
    display(pd.Series(t[chave]["contagem"], name=chave).to_frame().T)"""),
    ("md", """Os eventos globais de branqueamento que a NOAA registra (1998, 2010, 2014-2017 e 2023-2024) aparecem nas séries?"""),
    ("code", """g = r["eventos_globais"]["dhw4"]
display(pd.DataFrame(g["por_evento"]).T)
display(pd.DataFrame(g["dez_piores_anos"]))
print("média nos anos de evento global:", round(g["media_nos_anos_de_evento"], 3), "| nos outros anos:", round(g["media_nos_outros_anos"], 3))"""),
    ("md", """### Intervalo de retorno, antes e depois de 2005

O intervalo de retorno é o número médio de anos entre dois anos de alerta: o inverso da frequência."""),
    ("code", """linhas = []
for chave in ("dhw4", "dhw8"):
    for nome, x in t[chave]["retorno"].items():
        linhas.append({"limiar": chave, "recorte": nome, "recifes": x["recifes"], "retorno 1985-2004": x["antes"]["retorno"], "retorno 2005-2024": x["depois"]["retorno"], "razão de frequência": x["razao_de_frequencia"], "IC 95%": x["razao_ic"]})
display(pd.DataFrame(linhas).set_index(["limiar", "recorte"]))
mostrar(graficos.retorno_por_regiao(t, "dhw4", "Intervalo de retorno do alerta (DHW ≥ 4) antes e depois de 2005", "Anos, em média, entre dois anos de alerta. Entre parênteses, o número de recifes."))"""),
    ("md", """### Recife a recife, com correção para múltiplas comparações

Com cerca de 40 anos e poucos eventos por recife, a tendência individual é incerta. O valor-p vem de uma permutação
em blocos; `p_bh` é o valor ajustado por Benjamini-Hochberg entre os recifes com algum evento."""),
    ("code", """por_recife = pd.DataFrame(t["dhw4"]["por_recife"])
por_recife["décadas"] = por_recife["por_decada"].apply(lambda v: " | ".join(str(x) for x in v))
display(por_recife.set_index("nome")[["grupo", "eventos", "décadas", "primeiro_ano", "inclinacao", "ic", "p", "p_bh"]].sort_values("p"))"""),
    ("md", """## 5. Dá para avisar com antecedência?

O alvo: na data-alvo, dentro da estação quente, o DHW do recife estará em 4 ou mais? Previsões emitidas 4, 8 e 12
semanas antes. Treino com alvos até 2010; teste de 2011 em diante.

- **Persistência da anomalia**: a anomalia de hoje continua; projeta-se a temperatura e calcula-se o DHW.
- **Climatologia**: a frequência do alerta naquele recife e época do ano, no treino.
- **Modelo simples**: logística com a anomalia, a tendência de 4 semanas, o DHW de hoje, a posição na estação e o
  Niño 3.4 (com um coeficiente por bacia)."""),
    ("code", """p = r["previsao"]
linhas = []
for semanas, x in p["antecedencias"].items():
    for nome, m in x["metodos"].items():
        linhas.append({"semanas": int(semanas), "método": m["rotulo"], "Brier": m["brier"], "IC inf.": m["brier_ic"][0], "IC sup.": m["brier_ic"][1], "ganho sobre a climatologia": m["ganho_sobre_climatologia"], "AUC": m["auc"], "Brier (fora do alerta)": m["brier_fora_do_alerta"], "AUC (fora do alerta)": m["auc_fora_do_alerta"], "alertas confirmados": m["alerta"]["precisao"], "eventos avisados": m["alerta"]["avisados"]})
display(pd.DataFrame(linhas).set_index(["semanas", "método"]))
display(pd.DataFrame({s: x["teste"] for s, x in p["antecedencias"].items()}))
mostrar(graficos.previsao_por_antecedencia(p, "Erro de cada método por antecedência e confiabilidade a 8 semanas", "Previsão de DHW ≥ 4 na estação quente; teste de 2011 em diante."))"""),
    ("code", """linhas = []
for semanas, x in p["antecedencias"].items():
    for nome, c in x["comparacoes"].items():
        linhas.append({"semanas": int(semanas), "comparação (diferença de Brier)": nome.replace("_menos_", " − "), "diferença": c["diferenca"], "IC inf.": c["ic"][0], "IC sup.": c["ic"][1], "P(primeiro melhor)": c["prob_primeiro_melhor"]})
display(pd.DataFrame(linhas).set_index(["semanas", "comparação (diferença de Brier)"]))
display(pd.DataFrame({s: x["coeficientes"]["modelo"] for s, x in p["antecedencias"].items()}))"""),
    ("md", """## 6. Ranking de exposição e a incerteza do ranking

Exposição em 2005-2024: fração de anos com DHW de 4 ou mais, somada à fração com 8 ou mais. A incerteza do posto vem
de sortear de novo os anos (em blocos, os mesmos para todos os recifes). **Exposição térmica não é branqueamento**:
profundidade, turbidez, aclimatação e espécie mudam o resultado."""),
    ("code", """k = r["ranking"]
display(pd.DataFrame(k["por_recife"]).set_index("posto")[["nome", "grupo", "anos_dhw4", "anos_dhw8", "dhw_maximo", "prob_terco_mais_exposto", "posto_ic"]])
mostrar(graficos.ranking_com_incerteza(k, "Probabilidade de cada recife estar no terço mais exposto", "Exposição em 2005-2024."))
mostrar(graficos.mapa_de_exposicao(base.recifes, base.costa, k, [x["slug"] for x in k["por_recife"][:6]], "Onde o alerta veio mais vezes em 2005-2024", "Um ponto por recife."))"""),
    ("md", """## 7. O satélite contra o que se viu em campo

A base de van Woesik e Burkepile (2022) reúne levantamentos de branqueamento com data e local. Para cada levantamento
a até 100 km de um recife do estudo, o estresse é o maior DHW oficial do ponto nas 12 semanas anteriores."""),
    ("code", """bo = r["branqueamento_observado"]
print({c: bo[c] for c in ("linhas", "levantamentos", "recifes", "recifes_ano", "anos")}, bo["por_fonte"])
display(pd.DataFrame(bo["por_faixa"]).set_index("faixa_dhw"))
display(pd.DataFrame(bo["limiares"]).T)
print(bo.get("so_reef_check"))"""),
    ("md", """## 8. O que levar daqui

- Refazer o índice oficial é o primeiro teste: com a mesma temperatura e o mesmo MMM, a acumulação reproduz o produto
  da NOAA; as diferenças que sobram vêm da climatologia e, sobretudo, do produto de temperatura.
- No conjunto dos recifes a tendência é clara; recife a recife, 40 anos com poucos eventos sustentam menos, e a
  correção para múltiplas comparações tira parte das tendências "significativas".
- A persistência da anomalia é uma linha de base forte. O modelo simples ganha dela com 4 semanas, empata com 8 e
  perde com 12; o índice Niño 3.4 não acrescentou nada mensurável.
- O ranking tem um topo e um fundo firmes e um meio indefinido. E o topo inclui lugares conhecidos por corais
  tolerantes ao calor: exposição térmica não é branqueamento.
- Com levantamentos de rotina (Reef Check), o DHW do ponto do recife quase não separa quem branqueou de quem não.
- O README lista onde o estudo falha e o que faltaria para isto virar contribuição científica."""),
]


def main() -> None:
    caderno = new_notebook()
    caderno.cells = [new_markdown_cell(texto) if tipo == "md" else new_code_cell(texto) for tipo, texto in CELULAS]
    caderno.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    caderno.metadata["language_info"] = {"name": "python"}
    nbformat.write(caderno, RAIZ / "analise.ipynb")
    print(f"analise.ipynb montado com {len(caderno.cells)} células")


if __name__ == "__main__":
    main()
