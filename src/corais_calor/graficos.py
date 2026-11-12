"""Figuras do estudo. A cor segue a entidade: azul é o método ou a medida principal, laranja é a linha de base
(persistência, período anterior), verde-água é a alternativa, cinza é referência. Severidade usa a rampa de azul."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from corais_calor.estilo import (
    APAGADO,
    AQUA,
    AZUL,
    EIXO,
    ESTILO,
    GRADE,
    LARANJA,
    RAMPA_AZUL,
    SUPERFICIE,
    TINTA,
    TINTA_SECUNDARIA,
    numero,
    percentual,
)

AZUL_CLARO, AZUL_ESCURO = RAMPA_AZUL[0], RAMPA_AZUL[4]


def _titulos(fig: Figure, titulo: str, subtitulo: str, y: float = 0.965) -> None:
    fig.text(0.02, y, titulo, fontsize=13, fontweight="bold", color=TINTA, va="top")
    fig.text(0.02, y - 0.055, subtitulo, fontsize=9.5, color=TINTA_SECUNDARIA, va="top")


def fracao_por_ano(tend: dict, eventos_globais: dict[str, list[int]], titulo: str, subtitulo: str) -> Figure:
    """Fração dos recifes em estresse severo por ano, com a tendência e os eventos globais marcados."""
    anos = np.array(tend["anos"])
    f4 = np.array(tend["dhw4"]["conjunto"]["fracao_por_ano"])
    f8 = np.array(tend["dhw8"]["conjunto"]["fracao_por_ano"])
    curva = np.array(tend["dhw4"]["conjunto"]["curva"])
    inf = np.array(tend["dhw4"]["conjunto"]["curva_inf"])
    sup = np.array(tend["dhw4"]["conjunto"]["curva_sup"])
    with plt.rc_context(ESTILO):
        fig, ax = plt.subplots(figsize=(8.6, 4.7), dpi=160)
        fig.subplots_adjust(top=0.80, left=0.08, right=0.97, bottom=0.11)
        _titulos(fig, titulo, subtitulo)
        for nome, lista in eventos_globais.items():
            ax.axvspan(min(lista) - 0.5, max(lista) + 0.5, color=GRADE, alpha=0.55, zorder=0, linewidth=0)
            ax.annotate(nome, ((min(lista) + max(lista)) / 2, 1.0), xytext=(0, -4), textcoords="offset points", ha="center", va="top", fontsize=8, color=TINTA_SECUNDARIA)
        ax.fill_between(anos, inf, sup, color=APAGADO, alpha=0.18, linewidth=0, zorder=1)
        ax.plot(anos, curva, color=APAGADO, linewidth=1.6, zorder=2, label="tendência do DHW ≥ 4 (faixa de 95%)")
        ax.plot(anos, f4, "-o", color=AZUL, markersize=5, markeredgewidth=1, zorder=4, label="DHW ≥ 4 °C-semana (alerta nível 1)")
        ax.plot(anos, f8, "-o", color=AZUL_ESCURO, markersize=5, markeredgewidth=1, zorder=5, label="DHW ≥ 8 °C-semana (alerta nível 2)")
        ax.set_ylim(0, 1.0)
        ax.set_xlim(anos.min() - 0.7, anos.max() + 0.7)
        ax.yaxis.set_major_formatter(lambda v, _: percentual(v))
        ax.set_ylabel("fração dos recifes do estudo")
        ax.legend(loc="upper left", fontsize=8.5, bbox_to_anchor=(0.0, 0.93))
        return fig


def mapa_de_exposicao(recifes, costa: list[np.ndarray], rank: dict, rotulados: list[str], titulo: str, subtitulo: str) -> Figure:
    """Mapa dos recifes: a cor e o tamanho do ponto mostram em quantos anos do período o DHW passou de 4."""
    por_slug = {linha["slug"]: linha for linha in rank["por_recife"]}
    n_anos = rank["anos"]
    with plt.rc_context(ESTILO):
        fig, ax = plt.subplots(figsize=(8.6, 3.9), dpi=160)
        fig.subplots_adjust(top=0.83, left=0.01, right=0.99, bottom=0.17)
        _titulos(fig, titulo, subtitulo, y=0.97)
        ax.grid(visible=False)
        for lado in ("bottom", "left"):
            ax.spines[lado].set_visible(False)
        for linha in costa:
            ax.plot(linha[:, 0], linha[:, 1], color=EIXO, linewidth=0.6, zorder=1)
        lon = recifes["lon"].to_numpy()
        lat = recifes["lat"].to_numpy()
        anos4 = np.array([por_slug[s]["anos_dhw4"] for s in recifes.index])
        degraus = [(0, 1, RAMPA_AZUL[0], "nenhum"), (1, 4, RAMPA_AZUL[1], "1 a 3"), (4, 7, RAMPA_AZUL[2], "4 a 6"), (7, 10, RAMPA_AZUL[3], "7 a 9"), (10, 99, RAMPA_AZUL[4], "10 ou mais")]
        for a, b, cor, nome in degraus:
            m = (anos4 >= a) & (anos4 < b)
            ax.scatter(lon[m], lat[m], s=34 + 9 * anos4[m], color=cor, edgecolor=SUPERFICIE, linewidth=1.2, zorder=3, label=f"{nome} ({int(m.sum())})")
        ax.set_xlim(-180, 180)
        ax.set_ylim(-48, 48)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        # Rótulos: para cada um, tenta acima, abaixo, à direita e à esquerda do ponto e fica com a primeira
        # posição que não cobre um rótulo já colocado nem outro ponto.
        fig.canvas.draw()
        pontos_px = ax.transData.transform(np.column_stack([lon, lat]))
        ocupados: list[tuple[float, float, float, float]] = [(x - 9, y - 9, x + 9, y + 9) for x, y in pontos_px]
        escala = fig.dpi / 72.0
        limites = ax.get_window_extent()
        for slug in dict.fromkeys(s for s in rotulados if s in recifes.index):
            r = recifes.loc[slug]
            texto = f"{r['nome']} · {por_slug[slug]['anos_dhw4']}"
            largura, altura = 0.56 * 7.5 * escala * len(texto), 7.5 * escala * 1.25
            x0, y0 = ax.transData.transform((r["lon"], r["lat"]))
            candidatos = [(0, 9, "center", "bottom"), (0, -9, "center", "top"), (9, 0, "left", "center"), (-9, 0, "right", "center"), (0, 21, "center", "bottom"), (0, -21, "center", "top"), (9, 12, "left", "bottom"), (-9, -12, "right", "top")]
            escolhido, caixa_escolhida = candidatos[0], None
            for dx, dy, ha, va in candidatos:
                cx = x0 + dx * escala - (largura / 2 if ha == "center" else (largura if ha == "right" else 0))
                cy = y0 + dy * escala - (altura / 2 if va == "center" else (altura if va == "top" else 0))
                caixa = (cx, cy, cx + largura, cy + altura)
                proprio = (x0 - 9, y0 - 9, x0 + 9, y0 + 9)
                livre = all(caixa[2] < o[0] or caixa[0] > o[2] or caixa[3] < o[1] or caixa[1] > o[3] for o in ocupados if o != proprio)
                livre = livre and caixa[0] >= limites.x0 and caixa[2] <= limites.x1  # não sai pela lateral do mapa
                if livre:
                    escolhido, caixa_escolhida = (dx, dy, ha, va), caixa
                    break
            dx, dy, ha, va = escolhido
            if caixa_escolhida:
                ocupados.append(caixa_escolhida)
            ax.annotate(texto, (r["lon"], r["lat"]), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=7.5, color=TINTA_SECUNDARIA, zorder=4)
        legenda = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=5, fontsize=8.5, title=f"anos com DHW ≥ 4 em {rank['periodo'][0]}-{rank['periodo'][1]} ({n_anos} anos); entre parênteses, o número de recifes", title_fontsize=8.5, columnspacing=1.4, handletextpad=0.3)
        legenda.get_title().set_color(TINTA_SECUNDARIA)
        return fig


def conferencia_do_dhw(conf: dict, titulo: str, subtitulo: str) -> Figure:
    """Máximo anual do DHW reimplementado contra o oficial, com a mesma temperatura e com o OISST."""
    with plt.rc_context(ESTILO):
        fig, eixos = plt.subplots(1, 2, figsize=(8.6, 4.6), dpi=160, sharey=True)
        fig.subplots_adjust(top=0.76, left=0.08, right=0.97, bottom=0.13, wspace=0.08)
        _titulos(fig, titulo, subtitulo)
        paineis = [
            ("climatologia", "climatologia", AZUL, "Mesma temperatura (CoralTemp, 5 km), MMM refeito"),
            ("outro_produto", "outro_produto", AQUA, "Outra temperatura (OISST, 0,25°), MMM refeito"),
        ]
        for ax, (chave, resumo, cor, nome) in zip(eixos, paineis):
            pares = np.array(conf["pares_do_maximo_anual"][chave])
            limite = max(pares.max() * 1.05, 10)
            ax.grid(axis="x", visible=True)
            ax.plot([0, limite], [0, limite], color=EIXO, linewidth=1.2, zorder=1)
            for corte in (4, 8):
                ax.axhline(corte, color=GRADE, linewidth=1.0, zorder=1)
                ax.axvline(corte, color=GRADE, linewidth=1.0, zorder=1)
            ax.plot(pares[:, 0], pares[:, 1], "o", color=cor, markersize=4.5, markeredgewidth=0.6, alpha=0.75, zorder=3)
            r = conf["resumo"][resumo]
            ax.set_title(f"{nome}\ncorrelação {numero(r['correlacao_do_maximo_anual'], 3)} · erro médio {numero(r['erro_absoluto_do_maximo_anual'])} °C-semana", fontsize=9.5, color=TINTA_SECUNDARIA, loc="left", pad=8)
            ax.set_xlim(0, limite)
            ax.set_ylim(0, limite)
            ax.set_xlabel("DHW máximo do ano, oficial (°C-semana)")
        eixos[0].set_ylabel("DHW máximo do ano, reimplementado")
        return fig


def retorno_por_regiao(tend: dict, chave: str, titulo: str, subtitulo: str) -> Figure:
    """Intervalo de retorno do estresse severo antes e depois de 2005, por região (escala log)."""
    retorno = tend[chave]["retorno"]
    nomes = [n for n in retorno if n != "todos"] + ["todos"]
    rotulos = [f"{n} ({retorno[n]['recifes']})" if n != "todos" else f"Todos os recifes ({retorno[n]['recifes']})" for n in nomes]
    teto = 150.0
    with plt.rc_context(ESTILO):
        fig, ax = plt.subplots(figsize=(8.6, 4.7), dpi=160)
        fig.subplots_adjust(top=0.78, left=0.30, right=0.95, bottom=0.14)
        _titulos(fig, titulo, subtitulo)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        y = np.arange(len(nomes))[::-1].astype(float)
        for i, nome in enumerate(nomes):
            for periodo, cor, desloc in (("antes", LARANJA, 0.16), ("depois", AZUL, -0.16)):
                r = retorno[nome][periodo]
                # No JSON, "infinito" (nenhum evento no período) é gravado como nulo.
                valor, limite_inf, limite_sup = (float("inf") if v is None else v for v in (r["retorno"], *r["retorno_ic"]))
                centro = min(valor, teto)
                inf, sup = min(limite_inf, teto), min(limite_sup, teto)
                ax.plot([inf, sup], [y[i] + desloc] * 2, color=cor, linewidth=1.6, alpha=0.55, zorder=2)
                ax.plot(centro, y[i] + desloc, "o" if np.isfinite(valor) else ">", color=cor, zorder=3, label={"antes": "1985-2004", "depois": "2005-2024"}[periodo] if i == 0 else None)
                texto = f"{numero(valor, 1)}" if np.isfinite(valor) else "nenhum evento"
                ax.annotate(texto, (sup, y[i] + desloc), xytext=(6, 0), textcoords="offset points", va="center", fontsize=8, color=TINTA_SECUNDARIA)
        ax.set_xscale("log")
        ax.set_xlim(1, teto * 2.2)
        ax.set_xticks([1, 2, 5, 10, 20, 50, 100], ["1", "2", "5", "10", "20", "50", "100"])
        ax.minorticks_off()
        ax.set_yticks(y, rotulos, fontsize=9)
        ax.set_ylim(-0.6, len(nomes) - 0.4)
        ax.set_xlabel("anos entre dois anos de alerta, em média (escala logarítmica; a barra é a faixa de 95%)")
        ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, fontsize=9, columnspacing=1.5)
        return fig


def previsao_por_antecedencia(prev: dict, titulo: str, subtitulo: str, semanas_da_curva: str = "8") -> Figure:
    """Esquerda: erro de Brier de cada método por antecedência. Direita: curva de confiabilidade."""
    estilos = {
        "climatologia": (APAGADO, "Climatologia"),
        "persistencia": (LARANJA, "Persistência (sim ou não)"),
        "persistencia_calibrada": ("#f3a57f", "Persistência calibrada"),
        "modelo": (AZUL, "Modelo simples"),
        "modelo_com_projecao": (AQUA, "Modelo + projeção"),
    }
    semanas = list(prev["antecedencias"])
    with plt.rc_context(ESTILO):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 4.7), dpi=160, gridspec_kw={"width_ratios": [1.25, 1]})
        fig.subplots_adjust(top=0.76, left=0.08, right=0.97, bottom=0.13, wspace=0.22)
        _titulos(fig, titulo, subtitulo)
        largura = 0.16
        for j, (metodo, (cor, nome)) in enumerate(estilos.items()):
            x = np.arange(len(semanas)) + (j - 2) * largura
            valores = [prev["antecedencias"][s]["metodos"][metodo]["brier"] for s in semanas]
            ic = np.array([prev["antecedencias"][s]["metodos"][metodo]["brier_ic"] for s in semanas])
            ax1.bar(x, valores, width=largura - 0.02, color=cor, zorder=3, label=nome)
            ax1.vlines(x, ic[:, 0], ic[:, 1], color=TINTA_SECUNDARIA, linewidth=1.0, zorder=4)
        ax1.set_xticks(np.arange(len(semanas)), [f"{s} semanas" for s in semanas])
        ax1.set_ylabel("erro de Brier no teste (menor é melhor)")
        ax1.yaxis.set_major_formatter(lambda v, _: numero(v, 2))
        ax1.set_title("Erro por antecedência (traço: faixa de 95%)", fontsize=9.5, color=TINTA_SECUNDARIA, loc="left", pad=8)
        ax1.set_ylim(0, ax1.get_ylim()[1] * 1.32)
        ax1.legend(loc="upper left", fontsize=8, ncol=2, columnspacing=1.0, handlelength=1.2)
        ax1.tick_params(axis="x", length=0)

        ax2.grid(axis="x", visible=True)
        ax2.plot([0, 1], [0, 1], color=EIXO, linewidth=1.2, zorder=1)
        metodos = prev["antecedencias"][semanas_da_curva]["metodos"]
        for metodo in ("persistencia_calibrada", "modelo"):
            cor, nome = estilos[metodo]
            pontos = [(f["previsto"], f["observado"]) for f in metodos[metodo]["confiabilidade"] if f["n"] >= 20]
            ax2.plot(*zip(*pontos), "-o", color=cor, markersize=6, zorder=3, label=nome)
        ax2.set_xlim(0, 1)
        ax2.set_ylim(0, 1)
        ax2.set_aspect("equal")
        ax2.xaxis.set_major_formatter(lambda v, _: percentual(v))
        ax2.yaxis.set_major_formatter(lambda v, _: percentual(v))
        ax2.set_xlabel("probabilidade prevista")
        ax2.set_ylabel("frequência observada")
        ax2.set_title(f"Confiabilidade a {semanas_da_curva} semanas", fontsize=9.5, color=TINTA_SECUNDARIA, loc="left", pad=8)
        ax2.legend(loc="upper left", fontsize=8)
        return fig


def ranking_com_incerteza(rank: dict, titulo: str, subtitulo: str) -> Figure:
    """Probabilidade de cada recife estar no terço mais exposto, na ordem do posto."""
    linhas = rank["por_recife"]
    with plt.rc_context(ESTILO):
        fig, ax = plt.subplots(figsize=(8.6, 8.6), dpi=160)
        fig.subplots_adjust(top=0.90, left=0.27, right=0.85, bottom=0.07)
        fig.text(0.02, 0.98, titulo, fontsize=13, fontweight="bold", color=TINTA, va="top")
        fig.text(0.02, 0.952, subtitulo, fontsize=9.5, color=TINTA_SECUNDARIA, va="top")
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        y = np.arange(len(linhas))
        prob = np.array([linha["prob_terco_mais_exposto"] for linha in linhas])
        cores = [AZUL if p >= 0.9 else (GRADE if p <= 0.1 else AZUL_CLARO) for p in prob]
        ax.barh(y, prob, height=0.62, color=cores, zorder=3)
        for i, linha in enumerate(linhas):
            ax.annotate(f"{linha['anos_dhw4']} / {linha['anos_dhw8']}", (1.0, y[i]), xytext=(8, 0), textcoords="offset points", va="center", fontsize=8, color=TINTA_SECUNDARIA, annotation_clip=False)
        ax.annotate("anos com DHW\n≥ 4 / ≥ 8", (1.0, -1.45), xytext=(8, 0), textcoords="offset points", va="center", fontsize=8, color=APAGADO, annotation_clip=False)
        ax.axhline(rank["tamanho_do_terco"] - 0.5, color=EIXO, linewidth=1.0, zorder=2)
        ax.set_yticks(y, [f"{linha['posto']}. {linha['nome']}" for linha in linhas], fontsize=8.5)
        ax.set_ylim(len(linhas) - 0.4, -2.2)
        ax.set_xlim(0, 1)
        ax.xaxis.set_major_formatter(lambda v, _: percentual(v))
        ax.set_xlabel("probabilidade de estar no terço mais exposto (bootstrap em blocos de anos)")
        return fig
