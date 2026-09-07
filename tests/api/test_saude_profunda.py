"""Item L7-34-saude-profunda: GET /saude/profunda. Portão de pronto (laco/vivo/prompts/L7-34-saude-profunda.md):
(1) componente parado de propósito vira `erro` em <=10s e o geral acompanha a tabela declarada; (2) resposta
anônima não vaza host/porta/versão; (3) sonda com tempo limite individual não trava o endpoint (Garage
pendurado); (4) 200/503 coerente com o uso pelo balanceador.

Nota sobre "componente derrubado de verdade" (retomada): banco é isento por D22 (Postgres compartilhado com
dezenas de frentes da casa). O Garage e o nginx desta máquina são a MESMA classe de risco: um único processo
serve TODAS as trilhas simultâneas (`pgrep -af garage` mostra um só, de `plataforma/pipeline/garage`, e nginx é
o servidor web da máquina inteira) — pendurá-los de verdade (SIGSTOP/iptables) derrubaria o teste de todo mundo
que está rodando ao mesmo tempo, não só este item. Por isso o teste de "sonda pendurada" usa um servidor TCP
de verdade, isolado neste processo, que aceita a conexão e nunca responde — reproduz bit a bit o sintoma real
(handshake TCP completo, sem resposta HTTP) sem tocar nenhuma infraestrutura compartilhada. Já a `fila` É
verificada com o worker de verdade fora do ar: esta trilha não sobe `plat-worker` nenhum (schema isolado
`plat_til734saudep`), então `workers_vivos == 0` já é o estado real, não simulado."""

import json
import socket
import threading
import time

import pytest

COMPONENTES_ESPERADOS = {
    "banco", "fila", "martin", "titiler", "garage", "worker", "nginx", "certificado", "disco", "ram",
    "cdn_ultimo_hit", "backup", "licenca",
}
ESTADOS_VALIDOS = {"ok", "degradado", "erro", "ausente"}


def test_profunda_200_estrutura_e_geral_ok(cliente):
    r = cliente.get("/saude/profunda")
    j = r.json()
    assert set(j) == {"estado", "componentes", "tempo_ms", "em"}, j
    assert set(j["componentes"]) == COMPONENTES_ESPERADOS, j["componentes"]
    for nome, c in j["componentes"].items():
        assert c["estado"] in ESTADOS_VALIDOS, (nome, c)
        assert isinstance(c["tempo_ms"], int | float) and c["tempo_ms"] >= 0
    assert j["estado"] in ESTADOS_VALIDOS
    assert r.headers["Cache-Control"] == "no-store"
    assert r.status_code == (200 if j["estado"] == "ok" else 503)
    # banco está de pé nesta base de trilha (D22: nunca derrubado de verdade em teste)
    assert j["componentes"]["banco"]["estado"] == "ok", j["componentes"]["banco"]


def test_profunda_head(cliente):
    r = cliente.head("/saude/profunda")
    assert r.status_code in (200, 503)


def test_profunda_fila_real_sem_worker_e_degradada(sessao_plat):
    """Esta trilha não sobe plat-worker (ADR 0003; laco/trilha_ambiente.sh não inclui a unidade) — workers_vivos
    é ZERO de verdade, não simulado. `fila` tem de refletir isso como degradado, nunca como ok.
    Detalhe por componente (workers_vivos) só existe na versão admin — anônimo é resumido de propósito
    (cláusula 2 do portão), por isso esta cláusula 1 é medida com sessão de superadmin."""
    r = sessao_plat.get("/saude/profunda")
    fila = r.json()["componentes"]["fila"]
    assert fila["workers_vivos"] == 0, fila
    assert fila["estado"] == "degradado", fila


def test_profunda_disco_e_ram_batem_com_a_maquina_real(sessao_plat):
    """disco e ram não são simulados: leem o estado real da máquina (os.statvfs/proc/meminfo). Aqui só se
    confere que a rota não inventa um número diferente do que a própria máquina mostra AGORA. Volumes por
    disco só aparecem na versão admin — por isso sessão de superadmin, não a anônima."""
    import os

    r = sessao_plat.get("/saude/profunda")
    disco = r.json()["componentes"]["disco"]
    st = os.statvfs("/")
    livre_pct_agora = 100.0 * st.f_bavail / st.f_blocks
    livre_pct_resposta = disco["volumes"]["/"]["livre_pct"]
    assert abs(livre_pct_agora - livre_pct_resposta) < 1.0, (livre_pct_agora, disco)
    esperado = "erro" if livre_pct_agora < 3.0 else ("degradado" if livre_pct_agora < 10.0 else "ok")
    assert disco["volumes"]["/"]["estado"] == esperado, disco


# ---------------------------------------------------------------- cláusula 2: anônimo nunca vaza host/porta/versão


def test_profunda_anonimo_e_resumido_sem_alvo(cliente):
    r = cliente.get("/saude/profunda")
    j = r.json()
    for nome, c in j["componentes"].items():
        assert set(c) == {"estado", "tempo_ms"}, (nome, c, "resposta anônima tem de trazer só estado+tempo")
    _varrer_sem_segredo_nem_topologia(json.dumps(j))


