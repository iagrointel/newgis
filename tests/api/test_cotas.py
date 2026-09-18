"""Teto de cota imposto pela plataforma (item L0-07-c-cotas-uso; ADR docs/adr/20260906T2124-cotas-uso.md;
migração de correção 20260907T0145_cotas_teto.sql), nascido direto do adversário de 06/09 contra este item:
o admin do inquilino (PUT /api/org, privilégio org.configurar) tinha só um piso (Field(ge=...)) e nenhum
teto — subia a própria cota_bytes/cota_usuarios sem limite algum. Agora plat.tenant.cota_bytes_teto/
plat.cota_usuarios_teto() são o teto, movido só pelo superadmin (POST /api/plataforma/inquilinos/{id}/cotas
→ plat.tenant_cotas_definir), e PUT /api/org recusa (422 cota_*_acima_do_teto) qualquer valor acima dele.

O outro achado do mesmo adversário — o contador de cota (tenant.uso_bytes) só subia e nunca descia no
expurgo — está em tests/api/catalogo/test_uso_bytes_simetrico.py (precisa das fixtures itens_a/worker_vivo,
que só existem sob tests/api/catalogo/)."""

# ---------------------------------------------------------------- teto imposto pela plataforma
def test_admin_do_inquilino_nao_ultrapassa_o_teto_so_superadmin_move_o_teto(sessao_a, sessao_plat):
    original = sessao_a.get("/api/org").json()
    teto_bytes_original = original["armazenamento"]["cota_bytes_teto"]
    assert teto_bytes_original >= original["armazenamento"]["cota_bytes"]  # invariante cota <= teto, sempre

    def _corpo(org):
        return {
            "nome": org["nome"], "cor": org["cor"], "idioma_padrao": org["idioma_padrao"],
            "resumo": org["resumo"], "contato": org["contato"],
            "contatos_admin": list(org["contatos_admin"]),
            "unidades": org["regional"]["unidades"], "formato_data": org["regional"]["formato_data"],
            "formato_numero_data": org["regional"]["formato_numero_data"],
            "centro": org["mapa"]["centro"], "zoom": org["mapa"]["zoom"], "basemap": org["mapa"]["basemap"],
            "extent": org["mapa"]["extent"],
            "srid_padrao": org["mapa"]["srid_padrao"], "cota_bytes": org["armazenamento"]["cota_bytes"],
            "pagina_inicial": [dict(b) for b in org["pagina_inicial"]],
            "galeria_destaque": org["galeria_destaque"],
            "banner_aviso": org["banner_aviso"], "termo_acesso": org["termo_acesso"],
            "cota_usuarios": org["usuarios"]["cota"], "auth": dict(org["auth"]),
        }

    # 1) superadmin BAIXA o teto para logo acima da cota atual: o admin do inquilino tenta ultrapassar e apanha 422
    novo_teto = original["armazenamento"]["cota_bytes"] + 10 * 1024 * 1024  # 10 MiB de folga só
    tenant_id_demo = _tenant_id_demo(sessao_plat)
    r_teto = sessao_plat.post(f"/api/plataforma/inquilinos/{tenant_id_demo}/cotas", json={"cota_bytes_teto": novo_teto})
    assert r_teto.status_code == 204, r_teto.text
    try:
        org = sessao_a.get("/api/org").json()
        assert org["armazenamento"]["cota_bytes_teto"] == novo_teto  # efeito IMEDIATO, sem cache

        corpo = _corpo(org)
        corpo["cota_bytes"] = novo_teto + 50 * 1024 * 1024  # bem acima do teto que acabou de ser imposto
        r = sessao_a.put("/api/org", json=corpo)
        assert r.status_code == 422 and r.json()["erro"] == "cota_bytes_acima_do_teto", r.text
        assert r.json()["detalhe"]["teto"] == novo_teto

        # dentro do teto continua livre (o admin do inquilino não fica travado, só tem um limite de cima)
        corpo["cota_bytes"] = novo_teto  # exatamente no teto: permitido
        r2 = sessao_a.put("/api/org", json=corpo)
        assert r2.status_code == 200, r2.text
        assert sessao_a.get("/api/org").json()["armazenamento"]["cota_bytes"] == novo_teto
    finally:
        corpo = _corpo(sessao_a.get("/api/org").json())
        corpo["cota_bytes"] = original["armazenamento"]["cota_bytes"]
        # restaura a cota ANTES do teto (senão o PUT recusaria a própria restauração se a cota antiga
        # já estivesse abaixo do teto novo — não é o caso aqui, mas a ordem certa é sempre cota depois teto)
        assert sessao_a.put("/api/org", json=corpo).status_code == 200
        r_restaura = sessao_plat.post(
            f"/api/plataforma/inquilinos/{tenant_id_demo}/cotas", json={"cota_bytes_teto": teto_bytes_original}
        )
        assert r_restaura.status_code == 204, r_restaura.text
        assert sessao_a.get("/api/org").json()["armazenamento"]["cota_bytes_teto"] == teto_bytes_original


def test_superadmin_nao_abaixa_teto_abaixo_da_cota_usuarios_vigente_e_efeito_e_imediato(sessao_a, sessao_plat):
    original = sessao_a.get("/api/org").json()
    tenant_id_demo = _tenant_id_demo(sessao_plat)
    teto_usuarios_original = original["usuarios"]["teto"]
    try:
        # teto abaixo da cota_usuarios vigente: a função recusa (invariante cota <= teto nunca fica quebrado)
        cota_usuarios_atual = original["usuarios"]["cota"]
        r_ruim = sessao_plat.post(
            f"/api/plataforma/inquilinos/{tenant_id_demo}/cotas",
            json={"cota_usuarios_teto": max(1, cota_usuarios_atual - 1)},
        )
        assert r_ruim.status_code == 422 and r_ruim.json()["erro"] == "cota_usuarios_acima_do_teto", r_ruim.text
        assert sessao_a.get("/api/org").json()["usuarios"]["teto"] == teto_usuarios_original  # nada mudou

        # teto novo, folgado: aceito e refletido de imediato (sem novo login, sem reinício de processo)
        novo_teto = cota_usuarios_atual + 5
        r_ok = sessao_plat.post(
            f"/api/plataforma/inquilinos/{tenant_id_demo}/cotas", json={"cota_usuarios_teto": novo_teto}
        )
        assert r_ok.status_code == 204, r_ok.text
        assert sessao_a.get("/api/org").json()["usuarios"]["teto"] == novo_teto
    finally:
        assert sessao_plat.post(
            f"/api/plataforma/inquilinos/{tenant_id_demo}/cotas",
            json={"cota_usuarios_teto": teto_usuarios_original},
        ).status_code == 204


def test_nao_superadmin_nao_chama_a_rota_de_teto(sessao_a):
    r = sessao_a.post("/api/plataforma/inquilinos/1/cotas", json={"cota_bytes_teto": 1_000_000_000})
    assert r.status_code == 404  # console do superadmin: 404 para quem não é (a rota não se confirma)


def _tenant_id_demo(sessao_plat) -> int:
    r = sessao_plat.get("/api/plataforma/inquilinos")
    assert r.status_code == 200, r.text
    linha = next(x for x in r.json() if x["slug"] == "demo")
    return linha["id"]


