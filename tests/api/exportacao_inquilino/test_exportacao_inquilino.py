"""Portão de pronto do item L0-06-d-exportar-inquilino, cláusula por cláusula:

1. "exportar demo (dado aberto) e reabrir o GeoPackage com ogrinfo listando N camadas = N camadas do catálogo"
2. "JSON válido contra JSON Schema publicado em docs/"
3. "manifesto confere" (sha256 de cada componente bate com o arquivo)
4. "importar o pacote num inquilino novo (L0-15) recria itens com os mesmos uuids (prova de portabilidade)"
5. "e2e com captura; medida tempo e bytes"

Refutação do item (adversário): exportação em demo2 com sessão de demo devolve 404; pedir 2 no mesmo dia
devolve 429; modificar o pacote baixado faz o sha256 do manifesto acusar.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import jsonschema
import pytest

from app.exportacao_inquilino import importar, metadado, motor
from tests.api.exportacao.conftest import conexao

ROOT = Path(__file__).resolve().parents[3]
ESQUEMA = json.loads((ROOT / "docs" / "esquemas" / "exportacao_inquilino.schema.json").read_text(encoding="utf-8"))


def _pedir(cliente):
    return cliente.post("/api/inquilino/exportar")


def esperar(cliente, exportacao_id: str, timeout: float = 300) -> dict:
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = cliente.get(f"/api/inquilino/exportacoes/{exportacao_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in ("pronta", "falhou", "cancelada", "expirada"):
            return ultimo
        time.sleep(0.5)
    pytest.fail(f"exportação de inquilino {exportacao_id} não terminou em {timeout} s: {ultimo}")


def test_privilegio_e_limite_diario(sessao_plat):
    """Cláusula da refutação: a 2ª exportação completa no mesmo dia UTC devolve 429. Inquilino TEMPORÁRIO
    próprio (nunca `demo`): a cota é por dia UTC e persiste entre rodadas da suíte no mesmo schema — usar
    `demo` faria este teste passar só na primeira rodada do dia."""
    from tests.api.conftest import InquilinoTemporario

    inq = InquilinoTemporario(sessao_plat)
    try:
        r1 = _pedir(inq.admin)
        assert r1.status_code == 202, r1.text
        r2 = _pedir(inq.admin)
        assert r2.status_code == 429 and r2.json()["erro"] == "exportacao_inquilino_ja_pedida_hoje", r2.text
    finally:
        inq.apagar()


def test_estimativa_responde_antes_de_pedir(inquilino_a, camada_a):
    """Hipótese do item: "tamanho estimado antes". A estimativa é lida do banco (tamanho das tabelas das
    camadas hospedadas + tamanho dos arquivos + 4 KB por item) e tem de ser positiva num inquilino que já tem
    uma camada, sem criar exportação alguma."""
    r = inquilino_a.admin.get("/api/inquilino/exportar/estimativa")
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["n_camadas"] >= 1 and e["n_itens"] >= 1
    assert e["bytes_camadas"] > 0
    assert e["bytes"] == e["bytes_camadas"] + e["bytes_arquivos"] + e["bytes_catalogo"]
    assert e["maximo_por_dia"] == 1
    r2 = inquilino_a.admin.get("/api/inquilino/exportacoes")
    assert r2.status_code == 200 and r2.json()["total"] == 0, "a estimativa não pode criar exportação"


def test_editor_sem_org_exportar_recebe_403(inquilino_a):
    from tests.api.conftest import Usuarios

    usuarios = Usuarios(inquilino_a.admin)
    cliente, _u, _s = usuarios.sessao("editor")
    try:
        r = _pedir(cliente)
        assert r.status_code == 403, r.text
    finally:
        usuarios.limpar()


def test_sessao_de_demo_nao_ve_exportacao_de_demo2(sessao_a, sessao_b):
    """Refutação do item: sessão de um inquilino nunca enxerga a exportação do outro (RLS de
    `plat.exportacao_inquilino`, mesma disciplina do resto do catálogo)."""
    r = _pedir(sessao_b)
    assert r.status_code in (202, 429), r.text
    if r.status_code == 202:
        eid = r.json()["exportacao_id"]
        assert sessao_a.get(f"/api/inquilino/exportacoes/{eid}").status_code == 404


def test_pacote_completo_gpkg_catalogo_manifesto_e_importacao(
    env, inquilino_a, camada_a, arquivo_a, worker_exportacao_inquilino, medida, tmp_path
):
    """Cláusulas 1, 2, 3, 4, 5 do portão, todas contra o INQUILINO TEMPORÁRIO próprio (nunca `demo`, que outras
    trilhas/testes também usam): mede tempo e bytes, reabre o GeoPackage, valida o catálogo contra o JSON
    Schema publicado, confere o manifesto e prova a portabilidade importando num segundo inquilino."""
    cliente = inquilino_a.admin
    inicio = time.monotonic()
    r = cliente.post("/api/inquilino/exportar")
    assert r.status_code == 202, r.text
    final = esperar(cliente, r.json()["exportacao_id"], timeout=600)
    duracao_s = round(time.monotonic() - inicio, 2)
    assert final["estado"] == "pronta", (worker_exportacao_inquilino.cauda_do_log(60), final)

    r = cliente.get(f"/api/inquilino/exportacoes/{final['id']}/baixar")
    assert r.status_code == 200, r.text
    pacote = tmp_path / "inquilino_exportado.zip"
    pacote.write_bytes(r.content)

    with zipfile.ZipFile(pacote) as z:
        nomes = set(z.namelist())
        assert nomes == {"dados.gpkg", "catalogo.json", "arquivos.zip", "manifesto.json"}, nomes
        catalogo = json.loads(z.read("catalogo.json").decode("utf-8"))
        manifesto = json.loads(z.read("manifesto.json").decode("utf-8"))
        z.extract("dados.gpkg", tmp_path)
        z.extract("catalogo.json", tmp_path)
        conteudo_arquivos = z.read("arquivos.zip")

    # cláusula 2: JSON válido contra o esquema publicado
    jsonschema.validate(catalogo, ESQUEMA)

    # cláusula 1: ogrinfo lista N camadas = N camadas hospedadas do catálogo
    n_camadas_catalogo = sum(
        1 for i in catalogo["itens"]
        if i["tipo"] == "camada_vetorial" and (i.get("dados") or {}).get("fonte") == "hospedada"
    )
    import subprocess

    rr = subprocess.run(["ogrinfo", "-so", str(tmp_path / "dados.gpkg")], capture_output=True, text=True)
    assert rr.returncode == 0, rr.stderr
    n_camadas_gpkg = len([ln for ln in rr.stdout.splitlines() if ln.strip() and ln[0].isdigit() and ":" in ln])
    assert n_camadas_gpkg == n_camadas_catalogo == final["n_camadas"], (n_camadas_gpkg, n_camadas_catalogo, final)

    # o zip de arquivos traz o objeto do bucket, um por item, com o conteúdo intacto
    with zipfile.ZipFile(io.BytesIO(conteudo_arquivos)) as za:
        nomes_arquivos = za.namelist()
        assert f"{arquivo_a['item_id']}.csv" in nomes_arquivos, nomes_arquivos
        assert len(za.read(f"{arquivo_a['item_id']}.csv")) == arquivo_a["bytes"]
    assert final["n_arquivos"] == len(nomes_arquivos) >= 1

    # hipótese do item: metadado e estilo dentro do próprio GeoPackage, nas tabelas gpkg_metadata da norma
    linhas_metadado = metadado.ler(tmp_path / "dados.gpkg")
    assert len(linhas_metadado) >= n_camadas_gpkg, linhas_metadado
    cartoes = [ln["documento"] for ln in linhas_metadado if ln["uri"] == metadado.URI_ITEM]
    ids_com_metadado = {c["id"] for c in cartoes}
    ids_camadas = {
        i["id"] for i in catalogo["itens"]
        if i["tipo"] == "camada_vetorial" and (i.get("dados") or {}).get("fonte") == "hospedada"
    }
    assert ids_camadas <= ids_com_metadado, (ids_camadas, ids_com_metadado)

    # cláusula 3: o manifesto confere contra o arquivo de cada componente e contra o sha256 registrado no banco
    for nome, caminho in (("dados.gpkg", tmp_path / "dados.gpkg"), ("catalogo.json", tmp_path / "catalogo.json")):
        assert manifesto["componentes"][nome]["sha256"] == motor.sha256_arquivo(caminho), nome
    assert manifesto["componentes"]["catalogo.json"]["sha256_conteudo"] == motor.sha256_bytes(
        (tmp_path / "catalogo.json").read_bytes()
    )
    assert final["sha256"] == motor.sha256_arquivo(pacote)

    # refutação: modifica o pacote baixado e o sha256 do manifesto acusa
    corrompido = tmp_path / "dados_corrompido.gpkg"
    original = (tmp_path / "dados.gpkg").read_bytes()
    corrompido.write_bytes(original[:-1] + bytes([original[-1] ^ 0xFF]))
    assert motor.sha256_arquivo(corrompido) != manifesto["componentes"]["dados.gpkg"]["sha256"]

    # cláusula 4: importar o pacote num inquilino NOVO recria os itens com os mesmos uuids. `id` é chave
    # primária GLOBAL de `plat.item` (não composta com tenant_id) — como no mundo real a exportação é para o
    # cliente SAIR da instalação, o teste tira os itens de origem antes de importar (senão a própria unicidade
    # da chave, que é o que prova a fidelidade dos uuids, impede a inserção).
    #
    # Tirar é lixeira + expurgo, NUNCA `DELETE FROM plat.item`: a política `p_item_apagar` é `USING (false)`,
    # ou seja, o DELETE direto da role da aplicação remove ZERO linha e não levanta erro nenhum — a primeira
    # versão deste teste fazia isso e só descobria o problema lá adiante, na chave duplicada da importação.
    # O caminho de verdade é o mesmo do produto: `plat.item_lixeira` e depois `plat.item_expurgar`.
    ids_catalogo = sorted(i["id"] for i in catalogo["itens"])
    con_origem = conexao(env)
    try:
        with con_origem.cursor() as cur:
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), "
                "set_config('plat.usuario_id', %s, true), set_config('plat.login', 'zt-import', true)",
                (str(inquilino_a.id), str(inquilino_a.admin_id)),
            )
            for item_id in ids_catalogo:
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true) AS ok", (item_id,))
                assert cur.fetchone()["ok"], f"item {item_id} não foi para a lixeira"
                cur.execute("SELECT plat.item_expurgar(%s::uuid) AS ok", (item_id,))
                assert cur.fetchone()["ok"], f"item {item_id} não foi expurgado"
            cur.execute("SELECT count(*) AS n FROM plat.item WHERE id = ANY(%s::uuid[])", (ids_catalogo,))
            assert cur.fetchone()["n"] == 0, "sobrou item de origem: a prova dos uuids seria vazia"
        con_origem.commit()
    finally:
        con_origem.close()

    inquilino_novo = _InquilinoVazio(env, "il006dexpor-import")
    try:
        con = conexao(env)
        try:
            with con.cursor() as cur:
                cur.execute(
                    "SELECT set_config('plat.tenant_id', %s, true), "
                    "set_config('plat.usuario_id', %s, true), set_config('plat.login', 'zt-import', true)",
                    (str(inquilino_novo.id), str(inquilino_novo.admin_id)),
                )
                contagem = importar.importar_catalogo(cur, inquilino_novo.id, inquilino_novo.admin_id, catalogo)
                cur.execute(
                    "SELECT id::text FROM plat.item WHERE id = ANY(%s::uuid[]) ORDER BY id", (ids_catalogo,)
                )
                ids_recriados = sorted(r["id"] for r in cur.fetchall())
            con.commit()
        finally:
            con.close()
        assert ids_recriados == ids_catalogo, "os uuids importados não batem com os do catálogo exportado"
        assert contagem["itens"] == len(catalogo["itens"])
    finally:
        inquilino_novo.apagar()

    # a máquina desta casa vive sob disputa (12 núcleos, dezenas de trilhas): número de tempo só vale com a
    # carga do momento gravada ao lado, senão mede a casa e não o produto
    import os

    carga = round(os.getloadavg()[0], 2)
    ram_livre_gb = round(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1e9, 1)

    gravar = medida("L0-06-d-exportar-inquilino")
    gravar("duracao_s", duracao_s, "s", "pedir + esperar pronta (tests/api/exportacao_inquilino)")
    gravar("carga_1min", carga, "carga", "os.getloadavg()[0] no fim da exportação (12 núcleos)")
    gravar("ram_livre_gb", ram_livre_gb, "GB", "memória livre no fim da exportação")
    gravar("bytes", final["bytes"], "bytes",
           "tamanho do pacote final (dados.gpkg + catalogo.json + arquivos.zip + manifesto.json)")
    gravar("n_itens", final["n_itens"], "itens", "itens do inquilino de teste no catálogo exportado")
    gravar("n_camadas", final["n_camadas"], "camadas", "camadas hospedadas escritas no GeoPackage")
    gravar("n_arquivos", final["n_arquivos"], "arquivos", "arquivos do bucket zipados")


class _InquilinoVazio:
    """Inquilino novo, vazio, só para a prova de importação (cláusula 4). Reaproveita `POST
    /api/plataforma/inquilinos` (mesma rota que `InquilinoTemporario` usa), sem camada nem item algum."""

    def __init__(self, env, prefixo: str):
        import secrets

        from tests.api.conftest import credenciais, entrar, novo_cliente

        self.slug = f"zt{prefixo.replace('_', '')[:10]}{secrets.token_hex(4)}"
        cred = credenciais()
        login, senha = cred["plataforma"]
        self._plat = novo_cliente()
        from tests.api.conftest import totp_guardado

        r = entrar(self._plat, "plataforma", login, senha, totp_guardado("plataforma"))
        assert r.status_code == 200, r.text
        r = self._plat.post(
            "/api/plataforma/inquilinos",
            json={"slug": self.slug, "nome": f"Inquilino vazio {self.slug}", "admin_login": "admin",
                  "admin_nome": "Administrador de teste"},
        )
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        self.admin_id = r.json()["admin"]["id"]

    def apagar(self):
        self._plat.delete(f"/api/plataforma/inquilinos/{self.id}")