def test_profunda_admin_ve_mais_mas_nunca_segredo(cliente, sessao_plat):
    r = sessao_plat.get("/saude/profunda")
    assert r.status_code in (200, 503)
    j = r.json()
    algum_componente_mais_rico = any(set(c) - {"estado", "tempo_ms"} for c in j["componentes"].values())
    assert algum_componente_mais_rico, j["componentes"]
    _varrer_sem_segredo_nem_topologia(json.dumps(j))


def _varrer_sem_segredo_nem_topologia(texto: str) -> None:
    """Varredura de texto (exigência da retomada): a rota nunca pode vazar DSN, token ou nome de inquilino."""
    from app.settings import settings

    assert "postgresql://" not in texto, "DSN vazou no corpo"
    assert settings.PLAT_SECRET not in texto
    if settings.PLAT_GARAGE_ADMIN_TOKEN:
        assert settings.PLAT_GARAGE_ADMIN_TOKEN not in texto, "token do Garage vazou no corpo"
    for chave in ("PLAT_DSN", "PLAT_DSN_WORKER"):
        dsn = getattr(settings, chave, None)
        if dsn and "://" in dsn and "@" in dsn:
            credencial = dsn.split("://", 1)[1].split("@", 1)[0]  # usuario:senha
            assert credencial not in texto, f"{chave}: credencial vazou"
    assert settings.PLAT_SCHEMA not in texto, "nome do schema/inquilino técnico vazou"


# ---------------------------------------------------------------- cláusula 1 + 3: sonda pendurada não trava o endpoint


class _ServidorPendurado:
    """Escuta de verdade em 127.0.0.1, aceita a conexão TCP e nunca escreve nada — reproduz o sintoma exato de
    um serviço pendurado (SIGSTOP/iptables DROP: handshake completo, resposta nunca chega) sem tocar nenhum
    processo real da máquina compartilhada."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.porta = self.sock.getsockname()[1]
        self._parar = False
        self._thread = threading.Thread(target=self._aceitar, daemon=True)
        self._thread.start()

    def _aceitar(self):
        self.sock.settimeout(0.5)
        conexoes = []
        while not self._parar:
            try:
                con, _ = self.sock.accept()
                conexoes.append(con)  # aceita e segura; nunca lê nem escreve
            except TimeoutError:
                continue
            except OSError:
                break
        for c in conexoes:
            try:
                c.close()
            except OSError:
                pass

    def url(self) -> str:
        return f"http://127.0.0.1:{self.porta}"

    def parar(self):
        self._parar = True
        self._thread.join(timeout=2)
        self.sock.close()


@pytest.fixture
def servidor_pendurado():
    s = _ServidorPendurado()
    yield s
    s.parar()


def test_profunda_servico_pendurado_vira_erro_em_ate_10s_sem_travar(cliente, servidor_pendurado, monkeypatch):
    """Aponta martin (sonda mais simples, sem lógica extra) para o servidor pendurado: TCP aceita, HTTP nunca
    responde. A sonda tem TEMPO_LIMITE_SONDA_S=2s embutido; o endpoint inteiro tem de responder bem abaixo do
    limite de 10s do portão, e o componente tem de virar `erro`."""
    from app.settings import settings

    original = settings.PLAT_MARTIN_URL
    object.__setattr__(settings, "PLAT_MARTIN_URL", servidor_pendurado.url())
    try:
        inicio = time.perf_counter()
        r = cliente.get("/saude/profunda")
        duracao_s = time.perf_counter() - inicio
        assert duracao_s <= 10.0, f"endpoint travou {duracao_s:.1f}s com martin pendurado"
        j = r.json()
        assert j["componentes"]["martin"]["estado"] == "erro", j["componentes"]["martin"]
        assert j["estado"] in ("degradado", "erro"), j["estado"]
        assert r.status_code == 503
    finally:
        object.__setattr__(settings, "PLAT_MARTIN_URL", original)


def test_profunda_garage_pendurado_tambem_vira_erro_sem_travar(cliente, servidor_pendurado, monkeypatch):
    """Mesma técnica para o componente garage (S3 + admin API), que tem lógica própria (`_garage`)."""
    from app.settings import settings

    orig_url = settings.PLAT_GARAGE_URL
    orig_admin = settings.PLAT_GARAGE_ADMIN_URL
    object.__setattr__(settings, "PLAT_GARAGE_URL", servidor_pendurado.url())
    object.__setattr__(settings, "PLAT_GARAGE_ADMIN_URL", servidor_pendurado.url())
    try:
        inicio = time.perf_counter()
        r = cliente.get("/saude/profunda")
        duracao_s = time.perf_counter() - inicio
        assert duracao_s <= 10.0, f"endpoint travou {duracao_s:.1f}s com garage pendurado"
        j = r.json()
        assert j["componentes"]["garage"]["estado"] == "erro", j["componentes"]["garage"]
        assert r.status_code == 503
    finally:
        object.__setattr__(settings, "PLAT_GARAGE_URL", orig_url)
        object.__setattr__(settings, "PLAT_GARAGE_ADMIN_URL", orig_admin)
