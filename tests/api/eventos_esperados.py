"""Evento(s) de domínio que cada rota de escrita do L0-02 registra (ADR 0002 seção 9.4). Rota de escrita no
OpenAPI sem entrada aqui = falha em test_eventos.py.

- `EVENTOS_POR_ROTA`: rota que MUDA estado do inquilino, com a lista dos tipos de evento que narra. Nunca
  fica vazia aqui (achado G4-03: lista vazia era "sem evento" disfarçado) — quem não gera evento vai para
  `ROTAS_SEM_EVENTO`.
- `ROTAS_SEM_EVENTO`: as poucas rotas de verbo de escrita que NÃO alteram estado (cálculo puro, protocolo Esri
  que usa POST para leitura, parte de um envio que já é narrado pelo início e pela conclusão). Cada entrada
  carrega o MOTIVO escrito, e `test_eventos.py` reprova motivo curto ou ausente, entrada repetida nas duas
  listas, e rota que aparece aqui apesar de o seu módulo chamar `registrar_evento`.

Rota de escrita do OpenAPI que não esteja em uma das duas = falha em `test_eventos.py`."""

EVENTOS_POR_ROTA: dict[tuple[str, str], list[str]] = {
    ("POST", "/api/login"): ["usuarios/entrar", "usuarios/falha_login"],
    ("POST", "/api/login/2fa"): ["usuarios/entrar", "usuarios/falha_login"],
    ("POST", "/api/logout"): ["usuarios/sair"],
    ("PUT", "/api/eu"): ["usuarios/atualizar"],
    ("PUT", "/api/eu/senha"): ["usuarios/trocar_senha"],
    ("DELETE", "/api/eu/sessoes"): ["sessoes/revogar"],
    ("DELETE", "/api/eu/sessoes/{id}"): ["sessoes/revogar"],
    ("POST", "/api/eu/2fa/confirmar"): ["usuarios/2fa_ligar"],
    ("POST", "/api/eu/2fa/desativar"): ["usuarios/2fa_desligar"],
    ("POST", "/api/eu/2fa/codigos"): ["usuarios/2fa_codigos"],
    # L1-27: a ficha grava sempre; afrouxar licença restrita -> livre gera o evento próprio (aprovada) ou o
    # de recusa (sem o privilégio org.configurar), e é isso que a auditoria da casa lê
    ("PUT", "/api/imagens/{item_id}/ficha"): [
        "imagens/ficha_gravar",
        "imagens/ficha_licenca_afrouxada",
        "imagens/ficha_licenca_recusada",
    ],
    ("POST", "/api/papeis"): ["papeis/criar"],
    ("PUT", "/api/papeis/{id}"): ["papeis/atualizar"],
    ("DELETE", "/api/papeis/{id}"): ["papeis/apagar"],
    ("POST", "/api/usuarios"): ["usuarios/criar"],
    ("POST", "/api/usuarios/lote"): ["usuarios/papel", "usuarios/desabilitar", "usuarios/reabilitar"],
    ("PUT", "/api/usuarios/{id}"): [
        "usuarios/atualizar",
        "usuarios/papel",
        "usuarios/desabilitar",
        "usuarios/reabilitar",
    ],
    ("DELETE", "/api/usuarios/{id}"): ["usuarios/apagar"],
    ("POST", "/api/usuarios/{id}/senha"): ["usuarios/redefinir_senha"],
    ("POST", "/api/usuarios/{id}/2fa/desativar"): ["usuarios/2fa_desligar"],
    ("POST", "/api/usuarios/{id}/desbloquear"): ["usuarios/desbloquear"],
    ("POST", "/api/grupos"): ["grupos/criar"],
    ("PUT", "/api/grupos/{id}"): ["grupos/atualizar", "grupos/transferir"],
    ("DELETE", "/api/grupos/{id}"): ["grupos/apagar"],
    ("POST", "/api/grupos/{id}/membros"): ["grupos/convidar"],
    ("POST", "/api/grupos/{id}/entrar"): ["grupos/entrar", "grupos/pedir"],
    ("POST", "/api/grupos/{id}/aceitar"): ["grupos/entrar"],
    ("POST", "/api/grupos/{id}/recusar"): ["grupos/recusar"],
    ("POST", "/api/grupos/{id}/membros/{uid}/aprovar"): ["grupos/aprovar"],
    ("PUT", "/api/grupos/{id}/membros/{uid}"): ["grupos/papel"],
    ("DELETE", "/api/grupos/{id}/membros/{uid}"): ["grupos/sair", "grupos/remover"],
    ("POST", "/api/tokens"): ["tokens/criar"],
    ("POST", "/api/tokens/{id}/renovar"): ["tokens/renovar"],
    ("DELETE", "/api/tokens/{id}"): ["tokens/revogar"],
    ("POST", "/api/plataforma/inquilinos"): ["inquilinos/criar"],
    ("POST", "/api/plataforma/inquilinos/{id}/suspender"): ["inquilinos/suspender"],
    ("POST", "/api/plataforma/inquilinos/{id}/reativar"): ["inquilinos/reativar"],
    ("DELETE", "/api/plataforma/inquilinos/{id}"): ["inquilinos/apagar"],
    # ---- fila de jobs (L0-05; vocabulário na migração 007)
    ("POST", "/api/jobs"): ["jobs/criar"],
    ("POST", "/api/jobs/{job_id}/cancelar"): ["jobs/cancelar"],
    ("POST", "/api/jobs/{job_id}/repetir"): ["jobs/criar"],
    ("POST", "/api/agendas"): ["agendas/criar"],
    ("PUT", "/api/agendas/{agenda_id}"): ["agendas/atualizar"],
    ("DELETE", "/api/agendas/{agenda_id}"): ["agendas/apagar"],
    ("POST", "/api/agendas/{agenda_id}/pausar"): ["agendas/pausar"],
    ("POST", "/api/agendas/{agenda_id}/retomar"): ["agendas/retomar"],
    ("POST", "/api/agendas/{agenda_id}/rodar-agora"): ["jobs/criar"],
    # ---- catálogo (L0-03; vocabulário na migração 011)
    ("POST", "/api/itens"): ["itens/adicionar"],
    ("POST", "/api/acervo/{fonte_id}/adicionar"): ["itens/adicionar", "acervo/adicionar_recusado_pii"],
    ("PUT", "/api/itens/{id}"): ["itens/atualizar", "itens/status", "itens/proteger", "itens/desproteger"],
    ("PATCH", "/api/itens/{id}"): ["itens/atualizar", "itens/status", "itens/proteger", "itens/desproteger"],
    ("DELETE", "/api/itens/{id}"): ["itens/apagar"],
    ("POST", "/api/itens/lote"): ["itens/apagar", "itens/restaurar", "itens/mover", "itens/atualizar", "itens/proteger",
                                  "itens/desproteger", "itens/status", "compartilhamento/alterar"],
    ("POST", "/api/itens/transferir"): ["itens/transferir"],
    ("POST", "/api/itens/{id}/mover"): ["itens/mover"],
    ("POST", "/api/itens/{id}/miniatura"): ["itens/miniatura"],
    ("POST", "/api/itens/{id}/miniatura/gerar"): ["itens/miniatura"],
    ("DELETE", "/api/itens/{id}/miniatura"): ["itens/miniatura"],
    ("POST", "/api/itens/{id}/versoes/{n}/restaurar"): ["itens/atualizar", "itens/versao_restaurar"],
    ("POST", "/api/itens/{id}/versoes/{n}/publicar"): ["itens/versao_publicar"],
    ("PUT", "/api/itens/{id}/relacoes"): ["itens/relacoes"],
    ("PUT", "/api/itens/{id}/compartilhamento"): ["compartilhamento/alterar"],
    ("POST", "/api/itens/{id}/links"): ["compartilhamento/link_criar"],
    ("DELETE", "/api/itens/{id}/links/{lid}"): ["compartilhamento/link_revogar"],
    ("POST", "/api/pastas"): ["pastas/criar"],
    ("PUT", "/api/pastas/{id}"): ["pastas/renomear", "pastas/mover"],
    ("DELETE", "/api/pastas/{id}"): ["pastas/apagar"],
    ("PUT", "/api/categorias"): ["categorias/alterar"],
    ("POST", "/api/categorias/importar"): ["categorias/importar"],
    ("PUT", "/api/favoritos/{item_id}"): ["favoritos/adicionar"],
    ("DELETE", "/api/favoritos/{item_id}"): ["favoritos/remover"],
    ("POST", "/api/lixeira/{id}/restaurar"): ["itens/restaurar"],
    ("POST", "/api/lixeira/esvaziar"): ["lixeira/esvaziar"],
    # ---- LDAP/Active Directory (L0-08-d): login registra a MESMA sequência do login local, reaproveitada de
    # _abrir_sessao ("usuarios/entrar"), mais o provisionamento automático (criação ou sincronização do
    # usuário a partir do diretório); administração do provedor tem vocabulário próprio ("org/*")
    ("POST", "/api/login/ldap"): ["usuarios/criar", "usuarios/atualizar", "usuarios/entrar"],
    ("PUT", "/api/org/ldap"): ["org/ldap_configurar"],
    ("POST", "/api/org/ldap/importar"): ["org/ldap_importar"],
    # ---- configurações da organização (L0-07-a-configuracoes-org)
    ("PUT", "/api/org"): ["org/configurar"],
    ("POST", "/api/org/logo"): ["org/logo_enviar"],
    ("DELETE", "/api/org/logo"): ["org/logo_remover"],
    # ---- convite de membro por e-mail (L0-07-d-smtp-convites; ADR 0013)
    ("POST", "/api/convites"): ["convites/criar"],
    ("DELETE", "/api/convites/{id}"): ["convites/cancelar"],
    ("POST", "/api/convites/aceitar"): ["usuarios/convite_aceito"],
    # ---- redefinição de senha por e-mail (L0-07-d-smtp-convites; ADR 0002 seção 6.3): o evento nasce só
    # quando a senha É trocada, em `aplicar` (ver `solicitar` em ROTAS_SEM_EVENTO).
    ("POST", "/api/senha/redefinir/aplicar"): ["usuarios/redefinir_senha_email"],
    # ---- SMTP por inquilino (L0-07-d-smtp-convites; ADR 0013): PUT tanto configura quanto remove o override
    # (host="" apaga), então os dois tipos aparecem juntos.
    ("PUT", "/api/org/smtp"): ["org/smtp_configurar", "org/smtp_remover"],
    ("POST", "/api/org/smtp/testar"): ["org/smtp_testar"],
    # ---- upload retomável (L0-04-a-upload-arquivo; ADR 0005 seção 3): `enviar_parte` não registra evento por
    # parte (ver ROTAS_SEM_EVENTO); `uploads/iniciar` e `uploads/concluir`/`uploads/abortar` já narram início e
    # fim do processo.
    ("POST", "/api/uploads"): ["uploads/iniciar"],
    ("POST", "/api/uploads/{id}/concluir"): ["uploads/concluir"],
    ("DELETE", "/api/uploads/{id}"): ["uploads/abortar"],
    # ---- ingestão vetorial (L0-04-b/c/d; ADR 0005 seção 16): `apagar` de proposta nunca carregada vai para
    # ROTAS_SEM_EVENTO — sem efeito sobre o catálogo.
    ("POST", "/api/importacoes"): ["importacoes/criar"],
    ("PUT", "/api/importacoes/{id}/confirmar"): ["importacoes/confirmar"],
    # ---- achado nesta verificação: as duas famílias abaixo já existiam em master sem entrada aqui (não são
    # deste turno) — /api/eu/foto (app/auth/rotas_eu.py) e /api/conexoes (L6-02-a-modelo-conexao-e-seguranca,
    # app/conexao/rotas.py). Sem elas o portão de cobertura nunca passava, mesmo antes das rotas novas.
    ("POST", "/api/eu/foto"): ["usuarios/foto_enviar"],
    ("DELETE", "/api/eu/foto"): ["usuarios/foto_remover"],
    ("POST", "/api/conexoes"): ["conexoes/criar"],
    ("PATCH", "/api/conexoes/{id}"): ["conexoes/editar"],
    ("DELETE", "/api/conexoes/{id}"): ["conexoes/apagar"],
    ("POST", "/api/conexoes/{id}/testar"): ["conexoes/testar"],
    ("POST", "/api/conexoes/{id}/publicar"): ["conexoes/publicar_camada"],
    # ---- motor multicritério em grades aninhadas (L3-19-multiescala; vocabulário nas migrações
    # 20260906T1640_multiescala.sql e 20260906T1823_multiescala_apagar.sql). Conjunto, fator e execução são
    # tabelas do inquilino com dono humano, então toda escrita narra evento; o DELETE apaga em cascata e por
    # isso tem tipo próprio (`_apagar`), separado do de criação.
    ("POST", "/api/multiescala/conjuntos"): ["multiescala/conjunto"],
    ("DELETE", "/api/multiescala/conjuntos/{id}"): ["multiescala/conjunto_apagar"],
    ("POST", "/api/multiescala/fatores"): ["multiescala/fator"],
    ("DELETE", "/api/multiescala/fatores/{id}"): ["multiescala/fator_apagar"],
    ("POST", "/api/multiescala/fatores/{id}/amostras"): ["multiescala/amostras"],
    ("POST", "/api/multiescala/conjuntos/{id}/macro"): ["multiescala/macro"],
    ("POST", "/api/multiescala/execucoes/{id}/micro"): ["multiescala/micro"],
    # ---- rede de utilidades (L4-01-a/b, L4-02-a, L4-05-d, L4-05-e; vocabulário nas migrações
    # 20260906T1553, 20260906T2000, 20260906T2048, 20260907T1306, 20260907T1629 e 20260908T1032). As rotas de
    # escrita desta família já existiam sem entrada aqui — o portão de cobertura só passou a alcançá-las quando
    # `docs/openapi.json` foi regerado (item L4-05-e); o GET .../epanet e as duas conferências de gás e esgoto
    # são leitura e não aparecem, como as demais leituras.
    ("POST", "/api/rede"): ["redes/criar"],
    ("DELETE", "/api/rede/{rede_id}"): ["redes/apagar"],
    ("POST", "/api/rede/{rede_id}/pacote"): ["redes/importar_pacote"],
    ("POST", "/api/rede/{rede_id}/feicoes/pontos"): ["redes/feicao_criar"],
    ("POST", "/api/rede/{rede_id}/feicoes/linhas"): ["redes/feicao_criar"],
    ("POST", "/api/rede/{rede_id}/feicoes/pontos/applyEdits"): ["redes/feicao_editar"],
    ("POST", "/api/rede/{rede_id}/feicoes/linhas/applyEdits"): ["redes/feicao_editar"],
    ("POST", "/api/rede/{rede_id}/topologia/habilitar"): ["redes/topologia_habilitar"],
    ("POST", "/api/rede/{rede_id}/tracar"): ["redes/tracar"],
    ("POST", "/api/rede/{rede_id}/epanet"): ["redes/epanet_importar"],
    ("POST", "/api/rede/{rede_id}/teksi"): ["redes/teksi_importar"],
    # L7-03-a: o envio bem-sucedido continua sem evento (sem dono humano — a auditoria é plat.arquivo +
    # plat.log_acesso); a RECUSA pelo pipeline único (tipo fora da rota, bytes, zip-bomba, SVG, antivírus) é
    # o que vai para a trilha.
    ("POST", "/api/arquivos"): ["arquivos/conteudo_recusado", "arquivos/quarentena"],
}


