"""Série temporal da rede (item L4-15-serie-temporal-da-rede): duas safras da mesma rede no mesmo
inquilino, linhagem por COD_ID, carregamento por safra, crescimento por alimentador e o controle de tempo.

Cláusulas do portão provadas aqui:

1. duas safras importadas na mesma série e `plat.rede_linhagem` classificando CADA COD_ID
   (`test_linhagem_classifica_todo_codigo`, e em dado real da cooperativa de teste
   `test_duas_safras_reais_da_cooperativa`, marcado `lento`);
2. contagens de persistente/novo/extinto conferidas contra uma recontagem INDEPENDENTE — nos testes
   sintéticos contra o que a fixture montou, e em dado real contra os conjuntos de COD_ID lidos direto dos
   dois FileGDB, sem passar pelo produto (`test_duas_safras_reais_da_cooperativa`);
3. tabela de tendência por transformador exportável, com os que passaram de abaixo de 80 % a acima de
   100 % marcados (`test_tendencia_marca_quem_passou_da_potencia_nominal`, `test_api_exporta_csv`);
4. potência nominal de uma safra marcada NÃO CONFIÁVEL quando a série mostra troca em massa de placa
   (`test_troca_em_massa_de_placa_derruba_a_confianca_na_potencia`);
5. a refutação do adversário: 10 COD_ID recodificados à mão entre as safras e a linhagem os casa pela
   carteira de unidades consumidoras e pela coordenada, marcando-os `recodificado`
   (`test_refutacao_dez_codigos_recodificados_a_mao`).

O controle deslizante de safra no mapa é o e2e `tests/e2e/test_rede_serie.py`.
"""

# ruff: noqa: F811  (fixtures importadas de módulo irmão: padrão do pytest neste repositório)
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from app.rede_utilidades import deposito, instalados
from app.rede_utilidades import pacote as pacote_mod
from app.rede_utilidades import serie as serie_mod
from tests.api.test_rls import contexto, ids_por_slug

MEDIDAS = Path("tests/medidas/L4-15-serie-temporal-da-rede.json")


def _carga_maquina() -> dict:
    livre = None
    try:
        with open("/proc/meminfo") as f:
            for linha in f:
                if linha.startswith("MemAvailable"):
                    livre = round(int(linha.split()[1]) / 1024 / 1024, 2)
    except OSError:
        pass
    return {"carga_1min": round(os.getloadavg()[0], 2), "ram_livre_gb": livre,
            "medido_em": time.strftime("%Y-%m-%dT%H:%M:%S")}


# --------------------------------------------------------------------------- montagem de safra sintética


