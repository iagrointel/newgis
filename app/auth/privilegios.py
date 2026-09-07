"""Vocabulário de privilégios (ADR 0002 seção 3.2), espelho em Python do que a migração 003 semeia em
plat.privilegio/plat.perfil_privilegio. `tests/api/test_privilegios_declarados.py` prova que os dois coincidem;
o banco é a verdade em tempo de execução (privilegios_de/tem), esta lista serve a testes, documentação e ao
cálculo de `perfil_minimo` sem consulta."""

PERFIS = ("visualizador", "campo", "editor", "admin")
ORDEM_PERFIL = {p: i for i, p in enumerate(PERFIS)}
# (nome, grupo, descrição, administrativo, perfis que o têm por padrão)
V, C, E, A = "visualizador", "campo", "editor", "admin"
QUATRO_PERFIS = (V, C, E, A)
PRIVILEGIOS: tuple[tuple[str, str, str, bool, tuple[str, ...]], ...] = (
    ("membros.ver", "membros", "ver nome, login, perfil e último acesso dos membros do inquilino", False,
     QUATRO_PERFIS),
    ("membros.ver_tudo", "membros", "ver e-mail, IP, sessões, tokens e 2FA de qualquer membro", True, (A,)),
    (
        "membros.gerir",
        "membros",
        "criar, editar nome/e-mail, desabilitar/reabilitar, redefinir senha, desligar 2FA, desbloquear",
        True,
        (A,),
    ),  # noqa: E501
    ("membros.papel", "membros", "mudar perfil e papel (para/de admin só quem é admin)", True, (A,)),
    ("membros.apagar", "membros", "apagar membro (só sem conteúdo e sem grupo)", True, (A,)),
    ("papeis.gerir", "papeis", "criar, editar, apagar papel personalizado", True, (A,)),
    ("grupos.ver_inquilino", "grupos", "ver grupos com visibilidade inquilino", False, QUATRO_PERFIS),
    ("grupos.entrar", "grupos", "pedir entrada ou entrar em grupo de entrada livre", False, QUATRO_PERFIS),
    ("grupos.criar", "grupos", "criar, editar e apagar os próprios grupos", False, (E, A)),
    ("grupos.atualizacao_compartilhada", "grupos", "criar grupo com atualização compartilhada", False, (E, A)),
    ("grupos.administrativo", "grupos", "criar grupo administrativo (membro não sai)", True, (A,)),
    ("grupos.gerir_todos", "grupos", "editar, apagar, transferir dono e gerir membros de qualquer grupo", True, (A,)),
    ("conteudo.ver_inquilino", "conteudo", "ver itens compartilhados com o inquilino", False, QUATRO_PERFIS),
    ("conteudo.criar", "conteudo", "criar, editar e apagar os próprios itens (mapa, app, pasta)", False, (E, A)),
    ("conteudo.publicar_camada", "conteudo", "publicar camada vetorial hospedada", False, (E, A)),
    ("conteudo.publicar_tiles", "conteudo", "publicar tiles vetoriais", False, (E, A)),
    ("conteudo.publicar_raster", "conteudo", "publicar imagem/raster", False, (E, A)),
    ("conteudo.registrar_fonte", "conteudo", "registrar fonte de dado externa", False, (E, A)),
    ("conteudo.categorias", "conteudo", "gerir categorias do inquilino", True, (A,)),
    ("conteudo.ver_tudo", "conteudo", "ver qualquer item do inquilino, inclusive privado", True, (A,)),
    ("conteudo.editar_tudo", "conteudo", "editar metadado e dado de qualquer item", True, (A,)),
    ("conteudo.apagar_tudo", "conteudo", "apagar/restaurar qualquer item", True, (A,)),
    ("conteudo.transferir", "conteudo", "mudar dono de item", True, (A,)),
    ("compartilhar.grupo", "compartilhar", "compartilhar item com grupo em que pode contribuir", False, (E, A)),
    ("compartilhar.inquilino", "compartilhar", "compartilhar item com todo o inquilino", False, (E, A)),
    ("compartilhar.link", "compartilhar", "criar link por token", False, (E, A)),
    ("compartilhar.publico", "compartilhar", "tornar item público (só com config.compartilhar_publico)", True, (A,)),
    ("feicoes.editar", "feicoes", "editar feições de camada compartilhada com edição habilitada", False, (C, E, A)),
    ("feicoes.editar_total", "feicoes", "editar qualquer camada, mesmo sem edição habilitada", True, (A,)),
    ("campo.coletar", "campo", "usar formulários e a PWA de campo", False, (C, E, A)),
    ("campo.localizacao", "campo", "compartilhar localização/trilhas", False, (C, E, A)),
    ("analise.geocodificar", "analise", "geocodificar e buscar lugar", False, QUATRO_PERFIS),
    ("analise.rotas", "analise", "rotas e isócronas", False, QUATRO_PERFIS),
    ("analise.executar", "analise", "geoprocessamento sobre dado próprio", False, (E, A)),
    ("analise.amc", "analise", "criar e executar modelo multicritério", False, (E, A)),
    ("analise.raster", "analise", "análise de imagem", False, (E, A)),
    ("rede.tracar", "rede", "traçado e subrede", False, (E, A)),
    ("rede.editar", "rede", "editar rede de utilidades", False, (E, A)),
    # migração 20260906T2219 (item L4-03-a): a comporta `regras_ativas` e a substituição do conjunto de
    # regras por CSV ficam FORA do editar do dia a dia — quem edita feição não abre a comporta
    ("rede.administrar", "rede",
     "ligar/desligar a avaliação de regras da rede e substituir o conjunto de regras por CSV", True, (A,)),
    ("jobs.ver", "jobs", "ver a lista, o detalhe, o log e os tipos de job do inquilino (leitura)", False,
     QUATRO_PERFIS),  # acrescentado em T2 (migração 015): sem ele o visualizador tomava 403 na tela Tarefas
    ("jobs.executar", "jobs", "criar, cancelar e repetir os próprios jobs, e gerir agendas", False,
     (C, E, A)),
    ("jobs.gerir_todos", "jobs", "ver e cancelar jobs de qualquer membro", True, (A,)),
    ("tokens.gerar", "tokens", "criar e revogar os próprios tokens de serviço", False, QUATRO_PERFIS),
    ("tokens.gerir_todos", "tokens", "ver e revogar tokens de qualquer membro", True, (A,)),
    ("org.configurar", "org", "editar tenant.config, política de senha, exigir 2FA, domínios de e-mail", True, (A,)),
    ("org.log_ver", "org", "ler log_acesso e evento do inquilino, exportar CSV", True, (A,)),
    ("org.exportar", "org", "exportar o inquilino, relatórios", True, (A,)),
    ("org.integracoes", "org", "SSO, SMTP, webhooks, CORS", True, (A,)),
)
NOMES = frozenset(p[0] for p in PRIVILEGIOS)
ADMINISTRATIVOS = frozenset(p[0] for p in PRIVILEGIOS if p[3])


def teto(perfil: str) -> frozenset[str]:
    return frozenset(p[0] for p in PRIVILEGIOS if perfil in p[4])


def perfil_minimo(privilegios: set[str] | frozenset[str]) -> str | None:
    """Menor perfil cujo teto contém todos os privilégios; None se nenhum contém (nome desconhecido)."""
    for perfil in PERFIS:
        if set(privilegios) <= teto(perfil):
            return perfil
    return None
