"""Trava da reescrita de schema (app/schema_ambiente.py, item L7-31).

Em 06/09/2026 o MESMO defeito apareceu três vezes num dia: o `bytes` que `psycopg2.extras.execute_values` manda ao
cursor, as conexões de teste e o `executemany` de `POST`/`PUT /api/papeis`. Nos três casos a consulta escapou da
reescrita e foi para o schema `plat` de PRODUÇÃO com `PLAT_SCHEMA` apontando para outro lugar; nos três, o 42501
que voltava chegava ao cliente como 403 "operação fora do inquilino da sessão", e uma prova de isolamento entre
inquilinos passou a rodar contra o schema errado.

Este arquivo fecha a classe do defeito em vez de tapar buraco por buraco:

1. `test_todo_ponto_de_entrada_com_consulta_esta_declarado` reprova se o cursor do psycopg2 tiver um método que
   carrega comando SQL e que não esteja nem coberto nem declarado como fora de cobertura com a razão escrita;
2. `test_a_casa_nao_usa_ponto_de_entrada_fora_de_cobertura` reprova se alguém começar a usar, no código de
   produção, um dos pontos que hoje ficam de fora (`copy_from`, `copy_to`);
3. `test_cada_metodo_coberto_entrega_a_consulta_reescrita` chama CADA método coberto sobre uma base espiã, sem
   banco, e confere o que chegaria ao driver — em texto e em bytes;
4. `test_no_op_no_schema_padrao` prova que produção continua sem pagar nada.

Sem estes quatro, a classe volta.
"""

import inspect

import psycopg2.extensions
import psycopg2.extras
import pytest

import app.settings
from app.schema_ambiente import (
    SCHEMA_PADRAO,
    SCHEMA_TRABALHO_PADRAO,
    CursorSchemaAmbiente,
    MixinReescritaSchema,
    reescrever_schema,
)

# O que, na API de cursor do psycopg2 2.x, recebe um comando SQL ou um nome de objeto do schema. Lista escrita à
# mão a partir da documentação do driver: é ela que o teste 1 confronta com o que a casa cobre.
PONTOS_DE_ENTRADA_DO_DRIVER = {
    "execute": "comando SQL (str, bytes ou Composable)",
    "executemany": "comando SQL repetido para cada tupla de parâmetros",
    "callproc": "nome da função/procedimento (pode vir com schema)",
    "mogrify": "comando SQL; devolve o texto que iria ao servidor",
    "copy_expert": "comando COPY inteiro, em texto",
    "copy_from": "NOME de tabela, que também leva o prefixo do schema",
    "copy_to": "NOME de tabela, que também leva o prefixo do schema",
}
SCHEMA_DE_TESTE = "plat_tteste"
SCHEMA_TRABALHO_DE_TESTE = "plat_trabalho_tteste"


class BaseEspia:
    """Fica no lugar do cursor do psycopg2 na MRO: guarda o que o mixin entregaria ao driver."""

    def __init__(self):
        self.recebido: list[tuple[str, object]] = []

    def execute(self, query, *args, **kwargs):
        self.recebido.append(("execute", query))

    def executemany(self, query, *args, **kwargs):
        self.recebido.append(("executemany", query))

    def callproc(self, procname, *args, **kwargs):
        self.recebido.append(("callproc", procname))

    def mogrify(self, query, *args, **kwargs):
        self.recebido.append(("mogrify", query))
        return query

    def copy_expert(self, sql, *args, **kwargs):
        self.recebido.append(("copy_expert", sql))


class CursorEspiao(MixinReescritaSchema, BaseEspia):
    """A MESMA reescrita da produção (o mixin não é copiado, é importado) sobre uma base sem banco."""


class _SettingsDeTeste:
    """`app.settings.settings` é uma dataclass congelada; a reescrita lê o atributo do MÓDULO a cada chamada
    (`from app.settings import settings` dentro da função), então a troca é do módulo, não do objeto."""

    def __init__(self, schema: str, schema_trabalho: str):
        self.PLAT_SCHEMA = schema
        self.PLAT_SCHEMA_TRABALHO = schema_trabalho


