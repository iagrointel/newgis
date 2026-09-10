# Ciclo de vida do item de imagem: lixeira com retenção, expurgo pelo catálogo e coleta de lixo que lista, não apaga

- Estado: aceito
- Data: 2026-09-08
- Item: L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo

## Contexto

O item de imagem até aqui tinha só nascimento (L1-01-a a L1-01-h): coleção STAC, COG em dois perfis,
espelho `plat.raster_item` e tiles. O portão deste item pede o fim da linha: excluir pelo navegador com o
tile respondendo 404 em <= 5 s, o STAC deixando de listar, restauração dentro de uma retenção de 7 dias,
objetos saindo do balde depois dela, expurgo pelo catálogo, coleta de lixo com relatório de órfãos e
quebrados visível em Tarefas, e a cota do inquilino recalculada pelo próprio Garage. A refutação exige
três itens, apagar dois e provar que o terceiro fica intacto — e que o COG excluído não volta pela URL
antiga, nem da fatia em cache do nginx.

## Decisões

1. **Excluir é sair do STAC na hora, não apagar objeto.** A rota DELETE do catálogo já marca
   `apagado_em` (a RLS esconde o item e os tiles respondem 404 imediatamente — medido 0,016 s). Na MESMA
   transação, `ciclo_vida.ao_ir_para_lixeira` guarda o corpo STAC inteiro na coluna nova
   `plat.raster_item.stac` (migração 20260908T1911), muda o espelho para `estado='excluido'` com
   `excluido_em`, remove o item do pgstac (`pgstac.delete_item`) e enfileira o job
   `imagens.raster_apagar_objetos` com `agendado_para = agora + 7 dias` (`limites.RASTER_LIXEIRA_DIAS`).
   A busca deixa de listar o item no mesmo commit em que o item do catálogo sai.

2. **Restaurar dentro da retenção devolve TUDO porque o objeto nunca saiu.** `ao_restaurar` devolve o
   corpo STAC guardado ao pgstac e volta o espelho a 'ativo'; os objetos do balde não foram tocados. Fora
   da retenção a rota recusa com 409 `objetos_ja_apagados` — `checar_restauravel` confere o COG visual
   pelo HEAD do balde antes de deixar restaurar, porque devolver um item sem dado é pior que recusar. A
   conferência usa `objetos_raster.existe` (a chave de imagem casa com o padrão de imagem; o padrão
   genérico de `objetos.existe` diria False sempre).

3. **O apagamento de objetos é um job SEPARADO e defensivo.** `apagar_objetos` confere de novo o estado do
   espelho: se o item voltou a 'ativo' (restauração dentro da retenção) antes do job rodar, NADA é apagado
   e o resultado registra `pulado`. Idempotente: segunda execução devolve zeros.

4. **`pgstac.delete_item` depende do search_path; os outros não.** `get_item`/`create_item`/`create_collection`
   trazem `SET SEARCH PATH` na própria definição; `delete_item` resolve `items` SEM qualificar. Nova função
   `imagens.pgstac.item_apagar` troca o search_path com `SET LOCAL` (mesmo contrato de `_entrar_no_pgstac`)
   e devolve o anterior com identificadores psycopg2 — quem chama segue no banco do app, na mesma
   transação.

5. **Expurgo = destruidor do tipo 'raster' do catálogo.** `catalogo.destruidores` ganha a entrada `raster`:
   `ciclo_vida.expurgar` apaga os objetos (`objetos_raster.apagar_item`, com `plat.arquivo` marcado
   `apagado_em`), o item STAC que por ventura tenha ficado e a linha do espelho, e devolve os bytes
   liberados para o evento `lixeira/expurgar`. O "apagar agora" da lixeira (POST /api/lixeira/{id}/expurgar)
   e o periódico diário passam pelo mesmo corpo.

6. **Coleta de lixo LISTA e RELATA; apagar órfão é decisão humana.** O job `imagens.raster_gc` (somente
   sistema, periódico de domingo 05:00 no inquilino `plataforma`, app/imagens/periodicos.py somado à lista
   do L0-05 sem editar arquivo alheio) e o CLI `plat raster gc` produzem o mesmo relatório: órfãos (chave
   na forma de imagem sem linha no espelho), quebrados (ativo sem STAC ou sem o COG visual) e lixeira
   vencida. Nenhuma exclusão automática de órfão.

7. **A CLI conclui o relatório em Tarefas sem worker: `plat.job_registrar_concluido` (migração 1932).** O
   gatilho `plat.job_transicao` não aceita job nascendo 'concluido' nem transição fora do GUC
   `plat.via_worker`, e `via_worker_ligar` só é executável pela role worker. A função nova (SECURITY
   DEFINER, revogada para PUBLIC) faz o caminho honesto pela máquina de estados: nasce pendente por
   `jobs.sistema.enfileirar` (mesma cota diária e teto de pendentes), vira 'rodando' SE ainda estiver
   pendente (rowcount 0 → devolve false, um worker de verdade pegou) e termina por `plat.job_terminar`,
   com os mesmos disparos de notificação. A enumeração de inquilinos da CLI passa pela leitura
   SECURITY DEFINER `plat.tenants_para_manutencao()` — `plat.tenant` é vazia para o app fora de sessão de
   inquilino (RLS), e a função expõe só `id` e `slug`, nunca cota ou configuração.

8. **A subrequisição do nginx nega item excluído mesmo com o objeto no balde.** Migração 1911 adiciona
   `plat.raster_item_estado_por_item(slug, item_id)` (SECURITY DEFINER, uma linha, revogada para PUBLIC) e
   `rotas_arquivos.cog_autorizar` recusa estado 'excluido' com 403 — é isto que barra a fatia em cache do
   nginx sem PURGE: dentro da retenção a negação é de aplicação; depois dela o objeto já não existe e o
   nginx responde 404 por ausência.

9. **A cota do inquilino é recalculada pelo Garage, não por soma nossa.** A prova da cláusula compara o
   GetBucketInfo do balde antes e depois do apagamento (bytes e contagem de objetos caem exatamente o que
   o item tinha) com `objetos.uso_detalhado` — o acervo de contabilidade nunca diverge do armazém.

## Consequências

- O corpo STAC guardado na lixeira é o único custo novo por item excluído (um JSON); ele se paga na
  restauração, que não depende de reingestão.
- Órfãos de verdade ficam no relatório à espera de decisão — a rodada inicial de gc numa base com histórico
  de testes lista, e não apaga.
- `imagens.raster_apagar_objetos` é `somente_sistema` com chave por item: exclusão repetida não duplica job.
- O período de retenção é uma constante do código (`limites.RASTER_LIXEIRA_DIAS = 7`); torná-lo configurável
  por inquilino é trabalho de item de configuração, não deste.