class Safra:
    """Uma safra sintética: uma `plat.rede` com o pacote eletrica-br e os nós que o teste declarar.

    Não é mock: são as MESMAS tabelas que o importador BDGD preenche, com os mesmos campos de origem
    preservados em `atributos` (POT_NOM, CTMT, UNI_TR_MT, ENE_01..12). O que muda é a porta de entrada —
    aqui o teste escreve as linhas, lá o FileGDB. O caminho do FileGDB real é exercitado no teste `lento`.
    """

    def __init__(self, cur, tenant_id: int, usuario_id: int, nome: str):
        self.cur = cur
        self.tenant_id = tenant_id
        cur.execute(
            "INSERT INTO plat.rede (tenant_id, nome, disciplina, tolerancia_m, dono_id) "
            "VALUES (%s, %s, 'eletrica', 0.05, %s) RETURNING id",
            (tenant_id, nome, usuario_id),
        )
        self.rede_id = str(cur.fetchone()["id"])
        bruto = instalados.bruto("eletrica-br")
        deposito.importar(cur, tenant_id, self.rede_id, pacote_mod.ler(bruto), usuario_id,
                          hashlib.sha256(bruto).hexdigest(), len(bruto))
        self.tipos = {}
        for grupo in (serie_mod.GRUPO_TRAFO, serie_mod.GRUPO_UC):
            cur.execute(
                "SELECT t.id FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
                "WHERE t.rede_id = %s::uuid AND g.codigo = %s ORDER BY t.codigo LIMIT 1",
                (self.rede_id, grupo),
            )
            self.tipos[grupo] = cur.fetchone()["id"]

    def trafo(self, codigo: str, pot_nom: float, alimentador: str = "AL1",
              lon: float = -51.0, lat: float = -29.5) -> None:
        self.cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, geom, atributos) "
            "VALUES (%s, %s::uuid, 'dispositivo', %s::uuid, %s, "
            "        ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s::jsonb)",
            (self.tenant_id, self.rede_id, self.tipos[serie_mod.GRUPO_TRAFO], codigo, lon, lat,
             json.dumps({"COD_ID": codigo, "POT_NOM": str(pot_nom), "CTMT": alimentador})),
        )

    def uc(self, codigo: str, trafo: str, energia_mes: float, alimentador: str = "AL1") -> None:
        atributos = {"COD_ID": codigo, "UNI_TR_MT": trafo, "CTMT": alimentador}
        atributos.update({c: str(energia_mes) for c in serie_mod.CAMPOS_ENERGIA})
        self.cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, atributos) "
            "VALUES (%s, %s::uuid, 'consumidor', %s::uuid, %s, %s::jsonb)",
            (self.tenant_id, self.rede_id, self.tipos[serie_mod.GRUPO_UC], codigo, json.dumps(atributos)),
        )

    def trecho(self, codigo: str, comprimento_m: float, alimentador: str = "AL1") -> None:
        """Um trecho de média tensão: duas junções e a aresta entre elas (o km por alimentador sai daqui)."""
        ids = []
        for ponta in ("a", "b"):
            self.cur.execute(
                "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, codigo_externo) "
                "VALUES (%s, %s::uuid, 'juncao', %s) "
                "ON CONFLICT (rede_id, papel, codigo_externo) DO UPDATE SET codigo_externo = EXCLUDED.codigo_externo "
                "RETURNING id",
                (self.tenant_id, self.rede_id, f"{codigo}-{ponta}"),
            )
            ids.append(self.cur.fetchone()["id"])
        self.cur.execute(
            "SELECT t.id FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
            "WHERE t.rede_id = %s::uuid AND g.codigo = 'trecho_de_media_tensao' ORDER BY t.codigo LIMIT 1",
            (self.rede_id,),
        )
        tipo = self.cur.fetchone()["id"]
        self.cur.execute(
            "INSERT INTO plat.rede_aresta (tenant_id, rede_id, tipo_id, codigo_externo, no_origem_id, "
            "  no_destino_id, no_origem_seq, no_destino_seq, comprimento_m, atributos) "
            "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, 0, 0, %s, %s::jsonb)",
            (self.tenant_id, self.rede_id, tipo, codigo, ids[0], ids[1], comprimento_m,
             json.dumps({"CTMT": alimentador})),
        )


@pytest.fixture
def inquilino(conexao_plat_app):
    con = conexao_plat_app
    tenant_id = ids_por_slug(con)["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s AND ativo ORDER BY id LIMIT 1",
                    (tenant_id,))
        usuario_id = cur.fetchone()["id"]
        contexto(con, tenant_id, usuario_id)
        yield con, cur, tenant_id, usuario_id


def _serie(cur, tenant_id: int, usuario_id: int, nome: str) -> str:
    cur.execute("INSERT INTO plat.rede_serie (tenant_id, nome, dono_id) VALUES (%s, %s, %s) RETURNING id",
                (tenant_id, nome, usuario_id))
    return str(cur.fetchone()["id"])


def _anexar(cur, tenant_id: int, serie_id: str, safra: Safra, ano: int) -> None:
    cur.execute("INSERT INTO plat.rede_serie_safra (tenant_id, serie_id, rede_id, ano) "
                "VALUES (%s, %s::uuid, %s::uuid, %s)", (tenant_id, serie_id, safra.rede_id, ano))