@pytest.fixture
def fora_do_schema_padrao(monkeypatch):
    monkeypatch.setattr(app.settings, "settings", _SettingsDeTeste(SCHEMA_DE_TESTE, SCHEMA_TRABALHO_DE_TESTE))


@pytest.fixture
def no_schema_padrao(monkeypatch):
    monkeypatch.setattr(app.settings, "settings", _SettingsDeTeste(SCHEMA_PADRAO, SCHEMA_TRABALHO_PADRAO))


# ================================================================ 1. a trava
def test_todo_ponto_de_entrada_com_consulta_esta_declarado():
    """Se o driver tiver um método que carrega comando e a casa não o cobrir nem declarar por que não cobre, este
    teste reprova. É o que impede o defeito de voltar por um caminho novo."""
    cobertos = set(MixinReescritaSchema.METODOS_COM_CONSULTA)
    declarados_de_fora = set(MixinReescritaSchema.METODOS_FORA_DE_COBERTURA)
    assert not (cobertos & declarados_de_fora), "método coberto e declarado fora ao mesmo tempo"

    # (a) tudo o que a lista do driver traz está num dos dois lados
    faltando = set(PONTOS_DE_ENTRADA_DO_DRIVER) - cobertos - declarados_de_fora
    assert not faltando, f"ponto de entrada sem decisão escrita: {sorted(faltando)}"

    # (b) o que a casa diz cobrir existe mesmo no cursor do psycopg2 e está sobrescrito no mixin
    for nome in cobertos:
        assert hasattr(psycopg2.extensions.cursor, nome), f"{nome} não existe no cursor do psycopg2"
        assert nome in MixinReescritaSchema.__dict__, f"{nome} está na lista mas não foi sobrescrito"
        assert "self._reescrever(" in inspect.getsource(getattr(MixinReescritaSchema, nome)), \
            f"{nome} foi sobrescrito sem chamar a reescrita"

    # (c) toda razão de exclusão é uma frase escrita, não um vazio
    for nome, razao in MixinReescritaSchema.METODOS_FORA_DE_COBERTURA.items():
        assert isinstance(razao, str) and len(razao) > 30, f"{nome}: razão de exclusão vaga ou ausente"

    # (d) e nenhum método público do mixin ficou de fora da lista (o que fecha o outro lado da porta)
    publicos = {n for n, f in vars(MixinReescritaSchema).items()
                if callable(f) and not n.startswith("_") and n not in ("METODOS_COM_CONSULTA",
                                                                       "METODOS_FORA_DE_COBERTURA")}
    assert publicos == cobertos, f"método público do mixin fora da lista declarada: {sorted(publicos ^ cobertos)}"


