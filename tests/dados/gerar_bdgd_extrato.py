"""Extrai a BDGD REAL de uma cooperativa inteira (item L4-01-modelo-rede) para `tests/dados/gerados/`
(gitignorado — nada de FileGDB no repositório, disco apertado é regra do laço, mesmo motivo por que
`gerar_rede.py` usa rede SINTÉTICA para o item irmão L4-01-b). Diferente daquele gerador: aqui o
PONTO é justamente testar contra dado REAL da ANEEL (esquisitices de campo incluídas — é o que a
cláusula "contagem conferida contra o arquivo" pede), não uma malha de ordem de grandeza equivalente.

Fonte: a variável de ambiente `PLAT_REDE_REFERENCIA_GDB` aponta o pacote `.gdb.zip` da distribuidora de
referência (ativo da casa, BDGD 2024-12-31 V11, 13,5 MB comprimidos, 56 MB abertos: 6 SUB, 21 CTMT,
44.268 SSDMT, 5.481 UNTRMT, 29.244 SSDBT, 27.587 UCBT_tab, 26.581 RAMLIG, 3.064 UNSEMT, 142 UCMT_tab,
60.549 PONNOT — uma distribuidora REAL inteira, não um recorte). O caminho NUNCA é escrito em arquivo:
vem do ambiente da máquina que tem o ativo. Sem a variável (ou sem o arquivo), o chamador pula o teste —
`obter_extrato()` levanta `FileNotFoundError` para isso.

Achado ao medir (06-07/09/2026): importar a distribuidora de referência INTEIRA (44.268 SSDMT + 29.244 SSDBT + 27.587
UCBT_tab + 5.481 UNTRMT + 3.064 UNSEMT — a associação de cada dispositivo/consumidor com a junção é
UMA CONSULTA por linha, não em lote) passou de 13 minutos sem terminar numa trilha sob disputa de
banco compartilhada — achado registrado em `docs/rede/MODELO_REDE.md` §4 como pendência de
performance (falta o mesmo tratamento em lote que `_gravar_arestas` já tem). `obter_extrato()`
continua devolvendo o arquivo INTEIRO (é o ativo certo para medir isso fora da suíte, com tempo
maior); `obter_extrato_pequeno()` recorta só um alimentador (CTMT) pequeno da MESMA distribuidora
real — mesmas esquisitices de campo (RAMLIG sem PN_CON_2, SUB residual etc.), escala que cabe no
orçamento de uma trilha (a suíte automatizada usa este).

Uso:  venv/bin/python tests/dados/gerar_bdgd_extrato.py   (imprime os dois caminhos e a contagem por camada)
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

RAIZ_GERADOS = Path(__file__).resolve().parent / "gerados"
DESTINO = RAIZ_GERADOS / "bdgd_referencia.gdb"
DESTINO_PEQUENO = RAIZ_GERADOS / "bdgd_referencia_ctmt.gdb"
# O alimentador (CTMT) do recorte pequeno também vem do ambiente: o código traz a sigla da distribuidora.
CTMT_PEQUENO = os.environ.get("PLAT_REDE_REFERENCIA_CTMT", "")


def fonte() -> Path | None:
    """O pacote `.gdb.zip` da distribuidora de referência, do ambiente. None quando a máquina não o tem."""
    caminho = os.environ.get("PLAT_REDE_REFERENCIA_GDB", "").strip()
    return Path(caminho) if caminho else None


def obter_extrato() -> str:
    """Devolve o caminho do FileGDB extraído, extraindo de novo só se ainda não existe (idempotente).
    Levanta FileNotFoundError se o ativo da casa não estiver nesta máquina."""
    if DESTINO.exists() and any(DESTINO.iterdir()):
        return str(DESTINO)
    origem = fonte()
    if origem is None or not origem.exists():
        raise FileNotFoundError(
            "ativo da casa ausente: defina PLAT_REDE_REFERENCIA_GDB com o caminho do .gdb.zip da "
            "distribuidora de referência (BDGD real, item L4-01-c); sem ela, os testes que dependem "
            "de distribuidora real pulam"
        )
    RAIZ_GERADOS.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(DESTINO, ignore_errors=True)
    with zipfile.ZipFile(origem) as z:
        nomes_gdb = {n.split("/", 1)[0] for n in z.namelist() if ".gdb/" in n}
        raiz_no_zip = next(iter(sorted(nomes_gdb)), None)
        if raiz_no_zip is None:
            raise FileNotFoundError(f"{origem} não contém um .gdb dentro do zip")
        z.extractall(RAIZ_GERADOS)
    extraido = RAIZ_GERADOS / raiz_no_zip
    extraido.rename(DESTINO)
    return str(DESTINO)


def obter_extrato_pequeno() -> str:
    """Um alimentador (CTMT) só, da mesma distribuidora real — rápido o bastante para a suíte
    automatizada, com as mesmas esquisitices de dado real (RAMLIG sem PN_CON_2 etc.)."""
    if DESTINO_PEQUENO.exists() and any(DESTINO_PEQUENO.iterdir()):
        return str(DESTINO_PEQUENO)
    if not CTMT_PEQUENO:
        raise FileNotFoundError(
            "defina PLAT_REDE_REFERENCIA_CTMT com o código do alimentador do recorte pequeno "
            "(medido: o menor CTMT com as 5 camadas de aresta/nó todas presentes)"
        )
    completo = obter_extrato()
    import pyogrio

    shutil.rmtree(DESTINO_PEQUENO, ignore_errors=True)
    sub = pyogrio.read_dataframe(completo, layer="SUB")
    ctmt = pyogrio.read_dataframe(completo, layer="CTMT", where=f"COD_ID = '{CTMT_PEQUENO}'", read_geometry=False)
    camadas_geo = {
        "SSDMT": "MultiLineString", "UNTRMT": "Point", "SSDBT": "MultiLineString", "UNSEMT": "Point",
    }
    camadas_sem_geo = ("UCBT_tab", "RAMLIG", "UCMT_tab")
    pn_cons: set[str] = set()
    quadros = {}
    for camada in list(camadas_geo) + list(camadas_sem_geo):
        df = pyogrio.read_dataframe(completo, layer=camada, where=f"CTMT = '{CTMT_PEQUENO}'",
                                     read_geometry=camada in camadas_geo)
        quadros[camada] = df
        for col in ("PN_CON_1", "PN_CON_2", "PN_CON"):
            if col in df.columns:
                pn_cons.update(df[col].dropna().astype(str))
    ponnot = pyogrio.read_dataframe(completo, layer="PONNOT")
    ponnot = ponnot[ponnot["COD_ID"].astype(str).isin(pn_cons)]

    pyogrio.write_dataframe(sub, DESTINO_PEQUENO, layer="SUB", driver="OpenFileGDB",
                             geometry_type="MultiPolygon", append=False)
    pyogrio.write_dataframe(ctmt, DESTINO_PEQUENO, layer="CTMT", driver="OpenFileGDB", append=True)
    for camada, tipo in camadas_geo.items():
        pyogrio.write_dataframe(quadros[camada], DESTINO_PEQUENO, layer=camada, driver="OpenFileGDB",
                                 geometry_type=tipo, append=True)
    for camada in camadas_sem_geo:
        pyogrio.write_dataframe(quadros[camada], DESTINO_PEQUENO, layer=camada, driver="OpenFileGDB", append=True)
    pyogrio.write_dataframe(ponnot, DESTINO_PEQUENO, layer="PONNOT", driver="OpenFileGDB",
                             geometry_type="Point", append=True)
    return str(DESTINO_PEQUENO)


if __name__ == "__main__":
    import json

    import pyogrio

    for caminho in (obter_extrato(), obter_extrato_pequeno()):
        print(caminho)
        contagens = {
            camada: int(pyogrio.read_info(caminho, layer=camada)["features"])
            for camada, _ in pyogrio.list_layers(caminho)
        }
        print(json.dumps(contagens, ensure_ascii=False, indent=1))
