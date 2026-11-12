"""Imprime, em Markdown, as tabelas do README a partir de reports/resultados.json.

    uv run python scripts/tabelas_do_readme.py > tabelas.md

Serve para conferir o README: toda tabela dele é uma destas, copiada sem editar os números.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def n(valor, casas: int = 2) -> str:
    """Número com vírgula decimal; nulo (infinito no JSON) vira travessão."""
    if valor is None:
        return "—"
    return f"{valor:.{casas}f}".replace(".", ",")


def pc(valor, casas: int = 0) -> str:
    return "—" if valor is None else f"{valor * 100:.{casas}f}%".replace(".", ",")


def faixa(par, casas: int = 2) -> str:
    return f"{n(par[0], casas)} a {n(par[1], casas)}"


def tabela(cabecalho: list[str], linhas: list[list[str]]) -> None:
    print("| " + " | ".join(cabecalho) + " |")
    print("|" + "---|" * len(cabecalho))
    for linha in linhas:
        print("| " + " | ".join(str(c) for c in linha) + " |")
    print()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    r = json.loads((RAIZ / "reports" / "resultados.json").read_text(encoding="utf-8"))
    conf, tend, prev, rank, branq, ondas = (r[k] for k in ("conferencia_do_dhw", "tendencias", "previsao", "ranking", "branqueamento_observado", "ondas_de_calor"))

    print("## Recifes\n")
    tabela(
        ["Recife", "Região", "Lat. ref.", "Lon. ref.", "Pixel NOAA (lat, lon)", "MMM (°C)", "Fonte da coordenada"],
        [[("**" + x["nome"] + "**") if x["referencia"] else x["nome"], x["regiao"], n(x["lat"], 3), n(x["lon"], 3), f"{n(x['lat_crw'], 3)}; {n(x['lon_crw'], 3)}", n(x["mmm_noaa"]), x["fonte"]] for x in r["recifes"]],
    )

    print("## DHW refeito contra o oficial (máximo anual)\n")
    nomes = {
        "algoritmo": "Algoritmo: temperatura e MMM oficiais, diário",
        "climatologia": "Climatologia: mesma temperatura, MMM refeito",
        "outro_produto": "Outro produto: OISST diário, MMM do OISST",
        "semanal": "Semanal: uma temperatura a cada 7 dias, MMM oficial",
        "amostragem_semanal": "Produto oficial lido 1 dia em 7, contra todos os dias",
    }
    tabela(
        ["Degrau", "Recifes-ano", "Correlação", "Viés", "Erro médio", "Erro máximo", "Concordância em DHW ≥ 4 (kappa)", "Só o refeito / só o oficial"],
        [
            [nomes[k], v["recifes_ano"], n(v["correlacao_do_maximo_anual"], 3), n(v["vies_do_maximo_anual"]), n(v["erro_absoluto_do_maximo_anual"]), n(v["erro_maximo_do_maximo_anual"]), f"{pc(v['dhw4']['concordancia'], 1)} ({n(v['dhw4']['kappa'])})", f"{v['dhw4']['so_reimplementado']} / {v['dhw4']['so_oficial']}"]
            for k, v in conf["resumo"].items()
        ],
    )
    tabela(
        ["Recife de referência", "MMM oficial", "MMM refeito", "MMM do OISST", "Erro diário: algoritmo", "Erro diário: OISST", "DHW máximo: oficial", "DHW máximo: OISST"],
        [[x["nome"], n(x["mmm_noaa"]), n(x["mmm_coraltemp"]), n(x["mmm_oisst"]), n(x["erro_diario_algoritmo"], 4), n(x["erro_diario_outro_produto"]), n(x["dhw_maximo_noaa"]), n(x["dhw_maximo_outro_produto"])] for x in conf["por_recife"]],
    )
    print("MMM:", {k: v for k, v in conf["mmm"].items() if k != "por_recife"})
    print("Lacunas do OISST:", conf["lacunas_do_oisst"], "\n")

    print("## Ondas de calor marinhas (recifes de referência)\n")
    periodos = [d["periodo"] for d in ondas["por_decada"]]
    tabela(
        ["Recife"] + [f"Dias por ano, {p}" for p in periodos] + ["Dias a mais por década", "Maior evento (início, duração)"],
        [[x["nome"]] + [n(d["dias_por_ano"], 0) for d in x["decadas"]] + [n(x["dias_a_mais_por_decada"], 0), f"{x['maior_evento']['inicio']}, {x['maior_evento']['duracao']} dias"] for x in ondas["por_recife"]]
        + [["**Média**"] + [n(d["dias_por_ano"], 0) for d in ondas["por_decada"]] + ["", ""]],
    )
    tabela(
        ["Década", "Eventos por ano", "Dias por ano", "Duração média (dias)", "Intensidade máxima média (°C)"],
        [[d["periodo"], n(d["eventos_por_ano"], 1), n(d["dias_por_ano"], 0), n(d["duracao_media"], 0), n(d["intensidade_maxima_media"])] for d in ondas["por_decada"]],
    )

    print("## Tendência\n")
    for chave in ("dhw4", "dhw8"):
        c = tend[chave]["conjunto"]
        print(f"{chave}: razão de chances por década {n(c['razao_de_chances_por_decada'])} ({faixa(c['razao_de_chances_ic'])}); Poisson {n(c['fator_poisson_por_decada'])} ({faixa(c['fator_poisson_ic'])}); superdispersão {n(c['superdispersao'], 1)}; P(inclinação > 0) {n(c['prob_inclinacao_positiva'], 3)}")
        print("   contagem:", tend[chave]["contagem"])
    print()
    anos = tend["anos"]
    for chave in ("dhw4", "dhw8"):
        f = tend[chave]["conjunto"]["fracao_por_ano"]
        print(chave, "fração por ano:", ", ".join(f"{a}: {pc(v)}" for a, v in zip(anos, f)))
    print()
    g = r["eventos_globais"]
    tabela(
        ["Evento global (NOAA)", "Maior fração com DHW ≥ 4", "Maior fração com DHW ≥ 8"],
        [[k, pc(g["dhw4"]["por_evento"][k]["fracao_maxima"]), pc(g["dhw8"]["por_evento"][k]["fracao_maxima"])] for k in g["dhw4"]["por_evento"]],
    )
    print("dhw4 média nos anos de evento:", pc(g["dhw4"]["media_nos_anos_de_evento"]), "| nos outros:", pc(g["dhw4"]["media_nos_outros_anos"]), "| piores:", [(d["ano"], pc(d["fracao"]), d["evento_global"]) for d in g["dhw4"]["dez_piores_anos"]], "| fora dos eventos com 20% ou mais:", g["dhw4"]["anos_fora_dos_eventos_acima_de_20"], "\n")

    print("## Intervalo de retorno\n")
    for chave in ("dhw4", "dhw8"):
        tabela(
            [f"Recorte ({chave})", "Recifes", "1985-2004 (IC 95%)", "2005-2024 (IC 95%)", "Frequência: depois / antes (IC 95%)"],
            [
                [nome, x["recifes"], f"{n(x['antes']['retorno'], 1)} ({faixa(x['antes']['retorno_ic'], 1)})", f"{n(x['depois']['retorno'], 1)} ({faixa(x['depois']['retorno_ic'], 1)})", f"{n(x['razao_de_frequencia'], 1)} ({faixa(x['razao_ic'], 1) if x['razao_ic'] else '—'})"]
                for nome, x in tend[chave]["retorno"].items()
            ],
        )

    print("## Por recife (ordem do ranking)\n")
    t4 = {x["slug"]: x for x in tend["dhw4"]["por_recife"]}
    t8 = {x["slug"]: x for x in tend["dhw8"]["por_recife"]}
    tabela(
        ["Posto", "Recife", "Anos com DHW ≥ 4 por década", "Anos com DHW ≥ 8 por década", "1º ano ≥ 4", "Tendência ≥ 4 (IC 95%)", "p", "p ajustado", "Retorno 85-04 → 05-24", "P(terço mais exposto)", "Posto (5% a 95%)"],
        [
            [
                k["posto"], k["nome"], " / ".join(str(v) for v in t4[k["slug"]]["por_decada"]) + f" (+{t4[k['slug']]['depois_de_2024']})", " / ".join(str(v) for v in t8[k["slug"]]["por_decada"]) + f" (+{t8[k['slug']]['depois_de_2024']})",
                t4[k["slug"]]["primeiro_ano"] or "—", f"{n(t4[k['slug']]['inclinacao'])} ({faixa(t4[k['slug']]['ic']) if t4[k['slug']]['ic'][0] is not None else '—'})", n(t4[k["slug"]]["p"], 3), n(t4[k["slug"]]["p_bh"], 3),
                f"{n(t4[k['slug']]['retorno_antes']['retorno'], 1)} → {n(t4[k['slug']]['retorno_depois']['retorno'], 1)}", pc(k["prob_terco_mais_exposto"]), f"{k['posto_ic'][0]} a {k['posto_ic'][1]}",
            ]
            for k in rank["por_recife"]
        ],
    )
    print("ranking:", {k: v for k, v in rank.items() if k != "por_recife"}, "\n")

    print("## Previsão\n")
    for semanas, x in prev["antecedencias"].items():
        print(f"{semanas} semanas | treino {x['treino']} | teste {x['teste']}")
    print("Niño:", prev["nino"], "\n")
    ordem = ["climatologia", "persistencia", "persistencia_calibrada", "modelo", "modelo_com_projecao", "modelo_sem_nino"]
    tabela(
        ["Antecedência", "Método", "Brier (IC 95%)", "Ganho sobre a climatologia", "AUC", "Brier fora do alerta", "AUC fora do alerta", "Alertas confirmados", "Eventos avisados"],
        [
            [f"{s} semanas" if m == ordem[0] else "", x["metodos"][m]["rotulo"], f"{n(x['metodos'][m]['brier'], 3)} ({faixa(x['metodos'][m]['brier_ic'], 3)})", pc(x["metodos"][m]["ganho_sobre_climatologia"]), n(x["metodos"][m]["auc"]), n(x["metodos"][m]["brier_fora_do_alerta"], 3), n(x["metodos"][m]["auc_fora_do_alerta"]), pc(x["metodos"][m]["alerta"]["precisao"]), pc(x["metodos"][m]["alerta"]["avisados"])]
            for s, x in prev["antecedencias"].items()
            for m in ordem
        ],
    )
    tabela(
        ["Antecedência", "Comparação (diferença de Brier; negativo: o primeiro é melhor)", "Diferença (IC 95%)", "P(primeiro melhor)"],
        [[f"{s} semanas", k.replace("_menos_", " − "), f"{n(c['diferenca'], 4)} ({faixa(c['ic'], 4)})", n(c["prob_primeiro_melhor"])] for s, x in prev["antecedencias"].items() for k, c in x["comparacoes"].items()],
    )
    tabela(
        ["Antecedência", "Método", "Alertas fora do alerta", "Confirmados", "Eventos novos avisados"],
        [[f"{s} semanas", x["metodos"][m]["rotulo"], x["metodos"][m]["alerta_fora_do_alerta"]["alertas"], pc(x["metodos"][m]["alerta_fora_do_alerta"]["precisao"]), pc(x["metodos"][m]["alerta_fora_do_alerta"]["avisados"])] for s, x in prev["antecedencias"].items() for m in ("persistencia", "persistencia_calibrada", "modelo", "modelo_com_projecao")],
    )
    for s, x in prev["antecedencias"].items():
        print(f"coeficientes do modelo a {s} semanas:", x["coeficientes"]["modelo"])
    print()

    print("## Branqueamento observado\n")
    print({k: v for k, v in branq.items() if k not in ("por_faixa", "limiares", "por_recife")})
    tabela(
        ["DHW máximo nas 12 semanas anteriores", "Linhas", "Percentual médio branqueado", "Com 10% ou mais", "Com 30% ou mais"],
        [[x["faixa_dhw"], x["linhas"], n(x["percentual_medio"], 1), pc(x["fracao_com_10_ou_mais"]), pc(x["fracao_com_30_ou_mais"])] for x in branq["por_faixa"]],
    )
    tabela(
        ["Branqueamento", "Linhas com", "AUC do DHW (IC 95%)", "Sensibilidade de DHW ≥ 4", "Especificidade de DHW ≥ 4", "Com branqueamento e DHW zero"],
        [[f"{k}% ou mais", v["com_branqueamento"], f"{n(v['auc'])} ({faixa(v['auc_ic'])})", pc(v["sensibilidade_dhw4"]), pc(v["especificidade_dhw4"]), pc(v["branqueamento_sem_estresse"])] for k, v in branq["limiares"].items()],
    )
    tabela(
        ["Recife", "Linhas", "Anos com levantamento", "Com 10% ou mais", "Dessas, com DHW abaixo de 4", "Maior DHW nos levantamentos"],
        [[x["nome"], x["linhas"], x["anos_com_levantamento"], x["com_10_ou_mais"], x["dessas_com_dhw_abaixo_de_4"], n(x["dhw_maximo_nos_levantamentos"], 1)] for x in branq["resumo_por_recife"]],
    )
    print("coleta:", json.dumps(r["coleta"], ensure_ascii=False))
    print("para_o_site:", json.dumps({k: v for k, v in r["para_o_site"].items() if k != "grafico"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
