"""Eventos de domínio (ADR 0002 seção 9.4): toda rota de escrita do OpenAPI tem entrada em eventos_esperados.py;
todo tipo citado existe em plat.evento_tipo; o vocabulário do ADR está inteiro no banco; os eventos de uma
sequência real (criar usuário → mudar perfil → apagar) aparecem com antes/depois e sem segredo."""

import secrets
from pathlib import Path

from tests.api.conftest import PREFIXO_TESTE, arquivo_openapi
from tests.api.eventos_esperados import EVENTOS_POR_ROTA, ROTAS_SEM_EVENTO

ROOT = Path(__file__).resolve().parents[2]

VOCABULARIO_ADR = {
    "usuarios/entrar",
    "usuarios/sair",
    "usuarios/falha_login",
    "usuarios/criar",
    "usuarios/atualizar",
    "usuarios/desabilitar",
    "usuarios/reabilitar",
    "usuarios/apagar",
    "usuarios/papel",
    "usuarios/redefinir_senha",
    "usuarios/trocar_senha",
    "usuarios/2fa_ligar",
    "usuarios/2fa_desligar",
    "usuarios/desbloquear",
    "papeis/criar",
    "papeis/atualizar",
    "papeis/apagar",
    "grupos/criar",
    "grupos/atualizar",
    "grupos/apagar",
    "grupos/transferir",
    "grupos/convidar",
    "grupos/pedir",
    "grupos/aprovar",
    "grupos/entrar",
    "grupos/sair",
    "grupos/remover",
    "grupos/papel",
    "tokens/criar",
    "tokens/renovar",
    "tokens/revogar",
    "sessoes/revogar",
    "inquilinos/criar",
    "inquilinos/suspender",
    "inquilinos/reativar",
}


def rotas_de_escrita() -> set[tuple[str, str]]:
    spec = arquivo_openapi()
    return {
        (m.upper(), c) for c, ms in spec["paths"].items() for m in ms if m.upper() in ("POST", "PUT", "DELETE", "PATCH")
    }


def test_toda_rota_de_escrita_tem_evento_declarado(conexao_plat_app):
    escrita = rotas_de_escrita()
    declaradas = set(EVENTOS_POR_ROTA) | set(ROTAS_SEM_EVENTO)
    faltando = sorted(escrita - declaradas)
    assert faltando == [], faltando
    sobrando = sorted(declaradas - escrita)
    assert sobrando == [], sobrando
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT nome FROM plat.evento_tipo")
        tipos = {r["nome"] for r in cur.fetchall()}
    citados = {t for lista in EVENTOS_POR_ROTA.values() for t in lista}
    assert citados <= tipos, citados - tipos
    assert VOCABULARIO_ADR <= tipos, VOCABULARIO_ADR - tipos


def test_declaracao_de_evento_nunca_e_vazia():
    """Achado G4-03: a cobertura media DECLARAÇÃO e aceitava lista vazia — `POST` e `DELETE /api/arquivos`
    estavam registrados como 'sem evento' e o guardião aprovava destruição de objeto do inquilino sem rastro."""
    vazias = sorted(k for k, v in EVENTOS_POR_ROTA.items() if not v)
    assert vazias == [], f"declaração vazia em EVENTOS_POR_ROTA (use ROTAS_SEM_EVENTO com motivo): {vazias}"


def test_rota_sem_evento_tem_motivo_escrito_e_nao_se_repete():
    """A saída de emergência existe, mas é cara: motivo escrito por extenso, uma lista só, sem sobreposição."""
    repetidas = sorted(set(EVENTOS_POR_ROTA) & set(ROTAS_SEM_EVENTO))
    assert repetidas == [], repetidas
    curtos = sorted(k for k, motivo in ROTAS_SEM_EVENTO.items() if len((motivo or "").strip()) < 40)
    assert curtos == [], f"motivo ausente ou curto demais em ROTAS_SEM_EVENTO: {curtos}"


def test_todo_tipo_declarado_aparece_no_codigo():
    """Mede FATO, não só declaração: cada tipo citado tem de existir como literal em `app/` (a chamada que o
    grava) ou em `db/migracoes/` (os eventos que o próprio banco registra, como o login)."""
    fontes = ""
    for base in (ROOT / "app", ROOT / "db" / "migracoes"):
        for arq in base.rglob("*"):
            if arq.suffix in (".py", ".sql"):
                fontes += arq.read_text(encoding="utf-8")
    citados = {t for lista in EVENTOS_POR_ROTA.values() for t in lista}
    ausentes = sorted(t for t in citados if f'"{t}"' not in fontes and f"'{t}'" not in fontes)
    assert ausentes == [], f"tipo declarado que nenhuma linha de código grava: {ausentes}"


def test_sequencia_real_gera_eventos_com_antes_depois_e_sem_segredo(sessao_a, usuarios_a):
    u, temporaria = usuarios_a.criar("visualizador")
    assert sessao_a.put(f"/api/usuarios/{u['id']}", json={"perfil": "editor"}).status_code == 200
    assert (
        sessao_a.put(f"/api/usuarios/{u['id']}", json={"nome": "Nome novo " + secrets.token_hex(1)}).status_code == 200
    )
    assert sessao_a.delete(f"/api/usuarios/{u['id']}").status_code == 204
    usuarios_a.criados.remove(u["id"])
    itens = sessao_a.get("/api/eventos?limite=50").json()["itens"]
    meus = [e for e in itens if e["alvo_tipo"] == "usuario" and e["alvo_id"] == str(u["id"])]
    tipos = [e["tipo"] for e in reversed(meus)]
    assert tipos == ["usuarios/criar", "usuarios/papel", "usuarios/atualizar", "usuarios/apagar"], tipos
    papel = next(e for e in meus if e["tipo"] == "usuarios/papel")
    assert papel["propriedades"] == {
        "antes": {"perfil": "visualizador", "papel_id": None},
        "depois": {"perfil": "editor", "papel_id": None},
    }
    assert all(e["req_id"] and e["ip"] and e["ator"]["login"] for e in meus)
    texto = str(itens)
    assert temporaria not in texto and "senha_hash" not in texto and PREFIXO_TESTE in texto