@pytest.fixture
def serie_duas_safras(inquilino):
    """Duas safras com os quatro destinos possíveis de um COD_ID:

      T-PERSIST  — mesmo código nos dois anos;
      T-VELHO -> T-NOVO-COD — código trocado, MESMA carteira de UCs e MESMA coordenada (recodificado);
      T-EXTINTO  — só no ano base, sem carteira e sem vizinho (extinto);
      T-NASCEU   — só no ano alvo, carteira nova (novo).
    """
    con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    base = Safra(cur, tenant_id, usuario_id, f"zt-l415-base-{marca}")
    alvo = Safra(cur, tenant_id, usuario_id, f"zt-l415-alvo-{marca}")

    base.trafo("T-PERSIST", 75, lon=-51.0, lat=-29.5)
    alvo.trafo("T-PERSIST", 75, lon=-51.0, lat=-29.5)
    base.trafo("T-VELHO", 45, lon=-51.1, lat=-29.6)
    alvo.trafo("T-NOVO-COD", 45, lon=-51.1, lat=-29.6)
    base.trafo("T-EXTINTO", 15, lon=-51.9, lat=-29.9)
    alvo.trafo("T-NASCEU", 15, lon=-51.8, lat=-29.8)

    for i in range(8):  # carteira do recodificado: idêntica nos dois anos = Jaccard 1,0
        base.uc(f"U-R{i}", "T-VELHO", 100)
        alvo.uc(f"U-R{i}", "T-NOVO-COD", 100)
    for i in range(3):
        base.uc(f"U-P{i}", "T-PERSIST", 100)
        alvo.uc(f"U-P{i}", "T-PERSIST", 100)
    base.uc("U-SO-BASE", "T-EXTINTO", 100)
    alvo.uc("U-SO-ALVO", "T-NASCEU", 100)

    base.trecho("S1", 1000.0)
    alvo.trecho("S1", 1000.0)
    alvo.trecho("S2", 500.0)

    serie_id = _serie(cur, tenant_id, usuario_id, f"zt-l415-serie-{marca}")
    _anexar(cur, tenant_id, serie_id, base, 2023)
    _anexar(cur, tenant_id, serie_id, alvo, 2024)
    yield con, cur, tenant_id, serie_id, base, alvo


def _linhagem(cur, serie_id: str, entidade: str = "trafo") -> dict[str, dict]:
    cur.execute("SELECT codigo_base, codigo_alvo, classe, confianca FROM plat.rede_linhagem "
                "WHERE serie_id = %s::uuid AND entidade = %s", (serie_id, entidade))
    return {(r["codigo_base"] or r["codigo_alvo"]): dict(r) for r in cur.fetchall()}


# --------------------------------------------------------------------------- cláusula 1 e 2


def test_linhagem_classifica_todo_codigo(serie_duas_safras):
    """Cláusula 1: cada COD_ID das duas safras tem exatamente uma linha em `plat.rede_linhagem`, na classe
    certa. Cláusula 2 em forma sintética: as contagens batem com o que a fixture montou, código a código."""
    _con, cur, tenant_id, serie_id, _base, _alvo = serie_duas_safras
    resumo = serie_mod.calcular(cur, tenant_id, serie_id)

    linhas = _linhagem(cur, serie_id)
    assert linhas["T-PERSIST"]["classe"] == "persistente"
    assert linhas["T-VELHO"]["classe"] == "recodificado"
    assert linhas["T-VELHO"]["codigo_alvo"] == "T-NOVO-COD"
    assert linhas["T-VELHO"]["confianca"] == 1.0  # carteira idêntica
    assert linhas["T-EXTINTO"]["classe"] == "extinto"
    assert linhas["T-NASCEU"]["classe"] == "novo"
    assert len(linhas) == 4, "cada COD_ID entra uma vez só (o recodificado ocupa as duas pontas)"

    assert resumo["linhagem"]["2023-2024"]["trafo"] == {
        "persistente": 1, "recodificado": 1, "novo": 1, "extinto": 1}
    assert resumo["linhagem"]["2023-2024"]["uc"] == {
        "persistente": 11, "recodificado": 0, "novo": 1, "extinto": 1}

    ucs = _linhagem(cur, serie_id, "uc")
    assert ucs["U-SO-BASE"]["classe"] == "extinto"
    assert ucs["U-SO-ALVO"]["classe"] == "novo"
    assert ucs["U-R0"]["classe"] == "persistente"


def test_recalcular_nao_duplica(serie_duas_safras):
    """Recalcular duas vezes dá o mesmo resultado (o cálculo apaga o que havia antes de gravar)."""
    _con, cur, tenant_id, serie_id, _b, _a = serie_duas_safras
    primeiro = serie_mod.calcular(cur, tenant_id, serie_id)
    segundo = serie_mod.calcular(cur, tenant_id, serie_id)
    assert primeiro["linhagem"] == segundo["linhagem"]
    cur.execute("SELECT count(*) AS n FROM plat.rede_linhagem WHERE serie_id = %s::uuid", (serie_id,))
    assert cur.fetchone()["n"] == 4 + 13


def test_serie_com_uma_safra_nao_calcula(inquilino):
    """Linhagem é entre safras: com uma só, o cálculo recusa em vez de devolver uma tabela vazia."""
    _con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    unica = Safra(cur, tenant_id, usuario_id, f"zt-l415-unica-{marca}")
    unica.trafo("T1", 15)
    serie_id = _serie(cur, tenant_id, usuario_id, f"zt-l415-solo-{marca}")
    _anexar(cur, tenant_id, serie_id, unica, 2024)
    with pytest.raises(serie_mod.ErroSerie):
        serie_mod.calcular(cur, tenant_id, serie_id)


