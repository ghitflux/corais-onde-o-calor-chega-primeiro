"""Baixa as bases públicas para data/brutos/ e regrava o extrato versionado em data/.

    uv run python scripts/baixar_dados.py            # baixa o que faltar e monta o extrato
    uv run python scripts/baixar_dados.py crw        # só os produtos do Coral Reef Watch (servidor OceanWatch)
    uv run python scripts/baixar_dados.py oisst      # só o OISST (servidor CoastWatch)
    uv run python scripts/baixar_dados.py apoio      # só os arquivos pequenos: Niño 3.4, branqueamento e costa
    uv run python scripts/baixar_dados.py extrato    # monta o extrato com o que já foi baixado, sem rede

O download é lento, porque o ERDDAP lê um arquivo por dia de dado: cerca de 3 horas no total. `crw` e `oisst`
falam com servidores diferentes e podem rodar em dois terminais ao mesmo tempo; cada um faz uma requisição por
vez. Nada é baixado duas vezes: se a execução cair, rode de novo e ela continua de onde parou. As datas finais
são as da coleta original, para que o extrato regerado seja o mesmo.
"""

import sys
from pathlib import Path

from corais_calor import coleta
from corais_calor.recifes import RECIFES

FIM_OISST = "2026-10-27"
FIM_CRW = "2026-11-10"
RAIZ = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    etapa = sys.argv[1] if len(sys.argv) > 1 else "tudo"
    brutos = RAIZ / "data" / "brutos"
    if etapa == "crw":
        coleta.baixar_crw(brutos, FIM_CRW, RECIFES, baixar=True)
    elif etapa == "oisst":
        coleta.baixar_oisst(brutos, FIM_OISST, RECIFES, baixar=True)
        coleta.nino_da_caixa(brutos, FIM_OISST, baixar=True)
    elif etapa == "apoio":
        coleta.baixar_apoio(brutos, baixar=True)
    elif etapa in ("tudo", "extrato"):
        resumo = coleta.montar_extrato(RAIZ, FIM_OISST, FIM_CRW, baixar=etapa == "tudo")
        for chave, valor in resumo.items():
            print(f"{chave}: {valor}")
    else:
        raise SystemExit(f"etapa desconhecida: {etapa}")
    print("fim", flush=True)
