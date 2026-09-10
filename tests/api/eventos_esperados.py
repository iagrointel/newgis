"""Evento(s) de domínio que cada rota de escrita do L0-02 registra (ADR 0002 seção 9.4).

Duas listas, e nenhuma das duas aceita silêncio (achado G4-03 do ataque ao grupo G4: a lista VAZIA era aceita,
e `POST`/`DELETE /api/arquivos` — que criam e destroem objeto do inquilino — estavam declarados como "sem
evento", de modo que o guardião aprovava destruição de dado sem rastro):

- `EVENTOS_POR_ROTA`: rota que altera estado. **Lista vazia é proibida** (`test_eventos.py` reprova); toda
  entrada tem pelo menos um tipo, e todo tipo citado tem de existir como literal no código de `app/` e como
  linha em `plat.evento_tipo`.
- `ROTAS_SEM_EVENTO`: as poucas rotas de verbo de escrita que NÃO alteram estado (cálculo puro, protocolo Esri
  que usa POST para leitura, parte de um envio que já é narrado pelo início e pela conclusão). Cada entrada
  carrega o MOTIVO escrito, e `test_eventos.py` reprova motivo curto ou ausente, entrada repetida nas duas
  listas, e rota que aparece aqui apesar de o seu módulo chamar `registrar_evento`.

Rota de escrita do OpenAPI que não esteja em uma das duas = falha em `test_eventos.py`. E, desde o mesmo
conserto, `tests/api/test_openapi_contrato.py` garante que o OpenAPI comitado é o da aplicação viva — sem ele
a cobertura media um arquivo velho (achado G4-01).
"""

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
    # ---- L0-07-f console da plataforma (vocabulário na migração 20260907T2325)
    ("PUT", "/api/plataforma/inquilinos/{id}/cotas"): ["inquilinos/cotas"],
    ("POST", "/api/plataforma/inquilinos/{id}/admins/{usuario_id}/2fa/desativar"): ["inquilinos/2fa_desligar"],
    # ---- relatórios do admin (L0-07-e; vocabulário na migração 20260908T0136)
    ("POST", "/api/relatorios"): ["relatorios/gerar"],
    ("POST", "/api/relatorios/agendas"): ["relatorios/agendar"],
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
    # ---- arquivos/objetos (L0-11): gravar e apagar objeto do inquilino são eventos de domínio. A decisão
    # anterior ("sem dono humano para narrar") deixava a destruição de dado sem rastro — foi o achado G4-08.
    ("POST", "/api/arquivos"): ["arquivos/enviar"],
    ("DELETE", "/api/arquivos/{sha256}"): ["arquivos/apagar"],
    # ---- LDAP/Active Directory (L0-08-d): login registra a MESMA sequência do login local, reaproveitada de
    # _abrir_sessao ("usuarios/entrar"), mais o provisionamento automático (criação ou sincronização do
    # usuário a partir do diretório); administração do provedor tem vocabulário próprio ("org/*")
    ("POST", "/api/login/ldap"): ["usuarios/criar", "usuarios/atualizar", "usuarios/entrar"],
    ("PUT", "/api/org/ldap"): ["org/ldap_configurar"],
    ("POST", "/api/org/ldap/importar"): ["org/ldap_importar"],
    # ---- configurações da organização (L0-07-a-configuracoes-org)
    ("PUT", "/api/org"): ["org/configurar"],
    ("PUT", "/api/org/tema"): ["org/tema_gravar"],  # L5-10: tema do inquilino gravado ou removido (mesma rota)
    ("POST", "/api/org/logo"): ["org/logo_enviar"],
    ("DELETE", "/api/org/logo"): ["org/logo_remover"],
    # ---- L4-01-b-topologia-derivada: eventos registrados pelas rotas (vocabulário em db/migracoes da rede)
    ("POST", "/api/rede/{rede_id}/feicoes/pontos/applyEdits"): ["redes/feicao_editar"],
    ("POST", "/api/rede/{rede_id}/feicoes/linhas/applyEdits"): ["redes/feicao_editar"],
    # ---- edição transacional de feições (L2-03-a): um evento por LOTE (nunca um por feição), com a contagem
    # de adicionadas/atualizadas/apagadas em propriedades — mesmo em modo `parcial` com tudo recusado
    ("POST", "/api/camadas/{id}/edicoes"): ["camadas/editar"],
    # L2-10-d-regras-de-atributo: definir regras grava evento próprio; validar enfileira job (evento do serviço)
    ("PUT", "/api/camadas/{id}/regras"): ["camadas/regras_definir"],
    ("POST", "/api/camadas/{id}/validar"): ["jobs/criar"],
    # ---- convite de membro por e-mail (L0-07-d-smtp-convites; ADR 0013)
    ("POST", "/api/convites"): ["convites/criar"],
    ("DELETE", "/api/convites/{id}"): ["convites/cancelar"],
    ("POST", "/api/convites/aceitar"): ["usuarios/convite_aceito"],
    # ---- redefinição de senha por e-mail (L0-07-d-smtp-convites; ADR 0002 seção 6.3): `solicitar` SEMPRE
    # responde {"ok": true} sem revelar se o e-mail existe e não registra evento nenhum (mesma decisão de
    # /api/login com credencial errada) — o evento nasce só quando a senha É trocada, em `aplicar`.
    # ---- rede de utilidades — controlador de subrede e tiers (L4-04-a): as quatro escritas registram evento;
    # a importação registra um evento só, com a contagem por tier no detalhe.
    # --- rede de utilidades (L4-01-a/L4-01-b/L4-02-a/L4-18): as rotas vieram nos ramos-base desta família e
    # ainda não tinham entrada aqui; o nome do evento é o que cada rota registra de fato.
    ("POST", "/api/rede"): ["redes/criar"],
    ("DELETE", "/api/rede/{rede_id}"): ["redes/apagar"],
    ("POST", "/api/rede/{rede_id}/pacote"): ["redes/importar_pacote"],
    # L4-01-c: a importação BDGD é um job; o evento é o do enfileiramento
    ("POST", "/api/rede/{rede_id}/importar-bdgd"): ["redes/importar_bdgd"],
    ("POST", "/api/rede/{rede_id}/matpower"): ["redes/importar_matpower"],
    # L4-01-a/L4-01-b/L4-18: as rotas de escrita da rede de utilidades que ainda não estavam declaradas
    # aqui (a rota existe e registra o evento; faltava a linha desta tabela). Lidas uma a uma em
    # app/rede_utilidades/rotas*.py.
    ("POST", "/api/rede/{rede_id}/feicoes/pontos"): ["redes/feicao_criar"],
    ("POST", "/api/rede/{rede_id}/feicoes/linhas"): ["redes/feicao_criar"],
    # (applyEdits de ponto e de linha já estão declarados no bloco do L4-01-b, acima)
    ("POST", "/api/rede/{rede_id}/topologia/habilitar"): ["redes/topologia_habilitar"],
    ("POST", "/api/rede/{rede_id}/tracar"): ["redes/tracar"],
    # ---- L4-02-f: o resultado do traçado vira arquivo, camada e histórico
    ("POST", "/api/rede/{rede_id}/tracar/exportar"): ["redes/tracar_exportar"],
    ("POST", "/api/rede/{rede_id}/tracar/camada"): ["redes/tracar_camada"],
    ("POST", "/api/rede/{rede_id}/tracados/{execucao_id}/repetir"): ["redes/tracar"],
    ("POST", "/api/rede/{rede_id}/config_tracado"): ["redes/config_tracado_criar"],
    ("PUT", "/api/rede/{rede_id}/config_tracado/{config_id}"): ["redes/config_tracado_alterar"],
    ("DELETE", "/api/rede/{rede_id}/config_tracado/{config_id}"): ["redes/config_tracado_apagar"],
    ("POST", "/api/rede/simples"): ["redes/simples_criar"],
    ("POST", "/api/rede/{rede_id}/promover"): ["redes/simples_promover"],
    ("POST", "/api/rede/{rede_id}/controlador"): ["redes/controlador_definir"],
    ("DELETE", "/api/rede/{rede_id}/controlador/{controlador_id}"): ["redes/controlador_remover"],
    ("POST", "/api/rede/{rede_id}/controladores/importar"): ["redes/controlador_importar"],
    ("POST", "/api/rede/{rede_id}/subredes/{subrede_id}/atualizar"): ["redes/subrede_atualizar"],
    # L4-04-b: o lote é um JOB — o evento é o do enfileiramento; a exportação e a conferência são leituras
    ("POST", "/api/rede/{rede_id}/subredes/atualizar"): ["redes/subredes_atualizar"],
    ("PUT", "/api/rede/{rede_id}/tier/{codigo}/propagadores"): ["redes/tier_propagadores"],
    ("POST", "/api/rede/{rede_id}/subredes/resumos/calcular"): ["redes/subrede_resumo"],
    ("POST", "/api/rede/{rede_id}/subrede/{nome}/curto"): ["redes/curto_circuito"],
    # L4-04-d diagrama de rede
    ("POST", "/api/rede/{rede_id}/diagrama"): ["redes/diagrama_gerar"],
    ("POST", "/api/rede/{rede_id}/diagrama/{diagrama_id}/layout"): ["redes/diagrama_layout"],
    ("DELETE", "/api/rede/{rede_id}/diagrama/{diagrama_id}"): ["redes/diagrama_apagar"],
    ("PUT", "/api/rede/{rede_id}/diagrama-modelo/{codigo}"): ["redes/diagrama_modelo_definir"],
    ("POST", "/api/rede/{rede_id}/subrede/{nome}/fluxo"): ["redes/fluxo_potencia"],
    ("POST", "/api/senha/redefinir/solicitar"): [],
    ("POST", "/api/senha/redefinir/aplicar"): ["usuarios/redefinir_senha_email"],
    # ---- SMTP por inquilino (L0-07-d-smtp-convites; ADR 0013): PUT tanto configura quanto remove o override
    # (host="" apaga), então os dois tipos aparecem juntos.
    ("PUT", "/api/org/smtp"): ["org/smtp_configurar", "org/smtp_remover"],
    ("POST", "/api/org/smtp/testar"): ["org/smtp_testar"],
    # ---- upload retomável (L0-04-a-upload-arquivo; ADR 0005 seção 3): `enviar_parte` não registra evento por
    # parte (o volume de partes tornaria o log ruidoso sem valor de auditoria; `uploads/iniciar` e
    # `uploads/concluir`/`uploads/abortar` já narram início e fim do processo).
    ("POST", "/api/uploads"): ["uploads/iniciar"],
    ("PUT", "/api/uploads/{id}/partes/{n}"): [],
    ("POST", "/api/uploads/{id}/concluir"): ["uploads/concluir"],
    ("DELETE", "/api/uploads/{id}"): ["uploads/abortar"],
    # ---- ingestão vetorial (L0-04-b/c/d; ADR 0005 seção 16): `apagar` só remove importações que nunca
    # chegaram a carregar (proposta/falhou/cancelada/expirada) — sem efeito sobre o catálogo, sem evento.
    ("POST", "/api/importacoes"): ["importacoes/criar"],
    ("PUT", "/api/importacoes/{id}/confirmar"): ["importacoes/confirmar"],
    ("DELETE", "/api/importacoes/{id}"): [],
    # ---- geocodificador (L2-11-a/b): cálculo sobre dado aberto CNEFE/IBGE, sem tabela de inquilino e sem
    # dono humano para narrar — mesma decisão já usada acima em /api/rota, /api/matriz, /api/isocrona.
    ("POST", "/api/geocodificar"): [],
    ("POST", "/api/reverso"): [],
    # ---- agregação e gráfico por camada (L2-06-e, L2-01-i): POST só porque o pedido é um corpo JSON; são
    # LEITURAS (SELECT agregado, nada muda no catálogo nem na camada) — sem evento, como /api/geocodificar.
    ("POST", "/api/camadas/{item_id}/estatisticas"): [],
    ("POST", "/api/camadas/{item_id}/grafico"): [],
    ("POST", "/rest/services/Geocodificador/GeocodeServer"): [],
    ("POST", "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"): [],
    ("POST", "/rest/services/Geocodificador/GeocodeServer/reverseGeocode"): [],
    ("POST", "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses"): [],
    # ---- achado nesta verificação: as duas famílias abaixo já existiam em master sem entrada aqui (não são
    # deste turno) — /api/eu/foto (app/auth/rotas_eu.py) e /api/conexoes (L6-02-a-modelo-conexao-e-seguranca,
    # app/conexao/rotas.py). Sem elas o portão de cobertura nunca passava, mesmo antes das rotas novas.
    ("POST", "/api/eu/foto"): ["usuarios/foto_enviar"],
    ("DELETE", "/api/eu/foto"): ["usuarios/foto_remover"],
    # ---- teto de cota, escrito só pela plataforma (conserto dos achados G4-04/G4-05)
    ("PUT", "/api/plataforma/inquilinos/{id}/cotas"): ["inquilinos/cotas_teto"],
    # ---- convite de membro por e-mail (L0-07-d-smtp-convites)
    ("POST", "/api/convites"): ["convites/criar"],
    ("DELETE", "/api/convites/{id}"): ["convites/cancelar"],
    ("POST", "/api/convites/aceitar"): ["usuarios/convite_aceito"],
    # ---- redefinição de senha por e-mail (L0-07-d-smtp-convites)
    ("POST", "/api/senha/redefinir/solicitar"): ["usuarios/redefinir_senha_pedido"],
    ("POST", "/api/senha/redefinir/aplicar"): ["usuarios/redefinir_senha_email"],
    # ---- SMTP por inquilino (L0-07-d-smtp-convites)
    ("PUT", "/api/org/smtp"): ["org/smtp_configurar", "org/smtp_remover"],
    ("POST", "/api/org/smtp/testar"): ["org/smtp_testar"],
    # ---- foto do próprio perfil (L0-02)
    ("POST", "/api/eu/foto"): ["usuarios/foto_enviar"],
    ("DELETE", "/api/eu/foto"): ["usuarios/foto_remover"],
    # ---- 2FA: iniciar não muda a conta, mas registra a tentativa (não há mais declaração vazia)
    ("POST", "/api/eu/2fa/iniciar"): ["usuarios/2fa_iniciar"],
    # ---- envio retomável em partes (L0-04-a-upload-arquivo)
    ("POST", "/api/uploads"): ["uploads/iniciar"],
    ("POST", "/api/uploads/{id}/concluir"): ["uploads/concluir"],
    ("DELETE", "/api/uploads/{id}"): ["uploads/abortar"],
    # ---- fontes externas registradas (conexões)
    ("POST", "/api/conexoes"): ["conexoes/criar"],
    ("PATCH", "/api/conexoes/{id}"): ["conexoes/editar"],
    ("DELETE", "/api/conexoes/{id}"): ["conexoes/apagar"],
    ("POST", "/api/conexoes/{id}/testar"): ["conexoes/testar"],
    ("POST", "/api/conexoes/{id}/publicar"): ["conexoes/publicar_camada"],
    # ---- L4-18-rede-simples: eventos registrados pelas rotas (vocabulário em db/migracoes da rede)
    ("POST", "/api/rede/simples"): ["redes/simples_criar"],
    ("POST", "/api/rede/{rede_id}/promover"): ["redes/simples_promover"],
    # ---- motor multicritério em grades aninhadas (L3-19-multiescala; vocabulário nas migrações
    # 20260906T1640_multiescala.sql e 20260906T1823_multiescala_apagar.sql). Conjunto, fator e execução são
    # tabelas do inquilino com dono humano, então toda escrita narra evento; o DELETE apaga em cascata e por
    # isso tem tipo próprio (`_apagar`), separado do de criação.
    # ---- fronteira de Pareto (L3-08-pareto): as duas rotas são LEITURA; usam POST só porque a lista de
    # objetivos não cabe em query string. Não escrevem nada, logo não há evento de domínio a registrar.
    ("POST", "/api/amc/pareto"): [],
    ("POST", "/api/amc/pareto/camada"): [],
    ("POST", "/api/multiescala/conjuntos"): ["multiescala/conjunto"],
    ("DELETE", "/api/multiescala/conjuntos/{id}"): ["multiescala/conjunto_apagar"],
    ("POST", "/api/multiescala/fatores"): ["multiescala/fator"],
    ("DELETE", "/api/multiescala/fatores/{id}"): ["multiescala/fator_apagar"],
    ("POST", "/api/multiescala/fatores/{id}/amostras"): ["multiescala/amostras"],
    ("POST", "/api/multiescala/conjuntos/{id}/macro"): ["multiescala/macro"],
    ("POST", "/api/multiescala/execucoes/{id}/micro"): ["multiescala/micro"],
    # ---- edição transacional de feições (L2-03-a): um evento por LOTE (nunca um por feição), com a contagem
    # de adicionadas/atualizadas/apagadas em propriedades — mesmo em modo `parcial` com tudo recusado
    ("POST", "/api/camadas/{id}/edicoes"): ["camadas/editar"],
    # --- construtor de camada por esquema (L5-31) e vista de camada (L5-32)
    ("POST", "/api/camadas/esquema"): ["camadas/criar_esquema"],
    ("POST", "/api/camadas/{item_id}/esquema/plano"): [],  # só simula o plano; nada muda no banco
    ("PUT", "/api/camadas/{item_id}/esquema"): ["camadas/alterar_esquema"],
    ("POST", "/api/camadas/{camada_id}/vistas"): ["camadas/criar_vista"],
    ("PUT", "/api/vistas/{vista_id}"): ["camadas/alterar_vista"],
    # --- edição de feição por caminhos próprios (L2-03) — todos passam pela porta única de escrita
    ("POST", "/api/camadas/{id}/feicoes/unir"): ["camadas/unir"],
    ("POST", "/api/camadas/{id}/feicoes/dividir"): ["camadas/dividir"],
    ("POST", "/api/camadas/{id}/feicoes/{globalid}/historico/{historico_id}/restaurar"): ["camadas/restaurar"],
    ("POST", "/api/camadas/{id}/feicoes/{globalid}/anexos"): ["camadas/anexo_enviar"],
    ("DELETE", "/api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}"): ["camadas/anexo_apagar"],
    # --- escrita compatível Esri (L2-04-d): tudo desemboca em aplicar_edicoes, que grava camadas/editar
    ("POST", "/rest/services/{item_id}/FeatureServer/applyEdits"): ["camadas/editar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/applyEdits"): ["camadas/editar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/addFeatures"): ["camadas/editar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/updateFeatures"): ["camadas/editar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/deleteFeatures"): ["camadas/editar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/calculate"): ["camadas/editar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/{object_id}/addAttachment"):
        ["camadas/anexo_enviar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/{object_id}/updateAttachment"):
        ["camadas/anexo_enviar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/{object_id}/deleteAttachments"):
        ["camadas/anexo_apagar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/uploads/upload"): ["camadas/upload_esri"],
    # leituras que o protocolo Esri manda por POST (o corpo é o pedido, nada muda no banco)
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/query"): [],
    ("POST", "/rest/services/{item_id}/FeatureServer/{camada_id}/queryAttachments"): [],
    ("POST", "/svc/{token}/rest/info"): [],  # ficha do servidor; sem credencial e sem efeito
    ("POST", "/svc/{token}/rest/generateToken"): [],  # a emissão já é registrada pelo caminho de token
    # L5-36: instalar/desinstalar widget externo é configuração da organização — ambos narrados
    ("POST", "/api/widgets/externos"): ["widgets/instalar"],
    ("DELETE", "/api/widgets/externos/{nome}"): ["widgets/desinstalar"],
    # L2-13-b: criar registra a réplica (o pacote em si é job), sincronizar registra o lote,
    # apagar registra a remoção. Baixar o pacote é leitura: sem evento de domínio (o log de acesso cobre).
    ("POST", "/api/replicas"): ["replicas/criar"],
    ("POST", "/api/replicas/{id}/sincronizar"): ["replicas/sincronizar"],
    ("DELETE", "/api/replicas/{id}"): ["replicas/apagar"],
    # L2-04-k: as rotas Esri são a MESMA fachada — o evento é o do mecanismo de réplica da casa.
    # extractChanges é leitura de janela, não conta como sincronização: sem evento de domínio.
    ("POST", "/rest/services/{item_id}/FeatureServer/createReplica"): ["replicas/criar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/synchronizeReplica"): ["replicas/sincronizar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/unRegisterReplica"): ["replicas/apagar"],
    ("POST", "/rest/services/{item_id}/FeatureServer/extractChanges"): [],
    # --- clonagem de camadas hospedadas (L2-08-b)
    ("POST", "/api/migracao/clones"): ["migracao/clonar"],
    ("DELETE", "/api/migracao/clones/{id}"): ["migracao/clone_apagar"],
    # ---- análise 3D (L2-09-d; vocabulário na migração 20260908T1703_analise3d.sql): toda rota registra o
    # evento analise3d/<analise>; com salvar_item o item é criado pela rota do catálogo, que registra o SEU
    # itens/adicionar além deste
    ("POST", "/api/analise3d/visada"): ["analise3d/visada"],
    ("POST", "/api/analise3d/viewshed"): ["analise3d/viewshed"],
    ("POST", "/api/analise3d/perfil"): ["analise3d/perfil"],
    ("POST", "/api/analise3d/sombra"): ["analise3d/sombra"],
    ("POST", "/api/camadas/{id}/lote"): ["camadas/lote"],  # L2-03-f: síncrono e job registram o mesmo evento
    # L2-03-edicao (histórico/restauração, anexos, unir/dividir)
    ("POST", "/api/camadas/{id}/feicoes/{globalid}/historico/{historico_id}/restaurar"): ["camadas/restaurar"],
    ("POST", "/api/camadas/{id}/feicoes/{globalid}/anexos"): ["camadas/anexo_enviar"],
    ("DELETE", "/api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}"): ["camadas/anexo_apagar"],
    ("POST", "/api/camadas/{id}/feicoes/unir"): ["camadas/unir"],
    ("POST", "/api/camadas/{id}/feicoes/dividir"): ["camadas/dividir"],
    # ---- importação de arquivo vetorial
    ("POST", "/api/importacoes"): ["importacoes/criar"],
    ("PUT", "/api/importacoes/{id}/confirmar"): ["importacoes/confirmar"],
    ("DELETE", "/api/importacoes/{id}"): ["importacoes/apagar"],
}