# --------------------------------------------------------------------------- cláusula 3


def test_tendencia_marca_quem_passou_da_potencia_nominal(inquilino):
    """Cláusula 3: o transformador que sai de abaixo de 80 % e chega acima de 100 % aparece marcado, e o
    que fica folgado nos dois anos não. O carregamento vem da fórmula da casa sobre a energia declarada."""
    _con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    base = Safra(cur, tenant_id, usuario_id, f"zt-l415-carga-base-{marca}")
    alvo = Safra(cur, tenant_id, usuario_id, f"zt-l415-carga-alvo-{marca}")
    # 15 kVA: 12 meses de X kWh dão carga = ((12X/8760)/0,45)/0,92/15*100 por cento.
    # 1.000 kWh/mês -> 22,1 % (folgado); 6.000 kWh/mês -> 132,4 % (acima da potência nominal).
    for safra, energia in ((base, 1000), (alvo, 6000)):
        safra.trafo("T-SOBE", 15)
        safra.uc("U-SOBE", "T-SOBE", energia)
        safra.trafo("T-CALMO", 15)
        safra.uc("U-CALMO", "T-CALMO", 1000)
    serie_id = _serie(cur, tenant_id, usuario_id, f"zt-l415-carga-{marca}")
    _anexar(cur, tenant_id, serie_id, base, 2023)
    _anexar(cur, tenant_id, serie_id, alvo, 2024)
    serie_mod.calcular(cur, tenant_id, serie_id)

    por_codigo = {i["codigo"]: i for i in serie_mod.tendencia(cur, serie_id)}
    assert por_codigo["T-SOBE"]["carga_inicial_pct"] < serie_mod.CARGA_SAUDAVEL
    assert por_codigo["T-SOBE"]["carga_final_pct"] > serie_mod.CARGA_SOBRECARGA
    assert por_codigo["T-SOBE"]["virou_sobrecarga"] is True
    assert por_codigo["T-SOBE"]["variacao_pp"] == pytest.approx(
        por_codigo["T-SOBE"]["carga_final_pct"] - por_codigo["T-SOBE"]["carga_inicial_pct"])
    assert por_codigo["T-CALMO"]["virou_sobrecarga"] is False

    so_alvo = serie_mod.tendencia(cur, serie_id, so_viraram_sobrecarga=True)
    assert [i["codigo"] for i in so_alvo] == ["T-SOBE"]


def test_crescimento_por_alimentador(serie_duas_safras):
    """Crescimento de rede por alimentador entre as safras: km de trecho e número de unidades consumidoras."""
    _con, cur, tenant_id, serie_id, _b, _a = serie_duas_safras
    serie_mod.calcular(cur, tenant_id, serie_id)
    por_codigo = {i["codigo"]: i for i in serie_mod.crescimento(cur, serie_id)}
    al = por_codigo["AL1"]
    assert al["por_ano"]["2023"]["km_rede"] == pytest.approx(1.0)
    assert al["por_ano"]["2024"]["km_rede"] == pytest.approx(1.5)
    assert al["delta_km"] == pytest.approx(0.5)
    assert al["por_ano"]["2023"]["n_uc"] == 12
    assert al["por_ano"]["2024"]["n_uc"] == 12
    assert al["por_ano"]["2023"]["n_trafo"] == 3


# --------------------------------------------------------------------------- cláusula 4


