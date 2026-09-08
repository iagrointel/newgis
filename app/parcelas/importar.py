"""Importação de malha pronta como parcelas do tipo 'lote' (a cláusula do portão: "importar
lotes derivados do SIG de teste interno (dado aberto) como parcelas do tipo 'lote' com
registro sintético").

A importação é UMA RODADA sem reverência ao que já existe (rodar de novo com a mesma origem
duplica — um segundo registro é um segundo documento, não a mesma): um registro SINTÉTICO por
empreendimento de origem (tipo 'loteamento', origem 'sintetico', código do formato
`prefixo-<empreendimento>` — número, nunca nome), pontos deduplicados por coordenada (a malha
derivada compartilha vértices exatos entre lotes vizinhos), linhas deduplicadas pelo par de
pontos (é aqui que nasce LINHA PARTILHADA: um par de vértices servindo dois lotes vira UMA
linha com dois usos em `plat.parcela_linha_parcela`), e a parcela 'lote' com a geometria da
origem. Precisão dos pontos importados: NULA — derivada de malha aberta, a precisão não é
declarada pela origem, e inventar número é pior que nulo (a coluna existe para quem mediu).

Nada aqui resolve identidade: o lote de origem é dado aberto derivado, sem CPF, sem nome, sem
matrícula. A origem fica em `parcela.atributos` (marca da malha + empreendimento de origem).
"""

from uuid import uuid4

from app import limites
from app.erros import ErroAPI
from app.parcelas.modelo import SRID, criar_parcela, criar_registro

_MARCA_MALHA = "sig_lote_derivado"  # marca em parcela.atributos; nunca é origem de medição


def importar_lotes(cur, tenant_id: int, lotes, *, prefixo_registro: str = "LS") -> dict:
    """`lotes`: iterável de dicionários {empreendimento_id:int, codigo:str, wkt:str} na SRID da
    casa (31982). Um registro sintético por empreendimento; parcelas do tipo 'lote'. Devolve a
    contagem da rodada (o que entrou, quantos pontos/linhas deduplicados, quantas linhas
    partilhadas)."""
    importados = list(lotes)
    if len(importados) > limites.PARCELA_IMPORT_LOTES_MAX:
        raise ErroAPI(
            422, "lotes_demais",
            f"{len(importados)} lotes numa rodada; o teto é {limites.PARCELA_IMPORT_LOTES_MAX}",
        )
    registros: dict[int, str] = {}
    pontos: dict[tuple, str] = {}
    coords: dict[str, tuple[float, float]] = {}
    linhas: dict[tuple, str] = {}
    usos_linha: dict[str, int] = {}
    n_parcelas = 0
    for lote in importados:
        emp = int(lote["empreendimento_id"])
        if emp not in registros:
            registros[emp] = str(criar_registro(
                cur, tenant_id, codigo=f"{prefixo_registro}-{emp}", tipo="loteamento",
                origem="sintetico",
                descricao="Registro sintetico do import de malha derivada (dado aberto; sem matricula, sem nome)",
            )["id"])
        anel = _anel(lote["wkt"])
        ids_pontos = []
        for vertice in anel:
            chave = (round(vertice[0], 6), round(vertice[1], 6))
            if chave not in pontos:
                pid = str(uuid4())
                pontos[chave] = pid
                coords[pid] = chave
                cur.execute(
                    "INSERT INTO plat.parcela_ponto(id, tenant_id, geom, origem, "
                    "criada_por_registro) VALUES (%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),%s),"
                    "'derivada',%s)",
                    (pid, tenant_id, chave[0], chave[1], SRID, registros[emp]),
                )
            ids_pontos.append(pontos[chave])
        ids_linhas = []
        for i in range(len(ids_pontos)):
            de_id, para_id = ids_pontos[i], ids_pontos[(i + 1) % len(ids_pontos)]
            chave = (de_id, para_id) if de_id <= para_id else (para_id, de_id)
            if chave not in linhas:
                lid = str(uuid4())
                linhas[chave] = lid
                usos_linha[lid] = 0
                a, b = coords[chave[0]], coords[chave[1]]
                cur.execute(
                    "INSERT INTO plat.parcela_linha(id, tenant_id, de_ponto_id, para_ponto_id, "
                    "geom, origem, criada_por_registro) VALUES (%s,%s,%s,%s,"
                    "ST_SetSRID(ST_MakeLine(ST_MakePoint(%s,%s),ST_MakePoint(%s,%s)),%s),"
                    "'derivada',%s)",
                    (lid, tenant_id, chave[0], chave[1], a[0], a[1], b[0], b[1], SRID,
                     registros[emp]),
                )
            usos_linha[linhas[chave]] += 1
            ids_linhas.append(linhas[chave])
        parcela = criar_parcela(
            cur, tenant_id, tipo="lote", codigo=str(lote["codigo"]), registro_id=registros[emp],
            wkt=_wkt(anel),
            atributos={"origem": _MARCA_MALHA, "empreendimento_origem": emp},
        )
        for lid in ids_linhas:
            cur.execute(
                "INSERT INTO plat.parcela_linha_parcela(tenant_id, linha_id, parcela_id) "
                "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (tenant_id, lid, str(parcela["id"])),
            )
        n_parcelas += 1
    return {
        "registros": len(registros),
        "parcelas": n_parcelas,
        "pontos": len(pontos),
        "linhas": len(linhas),
        "linhas_partilhadas": sum(1 for n in usos_linha.values() if n > 1),
        "associacoes": sum(usos_linha.values()),
    }


def _anel(wkt: str) -> list:
    """Lê o POLYGON WKT e devolve o anel exterior SEM o ponto repetido do fechamento (a
    parcela fecha sozinho em criar_parcela). Coordenada vai arredondada a 1e-6 m (a chave de
    deduplicação de vértice do import) e VÉRTICE CONSECUTIVO IGUAL é descartado — malha
    derivada traz anel com vértice repetido e, sem isso, o par de/ponto=ponto viola a restrição
    da linha. Polígono com buraco é recusado — lote de malha aberta não tem buraco."""
    texto = (wkt or "").strip()
    if texto.upper().startswith("SRID="):  # EWKT
        texto = texto.split(";", 1)[1].strip()
    if not texto.upper().startswith("POLYGON"):
        raise ErroAPI(422, "tipo_invalido", "lote de origem precisa ser POLYGON")
    interior = texto[texto.index("((") + 2: texto.rindex("))")]
    aneis = interior.split("),(")
    if len(aneis) > 1:
        raise ErroAPI(422, "tipo_invalido", "lote de origem não pode ter buraco")
    vertices = []
    for par in aneis[0].split(","):
        x, y = par.split()
        vertices.append((round(float(x), 6), round(float(y), 6)))
    vertices = [v for i, v in enumerate(vertices)
                if i == 0 or v != vertices[i - 1]]
    if len(vertices) > 1 and vertices[0] == vertices[-1]:
        vertices = vertices[:-1]
    if len(vertices) < 3:
        raise ErroAPI(422, "tipo_invalido", "anel do lote precisa de pelo menos 3 vértices")
    return vertices


def _wkt(anel: list) -> str:
    fechado = anel + [anel[0]]
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in fechado) + "))"
