# Chamados de suporte dentro do produto (item L7-13-a-chamados)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L7_CONCEITO.md` (decisões sobre o laço agêntico);
ADR `20260907T1355-paginas-e-layout-do-app.md` (páginas/layout); ADR 0002 seção 5.3 (CSRF sob cookie) e
ADR 0005 (objeto no Garage).

## Contexto

O produto não tinha porta de entrada para o cliente pedir socorro: o reporte vivia fora do produto
(e-mail/WhatsApp), sem captura de tela, sem contexto técnico e sem rastro auditável. O item pede o fluxo
inteiro: abrir chamado com captura automática, operador responde, cliente vê e fecha; anexo malicioso
recusado; e-mail de notificação nos 3 idiomas (SMTP de captura nos testes); tempo de primeira resposta
medido e exibido; chamado de outro inquilino invisível. O painel do operador é a porta do laço agêntico
(L7-13-c) — quem responde hoje é gente; amanhã pode ser agente, pela mesma fila.

## Decisão

1. **RLS em toda a pilha do cliente; o operador passa por cima com identidade provada DENTRO da função.**
   `plat.chamado`, `plat.chamado_comentario` e `plat.chamado_anexo` têm `tenant_id` com RLS
   (`tenant_id = plat.tenant_atual()`). As funções do painel (`plat.chamado_fila_operador`,
   `chamado_operador_ver`, `_comentarios`, `_anexos`, `_estado`) são `SECURITY DEFINER` e provam o
   superadmin pelo hash da sessão (`plat.plataforma_operador(p_sessao_hash)`, padrão da migração 003),
   nunca por GUC — a fila cruza inquilinos por construção, e a rota devolve 404 (nunca 403) a quem não é
   superadmin, para não confirmar que o caminho existe.

2. **Captura e anexos entram por base64-sob-JSON no MESMO corpo da escrita.** O CSRF sob cookie de sessão
   exige `application/json` em todo verbo de escrita (ADR 0002 seção 5.3); multipart ficaria de fora dessa
   proteção. A captura é um data URL de PNG, re-codificada pelo Pillow no servidor (mesma defesa do
   logotipo/miniatura: a saída é PNG novo, sem EXIF/ICC). Tetos por instalação em `app/limites.py`
   (`CHAMADO_*`); o que passa do teto é recusado com 413, nunca cortado em silêncio.

3. **A chave do objeto no Garage NUNCA sai do banco.** O download só existe pela rota da API
   (`GET /api/chamados/{id}/anexos/{anexo_id}` e a gêmea do operador), com sessão e RLS. A refutação do
   item ("ler anexo de chamado alheio pela URL do objeto") não tem URL para advinhar: a chave é
   `{slug}/chamado_anexo/{sha256}.{ext}` e é resolvida por `plat.arquivo_bucket_resolver` só dentro do
   servidor. Teste cruzado com dois inquilinos temporários prova 404 nas quatro tentativas (ler chamado,
   ler anexo, comentar, fechar).

4. **Anexo passa por duas provas, e a segunda lê o objeto de VOLTA do Garage — por isso acontece FORA da
   transação.** A primeira prova (`app/varredura_conteudo.py::escanear_cabecalho`) roda sobre os bytes em
   memória antes de gravar (executável MZ declarado geojson → 415 `conteudo_recusado`). A segunda
   (`app/uploads/tipos.py::verificar_conteudo`) lê o objeto gravado por OUTRA conexão; como
   `objetos.guardar` cria o bucket dentro da transação da requisição, essa leitura só enxerga o bucket
   DEPOIS do commit — rodar a prova dentro da transação dava `FileNotFoundError` disfarçado de 500
   (medido nesta rodada). Ordem final: transação grava objeto + linha; prova fora da transação; recusa
   apaga a linha e o objeto e responde 422 `conteudo_nao_corresponde`; o evento de auditoria só é
   registrado depois da prova passar (nunca há evento de anexo que foi recusado).