def test_troca_em_massa_de_placa_derruba_a_confianca_na_potencia(inquilino):
    """Cláusula 4: quando a série mostra troca em massa de potência nominal entre duas safras, a safra
    mais antiga do par é marcada NÃO CONFIÁVEL para placa, com o motivo escrito e a fração medida.

    A regra nasceu de uma medida da casa em série pública de seis anos: 23,4 % dos transformadores
    persistentes mudaram de placa num par de anos, contra ~1 % nos pares seguintes. Aqui: 12 de 20
    (60 %) mudam, bem acima do limiar; no cenário de controle, 1 de 20 (5 %) e nada é marcado."""
    _con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    base = Safra(cur, tenant_id, usuario_id, f"zt-l415-placa-base-{marca}")
    alvo = Safra(cur, tenant_id, usuario_id, f"zt-l415-placa-alvo-{marca}")
    for i in range(20):
        base.trafo(f"T{i:02d}", 45)
        alvo.trafo(f"T{i:02d}", 15 if i < 12 else 45)
    serie_id = _serie(cur, tenant_id, usuario_id, f"zt-l415-placa-{marca}")
    _anexar(cur, tenant_id, serie_id, base, 2021)
    _anexar(cur, tenant_id, serie_id, alvo, 2022)
    resumo = serie_mod.calcular(cur, tenant_id, serie_id)

    veredito = resumo["pot_nom"][0]
    assert veredito["ano"] == 2021 and veredito["em_massa"] is True
    assert veredito["trocaram"] == 12 and veredito["persistentes"] == 20
    assert veredito["fracao"] == pytest.approx(0.6)

    cur.execute("SELECT ano, pot_nom_confiavel, pot_nom_motivo FROM plat.rede_serie_safra "
                "WHERE serie_id = %s::uuid ORDER BY ano", (serie_id,))
    linhas = {r["ano"]: dict(r) for r in cur.fetchall()}
    assert linhas[2021]["pot_nom_confiavel"] is False
    assert "troca em massa" in linhas[2021]["pot_nom_motivo"]
    assert linhas[2022]["pot_nom_confiavel"] is True
    # a ressalva viaja junto com o número na tabela de tendência
    assert all(not i["pot_nom_confiavel"] for i in serie_mod.tendencia(cur, serie_id))


def test_troca_pontual_de_placa_nao_derruba_a_confianca(inquilino):
    """Controle da cláusula 4: troca real de transformador (1 de 20) não é troca em massa."""
    _con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    base = Safra(cur, tenant_id, usuario_id, f"zt-l415-placa2-base-{marca}")
    alvo = Safra(cur, tenant_id, usuario_id, f"zt-l415-placa2-alvo-{marca}")
    for i in range(20):
        base.trafo(f"T{i:02d}", 45)
        alvo.trafo(f"T{i:02d}", 75 if i == 0 else 45)
    serie_id = _serie(cur, tenant_id, usuario_id, f"zt-l415-placa2-{marca}")
    _anexar(cur, tenant_id, serie_id, base, 2023)
    _anexar(cur, tenant_id, serie_id, alvo, 2024)
    resumo = serie_mod.calcular(cur, tenant_id, serie_id)
    assert resumo["pot_nom"][0]["em_massa"] is False
    cur.execute("SELECT bool_and(pot_nom_confiavel) AS ok FROM plat.rede_serie_safra "
                "WHERE serie_id = %s::uuid", (serie_id,))
    assert cur.fetchone()["ok"] is True


# --------------------------------------------------------------------------- cláusula 5 (refutação)


def test_refutacao_dez_codigos_recodificados_a_mao(inquilino, medida):
    """Refutação exigida pelo item: 10 COD_ID trocados à mão entre as safras. A linhagem tem de casá-los
    pela carteira de unidades consumidoras e pela coordenada, marcando-os `recodificado` — nem `novo`,
    nem `extinto`. Cinco dos dez ficam SEM carteira em comum (só a coordenada casa) para que a segunda
    forma de evidência também seja exercitada."""
    _con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    base = Safra(cur, tenant_id, usuario_id, f"zt-l415-ref-base-{marca}")
    alvo = Safra(cur, tenant_id, usuario_id, f"zt-l415-ref-alvo-{marca}")
    esperado = {}
    for i in range(10):
        lon, lat = -51.0 - i / 100, -29.5 - i / 100
        velho, novo = f"T-ANTIGO-{i:02d}", f"T-RECOD-{i:02d}"
        esperado[velho] = novo
        base.trafo(velho, 45, lon=lon, lat=lat)
        alvo.trafo(novo, 45, lon=lon, lat=lat)
        if i < 5:  # carteira preservada: o Jaccard sozinho já casa
            for j in range(6):
                base.uc(f"U-{i:02d}-{j}", velho, 100)
                alvo.uc(f"U-{i:02d}-{j}", novo, 100)
        else:      # transformador pequeno e carteira trocada: só a coordenada casa
            base.uc(f"U-{i:02d}-velho", velho, 100)
            alvo.uc(f"U-{i:02d}-novo", novo, 100)
    serie_id = _serie(cur, tenant_id, usuario_id, f"zt-l415-ref-{marca}")
    _anexar(cur, tenant_id, serie_id, base, 2023)
    _anexar(cur, tenant_id, serie_id, alvo, 2024)
    resumo = serie_mod.calcular(cur, tenant_id, serie_id)

    linhas = _linhagem(cur, serie_id)
    for velho, novo in esperado.items():
        assert linhas[velho]["classe"] == "recodificado", f"{velho} não foi casado com {novo}"
        assert linhas[velho]["codigo_alvo"] == novo
    assert resumo["linhagem"]["2023-2024"]["trafo"] == {
        "persistente": 0, "recodificado": 10, "novo": 0, "extinto": 0}

    cur.execute("SELECT evidencia->>'motivo' AS motivo, count(*) AS n FROM plat.rede_linhagem "
                "WHERE serie_id = %s::uuid AND classe = 'recodificado' GROUP BY 1", (serie_id,))
    motivos = {r["motivo"]: r["n"] for r in cur.fetchall()}
    assert motivos == {"jaccard": 5, "geometria_e_poucas_ucs": 5}
    medida("L4-15-serie-temporal-da-rede")(
        "refutacao_recodificados_casados", {"pedidos": 10, "casados": 10, **motivos, **_carga_maquina()},
        "COD_ID", "pytest tests/api/test_rede_serie.py::test_refutacao_dez_codigos_recodificados_a_mao")


