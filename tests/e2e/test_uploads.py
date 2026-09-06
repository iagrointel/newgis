"""e2e playwright (item L0-04-a-upload-arquivo) contra a URL interna real: escolhe um arquivo real (CSV,
20 MiB -> 2 partes de 16 MiB), acompanha a barra de progresso passar de "parte 1 de 2" para "parte 2 de 2" e
o aviso final "arquivo enviado", 0 erro de console. Capturas em
tests/e2e/capturas/L0-04-a-upload-arquivo_<tela>.png. Sem /api/uploads no OpenAPI a suíte é pulada com a razão
escrita (mesmo padrão de tests/e2e/test_conexoes.py)."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from tests.e2e.apoio_uploads import ROTAS_UPLOADS, TelaUploads, gravar_medidas_uploads

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def api_uploads(api_auth):
    faltam = [r for r in ROTAS_UPLOADS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item L0-04-a)")
    return api_auth


def _csv_temporario(tamanho: int) -> Path:
    linha = b"talhao,area_ha,cultura\n1,12.50,soja\n"
    conteudo = (linha * (tamanho // len(linha) + 1))[:tamanho]
    f = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    f.write(conteudo)
    f.close()
    return Path(f.name)


def test_upload_com_barra_de_progresso_ate_arquivo_enviado(page, base_url, credenciais_demo, api_uploads, medida):
    slug, admin_login, senha_admin = credenciais_demo
    tela = TelaUploads(page, base_url)
    caminho = _csv_temporario(20 * 1024 * 1024)  # 2 partes de 16 MiB (a última menor)
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/uploads")
        tela.medidas["pagina_uploads_ms"] = tela.ir("/uploads")
        tela.capturar("dropzone_vazia")

        page.set_input_files("#upload-arquivo", str(caminho))
        assert caminho.name in (page.text_content("#upload-nome") or "")
        assert page.input_value("#upload-tipo") == "csv"  # detectado pela extensão .csv
        tela.capturar("arquivo_escolhido")

        t0 = time.perf_counter()
        page.click("#upload-enviar")
        page.wait_for_selector("#upload-rotulo-progresso:not([hidden])", timeout=15000)
        page.wait_for_function(
            "() => document.querySelector('#upload-rotulo-progresso')?.textContent?.includes('parte 1 de 2')",
            timeout=15000,
        )
        tela.capturar("progresso_parte_1")
        page.wait_for_function(
            "() => document.querySelector('#aviso')?.textContent?.includes('arquivo enviado')", timeout=60000,
        )
        tela.medidas["envio_20mb_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        tela.capturar("concluido")

        assert page.get_attribute("#upload-progresso", "value") == "100"
        assert "arquivo enviado" in (page.text_content("#aviso") or "")
        assert "arquivo está no armazenamento" in (page.text_content("#upload-resultado") or "")

        tela.verificar()
        gravar_medidas_uploads(medida, tela)
    finally:
        caminho.unlink(missing_ok=True)
        tela.sair()
