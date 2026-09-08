"""Importação de um caso MATPOWER para o grafo da rede (item L4-05-c-pandapower-e-matpower).

O caso do MATPOWER descreve uma rede elétrica SEM COORDENADA NENHUMA. A plataforma tem dois lugares
onde uma rede pode morar:

  * as camadas de feição (`plat.rede_feicao_ponto`/`rede_feicao_linha`), que exigem geometria — coluna
    `geom` NOT NULL — porque existem para desenhar e editar no mapa;
  * o grafo de negócio (`plat.rede_no`/`plat.rede_aresta`, item L4-01-modelo-rede), onde a geometria é
    OPCIONAL e a conectividade é explícita.

O caso MATPOWER vai para o SEGUNDO, com `geom` NULO. Escrever a barra como ponto (0, 0) para caber na
primeira tabela seria inventar uma posição no golfo da Guiné e fazer a barra aparecer no mapa como se
tivesse sido medida. O pacote de ativos `transmissao-matpower` declara os dois grupos com geometria
`sem_geometria`, para que o catálogo diga a mesma coisa que a tabela.

O que a importação faz:
  * matriz `bus`   -> um `plat.rede_no` por barra (papel derivado do tipo e da geração/demanda);
  * matriz `gen`   -> somada por barra e gravada nos ATRIBUTOS da barra (o pacote declara gen_n,
    gen_pg, gen_qg e gen_vg no grupo `barra`);
  * matriz `branch`-> uma `plat.rede_aresta` por ramo, tipo `linha_de_transmissao` quando a relação de
    transformação é zero e `transformador_de_potencia` quando não é.

`comprimento_m` fica NULO: o caseformat não traz comprimento, só impedância em por unidade. O traçado
de menor caminho da casa (`plat.rede_menor_caminho`) trata comprimento nulo como custo zero e CONTA
quantos ramos entraram assim, então um caminho barato demais nunca passa por medição.
"""

from psycopg2.extras import Json, execute_values

from app.rede_utilidades.matpower import COLUNAS_BRANCH, COLUNAS_BUS, COLUNAS_GEN, coluna

LOTE = 2000
# tipo da barra na matriz bus (coluna `type`) -> chave do tipo no pacote transmissao-matpower
TIPO_DA_BARRA = {1: "barra_de_carga", 2: "barra_de_geracao", 3: "barra_de_referencia",
                 4: "barra_isolada"}