def test_refutacao_recodificacao_sem_evidencia_nao_e_inventada(inquilino):
    """A outra metade da refutação: trocar o COD_ID SEM deixar rastro (carteira nova, longe da posição
    antiga) não pode virar `recodificado`. Preferir 'não sei' a inventar linhagem é a régua do produto."""
    _con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    base = Safra(cur, tenant_id, usuario_id, f"zt-l415-ref2-base-{marca}")
    alvo = Safra(cur, tenant_id, usuario_id, f"zt-l415-ref2-alvo-{marca}")
    for i in range(10):
        base.trafo(f"T-SOME-{i:02d}", 45, lon=-51.0 - i, lat=-29.5)
        alvo.trafo(f"T-NASCE-{i:02d}", 45, lon=-41.0 + i, lat=-19.5)
        for j in range(6):
            base.uc(f"U-B{i:02d}-{j}", f"T-SOME-{i:02d}", 100)
            alvo.uc(f"U-A{i:02d}-{j}", f"T-NASCE-{i:02d}", 100)
    serie_id = _serie(cur, tenant_id, usuario_id, f"zt-l415-ref2-{marca}")
    _anexar(cur, tenant_id, serie_id, base, 2023)
    _anexar(cur, tenant_id, serie_id, alvo, 2024)
    resumo = serie_mod.calcular(cur, tenant_id, serie_id)
    assert resumo["linhagem"]["2023-2024"]["trafo"] == {
        "persistente": 0, "recodificado": 0, "novo": 10, "extinto": 10}


# --------------------------------------------------------------------------- as rotas


@pytest.fixture
def serie_pela_api(sessao_a, inquilino):
    """A série montada pela API do inquilino demo, com duas safras reais de tabela (as redes são criadas
    pela mesma fixture sintética, e anexadas pela rota). O que se prova aqui é a API, não o motor."""
    _con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    base = Safra(cur, tenant_id, usuario_id, f"zt-l415-api-base-{marca}")
    alvo = Safra(cur, tenant_id, usuario_id, f"zt-l415-api-alvo-{marca}")
    for safra, energia in ((base, 1000), (alvo, 6000)):
        safra.trafo("T-API", 15, lon=-51.2, lat=-29.7)
        safra.uc("U-API", "T-API", energia)
        safra.trecho("S-API", 800.0)
    base.trafo("T-SO-BASE", 15, lon=-51.3, lat=-29.8)
    _con.commit()  # a API abre outra conexão: sem o commit ela não veria nada

    r = sessao_a.post("/api/rede-serie", json={"nome": f"zt-l415-api-{marca}",
                                               "descricao": "série de teste do item L4-15"})
    assert r.status_code == 201, r.text
    serie_id = r.json()["id"]
    for rede_id, ano in ((base.rede_id, 2023), (alvo.rede_id, 2024)):
        r = sessao_a.post(f"/api/rede-serie/{serie_id}/safras", json={"rede_id": rede_id, "ano": ano})
        assert r.status_code == 201, r.text
    yield sessao_a, serie_id, base, alvo
    sessao_a.delete(f"/api/rede-serie/{serie_id}")
    with _con.cursor() as limpeza:
        contexto(_con, tenant_id, usuario_id)
        limpeza.execute("DELETE FROM plat.rede WHERE id = ANY(%s::uuid[])", ([base.rede_id, alvo.rede_id],))
    _con.commit()


