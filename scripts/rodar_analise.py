"""Roda a análise completa sobre o extrato em data/ e grava reports/ (resultados.json, CSV e figuras)."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from corais_calor import analise, dados, graficos, site
from corais_calor.estilo import numero, percentual

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "reports"
FIGURAS = SAIDA / "figuras"


def _limpo(valor):
    """Troca NaN e infinito por None e arredonda, para o JSON ficar válido e legível."""
    if isinstance(valor, dict):
        return {str(k): _limpo(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpo(v) for v in valor]
    if isinstance(valor, float):
        return None if math.isnan(valor) or math.isinf(valor) else round(valor, 5)
    if hasattr(valor, "item"):
        return _limpo(valor.item())
    return valor


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    inicio = time.time()
    FIGURAS.mkdir(parents=True, exist_ok=True)

    def passo(nome: str) -> None:
        print(f"[{time.time() - inicio:5.0f} s] {nome}", flush=True)

    base = dados.carregar()
    passo("dados carregados")
    series, diarias = analise.preparar(base)
    conferencia = analise.conferir_dhw(series, diarias)
    passo("DHW reimplementado e conferido")
    ondas_calor = analise.ondas_de_calor(diarias)
    passo("ondas de calor marinhas")
    tend = analise.tendencias(series)
    globais = analise.eventos_globais(tend)
    passo("tendências e intervalos de retorno")
    prev = analise.previsoes(series, base.nino34)
    prev["nino"]["conferencia_com_a_caixa_do_oisst"] = None if base.nino_caixa is None else analise.conferir_nino(base.nino34, base.nino_caixa)
    passo("previsão")
    rank = analise.ranking(series)
    branq = analise.validar_com_branqueamento(series, base.branqueamento)
    passo("ranking e validação com branqueamento observado")

    exposicao = analise.tabela_de_exposicao(base, tend, rank)
    exposicao.to_csv(SAIDA / "exposicao_por_recife.csv", index=False, encoding="utf-8", lineterminator="\n")

    resultados = {
        "coleta": base.coleta,
        "parametros": {
            "limiares_dhw": analise.LIMIARES,
            "decadas": analise.DECADAS,
            "periodos_do_retorno": analise.PERIODOS,
            "eventos_globais": analise.EVENTOS_GLOBAIS,
            "antecedencias_semanas": analise.ANTECEDENCIAS,
            "ultimo_ano_de_treino": analise.ULTIMO_ANO_DE_TREINO,
            "bloco_do_bootstrap_anos": analise.BLOCO_ANOS,
            "semente": analise.SEMENTE,
        },
        "recifes": json.loads(base.recifes.reset_index().to_json(orient="records", force_ascii=False)),
        "conferencia_do_dhw": conferencia,
        "ondas_de_calor": ondas_calor,
        "tendencias": tend,
        "eventos_globais": globais,
        "previsao": prev,
        "ranking": rank,
        "branqueamento_observado": branq,
    }
    resultados["para_o_site"] = site.montar(resultados)
    resultados = _limpo(resultados)
    (SAIDA / "resultados.json").write_text(json.dumps(resultados, indent=1, ensure_ascii=False), encoding="utf-8")

    c4 = tend["dhw4"]["conjunto"]
    ret = tend["dhw4"]["retorno"]["todos"]
    r_proprio = conferencia["resumo"]["climatologia"]
    r_oisst = conferencia["resumo"]["outro_produto"]
    oito = prev["antecedencias"]["8"]["metodos"]
    lider = rank["por_recife"][0]
    regioes = {nome: r for nome, r in tend["dhw4"]["retorno"].items() if nome != "todos"}
    encolheu = sum(1 for r in regioes.values() if r["depois"]["retorno"] < r["antes"]["retorno"])
    figuras = {
        "fracao_por_ano": graficos.fracao_por_ano(
            tend,
            analise.EVENTOS_GLOBAIS,
            f"O ano de alerta de branqueamento passou de 1 em cada {numero(ret['antes']['retorno'], 0)} para 1 em cada {numero(ret['depois']['retorno'], 0)} por recife",
            f"Fração dos {len(series)} recifes com DHW acima do limiar em cada ano. Em cinza, os eventos globais de branqueamento da NOAA.",
        ),
        "mapa_de_exposicao": graficos.mapa_de_exposicao(
            base.recifes,
            base.costa,
            rank,
            [linha["slug"] for linha in rank["por_recife"][:6]] + ["abrolhos", "rocas"],
            f"{lider['nome']} lidera: {lider['anos_dhw4']} anos de alerta em {rank['anos']}",
            "Um ponto por recife. Rótulo: nome e número de anos com DHW de 4 °C-semana ou mais.",
        ),
        "conferencia_do_dhw": graficos.conferencia_do_dhw(
            conferencia,
            f"O DHW refeito bate com o oficial (erro de {numero(r_proprio['erro_absoluto_do_maximo_anual'])}); com outra temperatura, o erro sobe para {numero(r_oisst['erro_absoluto_do_maximo_anual'])}",
            f"Cada ponto é um ano num dos {len(diarias)} recifes de referência. Linhas finas: os limiares de 4 e 8; diagonal: igualdade.",
        ),
        "retorno_por_regiao": graficos.retorno_por_regiao(
            tend,
            "dhw4",
            f"O intervalo entre anos de alerta encolheu nas {len(regioes)} regiões" if encolheu == len(regioes) else f"O intervalo entre anos de alerta encolheu em {encolheu} das {len(regioes)} regiões",
            "Anos, em média, entre dois anos com DHW de 4 °C-semana ou mais. Entre parênteses, o número de recifes.",
        ),
        "previsao_por_antecedencia": graficos.previsao_por_antecedencia(
            prev,
            f"A 8 semanas, o modelo erra {numero(oito['modelo']['brier'], 3)} e a persistência calibrada, {numero(oito['persistencia_calibrada']['brier'], 3)}",
            f"Previsão de DHW ≥ 4 na estação quente; treino até {analise.ULTIMO_ANO_DE_TREINO}, teste de {analise.ULTIMO_ANO_DE_TREINO + 1} em diante.",
        ),
        "ranking_com_incerteza": graficos.ranking_com_incerteza(
            rank,
            f"{rank['certos_no_terco']} recifes estão no terço mais exposto com 90% de certeza; {rank['indefinidos']} ficam indefinidos",
            f"Exposição em {rank['periodo'][0]}-{rank['periodo'][1]}. Azul forte: 90% ou mais; azul claro: indefinido; cinza: 10% ou menos.",
        ),
    }
    for nome, figura in figuras.items():
        figura.savefig(FIGURAS / f"{nome}.png")
        plt.close(figura)
    passo("figuras gravadas")

    print("\n== DHW reimplementado x oficial")
    print(json.dumps(_limpo(conferencia["resumo"]), indent=1, ensure_ascii=False))
    print(json.dumps(_limpo({k: v for k, v in conferencia["mmm"].items() if k != "por_recife"}), ensure_ascii=False))
    print("erro diário médio:", conferencia["erro_diario_medio"], "máximo do algoritmo:", conferencia["erro_diario_maximo_algoritmo"])
    for r in conferencia["por_recife"]:
        print("  ", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    print("\n== Ondas de calor por década (média dos recifes de referência)")
    for linha in ondas_calor["por_decada"]:
        print(f"  {linha['periodo']}: {numero(linha['eventos_por_ano'], 1)} eventos/ano, {numero(linha['dias_por_ano'], 0)} dias/ano, duração {numero(linha['duracao_media'], 0)} dias, intensidade {numero(linha['intensidade_maxima_media'])}")
    print(f"  razão de dias última/primeira: {numero(ondas_calor['razao_dias_ultima_sobre_primeira'])}", ondas_calor["razao_por_recife"])
    for r in ondas_calor["por_recife"]:
        print("  ", r["slug"], [round(d["dias_por_ano"], 1) for d in r["decadas"]], round(r["dias_a_mais_por_decada"], 1), r["maior_evento"])
    for chave in ("dhw4", "dhw8"):
        c = tend[chave]["conjunto"]
        print(f"\n== {chave}: razão de chances por década {numero(c['razao_de_chances_por_decada'])} {[round(v, 2) for v in c['razao_de_chances_ic']]}; superdispersão {numero(c['superdispersao'], 1)}")
        print("  contagem:", tend[chave]["contagem"])
        for nome, r in tend[chave]["retorno"].items():
            print(f"  {nome}: retorno {r['antes']['retorno']:.1f} -> {r['depois']['retorno']:.1f}; razão {r['razao_de_frequencia']} {r['razao_ic']}")
        print("  eventos globais:", json.dumps(_limpo(globais[chave]["por_evento"]), ensure_ascii=False))
        print("  piores anos:", [(d["ano"], round(d["fracao"], 2)) for d in globais[chave]["dez_piores_anos"]])
    print("\n== Previsão (Brier no teste | AUC | fora do alerta: Brier, AUC | alerta 50%: precisão, avisados)")
    print("  Niño:", prev["nino"])
    for semanas, r in prev["antecedencias"].items():
        print(f"  {semanas} semanas: teste {r['teste']}")
        for nome, m in r["metodos"].items():
            a = m["alerta"]
            print(f"    {nome:24s} {m['brier']:.4f} {[round(v, 4) for v in m['brier_ic']]} | {m['auc']:.3f} | {m['brier_fora_do_alerta']:.4f} {m['auc_fora_do_alerta']:.3f} | {a['precisao']} {a['avisados']}")
        for nome, c in r["comparacoes"].items():
            print(f"    {nome}: {c['diferenca']:+.4f} {[round(v, 4) for v in c['ic']]} P={c['prob_primeiro_melhor']:.2f}")
        print("    coeficientes:", r["coeficientes"]["modelo"])
    print("\n== Ranking")
    for linha in rank["por_recife"]:
        print(f"  {linha['posto']:2d} {linha['nome']:26s} dhw4={linha['anos_dhw4']:2d} dhw8={linha['anos_dhw8']:2d} P(terço)={percentual(linha['prob_terco_mais_exposto'])} posto {linha['posto_ic']}")
    print("\n== Branqueamento observado")
    print(json.dumps(_limpo({k: v for k, v in branq.items() if k != "por_recife"}), indent=1, ensure_ascii=False))
    print(f"\nGravado em {SAIDA}. Tempo total: {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