class ErroImportacaoMatpower(Exception):
    """Entrada recusada antes de qualquer gravação (rede sem o pacote de transmissão, ramo apontando
    barra que o caso não declara)."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _tipos(cur, rede_id: str) -> dict[str, str]:
    cur.execute(
        "SELECT tp.chave, tp.id FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo IN ('barra', 'ramo')", (rede_id,))
    return {r["chave"]: str(r["id"]) for r in cur.fetchall()}


def _papel(tipo_bus: int, tem_gerador: bool, demanda: float) -> str:
    if tipo_bus == 3 or tem_gerador:
        return "fonte"
    if abs(demanda) > 0:
        return "consumidor"
    return "juncao"


def importar(cur, tenant_id: int, rede_id: str, caso: dict, prefixo: str = "") -> dict:
    """Grava o caso na rede. Devolve as contagens e a lista do que foi lido e não virou objeto.

    `prefixo` entra no `codigo_externo` (que é único por rede): permite importar mais de um caso na
    mesma rede sem colisão. Idempotente por código: reimportar o mesmo caso com o mesmo prefixo não
    duplica nada (`ON CONFLICT DO NOTHING`), e o que não entrou é contado.
    """
    tipos = _tipos(cur, rede_id)
    exigidos = set(TIPO_DA_BARRA.values()) | {"linha_de_transmissao", "transformador_de_potencia"}
    faltando = sorted(exigidos - set(tipos))
    if faltando:
        raise ErroImportacaoMatpower(
            "pacote_de_transmissao_ausente",
            "esta rede não tem o pacote de ativos 'transmissao-matpower' importado: faltam os tipos "
            + ", ".join(faltando))

    # 1. matriz gen somada por barra (o caseformat permite mais de um gerador na mesma barra)
    geracao: dict[int, dict] = {}
    for linha in caso["gen"]:
        if coluna(linha, COLUNAS_GEN, "status") <= 0:
            continue
        numero = int(coluna(linha, COLUNAS_GEN, "bus"))
        g = geracao.setdefault(numero, {"gen_n": 0, "gen_pg": 0.0, "gen_qg": 0.0, "gen_vg": None})
        g["gen_n"] += 1
        g["gen_pg"] += coluna(linha, COLUNAS_GEN, "Pg")
        g["gen_qg"] += coluna(linha, COLUNAS_GEN, "Qg")
        if g["gen_vg"] is None:
            g["gen_vg"] = coluna(linha, COLUNAS_GEN, "Vg")

    # 2. barras
    tuplas = []
    numeros: list[int] = []
    for linha in caso["bus"]:
        numero = int(coluna(linha, COLUNAS_BUS, "bus_i"))
        tipo_bus = int(coluna(linha, COLUNAS_BUS, "type"))
        chave = TIPO_DA_BARRA.get(tipo_bus)
        if chave is None:
            raise ErroImportacaoMatpower(
                "tipo_de_barra_desconhecido",
                f"a barra {numero} declara type = {tipo_bus}, que não está no caseformat 2 (1 a 4)")
        atributos = {nome.lower(): coluna(linha, COLUNAS_BUS, nome) for nome in COLUNAS_BUS}
        atributos.pop("bus_i")
        atributos["bus_i"] = numero
        atributos["bus_type"] = tipo_bus
        atributos["base_kv"] = coluna(linha, COLUNAS_BUS, "baseKV")
        atributos.update(geracao.get(numero, {}))
        demanda = abs(coluna(linha, COLUNAS_BUS, "Pd")) + abs(coluna(linha, COLUNAS_BUS, "Qd"))
        tuplas.append((tenant_id, rede_id, _papel(tipo_bus, numero in geracao, demanda),
                       tipos[chave], f"{prefixo}bus{numero}", Json(atributos)))
        numeros.append(numero)
    for i in range(0, len(tuplas), LOTE):
        execute_values(
            cur,
            # geom fica de fora do INSERT de propósito: NULO, nunca (0, 0). Ver o cabeçalho do módulo.
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, atributos) "
            "VALUES %s ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING",
            tuplas[i:i + LOTE], template="(%s, %s::uuid, %s, %s::uuid, %s, %s)", page_size=LOTE)

    cur.execute("SELECT id, codigo_externo FROM plat.rede_no WHERE rede_id = %s::uuid "
                "AND codigo_externo = ANY(%s)", (rede_id, [f"{prefixo}bus{n}" for n in numeros]))
    id_da_barra = {r["codigo_externo"]: str(r["id"]) for r in cur.fetchall()}
    barras_gravadas = len(id_da_barra)

    # 3. ramos
    tuplas = []
    fora_de_servico = 0
    for i, linha in enumerate(caso["branch"], start=1):
        de = int(coluna(linha, COLUNAS_BRANCH, "fbus"))
        para = int(coluna(linha, COLUNAS_BRANCH, "tbus"))
        no_de = id_da_barra.get(f"{prefixo}bus{de}")
        no_para = id_da_barra.get(f"{prefixo}bus{para}")
        if no_de is None or no_para is None:
            raise ErroImportacaoMatpower(
                "ramo_aponta_barra_inexistente",
                f"o ramo {i} liga as barras {de} e {para}, e o caso não declara as duas")
        if coluna(linha, COLUNAS_BRANCH, "status") <= 0:
            fora_de_servico += 1
        relacao = coluna(linha, COLUNAS_BRANCH, "ratio")
        chave = "transformador_de_potencia" if relacao else "linha_de_transmissao"
        atributos = {nome.lower(): coluna(linha, COLUNAS_BRANCH, nome) for nome in COLUNAS_BRANCH}
        atributos["f_bus"], atributos["t_bus"] = de, para
        atributos["rate_a"] = atributos.pop("ratea")
        atributos.pop("fbus")
        atributos.pop("tbus")
        tuplas.append((tenant_id, rede_id, tipos[chave], f"{prefixo}branch{i}", no_de, no_para,
                       Json(atributos)))
    for i in range(0, len(tuplas), LOTE):
        execute_values(
            cur,
            # no_origem_seq/no_destino_seq entram como 0 e o gatilho rede_aresta_validar copia os seqs
            # reais; comprimento_m e geom ficam NULOS (o caseformat não tem comprimento nem traçado).
            "INSERT INTO plat.rede_aresta (tenant_id, rede_id, tipo_id, codigo_externo, no_origem_id, "
            "no_destino_id, no_origem_seq, no_destino_seq, atributos) VALUES %s "
            "ON CONFLICT (rede_id, codigo_externo) DO NOTHING",
            tuplas[i:i + LOTE],
            template="(%s, %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, 0, 0, %s)", page_size=LOTE)

    cur.execute("SELECT count(*) AS n FROM plat.rede_aresta WHERE rede_id = %s::uuid "
                "AND codigo_externo LIKE %s", (rede_id, f"{prefixo}branch%"))
    ramos_gravados = int(cur.fetchone()["n"])
    cur.execute("SELECT count(*) AS n FROM plat.rede_no WHERE rede_id = %s::uuid "
                "AND codigo_externo LIKE %s AND geom IS NULL", (rede_id, f"{prefixo}bus%"))
    sem_geometria = int(cur.fetchone()["n"])
    return {
        "base_mva": caso["baseMVA"],
        "barras_no_caso": len(caso["bus"]), "barras_gravadas": barras_gravadas,
        "ramos_no_caso": len(caso["branch"]), "ramos_gravados": ramos_gravados,
        "ramos_fora_de_servico": fora_de_servico,
        "geradores_no_caso": len(caso["gen"]), "barras_com_geracao": len(geracao),
        "barras_sem_geometria": sem_geometria,
        "transformadores": sum(1 for b in caso["branch"] if coluna(b, COLUNAS_BRANCH, "ratio")),
        "comprimento_declarado": False,
    }