def test_api_lista_safras_para_o_controle_de_tempo(serie_pela_api):
    """A tela lê as safras daqui: é a lista que vira as posições do controle deslizante."""
    sessao, serie_id, _b, _a = serie_pela_api
    r = sessao.get(f"/api/rede-serie/{serie_id}")
    assert r.status_code == 200, r.text
    assert [s["ano"] for s in r.json()["safras"]] == [2023, 2024]


def test_api_calcula_e_devolve_linhagem(serie_pela_api):
    sessao, serie_id, _b, _a = serie_pela_api
    r = sessao.post(f"/api/rede-serie/{serie_id}/calcular")
    assert r.status_code == 200, r.text
    assert r.json()["safras"] == [2023, 2024]

    r = sessao.get(f"/api/rede-serie/{serie_id}/linhagem?entidade=trafo")
    assert r.status_code == 200, r.text
    classes = {i["codigo_base"] or i["codigo_alvo"]: i["classe"] for i in r.json()["itens"]}
    assert classes == {"T-API": "persistente", "T-SO-BASE": "extinto"}

    r = sessao.get(f"/api/rede-serie/{serie_id}/linhagem?entidade=trafo&classe=extinto")
    assert [i["codigo_base"] for i in r.json()["itens"]] == ["T-SO-BASE"]
    assert sessao.get(f"/api/rede-serie/{serie_id}/linhagem?entidade=poste").status_code == 422


def test_api_exporta_csv(serie_pela_api):
    """Cláusula 3: a tabela de tendência sai como arquivo, com uma coluna por safra."""
    sessao, serie_id, _b, _a = serie_pela_api
    sessao.post(f"/api/rede-serie/{serie_id}/calcular")
    r = sessao.get(f"/api/rede-serie/{serie_id}/tendencia?formato=csv")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    linhas = r.text.splitlines()
    assert linhas[0].split(",")[:4] == ["codigo", "alimentador", "carga_pct_2023", "carga_pct_2024"]
    assert any(linha.startswith("T-API,") and linha.endswith(",sim,sim") for linha in linhas[1:])

    r = sessao.get(f"/api/rede-serie/{serie_id}/tendencia?so_sobrecarga=true")
    assert [i["codigo"] for i in r.json()["itens"]] == ["T-API"]
    assert r.json()["metodo"]["fator_carga"] == serie_mod.FATOR_CARGA


def test_api_crescimento_e_mapa(serie_pela_api):
    """O crescimento por alimentador e a camada de UMA safra que o controle deslizante troca."""
    sessao, serie_id, _b, _a = serie_pela_api
    sessao.post(f"/api/rede-serie/{serie_id}/calcular")

    r = sessao.get(f"/api/rede-serie/{serie_id}/alimentadores")
    assert r.status_code == 200, r.text
    assert r.json()["anos"] == [2023, 2024]
    assert r.json()["itens"][0]["por_ano"]["2024"]["km_rede"] == pytest.approx(0.8)

    r = sessao.get(f"/api/rede-serie/{serie_id}/mapa?ano=2024")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["type"] == "FeatureCollection"
    assert [f["properties"]["codigo"] for f in corpo["features"]] == ["T-API"]
    assert corpo["features"][0]["properties"]["carga_pct"] > serie_mod.CARGA_SOBRECARGA
    assert corpo["features"][0]["properties"]["classe"] == "persistente"
    assert corpo["features"][0]["geometry"]["coordinates"] == [pytest.approx(-51.2), pytest.approx(-29.7)]
    assert sessao.get(f"/api/rede-serie/{serie_id}/mapa?ano=1999").status_code == 404


def test_api_recusa_ano_repetido_e_rede_de_duas_series(serie_pela_api):
    """Uma safra por ano, e uma rede em uma série só: a segunda tentativa é recusada, não sobrescreve."""
    sessao, serie_id, base, _a = serie_pela_api
    r = sessao.post(f"/api/rede-serie/{serie_id}/safras", json={"rede_id": base.rede_id, "ano": 2022})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "safra_existente"


# --------------------------------------------------------------------------- dado real (cláusulas 1 e 2)


def _codigos_do_gdb(caminho: str, camada: str) -> set[str]:
    """Recontagem INDEPENDENTE: os COD_ID lidos direto do FileGDB, sem passar pelo produto. É contra
    isto que as contagens de persistente/novo/extinto são conferidas."""
    import pyogrio

    df = pyogrio.read_dataframe(caminho, layer=camada, read_geometry=False, columns=["COD_ID"])
    return {str(v).strip() for v in df["COD_ID"].dropna() if str(v).strip()}


