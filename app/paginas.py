"""Páginas servidas pela API a partir de web/ com Cache-Control: no-store (ADR 0002 seção 15). Cada trilha
acrescenta a sua linha em PAGINAS; main.py só inclui o router. Arquivo ausente = 404 (nunca uma casca)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.erros import ErroAPI

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PAGINAS = {
    # --- identidade (L0-02)
    "/entrar": "login.html",
    "/conta": "conta.html",
    "/admin": "admin/index.html",
    "/admin/acervo": "admin/acervo.html",
    "/admin/usuarios": "admin/usuarios.html",
    "/admin/grupos": "admin/grupos.html",
    "/admin/papeis": "admin/papeis.html",
    "/admin/tokens": "admin/tokens.html",
    "/admin/log": "admin/log.html",
    # --- configurações da organização (L0-07-a-configuracoes-org)
    "/admin/organizacao": "admin/organizacao.html",
    # --- catálogo (L0-03)
    "/conteudo": "conteudo.html",
    "/conteudo/lixeira": "conteudo_lixeira.html",
    "/conteudo/{id}": "conteudo_item.html",
    "/c/{token}": "compartilhado.html",
    # --- mapa (L2-01-a)
    "/mapa": "mapa.html",
    # --- casca do SIG (L2-01-a-casca-sig, 10/09/2026): mapa em tela cheia, painéis flutuantes. `/mapa`
    # continua existindo até a casca nova estar aprovada (decisão do orientador depois das capturas).
    "/sig": "sig.html",
    # --- publicação de documento do construtor (L5-06): o mesmo motor usado pelo construtor
    "/aplicativo": "aplicativo.html",
    # --- documento de painel (L2-06-a-modelo-painel-fontes)
    "/paineis/{id}": "painel.html",
    # --- conexões externas (L6-02-a/L6-02-l/L6-05)
    "/conexoes": "conexoes.html",
    # --- SMTP, convite de membro e redefinição de senha (L0-07-d-smtp-convites): públicas, sem sessão
    "/aceitar-convite": "aceitar_convite.html",
    "/redefinir-senha": "redefinir_senha.html",
    # --- rede simples (L4-18-rede-simples-trace-network)
    "/redes/simples": "redes_simples.html",
    # --- controladores de subrede e tiers (L4-04-a-controladores-e-tiers)
    "/redes/controladores": "redes_controladores.html",
    # --- configurações de traçado (L4-02-e-configuracoes-de-tracado)
    "/redes/configuracoes": "redes_configuracoes.html",
    # --- diagrama de rede (L4-04-d-diagrama-esquematico)
    "/redes/diagrama": "redes_diagrama.html",
    # --- fluxo de potência do alimentador (L4-07-fluxo-de-potencia)
    "/redes/fluxo": "redes_fluxo.html",
    # --- resultado de traçado: seleção, camada, exportação e histórico (L4-02-f-resultados-e-exportacao)
    "/redes/tracado": "redes_tracado.html",
    # --- traçado de isolamento (L4-02-c-isolamento)
    "/redes/isolamento": "redes_isolamento.html",
    # --- domínios e subtipos da camada (L2-10-a): campos x domínio, formulário de feição e tabela
    "/camadas/{id}/dominios": "camada_dominios.html",
    # --- upload retomável (L0-04-a-upload-arquivo)
    "/uploads": "uploads.html",
    # --- sistema de design (UX-01-sistema-de-design): guia viva de tokens e componentes
    "/estilo-guia": "estilo_guia.html",
    # --- construtor por arrasto (L5-08-editor-arrasto): ?item=<id de item app/painel>
    "/construtor": "construtor.html",
    # --- construtor de camada por esquema (L5-31)
    "/construtor-camada": "construtor_camada.html",
    # --- vista de camada (L5-32): filtro, campos ocultos, só leitura
    "/vista-de-camada": "vista_camada.html",
    # --- executor de páginas e layout (L5-01-a-layout-paginas): ?item=<id>&pagina=<caminho>
    "/executar": "executar.html",
    # --- catálogo de ferramentas (UX-09): formulário gerado do esquema de parâmetros de cada tipo de tarefa
    "/ferramentas": "ferramentas.html",
    # --- console do operador da plataforma (UX-18): superadmin
    "/plataforma": "plataforma.html",
    # --- migração de Portal/AGOL (L2-08-a-leitor-portal-inventario)
    "/migracao": "migracao.html",
    # --- análise 3D (L2-09-d): visada, viewshed, perfil e sombra sobre terreno de exemplo ou próprio
    "/analise3d": "analise3d.html",
    # --- console do superadmin (L0-07-f-console-plataforma): fora de qualquer inquilino, só superadmin de `plataforma`
    "/plataforma": "plataforma.html",
    # --- painel Atividade e relatórios do admin (L0-07-e-relatorios)
    "/admin/atividade": "admin/atividade.html",
}
router = APIRouter()


def servir(arquivo: str) -> FileResponse:
    caminho = WEB / arquivo
    if not caminho.is_file():
        raise ErroAPI(404, "pagina_inexistente", "página inexistente")
    return FileResponse(caminho, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


def _registrar(caminho: str, arquivo: str) -> None:
    async def pagina():
        return servir(arquivo)

    pagina.__name__ = "pagina_" + caminho.strip("/").replace("/", "_")
    router.add_api_route(caminho, pagina, methods=["GET", "HEAD"], include_in_schema=False)


for _caminho, _arquivo in PAGINAS.items():
    _registrar(_caminho, _arquivo)


# --- manual gerado (L7-04-a-manual-capturas-geradas): docs/manual/index.html (site estático, noindex).
# Fica fora de web/ por ser artefato de build (make manual), servido com X-Robots-Tag: noindex;
# arquivo ausente = 404 (nunca uma casca), mesma regra de servir().
@router.get("/manual", include_in_schema=False)
async def manual():
    caminho = ROOT / "docs" / "manual" / "index.html"
    if not caminho.is_file():
        raise ErroAPI(404, "pagina_inexistente", "manual não gerado (rode make manual)")
    return FileResponse(
        caminho, media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
    )
