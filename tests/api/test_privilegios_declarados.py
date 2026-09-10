"""Regra transversal (ADR 0002 seção 3.4): toda rota autenticada do OpenAPI declara `x-privilegio` e `x-auth`;
privilégio nomeado existe em plat.privilegio; o vocabulário em app/auth/privilegios.py coincide com o banco
(nomes, administrativos e tetos); docs/openapi.json comitado é o da aplicação."""

from pathlib import Path

from app.auth import privilegios as priv
from tests.api.conftest import arquivo_openapi

ROOT = Path(__file__).resolve().parents[2]
SEM_PRIVILEGIO = {"/saude", "/api/versao"}
VALORES_ESPECIAIS = {"publico", "proprio", "vocabulario", "superadmin", "rls:visibilidade"}


def _rotas(spec):
    for caminho, metodos in spec["paths"].items():
        for metodo, op in metodos.items():
            yield metodo.upper(), caminho, op


def test_toda_rota_declara_auth_e_privilegio(conexao_plat_app):
    spec = arquivo_openapi()
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT nome FROM plat.privilegio")
        nomes = {r["nome"] for r in cur.fetchall()}
    faltando = []
    for metodo, caminho, op in _rotas(spec):
        if caminho in SEM_PRIVILEGIO:
            continue
        auth, p = op.get("x-auth"), op.get("x-privilegio")
        if auth not in ("-", "S", "T", "S/T") or not p:
            faltando.append((metodo, caminho))
            continue
        for parte in p.replace("grupo:", "").replace("token:", "").split("|"):
            assert (
                parte in nomes
                or parte in VALORES_ESPECIAIS
                or parte in ("dono", "gerente", "membro", "convidado", "proprio")
            ), (metodo, caminho, parte)
    assert faltando == []


def test_vocabulario_python_igual_ao_banco(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT nome, grupo, descricao, administrativo FROM plat.privilegio ORDER BY nome")
        banco = {r["nome"]: r for r in cur.fetchall()}
        cur.execute("SELECT perfil, privilegio FROM plat.perfil_privilegio")
        tetos = {}
        for r in cur.fetchall():
            tetos.setdefault(r["perfil"], set()).add(r["privilegio"])
    assert set(banco) == set(priv.NOMES) and len(banco) == 48  # 47 + conteudo.exportar (L0-04-h-exportar)
    for nome, grupo, _descricao, adm, _perfis in priv.PRIVILEGIOS:
        assert banco[nome]["grupo"] == grupo and banco[nome]["administrativo"] is adm, nome
    for perfil in priv.PERFIS:
        assert tetos[perfil] == set(priv.teto(perfil)), perfil
    assert tetos["visualizador"] < tetos["editor"] < tetos["admin"] and tetos["campo"] < tetos["admin"]
    assert len(priv.ADMINISTRATIVOS) == 20  # a tabela do ADR diz 18 no rodapé; a contagem linha a linha dá 20


def test_openapi_comitado_esta_contido_na_aplicacao(cliente):
    """Toda rota do arquivo comitado existe na aplicação com os mesmos métodos. A árvore de trabalho é compartilhada
    entre trilhas: a aplicação viva pode ter rotas de outra trilha ainda não comitadas (o arquivo é regerado por quem
    comita a rota, com `make openapi`); rota no arquivo sem existir viva é o erro que este teste pega."""
    arquivo = arquivo_openapi()
    vivo = cliente.get("/api/openapi.json").json()
    for caminho, metodos in arquivo["paths"].items():
        assert caminho in vivo["paths"], caminho
        assert set(metodos) <= set(vivo["paths"][caminho]), caminho
        for metodo, op in metodos.items():
            assert op.get("x-privilegio") == vivo["paths"][caminho][metodo].get("x-privilegio"), (metodo, caminho)
    assert len(arquivo["paths"]) >= 41