def test_a_casa_nao_usa_ponto_de_entrada_fora_de_cobertura():
    """`copy_from`/`copy_to` ficam de fora porque ninguém usa. No dia em que alguém usar, este teste reprova e
    obriga a cobrir antes — em vez de a homologação descobrir sozinha."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    ofensas = []
    for pasta in ("app", "scripts", "db"):
        for arquivo in (raiz / pasta).rglob("*.py"):
            texto = arquivo.read_text(encoding="utf-8")
            for nome in MixinReescritaSchema.METODOS_FORA_DE_COBERTURA:
                if f".{nome}(" in texto:
                    ofensas.append(f"{arquivo.relative_to(raiz)}: usa .{nome}(")
    assert not ofensas, "ponto de entrada fora de cobertura em uso: " + "; ".join(ofensas)


def test_o_cursor_de_producao_usa_o_mixin_antes_do_psycopg2():
    """A ordem importa: o mixin tem de vir antes do cursor do driver, senão `super()` não chega ao psycopg2."""
    mro = [c.__name__ for c in CursorSchemaAmbiente.__mro__]
    assert mro.index("MixinReescritaSchema") < mro.index("RealDictCursor") < mro.index("cursor")


# ================================================================ 2. comportamento, método a método
CONSULTA = "SELECT 1 FROM plat.papel_privilegio JOIN plat_trabalho.tmp USING (id)"
ESPERADO = f"SELECT 1 FROM {SCHEMA_DE_TESTE}.papel_privilegio JOIN {SCHEMA_TRABALHO_DE_TESTE}.tmp USING (id)"


@pytest.mark.parametrize("metodo", sorted(MixinReescritaSchema.METODOS_COM_CONSULTA))
@pytest.mark.parametrize("tipo", ["texto", "bytes"])
def test_cada_metodo_coberto_entrega_a_consulta_reescrita(fora_do_schema_padrao, metodo, tipo):
    cur = CursorEspiao()
    entrada = CONSULTA if tipo == "texto" else CONSULTA.encode("utf-8")
    getattr(cur, metodo)(entrada, [])
    assert cur.recebido, f"{metodo} não chegou à base"
    nome, chegou = cur.recebido[-1]
    assert nome == metodo
    assert chegou == (ESPERADO if tipo == "texto" else ESPERADO.encode("utf-8")), chegou
    assert isinstance(chegou, type(entrada)), "o tipo que entrou tem de ser o tipo que sai"


def test_executemany_era_o_terceiro_buraco_da_mesma_classe(fora_do_schema_padrao):
    """`POST`/`PUT /api/papeis` gravam os privilégios do papel por `executemany`: sem esta cobertura as duas rotas
    batiam no schema `plat` de produção mesmo em base isolada, e `tests/api/test_cruzado.py` — a prova de
    isolamento entre inquilinos — terminava com erro fora de produção."""
    cur = CursorEspiao()
    cur.executemany("INSERT INTO plat.papel_privilegio(papel_id, privilegio) VALUES (%s, %s)", [(1, "a")])
    assert cur.recebido[-1][1] == f"INSERT INTO {SCHEMA_DE_TESTE}.papel_privilegio(papel_id, privilegio) " \
                                 "VALUES (%s, %s)"


def test_bytes_nao_utf8_passa_cru_em_vez_de_corromper(fora_do_schema_padrao):
    cru = b"SELECT 1 FROM plat.item -- \xff\xfe"
    cur = CursorEspiao()
    cur.execute(cru)
    assert cur.recebido[-1][1] == cru


def test_tipo_desconhecido_passa_cru(fora_do_schema_padrao):
    """Um `psycopg2.sql.Composed` (que a casa não usa) não é reescrito: passa como sempre passou, sem erro."""
    from psycopg2 import sql

    composto = sql.SQL("SELECT 1 FROM {}").format(sql.Identifier("plat", "item"))
    cur = CursorEspiao()
    cur.execute(composto)
    assert cur.recebido[-1][1] is composto


# ================================================================ 3. produção não muda
@pytest.mark.parametrize("metodo", sorted(MixinReescritaSchema.METODOS_COM_CONSULTA))
def test_no_op_no_schema_padrao(no_schema_padrao, metodo):
    """No schema padrão a consulta sai IDÊNTICA — o mesmo objeto, sem passar por regex nenhuma."""
    cur = CursorEspiao()
    getattr(cur, metodo)(CONSULTA, [])
    assert cur.recebido[-1][1] is CONSULTA
    cru = CONSULTA.encode("utf-8")
    getattr(cur, metodo)(cru, [])
    assert cur.recebido[-1][1] is cru


def test_reescrever_schema_nao_toca_no_guc():
    """A regex continua excluindo o GUC de sessão: quem grava (set_config) e quem lê (current_setting) têm de
    continuar batendo em qualquer ambiente."""
    sql = ("SELECT set_config('plat.tenant_id', '1', true), current_setting('plat.usuario_id', true) "
           "FROM plat.usuario")
    saida = reescrever_schema(sql, SCHEMA_DE_TESTE, SCHEMA_TRABALHO_DE_TESTE)
    assert "set_config('plat.tenant_id'" in saida and "current_setting('plat.usuario_id'" in saida
    assert f"FROM {SCHEMA_DE_TESTE}.usuario" in saida
