"""Conferência de escoamento por gravidade da rede de esgoto e drenagem (item L4-05-e-gas-e-esgoto).

O trecho de esgoto DECLARA o seu sentido de duas maneiras ao mesmo tempo: pela ordem dos vértices (o primeiro
é o de montante, o último é o de jusante — é a convenção do `dois_terminais` do pacote) e pelas cotas que
carrega (`cota_montante` e `cota_jusante`, a geratriz interna inferior em cada ponta). Num trecho que escoa
por gravidade, a ponta declarada como jusante tem de ser a mais baixa.

Esta passagem CONFERE essa concordância e NUNCA a conserta. Se a cota disser o contrário do sentido declarado,
a resposta traz o problema `contrafluxo` com as duas cotas e o que a cota diria — a geometria, os atributos e o
sentido gravado ficam exatamente como estavam. Inverter o trecho em silêncio seria escolher, por conta própria,
qual das duas declarações do cadastro está errada; quem sabe isso é quem levantou a rede.

Fora da conferência ficam, por decisão declarada no pacote (não no código): os trechos de categoria `recalque`,
onde o sentido é o da bomba e a cota sobe por projeto (linha de recalque, sifão invertido).

Testemunha independente: quando o trecho nomeia os nós das pontas (`no_montante`/`no_jusante`) e essas
estruturas existem na rede com `cota_de_fundo`, as cotas dos POÇOS são comparadas do mesmo jeito. É outra fonte
de dado que a mesma inversão não corrige sozinha."""

CATEGORIA_SOB_PRESSAO = "recalque"
# chaves de escoamento, iguais nos três grupos de trecho do pacote `esgoto-teksi` — é por isso que elas não
# levam o nome do grupo no código do atributo
CHAVE_COTA_MONTANTE = "cota_montante"
CHAVE_COTA_JUSANTE = "cota_jusante"
CHAVE_NO_MONTANTE = "no_montante"
CHAVE_NO_JUSANTE = "no_jusante"
CHAVE_COTA_DE_FUNDO = "cota_de_fundo"
CHAVE_IDENTIFICADOR = "identificador"

SQL_TRECHOS = """
SELECT f.id, f.atributos, g.codigo AS grupo, t.chave AS tipo_chave, t.nome AS tipo_nome,
       tr.codigo AS tier,
       coalesce((SELECT array_agg(c.codigo ORDER BY c.codigo)
                   FROM plat.rede_tipo_categoria tc JOIN plat.rede_categoria c ON c.id = tc.categoria_id
                  WHERE tc.tipo_id = t.id), '{}') AS categorias
  FROM plat.rede_feicao_linha f
  JOIN plat.rede_tipo t ON t.id = f.tipo_id
  JOIN plat.rede_tier tr ON tr.id = t.tier_id
  JOIN plat.rede_grupo g ON g.id = t.grupo_id
  JOIN plat.rede_dominio d ON d.id = g.dominio_id
 WHERE f.rede_id = %s::uuid AND d.disciplina = 'esgoto'
 ORDER BY f.criado_em, f.id
"""

SQL_ESTRUTURAS = """
SELECT f.atributos
  FROM plat.rede_feicao_ponto f
  JOIN plat.rede_tipo t ON t.id = f.tipo_id
  JOIN plat.rede_grupo g ON g.id = t.grupo_id
  JOIN plat.rede_dominio d ON d.id = g.dominio_id
 WHERE f.rede_id = %s::uuid AND d.disciplina = 'esgoto'
"""