5. **Captura de tela é nativa, sem biblioteca e sem serviço de terceiros.** `web/js/mapa/mapa.js` registra
   `window.platMapa`; `reportar.js` captura `getCanvas().toDataURL()` DENTRO de um evento `render`
   (fora dele o framebuffer já foi composto e limpo — restrição conhecida do MapLibre, medida na suíte do
   L2-01-a). Tela sem mapa não inventa captura: vai sem, e a estrutura do DOM (tag + texto curto de
   títulos/botões, NUNCA valor de campo) segue como contexto.

6. **Contexto automático é sanitizado no servidor, não confiado do navegador.** `contexto_limpo` corta
   campos conhecidos por teto, filtra `req_ids` pelo formato real (16 hex, `app/log.py::req_id`, máximo 20)
   e reduz o DOM a estrutura; o teto global (`CHAMADO_CONTEXTO_BYTES_MAX`) descarta a parte maior primeiro
   (dom → req_ids) e preserva tela/versão/idioma por último. O anel das últimas 20 requisições mora em
   `web/js/base/api.js` (uma função por página importa de lá), alimentado por todo `X-Req-Id` de resposta.

7. **SLA de primeira resposta: prazo DECLARADO por severidade junto do tempo MEDIDO em toda leitura.**
   `CHAMADO_SLA_PRIMEIRA_RESPOSTA_HORAS` (4/8/24/72 h) é hipótese declarada em `app/limites.py`; L7-22-sla
   (pendente) é quem move estes números para dado medido em tabela. `primeira_resposta_em` grava na PRIMEIRA
   resposta do operador e nunca mais muda; a lista exibe "respondeu em N h" com a etiqueta
   "dentro do prazo"/"fora do prazo" — o número sozinho não diz se está dentro ou fora.

8. **Estados com mapa de transição explícito, fechado é terminal.** `TRANSICOES` (rotas) é a única fonte:
   aberto → em análise/aguardando cliente/resolvido; resolvido → fechado ou de volta para em análise
   (reabertura); nenhum estado volta a "aberto". O cliente tem rota própria de fechar (idempotente, sempre
   permitida); chamado fechado recusa comentário de cliente E de operador com 409 `chamado_fechado`. O
   espelho do mapa no JS do painel é só para montar o seletor — o servidor valida de novo.

9. **E-mail só no sentido suporte → cliente; a volta é pelo produto.** `app/chamados/correio.py` monta
   assunto+texto em pt-BR/en/es (idioma preferido da CONTA do cliente), segue a regra de escrita de 03/09
   (sem exclamação, sem travessão interno, nada de "você recebe" — testado unidade a unidade), nunca põe
   texto do cliente no assunto e só enfileira o job quando a conta tem e-mail. Quem não tem e-mail é
   coberto pelo banner dentro do produto, que zera quando o cliente abre o chamado (`visto_cliente_em`).

10. **Rotas fixas antes de rotas com `{id}`**: `/api/chamados/banner` é declarada antes de
    `/api/chamados/{id}` — FastAPI casa na ordem de declaração e "banner" seria capturado como id
    (medido nesta rodada: 404 `chamado_inexistente` no banner até a reordenação). Os 6 tipos de evento
    (`chamado/*`) entram em `plat.evento_tipo` na migração, antes do primeiro uso — a FK do
    `plat.evento` reprova o primeiro chamado caso contrário (medido nesta rodada).

## Consequências

- O painel do operador é a interface estável do L7-13-c: um agente que responde chamados entra pela mesma
  fila e pelas mesmas funções SECURITY DEFINER, com identidade própria em `plat.operador_sessao`.
- O SLA declarado é hipótese visível e editável em um lugar (`app/limites.py`); L7-22 decide se vira dado.
- Anexo grande (vídeo, base de pontos) não é caso deste item: acima de 8 MiB a resposta orienta o upload
  retomável do L0-04-a; colar os dois fluxos é trabalho do L7-03-a quando o antivírus entrar.
- Front i18n é só pt-BR neste item (o dicionário `en`/`es` do front é a L7-10); os 3 idiomas do portão
  estão no CORREIO, que é backend e testado nos 3.