ROTAS_SEM_EVENTO: dict[tuple[str, str], str] = {
    ("POST", "/api/eu/2fa/iniciar"):
        "só liga no confirmar; iniciar sem confirmar não muda o estado da conta, nada para narrar ainda",
    ("DELETE", "/api/arquivos/{sha256}"):
        "mesma decisão de POST /api/arquivos: sem dono humano, a auditoria fica em plat.arquivo/log_acesso",
    ("POST", "/api/rota"):
        "cálculo de rota sobre dado aberto (OSM) pelo OSRM: nenhuma escrita em plat.*, nenhum objeto criado; "
        "o uso fica em plat.log_acesso (rota, ip, tempo, token_id)",
    ("POST", "/api/matriz"):
        "matriz de distância pelo OSRM: mesmo caso do POST /api/rota, cálculo sem escrita em plat.*",
    ("POST", "/api/isocrona"):
        "isócrona pelo OSRM: mesmo caso do POST /api/rota, cálculo sem escrita em plat.*",
    ("POST", "/api/senha/redefinir/solicitar"):
        "sempre responde {\"ok\": true} sem revelar se o e-mail existe e não registra evento nenhum (mesma "
        "decisão de /api/login com credencial errada); o evento nasce só quando a senha É trocada, em aplicar",
    ("PUT", "/api/uploads/{id}/partes/{n}"):
        "upload retomável: não registra evento por parte (o volume tornaria o log ruidoso sem valor de "
        "auditoria); uploads/iniciar e uploads/concluir/abortar já narram início e fim do processo",
    ("DELETE", "/api/importacoes/{id}"):
        "só remove importações que nunca chegaram a carregar (proposta/falhou/cancelada/expirada) — sem "
        "efeito sobre o catálogo, sem evento de domínio",
    ("POST", "/api/geocodificar"):
        "consulta ao gazetteer: leitura pura, é POST só porque o pedido é um corpo JSON grande demais para a "
        "linha de consulta; o uso fica em plat.log_acesso",
    ("POST", "/api/reverso"):
        "geocodificação reversa: leitura pura, mesmo caso do POST /api/geocodificar acima",
    ("POST", "/rest/services/Geocodificador/GeocodeServer"):
        "descritor do serviço no protocolo Esri: o mesmo documento do GET, que o cliente ArcGIS também pede "
        "por POST; nenhuma escrita em plat.*",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"):
        "busca de endereço no protocolo Esri: leitura pura, o cliente ArcGIS usa GET ou POST conforme o "
        "tamanho do pedido; mesma decisão de /api/geocodificar",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/reverseGeocode"):
        "geocodificação reversa no protocolo Esri: leitura pura, mesmo caso do findAddressCandidates acima",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses"):
        "geocodificação em lote no protocolo Esri: leitura pura, mesmo caso do findAddressCandidates acima",
    # ---- webhooks de eventos (L7-08-a-webhooks-eventos; vocabulário na migração 20260909T0345):
    # toda escrita narra evento, e o próprio webhook escuta esses fatos (subscribe em webhooks/*);
    # webhooks/desativar entra no log sem rota (nasce da tarefa de entrega por falhas seguidas).
    ("POST", "/api/webhooks"): ["webhooks/criar"],
    ("PATCH", "/api/webhooks/{id}"): ["webhooks/atualizar"],
    ("DELETE", "/api/webhooks/{id}"): ["webhooks/apagar"],
    ("POST", "/api/webhooks/{id}/rotacionar"): ["webhooks/rotacionar"],
    ("POST", "/api/webhooks/{id}/reativar"): ["webhooks/reativar"],
    ("POST", "/api/webhooks/{id}/entregas/{entrega_id}/reenviar"): ["webhooks/reenvio"],
    # L4-10 continuidade DEC/FEC: a importação do dado aberto da ANEEL e o apagamento por conjunto
    ("POST", "/api/rede/{rede_id}/continuidade/importar"): ["redes/continuidade_importar"],
    ("DELETE", "/api/rede/{rede_id}/continuidade"): ["redes/continuidade_apagar"],
}