def _numero(valor) -> float | None:
    """Cota vinda do jsonb: número, ou texto que representa um número. Qualquer outra coisa é ausência."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        try:
            return float(valor.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _problema(trecho: dict, erro: str, mensagem: str, extra: dict) -> dict:
    p = {
        "feicao_id": str(trecho["id"]),
        "identificador": trecho["atributos"].get(CHAVE_IDENTIFICADOR),
        "grupo": trecho["grupo"],
        "tipo": trecho["tipo_chave"],
        "erro": erro,
        "mensagem": mensagem,
    }
    p.update(extra)
    return p


def _cotas_dos_pocos(estruturas: list[dict]) -> dict[str, float]:
    saida: dict[str, float] = {}
    for e in estruturas:
        atr = e["atributos"] or {}
        ident = atr.get(CHAVE_IDENTIFICADOR)
        cota = _numero(atr.get(CHAVE_COTA_DE_FUNDO))
        if isinstance(ident, str) and cota is not None:
            saida[ident] = cota
    return saida


def conferir(cur, rede_id: str) -> dict:
    """Percorre os trechos de esgoto/drenagem da rede e devolve a conferência. Só lê."""
    cur.execute(SQL_TRECHOS, (rede_id,))
    trechos = cur.fetchall()
    cur.execute(SQL_ESTRUTURAS, (rede_id,))
    cotas_poco = _cotas_dos_pocos(cur.fetchall())

    problemas: list[dict] = []
    conformes = 0
    conferidos = 0
    sob_pressao = 0
    com_testemunha = 0
    for t in trechos:
        atributos = t["atributos"] or {}
        if CATEGORIA_SOB_PRESSAO in (t["categorias"] or []):
            sob_pressao += 1
            continue
        montante = _numero(atributos.get(CHAVE_COTA_MONTANTE))
        jusante = _numero(atributos.get(CHAVE_COTA_JUSANTE))
        if montante is None or jusante is None:
            faltando = [c for c, v in ((CHAVE_COTA_MONTANTE, montante), (CHAVE_COTA_JUSANTE, jusante))
                        if v is None]
            problemas.append(_problema(
                t, "cota_ausente",
                f"o trecho escoa por gravidade e não traz {' e '.join(faltando)}; sem as duas cotas não há como "
                f"conferir o sentido declarado",
                {"cota_montante": montante, "cota_jusante": jusante},
            ))
            continue
        conferidos += 1
        if jusante < montante:
            conformes += 1
        elif jusante > montante:
            problemas.append(_problema(
                t, "contrafluxo",
                f"a ponta declarada como jusante está {jusante - montante:.3f} m ACIMA da de montante "
                f"({montante:.3f} m para {jusante:.3f} m); por cota o escoamento seria no sentido inverso ao "
                f"declarado. O sentido gravado não foi alterado",
                {"cota_montante": montante, "cota_jusante": jusante,
                 "sentido_declarado": "montante_para_jusante", "sentido_por_cota": "jusante_para_montante",
                 "desnivel_m": round(jusante - montante, 3)},
            ))
        else:
            problemas.append(_problema(
                t, "sem_declive",
                f"as duas pontas estão na mesma cota ({montante:.3f} m): sem declive não há escoamento por "
                f"gravidade e a cota não confirma nem desmente o sentido declarado",
                {"cota_montante": montante, "cota_jusante": jusante, "desnivel_m": 0.0},
            ))
        # testemunha independente: as cotas de fundo das duas estruturas nomeadas pelo trecho
        no_m, no_j = atributos.get(CHAVE_NO_MONTANTE), atributos.get(CHAVE_NO_JUSANTE)
        fundo_m, fundo_j = cotas_poco.get(no_m), cotas_poco.get(no_j)
        if fundo_m is not None and fundo_j is not None:
            com_testemunha += 1
            if fundo_j > fundo_m:
                problemas.append(_problema(
                    t, "contrafluxo_nas_estruturas",
                    f"a estrutura de jusante ({no_j}) tem cota de fundo {fundo_j:.3f} m, acima da de montante "
                    f"({no_m}, {fundo_m:.3f} m): a segunda fonte de cota também aponta o sentido inverso",
                    {"no_montante": no_m, "no_jusante": no_j, "cota_de_fundo_montante": fundo_m,
                     "cota_de_fundo_jusante": fundo_j},
                ))
    return {
        "total": len(trechos),
        "sob_pressao": sob_pressao,
        "conferidos": conferidos,
        "conformes": conformes,
        "com_testemunha_nas_estruturas": com_testemunha,
        "percentual_concordancia": round(100.0 * conformes / conferidos, 4) if conferidos else None,
        "alterou_a_rede": False,
        "problemas": problemas,
    }