# Verbo de escrita que NÃO altera estado. Cada motivo é conferido por test_eventos.py (tamanho mínimo, sem
# repetição na outra lista, e o módulo da rota não pode chamar registrar_evento). Esta lista é curta de
# propósito: crescer aqui é a forma mais fácil de reabrir o buraco do G4-03.
ROTAS_SEM_EVENTO: dict[tuple[str, str], str] = {
    ("POST", "/api/rota"):
        "cálculo de rota sobre dado aberto (OSM) pelo OSRM: nenhuma escrita em plat.*, nenhum objeto criado; "
        "o uso fica em plat.log_acesso (rota, ip, tempo, token_id)",
    ("POST", "/api/matriz"):
        "matriz de distância pelo OSRM: mesmo caso do POST /api/rota, cálculo sem escrita",
    ("POST", "/api/isocrona"):
        "isócrona pelo OSRM: mesmo caso do POST /api/rota, cálculo sem escrita",
    ("POST", "/api/geocodificar"):
        "consulta ao gazetteer: leitura pura, é POST só porque o pedido é um corpo JSON grande demais para a "
        "linha de consulta; o uso fica em plat.log_acesso",
    ("POST", "/api/reverso"):
        "geocodificação reversa: leitura pura, mesmo caso do POST /api/geocodificar",
    ("POST", "/rest/services/Geocodificador/GeocodeServer"):
        "descritor do serviço no protocolo Esri: o mesmo documento do GET, que o cliente ArcGIS também pede "
        "por POST; nenhuma escrita",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates"):
        "busca de endereço no protocolo Esri: leitura pura, o cliente ArcGIS usa GET ou POST conforme o "
        "tamanho do pedido",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/reverseGeocode"):
        "geocodificação reversa no protocolo Esri: leitura pura, mesmo caso de findAddressCandidates",
    ("POST", "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses"):
        "geocodificação em lote no protocolo Esri: leitura pura, só existe como POST porque o lote vai no corpo",
    ("PUT", "/api/uploads/{id}/partes/{n}"):
        "uma parte de um envio retomável: o envio inteiro já é narrado por uploads/iniciar, uploads/concluir e "
        "uploads/abortar; um evento por parte encheria a auditoria de ruído (um arquivo de 1 GiB são 128 partes)",
}
