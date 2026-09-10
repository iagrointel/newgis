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
    # --- trilha de auditoria (L7-20)
    "/admin/auditoria": "admin/auditoria.html",
    # --- configurações da organização (L0-07-a-configuracoes-org)
    "/admin/organizacao": "admin/organizacao.html",
    # --- retrato operacional (L0-06-e-status): aberta, sem sessão, noindex
    "/status": "status.html",
    # --- categorias do inquilino (UX-12-categorias-sem-controle): PUT /api/categorias e POST /api/categorias/importar
    "/admin/categorias": "admin/categorias.html",
    # item UX-18-plataforma-sem-tela: console do superadmin (inquilinos)
    "/admin/inquilinos": "admin/inquilinos.html",
    # --- catálogo (L0-03)
    # --- catálogo (L0-03); /c/{token} é servida por app/catalogo/rotas_compartilhamento.py (leva og:)
    "/conteudo": "conteudo.html",
    "/conteudo/lixeira": "conteudo_lixeira.html",
    "/conteudo/{id}": "conteudo_item.html",
    # --- mapa (L2-01-a)
    "/mapa": "mapa.html",
    # --- casca do SIG (L2-01-a-casca-sig, 10/09/2026): mapa em tela cheia, painéis flutuantes. `/mapa`
    # continua existindo até a casca nova estar aprovada (decisão do orientador depois das capturas).
    "/sig": "sig.html",
    # --- publicação de documento do construtor (L5-06): o mesmo motor usado pelo construtor
    "/aplicativo": "aplicativo.html",
    # --- documento de painel (L2-06-a-modelo-painel-fontes)
    "/paineis/{id}": "painel.html",
    # --- motor de render no servidor (L2-12-a): página headless, sem chrome, sem sessão — o servidor injeta
    # o que precisa ANTES de navegar aqui (app/render/motor.py)
    "/render/mapa": "render_mapa.html",
    # --- símbolos, sprites e glifos (L2-02-e): galeria de ícones + upload + colocar no mapa
    "/simbolos": "simbolos.html",
    # --- ferramentas de análise (L2-05-a): formulário gerado do manifesto
    "/analise": "analise.html",
    # --- cena 3D (L2-09-b-cena-extrusao-slides): ?item=<id de item cena>
    "/cena": "cena.html",
    # --- conexões externas (L6-02-a/L6-02-l/L6-05)
    "/conexoes": "conexoes.html",
    # --- chamados de suporte (L7-13-a): cliente em /chamados, operador (superadmin) em /admin/chamados
    "/chamados": "chamados.html",
    "/admin/chamados": "admin/chamados.html",
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
    # --- fronteira de Pareto do motor multicritério (L3-08-pareto): ?execucao=<id>
    "/amc/pareto": "amc_pareto.html",
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
    # --- editor de tema do inquilino (L5-10-temas-marca)
    "/temas": "temas.html",
    # --- leitora de coleção (L5-04-c-temas-capa-colecao): ?item=<id de item colecao>
    "/colecao": "colecao.html",
    # --- revisão da geocodificação de tabela (L2-11-a-geocodificacao-csv)
    "/geocodificacoes/{geocodificacao_id}": "geocodificacao.html",
    # --- vídeos por tarefa (L7-04-d): arquivos em /videos/arquivo/... (app/rotas_videos.py)
    "/videos": "videos.html",
    # --- geocodificação de tabela (L2-11-a-geocodificacao-csv): revisão manual dos pendentes
    "/geocodificar/{item_id}": "geocodificar_revisao.html",
    # --- migração de Portal/AGOL (L2-08-a-leitor-portal-inventario)
    "/migracao": "migracao.html",
    # --- sistema de referência (L2-17-crs-transformacoes): lista curada + reprojeção de coordenada/bbox
    "/crs": "crs.html",
    # --- visualizador em tempo de execução (L5-15-vista-movel-responsivo): ?item=<id>, ou ?preview=1 dentro
    # do iframe de mesma origem que o construtor monta (web/js/editor/pre_visualizacao.js)
    "/visualizar": "visualizar.html",
    # --- executor de páginas e layout (L5-01-a-layout-paginas): ?item=<id>&pagina=<caminho>
    "/executar": "executar.html",
    # --- acervo da casa (L6-01-c-tela-acervo): equivalente do Living Atlas, sobre plat.acervo_ficha
    "/acervo": "acervo.html",
    # --- conexões externas (L6-02-a/L6-02-l/L6-05)
    "/conexoes": "conexoes.html",
    # item UX-14-geocodificador-sem-tela: tela de trabalho do geocodificador (POST /api/geocodificar e /api/reverso)
    "/geocodificar": "geocodificar.html",
    # --- SMTP, convite de membro e redefinição de senha (L0-07-d-smtp-convites): públicas, sem sessão
    "/aceitar-convite": "aceitar_convite.html",
    "/redefinir-senha": "redefinir_senha.html",
    # --- upload retomável (L0-04-a-upload-arquivo)
    "/uploads": "uploads.html",
    # --- identidade visual (L0-14): página viva do sistema de design, gerada dos tokens em web/estilo/tokens.css
    "/estilo": "estilo.html",
    # item UX-16-ingestao-sem-tela: importações (arquivo enviado -> camada vetorial)
    "/importacoes": "importacoes.html",
    # --- sistema de design (UX-01-sistema-de-design): guia viva de tokens e componentes
    "/estilo-guia": "estilo_guia.html",
    # --- construtor por arrasto (L5-08-editor-arrasto): ?item=<id de item app/painel>
    "/construtor": "construtor.html",
    # --- ramos de versão e diff de reconciliação (L2-13-a): ?camada=<id>
    "/versoes": "versoes.html",
    # --- executor de páginas e layout (L5-01-a-layout-paginas): ?item=<id>&pagina=<caminho>
    "/executar": "executar.html",
    # --- provedores de login e regras de provisionamento (L0-08-e-mapeamento-provisionamento)
    "/admin/logins": "admin/logins.html",
    # --- formulário de coleta (L2-07-b-formulario-de-coleta-xlsform)
    "/coleta": "coleta.html",
}
router = APIRouter()


def servir(arquivo: str) -> FileResponse:
    caminho = WEB / arquivo
    if not caminho.is_file():
        raise ErroAPI(404, "pagina_inexistente", "página inexistente")
    # X-Robots-Tag além da meta noindex que toda página já traz (L0-06-e-status): a meta só é lida por quem
    # interpreta o HTML; o cabeçalho vale para qualquer rastreador, inclusive em resposta não renderizada.
    return FileResponse(caminho, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})


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
