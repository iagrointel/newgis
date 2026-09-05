"""Sessão de teste sem senha: `plat.auth_login` + `plat.auth_sessao_criar` (funções SECURITY DEFINER) como plat_app.
Usado pelos testes de API (cookie no TestClient) e pelo e2e (`context.add_cookies`). Aceita a assinatura da 002
(`p_horas`) e a da 003 (`p_max_dias`, que exige o contexto do inquilino do usuário: `plat.contexto_confere`)."""

import psycopg2
import psycopg2.extras

COOKIE_SESSAO = "plat_sessao"


def _assinatura_criar(cur) -> str:
    cur.execute("SELECT pg_get_function_arguments(oid) AS a FROM pg_proc WHERE proname = 'auth_sessao_criar' "
                "AND pronamespace = 'plat'::regnamespace")
    r = cur.fetchone()
    assert r is not None, "plat.auth_sessao_criar ausente (rode db/migrar.sh)"
    return r["a"]


def contexto(cur, tenant_id: int, usuario_id: int, login: str) -> None:
    cur.execute("SET search_path = plat, public")
    cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                "set_config('plat.login', %s, true)", (str(tenant_id), str(usuario_id), login))


def criar_sessao(con, slug: str = "demo", login: str = "admin", horas: int = 2) -> tuple[str, int, int]:
    """Devolve (token em claro, tenant_id, usuario_id). A conexão deve estar com autocommit=False; faz commit."""
    with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, %s)", (slug, login))
        r = cur.fetchone()
        assert r is not None, f"usuário {login} de {slug} não semeado (rode install.sh)"
        assinatura = _assinatura_criar(cur)
        contexto(cur, r["tenant_id"], r["usuario_id"], login)
        if "p_max_dias" in assinatura:
            cur.execute("SELECT plat.auth_sessao_criar(%s, %s, '127.0.0.1', 'pytest') AS tok",
                        (r["usuario_id"], max(1, -(-horas // 24))))
        else:
            cur.execute("SELECT plat.auth_sessao_criar(%s, %s, '127.0.0.1', 'pytest') AS tok", (r["usuario_id"], horas))
        tok = cur.fetchone()["tok"]
    con.commit()
    return tok, int(r["tenant_id"]), int(r["usuario_id"])


def criar_usuario_temporario(con, tenant_id: int, admin_id: int, login: str, perfil: str = "editor") -> int:
    """Cria (ou reaproveita) um usuário do inquilino sob RLS, com hash inválido (nunca faz login por senha)."""
    with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        contexto(cur, tenant_id, admin_id, "admin")
        cur.execute("INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil) VALUES (%s, %s, %s, 'x', %s) "
                    "ON CONFLICT (tenant_id, login) DO UPDATE SET perfil = EXCLUDED.perfil, ativo = true RETURNING id",
                    (tenant_id, login, f"Usuário de teste {login}", perfil))
        uid = cur.fetchone()["id"]
    con.commit()
    return int(uid)


def apagar_usuario_temporario(con, tenant_id: int, admin_id: int, login: str) -> None:
    with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        contexto(cur, tenant_id, admin_id, "admin")
        cur.execute("DELETE FROM plat.job WHERE usuario_id IN (SELECT id FROM plat.usuario WHERE login = %s)", (login,))
        cur.execute("DELETE FROM plat.usuario WHERE login = %s AND tenant_id = %s", (login, tenant_id))
    con.commit()


def conectar(dsn: str):
    con = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    con.autocommit = False
    return con