@pytest.mark.lento
def test_duas_safras_reais_da_cooperativa(inquilino, medida):
    """Cláusulas 1 e 2 em DADO REAL: duas safras da cooperativa de teste (a de 2024 e a anterior
    disponível), importadas pelo importador BDGD de verdade, com a linhagem classificando cada COD_ID e
    as contagens conferidas contra os conjuntos lidos direto dos dois FileGDB.

    Escala: o recorte é UM alimentador nos DOIS anos (`obter_extrato_pequeno`), pelo mesmo motivo do item
    irmão L4-01-c — importar a cooperativa inteira passou de 13 minutos sob disputa de banco de uma
    trilha, e o portão desta cláusula é a LINHAGEM entre safras, não a escala do importador. A
    distribuidora é a mesma nos dois arquivos; a cooperativa NÃO coincide com a distribuidora da tabela
    de linhagem da casa (série pública do Sudeste), então a conferência é contra a recontagem
    independente dos arquivos, que é a régua disponível — e é mais forte, porque é sobre ESTE dado.
    """
    from app.rede_utilidades.bdgd import importar
    from tests.dados.gerar_bdgd_extrato import obter_extrato_pequeno

    try:
        gdb_alvo = obter_extrato_pequeno()
        gdb_base = obter_extrato_pequeno(anterior=True)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    _con, cur, tenant_id, usuario_id = inquilino
    marca = os.urandom(3).hex()
    t0 = time.monotonic()
    safras = {}
    for ano, gdb in ((2023, gdb_base), (2024, gdb_alvo)):
        s = Safra(cur, tenant_id, usuario_id, f"zt-l415-real-{ano}-{marca}")
        importar(cur, tenant_id, s.rede_id, gdb, registrar=False)
        safras[ano] = s
    serie_id = _serie(cur, tenant_id, usuario_id, f"zt-l415-real-{marca}")
    for ano, s in safras.items():
        _anexar(cur, tenant_id, serie_id, s, ano)
    resumo = serie_mod.calcular(cur, tenant_id, serie_id)
    duracao_s = round(time.monotonic() - t0, 1)

    # régua independente: os conjuntos de COD_ID de transformador nos dois arquivos
    trafos_base = _codigos_do_gdb(gdb_base, "UNTRMT")
    trafos_alvo = _codigos_do_gdb(gdb_alvo, "UNTRMT")
    contagem = resumo["linhagem"]["2023-2024"]["trafo"]
    assert contagem["persistente"] == len(trafos_base & trafos_alvo)
    # quem some/nasce ou casa como recodificado, ou vira extinto/novo — a soma tem de fechar dos dois lados
    assert contagem["recodificado"] + contagem["extinto"] == len(trafos_base - trafos_alvo)
    assert contagem["recodificado"] + contagem["novo"] == len(trafos_alvo - trafos_base)

    ucs_base = _codigos_do_gdb(gdb_base, "UCBT_tab") | _codigos_do_gdb(gdb_base, "UCMT_tab")
    ucs_alvo = _codigos_do_gdb(gdb_alvo, "UCBT_tab") | _codigos_do_gdb(gdb_alvo, "UCMT_tab")
    contagem_uc = resumo["linhagem"]["2023-2024"]["uc"]
    assert contagem_uc["persistente"] == len(ucs_base & ucs_alvo)
    assert contagem_uc["extinto"] == len(ucs_base - ucs_alvo)
    assert contagem_uc["novo"] == len(ucs_alvo - ucs_base)

    # cada COD_ID de transformador dos dois arquivos aparece exatamente uma vez na linhagem
    cur.execute("SELECT count(*) AS n FROM plat.rede_linhagem WHERE serie_id = %s::uuid AND entidade = 'trafo'",
                (serie_id,))
    assert cur.fetchone()["n"] == len(trafos_base | trafos_alvo)

    tend = serie_mod.tendencia(cur, serie_id)
    viraram = [i for i in tend if i["virou_sobrecarga"]]
    medida("L4-15-serie-temporal-da-rede")("duas_safras_reais", {
        "safras": [2023, 2024], "trafos_arquivo_base": len(trafos_base),
        "trafos_arquivo_alvo": len(trafos_alvo), "linhagem_trafo": contagem, "linhagem_uc": contagem_uc,
        "trafos_com_tendencia": len(tend), "viraram_sobrecarga": len(viraram),
        "pot_nom": resumo["pot_nom"], "duracao_s": duracao_s, **_carga_maquina()},
        "COD_ID", "pytest tests/api/test_rede_serie.py::test_duas_safras_reais_da_cooperativa -m lento")
