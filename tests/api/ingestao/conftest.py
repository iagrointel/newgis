"""Fixtures da ingestão vetorial (item L0-04-ingest-vetor): sobe um arquivo pela API (POST /api/arquivos, L0-11),
registra o item `arquivo` (POST /api/itens, L0-03), cria a importação (POST /api/importacoes) e espera os jobs;
camadas criadas são apagadas no fim (lixeira + expurgo físico apaga a tabela via o destruidor de
`camada_vetorial`, que já sabe achar `plat.camada_apagar`/DROP TABLE)."""

from __future__ import annotations

import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

from app.catalogo import destruidores
from tests.api.conftest import PREFIXO_TESTE, novo_cliente
from tests.api.test_rls import contexto, ids_por_slug

GERADOS = Path(__file__).resolve().parents[2] / "dados" / "gerados"


@pytest.fixture(scope="session", autouse=True)
def _dados_gerados():
    """Gera tests/dados/gerados/ uma vez por sessão (item L0-04: dado aberto real, sem baixar nada novo —
    ver tests/dados/gerar.py). Reaproveita se outra trilha/rodada já gerou (o gerador é idempotente)."""
    marcador = GERADOS / "cobertura.gpkg"
    if not marcador.exists():
        import subprocess
        import sys

        raiz = Path(__file__).resolve().parents[2].parent
        subprocess.run([sys.executable, str(raiz / "tests" / "dados" / "gerar.py")], check=True, cwd=raiz)
    return GERADOS


def esperar_job(sessao, job_id: str, timeout: float = 60) -> dict:
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = sessao.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
            return ultimo
        time.sleep(0.2)
    pytest.fail(f"job {job_id} não terminou em {timeout} s: {ultimo}")


def esperar_importacao(sessao, importacao_id: str, estados: tuple[str, ...], timeout: float = 60) -> dict:
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = sessao.get(f"/api/importacoes/{importacao_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in estados:
            return ultimo
        time.sleep(0.2)
    pytest.fail(f"importação {importacao_id} não chegou a {estados} em {timeout} s: {ultimo}")


class Ingestor:
    """Fábrica do fluxo completo (upload -> item -> importação); registra os item_id de camada criados para o
    teardown apagar."""

    def __init__(self, sessao):
        self.sessao = sessao
        self.camadas: list[str] = []
        self.arquivos: list[str] = []
        self._tok = None
        self._tok_id = None

    def _token(self) -> str:
        if self._tok is None:
            r = self.sessao.post("/api/tokens",
                                 json={"nome": f"{PREFIXO_TESTE}-ingestao", "escopos": ["admin:inquilino"]})
            assert r.status_code == 201, r.text
            self._tok = r.json()["token"]
            self._tok_id = r.json()["id"]
        return self._tok

    def liberar_token(self) -> None:
        if self._tok_id is not None:
            self.sessao.delete(f"/api/tokens/{self._tok_id}")
            self._tok_id = None

    def enviar_arquivo(self, caminho: Path, classe="camada_arquivo", content_type="application/octet-stream") -> dict:
        sem_cookie = novo_cliente()
        dados = caminho.read_bytes()
        r = sem_cookie.post(f"/api/arquivos?classe={classe}", content=dados,
                            headers={"authorization": f"Bearer {self._token()}", "content-type": content_type})
        assert r.status_code == 201, r.text
        return r.json()

    def item_arquivo(self, obj: dict, nome_original: str) -> str:
        r = self.sessao.post("/api/itens", json={
            "tipo": "arquivo", "titulo": f"{PREFIXO_TESTE} {nome_original}",
            "dados": {"chave": obj["chave"], "sha256": obj["sha256"], "bytes": obj["bytes"],
                      "content_type": obj["content_type"], "nome_original": nome_original},
        })
        assert r.status_code == 201, r.text
        iid = r.json()["id"]
        self.arquivos.append(iid)
        return iid

    def importar(self, nome_arquivo: str, formato: str, classe="camada_arquivo",
                 content_type="application/octet-stream") -> tuple[str, dict]:
        """Sobe `tests/dados/gerados/<nome_arquivo>`, cria a importação, espera a inspeção. Devolve
        (importacao_id, resposta completa da importação após inspecionar)."""
        caminho = GERADOS / nome_arquivo
        obj = self.enviar_arquivo(caminho, classe, content_type)
        item_id = self.item_arquivo(obj, nome_arquivo)
        r = self.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": formato})
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]
        esperar_job(self.sessao, job_id, timeout=60)
        r = self.sessao.get(f"/api/importacoes/{r.json()['importacao_id']}")
        return r.json()["id"], r.json()

    def confirmar(self, importacao_id: str, corpo: dict | None = None, timeout: float = 90) -> dict:
        """Confirma (preenchendo automaticamente `crs`/`codificacao` quando a proposta pede) e espera a carga."""
        r = self.sessao.get(f"/api/importacoes/{importacao_id}")
        proposta = r.json()["proposta"] or {}
        corpo = dict(corpo or {})
        perguntas = proposta.get("perguntas") or []
        if "crs" in perguntas and "crs" not in corpo:
            corpo["crs"] = {"srid": proposta["crs"].get("sugestao") or 4674}
        if "codificacao" in perguntas and "codificacao" not in corpo:
            corpo["codificacao"] = {"valor": "UTF-8"}
        r = self.sessao.put(f"/api/importacoes/{importacao_id}/confirmar", json=corpo)
        if r.status_code != 202:
            return {"confirmar_status": r.status_code, "confirmar_corpo": r.json()}
        job_id = r.json()["job_id"]
        esperar_job(self.sessao, job_id, timeout=timeout)
        r = self.sessao.get(f"/api/importacoes/{importacao_id}")
        final = r.json()
        if final["estado"] == "concluida":
            self.camadas.append(final["item_id"])
        return final


@pytest.fixture
def ingestor_a(sessao_a, env):
    ing = Ingestor(sessao_a)
    yield ing
    ing.liberar_token()
    if not (ing.camadas or ing.arquivos):
        return
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()["usuario_id"]
        contexto(con, ids["demo"], usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
            # plat.importacao.arquivo_id referencia plat.item SEM cascade de propósito (RESTRICT protege um
            # arquivo em inspeção); o teste apaga a própria linha de importacao antes de expurgar os itens
            cur.execute(
                "DELETE FROM plat.importacao WHERE arquivo_id = ANY(%s::uuid[]) OR item_id = ANY(%s::uuid[])",
                (ing.arquivos, ing.camadas),
            )
            for iid in ing.camadas + ing.arquivos:
                # camada_vetorial tem dado FÍSICO (tabela): plat.item_expurgar sozinho só apaga o REGISTRO —
                # o dado físico é apagado pelo destruidor do tipo (mesma chamada que catalogo.lixeira_expurgar
                # faz; pulá-la aqui é exatamente o bug que deixou tabelas órfãs em d_demo nesta suíte).
                cur.execute("SELECT tipo, dados, miniatura_chave FROM plat.item WHERE id = %s::uuid", (iid,))
                item = cur.fetchone()
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (iid,))
                if item is not None:
                    try:
                        destruidores.destruir(cur, item["tipo"], item["dados"], item["miniatura_chave"],
                                              lambda *_a: None)
                    except destruidores.Recusado:
                        pass
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (iid,))
        con.commit()
    finally:
        con.close()
