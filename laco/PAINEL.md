# Painel do laço PLATAFORMA ENTERPRISE

Gerado por `laco/gera_painel.py` de `laco/estado.json` em 2026-09-17 22:34 UTC. Não editar à mão: rode o script.

- Estado do laço: **ATIVO** · turno 9 · autoturno True
- Produto: codinome `plat` · nome público: PENDENTE (D18 do dono)
- URL interna: https://plat.iagrointel.com (noindex; nunca linkar de lugar público)
- Repositório: `/home/dev/plataforma/enterprise` · schema `plat` · role `plat_app` · portas 8150-8159 (api 8150, martin 8151, titiler 8152, worker 8153)
- Veredito do turno 9: pendente (gerente ainda não escreveu `99_veredito.md`); handoffs presentes: ADVXPASS-CONSERTO.md, CATALOGO-CONSERTO.md, ESTABILIZACAO.md, F2FIXCONEXOES2.md, F2FIXFILATESTE.md, FASE1.md, G7-afinidade-executor-CONSERTO.md, INGESTAO-CONSERTO.md, L2-03-b-CONSERTO.md, L2-13-b-L2-04-d-CONSERTO.md, L7-03-autenticar-CONSERTO.md, L7-31_garage_chave_propria.patch, UNIT2-CONSERTO.md, f2fixapi2-LAUDO.md, linha-L0-laudo-adversario-1.md, linha-L0-laudo-adversario-2.md, linha-L1-CONSERTO-href.md, linha-L1-CONSERTO-imagens.md, linha-L1-laudo-adversario-1.md, linha-L1-laudo-adversario-2.md, linha-L2-laudo-adversario-1.md, linha-L2-laudo-adversario-2.md, linha-L2-laudo-adversario-3.md, linha-L3-CONSERTO.md, linha-L3-laudo-adversario.md, linha-L4-CONSERTO.md, linha-L4-laudo-adversario-1.md, linha-L4-laudo-adversario-2.md, linha-L5-laudo-adversario-1.md, linha-L5-laudo-adversario-2.md, linha-L6-laudo-adversario.md, linha-L7-laudo-adversario-1.md, linha-L7-laudo-adversario-2.md

## Placar

Contagem por estado dos itens do backlog (lida do `estado.json`):

| estado | itens |
|---|---|
| entregue | 54 |
| parcial | 154 |
| tentando | 2 |
| refutado | 124 |
| pendente | 220 |
| **total** | **554** |

Placar registrado no estado (`placar`, atualizado pelo gerente no fim do turno): provados 18, entregues_sem_sha 36, promovidos_em_massa 0, entregues 54, parciais 154, refutados 124, tentando 2, pendentes 220, total 554, turnos 9.

Por linha:

| linha | itens | entregue | parcial | tentando | refutado | pendente |
|---|---|---|---|---|---|---|
| L0 fundação | 75 | 23 | 27 | 1 | 12 | 12 |
| L1 imagens | 66 | 4 | 3 | 0 | 10 | 49 |
| L2 plataforma | 126 | 7 | 71 | 0 | 22 | 26 |
| L3 motor AMC | 37 | 8 | 13 | 0 | 5 | 11 |
| L4 rede de utilidades | 73 | 1 | 9 | 1 | 29 | 33 |
| L5 builder | 63 | 6 | 12 | 0 | 6 | 39 |
| L6 conectores | 32 | 4 | 11 | 0 | 13 | 4 |
| L7 operação | 82 | 1 | 8 | 0 | 27 | 46 |

## O que o produto faz hoje

### L0-01-repo (entregue)

- Instala-se com um comando (`sudo bash install.sh <dominio> [porta]`): extensões, migrações, .env, senha da role, linha no pg_hba.conf, venv, administradores de demonstração, unidade systemd, nginx, certbot, conferência pública.
- Responde `GET /saude` por HTTPS com versão, commit, ambiente, estado do banco, migrações aplicadas/pendentes e sondas de martin/titiler/garage; 200 só com banco atualizado, 503 caso contrário.
- Responde `GET /api/versao` sem tocar o banco e mostra versão e saúde numa página inicial (única tela).
- Aplica migrações SQL idempotentes com sha256 por arquivo e recusa arquivo aplicado que tenha mudado.
- Isola inquilinos no banco: RLS em toda tabela com tenant_id; `plat_app` sem contexto vê 0 linhas; INSERT cruzado é recusado.
- Marca toda resposta com `X-Robots-Tag: noindex, nofollow` e escreve log JSON por requisição no journal.
- Roda `make check` (ruff, varredura de marcador de pendência, testes rápidos, e2e playwright com captura).

### L0-02-tenant-auth (parcial)

- Entra por `/entrar?inquilino=<slug>` com senha (política por inquilino, bloqueio 5 falhas/15 min por usuário e 10 r/min por IP no nginx, tempo constante para usuário inexistente) e, quando ligado, segundo fator TOTP com 8 códigos de recuperação e anti-replay; sai por `POST /api/logout`.
- Mantém sessão por cookie `plat_sessao` (HttpOnly, Secure, SameSite=Lax) com só o hash no banco, 12 h ociosa e 7 d no máximo por padrão; lista e encerra sessões em Minha conta; troca de senha derruba as outras.
- Administra usuários do inquilino na tela Usuários (criar com senha temporária, editar, desabilitar, redefinir senha, desligar 2FA, desbloquear, lote de 100; o último administrador não se apaga), grupos (dono/gerente/membro, convite, pedido, entrada livre) e papéis personalizados sobre 46 privilégios com teto por perfil.
- Emite tokens de serviço `plat_…` com escopo, restrição de origem e IP, validade até 365 d, rotação com 24 h de sobreposição e revogação imediata; cada uso do token fica no log de acesso com IP, rota e bytes.
- Grava `plat.log_acesso` por requisição autenticada (particionado por mês) e eventos de domínio em `plat.evento`; tela Log com filtros, CSV e aba Eventos.
- Isola inquilinos em toda rota: varredura A→B gerada do OpenAPI (74 rotas, 4 vetores, digest de B) na suíte e 73 rotas vivas com 411 chamadas e 0 acesso cruzado pelo testador; adversário PASSA em 2 rodadas.
- Superadmin só no inquilino técnico `plataforma` (2FA obrigatório), resolvido por hash de sessão; API para listar, criar, suspender, reativar e apagar inquilinos; leitura de outro inquilino só com `X-Plat-Inquilino` e evento.

### L0-03-catalogo (entregue)

- Catálogo de conteúdo completo: itens tipados por JSON Schema, pastas, tags, categorias ISO, busca com pesos e sintaxe por campo, compartilhamento em 5 níveis com link revogável, dependências que bloqueiam exclusão, proteção, lixeira de 30 dias com expurgo, versões imutáveis com sha256, transferência de dono.
- 612 testes, 10 defeitos reais corrigidos (2 de privacidade: link anônimo não entrega identidade, miniatura confere acesso antes do formato); adversário PASSA; busca de item por tipo em 21,8 ms (era 194,7 ms).

### L0-04-ingest-vetor (parcial)

- Sobe Shapefile (zip)/GeoPackage/GeoJSON/CSV(lat,lon): inspeciona (CRS, campos, geometria), o usuário confirma o mapeamento, e o arquivo vira tabela própria (`d_<inquilino>.c_<id>`) com RLS obrigatória e um item no catálogo.
- Recusa com mensagem exata shapefile sem `.prj`; corrige geometria autointersectada e conta quantas; CSV com vírgula decimal é lido certo.
- Formatos ainda fora desta fatia: KML/GPX/XLSX, DXF/DWG, FileGDB/GeoParquet — ver `laco/PAINEL.md` para a lista completa.

### L0-05-jobs (parcial)

- Enfileira trabalhos em `plat.job` (RLS por inquilino) e os executa na unidade `plat-worker`, um processo filho por job com limite de memória (`RLIMIT_DATA`), timeout, retentativa 2/4/8 s e 1 job pesado por vez.
- Mostra progresso em tempo real na tela Tarefas por SSE (primeiro evento em 0,022 s pela URL pública), com log ao vivo, cancelar (0,426 s cooperativo; SIGTERM 30 s + SIGKILL 10 s para tarefa que ignora), repetir e CSV.
- Sobrevive a reinício: `systemctl restart` ou `kill -9` no worker devolve o job a pendente com reinicios+1 e o retoma do zero (1,0 s); 5 devoluções sem terminar viram `falhou`; nunca `concluido` sem execução inteira.
- Só a role `plat_worker` muda estado de job (migração 006, achado do testador); `plat_app` cancela por `job_cancelar` e reporta por `job_progresso`; gatilho `job_transicao` recusa transição fora do worker.
- Agenda jobs por cron de 5 campos com fuso IANA (intervalo mínimo 15 min, 50 por inquilino, pausar/retomar/rodar agora, 5 falhas pausam); relógio no worker; periódico `jobs.expurgo` diário.
- Cláusula aberta (achado 2 do testador): worker homônimo fora do systemd devolve os jobs do worker vivo; o portão passa a exigir identidade única por processo e ceifa só por heartbeat vencido; correção (migrações 012 e 013) comitada em 9be9c6a, ainda sem veredito do testador e do adversário.

### L1-01-ingest-raster (entregue)

- O trabalho de fila `imagens.ingestar` converte o arquivo enviado em COG (GeoTIFF otimizado para nuvem) em dois perfis, visual e científico, com validação pelo rio-cogeo.
- O arquivo convertido sobe ao Garage com nome derivado do sha256 e nasce ao mesmo tempo como item STAC no pgstac, na coleção do inquilino, e como item do catálogo do tipo `raster`, com miniatura de 600 por 400 pixels e estatísticas.
- A gravação no catálogo é uma transação única: ou o item inteiro aparece, ou nada aparece; o tempo e a taxa de compressão de cada conversão ficam no resultado do trabalho.

### L2-01-mapa-web (entregue)

- Serve as camadas do inquilino como tiles vetoriais pelo Martin 1.15.0 (`plat-martin` em 127.0.0.1:8151), que publica só funções com RLS — a tabela da camada nunca é exposta.
- A tela `/mapa` lista camadas com ordem, opacidade, ligar e desligar, mostra legenda gerada da simbologia, abre janela de atributos, mede distância e área em geodésica, pesquisa endereço e coordenada, troca o mapa de fundo e imprime em PNG e PDF com escala e seta de norte.
- Medido com 1.000.000 de feições: 2,4 s do clique ao primeiro desenho, 1,5 s de zoom até o repouso e 61 MB de memória do navegador; 10 camadas ao mesmo tempo abrem em 4,3 s.

### L2-04-servicos-esri-ogc (parcial)

- Publica uma camada do catálogo em três protocolos de serviço ao mesmo tempo: diretório do FeatureServer no formato da Esri, OGC API Features Parte 1 (página inicial, conformidade, coleções, itens em GeoJSON) e WFS 2.0 por parâmetros de URL.
- Os três serviços são construídos em volta da mesma operação de consulta do item L2-04-c, sem um segundo gerador de SQL; 13 tentativas de injeção e de acesso a outro inquilino foram recusadas com 400 ou 404, nenhuma com erro 500.
- Falta a parte de escrita e de relacionamento: `applyEdits`, anexos e `queryRelatedRecords` dependem de itens ainda não construídos, e nenhum cliente de escritório real (QGIS, ArcGIS Pro, ArcGIS Online) foi testado contra o serviço nesta máquina.

### L2-07-campo (parcial)

- Guarda uma fila de trabalho de campo por inquilino: alvos que apontam uma feição do catálogo (camada e identificador global), roteiro pela ordem do vizinho mais próximo com refinamento 2-opt, registro de visita e foto.
- Seis tabelas com isolamento por inquilino (RLS), três telas e dois endereços GeoJSON (alvos e trajeto); o reenvio da mesma visita com o mesmo identificador do cliente não duplica, e a fila de um inquilino responde 404 para outro.
- Falta o centro do item: o construtor de formulário por arrasto que gera XLSForm e o aplicativo instalável no celular com coleta fora de rede; o que existe hoje é uma fila de escrita no navegador (localStorage) com chave de idempotência, sem instalação.

### L2-08-migracao-agol (parcial)

- Guarda a credencial de uma conta ArcGIS Online por inquilino, cifrada em AES-GCM no registro do inquilino, e publica camadas nessa conta pela tarefa de fila `agol.publicar`, com progresso, log e estado por camada em `plat.agol_publicacao`.
- O caminho de rede foi provado contra o portal real com credencial inválida: a tarefa devolve erro HTTP 403 em cerca de 2 segundos e marca o estado como erro, sem alegar publicação.
- Falta para ficar completo: uma credencial de conta real, que depende de decisão do dono, e o item agregado de mapa web combinando várias camadas.

### L2-09-3d (parcial)

- Converte modelo IFC (formato de projeto de edificação) em `.xkt` por tarefa de fila `modelo3d.converter` (16,8 s medidos de ponta a ponta) e abre o modelo na página `/modelo/{item}`, com os tipos de item `modelo3d` e `foto360` no catálogo.
- Falta para o item ficar completo: 3D dentro do mapa (hoje é página própria), miniatura do modelo e a decisão de licença do visualizador, que é AGPL-3.0 e está fora da lista aprovada no ADR 0001.

### L6-02-conectores-vivos (parcial)

- Cadastra uma camada externa por endereço de URL: o cadastro descobre sozinho o tipo de serviço (WMS, WMTS, WFS, OGC API, ArcGIS REST), lê nome, título, sistema de coordenadas e extensão, e grava a camada em `plat.conexao_camada` com isolamento por inquilino.
- Serve os ladrilhos de imagem do serviço externo por um intermediário próprio, provado ao vivo contra um serviço público de dado aberto: 8 camadas descobertas e ladrilhos de 82 a 730 KB entregues.
- A camada descoberta ainda não é desenhada no mapa do produto, porque a ligação com o visualizador não foi feita; apenas dois serviços públicos foram usados na prova ao vivo.

### L0-09-metadado-catalogo (refutado)

- Metadado ISO 19139 por item, validado offline contra o XSD oficial (sem tocar a rede); descoberta por OGC API Records, sempre autenticado por token com escopo.

### L0-02-a-login-sessao (entregue)

- Cláusulas cobertas pela identidade já entregue (`L0-02-tenant-auth`): cookie de sessão correto, expiração de 12 h/7 d e sessão nunca aparece em log.

### L0-02-b-politica-senha-bloqueio (entregue)

- Política de senha (mínimo/composição/histórico) e bloqueio de 5 falhas/15 min com desbloqueio pelo admin, provados de novo com evidência fresca.

### L0-02-c-2fa-totp (entregue)

- 2FA por TOTP com QR, replay recusado, código de recuperação de uso único, admin pode exigir 2FA por inquilino; segredo provado cifrado no banco por consulta direta (não só no cifrador).

### L0-02-d-token-servico (entregue)

- Token de serviço com escopo, restrição de IP/Referer com curinga, expiração até 365 d, revogação em ≤ 1 s, cada uso no log de acesso.

### L0-02-e-varredura-cruzada-rls (parcial)

- Varredura cruzada A→B cobre as 138 rotas do OpenAPI vivo (100%), gerada automaticamente — cresce sozinha quando uma rota nova nasce.

### L0-02-f-tela-usuarios (entregue)

- Tela Usuários completa (criar/editar/desabilitar/2FA/desbloquear/lote/perfil); dois defeitos reais achados e fechados: apagar usuário com item do catálogo caía em erro genérico (agora 409 nomeado com a lista) e um admin restrito podia forjar admin pleno atribuindo papel a outro usuário (agora exige o mesmo privilégio que está concedendo).

### L0-02-g-perfil-usuario (entregue)

- Perfil próprio do usuário: idioma, unidades, formato de data, visibilidade e foto (recorte 200x200, SVG recusado antes de qualquer gravação, limite de 1 MiB) — mesma whitelist contra escalada que já protegia nome/e-mail.

### L0-03-a-modelo-item (entregue)

- Item genérico do catálogo (`plat.item`/`plat.tipo_item`): uuid opaco e estável mesmo em PUT ou troca de pasta, RLS por inquilino, dado validado por JSON Schema por tipo com erro 422 nomeando o campo — auditado de novo cláusula a cláusula, listagem por tipo em 50,8 ms p95 com 10 mil itens.

### L0-03-b-pastas-tags-categorias-classificacao (entregue)

- Pastas, tags e categorias ISO 19115 na tela Conteúdo, com facetas que se contam sozinhas.

### L0-03-c-busca (entregue)

- Busca com pesos (título exato antes do rank) e sintaxe por campo.

### L0-03-d-grupos (entregue)

- Grupos do L0-02 (dono/gerente/membro) aplicados ao compartilhamento de itens do catálogo.

### L0-03-e-compartilhamento (pendente; código no repositório, item devolvido pelo driver (veredito do gerente pendente))

- Compartilhamento em 5 níveis com link por token; revogação nega acesso em 30 ms.

### L0-03-f-tela-conteudo (refutado)

- Tela Conteúdo (lista/grade), 0 erro de console, primeira pintura 24 ms.

### L0-03-g-detalhe-item-miniatura (entregue)

- Detalhe do item com miniatura — acesso conferido antes de responder o formato.

### L0-03-h-lixeira-protecao-status (pendente; código no repositório, item devolvido pelo driver (veredito do gerente pendente))

- Lixeira de 30 dias, proteção e status; exclusão de item protegido ou com dependente é recusada (409).

### L0-03-i-dependencias (entregue)

- Dependência entre itens bloqueia exclusão até ser desfeita.

### L0-03-j-transferencia-dono (pendente; código no repositório, item devolvido pelo driver (veredito do gerente pendente))

- Transferência de dono, inclusive apagar o usuário de origem depois de transferir tudo.

### L0-03-k-favoritos-notificacoes (refutado)

- Favoritos no item; notificações ainda não construídas.

### L0-03-l-versoes-item (pendente; código no repositório, item devolvido pelo driver (veredito do gerente pendente))

- Versões de item imutáveis por sha256 — gravar por SQL direto é negado (permission denied).

### L0-04-b-inspecao (parcial)

- Job de inspeção do arquivo enviado: formato, CRS, campos, contagem, tipo de geometria — antes de qualquer confirmação do usuário.

### L0-04-c-tabela-camada (parcial)

- Tabela própria por camada (`d_<inquilino>.c_<id>`) com RLS obrigatória, geometria tipada e SRID.

### L0-04-d-formatos-base (parcial)

- 4 formatos de entrada nesta fatia: Shapefile (zip), GeoPackage, GeoJSON, CSV com latitude/longitude.

### L0-04-e-formatos-cad (entregue)

- Importa desenho CAD de terceiro nos formatos DXF e DWG: a contagem de entidades por camada bate com a do `ogrinfo` nos quatro arquivos DXF de teste (blocos, polilinhas, textos e nome de camada longo) e nos dois DWG (R2000 e R2018).
- Abre o arquivo do cliente em processo filho isolado (`ogrinfo`/`ogr2ogr`/`dwg2dxf` com seccomp que fecha soquete de rede, tetos de memória e de processador, relógio de parede); o processo principal só lê bytes do cabeçalho.
- Converte coordenada de desenho em coordenada de terreno por pontos de controle e informa o erro quadrático médio (RMSE 0,0 m com 3 pontos exatos; 0,136 m com erro de 0,4 m injetado); DXF binário é recusado com mensagem própria, e sem CRS declarado a importação fica pendente de resposta do usuário.

### L0-04-f-fgdb-parquet-fgb-gml (parcial)

- As leituras de arquivo da ingestão vetorial (`ogrinfo` e `ogr2ogr`) rodam em ambiente isolado: variáveis do GDAL sem acesso HTTP e filtro de chamadas de sistema que bloqueia soquete de rede nas leituras que não tocam o Postgres.
- Os formatos do item — FileGDB, GeoParquet, FlatGeobuf e GML — não foram construídos nesta fatia: domínio codificado da FileGDB, aviso de raster não importado e medida de tempo por formato continuam pendentes.

### L0-04-h-exportar (entregue)

- `POST /api/exportacoes` enfileira a geração e devolve a camada em 11 formatos (GeoPackage, GeoJSON, Shapefile em zip, CSV, XLSX, KML, KMZ, FlatGeobuf, GML, DXF e GeoParquet), como arquivo com validade de 7 dias.
- Filtro, campos e sistema de coordenadas de saída são conferidos antes de existir tarefa; pedido inválido devolve 400 com o erro do banco saneado.
- O isolamento entre inquilinos é do PostgreSQL: o `ogr2ogr` abre conexão própria com o inquilino na string de conexão e a RLS corta; medido, os 11 formatos reabrem com as mesmas 100.000 feições, entre 0,80 s (FlatGeobuf) e 14,54 s (XLSX).

### L0-04-i-fonte-registrada (entregue)

- Registra um PostgreSQL/PostGIS externo do cliente como fonte de dado (`POST /api/conexoes` do tipo `postgres_fdw`), lista as tabelas desse banco por `pg_catalog` sem copiar dado e publica várias de uma vez, cada tabela virando uma camada vetorial referenciada no catálogo.
- Cada tabela publicada vira tabela estrangeira mais uma view que injeta o inquilino e filtra por ele, porque uma tabela estrangeira não aceita política de segurança por linha; a credencial fica cifrada e a view recebe apenas permissão de leitura.
- A defesa de alvo recusa o banco da própria instalação em qualquer endereço e o endereço de metadado de nuvem; um banco em rede privada continua permitido, porque é caso legítimo de cliente.

### L0-05-a-fila-postgres (parcial)

- Cláusulas cobertas pela fila já entregue (`L0-05-jobs`): unidade viva no `/saude`, 100 jobs sem duplicata, retentativa 2/4/8 s.

### L0-05-b-progresso-cancelamento (parcial)

- Log de 10 mil linhas resumido, limite de 10 conexões SSE por usuário com fechamento em 30 min, progresso sempre grampeado em 0-100 mesmo se o chamador mandar mais.

### L0-05-c-tela-tarefas (refutado)

- Tela Tarefas (lista/filtros/detalhe/log/agendas): defeito real achado por leitura de código — a visão de detalhe assina o SSE só na abertura e nunca reassina após o fechamento forçado de 30 min do servidor, ficando muda num job de execução longa; a lista se autorrecupera, o detalhe ainda não.

### L0-05-d-periodicos (entregue)

- 5 periódicos exigidos, todos vivos: expurgo de sessão, expurgo/compactação do catálogo, e agora também expurgo de sessão vencida e ANALYZE semanal das tabelas centrais.

### L0-06-a-dump-logico (entregue)

- O periódico `backup.dump_logico` roda às 03:00 e gera um `pg_dump` por inquilino mais um do schema da plataforma, cada arquivo restaurável sozinho, com sha256, bytes, tempo e número de tabelas gravados em `plat.backup` e a cópia enviada ao bucket `plat-backup`.
- O espaço livre é conferido antes de escrever qualquer byte, com mínimo de 10 GB por padrão; abaixo disso o trabalho termina em falha com os dois números na mensagem, grava evento e envia mensagem ao superadministrador.
- A retenção mantém 14 cópias diárias e 8 semanais por schema, apagando linha, arquivo e objeto juntos, e o periódico `backup.verificar` reconfere o sha256 de cada arquivo às segundas-feiras.

### L0-06-c-restore-drill (parcial)

- Roda um ensaio de restauração do backup: o trabalho `backup.restore_drill` restaura o último arquivo de cópia num banco de ensaio, compara a contagem de linhas de todas as tabelas com dono de inquilino contra a produção e confere o sha256 de objetos do balde contra o manifesto.
- O ensaio curto roda dentro do `make check` em 3,7 segundos com a máquina em carga 7,20, contra um teto de 60 segundos; arquivo de cópia corrompido é acusado, vira evento de falha e gera aviso por e-mail ao superadministrador, e `GET /saude` publica a data do último ensaio.
- O ensaio registrou uma exigência que a instalação não cumpre: o banco de ensaio só restaura o schema da plataforma com as extensões postgis, pgcrypto, pg_trgm e unaccent, e o `install.sh` cria apenas as duas primeiras.

### L0-06-d-exportar-inquilino (parcial)

- Exporta o inquilino inteiro por um botão em `/admin/organizacao` e pelo trabalho `inquilino.exportar`: um zip com `dados.gpkg` (uma camada por camada hospedada, com metadado e estilo nas tabelas da norma GeoPackage), `catalogo.json` validado contra esquema publicado, `arquivos.zip` do armazenamento de objetos e `manifesto.json` com sha256 e tamanho de cada parte.
- Mostra o tamanho estimado antes do clique e limita a uma execução por dia; o importador recria o catálogo num inquilino novo com os mesmos identificadores. Medido no ambiente de trilha: pacote de 23.782 bytes com 2 itens, 1 camada e 1 arquivo em 0,55 s.
- Não restaura o conteúdo das camadas nem os arquivos no destino: essa parte fica com a ingestão.

### L0-06-e-status (parcial)

- Publica a página `/status` e a rota `GET /api/status` sem exigir sessão, com estado de interface de programação, banco, worker, servidor de tiles, servidor de imagens e armazenamento de objetos, migrações aplicadas e pendentes, fila, última cópia de segurança, disco, certificado e histórico de 90 dias.
- A resposta é só agregado, sem versão de dependência, caminho de disco, endereço interno ou nome de inquilino, e o log de correções lido do changelog passa por higienização antes de aparecer.
- Mil pedidos em 20 conexões foram servidos em 1,07 segundo pelo cache de 30 segundos, sem consulta ao banco; o retrato frio leva 92 milissegundos. A cláusula do ensaio de restauração responde "indisponível" com a razão enquanto o item que a produz não entra no tronco.

### L0-07-a-configuracoes-org (refutado)

- Configurações da organização: nome, cor/logotipo, cota de armazenamento e de usuários, idioma e mapa padrão, política de senha/2FA — só o admin do inquilino acessa; cota de usuários agora barra criação nova (413) e a de armazenamento reflete na hora.

### L0-07-b-papeis-privilegios (entregue)

- Publica a tabela de privilégios em `docs/PRIVILEGIOS.md` lida ao vivo do banco: 47 privilégios em 12 grupos, 20 deles administrativos.
- Um teste chama toda rota do OpenAPI que declara privilégio com um usuário que não o tem e exige 403 em todas.
- Rebaixar o perfil de um usuário que possui itens do catálogo é recusado com 409 e a lista dos itens, a mesma regra que já valia para grupos.

### L0-07-d-smtp-convites (entregue)

- Configura o servidor de envio de e-mail (SMTP) na instalação e por inquilino, com a senha cifrada no banco; `POST /api/org/smtp/testar` faz um envio de prova e devolve o erro em texto legível, nunca a senha.
- Convida um membro por e-mail: o convite vale 7 dias, o endereço nunca viaja no link (o servidor lê o que o convite guarda), o uso é único e aceitar cria a conta na mesma transação que marca o convite usado.
- Redefine senha por e-mail sem revelar quem tem conta: o pedido responde sempre 202, e o limite de 5 pedidos a cada 15 minutos por endereço conta também endereço inexistente; as telas `/aceitar-convite` e `/redefinir-senha` são públicas.

### L0-07-e-relatorios (parcial)

- Gera cinco relatórios do inquilino como trabalho de fila (membros, itens, grupos, atividade e uso) em CSV com cabeçalho documentado, guardado no armazenamento de objetos e baixado por `GET /api/relatorios/{id}/csv`; outro inquilino recebe 404 e quem não tem o privilégio de exportar recebe 403.
- Aplica limites declarados de 12 meses de janela (422), 10 mil linhas por relatório (corte marcado) e um pedido por tipo por hora (429); o agendamento diário, semanal ou mensal vira entrada na tabela de agendas e entrega o link assinado por e-mail. O painel `/admin/atividade` reúne totais, itens mais acessados e eventos por dia.
- O código está na trilha de entrega e ainda não foi trazido para o ramo que serve a demonstração: `app/relatorios/` não existe nesse ramo. Medido na trilha: relatório de itens com 10.001 itens em 0,6 s de trabalho, contra o teto de 10 s do portão.

### L0-07-f-console-plataforma (parcial)

- Dá ao operador da plataforma a tela `/plataforma` e as rotas `/api/plataforma`: lista de inquilinos com uso contra cota, criação com administrador de senha temporária, alteração de cotas, suspensão com mensagem, reativação e trilha de eventos.
- Inquilino suspenso responde 503 com a mensagem no login, na sessão viva e no token, sem apagar dado; reativar devolve a mesma sessão.
- As 10 rotas do console respondem 404 a sessão comum, token e anônimo, e 401 a cookie forjado; a página fica pronta em 152 milissegundos.

### L0-08-a-oidc (parcial)

- Permite login federado por OpenID Connect em cada inquilino (`GET /api/sso/oidc/iniciar`, `retorno` e `logout`), com Authorization Code e PKCE, descoberta do provedor e validação do `id_token` em duas fases: assinatura pelo JWKS e conferência separada de emissor, audiência, validade e `nonce`.
- A transação de login vive em `plat.oidc_transacao` e é consumida uma única vez, o que barra reuso de código e troca de `state`; um inquilino pode ter mais de um provedor, e o segredo do cliente fica cifrado.
- Falta para o item ficar completo: a varredura cruzada da suíte inteira, em que 41 rotas publicadas de outros itens ainda não têm caso escrito.

### L0-08-b-saml (parcial)

- Entra por SAML 2.0 (protocolo de autenticação federada usado por provedores corporativos), com vários provedores por inquilino, início pelo produto ou pelo provedor, metadado do prestador de serviço assinado e válido contra o esquema oficial, e desconexão propagada nos dois sentidos.
- Recusa asserção sem assinatura, assinada por outra chave, com envelopamento de assinatura XML, com relógio 10 minutos adiantado ou repetida; o provedor fora do ar não impede o login local.
- Nada disso está no ramo de lançamento: `app/auth/saml.py`, a migração do provedor e a suíte de testes existem apenas na trilha de entrega, e o login federado do produto instalado hoje é só LDAP e OIDC.

### L0-08-c-govbr (parcial)

- Trata o Login Único gov.br como um modelo de provedor OIDC: o adaptador transforma o nível de confiabilidade (bronze, prata, ouro) e os selos do token de identidade em valores que a regra de mapeamento converte em perfil, papel e grupos; quando o token não traz esses dados, consulta a API de confiabilidades.
- Guarda o CPF apenas como pseudônimo SHA-256, nunca em login, identificador externo, evento ou registro de acesso; um token de identidade assinado por outro emissor com nível ouro forjado é recusado com 401, provado contra um provedor de identidade sintético.
- O código do adaptador não foi trazido para o ramo que serve a demonstração, e o teste contra o ambiente real do gov.br segue pendente de credencial do órgão, como o portão previa.

### L0-08-d-ldap (parcial)

- Login por LDAP/Active Directory por inquilino, mapeamento de grupo para perfil, provisionamento automático sem guardar a senha externa; diretório fora do ar nunca impede o login local.

### L0-08-e-mapeamento-provisionamento (parcial)

- Aplica um conjunto único de regras de provisionamento aos três tipos de login externo (LDAP, OIDC e SAML) depois que o provedor confirma a identidade: criar conta automaticamente ou só por convite prévio, padrões de perfil, grupos e pasta para membro novo, e mapa de valor exato de grupo do provedor para perfil e grupos internos.
- O mapeamento é por regra declarada, nunca por nome igual: um grupo chamado administrador sem regra não concede nada; a cada login o vínculo é reavaliado e a conta pode ser desligada quando o provedor deixa de enviar o grupo mapeado.
- A tela `/admin/logins` lista os provedores, liga e desliga cada um e edita as regras linha a linha.

### L0-09-a-procedencia (parcial)

- Todo item que carrega dado tem bloco de procedência com 10 campos (fonte, endereço, licença, data do dado, data de acesso, gerador, sha256, comando de reexecução, método e responsável, entre outros), cada campo marcado como declarado por alguém ou medido pela máquina.
- A camada importada por arquivo nasce com os 4 campos que a máquina mede — sha256, data de acesso, gerador e método — e a pontuação de completude aparece na ficha, na lista, na busca (`licenca:CC`, `procedencia:[5 TO 10]`) e na exportação da lista; item sem bloco fica com pontuação nula, nunca zero.
- Falta para o item ficar completo: a cláusula de levar a procedência na exportação do inquilino inteiro, que depende do item `L0-06-d-exportar-inquilino`, e a entrada do ramo na fila de junção, recusada por ser ramo protegido.

### L0-09-b-editor-iso-mgb (parcial)

- Edita o metadado do item no Perfil MGB 2.0 da INDE por três rotas: ler com a lista do que falta, validar um rascunho sem gravar e gravar.
- Título, resumo, palavras-chave, créditos e termos de uso continuam guardados uma vez só no item e são calculados a cada leitura, então mudar o título pelo editor de metadado muda o item e a recíproca vale; a linhagem é computada da procedência e dos eventos do item, sem campo de texto livre.
- Metadado acima de 1 MiB e data de fim antes da de início são recusados com o caminho do campo; extensão espacial declarada que contradiz o dado gera aviso, não bloqueio.
- Duas fronteiras: a exportação do inquilino inteiro, que levaria o metadado junto, não existe no repositório, e a linhagem foi provada com procedência sintética, não com camada importada de verdade.

### L0-09-c-xml-iso-validacao (parcial)

- Importa metadado no formato ISO 19139 por `POST /api/itens/{id}/metadado.xml`: título, resumo, palavras-chave, créditos, termos de uso e extensão entram pelo mesmo caminho de edição do item, e contato, sistema de referência e formato vão para a coluna de metadado do item.
- Trata o esquema XSD como parecer, não como porteiro: um registro real do catálogo aberto da INDE tem 20 erros contra o XSD oficial e mesmo assim preenche 22 campos; XML malformado, grande demais ou com raiz errada responde 422 com linha e coluna, e `?estrito=1` transforma o aviso em recusa.
- Exportar e reimportar não perde campo do perfil, e o que não tem onde ser guardado sai listado com caminho e exemplo. Fora desta fatia: o formato ISO 19115-3 e o botão de importar na tela.

### L0-10-eventos-historico (parcial)

- Toda rota que muda estado grava 1 evento (cobertura 100% das 75 rotas de escrita, medida); `plat_app` não consegue apagar nem alterar evento gravado.

### L0-11-arquivos-objetos (parcial)

- Guarda arquivo de cada inquilino em bucket próprio no Garage (chave de acesso e cota próprias, mirror de `tenant.cota_bytes`), nomeado pelo sha256 do conteúdo — nunca sobrescreve, nunca serve direto do Garage.
- `POST/GET/DELETE /api/arquivos[/{sha256}]` com upload multipart (iniciar/enviar/concluir/abortar); upload de corpo bruto exige token de serviço, não cookie de sessão (a mesma regra de CSRF que protege o resto da API).
- Varredura de objeto órfão e leitura de uso/cota por inquilino; dois inquilinos nunca leem o objeto um do outro (13 testes, incluindo ataque direto contra o Garage real: chave só-leitura tentando escrever, leitura cross-bucket).

### L0-12-contrato-api-e-limites (parcial)

- Documenta o contrato de API vivo em `docs/CONTRATO_API.md` (formato de erro, paginação, sem prefixo de versão na URL — o OpenAPI é o contrato) e gera `docs/LIMITES.md` a partir dos valores reais do código, nunca digitados à mão.
- Aplica limite de corpo (10 MiB padrão) com duas defesas: `Content-Length` grande demais recusa antes de ler; corpo em pedaços que mente o tamanho é contado byte a byte e cortado do mesmo jeito.

### L1-01-a-pgstac-e-stac-api-por-inquilino (entregue)

- A instalação expõe uma STAC API (catálogo padronizado de imagens) por inquilino em `/svc/<token>/stac/`, sobre o pgstac instalado pelas migrações, com a role da aplicação restrita aos papéis de leitura e ingestão.
- Medido em 06/09/2026 sobre uma coleção de 10.000 itens sintéticos: a busca por retângulo devolveu 567 itens em 234,73 ms de mediana em 5 chamadas HTTP completas, com a primeira chamada de aquecimento descartada (`tests/medidas/L1-01-a.json`).

### L1-01-b-validacao-e-isolamento-da-entrada (parcial)

- Inspeciona todo raster enviado pelo cliente dentro de um subprocesso separado, com limites declarados de memória, tempo de processador, descritores e relógio de parede, e com ambiente do GDAL sem leitura de diretório e sem acesso HTTP.
- O processo principal confere a assinatura de formato nos 64 primeiros bytes antes de abrir qualquer subprocesso, então um PNG renomeado para `.tif` é recusado sem leitura; o relatório termina em três estados — recusado, pendente (falta informação que só o usuário tem, como sistema de coordenadas) e aceito — e nunca supõe um sistema de coordenadas.
- Medido em 33 casos com arquivo sintético: o subprocesso leva 0,294 segundo na mediana e consome entre 87,1 e 130,4 MB; um arquivo esparso de 320.000 por 320.000 pixels, com 95,4 GB estimados, é recusado em 0,3 segundo sem derrubar o processo principal.

### L1-01-d-garage-por-inquilino (entregue)

- Balde próprio por inquilino no Garage: 6 cláusulas medidas; achado real ainda aberto — ListBuckets responde 200 com o próprio balde em vez de 403, e o bloco de rede ainda não está aplicado.

### L1-01-f-formatos-de-entrada (parcial)

- A ingestão de imagem tem uma tabela única de formatos: 12 aceitos (entre eles GeoTIFF, JPEG 2000, Erdas Imagine, ENVI, ASCII Grid, netCDF de uma variável e um tempo, GRIB de uma mensagem e Zarr), cada um provado com arquivo aberto, e os recusados respondem com mensagem própria (ECW e MrSID por falta do programa proprietário).
- `GET /api/imagens/formatos` devolve a mesma tabela que a tela de envio mostra, e um zip com 4 cenas contíguas vira um único COG mosaicado, enquanto cenas de sistemas de coordenadas diferentes são recusadas dizendo quais.
- O portão roda contra a tarefa real, o armazenamento de objetos e o catálogo de imagem, com 22 testes.

### L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo (parcial)

- Exclui uma imagem e o efeito é imediato: o ladrilho responde 404 em 0,016 segundo, o item sai do catálogo de imagens (STAC) e o apagamento dos objetos no balde é agendado para 7 dias depois.
- Restaurar dentro dos 7 dias devolve o item inteiro, porque o objeto nunca saiu do balde; fora do prazo a restauração é recusada com 409.
- O comando `plat raster gc` lista objetos órfãos, quebrados e lixeira vencida e registra o relatório como tarefa concluída; a coleta lista e relata, apagar órfão continua sendo decisão humana.

### L1-01-j-proveniencia-da-imagem-lastro (entregue)

- Cada item de imagem carrega a cadeia de origem: versões de GDAL, rio-cogeo, rasterio e da própria plataforma medidas no momento da conversão, o argumento exato de cada `gdal_translate`, o sha256 de entrada e de saída de cada passo e um sha256 do item inteiro sem essa própria chave.
- `POST /api/imagens/<item>/conferir` baixa cada arquivo com resumo criptográfico de volta do repositório de objetos em fluxo, recalcula o sha256 e compara por arquivo, sem um veredito único que esconda a divergência de um deles.
- Itens ingeridos antes deste item podem ser completados por uma rota de administração, que preenche só o metadado já medido, e pelo trabalho de fila `imagens.reexecutar`, que reconverte o arquivo bruto e compara o sha256 obtido com o registrado; quando a cadeia não existe, o campo fica ausente em vez de ser preenchido.

### L2-01-a-documento-mapa (entregue)

- O mapa deixa de ser um conjunto de endereços e passa a ser um documento com esquema publicado: mapa-base, lista ordenada de camadas com visibilidade, opacidade, faixa de escala, grupo de até 3 níveis, estilo, janela de atributos, filtro, rótulos e campo de tempo. Cada camada aponta o item do catálogo pelo identificador interno, nunca por URL.
- `GET /api/mapas/{id}/completo` devolve o documento com as camadas já resolvidas numa chamada: p95 de 20,7 ms em 50 chamadas num mapa de 10 camadas, contra o teto de 150 ms do portão.
- Camada de outro inquilino citada no documento responde 404; apagar camada usada por mapa responde 409 com a lista dos mapas dependentes; 500 camadas, 5 níveis de grupo, ciclo de grupo e extensão fora do mundo respondem 422. Na tela a lista de camadas reordena por arrasto e por teclado, e a ordem sobrevive ao recarregamento.

### L2-01-b-martin-tiles-vetoriais (parcial)

- Serve tiles vetoriais pelo Martin 1.15.0 sobre o PostGIS, com simplificação de geometria por nível de zoom e corte de 10.000 feições por tile.
- A conferência do token acontece fora do Martin, numa rota interna que o nginx consulta antes de repassar o pedido, e o item a que o tile pertence é lido da tabela pedida na URL, nunca de parâmetro do cliente — correção de um acesso cruzado achado pelo adversário.
- Medido: tile em zoom 8 de uma camada de 100 mil feições em 41,8 milissegundos frio e 4,3 quente; 472.780 setores censitários navegados de zoom 4 a 14 sem erro, com 1 tile de 110 amostrados 1,3 % acima de 1 MB. Fora desta fatia: subdivisão de polígono muito denso, unidade de serviço própria e abertura conferida em cliente de mesa.

### L2-01-c-lista-camadas-legenda (parcial)

- A árvore de camadas e a legenda dinâmica do mapa existem e respondem aos estilos proporcional, de calor e de imagem, provadas por 26 testes de unidade.
- Falta para o item ficar completo: o teste de navegador com reordenação por arrasto e por teclado, opacidade lida do estilo aplicado, camada fora de escala e captura de tela; nada disso foi executado nesta retomada.

### L2-01-e-mapas-base (parcial)

- Oferece galeria de mapas base: 4 fontes de dado aberto instaladas como item de catálogo do tipo mapa base, instalação idempotente e um só padrão por inquilino.
- Serve o mapa base do OpenStreetMap por um intermediário com cache próprio (30,2 ms na primeira leitura, 0,05 ms na repetida) que não aceita host escolhido pelo chamador, o que impede seu uso como intermediário aberto; a licença de cada fonte está em `docs/DADO_DEMO.md` e o pior caso de disco medido é de 124.039.134 bytes.
- Falta a prova pelo navegador: troca de mapa base preservando camadas e extensão, entrega por faixa de bytes e atribuição na impressão estão escritas como teste e não rodam na trilha, que não tem servidor web à frente da aplicação.

### L2-01-f-navegacao-medicao-coordenadas (parcial)

- Mede distância e área sobre o elipsoide no próprio navegador, com erro de até 0,1 % contra o cálculo geográfico do PostGIS em 5 segmentos e 3 polígonos; mostra os segmentos parciais e permite copiar o resultado.
- Mostra a coordenada do cursor no sistema de referência escolhido (entre eles 4326, 4674, os fusos UTM brasileiros e 5880), com diferença de até 1 cm em relação à transformação do banco; o campo "ir para" aceita decimal com vírgula, grau-minuto-segundo e par de coordenadas com código EPSG.
- Guarda favoritos de extensão, histórico de voltar e avançar, botão de norte, tela cheia e localização do usuário com círculo de precisão. Os favoritos ficam no navegador (localStorage), não no documento do mapa.

### L2-01-g-tabela-atributos (parcial)

- Mostra a tabela de atributos da camada acoplada ao mapa, paginada no servidor em 50, 200 ou 1.000 linhas, com ordenação, busca em texto sem acento, filtro pela extensão visível, filtro pela seleção do mapa e estatísticas por coluna numérica calculadas no banco.
- A seleção anda nos dois sentidos: clicar na linha centra a feição e clicar na feição filtra a tabela; coluna oculta pela vista do usuário não sai nem na rota de colunas, e nome de coluna pedido que não exista no catálogo do banco vira erro 422 antes de virar consulta.
- Medido em camada de 1 milhão de feições: primeira página em 275,9 milissegundos e ordenação por coluna indexada em 15,2 milissegundos, no percentil 95. Os testes de tela ficaram pulados por falta de endereço que resolva na máquina de trilha.

### L2-01-h-selecao-filtros (parcial)

- O servidor faz seleção e filtro de feições: `/valores`, `/filtrar`, `/selecionar` e `/selecao-espacial` aceitam CQL2 (linguagem de filtro padronizada pela OGC), e o resultado bate com o PostGIS escrito à mão em polígono, em três cláusulas com OR aninhado, em campo de data com fuso e em distância.
- Campo inexistente, operador inválido, função proibida, 200 cláusulas e SQL bruto devolvem 422, nunca 500.
- Falta para o item ficar completo: a interface — desenho da seleção no mapa, construtor visual de filtro e estado do filtro na URL não existem.

### L2-01-i-graficos-de-camada (parcial)

- Desenha cinco tipos de gráfico por camada — barras, pizza, linha por faixa de data, histograma e dispersão — com toda a agregação feita no servidor por `POST /api/camadas/{id}/grafico`, nunca com dado bruto no navegador.
- As contas conferem contra referência independente: as bordas e contagens do histograma reproduzem as do `numpy.histogram` e a reta da dispersão bate com a do `numpy.polyfit` na tolerância de 1e-6; clicar numa barra seleciona no mapa a mesma contagem.
- Uma camada de 1 milhão de feições responde entre 72 e 168 ms no percentil 95, depois que a função de contexto de inquilino passou a permitir varredura paralela; o gráfico sai em SVG próprio de até 40 kB, com exportação em PNG e CSV.
- A escolha de gráfico de cada camada ainda fica guardada no navegador, não no documento de mapa.

### L2-01-j-comparacao-cortina-tempo (entregue)

- Compara dois conjuntos de camadas no mesmo mapa por quatro ferramentas: cortina vertical e horizontal, mapas lado a lado sincronizados, lupa e controle de tempo para camada com campo de data.
- O sincronismo do lado a lado foi medido em 20 movimentos de centro, zoom e rotação: diferença de centro igual a zero em todos, com zoom e rotação idênticos.
- O controle de tempo filtra no servidor pela mesma operação de consulta do serviço compatível com Esri: 5 passos da janela instantânea e 3 da acumulativa bateram exatamente com a contagem feita direto no banco, sobre camada de teste de 100 mil pontos com 3 % de datas nulas e um quarto gravado em fuso diferente de UTC.

### L2-02-a-modelo-estilo (parcial)

- Define o estilo de camada num documento próprio com esquema publicado, valida contra a especificação de estilo do MapLibre e recusa documento inválido com erro 422 trazendo a mensagem do validador.
- O servidor recompila o estilo canônico a cada gravação, e a ida e volta entre exportar e importar foi provada sem perda; 6 dos 7 tipos de estilo desenham de ponta a ponta no navegador, com captura por tipo (raster ficou de fora por falta de tile na bancada).
- Duas cláusulas ficam abertas: o estilo padrão determinístico existe e é testado, mas ainda não está ligado à gravação da ingestão, e a conferência do arquivo SLD em cliente de mesa não foi medida nesta máquina.

### L2-02-b-classificacao-servidor (parcial)

- Classifica os valores de um campo no servidor por quantil, intervalo igual e quebras naturais (Jenks), com cortes iguais aos do numpy e de uma implementação de referência independente.
- Nulos são excluídos e contados, valores repetidos não geram classe vazia, e um milhão de valores é classificado dentro do teto do portão.
- Falta para o item ficar completo: o portão passou na árvore junta do ramo de reentrega, ainda sem veredito registrado sobre o item inteiro.

### L2-02-c-editor-simbologia-vetor (parcial)

- Edita a simbologia da camada no visualizador: símbolo único, por categoria, por classe de cor e de tamanho, proporcional, mapa de calor, agrupamento de pontos, efeitos e faixa de escala, com pré-visualização pela mesma função que grava.
- O estilo é salvo como item de catálogo ligado à camada, exportável e importável em JSON; as rampas de cor ColorBrewer 1.7.0 estão no repositório com o arquivo de licença ao lado.
- Os cortes de classe são os do item irmão de classificação no servidor, e valores acima de 200 categorias entram num grupo "outros".
- A entrega atual é por junção de ramo: as capturas de tela do portão e a medida de fluidez com 1 milhão de pontos não foram rodadas.

### L2-02-d-rotulos (parcial)

- Rotula a camada por campo, por expressão da linguagem própria ou por classes com filtro: cada classe tem fonte, tamanho fixo ou por zoom, cor, halo, âncora, deslocamento, repetição ao longo da linha, maiúsculas, unidade, prioridade e faixa de escala própria.
- A expressão é compilada para o equivalente nativo do MapLibre quando existe; o que não compila, a começar pela formatação em português como `1.234,5 ha`, cai para uma coluna pré-calculada no servidor, e os dois caminhos produzem texto idêntico nas 100 feições do teste.
- Medido na colisão entre classes: quem decide no MapLibre é a ordem das camadas de símbolo, não só a chave de ordenação, e o gerador passou a reordenar por prioridade. Não medido: o tempo de tile com rótulo calculado no servidor em camada de 1 milhão de feições, porque a função de tile real pertence a outro item.

### L2-02-e-simbolos-sprites-glifos (parcial)

- Traz uma biblioteca própria de 153 ícones e 10 padrões de preenchimento sob licença CC0-1.0, com licença e resumo criptográfico de cada arquivo listados em documento gerado do manifesto.
- Monta o atlas de símbolos por inquilino em 1x e 2x pela própria interface de programação, porque o servidor de tiles lê o diretório de símbolos só uma vez na subida; os glifos de fonte continuam vindo dele, sobre as fontes Noto Sans e Open Sans embutidas.
- Ícone enviado pelo inquilino passa por saneamento: script embutido, referência externa e declaração de entidade XML são recusados com erro 422, arquivo acima de 64 kB é recusado, e o pedido do atlas de outro inquilino responde 403. Compor o atlas de 163 itens leva 0,097 segundo em 1x e 0,145 em 2x.

### L2-03-a-api-edicao-transacional (parcial)

- `POST /api/camadas/{id}/edicoes` é a única porta de escrita de feição da plataforma: adicionar, atualizar e apagar numa transação tudo-ou-nada, ou por feição com ponto de salvamento.
- A validação mora no servidor: tipo de geometria, sistema de coordenadas, geometria válida (corrigida só quando pedido), domínio de atributo, tamanho de texto e campos de rastreio que nunca vêm do cliente; edição com versão desatualizada devolve 409 com a feição atual, sem sobrescrever em silêncio.
- Falta para o item ficar completo: o teste de navegador da edição no mapa não foi rodado nesta passagem.

### L2-03-b-ferramentas-geometria (entregue)

- A edição no mapa tem as operações de geometria do item: unir feições (`POST /api/camadas/{id}/unir`), dividir feição (`/dividir`) e as demais operações de desenho, todas pela mesma porta de escrita de feição da plataforma.
- A porta de escrita valida tipo de geometria, SRID, validade do polígono, campo obrigatório, domínio e tamanho, e controla concorrência por número de versão da feição.

### L2-03-c-formulario-atributos-runtime (parcial)

- Gera o formulário de atributos a partir do esquema da camada durante a edição no mapa: domínio de valores e campo obrigatório aparecem no navegador e são reconferidos no servidor, que continua sendo a autoridade.
- Falta o motor de formulário completo: grupos recolhíveis, visibilidade condicional, cálculo por expressão e troca de lista de domínio por subtipo dependem de itens de expressão e de relações ainda não integrados.

### L2-03-f-edicao-em-lote-calculo-campo (parcial)

- `POST /api/camadas/{id}/lote` aplica uma operação a uma seleção de feições: calcular campo por expressão, atribuir valor fixo, apagar, corrigir geometria inválida, copiar ou mover entre camadas com mapeamento de campos, e pré-visualizar 10 linhas antes e depois sem gravar.
- Até 5.000 feições a operação corre no próprio pedido; acima disso vira trabalho de fila com progresso e cancelamento, tudo numa transação só, de modo que erro ou cancelamento devolve a camada ao estado anterior. Medido: 100 mil polígonos com `area_ha = $area_m2 / 10000` em 16,1 s, amostra de 1.000 igual ao cálculo do PostGIS e histórico gerado para as 100 mil.
- Fora desta fatia: reprojeção no lote e o filtro que depende do motor de estatísticas do item L2-06-e.

### L2-04-a-leitor-rls-martin (parcial)

- Cria um papel de banco só de leitura, sem privilégio de contornar a segurança por linha, para o servidor de tiles, e uma função de contexto que valida o token de serviço, confere o escopo e a restrição de origem e endereço, grava o uso no log de acesso e fixa o inquilino na transação.
- A política de segurança por linha não confia na variável de sessão crua: exige uma prova assinada emitida apenas por essa função, então o próprio papel de leitura não consegue se declarar de outro inquilino. Medido: 0 linhas ao forjar a variável, 6 chamadas cruzadas devolvendo 0 tile com dado, token revogado sem efeito em 0,002 segundo e 1 linha de log por chamada aceita.
- Duas fronteiras declaradas: a cláusula do instalador foi provada no passo que instala o papel, não no instalador inteiro, e a recusa de contexto não deixa linha no log de acesso, porque a transação aborta.

### L2-04-b-featureserver-catalogo-metadados (parcial)

- Publica um diretório de serviços no formato Esri em `/svc/{token}/rest`, com `info`, `generateToken` (validade máxima de 24 h), `services` por pasta, `FeatureServer`, a camada por id, `layers`, `itemInfo` e metadado ISO 19139, nos formatos `json`, `pjson` e `html`.
- O descritor da camada traduz o estilo MapLibre em `drawingInfo` nos três tipos (símbolo único, valor único e faixas de classe); expressão fora desses casos sai como símbolo cinza com o motivo escrito, nunca aproximada.
- Falta para o item ficar completo: a conferência com o QGIS e com a biblioteca Python da Esri, que esta máquina não tem; domínio, subtipo e relacionamento saem vazios porque dependem de itens ainda ausentes desta base.

### L2-04-c-featureserver-query (parcial)

- Responde à operação `query` do FeatureServer no formato da Esri com 39 dos 45 parâmetros da documentação exercidos por pedido real, contra o piso de 38 do portão.
- Devolve o formato binário PBF oficial da Esri, decodificado pela mesma definição que o cliente usa e igual ao JSON; consulta espacial sobre 8,4 milhões de imóveis responde em 1,6 ms no percentil 95 com índice espacial.
- Filtro inválido sempre volta como erro 4xx, nunca 500, e nenhuma consulta é montada sem parâmetro ligado.
- Não foi verificado: carga de camada com 100 milhões de linhas no QGIS, por falta de ambiente gráfico nesta máquina, e o adversário independente ainda não rodou contra o item.

### L2-04-d-featureserver-edicao-anexos (parcial)

- Aceita escrita pelo protocolo Esri: `applyEdits` na camada e no serviço, `addFeatures`, `updateFeatures`, `deleteFeatures`, `calculate`, os seis caminhos de anexo e o envio prévio de arquivo, todos em `/rest/services/{item}/FeatureServer/0/*`.
- Nenhuma dessas rotas escreve direto na tabela: todas traduzem o pedido e chamam a porta única de escrita do item L2-03-a, de modo que tipo, domínio, sistema de referência, propriedade e controle de versão valem igual para o cliente Esri. O erro sai com o código HTTP real e o corpo no formato Esri, e `rollbackOnFailure` é um ponto de retorno por lote.
- Duas cláusulas do portão não foram feitas e estão nomeadas: a prova com o QGIS editando uma feição e a prova com o pacote Python `arcgis`, ausentes desta máquina.

### L2-04-f-mapserver-identify-legend-geometryserver (parcial)

- Publica o contrato de serviço de mapa no protocolo Esri (descritor, camadas, `export`, `identify`, `find`, `legend` e `generateKml`) e o serviço de geometria com projeção, envoltória, áreas e comprimentos, distância, união, interseção, diferença, envoltória convexa e simplificação.
- O desenho usa a mesma estrutura de simbologia que o serviço de feições publica, então legenda e mapa não podem divergir de cor; toda operação de geometria é uma chamada ao PostGIS.
- Medido: imagem de 1024 por 768 pixels sobre 5.003 polígonos em 0,075 segundo quente; projeção de 100 pontos com diferença de 0,0 metro contra a função do banco; envoltória geodésica de 1 km com erro relativo de área 0,0. A conferência em cliente de mesa não foi feita: a máquina não tem ambiente gráfico.

### L2-04-g-ogc-api-features-crs-cql2 (parcial)

- Serve OGC API - Features com sistema de coordenadas escolhido pelo cliente e filtro CQL2 sobre a parte 1 do padrão, com 53 testes verdes na trilha do item.
- Falta para o item ficar completo: o veredito cláusula a cláusula do portão não foi registrado, incluindo o validador oficial da OGC e a conferência com o QGIS.

### L2-04-h-wfs-2-gml (parcial)

- Serve WFS 2.0.0 e 1.1.0 por token: o documento de capacidades é válido contra o esquema oficial do OGC lido de cache local, e o `DescribeFeatureType` gera o esquema a partir das colunas da camada.
- Aceita filtro FES 2.0 (comparação, lógica, espacial e temporal) traduzido para a mesma árvore do CQL2 e compilado pelo mesmo gerador de SQL, com o XML lido por analisador que recusa entidade e referência externa.
- Escreve pela operação Transaction, sempre pela porta única de edição da casa, marcando a origem `wfs` no evento; o GDAL 3.8.4 lê o serviço vivo e conta as mesmas 250 feições do banco, e 1.000 feições em GML 3.2 reabrem com geometria válida.
- Não medido: QGIS, que não está instalado nesta máquina, e os clientes da Esri, que dependem de credencial de parceiro.

### L2-04-j-conformidade-clientes-e-paridade (parcial)

- A lista de conformidade com os serviços Esri e OGC deixa de ser texto escrito à mão e passa a ser saída de medida: `make conformidade` roda as provas e grava 102 linhas com data e versão do repositório, e a seção do documento de paridade é reescrita a partir desse arquivo.
- A regra é fechada: prova que falha derruba a linha para refutado, e linha sem prova executada fica como não medida, nunca como suportada. Estado atual: 81 linhas suportadas, 5 parciais, 12 fora de escopo e 4 não medidas.
- Um cliente OGC de terceiros (owslib) lê as capacidades do WFS 2.0 e busca feições pelo próprio código dele. QGIS em contêiner, o pacote Python `arcgis` e o conjunto de testes teamengine não estão nesta máquina e ficam como não medidos; o protocolo para o parceiro executar com ArcGIS Pro e ArcGIS Online está escrito e marcado como pendente.

### L2-04-k-sync-replicas-esri (parcial)

- Responde as quatro operações de sincronização do protocolo Esri — criar réplica, sincronizar, extrair mudanças e remover registro — como fachada sobre o mecanismo de réplica da casa, sem relógio novo e sem formato novo.
- A repetição do mesmo pedido com a mesma geração do cliente devolve a resposta guardada e aplica zero mudança; atualizar feição apagada é conflito declarado, nunca inserção silenciosa; a extração de mudanças lê a janela sem adiantar o ponteiro.
- Medido: réplica de 200 feições criada em 0,35 segundo, com 14 testes passando. A conferência contra os aplicativos de campo e de mesa da Esri depende de credencial e fica pendente.

### L2-05-a-catalogo-ferramentas-gpserver (parcial)

- Registra ferramenta de análise por manifesto tipado no vocabulário de geoprocessamento da Esri, validado na construção: parâmetro sem tipo quebra o build.
- A mesma ferramenta roda por formulário gerado do manifesto na tela `/analise`, pela API própria `/api/ferramentas/{nome}/executar` e pelo serviço compatível `/rest/services/{ferramenta}/GPServer/{tarefa}`, com o mesmo resultado; a saída nasce como item de catálogo com procedência (ferramenta, versão, parâmetros e sha256 das entradas) e relação de derivação.
- Falta para o item ficar completo: a prova com o ArcGIS Pro real chamando o serviço, que depende da decisão D20.

### L2-05-b-vetor-basico (parcial)

- Oferece 19 ferramentas vetoriais elementares como expressão SQL no mesmo executor de ferramentas: área de influência geodésica, recorte, interseção, união, diferença, dissolver com estatística, mesclar, explodir, centroide, casco, simplificar, suavizar, reprojetar, calcular geometria, pontos aleatórios e conversões entre pontos, linhas e polígonos.
- Cada ferramenta é conferida contra referência independente na mesma entrada (shapely para geometria plana, pyproj para medida geodésica): a área de influência de 1 km na latitude −23 fica a 5,0e-5 do círculo de referência, contra o limite de 5e-4 do portão.
- Toda operação booleana em massa corrige a geometria antes de operar e grava na procedência da camada de saída quantas geometrias de entrada eram inválidas.
- O volume foi medido com 1.156 polígonos por camada, não com as 100 mil do portão, porque o disco estava em 93% e a máquina em carga 8,7; a prova pelo navegador não rodou.

### L2-05-c-sobreposicao-agregacao (parcial)

- Acrescenta nove ferramentas que relacionam duas camadas: junção espacial, junção por atributo, resumir dentro, contar dentro, resumir perto, agregar pontos em polígono ou em grade quadrada ou hexagonal, enriquecer por proporção de área, vizinho mais próximo e tabela de distâncias.
- Vinte e seis testes conferem cada ferramenta contra geopandas, pandas, shapely e pyproj na mesma entrada lida de volta do banco, sem número esperado escrito à mão; a contagem dupla causada por polígonos sobrepostos é contada e declarada no método, e pode ser desfeita pela atribuição exclusiva.
- Não medidos: o teste de ponta a ponta na tela e a escala do portão de 1 milhão de pontos em 5.570 municípios, por falta de disco e por teto de 5 mil feições na máquina de trabalho.

### L2-05-d-grades-densidade-padroes-interpolacao (parcial)

- Acrescenta 8 ferramentas ao catálogo de geoprocessamento: grade quadrada, hexagonal e H3, densidade por núcleo de pontos e de linhas, agrupamento significativo pelo índice Gi*, centro médio e elipse, vizinho mais próximo médio, índice global de Moran, interpolação por distância inversa e isolinhas.
- Os resultados foram conferidos contra implementações de referência independentes: Gi* e Moran com diferença de 8,9 vezes 10 elevado a menos 16, área do hexágono contra a fórmula fechada com 1 vez 10 elevado a menos 9, densidade integrando o número de pontos com erro de 1,1 vez 10 elevado a menos 4, e interpolação idêntica à referência.
- Fica pendente a saída em formato raster, que depende da linha de imagens, e a captura de tela das ferramentas; a grade de 250 metros reproduz a mediana de área da grade interna da casa e difere em 9 células de borda das 73.115.

### L2-05-e-raster-basico (parcial)

- Oferece treze ferramentas de imagem sobre COG lido por janela: estatísticas por zona, calculadora, reclassificar, recortar, reprojetar, mosaico, terreno (declividade, orientação, sombreamento, rugosidade e índice de posição), curvas de nível, vetorizar, rasterizar, amostrar em pontos, visibilidade e distância.
- Os resultados batem com a referência: declividade e visibilidade iguais byte a byte ao GDAL, NDVI igual ao avaliador do TiTiler dentro de 1e-6, e estatísticas por zona reproduzindo o `rasterstats`; 5.570 zonas sobre o mapa de uso do solo em 3,35 s, com pico de 777 MB de memória num arquivo de 9,77 GB.
- Falta para o item ficar completo: o registro de veredito das cláusulas de tela e da comparação escrita com o conjunto de análise raster da Esri.

### L2-05-f-rede-isocrona-rota-ferramentas (parcial)

- Oferece seis ferramentas de rede que devolvem o resultado como camada: área de serviço por tempo de viagem, rota com paradas na ordem dada ou otimizada, matriz origem-destino, K mais próximas, ligação do ponto à rede e localizar-alocar por cobertura máxima.
- O cálculo continua no serviço de roteamento do produto, não num segundo cliente: a área de serviço de 30 minutos sai idêntica à da rota `/api/isocrona`, com diferença de área zero.
- Medido: matriz de 100 por 100, isto é, 10.000 pares, em 3,96 segundos incluindo a escrita da camada; rota de 10 paradas cai de 3.583,9 para 3.521,6 segundos quando a ordem é otimizada; toda camada de saída grava a versão do grafo de ruas na procedência.
- A prova pelo navegador está escrita e não foi executada, porque a aplicação na trilha não serve os arquivos estáticos sem servidor web à frente.

### L2-06-a-modelo-painel-fontes (entregue)

- O painel é um documento com esquema publicado, cujos elementos apontam para fontes declaradas; o motor agrupa todos os elementos que usam a mesma fonte numa única leitura por ciclo de atualização, em vez de uma consulta por elemento.
- O filtro usa a mesma gramática auditada do resto do produto: o filtro fixo da fonte combinado com os valores de execução (filtros globais e parâmetros da URL de quem abre a tela), sempre por igualdade e só em campo que a fonte expõe.
- Medido no painel de exemplo com 9 elementos: primeira pintura em 28 ms e página pronta em 858 ms.

### L2-06-b-elementos-basicos (parcial)

- Dá ao painel doze tipos de elemento: indicador com nove estatísticas, gráfico de barras, linhas e área por categoria ou por data, pizza e rosca, tabela com ordenação ou agrupamento com subtotal, lista paginada, mapa, detalhes, texto com formatação, legenda e cabeçalho.
- Nenhum número é calculado no navegador: toda agregação passa pelo motor do servidor, e a extensão desenhada pelo mapa vira condição espacial das demais fontes do painel.
- Medido: lista de 10.000 feições a 66,8 milissegundos por página no percentil 95, contra teto de 300, e a extensão do mapa recortando 10.000 feições para 999.

### L2-06-c-acoes-seletores-filtros-cruzados (parcial)

- No painel, um elemento seletor (categoria, faixa numérica, data ou feição) dispara ações sobre os outros elementos — filtrar, selecionar, limpar, aproximar, deslocar, piscar, abrir e fechar —, e o filtro é resolvido por SQL no servidor.
- Ação entre fontes sem relação declarada é recusada com 422 e a regra quebrada; o estado dos seletores vai na URL, então o endereço copiado reabre o painel como estava.
- Medido: latência do gatilho até a ação de 0,054 ms no percentil 95 com 10.000 feições, contra teto de 100 ms no portão.

### L2-06-d-atualizacao-viva-sse (parcial)

- O ramo de lançamento entrega fluxo de eventos do servidor (SSE) apenas para tarefas: a rota `/api/eventos` existe e exige sessão, `/api/eventos/camadas` responde 404 e não há gatilho de notificação de camada em nenhuma migração desse ramo.
- O trabalho completo — gatilho por comando na tabela da camada, fluxo por camada, painel que assina e mostra a hora da última atualização, reconexão que recupera o que passou — existe numa trilha separada de 43 arquivos que não está mesclada.
- O que foi medido nessa trilha: 0,0005 segundo entre a gravação no banco e o quadro no consumidor, contra o teto de 1 segundo do portão, e uma rajada de mil eventos vira uma única consulta.

### L2-06-e-estatisticas-servidor (parcial)

- Calcula no servidor as estatísticas que os painéis e os serviços mostram (soma, média, percentil, contagem distinta, agrupamento com filtro de grupo), com faixa de mês resolvida no fuso de São Paulo, e alimenta também o parâmetro `outStatistics` do serviço compatível com Esri.
- Medido: 1 milhão de linhas agrupadas por 100 categorias com p95 de 113 ms, contra o teto de 500 ms do portão, com a máquina livre.
- As seis cláusulas do portão passam no ramo próprio; falta a junção desse ramo no tronco.

### L2-07-b-formulario-de-coleta-xlsform (parcial)

- Importa uma planilha XLSForm e a transforma em item de formulário do catálogo, cria a camada de destino e uma camada filha por bloco de repetição, e traduz as regras de relevância, restrição, cálculo e filtro de lista para a linguagem de expressão da casa, com tabela de equivalência que declara o que ficou de fora.
- A tela `/coleta` desenha os campos, incluindo lista em cascata de três níveis, guarda rascunho a cada mudança e envia; o servidor recalcula, reaplica relevância e restrições e só então grava a feição, e cálculo com dependência circular é recusado com erro 422 na importação e no navegador.
- Conferido com 102 vetores nos dois avaliadores, com o motor em JavaScript devolvendo o mesmo resultado do motor em Python. Ficam fora desta fatia: leitura de posição por GPS, foto, áudio, assinatura, código de barras e fila para uso sem rede.

### L2-07-e-odk-central-ponte (parcial)

- Publica no ODK Central a mesma planilha de formulário usada na coleta própria, puxa os envios por OData com os anexos e grava tudo pela porta única de escrita, com as regras do formulário reavaliadas no servidor.
- A repetição é barrada pelo identificador de envio do ODK: sincronizar três vezes deixa 20 feições e nenhuma duplicata; envio recusado fica gravado com o motivo.
- Falta para o item ficar completo: a prova contra um ODK Central de verdade; o que existe foi provado contra um dublê HTTP da API documentada, porque a instalação do Central aqui depende da decisão D29.

### L2-08-a-leitor-portal-inventario (parcial)

- Lê, sem escrever nada, o inventário de um Portal for ArcGIS ou ArcGIS Online: itens, dados e recursos do item, itens relacionados, grupos com membros, usuários e contagem de feições dos serviços hospedados, como tarefa que retoma do ponto gravado depois de corte de rede.
- Classifica cada item em migra, migra parcial ou não migra pelo tipo, e tipo fora da tabela vira "desconhecido", nunca suposição; a tabela de usuários não tem coluna de e-mail, nome ou telefone, então o dado pessoal devolvido pelo portal não tem onde ser gravado.
- Sete achados de segurança do adversário foram corrigidos, entre eles a credencial que só viaja para a origem do portal configurado e a neutralização de fórmula no relatório em CSV.
- A prova contra um portal real depende de credencial de parceiro e não foi feita: hoje só há prova contra servidor de teste.

### L2-09-c-modelos-gltf-ifc-3dtiles (parcial)

- Põe modelo tridimensional no mapa por três caminhos, sem biblioteca com licença AGPL: glTF binário posicionado por longitude, latitude, altura, rotação e escala; arquivo IFC lido em Python puro, com elementos, pavimento e propriedades em tabela própria; e conjunto de tiles no formato OGC 3D Tiles 1.1 gerado do glTF.
- Medido: a caixa desenhada pelo navegador difere 0,097 m da calculada pelo servidor, contra a folga de 0,5 m do portão; o validador oficial de 3D Tiles aponta 0 erro e 0 aviso e reprova o controle negativo; a cena desenha a 58,7 quadros por segundo sem placa de vídeo; um IFC sintético de 50 MB com 62.038 elementos converte em 19,4 s com pico de 679 MB.
- Modelo que depende de arquivo externo, como textura fora do pacote, é recusado no servidor e no navegador. O consumo do conjunto de tiles pelo ArcGIS Pro segue pendente de decisão do dono, e o formato i3s fica fora, declarado.

### L2-09-d-analise-3d-visibilidade (parcial)

- Oferece quatro análises de terreno por rota própria: linha de visada, bacia visual, perfil de elevação e sombra, sobre uma grade de alturas enviada no corpo do pedido, com resumo criptográfico do terreno em toda a procedência.
- A bacia visual não é reimplementada: a casa grava o arquivo e chama o programa `gdal_viewshed` instalado, devolvendo os bytes dele e a linha de comando usada, conferida byte a byte em relevo suave e íngreme.
- Medido: ponto de obstrução a 2,75 metros do cruzamento verdadeiro, contra tolerância de 30 metros do portão, e sombra com desvio de 0,268 % contra a fórmula, contra tolerância de 5 %. Corte de malha e análise de malha integrada ficam fora do item.

### L2-10-c-linguagem-expressao (parcial)

- Núcleo da linguagem de expressão (equivalente ao Arcade): 18 funções, dois avaliadores (Python e JavaScript) que concordam byte a byte em 41 casos de teste, sem `eval`/`exec` em nenhum dos dois; dois ataques de pilha achados e fechados.

### L2-10-d-regras-de-atributo (parcial)

- Cada camada pode declarar regras de atributo: cálculo (campo alvo igual a uma expressão, com gatilho, ordem e encadeamento), restrição (falso recusa a edição com código e mensagem escolhidos) e validação em massa como tarefa, que grava os erros numa camada de erros do catálogo.
- As regras rodam no caminho único de escrita, campos virtuais são avaliados na leitura, e ciclo entre regras é detectado na configuração; 100 mil feições foram validadas em 3,45 s e 1.000 edições com 3 regras custaram 1,11 vez o tempo sem regras.
- Falta para o item ficar completo: a tela de configuração das regras, a compilação para SQL e a edição por WFS-T.

### L2-11-a-geocodificacao-csv (parcial)

- Geocodifica um arquivo de endereços em lote e mede o acerto contra dado aberto: em 1.000 endereços de um município, 95,0% saíram com acerto de número exato a até 50 metros, contra o piso de 85% do portão, e 0% caiu fora do município.
- O lote de 1.000 endereços leva 8,5 segundos, depois que dois índices novos acabaram com a repetição da busca por via a cada linha; ponto que caiu no centroide do município é sempre marcado como tal, nunca entregue como endereço encontrado.
- O item está com a suíte do geocodificador verde na trilha e aguarda decisão da fila de junção para entrar no ramo de lançamento.

### L2-11-b-geocodificador-brasil (parcial)

- Converte endereço em coordenada com base própria em PostgreSQL/PostGIS montada sobre o CNEFE 2022 do IBGE, sem depender de serviço externo; oferece busca, geocodificação reversa, sugestão enquanto se digita e um serviço compatível com o GeocodeServer da Esri.
- Medido sobre 50 endereços e 50 pontos reais do CNEFE: erro mediano de 0,0 m (portão pede até 30 m), acerto de número e face de 98,0 % (portão pede 90 %), reverso acertando o logradouro em 100 % e sugestão com p95 de 33,1 ms. A instalação de Roraima, a menor unidade da federação no CNEFE, ocupa 4,52 MB comprimidos e carrega em 10,4 s.
- Ambiguidade entre municípios é declarada e CEP incompatível com o município recusa com 422. O uso do serviço como localizador dentro do QGIS não foi provado nesta máquina, que não tem QGIS nem ambiente gráfico.

### L2-11-c-rota-matriz-isocrona (refutado)

- Rota, matriz e isócrona por um OSRM próprio e isolado (dado só de uma área de teste); isócrona por grade de pontos + envoltória côncava, já que o OSRM não tem isso nativo.

### L2-13-a-versoes-ramo-reconciliar (parcial)

- Permite marcar uma camada como versionada e abrir ramos de trabalho paralelos: ler no ramo mostra as edições dele sobre o padrão como estava quando o ramo nasceu, reconciliar lista as feições alteradas dos dois lados, resolver decide campo a campo e publicar leva as linhas para o padrão.
- As linhas do ramo moram em tabela companheira, e não em colunas novas da camada, de modo que nenhum caminho de leitura já existente precise lembrar de filtrar versão; a consulta aceita os parâmetros de versão e de momento histórico do protocolo Esri, e há um serviço de gerenciamento de versões com as operações do protocolo.
- Medido: reconciliar um ramo com 10 mil edições leva 29,6 segundos; 18 testes passam. Pendentes: conferência com o aplicativo de mesa da Esri e o teste de tela do comparativo, que só roda contra o endereço público.

### L2-13-b-replicas-sincronizacao (parcial)

- `POST /api/replicas` monta um recorte declarado de camadas e escreve um GeoPackage para trabalho sem conexão, com as tabelas de sincronização, geração e domínios dentro do próprio pacote.
- `POST /api/replicas/{id}/sincronizar` sobe as mudanças do aparelho pela porta única de escrita, resolve versão divergente pela política escolhida (servidor vence, cliente vence ou perguntar), baixa o que mudou no servidor e avança a geração; repetir o mesmo lote aplica zero.
- Falta para o item ficar completo: a prova com o aplicativo de campo num aparelho real; a forma do arquivo foi conferida pelo GDAL 3.8.4.

### L2-15-a-geoparquet-bucket-catalogo (parcial)

- Exporta camada para GeoParquet 1.1 no balde do inquilino e publica um item de catálogo com esquema, contagem, caixa envolvente por arquivo e sha256; a escrita pode ser em arquivo único ou particionada por coluna.
- Medido: 1.000.000 de polígonos exportados em 5,8 segundos, reabertos pelo DuckDB com a mesma contagem e diferença de área zero contra o PostGIS em 100 amostras; partição por unidade da federação gera exatamente 27 arquivos, e partição sem mudança não gera gravação nova.
- O modo arquivar só apaga a tabela de origem depois de conferir, na mesma transação, que a contagem no arquivo bate com a contagem apagada.
- Rebaixado a parcial pelo coordenador: a leitura pelo QGIS não foi medida e a URL assinada vencida responde 404, não o 403 que o texto do portão pedia.

### L2-16-c-script-vira-ferramenta (parcial)

- Transforma um script Python em ferramenta do catálogo: o cabeçalho do script declara nome, título, parâmetros e saídas, é validado antes de gravar, e o script vira item versionado. O formulário mostrado ao usuário é derivado só do cabeçalho, e o corpo do script não sai por ele.
- A execução valida os valores antes de enfileirar, confere que todo item de entrada existe no inquilino, congela versão e sha256 no pedido e roda o retrato imutável daquela versão dentro do contêiner do inquilino, com teto de tempo. A saída vira item com procedência que aponta a ferramenta, a versão e o sha256 do script.
- Provado que o script não alcança a rede, não lê `/etc`, não escreve sem permissão e não sobrevive ao teto de tempo, e que publicar versão nova não altera execução passada. Falta a cláusula de chamar a ferramenta pelo `submitJob` do serviço de geoprocessamento, que vive em outro ramo.

### L3-01-a-modelo-dado (refutado)

- Modelo de dado do motor multicritério: 207 testes, hash independente confere, isolamento cruzado A→B provado.

### L3-01-b-unidades (parcial)

- Grade de unidades de análise do motor multicritério: 250 m/2.000 km² em 1,14 s com 1,175% de desvio — 1 milhão de células ainda não gerado de verdade (250.986 medidas, o resto extrapolado).

### L3-01-c-extracao-fator (parcial)

- Extrai o valor de cada fator para cada unidade de análise do motor multicritério, tanto de raster (média por zona) quanto de vetor (área, comprimento, fração e distância), e grava a cobertura de cada fator, sem transformar valor ausente em zero.
- Os resultados foram conferidos contra recomputação independente em 200 unidades: média por zona com divergência máxima zero, área e comprimento dentro de 0,5 %, fração ponderada por área e não por centroide, e distância igual à referência geodésica em 50 unidades; raster sem sistema de coordenadas e camada vazia abortam o trabalho com erro nomeado.
- A cláusula de tempo do portão — 12 fatores sobre 73 mil células — não foi medida: a execução estourou o limite de 600 segundos na máquina compartilhada.

### L3-01-d-transformacoes (parcial)

- Transforma valor bruto em favorabilidade de 0 a 100 por 16 tipos de transformação (categoria, faixas com quatro métodos de quebra, linear, degraus e as doze funções contínuas equivalentes às do ArcGIS Pro), com a mesma conta escrita em Python e em SQL e diferença máxima de 0,01 entre as duas.
- A pré-visualização mostra o histograma de entrada e o de saída em 15 a 33 ms para 100 mil valores, e o manual traz a fórmula e o gráfico de cada função, gerados por script.
- Falta para o item ficar completo: a reprodução do motor logístico de referência, em que 4 dos 19 fatores batem em 100 % das células e os outros 15 ficam fora de escopo por motivo nomeado, e a medição da cláusula de desempenho com a máquina sem carga alta.

### L3-01-e-combinacao (entregue)

- Combina os fatores já transformados numa nota de favorabilidade por unidade de análise, com oito combinadores declarados: soma ponderada normalizada (padrão), soma percentual que fecha 100, média geométrica, mínimo, máximo, produto, soma e gama difusos.
- Ausência de dado é tratada como ausência, nunca como zero, e o veto é objeto separado do peso: entra como fração vetada e multiplica a nota, de modo que fração 1 zera a nota e grava o motivo.
- O recálculo de 4.346 unidades por 19 fatores leva 1,493 ms no servidor (teto de 50 ms) e 1,625 ms na versão que roda no navegador (teto de 20 ms), e todo resultado carrega a frase de que os pesos são escolhidos pelo usuário, não medidos.

### L3-01-f-explicacao (parcial)

- Responde por que uma unidade recebeu determinada nota no motor multicritério: tabela de fator, valor bruto com unidade e fonte, transformação aplicada, favorabilidade, peso e contribuição, mais a soma, o veto com o motivo e a cobertura.
- A explicação é recalculada a partir dos valores brutos no momento do pedido, nunca lida de uma tabela de explicação gravada, e usa o mesmo combinador do cálculo. Medido em 100 unidades sorteadas: a diferença entre a soma das contribuições e a nota gravada fica em 0,5 ou menos.
- Quando o combinador é do tipo difuso, a explicação mostra a favorabilidade de cada fator sem apresentar uma soma que não existe. A latência não foi medida e o teste de ponta a ponta não correu inteiro, por falta de servidor web na trilha.

### L3-01-g-tela-motor (parcial)

- Abre a tela `/amc/motor`, onde o usuário monta o modelo (camada mais extrator mais transformação, com pré-visualização do histograma sobre os valores já extraídos), marca restrições como veto separado do peso e escolhe o peso de cada fator por controle deslizante ou percentual com trava.
- Movida a barra de um peso, a tela recombina as notas no próprio navegador, sem nova chamada à interface de programação, recolore o mapa pela rampa declarada e abre a explicação fator a fator de cada unidade; o rótulo usado é sempre "pesos escolhidos pelo usuário".
- Os pesos viajam no endereço, e a tela recusa endereço adulterado (peso acima do máximo, fator inexistente, soma fora de 100), deixando o mapa vazio com a razão escrita. Pendente: o teste de tela completo, que exige o servidor de borda.

### L3-01-h-presets (entregue)

- A tela `/amc/presets` cria, edita, apaga, exporta e importa conjuntos de pesos nomeados do motor multicritério, com cinco conjuntos integrados somente de leitura que nascem com o schema, entre eles o de pesos iguais.
- Aplicar um conjunto (`POST /api/amc/presets/{id}/aplicar`) recebe a matriz, roda a combinação na mesma requisição e devolve o resultado, sem criar trabalho de fila.
- O conjunto de outro inquilino responde 404, provado na varredura cruzada entre dois inquilinos nas rotas de leitura, alteração, exclusão e aplicação; a importação recusa com 422 o conjunto que cite fator fora do modelo informado e nomeia o que falta.

### L3-01-i-exportacao-metodo (parcial)

- Exporta o método do motor multicritério como documento JSON canônico (`plat/amc_metodo`) com pesos, vetos, combinador, transformações, camadas de entrada com sha256 e o sha256 do próprio documento; documento alterado depois da exportação é recusado na importação.
- Gera também um relatório em PDF determinístico com uma seção por página; um teste extrai cada número do PDF e exige que ele exista no JSON — foram 23 números conferidos em 8 páginas.
- Falta para o item ficar completo: o registro do veredito do item inteiro; as cláusulas do portão estão medidas.

### L3-02-b-sensibilidade-sobol-oat (parcial)

- Mede a sensibilidade do modelo multicritério de duas formas: índices de Sobol de primeira ordem e total sobre pesos e parâmetros, com amostra de Saltelli, semente gravada e intervalo por reamostragem; e tornado um fator por vez, que move o peso de cada fator de −50% a +100% e mede quanto a lista dos melhores muda.
- A função de teste de Ishigami, que tem índices de forma fechada, é reproduzida com desvio máximo de 0,0004, contra a tolerância de 0,05 do portão; o relatório de um modelo de 2.000 unidades por 6 fatores levou 1,295 segundo.
- O relatório diz, em texto, que a medida é de dependência do modelo ao peso escolhido, não de importância real do fator.

### L3-02-c-smaa (entregue)

- O trabalho de fila `amc.smaa` responde de que pesos uma unidade precisaria para vencer: para cada unidade calcula a fração dos sorteios de peso em que ela ficou em cada posição até a vigésima, o vetor central de pesos que a põe em primeiro e um fator de confiança.
- A implementação segue o SMAA-2 de Lahdelma e Salminen (2001) e reutiliza o sorteio de pesos e o combinador já existentes, sem rota nova de interface de programação.
- A prova é de resposta conhecida: três unidades sintéticas com dois fatores dão, na conta a mão, 0,5 / 0,5 / 0 de aceitabilidade em primeiro lugar e vetor central (0,75; 0,25); com 20 mil sorteios o motor devolveu 0,5046 / 0,4955 / 0 e (0,7501; 0,2499).

### L3-05-localizar-regioes (parcial)

- Responde onde ficam as N áreas contíguas de maior favorabilidade, e não apenas quanto vale cada célula: cresce cada região por fila de prioridade a partir de sementes espalhadas, com compromisso declarado entre forma (círculo, quadrado ou hexágono) e utilidade, área total alvo, área mínima e máxima por região e distância mínima e máxima entre regiões.
- `POST /api/multiescala/execucoes/{id}/regioes` devolve um polígono por região com as estatísticas. Medido: grade de 1 milhão de células em 3,42 s para 3 regiões e 9,09 s para 10; sobre a superfície de teste com 3 picos, as 3 regiões saem a 0,03 célula dos picos, com área a 0 % de diferença do alvo e compacidade de 0,98 ou mais.
- Célula sem dado ou vetada é intransponível. Estão implementadas 3 das 7 formas e 4 dos 8 métodos de avaliação, e o item não tem tela própria.

### L3-06-criterios-de-feicao (parcial)

- Permite que a unidade de análise seja a feição do próprio usuário, com quatro critérios: atributo numérico da feição, contagem de pontos de outra camada num raio, contagem dentro do polígono e distância ao ponto mais próximo.
- A influência de cada critério é declarada pelo usuário como positiva, inversa ou ideal, e o filtro de inclusão por faixa tira a feição da comparação sem tratá-la como vetada; a tela mostra o ranque, o histograma por critério e a matriz de correlação entre critérios, e a exportação sai em CSV.
- Medido sobre dado aberto: 1.000 feições por 4 critérios em 131,7 milissegundos, com a contagem em raio conferida feição a feição contra a função do PostGIS, sem divergência. O teste de tela foi escrito mas não rodou na trilha.

### L3-07-agregacao (entregue)

- Leva o resultado do motor multicritério da célula da grade para qualquer feição (imóvel, lote, município ou setor) por interseção de área, com média por fator ponderada pela área, fração vetada, veto principal e recombinação opcional pelos pesos do modelo.
- Feição que não toca célula nenhuma sai marcada como sem célula, nunca como zero.
- Medido contra um motor logístico de referência, só leitura: 10 fatores comparáveis reproduzidos em 100 % das 4.346 feições dentro de 0,5, e o veto principal em 99,65 %, acima do piso de 99,5 % do portão.

### L3-08-pareto (parcial)

- Calcula a fronteira de Pareto, isto é, quais unidades podem ser as melhores para qualquer escolha de peso, com 2 a 4 objetivos, direção declarada por objetivo e ordenação em primeira, segunda e terceira fronteiras.
- A ordenação foi conferida contra um laço ingênuo escrito do zero no teste, em 2.000 unidades e cinco combinações de objetivos: ordem idêntica unidade a unidade; unidade com objetivo ausente fica fora da ordenação, nunca com zero no lugar do que falta.
- Duas rotas devolvem a ordem por unidade e a fronteira como camada em GeoJSON, e a tela liga gráfico de dispersão e mapa: selecionar um retângulo no gráfico realça no mapa exatamente aquelas unidades.
- A prova pelo navegador do arrasto no gráfico está escrita e não foi executada na trilha.

### L3-09-backtest-decisao-real (parcial)

- Compara o ranking de uma execução do motor multicritério com escolhas que já aconteceram: percentil das escolhas, distribuição nula por permutação, área sob a curva com valor-p de uma cauda, e preferência revelada por fator (sinal e ordem, nunca peso).
- Medido sobre dado aberto — 602 galpões do OpenStreetMap com área acima de 5.000 m², grade de 500 m, modelo de um fator: área sob a curva 0,718, percentil mediano 74,8 e valor-p 0,002 em 500 permutações; escolhas geradas pelo próprio modelo dão 1,000 e escolhas ao acaso 0,4993.
- As ressalvas ficam no corpo do relatório, não em rodapé: concordância com o passado não é acerto futuro, a distância confunde, e camada mais nova que a decisão sai marcada como anacrônica. O item não tem tela própria.

### L3-10-corredor-custo-minimo (parcial)

- Traça o corredor de custo mínimo entre dois pontos sobre a superfície do motor multicritério e devolve, na mesma resposta, a linha, o corredor e o manifesto com a superfície declarada, os parâmetros e as medidas.
- A reprodução do trecho de referência da casa foi medida: a superfície sai igual byte a byte à da rodada oficial, a rota fica a 100,0 metros da oficial pela distância de Hausdorff (uma célula de 100 metros) e o trecho de 382,4 quilômetros é traçado em 5,8 segundos, contra teto de 10 segundos.
- A tela que escolhe os dois pontos no mapa fica para a parcela de interface.

### L3-14-cobertura-dado-ausente (entregue)

- O motor multicritério mede, para cada fator, a fração de unidades de análise com dado válido e, quando a área da unidade é informada, a fração de área do território com dado válido.
- Fator com cobertura abaixo do limiar declarado, 80 % por padrão, sai marcado no relatório em vez de ser removido ou escondido.
- Ausência de dado nunca vira zero nem cem na cobertura: a conta usa só a máscara de valores finitos e não toca no valor do fator, que é trabalho da combinação.

### L3-15-metadado-fator (entregue)

- Cada fator do motor multicritério carrega uma ficha com fonte, versão da fonte, unidade, direção, base (norma, engenharia ou preferência), marca de indicador indireto com teto de peso, classe de peso, origem da âncora de peso e o que o fator não sustenta.
- O teto do indicador indireto é regra e não texto: a fatia de peso do fator sobre a soma dos pesos não pode passar do teto declarado, e a recusa sai 422 tanto no documento do modelo quanto nos pesos de uma execução, nomeando o fator, a fatia medida, o teto e o peso que caberia.
- O relatório e a explicação por unidade trazem a ficha de cada fator, a lista de indicadores indiretos e a lista de âncoras, com âncora não declarada registrada como terceira categoria, nunca convertida em escolhida.

### L3-16-desempenho-escala (entregue)

- O contrato de escala do motor multicritério está num módulo só: a combinação roda no navegador até 50.000 unidades e no servidor acima disso, em blocos de 50.000, e o plano é recusado antes de entrar na fila quando não cabe em unidades, fatores, memória ou prazo.
- Medido em 07/09/2026: a recombinação no servidor de 1 milhão de unidades por 15 fatores levou 0,9734 s contra o limite de 5 s do portão, com pico de 70,26 MB de memória em 20 blocos; a combinação de 50.000 por 15 no navegador levou 21,18 ms.
- Uma cláusula foi refutada e fica registrada: à taxa medida da estatística zonal, extrair 1 milhão de células por 15 fatores levaria 10.483,9 s contra os 1.800 s do portão, então o motor recusa esse plano e o limite honesto de hoje é uma grade de 166.898 unidades com 15 fatores.

### L3-19-multiescala (entregue)

- Roda o motor multicritério em duas grades ligadas: `POST /api/multiescala/conjuntos/{id}/macro` calcula a grade grosseira sobre a área de estudo inteira e `POST /api/multiescala/execucoes/{id}/micro` gera a grade fina somente dentro das células aprovadas na etapa anterior.
- `GET /api/multiescala/execucoes/{id}` devolve o relatório por fator com a escala da fonte, a escala da grade e a razão entre as duas, calculadas pelo servidor — o cliente não envia esse campo.

### L3-20-narrativa-de-resultado (parcial)

- Escreve o resumo textual do resultado do motor multicritério por modelo de frase puro sobre o documento do método, sem modelo de linguagem, sem banco e sem relógio: uma ideia por frase, e todo número com o universo a que se refere.
- A função de revisão marca no próprio texto número sem origem em campo do documento, termo da lista proibida pela regra de escrita da casa e pontuação proibida; o texto gerado passa com zero marcações e uma frase fabricada é marcada.
- Cada narração leva 0,02 ms, e a conferência à mão do texto de três unidades está registrada no arquivo de medidas.

### L6-01-a-registro (refutado)

- Registro do acervo da casa exposto ao catálogo — só fontes com licença escrita aparecem.

### L6-01-b-view-so-leitura (parcial)

- Publica camada do acervo da casa sem copiar dado: cada camada exposta vira uma view em schema próprio, com só as colunas da lista branca e um porteiro no filtro que exige assinatura do inquilino. Sem assinatura a view devolve zero linha e a API responde 403.
- A role da aplicação não recebe privilégio nenhum nas tabelas de origem, provado no banco: consulta direta à tabela original é negada, escrita na view é negada, e a varredura do catálogo do Postgres não encontra concessão direta. A consulta de mapa por caixa envolvente responde em 1,5 ms de mediana sobre 8.406.837 linhas contadas exatamente.
- Duas hipóteses caíram na medição e estão no registro de decisão: a view não pode ser do tipo que herda o chamador, e a marcação de barreira de segurança derruba o índice espacial. Falta ligar a publicação ao servidor de tiles e ao mapa, que ainda não existem nesse ramo.

### L6-01-d-ficha-fonte (parcial)

- Ficha de procedência por fonte do acervo: 10 campos, endpoints confirmados/vivos e nota de completude x/10 — campo ausente nunca é fabricado.

### L6-01-f-lgpd (refutado)

- Gate de LGPD no acervo: fonte com PII identificável (achada por varredura manual de 219 tabelas) exige confirmação explícita de risco antes de entrar no catálogo, senão recusa com 409.

### L6-01-g-licenca-curada (parcial)

- Licença curada do acervo: 29 fontes com licença ESCRITA testada por HTTP ao vivo (URL, evidência literal, confiança), amostra de 10 reconfirmada por curl independente; as que faltam (piso do portão é 40) ficaram de fora por motivo nomeado — sem termo escrito de verdade, não por atalho.

### L6-01-h-frescor-verificacao (entregue)

- Roda um trabalho semanal que verifica o frescor de cada camada exposta do acervo da casa: contagem exata de linhas com prazo de 25 segundos, resumo criptográfico do conteúdo quando existe comando de reexecução declarado, e teste HTTP dos endereços confirmados, com teto de 40 por rodada.
- Contagem que estoura o prazo é gravada como "não contado no prazo", nunca como zero, e a ficha do acervo e o mapa mostram o mesmo selo de verificação vencida com o motivo: endereço morto, prazo da fonte vencido, nunca verificada ou verificação com mais de 14 dias.
- As rotas expõem a lista de camadas com filtro de vencidas, as 12 verificações mais recentes de cada camada, as variações de contagem acima de 5 % e o histórico de execuções.

### L6-01-i-raster-e-arquivos (parcial)

- Expõe ao catálogo os arquivos do acervo da casa pela vista `plat.acervo_arquivo` e pela rota `GET /api/acervo/arquivos`: 321 arquivos com sha256, dos quais 26 são imagens.
- `POST /api/acervo/arquivos/expor` confere o sha256 antes de qualquer escrita; a imagem passa a servir ladrilho por token lida onde está, sem copiar byte, e o vetor é carregado uma vez para o PostGIS. Arquivo acima de 2 GB e lote acima de 3 GB são recusados, por causa do limite de disco.
- Falta para o item ficar completo: nenhuma das 27 fontes de arquivo tem licença escrita, então cada item nasce privado e marcado como de uso restrito.

### L6-02-a-modelo-conexao-e-seguranca (entregue)

- Modelo de conexão externa (WMS/WFS/STAC/etc.) com defesa contra SSRF: IP privado, localhost e redirecionamento para rede interna são recusados na criação, não só no uso.

### L6-02-c-wfs-ogcapi (entregue)

- Conecta a serviços WFS 2.0 e OGC API Features de terceiros e lê suas coleções; provado contra dois serviços públicos vivos, um deles com 9.708 coleções.
- Copia uma camada externa para dentro do produto: 50 mil feições em 10,19 segundos, em 10 requisições paginadas, com os tipos de atributo preservados.
- Serviço que anuncia 5 milhões de feições e não pagina faz a cópia parar no limite declarado e avisar, em 7,46 segundos, sem travar o processo de trabalho.

### L6-02-i-google-sheets (parcial)

- Lê planilha do Google Sheets como camada do inquilino e a atualiza periodicamente; a credencial da conta de serviço nunca aparece em registro de log, e planilha que deixa de responder mostra falha na atualização em vez de dado velho apresentado como novo.
- A cláusula que faltava, a rodada completa dos 8 testes da suíte de conexão, fechou em duas execuções consecutivas. A causa da falha anterior foi medida e corrigida: dois processos do trabalhador criavam o mesmo schema ao mesmo tempo, e a função passou a serializar por trava de aviso por inquilino.

### L6-02-l-saude (parcial)

- Saúde de conexão externa: histórico das últimas 30 verificações, estado agregado (ok/degradado/fora/nunca testada), reteste automático a cada 15 min de qualquer conexão parada ou nunca testada, tela própria com selo ao vivo e botão "testar agora".

### L6-02-m-catalogo-endpoints-brasil (parcial)

- Mantém um catálogo de endereços públicos de serviços geográficos, retestado por um trabalho semanal, e permite adicionar qualquer um deles como conexão do inquilino em um clique, já com a ficha de procedência.
- A verificação exige o documento do protocolo para considerar o endereço vivo: resposta 200 que traga página HTML ou erro do servidor conta como fora do ar, e a entrada morta sai da lista principal.
- Medido em 7 de setembro de 2026: 78 endereços vivos de 100 candidatos, com 29 endereços que nunca existiram removidos da semente.

### L6-02-o-importacao-exportacao-formatos (parcial)

- `POST /api/intercambio/exportacoes` acrescenta quatro formatos de saída aos onze já existentes (GeoJSON Sequence, File Geodatabase em zip, MBTiles e PMTiles) e, no modo inquilino, gera a saída completa: todas as camadas vetoriais num GeoPackage com manifesto de esquema, campos, contagem e sha256 por camada.
- Antes de gerar, a exportação escreve o que o formato de destino vai fazer com os campos — nome truncado em dez caracteres, data virando texto, texto cortado em 254 caracteres, inteiro longo virando número real.
- Falta para o item ficar completo: a importação não ganhou formato novo, e a abertura do File Geodatabase foi provada pelo driver do GDAL, não pelo aplicativo de desktop.

### L6-03-paridade-conectores (parcial)

- Mantém em `docs/PARIDADE.md` a comparação, linha a linha, entre os conectores do produto e os tipos de camada e fontes de dado do Map Viewer da Esri, com 35 linhas classificadas em feito, parcial ou fora, cada uma apontando o arquivo de teste e o ramo onde ele vive.
- Um teste automatizado reprova linha marcada como feita cujo teste não exista, e as 20 URLs de referência são testadas por script, com a data da verificação registrada.
- O adversário provou duas linhas falsas: duas exclusões diziam decorrer de decisão do dono sem que decisão nenhuma cobrisse o assunto; as linhas foram corrigidas para declarar que nenhum item e nenhuma decisão cobrem a exclusão, e a trava passou a exigir essa nomeação.
- Nove linhas não puderam ser reproduzidas pelo adversário por falta de configuração nos outros ramos.

### L6-05-proveniencia-camada-externa (refutado)

- Ficha de proveniência de camada externa: lê a licença de verdade que cada serviço declara (WMS/WFS, ArcGIS REST, STAC/OGC API) e publica no catálogo com o crédito exato do serviço — provado com dois serviços vivos que declaram licenças diferentes.

### L6-06-descoberta-csw (parcial)

- Busca no catálogo CSW 2.0.2 da INDE por texto e por caixa envolvente e cria a conexão WMS, WFS ou WMTS num clique, já com a ficha de procedência preenchida a partir do registro ISO do catálogo.
- Registro que declara protocolo mas não traz endereço de serviço responde 422 com o motivo e não cria conexão vazia. Toda busca passa pelo cliente HTTP com defesa contra requisição forjada para rede interna, teto de 1 MiB e 20 s, e o XML é lido por analisador que não resolve entidade externa.
- Medido contra a INDE: 52 registros para um termo de busca, 2 conexões criadas de um mesmo registro, as duas respondendo. Cinco endereços de catálogo estadual tentados não resolveram: só a INDE está verificada.

### L4-15-serie-temporal-da-rede (parcial)

- Compara safras sucessivas da base de rede elétrica e classifica cada identificador de elemento em quatro classes de linhagem, exporta a tendência por transformador em CSV, calcula crescimento por alimentador e oferece um controle deslizante de safra no mapa.
- A potência declarada da placa é marcada como não confiável quando a série mostra troca em massa, seguindo a regra medida da casa.
- Conferido em duas safras reais contra recontagem independente dos arquivos de origem, com 24 testes passando. A escala completa da distribuidora não foi medida: a importação não terminou em 45 minutos, limitada pelo item de importação.

### L4-20-consumidores-e-enderecos (parcial)

- Modela a ponta da rede elétrica em seis tabelas com RLS (trechos de média e baixa tensão, transformadores, unidades consumidoras, consumo anual e endereços do censo) e cinco rotas em `/api/rede/consumidores`, sem nenhum campo que identifique pessoa e com consumo apenas agregado, com mínimo de cinco unidades.
- A camada de endereços sem rede num raio de 700 m deu 10.914 endereços contra 10.911 da camada de referência da casa, diferença de 0,03 %, gerada em 6,4 s; os consumidores a jusante de 44.268 trechos de média tensão saem em 3,6 s.
- Falta para o item ficar completo: esse trabalho está num ramo que ainda não foi juntado ao tronco de lançamento.

### L4-27-curto-circuito-e-protecao (entregue)

- Calcula a corrente de curto-circuito de cada barra do alimentador, trifásica e fase-terra, sobre o mesmo modelo em memória que alimenta os exportadores para OpenDSS e pandapower, e entrega o resultado como tabela e como camada de pontos.
- Para cada barra informa o dispositivo de proteção a montante e o veredito de coordenação contra a faixa de interrupção cadastrada: interrompe, abaixo da faixa, acima da capacidade ou sem dado.
- As premissas voltam gravadas em toda execução (potência de curto da fonte, relação X/R, fator de tensão, sequência zero e base de potência), e fonte sem potência de curto declarada, ou com potência zero, é recusada, porque impedância nula daria corrente infinita.
- Medido num alimentador real da cooperativa de teste: 192 barras entre 6.442 e 10.982 ampères em 0,205 segundo; 191 das 192 barras saíram sem dado de coordenação, porque o arquivo da distribuidora não traz faixa de interrupção e nenhuma faixa foi suposta.

### L4-29-regras-de-atributo-de-rede (parcial)

- Define três perfis de regra sobre a rede: cálculo, que escreve um atributo; restrição, que responde se uma manobra é permitida, com a chave entre 13,8 kV e 34,5 kV sendo recusada; e validação, que lista em lote os casos irregulares, como transformador sem unidade consumidora.
- A linguagem de expressão ganhou seis funções de rede nos dois avaliadores. Uma rodada avalia cada regra uma vez por objeto, sem ponto fixo, de modo que a regra com laço de jusante não se repete; profundidade excessiva é recusada na criação, e a restrição falha fechada, recusando quando a avaliação dá erro.
- O trabalho está num ramo que ainda não foi trazido para o ramo da demonstração: ele diverge 336 commits atrás e toca os avaliadores de expressão, compartilhados por toda a plataforma.

### L4-parcelas-01-modelo-de-parcelas (parcial)

- Modela a malha de parcelas orientada a registro em seis tabelas por inquilino: o documento de registro, ponto com precisão declarada, linha com rumo, distância e raio com sinal, divisa partilhada entre parcelas, a parcela por tipo (lote, gleba, quadra, servidão, estrato) com área declarada, área calculada e erro de fechamento, e a conexão entre parcelas.
- Retirar uma parcela é ato de registro e não apaga nada: a parcela sai do conjunto atual e entra no histórico com o registro, a linha exclusiva sai junto e a linha partilhada permanece; a sobreposição entre parcelas ativas do mesmo tipo é validada por consulta com tolerância de 1 centímetro quadrado.
- A importação foi medida com 11.473 lotes de um SIG de teste interno, com dado aberto e registro sintético; nenhum documento real e nenhum nome de pessoa entram no modelo.

### L4-parcelas-02-fluxos-cogo (parcial)

- Edita malha de parcelas com os fluxos da referência: dividir por rumo (área igual, proporção ou faixas de largura fixa), dividir por linha de corte, unir, recortar, construir parcelas a partir de linhas livres, sementes, duplicar e atribuir feição a registro.
- A poligonal de levantamento (traverse) mostra o erro de fechamento em vez de fechar em silêncio, e uma fachada REST no formato do ParcelFabricServer expõe esses fluxos; o leitor de DXF em texto fecha 125 faces a partir de 557 segmentos de uma planta de teste.
- Falta para o item ficar completo: o ramo com esse trabalho não está juntado ao tronco, e as capturas de tela não são possíveis nesta máquina, onde o navegador sem interface gráfica quebra.

### L4-parcelas-03-ajuste-e-qualidade (parcial)

- Ajusta a malha de parcelas por mínimos quadrados e gera a camada de qualidade com lacunas, sobreposições, área declarada contra calculada e erro de fechamento.
- Na malha sintética de 30 nós, 98 observações e 3 pontos de controle, as coordenadas ajustadas reproduzem a solução analítica a 1 milímetro; um erro de 1 metro plantado numa linha de 100 metros vira a suspeita principal pelo resíduo e, excluída a linha, a rede reconverge.
- Analisar não escreve nada, provado por soma de verificação; aplicar move o ponto, recompõe linha e face e grava a versão.
- Nada disso está no ramo de lançamento: o trabalho vive numa trilha separada, 355 mudanças atrás e 45 à frente do ramo de lançamento, e essa trilha estava em uso por outra sessão no dia da medição.

### L5-05-documento-versoes (entregue)

- Modelo genérico de documento de construtor (grafo com nó imutável por ULID), sobre o mesmo mecanismo de versão do catálogo; hash canônico verificável fora do banco — o hash nativo do Postgres não era reproduzível externamente.

### L5-06-motor-widgets (parcial)

- Monta a aplicação a partir de um registro de componentes com manifesto validado na conferência do repositório: seis componentes básicos, entre eles mapa, legenda, tabela, texto, botão e filtro. A página só carrega os módulos citados no documento, medido em 3 módulos.
- Componente de tipo desconhecido, configuração fora do esquema ou módulo ausente do disco desenham uma caixa de erro nomeada, em vez de derrubar a página. Medido: 1,32 kB por componente e primeira pintura em 48 ms.
- O motor está pronto no ramo próprio e aguarda a junção no tronco.

### L5-07-fontes-vistas-mensagens (parcial)

- Dá ao documento de aplicativo três peças: fontes (item do catálogo, caminho do servidor ou dado embutido), vistas (fonte com filtro, seleção, ordenação e campos) e mensagens, que ligam um gatilho de um componente a ações em outro.
- Relação entre fontes diferentes é exigida e declarada: sem ela, a ligação é recusada no construtor com mensagem e na interface de programação com erro 422, pelo mesmo validador rodando em JavaScript e em Python. O barramento corta ciclo em uma volta e avisa, e a seleção e os filtros ficam no endereço da página.
- Medido: da mudança do gatilho até a ação, 1,4 milissegundo no percentil 95 com 10 mil feições em memória, contra teto de 100 milissegundos.

### L5-08-editor-arrasto (entregue)

- Oferece um editor de arrasto próprio em `/construtor?item=<id>`, sem nenhuma biblioteca de arrasto de terceiro: paleta para a tela, tela para tela, alça de largura, árvore de estrutura, painel de propriedades gerado do JSON Schema do tipo e menu de mover para quem usa só toque ou teclado.
- O mesmo layout de cinco componentes montado só por arrasto e só por teclado grava documentos idênticos, e a largura é sempre gravada em colunas da grade de doze, nunca em pixel.

### L5-09-desfazer-refazer-rascunho (entregue)

- Desfaz e refaz a edição no construtor por pilha de alterações com o passo direto e o inverso, com atalho de teclado, agrupando alteração contínua num passo só.
- Salva rascunho no servidor e também no navegador: queda da interface de programação durante a edição deixa a cópia local marcada como pendente, e reabrir a tela oferece recuperar o rascunho que nunca chegou ao servidor.
- Compara duas versões do documento por identificador de nó, não por posição, e o mesmo documento aberto em duas abas gera conflito de versão nomeado, com a diferença na tela e clique explícito antes de sobrescrever.
- Medido: 50 operações desfeitas e refeitas devolvem o documento com o mesmo sha256 em cinco sementes.

### L5-10-temas-marca (parcial)

- Aplica tema de marca em três níveis: seis temas padrão, tema do inquilino e tema por documento; o editor `/temas` permite montar por arrasto, ver a prévia, conferir o contraste segundo as diretrizes WCAG e exportar ou importar o tema como JSON.
- Trocar o tema não recarrega a página, provado nos dois testes de ponta a ponta; valor de cor ou de fonte fora do formato esperado é recusado por validação, o que barra a tentativa de injetar código em um token.
- A suíte completa sofreu interrupção por tempo com quatro trilhas em paralelo; os testes unitários e de API passam por segmento.

### L5-11-expressoes-no-navegador (parcial)

- Acrescenta à linguagem de expressão sete perfis de uso — janela de feição, rótulo, cálculo de formulário, visibilidade, restrição, indicador de painel e título dinâmico — cada um declarando os tipos de retorno que aceita e o orçamento de tempo, de 50 milissegundos no navegador e 500 no servidor.
- Entraram seis funções de feição e geometria, levando a biblioteca de 43 para 49 funções nos dois avaliadores; medida de área e comprimento usa esfera de raio 6.371.008,8 metros, com erro de modelo de até 0,5 %, e não serve como medição legal.
- Nenhuma tela chama os perfis ainda: o que existe é a biblioteca, conferida com 339 vetores compartilhados rodados em Python e em Node.

### L5-12-acessibilidade-i18n-construtores (entregue)

- Os construtores têm dicionário em português, inglês e espanhol com paridade de chaves testada, e o seletor de idioma troca o dicionário sem recarregar a página.
- O fluxo inteiro — montar três componentes, ligar uma ação, salvar e publicar — é completado só por teclado, e o axe-core não acusa violação crítica ou séria nas telas do construtor.
- Correção que saiu daqui e vale para toda a interface: o acento do tema claro media 4,36:1 de contraste, abaixo do mínimo de 4,5:1, e foi escurecido para 4,74:1.

### L5-15-vista-movel-responsivo (entregue)

- Roda o aplicativo publicado em qualquer largura de tela: a grade de 12 colunas vira uma coluna abaixo de 600 pixels, o mapa continua presente e o quadro de dados troca de tabela para lista na mesma faixa.
- Permite uma vista para celular definida à mão, em que cada quadro de raiz tem visibilidade, ordem e largura próprias, e essa vista prevalece sobre o rearranjo automático.
- O construtor pré-visualiza o documento em edição em três larguras (375, 768 e 1440 pixels) sem precisar salvar, e o arrasto de quadro passou a funcionar por toque, além do botão e do menu que já existiam.

### L5-01-a-layout-paginas (entregue)

- Monta a aplicação em páginas pelo editor de arrasto: página de tela cheia ou rolável, cabeçalho, rodapé, menu, os componentes de layout (linha, coluna, grade, acordeão, painel fixo, painel lateral) e janela modal ou ancorada.
- O executor renderiza o mesmo documento como aplicação: o menu navega entre páginas, o endereço muda por página e recarregar reabre na página certa; a janela modal usa o elemento nativo do navegador e fecha com Esc; o painel lateral recolhe sem sumir do fluxo.
- Medido: aplicação de 2 páginas montada só por arrasto em 2.245 ms; a grade mantém a proporção 8 para 4 entre dois filhos em 1200 px e em 600 px, com diferença de 0,017; com 6 níveis aninhados em três larguras de tela não houve estouro horizontal nem componente com dimensão zerada.

### L5-01-c-widgets-dado (parcial)

- Faz os componentes de dado do aplicativo consultarem a camada no servidor em vez de exigir a fonte inteira no navegador: página, total, agregação, histograma, valores únicos, identificadores do filtro e exportação passam pelo serviço de feições quando a fonte é camada, e rodam em memória quando a fonte é embutida.
- Entram tabela com paginação e ordenação no servidor e exportação do filtro ativo em CSV e GeoJSON, gráfico com agregação no servidor, filtro por texto, valores únicos, intervalo e data, e os componentes de lista, consulta, seleção, informação da feição e adicionar dado; filtros de origens diferentes se combinam por E lógico.
- Medido: 113 milissegundos por página no percentil 95 com 100 mil feições, e cinco agregações conferidas contra consulta SQL direta. A edição dentro do aplicativo fica para outro item.

### L5-01-d-widgets-pagina-menu (parcial)

- Traz 12 componentes de página e de menu para o construtor: texto em Markdown com campo da feição, imagem, botão, cartão, incorporar página externa, divisor, menu, controlador de componentes, compartilhar, entrar, seletor de idioma e seletor de tema.
- O texto é sanitizado e dez tentativas de injeção de script não executam; a incorporação de página externa usa lista de domínios e caixa de areia, e o QR de compartilhamento é gerado na própria instalação por `GET /api/qr.svg`, sem serviço externo.
- Falta para o item ficar completo: o ramo com esse trabalho ainda não está no tronco, e a comparação com a documentação do produto da Esri foi escrita a partir da lista do item, porque a página oficial estava inacessível.

### L5-01-e-acoes-configuraveis (parcial)

- Configura ações entre quadros do aplicativo por painel: gatilho, alvo, ação, relação (mesma fonte, por atributo ou espacial) e condição, com a lista de eventos limitada ao que o tipo do quadro emite e a de ações ao que o alvo aceita.
- Valida nos dois lados, navegador e servidor: evento incompatível, alvo incompatível, gatilho repetido e condição com campo inexistente são acusados, e renomear o campo da camada marca a referência quebrada no painel.
- Dá ao usuário do aplicativo as ações de exportar em CSV ou GeoJSON as feições filtradas, ver na tabela, aproximar na seleção e criar item com a seleção; 30 ações em cadeia levam 0,47 ms no percentil 95, e ciclo fechado avisa e para.
- O tipo de item de seleção ainda não existe nesta base.

### L5-04-a-blocos-de-conteudo (parcial)

- Acrescenta o tipo de item narrativa, editado pelo mesmo editor de arrasto, com onze blocos: capa, texto, imagem, vídeo, áudio, mapa, tabela, botão, separador, conteúdo incorporado e aplicativo; o leitor mostra a narrativa na tela de execução e na página publicada por link.
- O bloco de mapa guarda a vista como caixa envolvente mais a proporção do quadro e a reabre por enquadramento: a diferença medida foi de 0,12 % em 5 mapas e 2 larguras de tela, contra o teto de 1 % do portão.
- Publicar recusa imagem sem texto alternativo, com 422 e a lista dos blocos em falta, e a regra está no servidor. Fica parcial: as camadas do mapa na página anônima dependem do escopo de tile por token, que é de outro item.

### L5-04-c-temas-capa-colecao (parcial)

- Cria o tipo de item coleção, com capa (título, subtítulo, mídia) e itens citados por identificador, mantendo as relações sincronizadas a cada gravação: citar item inexistente, de outro inquilino ou a si mesma é recusado com erro 422, e endereço de mídia só é aceito se for da casa ou HTTPS.
- Publicar a coleção por link avisa, na interface de programação e na tela, qual item citado ficou de fora do link, e oferece corrigir; o leitor anônimo lê o mesmo aviso em vez de encontrar um espaço vazio sem explicação.
- A página pública leva os metadados de compartilhamento social, e as internas não. A troca de tema sem reeditar blocos fica pendente, porque depende do item de temas, ainda ausente do tronco.

### L5-32-vistas-de-camada (parcial)

- Cria vista de camada como VIEW do PostgreSQL com `security_invoker`: o filtro fica congelado na definição, o campo oculto não existe na relação, vista somente leitura recusa edição com 403, e compartilhar a vista com o público não expõe a camada de origem.
- Falta para o item ficar completo: o teste de navegador da tela foi escrito, mas não roda na trilha.

### L5-36-widgets-personalizados-sdk (parcial)

- Instala quadro de aplicativo escrito por terceiro a partir de um pacote enviado pelo administrador do inquilino: o pacote fica em tabela com isolamento por inquilino, e o carregador reconfere o sha256 do conteúdo antes de executar.
- Executa o quadro externo em modo isolado, dentro de moldura com política de conteúdo restrita, para que ele não alcance o cookie de sessão nem rotas da administração.
- Está construído e testado apenas na trilha própria, com 15 testes de unidade e de interface de programação e 3 testes de navegador verdes; a medida de primeira pintura foi de 2.412 ms com a máquina em carga 5,3, e a cronometragem do passo a passo do manual por um testador humano ainda não foi feita.

### L7-15-processo-release (refutado)

- Processo de release do zero até a decisão humana de publicar: changelog do git, suíte inteira, homologação, pacote assinado com o manifesto de homologação embutido — impossível forjar sem a chave privada.

### L7-16-assinatura-pacote (refutado)

- Assina e verifica pacote de atualização por Ed25519 (`scripts/assinar_pacote.sh` / `verificar_pacote.sh`); 1 byte adulterado é suficiente para a verificação recusar; chave privada nunca entra no repositório, só a pública em `deploy/chaves_publicas_release.txt`.

### L7-31-ambiente-homologacao (refutado)

- Ambiente de homologação isolado no mesmo banco (schema `plat_homolog`), migrações reaplicadas de forma independente; isolamento provado ao vivo com uma tabela de teste.

### L7-11-c-telemetria-opcional (parcial)

- Mantém a telemetria da instalação desligada por padrão; só o superadministrador liga, e a tela mostra a prévia exata do que seria enviado, com 13 campos fixos e apenas valores agregados, sem nome, geometria ou conteúdo.
- Com a telemetria desligada, nenhuma chamada de rede sai, medido. O receptor na casa recusa chave desconhecida com 403 sem gravar, campo a mais com 422 e chave de outra instalação com 422; o envio corre num trabalho diário.
- O acompanhamento das instalações existe como rota de API, sem tela.

### L7-03-b-rate-limit-abuso (parcial)

- Limita volume de pedidos em três camadas independentes: o servidor de borda por endereço, a interface de programação por inquilino e plano com janela deslizante no Postgres, e o banimento por repetição de falha de login com ferramenta dedicada e registro de acesso próprio.
- A camada da interface é chamada na resolução de sessão, então cobre toda requisição autenticada, por sessão ou por token, e o cabeçalho de endereço de origem forjado não move o ponto em que o limite dispara; uma corrida achada pelo adversário na função do banco foi corrigida com trava e reprovada em 5 rodadas de 200 chamadas concorrentes, sem furo.
- Fica parcial a cláusula do limite de tiles por plano: a rota de tiles de imagem ainda não existe nesta base, embora a zona de borda e o mecanismo por escopo já estejam prontos.

### L7-03-d-injecao-consulta (parcial)

- Uma suíte de segurança dispara 180 tentativas de injeção de SQL contra o serviço de feições e as rotas OGC (filtro, campos de saída, ordenação, agrupamento, estatísticas, lista de identificadores): nenhuma resposta de erro de servidor, 8 ms de latência máxima e a tabela isca intacta.
- Um teste estático percorre a árvore do código e exige que nenhuma chamada ao banco monte SQL com texto do usuário; duas falhas de servidor foram corrigidas e agora devolvem 400 com o motivo.
- Falta para o item ficar completo: a varredura do ZAP não rodou, por falta de imagem e de disco.

### L7-03-f-dependencias-cve-log-correcoes (refutado)

- Varre `requirements.txt` com `pip-audit` (`make seguranca-deps`, ainda fora do `check` principal) e falha com CVE crítico/alto sem exceção viva registrada; achado real do dia: CVE médio em `idna`, não bloqueia.

### L7-19-segredos-e-certificados (refutado)

- `PLAT_SECRET` e a senha do worker não moram mais em arquivo legível: saem por `LoadCredential=` do systemd (`/etc/plat/segredos/`, 0600, só o processo do serviço lê).
- Rotaciona qualquer segredo sem reinstalar (`scripts/rotacionar_segredo.sh`), com prova de que a senha antiga para de funcionar; `docs/SEGURANCA.md` documenta onde cada segredo mora e quando o certificado renova.

### L7-20-trilha-auditoria (entregue)

- Grava trilha de auditoria de negócio em tabela que só aceita inserção: a role da aplicação não tem permissão de alterar, apagar ou truncar, e dois gatilhos recusam a tentativa mesmo assim.
- Cobre 112 de 112 rotas de escrita do contrato de interface de programação, por duas vias: gatilho sobre o evento de domínio, para as rotas que já registram evento, e uma chamada antes de confirmar toda transação de escrita, para as demais; o identificador da requisição, o endereço de origem, o token, o método e a rota chegam ao banco pela própria transação.
- A retenção é configurável por inquilino, com padrão de 730 dias e piso de 90 dias: o piso é a resposta à tentativa de apagar a trilha encolhendo a retenção, e o expurgo roda agendado, com nome derivado do schema e negado à role da aplicação.

### L7-07-b-replica-garage (parcial)

- Replica o armazenamento de objetos em três nós com fator de replicação 3: com um nó parado foram escritos 1.000 objetos; o nó voltou, sincronizou em 5,2 s, a varredura de verificação não acusou erro e os 1.000 valores sha256 conferiram com o nó que recebeu as escritas desligado.
- Medido também o limite do arranjo menor: dois nós com fator 2 mantêm a leitura mas recusam a escrita com um nó parado, respondendo 503 por falta de quórum; a escrita contínua exige três nós. A ressincronização de 256 MiB levou 4,7 s.
- O documento de operação cobre acrescentar nó, trocar disco, ver o layout e a varredura periódica. Fora do medido: a ressincronização de 10 GB e o arranjo em contêineres num ambiente de homologação separado.

### L7-08-c-sdk-js (parcial)

- Publica uma biblioteca JavaScript de acesso à plataforma, sem dependência externa, com o mesmo modelo da biblioteca Python: entrada, itens, camadas, mapas com paginação por cursor, espera de tarefa, tokens, repetição automática em erros temporários e erro tipado.
- Traz ajudantes para o MapLibre (fonte, camada, estilo, catálogo por extensão, assinatura de pedido e enquadramento) e regra embutida de que o cabeçalho de autorização nunca acompanha o cookie: a interface responde 400 nesse caso.
- Os 10 exemplos entregues abrem com política de conteúdo restritiva e são o próprio teste de ponta a ponta: 13 verdes no navegador, sem violação de política e sem erro de console. Feições por camada e tiles dinâmicos dependem do item de serviços.

### L6-01-a-procedencia-acervo (entregue)

- Expõe o acervo da casa (376 fontes) como camadas assináveis só-leitura em `GET /api/acervo` e `GET /api/acervo/{fonte}`; só as 68 fontes com **licença escrita** aparecem — a view em si filtra, não é uma regra de tela.
- `POST /api/acervo/{fonte}/adicionar` cria um item de catálogo tipo conexão apontando para a fonte, sem copiar dado; herda a RLS e o compartilhamento do catálogo normal.

### L7-14-instalacoes-apt-desta-linha (refutado)

- Lista fechada de 7 pacotes apt (`deploy/pacotes_apt.txt`) instalada de forma idempotente pelo `install.sh` (`dpkg -s` antes e depois); pgRouting/pgstac e ezdxf/LibreDWG ficam fora de propósito (outro item / D23 em aberto).

### L0-05-e-worker-em-container (refutado)

- Worker também roda em contêiner Docker (imagem própria, memória do processo filho nunca excede o teto do cgroup); achado crítico corrigido: dentro do contêiner o worker é PID 1, o que quebrava silenciosamente a detecção de processo-pai morto.

### L7-03-b-antivirus-anexos (refutado)

- Confere a assinatura mágica real do arquivo contra o `Content-Type` declarado em todo upload (`POST /api/arquivos`, PUT único e multipart) e recusa divergência; ClamAV de verdade ainda não instalado (disco/RAM apertados, D21) — a interface já está pronta para trocar depois.

### L2-04-b-parser-where-ast (entregue)

- Parser de filtro próprio (`app/consulta/where_ast.py`): gramática fechada, nunca `eval`/`exec`, gera SQL sempre parametrizado contra uma lista branca de colunas — usado por qualquer rota futura que aceitar um filtro do usuário.
- 39 tentativas de injeção clássica (`; DROP TABLE`, tautologia `1=1`, campo fora da lista, injeção dentro de `IN`) todas neutralizadas como texto literal ou recusadas, nunca executadas.

### L2-01-a-basemap-local-pmtiles (entregue)

- Primeiro mapa real do produto: tela `/mapa` a tela cheia com MapLibre GL JS 4.7.1 lendo um PMTiles local (`web/dados/basemap/guarulhos.pmtiles`, recorte OSM ODbL 1.0, 18,3 MiB) servido pelo próprio nginx por Range HTTP — sem Martin, sem serviço de tiles dinâmico, sem chave de terceiro.
- Navegação (zoom/pan), escala, coordenadas do cursor e seletor de camada base (uma opção hoje, mecanismo pronto para a próxima); estilo cartográfico próprio dentro da identidade "instrumento".
- e2e prova 206/Content-Range sem gzip no nginx e a captura do mapa com mais de 50 cores distintas (mapa desenhado de verdade, não tela em branco); 0 erro de console.

### L0-05-e-justica-entre-inquilinos (parcial)

- A fila de trabalhos alterna entre inquilinos em vez de servir por ordem global: com dois inquilinos e um trabalhador, um trabalho curto espera no máximo o trabalho que já está rodando — medido em 0,5 s com dois trabalhos de 300 s à frente e 0,2 s com cinquenta.
- A leitura de um trabalho pendente devolve a posição na fila do inquilino, e a tela Tarefas mostra esse número.
- Falta para o item ficar completo: a migração que faz o rodízio existe apenas na trilha de entrega; no ramo de lançamento a fila ainda é por ordem de chegada, e o teste de navegador com a posição na fila não foi feito.

### L0-14-identidade-visual (tentando; código no repositório, veredito do gerente pendente)

- Tela de entrada redesenhada na direção "instrumento" (fundo quase preto, acento âmbar, Big Shoulders Display para rótulos, IBM Plex Sans/Mono para texto e dado, moldura com tique de canto); tokens em `web/estilo/tokens.css` com os três temas (claro/escuro/explícito).
- As outras 8 telas ainda usam o painel anterior — só a entrada foi convertida nesta fatia; ícones, página `/estilo`, contraste AA medido e o restante das telas ficam para o resto do item.

### L0-02-g-checagem-privilegio-papel-id (entregue)

- Criar ou editar usuário passa a conferir se quem concede tem todos os privilégios do papel que está concedendo; sem isso a resposta é 403 e o detalhe lista o que faltaria.
- A mesma regra vale para o perfil e para o papel nulo, porque promover alguém a administrador sem papel concede o mesmo conjunto; a conferência também cobre a alteração em lote.
- A refutação foi rodada em forma completa: para cada um dos 47 privilégios do vocabulário, o ator ficou com todos menos um e ofereceu todos, em 94 chamadas de criação e edição, com 94 respostas 403 e nenhuma resposta de sucesso.

### UX-01-sistema-de-design (parcial)

- Concentra cor, tipografia, espaçamento, raio, sombra e foco num arquivo único de tokens, em duas camadas (primitivos por tema e semânticos), e todas as telas passam a usar a identidade visual "instrumento".
- Acrescenta quatro componentes base (estado de tela, avisos, painel e seletor de tema) e uma guia viva em `/estilo-guia` que calcula o contraste no próprio navegador.
- Uma verificação automática reprova cor ou tamanho escrito fora do arquivo de tokens; 15 casos foram corrigidos na primeira passagem, a auditoria de acessibilidade não acusa violação séria nos dois temas, e as 20 telas foram capturadas em 1280 e 390 pixels antes e depois.

### UX-02-telas-entrada-conta-convite (parcial)

- As telas públicas de entrada, aceitação de convite e redefinição de senha mostram o erro no campo que o causou, com foco no primeiro inválido, botão ocupado durante a chamada, aviso de tecla Caps Lock e estado nomeado quando o servidor não responde ou o token expirou.
- A interface resolve o idioma pela ordem endereço, preferência guardada, atributo da página, navegador e português; os arquivos de inglês e espanhol estão completos com 995 chaves, e a paridade de chaves e de variáveis é conferida por teste.
- O teste de ponta a ponta percorre entrar, segundo fator, conta e sair, com capturas em 360 e 1280 pixels e nenhuma violação séria de acessibilidade nas telas percorridas.

### UX-03-tela-conteudo-item-lixeira (parcial)

- Dá à lista do catálogo e ao painel do item estados explícitos em vez de tela em branco: vazio com ação sugerida, carregando com esqueleto, erro com a referência e opção de repetir, e acesso negado.
- Arrastar arquivos sobre a lista cria itens pelo mesmo caminho do botão de novo item, caminho que estava quebrado desde a entrega do catálogo e foi consertado; a seleção em massa sobrevive a reordenar e filtrar, porque é guardada por identificador.
- Medido: desenho da lista com 1.000 itens em 57,7 milissegundos no percentil 95, contra alvo de 500, com capturas em duas larguras e sem violação séria de acessibilidade.

### UX-04-tela-mapa-polimento (parcial)

- O visualizador tem uma moldura única: barra no topo, trilho à esquerda com um botão por painel e gaveta com os painéis de pesquisa, camadas, legenda, medição, desenho, anotações, impressão e exportação, mais a tabela de atributos ancorada no rodapé.
- Tem atalhos de teclado, tela cheia, impressão que manda só o mapa para o papel, painel inferior de 390 pixels no celular e mapa de fundo escuro; o teste de navegador abre cada painel em 1280 e em 390 pixels e roda o axe-core.
- Falta para o item ficar completo: o registro do veredito do item; a junção dos ramos de painel trouxe quatro correções, já aplicadas.

### UX-05-telas-conexoes-uploads-tarefas-compartilhado (parcial)

- A tela de conexões ganhou criar, editar e apagar com confirmação, busca, ordenação por coluna e estados de vazio, carregando, erro e sem permissão, com os erros do servidor aparecendo no campo certo.
- A tela de envio de arquivos virou fila: vários arquivos, uma barra por arquivo, cancelar um ou todos, tentar de novo, com bytes, velocidade e tempo restante.
- A tela de tarefas deixou de ter texto fixo no código e passou a usar o dicionário de idiomas, e a página pública de item compartilhado perdeu a barra lateral do produto, com estados nomeados para item não encontrado, expirado e excesso de pedidos.
- O progresso byte a byte no envio foi tentado e recusado pela própria trilha, porque o pedido com contador de bytes leva o cookie de sessão junto e cai em erro de autenticação ambígua; o envio segue em partes de 16 MiB, e a decisão ficou registrada para o dono da autenticação.

### UX-06-tela-administracao-inquilino (parcial)

- `/admin` reúne a administração do inquilino numa porta única: um cartão por assunto (usuários ativos, convites pendentes, grupos, papéis, tokens válidos, uso e cota de armazenamento, provedor de diretório, acervo com licença, acessos em 24 h), com o número lido da rota que já existe e o caminho da tela que gere o assunto.
- A tela `/admin/acervo` lista as fontes do acervo com busca, ficha de procedência e a ação de adicionar ao catálogo, transformando a exigência de confirmação de risco de dado pessoal em diálogo antes da segunda chamada; a seção de diretório LDAP ganhou tela, e toda escrita administrativa mostra o evento registrado.
- Nada disso está no ramo que serve a demonstração: nenhum commit da trilha de interface foi mesclado nele, e o merge reescreve quatro arquivos que outro agente edita agora, o que exige um turno dedicado.

### HARD-01-varredura-de-seguranca-continua (parcial)

- Roda a varredura de segurança dentro do portão de conferência do repositório: análise estática do código Python, auditoria de dependências Python e JavaScript, busca de segredo no histórico do repositório e varredura de imagem, com as ferramentas binárias fixadas por resumo criptográfico.
- Exceção só entra com prazo registrado em arquivo próprio, e a seção de segurança da documentação é gerada da varredura. Consertos que vieram dela: leitor de XML seguro no armazenamento de objetos, ocultação da versão do servidor de borda e cabeçalhos de política de conteúdo e de enquadramento.
- A varredura dinâmica da aplicação fica fora do portão principal, num alvo próprio, porque precisa de uma instância de teste.

### HARD-02-testes-de-carga-e-caos (parcial)

- A suíte de caos prova a retomada em dois cenários: o trabalhador morto no meio de um trabalho é ceifado por batimento vencido e o trabalho volta à fila com contador de reinícios; a API morta no meio não perde o trabalho nem a sessão, porque a sessão vive no banco e não no processo.
- Falta para o item ficar completo: a medição de latência no percentil 95 por rota contra as metas declaradas e o cenário de banco de dados derrubado, que está em outro ramo na fila.

### UX-07-telas-do-construtor-e-aplicativo (parcial)

- O construtor lista aplicativos e painéis quando aberto sem item, cria um novo, e com item mostra salvar, publicar com confirmação, executar e trocar de item, com o conflito de versão nomeado.
- As telas de execução do aplicativo mostram estados explícitos para item inexistente e tipo errado, e quadro com configuração inválida mostra erro nomeado no painel em vez de quebrar a tela.
- A árvore da estrutura do documento segue o padrão de acessibilidade de árvore, com a linha focável pelo teclado, e a paleta e o painel lateral ficaram presos ao topo com rolagem própria, porque o arrasto pegava o quadro errado quando a página rolava.
- Os rótulos da paleta ainda não estão no dicionário de idiomas.

### UX-08-telas-rede-de-utilidades-e-motor (parcial)

- O visualizador ganha dois painéis: Rotas, que calcula rota, isócrona e matriz de origens por destinos sobre o serviço de roteamento do recorte, mostrando a procedência da resposta e traduzindo os erros do serviço em texto nomeado; e Motor, que cria a área de estudo, escolhe fatores e pesos, roda a análise em escala grossa e refina só onde foi aprovado.
- As células do motor são pintadas no mapa com a nota, a cobertura e a aprovação em janela de atributos; rodar sem área ou sem fator mostra o motivo, em vez de painel vazio.
- Os dois painéis existem apenas num ramo separado, 201 commits à frente e 366 atrás do ramo de demonstração. A interface da rede de utilidades, com traçado montante e jusante e importação de BDGD ou EPANET, continua ausente do ramo de demonstração.

### UX-09-telas-ferramentas-e-tarefas (parcial)

- Abre a tela `/ferramentas`, que lista os tipos de tarefa disponíveis em cartões por grupo, com o custo declarado de cada um (memória, tempo, se é pesada, executor e perfil mínimo) e busca.
- O formulário de cada ferramenta é gerado do esquema dos parâmetros, com limites, valores permitidos, obrigatoriedade e padrão vindos do próprio esquema; a validação aponta o motivo no campo antes de qualquer chamada, e o erro do serviço volta ao campo correspondente.
- Executar cria a tarefa e mostra a execução ao vivo no mesmo painel, com barra, log e cancelamento, e liga para a tarefa e para o item do resultado. As ferramentas no vocabulário de geoprocessamento da Esri não estão cobertas por este item.

### UX-10-acervo-sem-tela (parcial)

- A tela `/acervo` ganhou o controle que faltava para a rota de escrita `POST /api/acervo/{fonte}/adicionar`, com os quatro estados do sistema de design na lista e no próprio controle: carregando, vazio, erro com referência e acesso negado com o nome do privilégio exigido.
- Fonte com dado pessoal abre diálogo de confirmação antes de entrar no catálogo, e o mapa de cobertura da interface caiu de 41 para 40 lacunas.
- Falta para o item ficar completo: ele depende do item do sistema de design, que ainda está parcial.

### UX-11-arquivos-sem-controle (parcial)

- A seção "Arquivos e objetos" da tela de organização mostra uso contra cota, roda a varredura de objetos órfãos e permite enviar, baixar e apagar arquivo com confirmação, com os erros de tamanho e de tipo nomeados na tela.
- O mapa de cobertura da interface foi regenerado com 240 rotas e 11 lacunas de escrita, nenhuma delas da trilha de interface.
- Nada dessa trilha está no ramo de lançamento: nada dela foi mesclado, e a junção depende de quatro arquivos que outros agentes editavam na mesma árvore.

### UX-12-categorias-sem-controle (parcial)

- A tela `/admin/categorias` dá controle às duas rotas de escrita de categorias que não tinham tela: editor da árvore de até três níveis, que grava a árvore inteira preservando os identificadores, e importação dos modelos ISO 19115 e INSPIRE, idempotente.
- Os erros da API aparecem nomeados no controle: categoria em uso responde 409 com os caminhos e itens, limite de categorias responde 422 com o número atingido e o máximo, e a falta de privilégio responde 403. A lista tem estado explícito para carregando, vazio, erro e negado.
- O mapa de cobertura da interface caiu de 41 para 36 lacunas; o item fica parcial porque depende do sistema de design, que também está parcial.

### UX-13-conexoes-sem-controle (parcial)

- Fecha a lacuna de escrita de conexões: as oito rotas de conexão externa têm controle alcançável na tela `/conexoes` — criar, editar, apagar com confirmação, testar, histórico e publicar.
- Conexão removida por outra pessoa deixa de prender o formulário: o erro 404 avisa e recarrega a lista, e os erros de privilégio, conflito de nome, validação, endereço inseguro e cota aparecem nomeados no campo ou no aviso da lista.
- O teste de ponta a ponta exercita 17 estados da tela, com capturas em duas larguras, sem violação séria de acessibilidade e sem erro de console.

### UX-14-geocodificador-sem-tela (parcial)

- A tela `/geocodificar` expõe as rotas de endereço para coordenada e de coordenada para endereço: até 50 candidatos com pontuação, tipo de acerto e botão de ver no mapa, e o caminho inverso com vizinho mais próximo, distância e marca de fora do raio.
- Resposta vazia aparece com o código e a mensagem reais do motor, nunca com o número cru; o mapa de cobertura da interface caiu de 35 para 33 lacunas.
- Falta para o item ficar completo: a resposta com endereço encontrado de verdade não foi provada, porque a base de endereços do IBGE não está carregada na trilha.

### UX-15-geocodificador-esri-sem-controle (parcial)

- A tela de geocodificação ganhou a seção do serviço compatível com a Esri: a URL do GeocodeServer para copiar, com o escopo exigido, e botões para ver o descritor, buscar candidatos por endereço, geocodificar ao contrário a partir de coordenada e geocodificar em lote até 500 endereços.
- As respostas aparecem no formato da Esri, e as respostas de negócio do protocolo viram estado nomeado na tela em vez de código cru; a tela de tokens passou a mostrar as URLs dos serviços externos com o escopo exigido.
- O mapa de cobertura da interface caiu de 33 para 29 lacunas; a consulta com retorno real contra a base de endereços não foi provada na trilha.

### UX-16-ingestao-sem-tela (parcial)

- A tela `/importacoes` dá controle ao fluxo de arquivo até camada: lista as importações com estado, formato, número de feições e erro; cria a importação a partir de um arquivo já enviado, com sugestão de formato pela extensão; acompanha o trabalho de inspeção até a proposta.
- Em "conferir e carregar" o usuário edita a proposta (título, sistema de referência quando o arquivo não declara, codificação, tipo de geometria, ação para geometrias inválidas e campos a importar), dispara a carga e acompanha até a conclusão; o erro da API aparece no campo que o causou.
- Achado corrigido no caminho: `GET /api/importacoes/formatos` respondia 404 porque estava declarado depois da rota com identificador. O mapa de cobertura da interface caiu de 29 para 26 lacunas.

### UX-17-login-sem-controle (parcial)

- Faz a tela de entrada declarar os provedores de login habilitados no inquilino: quando há diretório LDAP ligado, um botão alterna para o login por diretório com os mesmos campos, e o login local continua disponível.
- As respostas do diretório têm texto próprio na tela: fora do ar, desabilitado, usuário sem grupo autorizado e conta que já existe como login local.

### UX-18-plataforma-sem-tela (parcial)

- A tela `/admin/inquilinos` é o console do superadministrador: lista os inquilinos com estado, número de usuários, criação e último acesso, cria inquilino mostrando a senha temporária uma única vez, suspende, reativa e apaga com dupla confirmação.
- Quem não é superadministrador recebe 404 da API, que a tela mostra como acesso negado; erros de validação e de nome repetido aparecem no próprio campo, e o mapa de cobertura da interface caiu de 26 para 22 lacunas.
- Falta para o item ficar completo: ele depende do item do sistema de design, ainda parcial.

### UX-19-rede-sem-tela (parcial)

- As rotas de roteamento, área de serviço e matriz origem-destino existem no ramo de lançamento como interface de programação, entregues pelo item de rota e isócrona.
- A tela que chama essas rotas não existe no ramo de lançamento: o painel de rotas foi construído na trilha de interface e nada dessa trilha está mesclado.

### UX-20-usuarios-sem-controle (parcial)

- A rota de edição de papel que estava sem controle na tela fica coberta pela tela de administração de papéis da trilha de interface.
- Esse trabalho não está no ramo que serve a demonstração: nenhum commit da trilha de interface foi mesclado nele. O ramo acumula 392 commits em 316 arquivos e o merge reescreve quatro arquivos que outro agente edita agora, o que exige um turno dedicado.

### UX-21-multiescala-sem-tela (parcial)

- As rotas do motor de grades aninhadas deixam de existir apenas na interface de programação: o painel "Motor" do visualizador cria a área de estudo a partir da vista atual do mapa, lista e cadastra fatores com a escala nativa declarada, aplica peso por controle deslizante e roda as etapas macro e micro.
- Uma rota de leitura foi criada para a lacuna: as células com nota, cobertura e situação voltam como coleção de feições, com teto declarado e indicação de resultado truncado; quando a nota da célula vem do bloco da fonte, e não de dado próprio, o painel diz isso.
- O painel repete o aviso de que os pesos são escolhidos pelo usuário, não medidos.

### L0-02-z-apagar-inquilino-apaga-schema (entregue)

- Apagar um inquilino apaga também o schema de dado dele na mesma transação, com as tabelas de camada, as funções de tile e as políticas de acesso, sob trinco por identificador de inquilino.
- A origem do item foi um incidente com 1.219 schemas de teste deixados para trás; a fixture de teste agora confere, ao final, que o schema sumiu.

### L4-04-c-unificar-subrede (parcial)

- Guarda numa tabela só as duas leituras de subrede da rede elétrica, com a coluna de origem separando a subrede derivada do controlador, que é a canônica, da hierarquia declarada pelo arquivo da distribuidora.
- A migração copiou as linhas preservando o identificador e repôs as chaves estrangeiras de nós e arestas, e uma verificação por origem impede a mistura das duas.
- A importação liga as duas leituras pelo nome dentro do mesmo nível e conta o que não casa, sem tratar divergência como erro provado; no recorte da cooperativa de teste a reconciliação bateu em 3 de 3 alimentadores e 1.729 de 1.729 transformadores.

### L7-01-d-instalador-extensoes (parcial)

- A lista de extensões do Postgres que o produto exige passa a morar num arquivo único, lido pelos três consumidores: o instalador, o preparador de ambiente de trilha e o ensaio de restauração da cópia de segurança.
- A rotina cria o que falta e confere em seguida no catálogo do banco, terminando com erro que nomeia a extensão que não nasceu. Medido em base descartável: base só com PostGIS termina com as quatro extensões e o dump restaura nela sem passo manual; sem a extensão `unaccent` a tabela de itens não é criada e a conferência reprova nomeando-a.
- O `install.sh` inteiro continua sem teste que o execute, porque ele instala pacotes do sistema e escreve unidades do systemd.

### UX-23-mapa-sem-controle (parcial)

- Acrescenta ao visualizador o painel de seleção: por atributo, com condições combinadas por E e OU, valores únicos sugeridos e a consulta equivalente mostrada na tela; pela geometria desenhada, com interseção ou distância; e entre camadas.
- O resultado realça na tabela de atributos, vira filtro da camada no mapa e pode ser guardado como item de seleção.
- As anotações foram reescritas com estados explícitos, edição de texto pelo autor, resolver e reabrir e exclusão com confirmação, e o painel de exportação passou a importar pacote de mapa, com recusas locais e erros de tamanho e validação nomeados.

### L4-01-f-alcance-do-tracado-rede-real (parcial)

- A tolerância de conexão da rede passou a ser declarada por par de tipos de ativo, o que fez o traçado a jusante alcançar 599 de 600 transformadores, contra 428 antes, e levou o pior alimentador de 66,67 % para 99,51 % de alcance, com os cinco alimentadores acima do piso de 95 %.
- A folga extra só reencontra o mesmo ponto e nunca alcança um segundo, o que mantém o número de laços na média tensão igual ao de antes; `GET /api/rede/{id}/topologia/diagnostico` lista os órfãos restantes por classe, com contagem, distância e exemplo — de 1.038 para 495.
- Falta para o item ficar completo: o registro do veredito do item; as cláusulas do portão estão medidas.

## Fronteira: o que o produto NÃO faz ainda

Uma linha por linha do produto. O que está `pendente` não existe na tela nem na máquina.

### L0 fundação

Deve fazer: repositório, identidade e acesso, catálogo por inquilino, ingestão de vetor, fila de trabalhos, cópia de segurança, administração da organização, SSO, metadado.

Não faz ainda (52 de 75 itens não entregues; pendentes 12): `L0-02-e-varredura-cruzada-rls`, `L0-02-tenant-auth`, `L0-03-e-compartilhamento`, `L0-03-f-tela-conteudo`, `L0-04-a-upload-arquivo`, `L0-04-b-inspecao`, `L0-04-c-tabela-camada`, `L0-04-d-formatos-base`, `L0-04-ingest-vetor`, `L0-04-k-rota-formatos-encoberta`, `L0-05-a-fila-postgres`, `L0-05-b-progresso-cancelamento`, `L0-10-eventos-historico`, `L0-11-arquivos-objetos`, `L0-12-contrato-api-e-limites`, `L0-13-dado-demonstracao`, `L0-14-identidade-visual`, `L0-03-h-lixeira-protecao-status`, `L0-03-j-transferencia-dono`, `L0-04-f-fgdb-parquet-fgb-gml`, `L0-04-g-atualizar-dados`, `L0-05-c-tela-tarefas`, `L0-05-e-justica-entre-inquilinos`, `L0-05-jobs`, `L0-06-c-restore-drill`, `L0-06-d-exportar-inquilino`, `L0-06-e-status`, `L0-07-a-configuracoes-org`, `L0-07-admin-org`, `L0-07-c-cotas-uso`, `L0-07-f-console-plataforma`, `L0-09-a-procedencia`, `L0-14-cli-admin`, `L0-15-marca`, `UX-29-org-lacunas-1609`, `L0-03-k-favoritos-notificacoes`, `L0-03-l-versoes-item`, `L0-04-j-camada-vista`, `L0-06-b-pitr-pgbackrest`, `L0-06-backup-status`, `L0-07-e-relatorios`, `L0-08-a-oidc`, `L0-08-b-saml`, `L0-08-e-mapeamento-provisionamento`, `L0-08-sso`, `L0-09-b-editor-iso-mgb`, `L0-09-c-xml-iso-validacao`, `L0-09-d-ogc-records-csw`, `L0-09-metadado-catalogo`, `L0-05-e-worker-em-container`, `L0-08-c-govbr`, `L0-08-d-ldap`.

### L1 imagens

Deve fazer: COG/STAC/tiles por inquilino, token de acesso, conectores Sentinel/NASA/Copernicus/MapBiomas, série temporal, IA na entrada.

Não faz ainda (62 de 66 itens não entregues; pendentes 49): `L1-01-b-validacao-e-isolamento-da-entrada`, `L1-01-c-conversao-cog-perfis-miniatura-estatisticas`, `L1-02-a-servico-titiler-por-inquilino`, `L1-02-b-token-de-servico-com-escopo-por-lista`, `L1-02-c-wmts-xyz-tilejson-validados`, `L1-02-d-cache-nginx-cdn-e-bancada-de-carga`, `L1-02-f-predefinicoes-de-renderizacao-e-legenda`, `L1-02-tiles-token`, `L1-03-a-quadro-de-conectores-e-tela-sensores`, `L1-03-b-sentinel-2`, `L1-07-mosaico-por-colecao-e-pegadas`, `L1-12-linguagem-de-expressao-de-banda`, `L1-01-e-upload-grande-retomavel`, `L1-01-f-formatos-de-entrada`, `L1-01-g-raster-categorico-colormap-e-tabela-de-atributos`, `L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo`, `L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro`, `L1-02-g-wms-1-3-0-raster`, `L1-02-h-ponto-estatisticas-e-histograma`, `L1-03-c-sentinel-1-sar`, `L1-03-conectores-sensores`, `L1-03-d-landsat`, `L1-03-e-mapbiomas`, `L1-03-f-cog-globais-por-vsicurl`, `L1-03-k-planetary-computer-e-stac-de-terceiros`, `L1-03-l-item-referenciado-sem-copia`, `L1-04-c-grafico-de-indice-por-poligono`, `L1-05-a-registro-de-modelo-e-proveniencia`, `L1-05-b-trabalhador-gpu-remoto`, `L1-08-regras-de-mosaico-e-selecao-de-pixel`, `L1-09-mascara-de-nuvem`, `L1-13-cadeia-de-funcoes-raster-ao-vivo`, `L1-14-analise-raster-em-lote-gera-item-novo`, `L1-15-estatistica-zonal`, `L1-16-derivados-de-terreno-e-terrain-rgb`, `L1-20-exportacao-recorte-e-massa`, `L1-23-cota-e-medicao-por-tb`, `L1-25-servico-de-imagem-esri-compativel`, `L1-27-ficha-de-metadado-e-licenca-da-imagem`, `L1-29-teste-no-arcgis-real-do-parceiro`, `L1-30-paridade-image-server-documento-vivo`, `UX-32-imagens-lacunas-1609`, `L1-01-h-ingestao-em-lote-por-manifesto-e-cli`, `L1-02-i-ogc-api-tiles-e-maps`, `L1-03-h-clima-nasa-power-e-copernicus-cds`, `L1-03-n-comerciais-com-chave-do-cliente`, `L1-03-p-drone-ortomosaico-e-fotos-brutas`, `L1-03-q-lidar-copc-mdt-mds`, `L1-04-a-controle-de-tempo-cortina-e-lado-a-lado`, `L1-04-e-diferenca-entre-datas-e-tendencia`, `L1-04-serie-temporal`, `L1-05-c-mudanca-s2-calibrada`, `L1-06-rasters-do-acervo-em-cog`, `L1-10-camada-congelada-pmtiles`, `L1-21-wcs-2-0-1`, `L1-24-imagens-orientadas`, `L1-05-d-camadas-leves-edificacoes-e-vegetacao-em-faixa`, `L1-05-e-pacote-de-modelo-importavel`, `L1-05-ia-na-entrada`, `L1-19-multidimensional-netcdf-zarr`, `L1-05-f-amostras-e-rotulos-para-treino`, `L1-18-pansharpening-e-ortorretificacao-rpc`.

### L2 plataforma

Deve fazer: mapa web, simbologia, edição, serviços Esri-compatíveis e OGC, geoprocessamento, painéis, campo, migração de AGOL, 3D, relações e regras, geocodificação e rota, impressão, versionamento e sincronização, tempo real, analítica grande, notebooks.

Não faz ainda (119 de 126 itens não entregues; pendentes 26): `L2-01-b-martin-tiles-vetoriais`, `L2-01-c-lista-camadas-legenda`, `L2-01-d-popup-runtime`, `L2-01-e-mapas-base`, `L2-01-g-tabela-atributos`, `L2-01-h-selecao-filtros`, `L2-02-a-modelo-estilo`, `L2-02-b-classificacao-servidor`, `L2-02-c-editor-simbologia-vetor`, `L2-02-d-rotulos`, `L2-02-simbologia`, `L2-03-a-api-edicao-transacional`, `L2-03-c-formulario-atributos-runtime`, `L2-03-edicao`, `L2-04-a-leitor-rls-martin`, `L2-04-b-featureserver-catalogo-metadados`, `L2-04-c-featureserver-query`, `L2-04-d-featureserver-edicao-anexos`, `L2-04-g-ogc-api-features-crs-cql2`, `L2-04-j-conformidade-clientes-e-paridade`, `L2-04-servicos-esri-ogc`, `L2-05-a-catalogo-ferramentas-gpserver`, `L2-05-b-vetor-basico`, `L2-05-c-sobreposicao-agregacao`, `L2-06-e-estatisticas-servidor`, `L2-10-a-dominios-subtipos`, `L2-10-c-linguagem-expressao`, `UX-00-mapa-de-cobertura-da-interface`, `UX-01-sistema-de-design`, `UX-02-telas-entrada-conta-convite`, `UX-03-tela-conteudo-item-lixeira`, `UX-04-tela-mapa-polimento`, `UX-09-telas-ferramentas-e-tarefas`, `L2-01-f-navegacao-medicao-coordenadas`, `L2-01-i-graficos-de-camada`, `L2-01-k-desenho-anotacoes`, `L2-01-l-exportacao-do-mapa`, `L2-02-e-simbolos-sprites-glifos`, `L2-02-f-estilo-raster`, `L2-03-d-historico-restauracao`, `L2-03-e-anexos`, `L2-03-f-edicao-em-lote-calculo-campo`, `L2-04-e-vector-tile-server-tilejson`, `L2-04-h-wfs-2-gml`, `L2-05-d-grades-densidade-padroes-interpolacao`, `L2-05-e-raster-basico`, `L2-05-f-rede-isocrona-rota-ferramentas`, `L2-05-geoprocessamento`, `L2-06-b-elementos-basicos`, `L2-06-c-acoes-seletores-filtros-cruzados`, `L2-06-d-atualizacao-viva-sse`, `L2-06-paineis`, `L2-07-a-pwa-instalavel-cache`, `L2-07-b-formulario-de-coleta-xlsform`, `L2-07-c-fila-sincronizacao-idempotente`, `L2-08-a-leitor-portal-inventario`, `L2-08-b-clonar-camadas-hospedadas`, `L2-08-c-converter-web-map-e-estilo`, `L2-08-d-relatorio-migracao-e-exportacao-reversa`, `L2-08-migracao-agol`, `L2-10-b-relacionamentos`, `L2-10-d-regras-de-atributo`, `L2-10-relacoes-regras`, `L2-11-a-geocodificacao-csv`, `L2-11-b-geocodificador-brasil`, `L2-11-c-rota-matriz-isocrona`, `L2-11-geocodificacao-rota`, `L2-12-a-motor-render-servidor`, `L2-17-crs-transformacoes`, `L2-19-paridade-l2-e-manual`, `UX-05-telas-conexoes-uploads-tarefas-compartilhado`, `UX-06-tela-administracao-inquilino`, `UX-10-acervo-sem-tela`, `UX-11-arquivos-sem-controle`, `UX-12-categorias-sem-controle`, `UX-13-conexoes-sem-controle`, `UX-14-geocodificador-sem-tela`, `UX-15-geocodificador-esri-sem-controle`, `UX-16-ingestao-sem-tela`, `UX-17-login-sem-controle`, `UX-18-plataforma-sem-tela`, `UX-19-rede-sem-tela`, `UX-20-usuarios-sem-controle`, `UX-21-multiescala-sem-tela`, `UX-22-ferramentas-esri-sem-tela`, `UX-23-mapa-sem-controle`, `UX-25-camadas-lacunas-1609`, `UX-30-dominios-lacunas-1609`, `UX-33-mapa-lacunas-1609`, `UX-34-diversos-lacunas-1609`, `L2-04-f-mapserver-identify-legend-geometryserver`, `L2-04-i-wms-wmts-sld`, `L2-04-k-sync-replicas-esri`, `L2-07-campo`, `L2-07-d-mapa-offline-por-area`, `L2-09-3d`, `L2-09-a-terreno-terrain-rgb-relevo`, `L2-09-b-cena-extrusao-slides`, `L2-09-c-modelos-gltf-ifc-3dtiles`, `L2-12-b-layouts-elementos-exportacao`, `L2-12-impressao-layout`, `L2-13-a-versoes-ramo-reconciliar`, `L2-13-b-replicas-sincronizacao`, `L2-13-versionamento-sync`, `L2-14-a-ingestao-de-fluxos`, `L2-14-b-camada-viva-historico`, `L2-14-c-regras-alertas-incidentes`, `L2-14-tempo-real`, `L2-15-a-geoparquet-bucket-catalogo`, `L2-15-analitica-grande`, `L2-15-b-consultas-duckdb-em-escala`, `L2-18-camada-de-consulta-sql`, `L2-07-e-odk-central-ponte`, `L2-09-d-analise-3d-visibilidade`, `L2-12-c-series-de-mapas-lote`, `L2-16-a-sdk-python-geo`, `L2-16-b-jupyter-por-inquilino-isolado`, `L2-16-c-script-vira-ferramenta`, `L2-16-notebooks-scripts`.

### L3 motor AMC

Deve fazer: motor multicritério explicável como serviço, com robustez medida.

Não faz ainda (29 de 37 itens não entregues; pendentes 11): `L3-01-a-modelo-dado`, `L3-01-b-unidades`, `L3-01-c-extracao-fator`, `L3-01-d-transformacoes`, `L3-01-f-explicacao`, `L3-01-g-tela-motor`, `L3-01-j-equivalencia-motor-logistico`, `L3-01-motor-servico`, `L3-01-c2-extracao-em-lote`, `L3-01-i-exportacao-metodo`, `L3-04-restricoes`, `L3-06-criterios-de-feicao`, `L3-12-integracao-fluxo-e-api`, `L3-13-resultado-como-camada`, `L3-18-paridade-esri-amc`, `UX-26-amc-lacunas-1609`, `UX-27-multiescala-lacunas-1609`, `L3-02-a-monte-carlo-pesos`, `L3-02-b-sensibilidade-sobol-oat`, `L3-02-d-comparacao-cenarios`, `L3-02-robustez`, `L3-03-ahp-pares`, `L3-05-localizar-regioes`, `L3-09-backtest-decisao-real`, `L3-10-corredor-custo-minimo`, `L3-11-fator-de-rede`, `L3-08-pareto`, `L3-17-similaridade`, `L3-20-narrativa-de-resultado`.

### L4 rede de utilidades

Deve fazer: modelo de rede, traçado, edição com regras, sub-redes e diagramas, conectores BDGD/CIM, estruturas e regras avançadas.

Não faz ainda (72 de 73 itens não entregues; pendentes 33): `L4-01-a-pacote-de-ativos`, `L4-01-b-topologia-derivada`, `L4-01-c-importador-bdgd`, `L4-01-f-alcance-do-tracado-rede-real`, `L4-01-g-tarefas-import-tardio`, `L4-01-modelo-rede`, `L4-02-a-conectado-e-subrede`, `L4-02-b-montante-jusante`, `L4-02-c-isolamento`, `L4-02-tracado`, `L4-03-a-regras-de-conectividade`, `L4-03-c-edicao-topologica-no-mapa`, `L4-03-d-areas-sujas-e-validacao`, `L4-04-a-controladores-e-tiers`, `L4-04-b-atualizar-e-exportar-subrede`, `L4-05-a-exportar-opendss`, `L4-07-fluxo-de-potencia`, `L4-08-queda-de-tensao-e-carregamento`, `L4-23-isolamento-por-inquilino-na-rede`, `UX-08-telas-rede-de-utilidades-e-motor`, `L4-01-d-atributos-de-rede`, `L4-02-d-lacos-e-caminho-curto`, `L4-02-e-configuracoes-de-tracado`, `L4-03-b-terminais`, `L4-03-e-versao-de-rede`, `L4-03-edicao-rede`, `L4-04-c-sumarios-por-subrede`, `L4-04-c-unificar-subrede`, `L4-04-d-diagrama-esquematico`, `L4-05-b-cim-iec-61970-61968`, `L4-05-c-pandapower-e-matpower`, `L4-05-d-epanet-inp`, `L4-05-f-transmissao-sindat-sigel`, `L4-06-a-contencao`, `L4-06-b-estrutura-postes`, `L4-06-d-categorias-e-restricoes`, `L4-09-perdas-tecnicas-por-segmento`, `L4-10-continuidade-dec-fec`, `L4-11-gd-conectada-e-hospedagem`, `L4-12-inspecao-vegetacao-na-faixa`, `L4-13-integracao-telemetria`, `L4-16-api-rest-compativel-un`, `L4-21-qualidade-e-saude-da-rede`, `L4-22-desempenho-em-escala`, `L4-24-cartografia-de-rede`, `UX-24-rede-lacunas-1609`, `UX-28-parcelas-lacunas-1609`, `L4-01-e-dicionario-unidades-bdgd`, `L4-01-h-alinhamento-inspire-gnm`, `L4-02-f-resultados-e-exportacao`, `L4-04-e-diagrama-camadas-e-contencao`, `L4-04-subredes-diagramas`, `L4-05-conectores-rede`, `L4-05-e-gas-e-esgoto`, `L4-05-g-osm-power`, `L4-05-h-inspire-utility-networks`, `L4-06-c-objetos-nao-espaciais`, `L4-06-estruturas-regras-avancadas`, `L4-14-balanco-de-energia-por-alimentador`, `L4-15-serie-temporal-da-rede`, `L4-17-migracao-de-un-e-rede-geometrica`, `L4-18-rede-simples-trace-network`, `L4-19-planejamento-de-linha-nova`, `L4-20-consumidores-e-enderecos`, `L4-25-cenarios-e-se`, `L4-26-inspecao-de-campo-do-ativo`, `L4-28-identificadores-e-numeracao`, `L4-29-regras-de-atributo-de-rede`, `L4-parcelas-01-modelo-de-parcelas`, `L4-parcelas-02-fluxos-cogo`, `L4-30-manual-e-tour-de-rede`, `L4-parcelas-03-ajuste-e-qualidade`.

### L5 builder

Deve fazer: construtores arrasta-e-solta de aplicação, fluxo, formulário e narrativa.

Não faz ainda (57 de 63 itens não entregues; pendentes 39): `L5-01-b-widgets-mapa`, `L5-01-c-widgets-dado`, `L5-01-e-acoes-configuraveis`, `L5-02-a-editor-de-nos`, `L5-02-b-execucao-proveniencia`, `L5-03-a-construtor-elementos`, `L5-03-b-logica-condicional-calculo-restricao`, `L5-06-motor-widgets`, `L5-07-fontes-vistas-mensagens`, `L5-11-expressoes-no-navegador`, `L5-14-publicacao-links-embed`, `L5-26-construtor-popup`, `UX-07-telas-do-construtor-e-aplicativo`, `L5-01-app-builder`, `L5-01-d-widgets-pagina-menu`, `L5-01-f-modelos-app-galeria`, `L5-02-c-agendamento-variaveis`, `L5-02-d-exportar-python-importar-json`, `L5-02-f-fluxo-como-ferramenta-e-api`, `L5-02-fluxos`, `L5-03-c-dominios-listas-cascata`, `L5-03-d-repeticoes-relacionadas-anexos`, `L5-03-e-xlsform-ida-e-volta-idiomas`, `L5-04-a-blocos-de-conteudo`, `L5-10-temas-marca`, `L5-17-painel-elementos-avancados`, `L5-18-painel-parametros-url-vistas`, `L5-20-sites-paginas-publicas`, `L5-21-dados-abertos-catalogo-publico`, `L5-23-apps-instantaneos-motor-galeria`, `L5-24-apps-instantaneos-modelos-1`, `L5-27-simbologia-por-arrasto`, `L5-29-construtor-relatorio-pdf`, `L5-31-construtor-de-camada-esquema`, `L5-33-a-diagrama-de-trabalho`, `L5-33-b-modelos-e-trabalhos`, `L5-39-paridade-l5-e-manual`, `UX-31-fluxos-lacunas-1609`, `L5-02-e-iteradores-condicionais`, `L5-03-form-builder`, `L5-04-b-imersivos-sidecar-tour-swipe`, `L5-04-c-temas-capa-colecao`, `L5-13-edicao-concorrente`, `L5-19-painel-expressoes-de-dado-tempo-real`, `L5-22-sites-dominio-proprio-tema`, `L5-25-apps-instantaneos-modelos-2`, `L5-28-galeria-simbolos-rampas-estilos`, `L5-30-relatorio-lote-agendado`, `L5-32-vistas-de-camada`, `L5-33-c-atribuicao-avancada-indicadores`, `L5-34-captura-rapida-designer-pwa`, `L5-36-widgets-personalizados-sdk`, `L5-37-pacotes-modelos-entre-inquilinos`, `L5-04-storymap`, `L5-16-agente-escreve-configuracao`, `L5-35-missao-operacao-ao-vivo`, `L5-38-importadores-configuracao-esri`.

### L6 conectores

Deve fazer: acervo da casa e conectores vivos.

Não faz ainda (28 de 32 itens não entregues; pendentes 4): `L6-01-a-registro`, `L6-01-b-view-so-leitura`, `L6-01-f-lgpd`, `L6-01-g-licenca-curada`, `L6-01-acervo-casa`, `L6-01-c-tela-acervo`, `L6-01-d-ficha-fonte`, `L6-01-e-assinatura-e-uso`, `L6-02-b-wms-wmts`, `L6-02-d-arcgis-rest-externo`, `L6-02-g-pmtiles-xyz-tilejson`, `L6-02-h-csv-url-geojson-kml`, `L6-02-k-agendamento`, `L6-02-m-catalogo-endpoints-brasil`, `L6-03-paridade-conectores`, `L6-04-acervo-no-motor`, `L6-01-i-raster-e-arquivos`, `L6-02-conectores-vivos`, `L6-02-e-stac-externo`, `L6-02-f-geoparquet-duckdb`, `L6-02-i-google-sheets`, `L6-02-j-bancos-externos`, `L6-02-l-saude`, `L6-02-n-etl-na-entrada`, `L6-02-o-importacao-exportacao-formatos`, `L6-05-proveniencia-camada-externa`, `L6-01-j-multi-servidor`, `L6-06-descoberta-csw`.

### L7 operação

Deve fazer: instalador limpo, carga, segurança, manual e tour, observabilidade, alta disponibilidade, SDK e webhooks, medição e cobrança, i18n e acessibilidade, appliance no cliente, LGPD, suporte, produção final.

Não faz ainda (81 de 82 itens não entregues; pendentes 46): `HARD-01-varredura-de-seguranca-continua`, `HARD-02-testes-de-carga-e-caos`, `HARD-03-adversario-por-linha-em-lote`, `L7-01-d-instalador-extensoes`, `L7-19-b-journal-sem-segredo`, `L7-31-a-segredos-trilha`, `L7-01-a-compose-perfis`, `L7-01-b-instalacao-conteiner-limpo`, `L7-01-instalador-limpo`, `L7-03-a-antivirus-upload`, `L7-03-b-rate-limit-abuso`, `L7-03-c-ssrf-conectores`, `L7-03-d-injecao-consulta`, `L7-03-e-cabecalhos-csp-tls`, `L7-03-f-dependencias-cve-log-correcoes`, `L7-03-seguranca`, `L7-06-a-metricas-exporters`, `L7-06-b-alertas`, `L7-06-c-logs-consulta-req-id`, `L7-06-observabilidade`, `L7-15-processo-release`, `L7-16-assinatura-pacote`, `L7-19-segredos-e-certificados`, `L7-31-ambiente-homologacao`, `L7-33-modo-somente-leitura`, `L7-34-saude-profunda`, `L7-35-atualizacao-versao-assinada`, `D21 (dono)`, `L7-01-c-dado-demonstracao`, `L7-02-a-k6-cenarios`, `L7-02-b-pool-e-limites-por-inquilino`, `L7-02-carga`, `L7-03-g-asvs-nivel2-pentest`, `L7-04-a-manual-capturas-geradas`, `L7-04-b-tour-primeiro-acesso`, `L7-04-c-manual-admin-runbooks`, `L7-04-manual-e-tour`, `L7-06-d-paineis`, `L7-07-a-replica-postgres`, `L7-07-alta-disponibilidade`, `L7-07-b-replica-garage`, `L7-07-c-ensaio-failover`, `L7-08-a-webhooks-eventos`, `L7-08-b-sdk-python`, `L7-08-c-sdk-js`, `L7-08-d-portal-api-chaves`, `L7-08-sdk-api-webhooks`, `L7-09-a-medidor-diario`, `L7-09-b-planos-limites-relatorio`, `L7-09-medicao-cobranca`, `L7-10-a-i18n-pt-en-es`, `L7-10-b-acessibilidade-wcag21aa`, `L7-10-i18n-acessibilidade`, `L7-12-a-classificacao-retencao`, `L7-12-b-registro-tratamento-dpa-incidente`, `L7-12-lgpd-governanca`, `L7-14-instalacoes-apt-desta-linha`, `L7-17-capacidade-planejamento`, `L7-18-custo-por-inquilino`, `L7-21-pagina-status`, `L7-22-sla-e-incidentes`, `L7-23-pgbackrest-pitr`, `L7-24-drill-restauracao`, `L7-25-exportacao-inquilino`, `L7-26-cdn-tiles`, `L7-27-origem-br-soberania`, `L7-29-roteiro-demonstracao`, `L7-30-teste-parceiro-pro-agol`, `L7-03-b-antivirus-anexos`, `L7-04-d-videos-por-tarefa`, `L7-05-producao-final`, `L7-11-a-appliance-licenca`, `L7-11-appliance-cliente`, `L7-11-b-appliance-sem-internet`, `L7-11-c-telemetria-opcional`, `L7-13-a-chamados`, `L7-13-c-laco-agentico-suporte`, `L7-13-suporte-chamados`, `L7-14-extensoes-fdw`, `L7-28-iso27001-controles`, `L7-32-postgres-manutencao-versao`.

## Backlog: os itens por linha

Prioridade 1 = primeiro. `dep. abertas` = dependências ainda não entregues.

### L0 fundação (75 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L0-01-repo` | 1 | entregue | 2 | 3 | — | — |
| `L0-02-a-login-sessao` | 1 | entregue | 2 | 3 | L0-12-contrato-api-e-limites | — |
| `L0-02-b-politica-senha-bloqueio` | 1 | entregue | 2 | 3 | — | — |
| `L0-02-d-token-servico` | 1 | entregue | 2 | 3 | — | — |
| `L0-02-e-varredura-cruzada-rls` | 1 | parcial | 4 | 3 | — | 29 funcoes (19 fura isolamento + 10 destrutiva) corrigidas e testadas na trilha secdef (migracao 20260906T1601, resgatada e confirmada); colisao de merge com wt/g1fix resolvida em plat.ldap_provisionar (20260906T1758); EXECUTE para PUBLIC ja fechado por outra trilha (20260906T1615); achado critico novo: plat.tenant_apagar_interno e plat.agenda_registrar_fim com EXECUTE de plat_app em producao (REVOKE pronto, nao executado); 6 funcoes de drift (fura isolamento) sem migracao correspondente no repositorio; varredura completa das 117 funcoes em laco/handoffs/T3/VARREDURA-funcoes-privilegiadas.md; nada promovido a producao, falta merge + db/migrar.sh |
| `L0-02-f-tela-usuarios` | 1 | entregue | 1 | 3 | L0-10-eventos-historico | — |
| `L0-02-tenant-auth` | 1 | parcial | 2 | 3 | — | Bloqueio de T2 ('P3 depende da trilha B; P9 cronista em curso') estava PARCIALMENTE vencido: a trilha B (L0-03-catalogo) e a documentação (P9: CHANGELOG com múltiplas entradas de turno 3 + ADR 0002) já chegaram ao HEAD. Mas P3 ('make check' completo verde) CONTINUA não satisfeito -- e não por defeito deste item: rodada completa hoje (tests/unit+tests/api, não-lento, ~04:30 de execução) devolve ~40 falhas espalhadas por dezenas de itens não relacionados (geocodificador, acervo, arquivos, banco, eventos, migrações, privilégios, saúde, documento, miniatura) -- P3 é gate do LAÇO INTEIRO, não deste item. Mecanismo do PRÓPRIO item reverificado hoje com prova fresca e 2 defeitos reais corrigidos nesta rodada (commits be3eb8c/7c63251): RLS íntegra, 0 função SECURITY DEFINER com EXECUTE para PUBLIC (test_funcoes_seguras.py 20/20 -- achado antigo do G1-T2/secdef já resolvido em commit anterior desta mesma trilha, 4c4730d); sessão/2FA/troca de senha (test_sessao.py 8/8, corrigido o teste -- config semeada do inquilino demo travava o gancho de teste de expiração ociosa, não o mecanismo); papel/privilégio em lote (test_usuarios.py 11/11, corrigido bug real em CursorSchemaAmbiente.executemany). Achado por leitura, FORA do escopo de conserto pequeno: docs/openapi.json está 28 rotas atrasado (168 de 196 vivas); regenerá-lo (testado e revertido) revela que tests/api/cruzado_casos.py não tem caso definido para NENHUMA das 28 rotas novas (convites, redefinição de senha, uploads, geocodificador, ogc/records, importações) -- a cláusula 'varredura de TODAS as rotas' do portão está, hoje, medida sobre um retrato incompleto (RETOMADA_20260906.md pendência 3, do gerente); não fixei o arquivo para não deixar ~30 testes vermelhos sem os casos correspondentes escritos. Achados do G1 (turno 3, ramo wt/g1fix, NÃO mesclado: sessão ociosa não é limpa pelo periódico, pendência de 2FA vazando em 7 rotas, prefixo de token com 12 caracteres não 8, login LDAP trancava conta legítima) não avaliados/consertados aqui -- pertencem aos sub-itens L0-02-a/b/c/d e L0-08-d-ldap, cujo conserto já existe em outro ramo aguardando merge do gerente. |
| `L0-02-z-apagar-inquilino-apaga-schema` | 1 | entregue | 1 | 8 | L0-02-tenant-auth, L0-04-ingest-vetor | — |
| `L0-03-a-modelo-item` | 1 | entregue | 1 | 3 | L0-12-contrato-api-e-limites | — |
| `L0-03-b-pastas-tags-categorias-classificacao` | 1 | entregue | 0 |  | — | — |
| `L0-03-c-busca` | 1 | entregue | 0 |  | — | — |
| `L0-03-catalogo` | 1 | entregue | 1 | 2 | L0-02-tenant-auth | — |
| `L0-03-d-grupos` | 1 | entregue | 0 |  | L0-10-eventos-historico | — |
| `L0-03-e-compartilhamento` | 1 | pendente | 2 | 8 | — | órfão devolvido pelo driver em 2026-09-10 17:00 |
| `L0-03-f-tela-conteudo` | 1 | refutado | 1 | 3 | — | estrela de favorito mostra o contrario do que o servidor guardou apos recarga de lista em voo; e2e do repo para em test_conteudo.py:181 |
| `L0-03-g-detalhe-item-miniatura` | 1 | entregue | 0 |  | L0-03-f-tela-conteudo, L0-11-arquivos-objetos, L0-05-a-fila-postgres | — |
| `L0-04-a-upload-arquivo` | 1 | refutado | 1 | 3 | L0-11-arquivos-objetos | ADVERSARIO T3 (independente): nenhum usuario que nao seja admin do inquilino consegue usar o upload - a propria tela pede token com escopo admin:inquilino (web/js/uploads/*.js), e esse escopo so pode ser emitido para perfil admin; o vocabulario fechado de escopos (app/auth/escopos.py) nunca ganhou entrada para 'enviar arquivo', entao autenticado('conteudo.criar') sem escopo_token= cai no padrao admin:inquilino. MESMA causa raiz de L0-11-arquivos-objetos (app/rotas_arquivos.py linha 65) - afeta os dois itens, tratar junto. Mecanismo central (isolamento entre usuarios, integridade sha256, conclusao ponta a ponta) testado com token admin real e PASSA. Laudo: handoffs/T3/L0-04-a-ADVERSARIO.md |
| `L0-04-b-inspecao` | 1 | parcial | 3 | 3 | L0-04-a-upload-arquivo | medido 10/09: o bloqueio anterior ('wt/g3fix: 12 arquivos do portão cobertos, tempo_inspecao_s medido, tests/medidas/L0-04-b-inspecao.json') descreve trabalho que existe só no ramo wt/g3fix — em wt/lancamento não há tests/medidas/L0-04-b-inspecao.json, nem tests/api/ingestao/test_formatos_base.py, nem os 9 formatos extras (mesmo achado do L0-04-d). app/ingestao/formatos.py só reconhece shapefile.zip/gpkg/geojson/csv — os outros 8 dos 12 arquivos que o portão pede (shapefile latin-1, KML com pastas, GPKG 3 camadas, XLSX 2 planilhas, DXF com blocos, GML, GDB zipada, FlatGeobuf) nem seriam aceitos pela rota hoje. Não consegui medir contra `entrega` (127.0.0.1:8190): processo fora do ar nesta rodada, não reiniciado por instrução. Escopo real: o mesmo do L0-04-d (trazer os formatos de wt/g3fix) + o teste dos 12 arquivos com fixture — várias horas, não construído nesta rodada. |
| `L0-04-c-tabela-camada` | 1 | parcial | 5 | 3 | L0-04-b-inspecao, L0-05-a-fila-postgres | 2 dos 4 achados do adversário G3 corrigidos com prova nesta rodada (commits af63bab/5c881cd/07484ef no ramo wt/destrava): uso_bytes agora desce no expurgo (medido: sobe 188.416 na carga, volta ao valor exato depois de apagar+expurgar via catalogo.lixeira_expurgar); slug com hífen agora importa (migração 20260906T1812_ingestao_slug_com_hifen.sql + teste test_inquilino_com_hifen_no_slug_importa); medida tempo_import_100k_s=14,0s gravada (teto do portão 60s, tests/medidas/L0-04-c-tabela-camada.json). Restam 2 cláusulas nomeadas do próprio G3: (a) d_<slug> SEM prefixo de instalação -- duas instalações/bases no MESMO Postgres com um inquilino de mesmo slug colidem no mesmo schema físico (medido: 84 schemas d_* hoje compartilhados entre produção e trilhas de teste; conserto exige threading de um identificador de instalação em toda função que monta 'd_'||slug -- fora do escopo de conserto pequeno); (b) nenhum teste automatizado prova '0 tabela órfã' sob SIGKILL do worker no meio da carga (só verificado por leitura de código: _limpar_orfao só roda em except Cancelado/FalhaDefinitiva, nunca em finally). |
| `L0-04-d-formatos-base` | 1 | parcial | 3 | 3 | L0-04-c-tabela-camada | achado maior, medido 10/09: só 4 formatos existem em app/ingestao/formatos.py em wt/lancamento (shapefile.zip, gpkg, geojson, csv) — os 9 outros (geojsonseq, kml, kmz, gpx, xlsx do portão do L0-04-d; gml, flatgeobuf, dxf, gdb do L0-04-b) foram construídos no ramo wt/g3fix (ver laco/handoffs/T3/G3-CONSERTO-funcional.md, commit 1409076) e NUNCA foram mesclados em wt/lancamento — o mesmo padrão do L0-04-k e L0-02-z: bloqueio antigo descrevia um ramo separado como pronto. Não consegui medir contra a trilha `entrega` (127.0.0.1:8190) porque o processo estava fora do ar (connection refused) nesta rodada — não reiniciei, por instrução. Além disso, mesmo dentro dos 4 formatos existentes, CSV sem coluna de coordenada falha no job de carga por exigir SRID incondicional (ver bloqueio anterior, ainda válido). Escopo real: trazer os 9 formatos que faltam (idealmente recuperando o diff de wt/g3fix se o worktree ainda existir, em vez de reescrever) + o conserto do SRID — várias horas, não cabe nesta rodada de 20 min por item. |
| `L0-04-ingest-vetor` | 1 | parcial | 5 | 3 | — | Herda os 2 pendentes de L0-04-c (schema d_<slug> sem prefixo de instalação; sem teste automatizado de morte do worker no meio da carga). Núcleo (4 formatos: shapefile.zip/gpkg/geojson/csv) provado de ponta a ponta hoje: tests/api/ingestao 15/15 passam (só test_cota_excedida_nao_cria_tabela falha, por causa não relacionada -- a checagem de tabela órfã varre TODO o schema físico d_demo compartilhado por todas as trilhas do laço, não só esta trilha; conferido caso a caso: os 2 órfãos reais existentes eram debris de sessões antigas, já limpos, 0 órfão novo desta rodada). Do portão do item PAI, ainda faltam por construir (handoffs/T3/L0-04-ingest-vetor.md, seção Pendências): KML/KMZ, GPX, XLSX/XLS/ODS, DXF/DWG, FileGDB/FlatGeobuf/GML/MapInfo/GeoParquet -- só 4 dos ~9-13 formatos do ADR 0005 têm suporte e teste. Sem teto de tamanho/complexidade por feição declarado (G3 mediu 1 milhão de vértices 'passa' em 14,8s medido, mas não há FEICAO_BYTES_MAX nem limite de npoints no repositório). |
| `L0-04-k-rota-formatos-encoberta` | 1 | refutado | 3 | 9 | — | adversario T9: varredura anti-sombreamento cega ao convertor {x:path} multi-segmento; xfail test_l0_adv2_rotas_path.py |
| `L0-05-a-fila-postgres` | 1 | parcial | 2 | 3 | L0-12-contrato-api-e-limites | wt/partilha (recurso partilhado) consertou os 4 achados do adversario G3 sobre recurso partilhado: chave do trinco agora e (tenant_id, chave) - inquilino B nao trava mais pela chave do A; fila reparte por inquilino (menos trabalho rodando, depois mais espera) antes da prioridade do usuario - medido: quem chegou 1o saiu da posicao 21a para a 1a; plat.job_ceifar_vencidos novo deixa a API ceifar trabalho sem executor vivo (antes, 68s sem worker o job seguia rodando); morte do executor sem sinal (job_ceifar) passa a consumir TENTATIVA, nao reinicio - 3 SIGKILL seguidos fecham falhou na 3a, nunca concluido (systemctl restart continua reinicio); traceback saneado (app/jobs/sanear.py) antes de virar log ou campo erro, sem caminho de servidor nem credencial. Reproduzido ao vivo nesta trilha (tests/api/adversario_g3/g3_sigkill_worker.py: veredito PASSA) e via tests/api/jobs/test_jobs_reinicio.py reescrito (kill-9 agora le tentativa, nao reinicios). Migracao 20260906T1615a3f. Ver handoffs/T3/ataque-g3-ADVERSARIO.md e handoffs/T3/PARTILHA-CONSERTO.md. NAO verificado nesta trilha (fora do escopo de recurso partilhado, refutacao do proprio item): 10 mil jobs + /saude < 50ms; mudar o relogio do heartbeat. |
| `L0-05-b-progresso-cancelamento` | 1 | parcial | 2 | 3 | L0-05-a-fila-postgres | wt/partilha (recurso partilhado) consertou o achado 1 do adversario G3: limite de conexoes SSE (app/jobs/eventos.py) virou teto da INSTALACAO com 3 niveis (usuario/inquilino/total), repartido por PLAT_API_PROCESSOS entre os processos de uvicorn --workers N - antes o teto por usuario era por PROCESSO (a unidade sobe 2, o limite real valia o dobro do publicado) e nao havia teto por inquilino nenhum. Ver handoffs/T3/PARTILHA-CONSERTO.md. NAO consertado aqui (fora do escopo de recurso partilhado, ver handoffs/T3/ataque-g3-ADVERSARIO.md): plat.job_log aceita linha depois do estado final (linhas_log sobe mesmo apos falhou/cancelado); evento 'fim' via SSE significa duas coisas (fim de job x fim de conexao de 30 min) - painel de detalhe fica mudo. |
| `L0-10-eventos-historico` | 1 | parcial | 2 | 3 | — | G4-CONSERTO (wt/g4fix, 4cbedea): consertados G4-08 (DELETE /api/arquivos grava arquivos/apagar) e G4-10 (evento_expurgar/log_expurgar validam p_meses, nunca alcancam o mes corrente, sem EXECUTE para plat_app/plat_worker; expurgo por inquilino em funcao separada). Falta G4-02/03 (cobertura medida contra o app vivo e lista vazia - de outra trilha, mas o vocabulario de eventos_esperados.py ja foi reescrito com ROTAS_SEM_EVENTO obrigatorio), G4-11 (sem periodico de particao/retencao), G4-12 (sem exportacao CSV), G4-13 (sem tela Auditoria) - fora do escopo desta trilha. |
| `L0-11-arquivos-objetos` | 1 | parcial | 3 | 8 | — | clausula G4-19 fechada em wt/g4fix: /saude responde 503 com obrigatorio configurado e doente (OBRIGATORIOS=(garage,)), corpo declara servicos_obrigatorios, ADR 20260908T2125 com a fronteira (sem URL = ausente, 200; martin/titiler/worker informativos); teste adversarial G4-19 saiu de xfail estrito para portao, teste de fronteira novo, contrato do corpo atualizado (23 passed, 13 xfailed de outros achados); openapi.json regenerado (rotas de cotas do rebase) e registro de migracao renomeada 049 limpo na trilha. Falta so a juncao em master (ramo ja na fila) |
| `L0-12-contrato-api-e-limites` | 1 | parcial | 3 | 8 | — | CLAUSULA G4-23 FECHADA (faltam G4-14 rate limit, G4-15 teste de contrato/lint de esquema, G4-16 Retry-After no codigo): erro_do_banco so devolve 403 "fora do inquilino" com prova de violacao de row-level security na mensagem; os demais 42501 (GRANT faltando, schema errado, papel mal configurado) viram 500 configuracao_banco com a causa real no diario (wt/g4fix, commits c87118a8/c027abed/c5de88d5/aca8c8e3). Teste adversarial G4-23 graduado de xfail estrito para portao + teste de fronteira novo (RLS continua 403); CONTRATO_API.md ganhou a linha do 500. tests/api/test_g4_adversario.py + tests/unit/test_erros.py: 34 passed, 12 xfailed (xfails estritos de outros achados), ruff limpo na trilha g4fix. |
| `L0-13-dado-demonstracao` | 1 | refutado | 3 | 9 | L0-04-d-formatos-base, L0-03-e-compartilhamento | adversario T9: checagem de nome de cliente quebrada (extrai '?i' pela flag do regex) e docs/DADO_DEMO.md tomado por outro item; xfail test_l0_adv2_dado_demo.py |
| `L0-14-identidade-visual` | 1 | tentando | 2 | 3 | L0-02-tenant-auth | adversario G4: 56 literais de cor fora de web/estilo/tokens.css (style.css 21, mapa.css 9, tarefas.css 9, conteudo.css 4, js 13) e a varredura que o portao exige nao existe em tests/ nem no Makefile; nao ha rota /estilo; das 19 telas HTML do produto (o portao ainda fala em 9) so 5 carregam os tokens. Clausula (b), o par tipografico vendorizado com sha256 e OFL-1.1, esta de pe. Clausulas (c),(d),(f) nao medidas: sem navegador nesta maquina |
| `L0-02-c-2fa-totp` | 2 | entregue | 2 | 3 | — | — |
| `L0-02-g-checagem-privilegio-papel-id` | 2 | entregue | 2 | 8 | L0-02-tenant-auth | — |
| `L0-03-h-lixeira-protecao-status` | 2 | pendente | 2 | 8 | — | órfão devolvido pelo driver em 2026-09-10 17:00 |
| `L0-03-i-dependencias` | 2 | entregue | 0 |  | — | — |
| `L0-03-j-transferencia-dono` | 2 | pendente | 2 | 8 | L0-03-e-compartilhamento | órfão devolvido pelo driver em 2026-09-10 17:00 |
| `L0-04-e-formatos-cad` | 2 | entregue | 1 | 3 | L0-04-c-tabela-camada | — |
| `L0-04-f-fgdb-parquet-fgb-gml` | 2 | parcial | 1 | 3 | L0-04-c-tabela-camada | Conserto de segurança feito: ogrinfo/ogr2ogr da ingestao vetorial (que herdava so RLIMIT_DATA e o ambiente inteiro do worker) agora roda com app/ingestao/isolamento.py (ambiente GDAL sem HTTP/PROJ/READDIR + seccomp bloqueando AF_INET/AF_INET6 nas leituras que nao tocam Postgres), mesmo cinto+fecho do ADR 0015. O portao do item (GDB->plat.dominio, raster dentro do GDB listado como nao importado, FlatGeobuf/GML/Parquet fim-a-fim, medida de tempo por formato, cenarios do adversario) NAO foi construido nesta trilha: os 15 commits do Kimi sao quase todos de outros itens (L2-10-a dominios/subtipos, G3 adversario, L0-04-c/d). Suite de teste do diff NAO termina em 10 min (trava apos ~21 casos, 2 tentativas em foreground, timeout 600s cada) - registrado como achado, nao investigado a fundo por ordem do coordenador. |
| `L0-04-g-atualizar-dados` | 2 | pendente | 0 |  | L0-04-c-tabela-camada, L0-03-l-versoes-item | — |
| `L0-04-h-exportar` | 2 | entregue | 1 | 3 | L0-04-c-tabela-camada, L0-05-a-fila-postgres, L0-11-arquivos-objetos | — |
| `L0-05-c-tela-tarefas` | 2 | refutado | 2 | 3 | L0-05-b-progresso-cancelamento, L0-03-f-tela-conteudo | ADV G3: reproduzido em Node no modulo real - apos o 'fim' de 30 min a assinatura e apagada e nunca reassinada (painel de detalhe fica mudo). Aguentou: 100 mil jobs, 1a pagina em 0,138 s |
| `L0-05-d-periodicos` | 2 | entregue | 3 | 9 | L0-05-a-fila-postgres | — |
| `L0-05-e-justica-entre-inquilinos` | 2 | parcial | 2 | 8 | L0-05-jobs | passa na trilha entrega; falta trazer para o ramo da demonstração. db/migracoes/20260906T2110_jobs_justica_inquilino.sql (o rodízio por inquilino em plat.job_pegar) só existe em wt/entrega — em wt/lancamento plat.job_pegar (db/migracoes/006_jobs_transicoes.sql) não tem rodízio nenhum, é FIFO simples. tests/medidas/L0-05-e-justica-entre-inquilinos.json na trilha entrega mostra as duas cláusulas do portão medidas de verdade: com 2×300s de B + 1×1s de A, A espera 0,5s (≤1 job de B) e o mesmo com 50×300s de B (adversário) dá 0,2s — cláusula 'no máximo 1 job de B' cumprida nos dois casos; cota de simultâneos por inquilino também medida (3,1s). Achado curioso: tests/api/jobs/test_jobs_reinicio.py JÁ EXISTE em wt/lancamento (não é código órfão), mas sem a migração de justiça o teste de rodízio em si não tem o que exercitar. Falta ainda, mesmo na entrega: e2e da tela Tarefas com posição na fila (não achei captura). |
| `L0-05-jobs` | 2 | parcial | 2 | 3 | — | Bloqueio de T2 (semeadura e2e/perfil visualizador/Cache-Control; trilha do catálogo) RESOLVIDO e commitado -- confirmado hoje: 7037009/ea77246/a496cdd/4053e3c/7cf33c2 e a árvore de L0-03-catalogo são todos ancestrais do HEAD. Bloqueio ATUAL (adversário G3, turno 3, laco/handoffs/T3/ataque-g3-ADVERSARIO.md, commit-alvo 2520afd, nada consertado desde então -- só 2 commits tocaram app/jobs/ e nenhum destes achados): (1) ceifador de job morto só roda DENTRO do processo do worker -- sem worker vivo o job fica 'rodando' além do limite declarado (68s > LIMITE_SEM_SINAL_S=60s); (2) chave do lock (plat.job_pegar) não filtra por tenant_id -- inquilino A trava inquilino B com a mesma chave; (3) fila sem cota de vazão entre inquilinos (medido: quem criou o job primeiro foi atendido por último); (4) traceback do erro não é saneado antes de plat.job_log/API (vaza caminho absoluto do servidor); (5) limite de conexões SSE por usuário é por PROCESSO, não global (20 reais com --workers 2, não os 10 declarados); (6) plat.job_log aceita linha de log depois do job já em estado final; (7) tela Tarefas: evento SSE 'fim' serve para 'job acabou' E 'reconecte (30 min)' sem distinção -- cliente encerra a assinatura e nunca reconecta; (8) L0-05-d: chaves de periódico são constantes globais, qualquer inquilino comum ocupa a chave técnica jobs.sessoes_expurgar. |
| `L0-06-a-dump-logico` | 2 | entregue | 2 | 9 | L0-04-c-tabela-camada, L0-11-arquivos-objetos | — |
| `L0-06-c-restore-drill` | 2 | parcial | 2 | 8 | — | Ensaio de restauracao completo: job backup.restore_drill (restaura o ultimo dump em banco de ensaio, COUNT(*) de todas as tabelas com tenant_id contra producao, sha256 de objetos do bucket contra o manifesto), plat.backup_drill, periodico mensal, drill curto na suite em 3,7 s (carga 7,20; teto 60 s), dump corrompido acusado e notificado, /saude publica a data do ultimo ensaio, runbook e ADR. Achado: o dump do schema da plataforma so restaura com postgis+pgcrypto+pg_trgm+unaccent. |
| `L0-06-d-exportar-inquilino` | 2 | parcial | 2 | 8 | L0-05-a-fila-postgres | Pacote aberto do inquilino (GeoPackage com gpkg_metadata + catalogo.json validado por JSON Schema + arquivos.zip do bucket + manifesto sha256), estimativa antes do clique, cota de 1/dia, importador que recria itens com os mesmos uuids, secao na tela e e2e com 3 capturas; medido 23.782 bytes em 0,55 s (carga 12,02). Nao feito: restaurar conteudo de camada e arquivos no destino (fica com a ingestao). |
| `L0-06-e-status` | 2 | parcial | 2 | 8 | — | Pagina /status e GET /api/status abertos (noindex, cache de 30 s, so agregado): servicos, migracoes, fila, backup, disco, bucket, certificado, historico de 90 dias com percentual do mes de plat.status_amostra (periodico status.amostrar a cada 5 min) e log de correcoes higienizado do CHANGELOG. 1.000 pedidos em 1,07 s, 0 consulta ao banco; retrato frio 92 ms. Clausula do ensaio de restauracao fica pendente ate o L0-06-c entrar em master (campo responde 'indisponivel' com a razao). |
| `L0-07-a-configuracoes-org` | 2 | refutado | 3 | 9 | L0-11-arquivos-objetos | adversario T9: PUT /api/org falha ao vivo por cota do inquilino demo perto do teto (poluicao de trilha); sem prova do portao; laudo L0-2 |
| `L0-07-admin-org` | 2 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L0-07-b-papeis-privilegios` | 2 | entregue | 1 | 3 | L0-03-e-compartilhamento | — |
| `L0-07-c-cotas-uso` | 2 | refutado | 2 | 9 | L0-04-c-tabela-camada, L0-11-arquivos-objetos | adversario T9: plat.uso_inquilino e escrito mas nunca lido: nenhuma rota nem tela Uso; xfail test_l0_adv2_cotas_uso.py |
| `L0-07-d-smtp-convites` | 2 | entregue | 2 | 8 | L0-05-a-fila-postgres | — |
| `L0-07-f-console-plataforma` | 2 | parcial | 2 | 8 | L0-07-c-cotas-uso | passa na trilha entrega; falta trazer para o ramo da demonstração. web/plataforma.html e web/js/auth/plataforma.js não existem em wt/lancamento. tests/medidas/L0-07-f-console-plataforma.json na entrega cobre TODAS as cláusulas citadas no portão: 10 rotas /api/plataforma testadas com sessão comum/token/anônimo/cookie forjado → 404 (não-superadmin); página console pronta em 152 ms; e2e completo 'criar demo3 → suspender → 503 no navegador → reativar' medido como 1 fluxo passando (tests/e2e/test_plataforma.py). |
| `L0-09-a-procedencia` | 2 | parcial | 3 | 8 | L0-05-a-fila-postgres | cláusula do e2e de navegador fechada (60c57ab8): ficha com bloco cheio mostra section.procedencia, nota 10,0/10 e etiquetas medido/declarado; item sem bloco mostra "Sem procedência registrada"; capturas 1280/390 e 0 erro de console, 3 corridas verdes na trilha plat_tstac contra o próprio ramo; fila_merge RECUSOU a entrada porque wt/stac é ramo protegido (refutação aberta, junção do dono) — a entrada na fila fica para quando a proteção sair; a cláusula da exportação do inquilino segue na fronteira documentada até L0-06-d existir |
| `L0-14-cli-admin` | 2 | refutado | 3 | 9 | L0-04-c-tabela-camada, L0-06-d-exportar-inquilino | adversario T9: scripts/plat substituido pelo CLI menor de outro item (so segredo/demo); app/cli/principal.py orfao; 16/16 testes do item falham; xfail test_l0_adv2_cli_admin.py |
| `L0-15-marca` | 2 | pendente | 0 |  | L0-14-identidade-visual | — |
| `UX-29-org-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `L0-02-g-perfil-usuario` | 3 | entregue | 4 | 8 | L0-11-arquivos-objetos | — |
| `L0-03-k-favoritos-notificacoes` | 3 | refutado | 1 | 3 | L0-10-eventos-historico | notificacao interna nao existe (nenhuma rota, tabela, migracao ou codigo); favorito com estado errado na tela |
| `L0-03-l-versoes-item` | 3 | pendente | 2 | 8 | L0-10-eventos-historico | órfão devolvido pelo driver em 2026-09-10 17:00 |
| `L0-04-j-camada-vista` | 3 | pendente | 1 | 3 | L0-04-c-tabela-camada | ramo wt/il004jcamad rebaseado sobre master (5858b51) sem nenhum codigo do item: os 11 commits sao merges de wt/partilha (adversario G3, recurso partilhado) e wt/destrava (4 pais parciais), zero ocorrencia de 'vista' no diff inteiro. 0/6 clausulas do portao provadas. Handoff em laco/handoffs/T4/L0-04-j-camada-vista.md com o veredito e o proximo passo. |
| `L0-06-b-pitr-pgbackrest` | 3 | pendente | 2 | 8 | — | não construível nesta trilha: pgbackrest ausente (apt pelo gerente, root), archive_mode=on + archive_command exigem reinício do Postgres COMPARTILHADO (decisão do dono com janela; hoje archive_mode=off, archive_command disabled, wal_level=replica ok) e repositório fora da máquina (recurso externo/off-site não provisionado); L0-06-a é dependência |
| `L0-06-backup-status` | 3 | refutado | 1 | 9 | L0-04-ingest-vetor | adversario turno9 (wt/f2-adv-l01): os 2 periodicos de backup por inquilino (backup.executar/backup.ensaio_restauracao) nascem ativa=false e nunca rodaram; e mesmo ligados, sincronizar_periodicos so grava agenda no inquilino tecnico 'plataforma' -- inquilino de cliente (demo) tem ZERO linhas de agenda desses tipos. 'Backup diario' automatico por inquilino nao existe hoje para nenhum inquilino real, so disparo manual. Teste tests/api/adversario/test_l0_backup_status_periodico.py (2 casos, xfail strict, confirmados). |
| `L0-07-e-relatorios` | 3 | parcial | 2 | 8 | L0-07-c-cotas-uso, L0-10-eventos-historico | passa na trilha entrega; falta trazer para o ramo da demonstração. app/relatorios/ não existe em wt/lancamento (só em wt/entrega). tests/medidas/L0-07-e-relatorios.json na entrega cobre as cláusulas do portão: página Atividade pronta em 107,5 ms; job de relatório de itens com 10.001 itens conclui em 0,6 s de job / 0,63 s de parede (portão pede ≤10 s) — folga grande. Ainda faltaria confirmar ao vivo, mesmo na entrega, as cláusulas de CSV por relatório (cabeçalho documentado) e agendamento por e-mail — não medidas no json, só citadas no bloqueio antigo. |
| `L0-08-a-oidc` | 3 | parcial | 2 | 8 | L0-07-a-configuracoes-org | causa-raiz da suíte cruzada fechada: executemany não passava pela reescrita de schema (42501→403 em POST/PUT /api/papeis); sobrecarga + 5 testes unitários novos, 14 casos cruzados passam na trilha do item (-k "papeis or sso or oidc"); falta a suíte cruzada COMPLETA verde por 41 rotas de OUTROS itens sem caso em cruzado_casos.py (convites, smtp, redefinição de senha, uploads multipart, importações, geocodificador, /ogc/records) — cláusula de suíte compartilhada, não deste item |
| `L0-08-b-saml` | 3 | parcial | 1 | 8 | L0-08-a-oidc | passa na trilha entrega; falta trazer para o ramo da demonstração. app/auth/saml.py, db/migracoes/20260907T2050_provedor_saml.sql e toda a suíte tests/api/saml/ NÃO existem em wt/lancamento (grep vazio) — SSO local só tem LDAP/OIDC hoje nesse ramo. tests/medidas/L0-08-b-saml.json na trilha entrega confirma os números do bloqueio antigo: 16 testes forjados sem Docker + 5 contra Keycloak 26 (latência SP-initiated 533,7 ms sob carga alta, não é cláusula de desempenho). Cláusula pendente MESMO na entrega: nenhuma captura de e2e SAML em tests/e2e/capturas — mas o motivo dado ('chromium quebrado') pode estar desatualizado, porque L0-08-c/L0-08-e da MESMA trilha entrega usam chromium/playwright com sucesso (páginas Logins medidas em 51-57 ms); vale re-testar antes de aceitar a desculpa de novo. |
| `L0-08-e-mapeamento-provisionamento` | 3 | parcial | 2 | 8 | L0-08-a-oidc | passa na trilha entrega; falta trazer para o ramo da demonstração. Medido ao vivo 10/09 em http://127.0.0.1:8190: schema ProvedorOidcEntrada tem mapa_grupo_perfil, perfil_padrao e atributo_grupos (o mapeamento valor->perfil/grupo que o portão pede) e aceita criação real via POST /api/org/oidc. tests/medidas/L0-08-e-mapeamento-provisionamento.json na trilha entrega mostra login_gis_editores_vira_editor=1 caso (tests/api/oidc/test_provisionamento.py, Keycloak real) e tela 'Logins' pronta em 57,2 ms. app/auth/oidc.py, tests/unit/test_provisionamento.py e tests/e2e/test_logins.py NÃO existem em wt/lancamento (grep vazio) — mesmo padrão dos outros itens do lote: trabalho pronto num ramo que nunca foi mesclado. |
| `L0-08-sso` | 3 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L0-09-b-editor-iso-mgb` | 3 | parcial | 1 | 3 | L0-09-a-procedencia | Editor completo (essencial/completo, validar sem gravar, salvar), sincronização de título/resumo/palavras-chave/créditos/termos com o item nos dois sentidos, linhagem computada de procedência+eventos, estilo por inquilino (mgb2/iso19115-3/dublin core) sobre armazenamento único, paridade com Metadata 11.4 documentada, e as 3 refutações provadas (5 MB, datas fora de ordem, extent divergente=aviso). 11 testes de API + 1 e2e chromium com captura, todos verdes. PARCIAL por 1 fronteira honesta: a cláusula 'metadado exportado no L0-06-d' não pode ser cumprida porque L0-06-d-exportar-inquilino não existe no repositório (nenhuma linha entregue/parcial); e a dependência L0-09-a-procedencia (ac4dbce) não está mesclada em master, então a linhagem foi provada com dados.procedencia sintético, não com camada importada de verdade. |
| `L0-09-c-xml-iso-validacao` | 3 | parcial | 2 | 8 | L0-09-b-editor-iso-mgb | Importacao ISO 19139 na rota POST /api/itens/{id}/metadado.xml: 4 clausulas do portao passaram (XSD 0 erro em 3 itens; registro real da INDE preenche 22 campos; ida e volta diff=0; XML invalido 422 com linha/coluna) + refutacao (XXE, bomba, 50 MB, namespace errado). Fora: ISO 19115-3 e botao de importar na tela. XSD virou parecer com posicao, nao porteiro: o registro da INDE nao valida no XSD oficial. |
| `L0-09-d-ogc-records-csw` | 3 | pendente | 0 |  | L0-09-b-editor-iso-mgb, L0-03-e-compartilhamento | — |
| `L0-09-metadado-catalogo` | 3 | refutado | 2 | 3 | — | adversario G4: portao nao cumprido - sem CSW GetRecords, sem ISO 19115-3, sem editor de metadado na tela, sem e2e nem paridade escrita; a refutacao propria do item (apagar item protegido / usado por) AGUENTOU e a validacao ISO 19139 contra XSD cacheado passa |
| `L0-04-i-fonte-registrada` | 4 | entregue | 2 | 9 | L0-04-c-tabela-camada | — |
| `L0-05-e-worker-em-container` | 4 | refutado | 3 | 9 | — | adversario T9: clausula central (job real dentro do conteiner) nunca provada; commit de fechamento nao ancestral de wt/uniao; xfail test_l0_adv2_worker_container.py |
| `L0-08-c-govbr` | 4 | parcial | 2 | 8 | L0-08-a-oidc | passa na trilha entrega; falta trazer para o ramo da demonstração. Medido ao vivo 10/09 em http://127.0.0.1:8190 (trilha entrega, credenciais em laco/var/trilha/entrega.credenciais.txt): POST /api/org/oidc com modelo='govbr' cria o provedor e preenche api_base automaticamente ('https://api.staging.acesso.gov.br') — o adaptador do modelo gov.br existe e funciona. tests/medidas/L0-08-c-govbr.json na trilha entrega mostra nivel_ouro_vira_admin=1 caso (tests/api/oidc/test_govbr.py, IdP sintético) e a tela 'Logins' pronta em 51,1 ms (playwright). app/auth/govbr.py e app/auth/oidc.py NÃO existem em wt/lancamento (grep vazio) — o código nunca foi trazido para o ramo que serve a demonstração. Teste real fica pendente de credencial do órgão, como o próprio portão já previa (ver docs/PARIDADE.md na trilha entrega). |
| `L0-08-d-ldap` | 4 | parcial | 2 | 3 | — | G1-l3 consertado (o mais grave): login LDAP provisionava a conta local com o texto cru do cliente; a partir de agora usa o atributo canonico do diretorio (uid/cn/RDN do DN) e plat.ldap_provisionar busca por sujeito_externo (DN) antes do login, entao o mesmo DN atualiza a linha em vez de trancar o login canonico com 409 de indice unico; nome de restricao do banco nao sai mais em rota publica; caminho administrativo novo DELETE /api/usuarios/{id}/vinculo-externo para desfazer vinculo errado. Prova: test_l3_login_cru_nao_vira_identidade_local passa (xfail removido); suite tests/api/ldap -m lento = 17 passed, 3 xfailed. Continuam em aberto, fora do escopo desta trilha: G1-l1 (sem limit_req por IP em /api/login/ldap na borda, e deploy/nginx.conf nao foi tocado), G1-l2 (caminho TLS/StartTLS do LDAP nunca exercitado, exige diretorio de teste com certificado), G1-l4 (o glauth de teste trata a fuga RFC 4515 como curinga, entao o escape nunca e de fato exercitado - dependente do diretorio real). wt/g1fix, handoff laco/handoffs/T3/G1-CONSERTO-identidade.md |

### L1 imagens (66 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L1-01-a-pgstac-e-stac-api-por-inquilino` | 1 | entregue | 4 | 9 | L0-02-tenant-auth | — |
| `L1-01-b-validacao-e-isolamento-da-entrada` | 1 | parcial | 4 | 8 | L0-05-jobs | Conferencia do VRT percorre a arvore do XML (SourceDataset/VRTWarpedDataset, ../, /vsi, atributo) e ambiente do filho por lista de permissao; 10 casos de refutacao e os 3 xfail do 2o adversario passam |
| `L1-01-c-conversao-cog-perfis-miniatura-estatisticas` | 1 | pendente | 1 | fable | L1-01-b-validacao-e-isolamento-da-entrada | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L1-01-d-garage-por-inquilino` | 1 | entregue | 6 | 9 | L0-02-tenant-auth | — |
| `L1-01-ingest-raster` | 1 | entregue | 2 | 9 | L0-05-jobs | — |
| `L1-02-a-servico-titiler-por-inquilino` | 1 | pendente | 1 | fable | — | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L1-02-b-token-de-servico-com-escopo-por-lista` | 1 | refutado | 2 | 9 | L0-02-tenant-auth, L1-02-a-servico-titiler-por-inquilino | adversario T9 L1-1: item nao-UUID nao pode ser escopado por lista; xfail test_advl1_isolamento_href.py |
| `L1-02-c-wmts-xyz-tilejson-validados` | 1 | pendente | 0 |  | L1-02-b-token-de-servico-com-escopo-por-lista | — |
| `L1-02-d-cache-nginx-cdn-e-bancada-de-carga` | 1 | refutado | 1 | 9 | L1-02-c-wmts-xyz-tilejson-validados | adversario T9 L1-2: carga.frio_1_conexao.passou=false ja commitado; bancada so 16 conexoes; sem pagina de status de cache; xfail test_l1_adv2_cache_gate.py |
| `L1-02-f-predefinicoes-de-renderizacao-e-legenda` | 1 | refutado | 1 | 9 | L1-02-a-servico-titiler-por-inquilino, L1-12-linguagem-de-expressao-de-banda | adversario T9 L1-2: colormap explicito por intervalo/valor ausente do esquema; prova de pixel de referencia so em prosa; xfail test_l1_adv2_predefinicoes_gate.py |
| `L1-02-tiles-token` | 1 | refutado | 2 | 8 | L0-02-tenant-auth | artefato ausente em master (auditoria HARD-03 07/09): sem rota de tiles raster por token; martin/titiler não servido em app |
| `L1-03-a-quadro-de-conectores-e-tela-sensores` | 1 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas, L0-05-jobs | — |
| `L1-03-b-sentinel-2` | 1 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores | — |
| `L1-07-mosaico-por-colecao-e-pegadas` | 1 | refutado | 3 | 9 | L1-02-b-token-de-servico-com-escopo-por-lista | adversario T9 L1-2: medicao com cenas sinteticas onde o portao exige Sentinel-2 aberto; nome de arquivo de medidas errado; xfail test_l1_adv2_l107_gate.py |
| `L1-12-linguagem-de-expressao-de-banda` | 1 | pendente | 0 |  | L1-02-a-servico-titiler-por-inquilino | — |
| `L1-01-e-upload-grande-retomavel` | 2 | pendente | 1 | fable | L0-05-jobs | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L1-01-f-formatos-de-entrada` | 2 | parcial | 2 | 8 | L1-01-b-validacao-e-isolamento-da-entrada | tabela única de formatos testada ponta a ponta: 12 aceitos viram COG válido (22 testes contra o job real, Garage e pgstac), ECW/MrSID recusam com a mensagem, zip de 4 cenas vira 1 COG mosaicado, CRS diferentes recusam dizendo quais, tela lê a mesma tabela; 4 achados de produto consertados (savepoint do extents, cadeado ENVI via VRT, chave canônica do upload, migração do evento imagens/ingestar) |
| `L1-01-g-raster-categorico-colormap-e-tabela-de-atributos` | 2 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas | — |
| `L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo` | 2 | parcial | 2 | 8 | — | Ciclo de vida completo no ramo: excluir sai do STAC na hora (tile 404 em 0,016 s) e guarda corpo STAC na lixeira de 7 dias, restaurar devolve tudo dentro e recusa 409 fora, expurgo pelo destruidor do catálogo, gc que lista e não apaga (plat raster gc + periódico), nginx nega excluído por 403, cota recalculada pelo Garage; suíte 7/7, imagens 29, rls/unit 62, catálogo 93 verdes |
| `L1-01-j-proveniencia-da-imagem-lastro` | 2 | entregue | 2 | 9 | L1-01-c-conversao-cog-perfis-miniatura-estatisticas | — |
| `L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro` | 2 | refutado | 1 | 9 | L1-02-b-token-de-servico-com-escopo-por-lista | adversario T9 L1-2: docs/PRO_CONEXAO.md ausente; endpoint S3 por inquilino (Porta 2) nunca construido; xfail test_l1_adv2_cog_s3_gate.py |
| `L1-02-g-wms-1-3-0-raster` | 2 | refutado | 1 | 9 | L1-02-f-predefinicoes-de-renderizacao-e-legenda | adversario T9 L1-2: GetFeatureInfo nao implementado; so 2 de 4 CRS (falta EPSG:4674/UTM SIRGAS); xfail test_l1_adv2_wms_gate.py |
| `L1-02-h-ponto-estatisticas-e-histograma` | 2 | pendente | 0 |  | L1-02-a-servico-titiler-por-inquilino | — |
| `L1-03-c-sentinel-1-sar` | 2 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores | — |
| `L1-03-conectores-sensores` | 2 | pendente | 0 |  | — | — |
| `L1-03-d-landsat` | 2 | pendente | 0 |  | L1-03-b-sentinel-2 | — |
| `L1-03-e-mapbiomas` | 2 | pendente | 0 |  | L1-01-g-raster-categorico-colormap-e-tabela-de-atributos, L1-03-a-quadro-de-conectores-e-tela-sensores | — |
| `L1-03-f-cog-globais-por-vsicurl` | 2 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores, L1-01-g-raster-categorico-colormap-e-tabela-de-atributos | — |
| `L1-03-k-planetary-computer-e-stac-de-terceiros` | 2 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores, L1-03-l-item-referenciado-sem-copia | — |
| `L1-03-l-item-referenciado-sem-copia` | 2 | pendente | 0 |  | L1-02-a-servico-titiler-por-inquilino | — |
| `L1-04-c-grafico-de-indice-por-poligono` | 2 | pendente | 0 |  | L1-03-b-sentinel-2, L1-09-mascara-de-nuvem | — |
| `L1-05-a-registro-de-modelo-e-proveniencia` | 2 | pendente | 0 |  | — | — |
| `L1-05-b-trabalhador-gpu-remoto` | 2 | pendente | 0 |  | L0-05-jobs, L1-05-a-registro-de-modelo-e-proveniencia | — |
| `L1-08-regras-de-mosaico-e-selecao-de-pixel` | 2 | refutado | 1 | 9 | L1-07-mosaico-por-colecao-e-pegadas, L1-09-mascara-de-nuvem | adversario T9 L1-2: regra mais recente sem nuvem nunca implementada; CRS misto sem teste; PARIDADE.md desatualizado; xfail test_l1_adv2_mosaico_gate.py |
| `L1-09-mascara-de-nuvem` | 2 | pendente | 0 |  | L1-03-b-sentinel-2 | — |
| `L1-13-cadeia-de-funcoes-raster-ao-vivo` | 2 | pendente | 0 |  | L1-02-f-predefinicoes-de-renderizacao-e-legenda, L1-12-linguagem-de-expressao-de-banda | — |
| `L1-14-analise-raster-em-lote-gera-item-novo` | 2 | pendente | 0 |  | L1-13-cadeia-de-funcoes-raster-ao-vivo, L0-05-jobs | — |
| `L1-15-estatistica-zonal` | 2 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo | — |
| `L1-16-derivados-de-terreno-e-terrain-rgb` | 2 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo, L1-03-f-cog-globais-por-vsicurl | — |
| `L1-20-exportacao-recorte-e-massa` | 2 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo, L1-02-b-token-de-servico-com-escopo-por-lista, L0-06-backup-status | — |
| `L1-23-cota-e-medicao-por-tb` | 2 | pendente | 0 |  | L1-02-b-token-de-servico-com-escopo-por-lista, L7-09-medicao-cobranca | — |
| `L1-25-servico-de-imagem-esri-compativel` | 2 | refutado | 1 | 9 | L1-02-f-predefinicoes-de-renderizacao-e-legenda, L1-02-h-ponto-estatisticas-e-histograma, L1-07-mosaico-por-colecao-e-pegadas | adversario T9 L1-2: exportImage recusa TIFF; mosaicRule recusado incondicionalmente; xfail test_l1_adv2_imageserver_gate.py |
| `L1-27-ficha-de-metadado-e-licenca-da-imagem` | 2 | pendente | 1 | fable | L0-09-metadado-catalogo | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L1-29-teste-no-arcgis-real-do-parceiro` | 2 | pendente | 0 |  | L1-02-c-wmts-xyz-tilejson-validados, L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro | D20: credencial/tempo do parceiro no ArcGIS Pro/AGOL |
| `L1-30-paridade-image-server-documento-vivo` | 2 | pendente | 0 |  | L1-02-c-wmts-xyz-tilejson-validados | — |
| `UX-32-imagens-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `L1-01-h-ingestao-em-lote-por-manifesto-e-cli` | 3 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas, L1-01-e-upload-grande-retomavel | — |
| `L1-02-i-ogc-api-tiles-e-maps` | 3 | refutado | 2 | 9 | L1-02-c-wmts-xyz-tilejson-validados | adversario T9 L1-2: ENTREGUE contradiz o veredito PARCIAL da propria evidencia; sem prova via driver GDAL OGCAPI; xfail test_l1_adv2_ogc_tiles_gate.py |
| `L1-03-h-clima-nasa-power-e-copernicus-cds` | 3 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores, L1-19-multidimensional-netcdf-zarr | — |
| `L1-03-n-comerciais-com-chave-do-cliente` | 3 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores, L1-01-e-upload-grande-retomavel | chave de teste de fornecedor comercial = decisão do dono; até lá o item fecha só a parte 'sem chave' |
| `L1-03-p-drone-ortomosaico-e-fotos-brutas` | 3 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas, L1-05-b-trabalhador-gpu-remoto | — |
| `L1-03-q-lidar-copc-mdt-mds` | 3 | pendente | 0 |  | L1-16-derivados-de-terreno-e-terrain-rgb | — |
| `L1-04-a-controle-de-tempo-cortina-e-lado-a-lado` | 3 | pendente | 0 |  | L1-07-mosaico-por-colecao-e-pegadas | — |
| `L1-04-e-diferenca-entre-datas-e-tendencia` | 3 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo, L1-09-mascara-de-nuvem | — |
| `L1-04-serie-temporal` | 3 | pendente | 0 |  | L1-02-tiles-token, L1-03-conectores-sensores | — |
| `L1-05-c-mudanca-s2-calibrada` | 3 | pendente | 0 |  | L1-05-b-trabalhador-gpu-remoto, L1-04-e-diferenca-entre-datas-e-tendencia, L1-09-mascara-de-nuvem | — |
| `L1-06-rasters-do-acervo-em-cog` | 3 | pendente | 0 |  | L1-01-h-ingestao-em-lote-por-manifesto-e-cli, L1-01-g-raster-categorico-colormap-e-tabela-de-atributos | — |
| `L1-10-camada-congelada-pmtiles` | 3 | pendente | 0 |  | L1-02-f-predefinicoes-de-renderizacao-e-legenda, L0-05-jobs | — |
| `L1-21-wcs-2-0-1` | 3 | pendente | 0 |  | L1-20-exportacao-recorte-e-massa, L1-02-g-wms-1-3-0-raster | — |
| `L1-24-imagens-orientadas` | 3 | pendente | 1 | plataforma-48 | L2-03-edicao | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L1-05-d-camadas-leves-edificacoes-e-vegetacao-em-faixa` | 4 | pendente | 0 |  | L1-05-b-trabalhador-gpu-remoto, L1-03-f-cog-globais-por-vsicurl | — |
| `L1-05-e-pacote-de-modelo-importavel` | 4 | pendente | 0 |  | L1-05-a-registro-de-modelo-e-proveniencia, L1-05-b-trabalhador-gpu-remoto | — |
| `L1-05-ia-na-entrada` | 4 | pendente | 0 |  | L1-03-conectores-sensores, L0-05-jobs | — |
| `L1-19-multidimensional-netcdf-zarr` | 4 | pendente | 0 |  | L1-01-f-formatos-de-entrada, L1-04-c-grafico-de-indice-por-poligono | — |
| `L1-05-f-amostras-e-rotulos-para-treino` | 5 | pendente | 0 |  | L1-05-e-pacote-de-modelo-importavel, L2-03-edicao | — |
| `L1-18-pansharpening-e-ortorretificacao-rpc` | 5 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo, L1-03-f-cog-globais-por-vsicurl | — |

### L2 plataforma (126 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L2-01-a-documento-mapa` | 1 | entregue | 1 | 3 | L0-04-c-tabela-camada, L0-12-contrato-api-e-limites | — |
| `L2-01-b-martin-tiles-vetoriais` | 1 | parcial | 1 | 3 | L2-04-a-leitor-rls-martin, L0-04-c-tabela-camada | Martin real (v1.15.0) rodando com generalização por zoom + corte de 10.000 (herdado); nova verificação de token FORA do Martin (martin-core devolve 500 para tudo, nunca 401) via /internal/tiles/verificar, com item_da_tabela fechando achado real do adversario (token amplo de outro inquilino autenticava por item alegado). Medido: latencia z8 100k passou (41,8/4,3 ms); censo real=472.780 (nao 1mi) via PMTiles z4-z14 0 erros mas 1/110 tiles 1,3% acima de 1MB; RLS cruzada/revogacao/cache por versao passaram; 200 paralelos z0 passou na fonte PMTiles (RAM 38MB) e REFUTADO na funcao ao vivo (fora do desenho, documentado). Fora: ST_Subdivide, unidade systemd real, gate de token na fonte PMTiles, QGIS nao aberto (sem GUI). |
| `L2-01-c-lista-camadas-legenda` | 1 | parcial | 1 | 5 | L2-01-b-martin-tiles-vetoriais | Arvore de camadas e legenda dinamica (proporcional/calor/raster) construidas e provadas por unidade (12+14 testes verdes); e2e de navegador (arrasto/teclado, opacidade, fora-de-escala, styledata, captura, refutacao 60 camadas) nao executado nesta retomada, ver handoff e medidas. |
| `L2-01-d-popup-runtime` | 1 | refutado | 2 | 8 | L2-04-c-featureserver-query | artefato ausente em master (auditoria HARD-03 07/09): 0 ocorrência de popup em web/js/mapa/mapa.js; sem rota de popup |
| `L2-01-e-mapas-base` | 1 | parcial | 1 | 7 | L2-01-b-martin-tiles-vetoriais, L0-11-arquivos-objetos | Galeria de mapas base entregue e provada por API/unidade: 4 fontes abertas como item de catalogo (tipo mapa_base, JSON Schema na migracao), instalacao idempotente, um so padrao por inquilino, proxy OSM com cache (MISS 30,2 ms / HIT 0,05 ms contra o upstream real) e SEM parametro de host — tentativa de proxy aberto devolve o mesmo ladrilho, sha256 identico. Disco medido em tests/medidas/L2-01-e.json (124.039.134 bytes de pior caso contra teto interino 154.857.600; D27 do dono segue ABERTA, nao ha teto dele). Licenca das 4 fontes em docs/DADO_DEMO.md. PENDENTE: todas as clausulas de e2e com captura (galeria, preservacao de camada/extensao na troca, Range 206, atribuicao na impressao) — a base por trilha nao tem nginx e PLAT_URL_PUBLICA e invalida por desenho; tests/e2e/test_mapas_base.py esta escrito e salta. L2-12 (layout de impressao) ainda pendente no laco. |
| `L2-01-g-tabela-atributos` | 1 | parcial | 1 | 8 | L2-04-c-featureserver-query, L2-01-h-selecao-filtros | Tabela de atributos completa no servidor e no mapa: paginacao 50/200/1000, ordenacao, busca unaccent, filtro de extensao, selecao nos dois sentidos, colunas/alias/oculta/largura por usuario, estatisticas no banco, dominio na coluna. Medido em 1 mi de linhas com carga 10,7: primeira pagina p95 275,9 ms e ordenar por coluna indexada p95 15,2 ms. Pendente: e2e de tela pulado (a URL da trilha nao resolve nesta maquina) e captura junto com ele; edicao em linha (L2-03) e exportar (L2-01-n) sao itens proprios. |
| `L2-01-h-selecao-filtros` | 1 | parcial | 1 | 5 | L2-04-c-featureserver-query | Backend completo e verde: CQL2, /valores /filtrar /selecionar /selecao-espacial, migracao do tipo 'selecao', bancada propria, 14 testes de API + 17 unitarios batendo contra Postgres real (poligono==ST_Intersects, CQL2 3 clausulas+OR aninhado, data com fuso, distancia==ST_DWithin, 422 em campo/operador invalido) e refutacao (funcao proibida/200 clausulas/tipo errado/SQL bruto/10 aleatorias vs PostGIS), tudo 422 nunca 500. Corrigido de quebra: 2 hashes truncados em web/vendor/VERSOES.txt que make vendor nao testava. Pendente nomeado: front-end inteiro (terra-draw wiring, construtor de filtro visual, estado na URL) nao existe nesta trilha -- clausulas 'URL reabre em outra sessao' e 'captura de cada modo' ficam sem prova. |
| `L2-01-mapa-web` | 1 | entregue | 1 | 3 | L0-04-ingest-vetor, L0-14-identidade-visual | — |
| `L2-02-a-modelo-estilo` | 1 | parcial | 1 | 5 | — | Modelo de estilo (plat_construtor + maplibre) construído e testado: JSON Schema publicado, validador oficial da Style Spec (422 com a mensagem), compilador único para os 7 tipos, servidor sempre recompila o maplibre canônico na gravação (ida-e-volta sem perda provada), 6/7 exemplos renderizam de ponta a ponta no MapLibre via e2e com captura por tipo (raster fora, sem tile na bancada), bateria de refutação recusada em 422 (campo inexistente, 300 layers, sprite externo, faixa invertida, categoria duplicada, inquilino cruzado). PARCIAL em 2 cláusulas nomeadas: (1) estilo padrão da ingestão -- a função determinística (app/estilos/padrao.py) está pronta e testada, mas não foi ligada ao INSERT de app/ingestao/carregar.py (integração com L0-04-c fica para quem tocar aquele item); (2) SLD -- cores provadas iguais por leitura do XML, mas 'abre no QGIS' não foi medido porque qgis_process não está instalado nesta máquina. Adversário: os 4 vetores da coluna refutacao foram testados pelo próprio construtor (não por um papel adversário independente em contexto isolado); recomenda-se confirmação independente antes de tratar como P8 fechado. |
| `L2-02-b-classificacao-servidor` | 1 | parcial | 3 | 8 | L2-04-c-featureserver-query | reentrega por junção: master 61089697 + merge wt/cx202c (bdb104d7); portão de classificação verde na árvore junta (quantil/intervalo/Jenks = numpy, nulos, repetidos, 1 mi, cache, data, texto recusado); 6 concertos de junção (openapi/LIMITES regenerados, contagem de location sem comentário, regra 3 do vendor p/ LICENSE.txt, origem https, imports); sha 49e1c4ef |
| `L2-02-c-editor-simbologia-vetor` | 1 | parcial | 2 | 8 | L2-02-a-modelo-estilo, L2-02-b-classificacao-servidor, L2-02-e-simbolos-sprites-glifos | reentrega por junção: o ramo wt/il202bclas (master 61089697 + merge wt/cx202c bdb104d7) carrega o editor de simbologia (web/js/mapa/estilo_editor.js, POST /api/estilos/compilar) e ColorBrewer 1.7.0 no vendor com licença em arquivo ao lado das rampas (regra 3 estendida); test_estilos_editor + test_simbologia_* verdes; handoff T8/L2-02-b; sha 49e1c4ef |
| `L2-02-d-rotulos` | 1 | parcial | 2 | 6 | L2-02-a-modelo-estilo, L2-10-c-linguagem-expressao | Todas as clausulas do portao provadas com e2e real (MapLibre+Martin reais): campo, expressao com formatacao (servidor), 2 classes com filtro, linha ao_longo (z14), prioridade+colisao (achado: MapLibre decide por ORDEM dos layers, nao so symbol-sort-key - _rotulos_layers corrigido e documentado no ADR), faixa de escala (minzoom/maxzoom nativos), glifos do Martin com cache (14,6ms->1,1ms). Identidade dois-modos (compilado x servidor) provada texto-a-texto em 100 feicoes. Refutacao de seguranca do texto (divisao por zero/campo nulo/ausente/2000 chars nunca 'null'/'NaN'/'undefined') PASSA. PARCIAL, 1 clausula nomeada: a refutacao tambem pede 'medir tempo de tile com rotulo calculado no servidor em camada de 1 mi de feicoes' - NAO MEDIDO, porque a funcao de tile real do Martin com coluna calculada em SQL pertence ao pipeline de ingestao (item L2-04, contrato de funcao de tile em L2-04-a/wt-stac, ainda nao juntado); aqui so o CONTRATO Python (nome de coluna, calculo, texto seguro) foi provado, nao a latencia de tile em escala de producao. Fora tambem, nomeado: compilacao da expressao p/ SQL; posicao_poligono sem controle nativo distinto no MapLibre (motor sempre ancora dentro do poligono); glifario definitivo com licenca documentada e o item L2-02-e (usei Martin real + fontes abertas so p/ provar o mecanismo). |
| `L2-02-simbologia` | 1 | pendente | 2 | 8 | — | item-pai (agregador) — o editor está com o líder 1 em L2-02-c; devolvido |
| `L2-03-a-api-edicao-transacional` | 1 | parcial | 3 | 8 | L0-04-c-tabela-camada, L0-10-eventos-historico, L0-12-contrato-api-e-limites | reentrega por juncao do wt/cx203f sobre master atual (causa da refutacao era artefato ausente em master): porta unica de escrita com transacao, versao otimista 409, dominios/validacao no servidor e RLS; portao 20/20 e os 6 ataques da refutacao verdes na arvore junta (cruzado/eventos/docs 232, adversario+unit verde, lote 9 com worker da trilha, lint ok); e2e do L2-03-edicao nao rodado nesta passagem |
| `L2-03-b-ferramentas-geometria` | 1 | entregue | 3 | 9 | L2-03-a-api-edicao-transacional, L2-01-h-selecao-filtros | — |
| `L2-03-c-formulario-atributos-runtime` | 1 | parcial | 1 | 5 | L2-03-a-api-edicao-transacional, L2-10-a-dominios-subtipos | Formulario de atributos derivado do esquema da camada entregue dentro de web/js/mapa/edicao.js (dominio/obrigatorio espelhados no navegador, reconferidos no servidor). Fora desta rodada: motor de formulario RUNTIME completo (grupos recolhiveis, visibilidade condicional, calculo por expressao L2-10-c, GUID, subtipo trocando dominio) e o documento de formulario do L5-03 (construtor arrasta-e-solta) - dependem de L2-10-a/c ainda nao integrados a esta arvore. |
| `L2-03-edicao` | 1 | refutado | 2 | 8 | L0-02-tenant-auth | artefato ausente em master (auditoria HARD-03 07/09): sem rota edicoes/applyEdits nem tabela de feição editável em master |
| `L2-04-a-leitor-rls-martin` | 1 | parcial | 1 | 3 | L0-04-c-tabela-camada | 16 testes verdes em 3 execucoes (tests/api/test_leitor_tiles.py, base propria plat_tt204a): sem token 0 linhas e tile levanta token_ausente; com token so o proprio inquilino (3 linhas em demo, 0 em demo2 na mesma transacao); token revogado para de valer em 0,002 s; 1 linha de log por chamada aceita; varredura cruzada A->B em todas as camadas do catalogo = 6 chamadas, 0 tile com dado; set_config forjado pelo proprio leitor = 0 linhas (politica do leitor exige prova assinada, nao a GUC crua); restricao de Referer/IP provada. PARCIAL por 2 fronteiras: (1) a clausula do install.sh foi provada no passo que ele chama (db/leitor_instalar.sh, 2a execucao = 'mudancas: 0'), nao no install.sh inteiro, que reescreveria .env e migracoes da instalacao; (2) tests/api/ingestao nao roda nesta trilha (sem worker no canal, jobs ficam pendentes), entao a linha nova do carregar.py so esta provada pelo caminho equivalente do fixture. Handoff: laco/handoffs/T3/L2-04-a-leitor-rls-martin.md |
| `L2-04-b-featureserver-catalogo-metadados` | 1 | parcial | 1 | 7 | L2-04-a-leitor-rls-martin, L2-10-a-dominios-subtipos, L2-10-b-relacionamentos | Diretorio Esri por token em /svc/{token}/rest (info, generateToken teto 24 h, services com pastas, FeatureServer, /{id}, /layers, /info/itemInfo, /info/metadata ISO 19139), f=json|pjson|html + JSONP, CORS so em /svc//ogc//tiles, drawingInfo simple/uniqueValue/classBreaks do estilo MapLibre; 51 testes verdes, isolamento entre inquilinos medido. PENDENTE: captura no QGIS e cliente Python arcgis (sem ambiente grafico e biblioteca fora da venv); dominio/subtipo/relacionamento saem vazios porque L2-10-a/b nao estao nesta base. O ramo carrega tambem wt/esriogc (item-pai), sem o qual o item nao existe. |
| `L2-04-b-parser-where-ast` | 1 | entregue | 0 |  | — | — |
| `L2-04-c-featureserver-query` | 1 | parcial | 1 | 3 | L2-04-b-featureserver-catalogo-metadados | 39/45 parametros com pedido real (portao pede >=38), PBF oficial Esri decodificado igual ao JSON, ataques de where sempre 4xx, p95=1,6ms em 8,4mi CARs reais (GIST); pendente: QGIS 100mi linhas nao verificado (sem ambiente grafico), adversario independente ainda nao rodado. Ramo wt/fsquery, handoff em laco/handoffs/T4/L2-04-c-featureserver-query/ |
| `L2-04-d-featureserver-edicao-anexos` | 1 | parcial | 1 | 8 | L2-04-c-featureserver-query, L2-03-a-api-edicao-transacional, L2-03-e-anexos | applyEdits (camada e servico), add/update/deleteFeatures, calculate, 6 rotas de anexo e uploads/upload sobre a porta unica do L2-03-a; 26 testes passando; nao feitas e nomeadas: QGIS (nao instalado, sem ambiente grafico) e prova com o cliente Python arcgis (pacote nao instalado) |
| `L2-04-g-ogc-api-features-crs-cql2` | 1 | parcial | 2 | 5 | L2-04-a-leitor-rls-martin, L2-03-a-api-edicao-transacional | CRS+CQL2 sobre Part 1; 53 testes verdes na trilha g204 (relato do agente); veredito clausula a clausula NAO registrado (agente morreu por limitacao do servidor) -> parcial ate percorrer o portao |
| `L2-04-j-conformidade-clientes-e-paridade` | 1 | parcial | 2 | 8 | L2-04-c-featureserver-query, L2-04-d-featureserver-edicao-anexos, L2-04-g-ogc-api-features-crs-cql2 | Matriz viva de 102 linhas gerada por make conformidade (81 suportadas, 5 parciais, 12 fora, 4 nao medidas, 0 refutadas), com data, versao do repositorio e prova nomeada por linha; secao do PARIDADE.md gerada do JSON e conferida por teste; owslib WFS medido contra uvicorn proprio; protocolo do parceiro Pro/AGOL escrito e pendente. NAO medido: QGIS em conteiner, cliente Python arcgis e teamengine (ausentes da maquina, imagem/pacote fora do orcamento de disco) - ficam nao_medido na matriz, nunca suportado. Consertou de passagem 2 quebras de integracao (estilo do catalogo nao virava drawingInfo; tile vetorial 422 por colisao de rota em /tiles/) e 2 trechos de sintaxe invalida que o git juntou sem marcar conflito em tests/api/cruzado_casos.py. |
| `L2-04-servicos-esri-ogc` | 1 | parcial | 1 | 5 | L2-03-edicao, L0-02-tenant-auth | Diretório/metadados do FeatureServer + OGC API Features Part 1 + WFS 2.0 construídos em volta da query do L2-04-c (reuso total, zero reescrita). 13/13 ataques recusados com 400/404 (nunca 500); 2 bugs reais achados e corrigidos (item_id sem validar UUID = 500 real inclusive na /query original; landing OGC Features vazava 200 pra outro inquilino). Fora: applyEdits/anexos/relacionamentos (dependência L2-03-edicao/L2-10-b não satisfeita, bloqueio real); QGIS/Pro/AGOL reais não verificado (sem ambiente); OGC Features sem validador formal instalado. Ver laco/handoffs/T4/L2-04-servicos-esri-ogc/99_veredito.md |
| `L2-05-a-catalogo-ferramentas-gpserver` | 1 | parcial | 1 | 8 | L0-05-a-fila-postgres, L2-01-h-selecao-filtros | registro @ferramenta validado no make check, buffer por API própria/GPServer execute/submitJob com o mesmo sha256, proveniência conferível + derivado_de visível na ficha (e2e com captura), rerodar reproduz, cancelamento sem órfã, outro inquilino 404; Pro real pendente (D20); wt/cx205 na fila |
| `L2-05-b-vetor-basico` | 1 | parcial | 1 | 8 | L2-05-a-catalogo-ferramentas-gpserver | 19 ferramentas vetoriais no registro do L2-05-a, cada uma conferida contra shapely/pyproj.Geod na mesma entrada (29 testes verdes); buffer geodesico de 1 km em -23 a 5,0e-5 da referencia pyproj (portao aceita 5e-4); regra da casa ST_MakeValid+ST_ReducePrecision com relatorio de invalidas na procedencia; volume medido a 1.156 poligonos por camada, nao a 100 mil (disco 93 %, carga 8,7) e e2e nao rodado |
| `L2-05-c-sobreposicao-agregacao` | 1 | parcial | 2 | 8 | L2-05-b-vetor-basico | 9 ferramentas de relacao (juncao espacial e por atributo, resumir dentro/perto, agregar pontos em poligono ou grade quadrada/hexagonal no UTM local, contar dentro, enriquecer por proporcao de area, vizinho mais proximo, tabela de distancias) no registro do L2-05-a; 26 testes contra geopandas/pandas/shapely/pyproj; contagem dupla e ponto na fronteira declarados no metodo e evitaveis por atribuicao=exclusivo; jobs/tipos.py passou a registrar vetor e relacao (acima do custo sincrono elas eram recusadas). Nao medido: e2e (uvicorn solto nao serve /static; o e2e do L2-05-a falha na mesma linha) e a escala de 1 mi de pontos em 5.570 municipios (disco 93 %, carga 10, teto de 5 mil feicoes) |
| `L2-06-e-estatisticas-servidor` | 1 | parcial | 2 | 8 | L2-04-c-featureserver-query | clausula de desempenho fechada: 1 mi de linhas x 100 categorias p95 = 113 ms (<= 500 ms), medido com a maquina livre (carga 1,56-2,12) no ramo wt/il206eestat; as 6 clausulas do portao passam — falta so a fila juntar em master |
| `L2-10-a-dominios-subtipos` | 1 | refutado | 4 | 8 | L0-04-c-tabela-camada, L0-12-contrato-api-e-limites | artefato ausente em master (auditoria HARD-03 07/09): 0 plat.dominio em master |
| `L2-10-c-linguagem-expressao` | 1 | parcial | 4 | 3 | L0-12-contrato-api-e-limites | 3 refutações consertadas: convenção fixada nos dois lados (resto com sinal do dividendo, texto em ponto de código, Numero só ASCII, data com floor) + 30 vetores de convergência; decimal capturado; tabela de paridade honesta caiu de 29 para 11 'feito' (o conserto achou mais 12 linhas falsas além das 6 do adversário) com trava que reprova linha sem vetor; 1.652 testes passam. Falta: permissão de camada de outro inquilino (não há camada), Trim ainda delega à língua, Proxy não detectável no navegador |
| `UX-00-mapa-de-cobertura-da-interface` | 1 | refutado | 3 | 9 | — | adversario T9 (L2-3): docs/gerar_cobertura_ui.py conta URL em comentario JS como coberta — enfraquece a prova de UX-10..21/UX-23; xfail test_ux00_cobertura_ignora_codigo_morto.py |
| `UX-01-sistema-de-design` | 1 | parcial | 1 | 8 | — | tokens únicos em duas camadas + 4 componentes base novos + /estilo-guia + guarda de literal (0 fora de tokens.css) + axe 0 sérias nos dois temas + capturas 20 telas 1280/390 antes/depois |
| `UX-02-telas-entrada-conta-convite` | 1 | parcial | 1 | 8 | — | entrada/2FA/conta/convite/redefinição com erro por campo, estados nomeados, ocupado, Caps Lock; en+es completos (995 chaves, paridade testada); e2e fluxo inteiro 360/1280 + axe 0 sérias |
| `UX-03-tela-conteudo-item-lixeira` | 1 | parcial | 1 | 8 | — | estados explícitos na lista e no painel; arrastar-e-soltar cria item (caminho de upload consertado: token + arquivo_id); seleção sobrevive a reordenar/filtrar; p95 render 1.000 itens 57,7 ms (carga 11,3) |
| `UX-04-tela-mapa-polimento` | 1 | parcial | 1 | 8 | — | ramos de painel juntados por 3 vias; chrome único (trilho + gaveta plat-painel + tabela ancorada), atalhos, tela cheia, impressão, 390 px, base escura; e2e 1280/390 + axe; 4 consertos achados na junção |
| `UX-09-telas-ferramentas-e-tarefas` | 1 | parcial | 2 | 9 | — | MEDIDO 10/09 contra wt/lancamento (não contra ramo isolado): o trabalho existe e passa nos próprios testes, mas NENHUM commit da trilha UX está mesclado em wt/lancamento — `git merge-base --is-ancestor wt/cx3ux11 HEAD` = NOT merged (era a suposição a testar, e caiu: não é 'quase pronto', é 'nunca chegou'). wt/cx3ux11 (392 commits, 316 arquivos, 37.411 inserções) acumula UX-00,01-11,13,17,18,19,21,23 com docs/COBERTURA_UI.md real (240 rotas, 200 cobertas, 11 lacunas de escrita restantes fora deste lote) e e2e por item (test_ux06_admin.py, test_ux09_ferramentas.py, test_ux11_17_18_arquivos_ldap_plataforma.py, test_ux23_selecao_anotacoes_pacote.py etc.). BLOQUEIO REAL: o merge reescreve web/js/base/dom.js (+6/-x), web/js/camadas.js (+508), web/js/i18n/pt-BR.json (+2650/-769), web/js/mapa/atributos.js (+271) — os 4 arquivos que a regra da casa proíbe tocar porque outro agente edita AGORA (diff sujo confirmado: 217 linhas em 7 arquivos incl. esses 4, sig.js, sig.html, sig.css). Não é falta de trabalho, é ordem de chegada: precisa de um turno dedicado de merge (>1h, 316 arquivos) DEPOIS que os arquivos web/js/sig/*, camadas.js, dom.js e i18n/pt-BR.json ficarem livres. Específico: o próprio e2e (tests/e2e/test_ux09_ferramentas.py, dentro de wt/cx3ux11) documenta no docstring que a ferramenta GP Esri buffer (L2-05-a) 'não existe em ramo nenhum' — confirmado hoje (`git log --all --grep L2-05-a` só acha o item L2-05-a-catalogo-ferramentas-gpserver com buffer geodésico registrado no worker de jobs, sem vocabulário GP/Esri e sem ligação à tela). Então mesmo depois do merge, o portão exato ('e2e roda buffer numa camada e vê o resultado no mapa') fica parcial: a tela /ferramentas cobre o catálogo genérico de tarefas, não o buffer GP. |
| `L2-01-f-navegacao-medicao-coordenadas` | 2 | parcial | 2 | 8 | L2-17-crs-transformacoes | medição no elipsoide ≤ 0,1 % vs PostGIS (5 segmentos, 3 polígonos), coordenada em 31982 ≤ 1 cm, ir para 3 formas, favorito ± 1 px, e2e com 9 capturas e 0 erro de console; favoritos em localStorage (documento do mapa = L2-01-a na fila); ramo wt/cx201f = master + wt/l201mapa |
| `L2-01-i-graficos-de-camada` | 2 | parcial | 2 | 8 | L2-01-h-selecao-filtros | 5 gráficos por camada agregados no servidor (POST /api/camadas/{id}/grafico ao lado do L2-06-e): barras == SQL, histograma == numpy (bordas idênticas), regressão == polyfit 1e-6, clique seleciona a mesma contagem no mapa, 1 mi ≤ 168 ms p95 (exigiu tenant_atual() PARALLEL SAFE, migração 20260908T0100), SVG próprio ≤ 40 kB, PNG/CSV, guardado por camada (localStorage até o L2-01-a); 6 e2e com 12 capturas, 31 API, 17 unit |
| `L2-01-j-comparacao-cortina-tempo` | 2 | entregue | 1 | 9 | L2-01-c-lista-camadas-legenda, L1-04-serie-temporal | — |
| `L2-01-k-desenho-anotacoes` | 2 | refutado | 2 | 8 | L2-02-a-modelo-estilo | artefato ausente em master (auditoria HARD-03 07/09): só 1 menção em mapa.js, sem módulo de desenho/anotação |
| `L2-01-l-exportacao-do-mapa` | 2 | refutado | 2 | 8 | L2-01-h-selecao-filtros, L2-02-a-modelo-estilo | artefato ausente em master (auditoria HARD-03 07/09): 0 export em mapa.js; existe export de LISTA do catálogo, não do mapa |
| `L2-02-e-simbolos-sprites-glifos` | 2 | parcial | 4 | 8 | L2-01-b-martin-tiles-vetoriais, L0-11-arquivos-objetos | reentrega por junção: o ramo wt/il202bclas (master 61089697 + merge wt/cx202c bdb104d7) carrega a biblioteca inteira; refutação coberta na árvore junta (bomba de XML, muitos elementos, nome colidindo com ícone padrão, token cruzado de inquilino, ≥150 ícones/9 temas, sprite 1x-2x sem reiniciar, glifos Noto, licença por arquivo, galeria com busca); verde 78+1skip; handoff T8/L2-02-b; sha 49e1c4ef |
| `L2-02-f-estilo-raster` | 2 | refutado | 2 | 8 | L1-02-tiles-token, L2-02-a-modelo-estilo | artefato ausente em master (auditoria HARD-03 07/09): 0 estilo_raster em app |
| `L2-03-d-historico-restauracao` | 2 | refutado | 2 | 8 | L2-03-a-api-edicao-transacional, L0-10-eventos-historico | artefato ausente em master (auditoria HARD-03 07/09): item_versao é histórico de ITEM, não de feição; edição de feição ausente |
| `L2-03-e-anexos` | 2 | refutado | 2 | 8 | L2-03-a-api-edicao-transacional, L0-11-arquivos-objetos | artefato ausente em master (auditoria HARD-03 07/09): sem tabela/rota de anexo de feição em master |
| `L2-03-f-edicao-em-lote-calculo-campo` | 2 | parcial | 2 | 8 | L2-03-a-api-edicao-transacional, L2-10-c-linguagem-expressao, L0-05-a-fila-postgres | POST /api/camadas/{id}/lote: calcular (sql/linha a linha), atribuir, apagar, corrigir, copiar/mover, previa, job >5000 com cancelamento transacional; 100 mil em 16,1 s; painel no mapa; sem reprojetar e sem filtro L2-06-e |
| `L2-04-e-vector-tile-server-tilejson` | 2 | refutado | 2 | 8 | L2-01-b-martin-tiles-vetoriais, L2-02-a-modelo-estilo | artefato ausente em master (auditoria HARD-03 07/09): 0 VectorTileServer/TileJSON; sem rota /svc de tiles vetoriais |
| `L2-04-h-wfs-2-gml` | 2 | parcial | 2 | 8 | L2-04-g-ogc-api-features-crs-cql2 | WFS 2.0.0 e 1.1.0 por token: capabilities validados contra o XSD oficial do OGC em cache, DescribeFeatureType em XSD gerado que valida o proprio GetFeature, filtro FES 2.0 compilado pelo MESMO cql2.compilar, GML 3.2 com gml:id e Multi*, GetPropertyValue, GetFeatureById e Transaction pela porta unica (evento com origem=wfs). GDAL 3.8.4 le o servico vivo (250=banco, -spat 60, -where 50, ogr2ogr GPKG) e relê 1.000 feicoes GML validas; owslib le o capabilities. 57 testes do item verdes. NAO medido: QGIS (nao instalado) e AGOL/Pro (D20). |
| `L2-05-d-grades-densidade-padroes-interpolacao` | 2 | parcial | 2 | 8 | L2-05-c-sobreposicao-agregacao | 8 ferramentas no registro do L2-05-a (tesselacao quadrada/hexagonal/H3, densidade_kernel de pontos e linhas, hot_spot Gi*, centro_medio/elipse, vizinho_mais_proximo_medio, moran_global, interpolacao_idw, contorno); 43 testes verdes (Gi* e Moran contra esda 8,9e-16; area do hexagono contra formula 1e-9; densidade integra N com erro 1,1e-4; IDW identico a implementacao de referencia; isolinhas relidas pelo OGR). PENDENTE: saida raster COG pelo L1-01 (nao esta em master; saida sai como camada de celulas) e captura e2e. Grade de 250 m reproduz a mediana de area da grade interna da casa; contagem difere em 9 celulas-lasca de 73.115. |
| `L2-05-e-raster-basico` | 2 | parcial | 2 | 8 | L2-05-a-catalogo-ferramentas-gpserver, L1-02-tiles-token | 13 ferramentas raster sobre COG lido por janela; zonais reproduzem o rasterstats, declividade e visibilidade iguais byte a byte ao GDAL, NDVI igual ao TiTiler a 1e-6, 827 MB de pico em raster de 9,77 GB; e2e com captura |
| `L2-05-f-rede-isocrona-rota-ferramentas` | 2 | parcial | 2 | 8 | L2-05-a-catalogo-ferramentas-gpserver, L2-11-c-rota-matriz-isocrona | Seis ferramentas de rede no registro do L2-05-a chamando o serviço do L2-11-c; isócrona de 30 min igual à do serviço, matriz 100x100 em 3,96 s, ordem otimizada <= original, K confere com a matriz, atributos de tempo/distância e versão do grafo na procedência, paridade Use proximity escrita; e2e escrito mas não executado (a app não serve /static sem nginx) |
| `L2-05-geoprocessamento` | 2 | pendente | 0 |  | L0-05-jobs | — |
| `L2-06-a-modelo-painel-fontes` | 2 | entregue | 1 | 5 | — | — |
| `L2-06-b-elementos-basicos` | 2 | parcial | 2 | 8 | L2-06-e-estatisticas-servidor, L2-01-i-graficos-de-camada | L2-06-b fechado no ramo: semente do painel com funcao de tile garantida, fixture apaga pela lixeira (item_lixeira), rollback antes do assert na varredura; testes-alvo 53 verdes/8 saltos de bancada (L2-01); falhas da suite inteira sao herdadas da familia jobs/catalogo e o mestre ja as conserta |
| `L2-06-c-acoes-seletores-filtros-cruzados` | 2 | parcial | 2 | 8 | L2-06-b-elementos-basicos | interações do painel prontas e verdes: seletor filtra indicador/gráfico/tabela/mapa com contagem por SQL, barra filtra a lista, extensão muda o indicador, recusa 422 entre fontes sem relação, URL reabre com estado, p95 gatilho-ação 0,054 ms com 10 mil feições |
| `L2-06-d-atualizacao-viva-sse` | 2 | parcial | 3 | 9 | L2-03-a-api-edicao-transacional | MEDIDO 10/09: wt/lancamento tem SSE só para jobs (app/jobs/eventos.py, LISTEN plat_job) — '/api/eventos' existe (401 sem sessão, rota real) mas '/api/eventos/camadas' NÃO existe (404 ao vivo) e não há gatilho pg_notify('plat_camada', ...) em nenhuma migração de wt/lancamento (grep vazio). O trabalho completo (gatilho de camada+versão, fluxo SSE em /api/eventos/camadas, painel que assina e mostra hora da última atualização, e2e de reconexão) existe em wt/il206dsse (5 commits, 43 arquivos, 4.852 inserções) mas NÃO está mesclado (`git merge-base --is-ancestor wt/il206dsse HEAD` → NOT merged) e o diff toca web/js/i18n/pt-BR.json (871 linhas) — um dos arquivos que outro agente edita agora nesta mesma worktree. Merge de 43 arquivos + reteste dos 5 sub-portões (evento cruzado de inquilino, 100 clientes SSE simultâneos com CPU medida, Last-Event-ID, fallback por polling) é >1h e depende do i18n ficar livre. |
| `L2-06-paineis` | 2 | pendente | 0 |  | L0-14-identidade-visual | — |
| `L2-07-a-pwa-instalavel-cache` | 2 | refutado | 2 | 8 | — | artefato ausente em master (auditoria HARD-03 07/09): sem manifest nem service worker em web/ |
| `L2-07-b-formulario-de-coleta-xlsform` | 2 | parcial | 1 | 8 | L2-03-c-formulario-atributos-runtime, L2-10-c-linguagem-expressao | XLSForm importado por pyxform vira item formulario + camadas (filha por repeticao); relevant/constraint/calculation/choice_filter traduzidos por tabela feito/parcial/fora (102 vetores Py=JS); motor JS = motor Python; tela /coleta com cascata, busca, rascunho e envio; e2e Pixel 7 verde em https local; fora do brief: geoponto GPS, foto/EXIF, audio, assinatura, codigo de barras, paridade Survey123/Field Maps por coluna |
| `L2-07-c-fila-sincronizacao-idempotente` | 2 | pendente | 0 |  | L2-07-a-pwa-instalavel-cache, L2-03-a-api-edicao-transacional, L2-13-b-replicas-sincronizacao | — |
| `L2-08-a-leitor-portal-inventario` | 2 | parcial | 4 | 3 | L0-05-a-fila-postgres | 7 achados do adversário consertados (credencial só para a origem do portal, item malformado saneado ou pulado, falha nunca fica 'rodando', fórmula no CSV neutralizada, tamanho negativo nulo, privilégio antes de gravar); 28 testes passam. FALTA a cláusula original: prova contra portal REAL depende da credencial do parceiro (decisão D20) — provado só contra servidor de teste |
| `L2-08-b-clonar-camadas-hospedadas` | 2 | refutado | 2 | 9 | L2-08-a-leitor-portal-inventario, L0-04-c-tabela-camada, L2-10-a-dominios-subtipos, L2-10-b-relacionamentos | adversario L2-2 (T9): clausulas '500 mil feicoes' e '5 camadas' nunca medidas (so 3 camadas/2.000 feicoes); xfail test_l2_adv2_clone_500k.py |
| `L2-08-c-converter-web-map-e-estilo` | 2 | pendente | 1 | cx3 | L2-08-b-clonar-camadas-hospedadas, L2-02-a-modelo-estilo, L2-02-d-rotulos | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L2-08-d-relatorio-migracao-e-exportacao-reversa` | 2 | pendente | 0 |  | L2-08-c-converter-web-map-e-estilo, L5-03-e-xlsform-ida-e-volta-idiomas | — |
| `L2-08-migracao-agol` | 2 | parcial | 0 | 8 | L2-02-simbologia, L0-04-ingest-vetor | Portado do SIG de cliente (SIG de teste interno: pipeline/20_agol_publish.py + rotas /api/integracoes/agol) para o PLAT em 10/09, commits 4cbd4723a/0bad032fb/a3c83ed58 no ramo wt/lancamento: modulo app/agol/ com credencial cifrada POR INQUILINO (plat.tenant.config->'agol', AES-GCM), tarefa de fila agol.publicar com progresso e log, tabela plat.agol_publicacao com RLS, estado por camada, aba na tela do item, migracao 20260910T2015_agol.sql, 10 testes verdes. Caminho de rede provado contra o portal real com credencial invalida (http_403 em ~2 s, estado 'erro', nunca alegou publicacao). FALTA para entregue: credencial de conta AGOL de verdade (decisao D20 do dono) e o item agregado Web Map combinando varias camadas. |
| `L2-10-b-relacionamentos` | 2 | refutado | 2 | 9 | L2-10-a-dominios-subtipos, L2-03-a-api-edicao-transacional | adversario L2-2 (T9): refutacao exigida pelo portao (100 mil relacionados) nunca virou teste; xfail test_l2_adv2_relacionamentos_100k.py |
| `L2-10-d-regras-de-atributo` | 2 | parcial | 2 | 8 | L2-10-c-linguagem-expressao, L2-03-a-api-edicao-transacional, L0-05-a-fila-postgres | regras de atributo por camada (cálculo com gatilho/ordem/encadeamento, restrição com código+mensagem, validação como job camadas.validar com camada de erros, campos virtuais na leitura, excluir_em_massa, habilitar), motor com ciclo detectado na configuração, no caminho único de escrita do L2-03-a (mesclado); 100 mil validadas em 3,45 s com N conferido por SQL; 1.000 edições com 3 regras = 1,11x; sem tela; compilação SQL (L2-10-e) e WFS-T (inexistente em master) pendentes |
| `L2-10-relacoes-regras` | 2 | pendente | 0 |  | L2-03-edicao | — |
| `L2-11-a-geocodificacao-csv` | 2 | parcial | 2 | 8 | L2-11-b-geocodificador-brasil, L0-04-d-formatos-base | cláusula do portão fechada — os 2 testes nomeados passam na trilha (test_1000_enderecos_boa_vista: 95,0% numero_exato a <=50 m contra portão de 85%, 0% fora do município, job de 8,5 s; test_adversario: centroide sempre marcado, pendência real) — causa da falha anterior era dupla: (1) o job repetia a busca trgm da mesma via por linha (45 vias distintas em 1.000 endereços, 30-250 ms de recheck cada) e não terminava em 120 s — fechado com 2 migrações de índice (btree cod_municipio+logradouro_norm e GIN multicoluna com btree_gin) mais cache opcional por job no motor.buscar; (2) o teste lia a camada direto do banco sem declarar inquilino e as políticas de RLS escondiam a linha que ele próprio criou — fechado declarando plat.tenant_id/usuario_id/login como app.db.db faz; suíte inteira do geocodificador verde (44 testes), make lint e sem-marcador verdes; falta decisão da fila de junção |
| `L2-11-b-geocodificador-brasil` | 2 | parcial | 2 | 3 | L0-05-a-fila-postgres, L6-01-a-registro | portao medido: erro mediano 0,0 m / acerto numero-face 98,0% / reverso 100% / sugestao p95 33 ms / instalacao RR 4,52 MB 10,4 s, todos passam; PENDENCIA nomeada = QGIS real como locator (sem QGIS/ambiente grafico nesta maquina, protocolo testado por HTTP direto); Pro/AGOL reais = D20 (nao especifico deste item) |
| `L2-11-c-rota-matriz-isocrona` | 2 | refutado | 2 | 9 | L0-05-a-fila-postgres, L0-11-arquivos-objetos | adversario L2-2 (T9): pgRouting, NAServer, perfis pe/bicicleta, /mais-proximo e /ajuste-de-trajeto ausentes; xfail test_l2_adv2_rede_escopo.py |
| `L2-11-geocodificacao-rota` | 2 | pendente | 0 |  | — | — |
| `L2-12-a-motor-render-servidor` | 2 | refutado | 3 | 9 | L0-05-a-fila-postgres | adversario L2-2 (T9): evidencia commitada do fechamento f2a8cb15 tem quente_p95_ms=1290 > teto 1000 ms; ao vivo 167 ms = instavel sob carga, sem correcao; xfail tests/unit/test_l2_adv2_render_p95.py |
| `L2-17-crs-transformacoes` | 2 | refutado | 3 | 9 | L0-04-c-tabela-camada | adversario T9 (L2-3): install.sh nunca chama grades_ibge/instalar.sh (conferencia sha256 das grades NTv2) apesar do cabecalho alegar; xfail test_l2_17_grade_ibge_nao_instalada.py |
| `L2-19-paridade-l2-e-manual` | 2 | pendente | 0 |  | L2-04-j-conformidade-clientes-e-paridade, L2-01-c-lista-camadas-legenda, L2-02-c-editor-simbologia-vetor, L2-05-a-catalogo-ferramentas-gpserver, L2-06-b-elementos-basicos, L2-07-c-fila-sincronizacao-idempotente | — |
| `UX-05-telas-conexoes-uploads-tarefas-compartilhado` | 2 | parcial | 1 | 8 | — | 4 telas com controle e estados (conexões CRUD fecha UX-13, fila de envio, tarefas i18n, página pública sem chrome); progresso por byte bloqueado por autenticacao_ambigua (decisão do dono de auth); e2e 4/4 + suítes anteriores verdes |
| `UX-06-tela-administracao-inquilino` | 2 | parcial | 2 | 9 | — | MEDIDO 10/09 contra wt/lancamento (não contra ramo isolado): o trabalho existe e passa nos próprios testes, mas NENHUM commit da trilha UX está mesclado em wt/lancamento — `git merge-base --is-ancestor wt/cx3ux11 HEAD` = NOT merged (era a suposição a testar, e caiu: não é 'quase pronto', é 'nunca chegou'). wt/cx3ux11 (392 commits, 316 arquivos, 37.411 inserções) acumula UX-00,01-11,13,17,18,19,21,23 com docs/COBERTURA_UI.md real (240 rotas, 200 cobertas, 11 lacunas de escrita restantes fora deste lote) e e2e por item (test_ux06_admin.py, test_ux09_ferramentas.py, test_ux11_17_18_arquivos_ldap_plataforma.py, test_ux23_selecao_anotacoes_pacote.py etc.). BLOQUEIO REAL: o merge reescreve web/js/base/dom.js (+6/-x), web/js/camadas.js (+508), web/js/i18n/pt-BR.json (+2650/-769), web/js/mapa/atributos.js (+271) — os 4 arquivos que a regra da casa proíbe tocar porque outro agente edita AGORA (diff sujo confirmado: 217 linhas em 7 arquivos incl. esses 4, sig.js, sig.html, sig.css). Não é falta de trabalho, é ordem de chegada: precisa de um turno dedicado de merge (>1h, 316 arquivos) DEPOIS que os arquivos web/js/sig/*, camadas.js, dom.js e i18n/pt-BR.json ficarem livres. Específico: hub /admin completo (6 telas, e2e 6/6, evento registrado) vive em wt/cx3ux06 e dentro de wt/cx3ux11; nenhum dos dois mesclado. |
| `UX-10-acervo-sem-tela` | 2 | parcial | 2 | 8 | UX-01-sistema-de-design | rota POST /api/acervo/{fonte_id}/adicionar com controle nomeado na tela /acervo (base master + cx3ux05 + il601ctelaa): plat-estado na lista (carregando/vazio/erro/negado) e no controle adicionar dentro da ficha (403 negado com privilégio, 409 confirmação PII, 413/422 nomeados com referência); e2e 1/1 com 8 estados, axe 0 sérias, 0 erro de console, capturas 390/1280; COBERTURA_UI regenerado 41→40 lacunas; consertos de junção herdados (simbologia completa, nginx/vendor/i18n/tipos, PUBLIC em funções, expurgo); parcial só pela dependência UX-01 ainda parcial |
| `UX-11-arquivos-sem-controle` | 2 | parcial | 4 | 9 | UX-01-sistema-de-design | MEDIDO 10/09 contra wt/lancamento (não contra ramo isolado): o trabalho existe e passa nos próprios testes, mas NENHUM commit da trilha UX está mesclado em wt/lancamento — `git merge-base --is-ancestor wt/cx3ux11 HEAD` = NOT merged (era a suposição a testar, e caiu: não é 'quase pronto', é 'nunca chegou'). wt/cx3ux11 (392 commits, 316 arquivos, 37.411 inserções) acumula UX-00,01-11,13,17,18,19,21,23 com docs/COBERTURA_UI.md real (240 rotas, 200 cobertas, 11 lacunas de escrita restantes fora deste lote) e e2e por item (test_ux06_admin.py, test_ux09_ferramentas.py, test_ux11_17_18_arquivos_ldap_plataforma.py, test_ux23_selecao_anotacoes_pacote.py etc.). BLOQUEIO REAL: o merge reescreve web/js/base/dom.js (+6/-x), web/js/camadas.js (+508), web/js/i18n/pt-BR.json (+2650/-769), web/js/mapa/atributos.js (+271) — os 4 arquivos que a regra da casa proíbe tocar porque outro agente edita AGORA (diff sujo confirmado: 217 linhas em 7 arquivos incl. esses 4, sig.js, sig.html, sig.css). Não é falta de trabalho, é ordem de chegada: precisa de um turno dedicado de merge (>1h, 316 arquivos) DEPOIS que os arquivos web/js/sig/*, camadas.js, dom.js e i18n/pt-BR.json ficarem livres. Específico: código de UX-11 vive em wt/cx3ux11 junto com UX-17/18 (test_ux11_17_18_arquivos_ldap_plataforma.py existe lá). |
| `UX-12-categorias-sem-controle` | 2 | parcial | 2 | 8 | UX-01-sistema-de-design | PUT /api/categorias e POST /api/categorias/importar com controle na tela nova /admin/categorias (editor da árvore de 3 níveis + importar ISO 19115/INSPIRE) sobre master+cx3ux05+cxux10: plat-estado na lista (carregando/vazio/erro/negado) e no salvar/importar com 409/422/403 nomeados; i18n 3 idiomas; e2e 1/1 com 10 estados, axe 0 sérias, 0 erro de console, PUT e importação reais, capturas 390/1280; COBERTURA_UI regenerado 41→35 na junção; consertos de junção (27 casos cruzados, 13 eventos declarados); parcial só pela dependência UX-01 parcial |
| `UX-13-conexoes-sem-controle` | 2 | parcial | 2 | 8 | UX-01-sistema-de-design | tela /conexoes ja cobria as 8 rotas (UX-05); UX-13 = 404 em PATCH/DELETE tratado, e2e com 422/403/409/413/404 nomeados (17 estados, axe 0, console 0), COBERTURA_UI regenerado, junção test_ux05 cancelar |
| `UX-14-geocodificador-sem-tela` | 2 | parcial | 2 | 8 | UX-01-sistema-de-design | tela /geocodificar para POST /api/geocodificar e /api/reverso com plat-estado (vazio nomeado real, erro, negado, 422 no campo), i18n pt/en/es, COBERTURA_UI 35->33, e2e 10 estados axe 0; 200 real do CNEFE nao provado na trilha (UF nao carregada) |
| `UX-15-geocodificador-esri-sem-controle` | 2 | parcial | 2 | 8 | UX-01-sistema-de-design | secao GeocodeServer (Esri) em /geocodificar: URL para copiar, descritor, findAddressCandidates, reverseGeocode, geocodeAddresses com plat-estado e erro nomeado; URLs externas em /admin/tokens; COBERTURA_UI 33->29; e2e 11 estados axe 0; 200 real do CNEFE nao provado na trilha |
| `UX-16-ingestao-sem-tela` | 2 | parcial | 2 | 8 | UX-01-sistema-de-design | tela /importacoes: nova (POST), conferir e carregar (PUT confirmar), apagar (DELETE) com plat-estado, acompanhamento dos jobs e erro nomeado; fluxo real no e2e (13 estados, axe 0); COBERTURA_UI 29->26; achado: GET /api/importacoes/formatos respondia 404 (ordem das rotas), consertado |
| `UX-17-login-sem-controle` | 2 | parcial | 4 | 9 | UX-01-sistema-de-design | MEDIDO 10/09 contra wt/lancamento (não contra ramo isolado): o trabalho existe e passa nos próprios testes, mas NENHUM commit da trilha UX está mesclado em wt/lancamento — `git merge-base --is-ancestor wt/cx3ux11 HEAD` = NOT merged (era a suposição a testar, e caiu: não é 'quase pronto', é 'nunca chegou'). wt/cx3ux11 (392 commits, 316 arquivos, 37.411 inserções) acumula UX-00,01-11,13,17,18,19,21,23 com docs/COBERTURA_UI.md real (240 rotas, 200 cobertas, 11 lacunas de escrita restantes fora deste lote) e e2e por item (test_ux06_admin.py, test_ux09_ferramentas.py, test_ux11_17_18_arquivos_ldap_plataforma.py, test_ux23_selecao_anotacoes_pacote.py etc.). BLOQUEIO REAL: o merge reescreve web/js/base/dom.js (+6/-x), web/js/camadas.js (+508), web/js/i18n/pt-BR.json (+2650/-769), web/js/mapa/atributos.js (+271) — os 4 arquivos que a regra da casa proíbe tocar porque outro agente edita AGORA (diff sujo confirmado: 217 linhas em 7 arquivos incl. esses 4, sig.js, sig.html, sig.css). Não é falta de trabalho, é ordem de chegada: precisa de um turno dedicado de merge (>1h, 316 arquivos) DEPOIS que os arquivos web/js/sig/*, camadas.js, dom.js e i18n/pt-BR.json ficarem livres. Específico: há DUAS fontes — commits 'UX-17:' isolados em wt/cx5ux17 (glauth real, e2e próprio) E a versão consolidada dentro de wt/cx3ux11; nenhuma das duas está em wt/lancamento. |
| `UX-18-plataforma-sem-tela` | 2 | parcial | 3 | 8 | UX-01-sistema-de-design | tela /admin/inquilinos (console do superadmin): criar com senha temporaria uma vez, suspender, reativar, apagar com dupla confirmacao; plat-estado com negado real (404 da API a quem nao e superadmin), erros nomeados no campo (422 validacao, 409 slug_existente/slug_reservado, 409 plataforma_nao_suspende, 404 inexistente); COBERTURA_UI 26->22; e2e 13 estados com login TOTP do superadmin, axe 0 |
| `UX-19-rede-sem-tela` | 2 | parcial | 2 | 9 | UX-01-sistema-de-design | MEDIDO 10/09 contra wt/lancamento (não contra ramo isolado): o trabalho existe e passa nos próprios testes, mas NENHUM commit da trilha UX está mesclado em wt/lancamento — `git merge-base --is-ancestor wt/cx3ux11 HEAD` = NOT merged (era a suposição a testar, e caiu: não é 'quase pronto', é 'nunca chegou'). wt/cx3ux11 (392 commits, 316 arquivos, 37.411 inserções) acumula UX-00,01-11,13,17,18,19,21,23 com docs/COBERTURA_UI.md real (240 rotas, 200 cobertas, 11 lacunas de escrita restantes fora deste lote) e e2e por item (test_ux06_admin.py, test_ux09_ferramentas.py, test_ux11_17_18_arquivos_ldap_plataforma.py, test_ux23_selecao_anotacoes_pacote.py etc.). BLOQUEIO REAL: o merge reescreve web/js/base/dom.js (+6/-x), web/js/camadas.js (+508), web/js/i18n/pt-BR.json (+2650/-769), web/js/mapa/atributos.js (+271) — os 4 arquivos que a regra da casa proíbe tocar porque outro agente edita AGORA (diff sujo confirmado: 217 linhas em 7 arquivos incl. esses 4, sig.js, sig.html, sig.css). Não é falta de trabalho, é ordem de chegada: precisa de um turno dedicado de merge (>1h, 316 arquivos) DEPOIS que os arquivos web/js/sig/*, camadas.js, dom.js e i18n/pt-BR.json ficarem livres. Específico: POST /api/rota, /api/isocrona, /api/matriz ficam cobertos pelo painel Rotas de UX-08, dentro de wt/cx3ux11 (não mesclado). Nota: as rotas em SI (API) já existem em wt/lancamento (item L2-11-c) — falta é só a TELA. |
| `UX-20-usuarios-sem-controle` | 2 | parcial | 2 | 9 | UX-01-sistema-de-design | MEDIDO 10/09 contra wt/lancamento (não contra ramo isolado): o trabalho existe e passa nos próprios testes, mas NENHUM commit da trilha UX está mesclado em wt/lancamento — `git merge-base --is-ancestor wt/cx3ux11 HEAD` = NOT merged (era a suposição a testar, e caiu: não é 'quase pronto', é 'nunca chegou'). wt/cx3ux11 (392 commits, 316 arquivos, 37.411 inserções) acumula UX-00,01-11,13,17,18,19,21,23 com docs/COBERTURA_UI.md real (240 rotas, 200 cobertas, 11 lacunas de escrita restantes fora deste lote) e e2e por item (test_ux06_admin.py, test_ux09_ferramentas.py, test_ux11_17_18_arquivos_ldap_plataforma.py, test_ux23_selecao_anotacoes_pacote.py etc.). BLOQUEIO REAL: o merge reescreve web/js/base/dom.js (+6/-x), web/js/camadas.js (+508), web/js/i18n/pt-BR.json (+2650/-769), web/js/mapa/atributos.js (+271) — os 4 arquivos que a regra da casa proíbe tocar porque outro agente edita AGORA (diff sujo confirmado: 217 linhas em 7 arquivos incl. esses 4, sig.js, sig.html, sig.css). Não é falta de trabalho, é ordem de chegada: precisa de um turno dedicado de merge (>1h, 316 arquivos) DEPOIS que os arquivos web/js/sig/*, camadas.js, dom.js e i18n/pt-BR.json ficarem livres. Específico: PUT /api/papeis/{id} fica coberto pela edição de papel de UX-06 (wt/cx3ux06 / dentro de wt/cx3ux11), não mesclado. |
| `UX-21-multiescala-sem-tela` | 2 | parcial | 2 | 9 | UX-01-sistema-de-design | MEDIDO 10/09 contra wt/lancamento (não contra ramo isolado): o trabalho existe e passa nos próprios testes, mas NENHUM commit da trilha UX está mesclado em wt/lancamento — `git merge-base --is-ancestor wt/cx3ux11 HEAD` = NOT merged (era a suposição a testar, e caiu: não é 'quase pronto', é 'nunca chegou'). wt/cx3ux11 (392 commits, 316 arquivos, 37.411 inserções) acumula UX-00,01-11,13,17,18,19,21,23 com docs/COBERTURA_UI.md real (240 rotas, 200 cobertas, 11 lacunas de escrita restantes fora deste lote) e e2e por item (test_ux06_admin.py, test_ux09_ferramentas.py, test_ux11_17_18_arquivos_ldap_plataforma.py, test_ux23_selecao_anotacoes_pacote.py etc.). BLOQUEIO REAL: o merge reescreve web/js/base/dom.js (+6/-x), web/js/camadas.js (+508), web/js/i18n/pt-BR.json (+2650/-769), web/js/mapa/atributos.js (+271) — os 4 arquivos que a regra da casa proíbe tocar porque outro agente edita AGORA (diff sujo confirmado: 217 linhas em 7 arquivos incl. esses 4, sig.js, sig.html, sig.css). Não é falta de trabalho, é ordem de chegada: precisa de um turno dedicado de merge (>1h, 316 arquivos) DEPOIS que os arquivos web/js/sig/*, camadas.js, dom.js e i18n/pt-BR.json ficarem livres. Específico: as 7 rotas do multiescala ficam cobertas pelo painel Motor de UX-08, que também está dentro de wt/cx3ux11 (não mesclado). |
| `UX-22-ferramentas-esri-sem-tela` | 2 | refutado | 1 | 8 | UX-01-sistema-de-design | as rotas /rest/services/{ferramenta}/GPServer/* não existem no tronco nem em ramo da fila (lacuna veio de um OpenAPI antigo); nada a cobrir até L2-05-a entrar — a tela /ferramentas (UX-09) já lista qualquer registro de ferramenta pelo esquema |
| `UX-23-mapa-sem-controle` | 2 | parcial | 3 | 9 | UX-01-sistema-de-design | MEDIDO 10/09 contra wt/lancamento (não contra ramo isolado): o trabalho existe e passa nos próprios testes, mas NENHUM commit da trilha UX está mesclado em wt/lancamento — `git merge-base --is-ancestor wt/cx3ux11 HEAD` = NOT merged (era a suposição a testar, e caiu: não é 'quase pronto', é 'nunca chegou'). wt/cx3ux11 (392 commits, 316 arquivos, 37.411 inserções) acumula UX-00,01-11,13,17,18,19,21,23 com docs/COBERTURA_UI.md real (240 rotas, 200 cobertas, 11 lacunas de escrita restantes fora deste lote) e e2e por item (test_ux06_admin.py, test_ux09_ferramentas.py, test_ux11_17_18_arquivos_ldap_plataforma.py, test_ux23_selecao_anotacoes_pacote.py etc.). BLOQUEIO REAL: o merge reescreve web/js/base/dom.js (+6/-x), web/js/camadas.js (+508), web/js/i18n/pt-BR.json (+2650/-769), web/js/mapa/atributos.js (+271) — os 4 arquivos que a regra da casa proíbe tocar porque outro agente edita AGORA (diff sujo confirmado: 217 linhas em 7 arquivos incl. esses 4, sig.js, sig.html, sig.css). Não é falta de trabalho, é ordem de chegada: precisa de um turno dedicado de merge (>1h, 316 arquivos) DEPOIS que os arquivos web/js/sig/*, camadas.js, dom.js e i18n/pt-BR.json ficarem livres. Específico: painel Seleção + anotações + importar pacote (6 rotas) vive dentro de wt/cx3ux11 (commits 'UX-23:'), não mesclado. |
| `UX-25-camadas-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `UX-30-dominios-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `UX-33-mapa-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `UX-34-diversos-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `L2-01-a-basemap-local-pmtiles` | 3 | entregue | 1 | 3 | — | — |
| `L2-04-f-mapserver-identify-legend-geometryserver` | 3 | parcial | 2 | 8 | L2-04-c-featureserver-query, L2-12-a-motor-render-servidor | MapServer (descritor, layers, export png/jpg/pdf, identify, find, legend, generateKml) e GeometryServer (project, buffer geodesico, areasAndLengths, lengths, distance, union, intersect, difference, convexHull, simplify) por token, sobre PostGIS e Pillow, sem dependencia nova; 49 testes de API + 57 de unidade passam; export 1024x768 de 5.003 poligonos em 0,075 s quentes (teto 1,5 s), project 100 pontos 0,0 m contra ST_Transform, buffer 1 km 0,0 de erro relativo contra ST_Buffer geography; identify em 3 camadas igual a consulta espacial direta; 18 linhas novas na matriz de conformidade. PENDENTE: QGIS/ArcGIS Pro nao existem na maquina (sem ambiente grafico) -> a clausula de captura de cliente e a comparacao com a captura do visualizador ficam NAO MEDIDAS, substituidas pela conferencia do pixel contra o drawingInfo. |
| `L2-04-i-wms-wmts-sld` | 3 | refutado | 3 | 9 | L2-12-a-motor-render-servidor, L2-02-a-modelo-estilo, L1-02-tiles-token | adversario L2-2 (T9): hipotese promete WMS unico raster+vetor+SLD; so existe o vetorial e recusa SLD_BODY por desenho; xfail test_l2_adv2_wms_raster_sld.py |
| `L2-04-k-sync-replicas-esri` | 3 | parcial | 2 | 8 | L2-13-b-replicas-sincronizacao, L2-04-d-featureserver-edicao-anexos | protocolo Esri de sincronizacao de replica completo (createReplica com filtro em 2 camadas conferido por ogrinfo, synchronizeReplica sobe/desce com conflito por politica e idempotencia, extractChanges sem adiantar o ponteiro, unregister, job assincrono pelos 3 estados, teto 413): 14 testes verdes, medida 0,35 s em 200 feicoes; Field Maps/Pro reais fica para D20 |
| `L2-07-campo` | 3 | parcial | 0 |  | L2-03-edicao | Portado do SIG de campo de cliente (rs-coop/certaja/sig) em 10/09, commits f92f882d2/a1ac9b4f8/59642c9be: app/campo/ (fila de trabalho, roteiro por vizinho mais proximo + 2-opt, visita, foto), 6 tabelas com RLS por inquilino, 3 telas, 6 testes, endpoints GeoJSON de alvos e trajeto. Fluxo inteiro provado por curl na instancia viva: fila com 3 alvos -> roteiro -> visita -> reenvio do mesmo cliente_uuid nao duplica -> foto no S3 do inquilino com URL assinada; inquilino B recebe 404 na fila do A; capturas com clique real. Difere do original: alvo e referencia (camada_id, globalid) a feicao do catalogo, nao tabela de dominio eletrico. ⛔ FALTA o CENTRO do portão: construtor de formulario arrasta-e-solta gerando XLSForm valido, e PWA instalavel no celular com coleta offline. O que existe de offline e uma fila de escrita em localStorage com chave de idempotencia (nao duplica, nao perde), sem a camada de instalabilidade. Paridade escrita contra Survey123/Field Maps tambem falta. |
| `L2-07-d-mapa-offline-por-area` | 3 | pendente | 0 |  | L2-07-a-pwa-instalavel-cache, L2-01-b-martin-tiles-vetoriais, L2-13-b-replicas-sincronizacao | — |
| `L2-09-3d` | 3 | parcial | 0 | 8 | — | Portado do SIG de cliente (SIG de teste interno: visualizador xeokit + pipeline IFC->xkt) para o PLAT em 10/09, commits 884076ff6/c835b6bd6 no ramo wt/lancamento: tipo de item modelo3d e foto360, tarefa de fila modelo3d.converter (IFC -> .xkt por xeokit-convert na maquina com GPU, 16,8 s medidos ponta a ponta), pagina /modelo/{item} com o visualizador, painel de item, migracao 20260910T2100_modelo3d.sql. Modelo real de gabarito girando no demo publico, 0 erro de console (captura em scratchpad/shots_3d/). FALTA para entregue: 3D dentro do mapa (hoje e pagina propria), miniatura do modelo, e a DECISAO DE LICENCA — o xeokit-sdk e AGPL-3.0-only, fora da lista do ADR 0001 secao 11.2; aviso preso em web/vendor/VERSOES.txt. |
| `L2-09-a-terreno-terrain-rgb-relevo` | 3 | refutado | 2 | 9 | L2-01-b-martin-tiles-vetoriais | adversario L2-2 (T9): 2 de 5 clausulas do portao autodeclaradas 'nao medida' no JSON de fechamento; xfail test_l2_adv2_terreno_gate.py |
| `L2-09-b-cena-extrusao-slides` | 3 | refutado | 3 | 9 | L2-09-a-terreno-terrain-rgb-relevo, L2-02-a-modelo-estilo | adversario L2-2 (T9): fps medido 8,3 contra portao >= 30, sem limiar declarado; xfail test_l2_adv2_cena_fps.py |
| `L2-09-c-modelos-gltf-ifc-3dtiles` | 3 | parcial | 2 | 8 | L2-09-b-cena-extrusao-slides, L0-11-arquivos-objetos, L0-05-a-fila-postgres | modelos 3D no mapa sem biblioteca AGPL: GLB posicionado por three.js (erro de 0,097 m contra folga de 0,5 m), IFC aberto lido em Python puro com 13 elementos = 13 linhas e clique mostrando propriedades por GUID, 3D Tiles 1.1 gerado e aprovado pelo validador oficial (0 erro, 0 aviso) a 58,7 fps; Pro consumindo o tileset segue PENDENTE (D20) e i3s fica FORA, declarado |
| `L2-12-b-layouts-elementos-exportacao` | 3 | pendente | 1 | cx3 | L2-12-a-motor-render-servidor, L2-01-c-lista-camadas-legenda, L2-02-a-modelo-estilo | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L2-12-impressao-layout` | 3 | pendente | 0 |  | L2-02-simbologia | — |
| `L2-13-a-versoes-ramo-reconciliar` | 3 | parcial | 2 | 8 | L2-03-a-api-edicao-transacional, L2-03-d-historico-restauracao | Versionamento por ramo inteiro (criar/editar/reconciliar/resolver/publicar/apagar), gdbVersion e historicMoment na consulta, VersionManagementServer com 12 passos do protocolo ok, tela de diff lado a lado; 18 testes verdes; reconciliar 10 mil edicoes em 29,6 s sob carga 9,3. Pendentes: Pro real (D20) e o e2e do diff, que so roda contra a URL publica. |
| `L2-13-b-replicas-sincronizacao` | 3 | parcial | 2 | 8 | L2-03-a-api-edicao-transacional, L0-05-a-fila-postgres | Replicas GeoPackage + sincronizacao com politica de conflito e idempotencia: 7 de 8 clausulas feitas (100 mil feicoes em 1,97 s sob carga 7,86); QField no aparelho nao testado (nao bloqueia, forma provada por GDAL 3.8.4) |
| `L2-13-versionamento-sync` | 3 | pendente | 0 |  | L2-03-edicao, L2-07-campo | — |
| `L2-14-a-ingestao-de-fluxos` | 3 | pendente | 1 | fable | L0-05-a-fila-postgres | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L2-14-b-camada-viva-historico` | 3 | pendente | 0 |  | L2-14-a-ingestao-de-fluxos, L2-06-d-atualizacao-viva-sse, L2-01-b-martin-tiles-vetoriais | — |
| `L2-14-c-regras-alertas-incidentes` | 3 | pendente | 0 |  | L2-14-b-camada-viva-historico, L2-10-c-linguagem-expressao, L7-08-a-webhooks-eventos | — |
| `L2-14-tempo-real` | 3 | pendente | 0 |  | L0-05-jobs | — |
| `L2-15-a-geoparquet-bucket-catalogo` | 3 | parcial | 2 | 7 | L0-11-arquivos-objetos, L0-05-a-fila-postgres | agente marcou entregue com cláusula QGIS-em-Docker não medida e 403 do portão devolvendo 404; rebaixado a parcial pelo coordenador. Ramo wt/il215ageopa f5aeef6 na fila. Achado a apurar: trava de aconselhamento global 'pesado' em app/jobs/worker.py::_pegar (classe F5) |
| `L2-15-analitica-grande` | 3 | pendente | 0 |  | L2-05-geoprocessamento | — |
| `L2-15-b-consultas-duckdb-em-escala` | 3 | pendente | 1 | fable | L2-15-a-geoparquet-bucket-catalogo, L2-05-a-catalogo-ferramentas-gpserver | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L2-18-camada-de-consulta-sql` | 3 | pendente | 0 |  | L0-04-c-tabela-camada, L0-04-j-camada-vista, L2-04-a-leitor-rls-martin | — |
| `L2-07-e-odk-central-ponte` | 4 | parcial | 2 | 8 | L2-07-b-formulario-de-coleta-xlsform, L0-05-a-fila-postgres | ponte ODK Central: publica XLSForm, puxa envios por OData com anexos, idempotente por instanceID, Entities como lista em cascata; provada contra dublê HTTP da API documentada (Central real nao instalavel aqui, D29) |
| `L2-09-d-analise-3d-visibilidade` | 4 | parcial | 2 | 8 | L2-09-a-terreno-terrain-rgb-relevo, L2-05-e-raster-basico | as 4 analises de terreno (visada, viewshed pelo binario gdal_viewshed byte a byte, perfil conferido com rasterio.sample, sombra prisma+NOAA), rotas+tela+e2e com captura de cada, paridade Scene Viewer escrita; medidas: obstrucao 2,75 m, desvio sombra 0,268 % |
| `L2-12-c-series-de-mapas-lote` | 4 | pendente | 0 |  | L2-12-b-layouts-elementos-exportacao, L2-01-h-selecao-filtros | — |
| `L2-16-a-sdk-python-geo` | 4 | refutado | 3 | 9 | L7-08-sdk-api-webhooks, L2-04-c-featureserver-query, L2-03-a-api-edicao-transacional | adversario T9 (L2-3): pacote/plat nao tem Camada.ler->GeoDataFrame, Raster, Tabela, Mapa nem widget de notebook (so CRUD de item) e colide nome+versao (plat 0.1.0) com sdk/python de L7-08-b com APIs incompativeis; xfail test_l2_16a_sdk_geo_ausente.py (6) |
| `L2-16-b-jupyter-por-inquilino-isolado` | 4 | refutado | 4 | 9 | L2-16-a-sdk-python-geo, L0-11-arquivos-objetos, L0-05-e-worker-em-container | adversario T9 (L2-3): trava '1 conteiner de notebook por vez' e threading.Lock por processo, mas plat-api sobe com --workers 2: dois processos passam juntos pela secao critica; xfail test_l2_16b_notebooks_trava_entre_processos.py |
| `L2-16-c-script-vira-ferramenta` | 4 | parcial | 2 | 8 | L2-16-b-jupyter-por-inquilino-isolado, L2-05-a-catalogo-ferramentas-gpserver | script com cabecalho YAML declarativo vira ferramenta-script versionada (L5-05); formulario do cabecalho, execucao como job no conteiner do inquilino (L2-16-b) com saida item ferramenta_resultado com procedencia versao+sha256, 422 antes do job, refutacao de rede//etc/teto/escrita/sha adulterado e versao nova nao muda execucao passada provados (32 passed 1 xfail); clausula 5 GPServer submitJob PENDENTE no wt/cx205 (L2-05-a, nao ancestral) |
| `L2-16-notebooks-scripts` | 4 | pendente | 0 |  | L5-02-fluxos | — |

### L3 motor AMC (37 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L3-01-a-modelo-dado` | 1 | refutado | 2 | 3 | L0-02-tenant-auth | adversário: gravar_feicoes usa execute_values e manda BYTES ao cursor, que só reescreve consulta str -> fora do schema plat (homologação e bases por trilha) morre com permission denied e devolve 403 enganoso; transformações inválidas aceitas (linear com faixa invertida, faixas com quebras fora de ordem, degraus fora de ordem, contínua sem parâmetro) entram no hash; zonas_utm_cobertas perde as zonas do meio; teto conferido sobre estimativa e não sobre resultado; chave repetida no JSON cru aceita; 3 e 3.0 dão hashes diferentes. Imutabilidade e isolamento entre inquilinos AGUENTARAM (18 rotas sondadas) |
| `L3-01-b-unidades` | 1 | parcial | 3 | 3 | L3-01-a-modelo-dado | adversário gerou a escala que faltava: 1.000.175 células em 30,97 s (projeção 34,3 s), desvio de contagem +0,201%; cláusula refeita por fora com shapely/pyproj. Falta: zonas_utm_cobertas perde zonas do meio; só vira entregue depois do merge (regra combinada com a outra sessão) |
| `L3-01-c-extracao-fator` | 1 | parcial | 1 | 3 | L3-01-b-unidades, L0-04-ingest-vetor | Extratores raster (app/amc/zonal.py, resgatado+revisado) e vetor (app/amc/vetorial.py, novo) no ramo wt/extrat. 14 clausulas verdes com recomputacao independente shapely/rasterio/pyproj puros: media zonal 200 unidades divergencia maxima 0 (portao <=1 celula); area/comprimento de vetor 200 unidades <=0,5%; fracao ponderada por AREA provada contra centroide; cobertura por fator gravada, NULL nunca vira 0; raster sem CRS e camada vazia abortam com ErroExtracao; poligono invalido reparado sem derrubar o job; distancia bate com pyproj.Geod (equivalente ST_Distance(geography)) em 50 unidades. Clausula de tempo (12 fatores x 73 mil celulas) NAO MEDIDA: roda_teste.sh estourou 600s com a maquina compartilhada (carga 6,31, RAM livre 9GB) — registrado em tests/medidas/L3-01-c-extracao-fator.json; extrapolacao de bancada nao oficial projeta ~543s, acima da referencia de 1-2min do motor logistico em SQL. Depende de L3-01-b-unidades (parcial, aguardando merge combinado com outra sessao). |
| `L3-01-d-transformacoes` | 1 | parcial | 1 | 5 | L3-01-c-extracao-fator | 16 tipos implementados numpy+SQL, equivalencia <=0,01 em todos (17 casos); adversario gaussiana/logistica/MSLarge bateu <=0,01; previsualizacao 15-33ms/100mil medido mas clausula de desempenho NAO MEDIDA (carga>8); CBRE: 4 de 19 fatores reproduzidos a 100% (decl,rod,agua,press), 15 fora de escopo nomeados (gru/se com coluna candidata divergente medida, os outros combinam varias colunas/veto fora do escopo de transformacao pura); MANUAL+16 graficos gerados por script; executor.py usa a biblioteca inteira |
| `L3-01-e-combinacao` | 1 | entregue | 1 | 3 | L3-01-d-transformacoes | — |
| `L3-01-f-explicacao` | 1 | parcial | 1 | 5 | — | backend+painel+testes entregues (100 unidades, veto, API real); latência não medida (carga_1min~23); e2e correto mas não corrido de ponta a ponta (sem nginx na trilha) |
| `L3-01-g-tela-motor` | 1 | parcial | 2 | 8 | L3-01-f-explicacao | Tela /amc/motor no ar: 5 fatores, veto, peso por deslizante ou percentual com trava, recombinacao no navegador com ZERO requisicao a API ao mover peso, mapa por rampa declarada, explicacao fator a fator, link com pesos validado (recusa 999/fator inexistente/soma 130 sem calcular). Rotas novas matriz e previsao, com caso cruzado, evento e x-auth. Pendente: geopandas fora da venv (import tardio contorna), suite api inteira estourou 900s sob carga, e2e sem nginx |
| `L3-01-j-equivalencia-motor-logistico` | 1 | refutado | 2 | 9 | — | adversario T9 L3: modelo de referencia recusado pelo esquema (campos do L3-15) e prova contra o oraculo pula sem PLAT_MOTOR_REFERENCIA_ESQUEMA na trilha — inverificavel; xfail |
| `L3-01-motor-servico` | 1 | pendente | 0 |  | L2-05-geoprocessamento | — |
| `L3-14-cobertura-dado-ausente` | 1 | entregue | 2 | 9 | L3-01-c-extracao-fator | — |
| `L3-01-c2-extracao-em-lote` | 2 | pendente | 0 |  | L3-01-c-extracao-fator | achado do L3-01-c (07/09): cláusula de tempo NÃO MEDIDA, extrapolação ~543 s. Item criado para não perder o achado. |
| `L3-01-h-presets` | 2 | entregue | 3 | 9 | L3-01-g-tela-motor | — |
| `L3-01-i-exportacao-metodo` | 2 | parcial | 2 | 8 | — | método exportado em JSON canônico (plat/amc_metodo, sha256, recusa documento alterado) + PDF determinístico uma seção por página, todo número do PDF no JSON (23 conferidos), 8 páginas = 8 seções, PDF lido página a página, e2e automatizado verde |
| `L3-04-restricoes` | 2 | refutado | 2 | 8 | L3-01-c-extracao-fator | artefato ausente em master (auditoria HARD-03 07/09): sem combinador de restrição em app/amc |
| `L3-06-criterios-de-feicao` | 2 | parcial | 2 | 8 | L3-01-c-extracao-fator | Critérios sobre a feição no motor AMC: 4 tipos, influência positiva/inversa/ideal, filtro de inclusão que não é veto, rotas JSON e CSV, tela com histograma e matriz de correlação. 38 testes verdes; contagem em raio bate com ST_DWithin em 1.000 feições, 0 divergência. e2e escrito mas NÃO medido na trilha (sem nginx para /static). |
| `L3-07-agregacao` | 2 | entregue | 1 | 6 | — | — |
| `L3-12-integracao-fluxo-e-api` | 2 | pendente | 0 |  | L3-01-g-tela-motor, L5-02-fluxos, L0-05-jobs | — |
| `L3-13-resultado-como-camada` | 2 | pendente | 2 | 8 | L2-04-servicos-esri-ogc, L1-02-tiles-token | agente Sonnet caiu por 429 às 17:20 sem worktree nem commit; devolvido a pendente pelo coordenador (nada em disco) |
| `L3-18-paridade-esri-amc` | 2 | pendente | 1 | plataforma-48 | L3-01-g-tela-motor | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `UX-26-amc-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `UX-27-multiescala-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `L3-02-a-monte-carlo-pesos` | 3 | refutado | 2 | 8 | — | artefato ausente em master (auditoria HARD-03 07/09): 0 monte-carlo em app; não implementado no motor AMC de master |
| `L3-02-b-sensibilidade-sobol-oat` | 3 | parcial | 2 | 8 | L3-02-a-monte-carlo-pesos | Sobol global (Saltelli/Jansen, Ishigami com desvio 0,0004) + tornado OAT + relatorio por modelo e job amc.sensibilidade; refutacao do fator duplicado passa nos dois alvos; sem rota nova |
| `L3-02-c-smaa` | 3 | entregue | 3 | 9 | L3-02-a-monte-carlo-pesos | — |
| `L3-02-d-comparacao-cenarios` | 3 | pendente | 1 | plataforma-48 | — | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L3-02-robustez` | 3 | pendente | 0 |  | L3-01-motor-servico | — |
| `L3-03-ahp-pares` | 3 | pendente | 1 | plataforma-48 | — | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L3-05-localizar-regioes` | 3 | parcial | 2 | 8 | — | motor de localizar regiões (app/amc/regioes.py): crescimento por fila de prioridade com compromisso forma × utilidade (círculo/quadrado/hexágono), área total alvo, área mín/máx por região, distância mín/máx, 4 métodos de avaliação, seleção sequencial e combinatória, veto intransponível e sem ilhas; rota POST /api/multiescala/execucoes/{id}/regioes devolve polígono por região; 3 picos = 3 regiões a ≤0,03 célula dos picos, área a 0% do alvo, compacidade ≥0,98, 1 mi de células em 3,42 s (N=3) e 9,09 s (N=10); refutações (área > disponível, N=31, mesma semente) cobertas; paridade contra o Locate Regions com a página lida em 08/09/2026; 3 de 7 formas e 4 de 8 métodos, sem tela (L3-01-g) |
| `L3-09-backtest-decisao-real` | 3 | parcial | 2 | 8 | L3-02-a-monte-carlo-pesos | backtest contra decisão real (app/amc/backtest.py + POST /api/multiescala/execucoes/{id}/backtest): percentil das escolhas, nulo por permutação, AUC Mann-Whitney com p-valor de uma cauda e preferência revelada por fator (sinal e ordem, nunca peso); ressalvas de correlação, distância e anacronismo no corpo do relatório; medido sobre dado aberto real (602 galpões OSM >5.000 m², grade de 500 m, fator proximidade de via arterial): AUC 0,718, percentil mediano 74,8, p 0,002; escolhas do próprio modelo AUC 1,000 e ao acaso 0,4993 (desvio 0,0145); refutações (todas as células escolhidas = AUC indefinida com a frase; escolhas fora da grade contadas) cobertas; sem tela (L3-01-g); a dependência L3-02-a (Monte Carlo de pesos) não foi usada — o nulo deste item é por permutação de unidades |
| `L3-10-corredor-custo-minimo` | 3 | parcial | 2 | 8 | L3-04-restricoes | traçado de custo mínimo exposto como rota HTTP síncrona sobre a execução multiescala, com registro triplo, reprodução bit a bit do trecho de referência da casa (Hausdorff 100 m, 382 km em 5,8 s) e testes de unidade, API e portões verdes; tela e2e fica para a parcela de frontend |
| `L3-11-fator-de-rede` | 3 | pendente | 2 | 8 | L3-01-c-extracao-fator, L2-11-geocodificacao-rota | solto por cx5 sem tocar em código: a sessão estava construindo L3-10-corredor-custo-minimo (ramo wt/cx5l310) e a reivindicação de 13:05 pegou este item por engano. Volta livre, intacto. |
| `L3-15-metadado-fator` | 3 | entregue | 2 | 9 | L3-01-d-transformacoes | — |
| `L3-16-desempenho-escala` | 3 | entregue | 2 | 9 | L3-01-c-extracao-fator | — |
| `L3-08-pareto` | 4 | parcial | 2 | 8 | — | fronteira de Pareto: módulo puro conferido contra laço ingênuo O(n²) em 2.000 unidades (2-4 objetivos), rotas /api/amc/pareto e /api/amc/pareto/camada, tela com dispersão e mapa ligados; e2e escrito e não corrido na trilha (sem nginx) |
| `L3-17-similaridade` | 4 | refutado | 2 | 8 | L3-01-c-extracao-fator | artefato ausente em master (auditoria HARD-03 07/09): sem similaridade no AMC (só em geocodificador) |
| `L3-19-multiescala` | 4 | entregue | 2 | 3 | L3-01-b-unidades | — |
| `L3-20-narrativa-de-resultado` | 4 | parcial | 2 | 8 | L3-01-i-exportacao-metodo | narrar()+revisar() em app/amc/narrativa.py; 13 testes; texto de 3 unidades conferido à mão; 0,02 ms/narração (carga 4,34); 5 commits |

### L4 rede de utilidades (73 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L4-01-a-pacote-de-ativos` | 1 | refutado | 4 | 8 | L0-04-ingest-vetor | artefato ausente em master (auditoria HARD-03 07/09): rede de utilidades ausente; app/rede é roteamento |
| `L4-01-b-topologia-derivada` | 1 | refutado | 2 | 8 | L4-01-a-pacote-de-ativos | artefato ausente em master (auditoria HARD-03 07/09): sem tabela de topologia de rede em master |
| `L4-01-c-importador-bdgd` | 1 | refutado | 2 | 9 | L4-01-b-topologia-derivada, L0-05-jobs | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-01-f-alcance-do-tracado-rede-real` | 1 | parcial | 2 | 8 | L4-01-c-importador-bdgd | tolerancia declarada por par de tipos (rede_regra.tolerancia_m): alcance a jusante de 428/600 para 599/600 trafos, pior alimentador 66,67% para 99,51%, 5 de 5 acima de 95%, lacos na MT iguais antes e depois, orfaos 1.038 para 495 com classes nomeadas; rota de diagnostico por classe |
| `L4-01-g-tarefas-import-tardio` | 1 | refutado | 3 | 9 | L4-01-c-importador-bdgd | adversario T9 L4-2: bdgd.py perdeu o import preguicoso _pyogrio na fusao 04f20ef8b (test_dependencias.py 2/6 falham); regressao |
| `L4-01-modelo-rede` | 1 | tentando | 2 | 9 | L0-04-ingest-vetor | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-02-a-conectado-e-subrede` | 1 | refutado | 2 | 9 | L4-01-b-topologia-derivada | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-02-b-montante-jusante` | 1 | refutado | 3 | 9 | L4-02-a-conectado-e-subrede, L4-04-a-controladores-e-tiers | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-02-c-isolamento` | 1 | refutado | 3 | 9 | L4-02-b-montante-jusante, L4-06-d-categorias-e-restricoes | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-02-tracado` | 1 | pendente | 0 |  | L4-01-modelo-rede | — |
| `L4-03-a-regras-de-conectividade` | 1 | refutado | 2 | 8 | L4-01-a-pacote-de-ativos | artefato ausente em master (auditoria HARD-03 07/09): sem regras de conectividade em master |
| `L4-03-c-edicao-topologica-no-mapa` | 1 | pendente | 0 |  | L4-03-a-regras-de-conectividade, L2-03-edicao | — |
| `L4-03-d-areas-sujas-e-validacao` | 1 | refutado | 2 | 8 | L4-01-b-topologia-derivada, L4-03-a-regras-de-conectividade | artefato ausente em master (auditoria HARD-03 07/09): sem áreas sujas/validação de rede em master |
| `L4-04-a-controladores-e-tiers` | 1 | refutado | 2 | 9 | L4-01-d-atributos-de-rede | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-04-b-atualizar-e-exportar-subrede` | 1 | refutado | 3 | 9 | L4-04-a-controladores-e-tiers, L4-02-a-conectado-e-subrede | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-05-a-exportar-opendss` | 1 | refutado | 3 | 9 | L4-01-c-importador-bdgd, L4-04-b-atualizar-e-exportar-subrede | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-07-fluxo-de-potencia` | 1 | pendente | 1 | fable | L4-05-a-exportar-opendss, L0-05-jobs | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L4-08-queda-de-tensao-e-carregamento` | 1 | pendente | 0 |  | L4-07-fluxo-de-potencia | — |
| `L4-23-isolamento-por-inquilino-na-rede` | 1 | refutado | 2 | 8 | L4-01-b-topologia-derivada, L0-02-tenant-auth | artefato ausente em master (auditoria HARD-03 07/09): rede de utilidades ausente |
| `UX-08-telas-rede-de-utilidades-e-motor` | 1 | parcial | 1 | 8 | — | medido 10/09: painéis Rotas e Motor existem completos (e2e+axe, cobertura 240 rotas/24 lacunas) só no ramo wt/cx3ux08 — diverge 201 commits à frente / 366 atrás de wt/lancamento, mescla não cabe num item. Front-end de rede de utilidades (traçado montante/jusante, importar BDGD/EPANET) segue AUSENTE em wt/lancamento (confirmado: nenhum HTML/JS sob web/ liga o chrome do visualizador à L4; mesma fronteira nomeada pelo item irmão L4-02-a/L4-02-d). Trilha `entrega` (127.0.0.1:8190, indicada pelo coordenador) estava FORA DO AR na medição de hoje (log parado em 17:21 UTC, último erro AttributeError em app/status.py `estatisticas_cluster`, sem processo ouvindo a porta) — não deu para confirmar lá. |
| `L4-01-d-atributos-de-rede` | 2 | refutado | 2 | 9 | L4-01-b-topologia-derivada | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-02-d-lacos-e-caminho-curto` | 2 | refutado | 3 | 9 | L4-02-a-conectado-e-subrede | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-02-e-configuracoes-de-tracado` | 2 | refutado | 3 | 9 | L4-02-c-isolamento, L4-02-d-lacos-e-caminho-curto | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-03-b-terminais` | 2 | pendente | 0 |  | L4-03-a-regras-de-conectividade, L4-01-d-atributos-de-rede | — |
| `L4-03-e-versao-de-rede` | 2 | pendente | 0 |  | L4-03-d-areas-sujas-e-validacao, L2-13-versionamento-sync | — |
| `L4-03-edicao-rede` | 2 | pendente | 0 |  | L4-02-tracado, L2-03-edicao | — |
| `L4-04-c-sumarios-por-subrede` | 2 | refutado | 3 | 9 | L4-04-b-atualizar-e-exportar-subrede | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-04-c-unificar-subrede` | 2 | parcial | 2 | 8 | L4-04-a-controladores-e-tiers, L4-01-c-importador-bdgd | Uma tabela so: plat.rede_subrede com origem controlador (canonica) x bdgd (declarada pelo arquivo), migracao 20260908T0152 copiando com o mesmo id e repontando rede_no/rede_aresta; reconciliacao medida 3/3 alimentadores e 1729/1729 trafos no recorte da cooperativa (carga 4,82); testes dos dois itens irmaos verdes |
| `L4-04-d-diagrama-esquematico` | 2 | refutado | 3 | 9 | L4-04-b-atualizar-e-exportar-subrede | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-05-b-cim-iec-61970-61968` | 2 | pendente | 0 |  | L4-01-a-pacote-de-ativos, L4-04-b-atualizar-e-exportar-subrede | — |
| `L4-05-c-pandapower-e-matpower` | 2 | refutado | 3 | 9 | L4-05-a-exportar-opendss | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-05-d-epanet-inp` | 2 | refutado | 3 | 9 | L4-01-a-pacote-de-ativos, L4-01-b-topologia-derivada | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-05-f-transmissao-sindat-sigel` | 2 | pendente | 0 |  | L4-01-a-pacote-de-ativos, L6-01-acervo-casa | — |
| `L4-06-a-contencao` | 2 | pendente | 0 |  | L4-03-a-regras-de-conectividade, L4-03-c-edicao-topologica-no-mapa | — |
| `L4-06-b-estrutura-postes` | 2 | pendente | 0 |  | L4-06-a-contencao | — |
| `L4-06-d-categorias-e-restricoes` | 2 | refutado | 2 | 9 | L4-01-a-pacote-de-ativos | adversario T9 L4-2: gas-br.json emite vocabulario antigo -> CheckViolation ao instalar; xfail test_l4_adv2_pacote_vocabulario.py |
| `L4-09-perdas-tecnicas-por-segmento` | 2 | pendente | 0 |  | L4-07-fluxo-de-potencia | — |
| `L4-10-continuidade-dec-fec` | 2 | pendente | 1 | fable | L4-04-c-sumarios-por-subrede, L6-01-acervo-casa | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L4-11-gd-conectada-e-hospedagem` | 2 | pendente | 0 |  | L4-07-fluxo-de-potencia, L4-04-c-sumarios-por-subrede | — |
| `L4-12-inspecao-vegetacao-na-faixa` | 2 | pendente | 0 |  | L4-01-c-importador-bdgd, L1-03-conectores-sensores, L0-05-jobs | — |
| `L4-13-integracao-telemetria` | 2 | refutado | 1 | 9 | L4-01-b-topologia-derivada, L2-14-tempo-real | adversario T9 L4-2: clausulas de desempenho (latencia 20 sensores, consulta 1 mes) nunca medidas; xfail test_l4_adv2_telemetria_medidas.py |
| `L4-16-api-rest-compativel-un` | 2 | pendente | 0 |  | L4-02-e-configuracoes-de-tracado, L4-03-d-areas-sujas-e-validacao, L4-04-b-atualizar-e-exportar-subrede, L2-04-servicos-esri-ogc | — |
| `L4-21-qualidade-e-saude-da-rede` | 2 | pendente | 0 |  | L4-03-d-areas-sujas-e-validacao, L4-04-c-sumarios-por-subrede | — |
| `L4-22-desempenho-em-escala` | 2 | pendente | 0 |  | L4-01-c-importador-bdgd, L4-02-e-configuracoes-de-tracado, L4-03-d-areas-sujas-e-validacao | — |
| `L4-24-cartografia-de-rede` | 2 | pendente | 1 | fable | L2-02-simbologia, L4-01-d-atributos-de-rede | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `UX-24-rede-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `UX-28-parcelas-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `L4-01-e-dicionario-unidades-bdgd` | 3 | refutado | 3 | 9 | L4-01-c-importador-bdgd | adversario T9 L4-2: bdgd.py perdeu a integracao de auditoria de unidades na fusao 04f20ef8b (test_rede_unidades_bdgd.py 2 failed + 3 error); regressao |
| `L4-01-h-alinhamento-inspire-gnm` | 3 | refutado | 2 | 9 | L4-01-a-pacote-de-ativos | adversario T9 L4-2: mapeamento INSPIRE GNM omite o dominio gas apesar do portao; xfail |
| `L4-02-f-resultados-e-exportacao` | 3 | refutado | 3 | 9 | L4-02-e-configuracoes-de-tracado | adversario T9 L4-1 (transversal): POST/GET /api/rede estoura ResponseValidationError porque rotas.py nao le/escreve tolerancia_m (regressao de fusao) e a 1a instalacao de qualquer pacote de dominio falha com CheckViolation (vocabulario antigo de rede_regra.tipo); arquivo oficial do item cai ao vivo (laudo linha-L4-laudo-adversario-1.md); xfail tests/api/adversario/test_l4_adv1_transversais.py |
| `L4-04-e-diagrama-camadas-e-contencao` | 3 | pendente | 0 |  | L4-04-d-diagrama-esquematico, L4-06-a-contencao | — |
| `L4-04-subredes-diagramas` | 3 | pendente | 0 |  | L4-03-edicao-rede | — |
| `L4-05-conectores-rede` | 3 | pendente | 0 |  | L4-01-modelo-rede | — |
| `L4-05-e-gas-e-esgoto` | 3 | refutado | 3 | 9 | L4-05-d-epanet-inp | adversario T9 L4-2: esgoto-teksi.json emite vocabulario antigo de rede_regra.tipo (migracao 20260906T2058 nao atualizou os pacotes) -> CheckViolation ao instalar; TEKSI so provado com GeoPackage sintetico; xfail test_l4_adv2_pacote_vocabulario.py |
| `L4-05-g-osm-power` | 3 | refutado | 2 | 8 | L4-01-a-pacote-de-ativos, L0-04-ingest-vetor | artefato ausente em master (auditoria HARD-03 07/09): sem rede de utilidades em master |
| `L4-05-h-inspire-utility-networks` | 3 | pendente | 0 |  | L4-05-b-cim-iec-61970-61968 | — |
| `L4-06-c-objetos-nao-espaciais` | 3 | pendente | 0 |  | L4-06-a-contencao, L4-03-b-terminais | — |
| `L4-06-estruturas-regras-avancadas` | 3 | pendente | 0 |  | L4-03-edicao-rede | — |
| `L4-14-balanco-de-energia-por-alimentador` | 3 | pendente | 0 |  | L4-04-c-sumarios-por-subrede, L4-09-perdas-tecnicas-por-segmento | — |
| `L4-15-serie-temporal-da-rede` | 3 | parcial | 2 | 8 | L4-01-c-importador-bdgd | Serie temporal no ar: rede_linhagem classifica cada COD_ID em 4 classes pela regua medida da casa, tendencia por trafo exportavel em CSV, crescimento por alimentador, placa marcada nao confiavel em troca em massa e controle deslizante de safra no mapa (e2e verde). 24 testes verdes + 1 lento em 2 safras REAIS conferidas contra recontagem independente dos GDB. Achado: o importador grava o OBJECTID como codigo_externo da UC, e a serie le a identidade de atributos->>COD_ID. Escala cheia da cooperativa NAO medida (45 min sem terminar a importacao, gargalo de L4-01-c). |
| `L4-17-migracao-de-un-e-rede-geometrica` | 3 | pendente | 0 |  | L4-01-a-pacote-de-ativos, L4-05-b-cim-iec-61970-61968, L2-08-migracao-agol | — |
| `L4-18-rede-simples-trace-network` | 3 | refutado | 2 | 8 | L4-01-b-topologia-derivada, L4-02-a-conectado-e-subrede | artefato ausente em master (auditoria HARD-03 07/09): 0 trace_network em master |
| `L4-19-planejamento-de-linha-nova` | 3 | pendente | 0 |  | L3-01-motor-servico, L4-01-a-pacote-de-ativos | — |
| `L4-20-consumidores-e-enderecos` | 3 | parcial | 2 | 8 | L4-01-c-importador-bdgd, L6-01-acervo-casa | trabalho completo (6 tabelas rede_* com RLS, 5 rotas, jusante por circuito, camada 10.914 vs 10.911 da casa = 0,03%, medições de 6,4s/3,6s, plano do KNN documentado em ADR) existe em wt/swL401, mas NÃO está em wt/lancamento — diverge 336 commits atrás / só 15 à frente, mesma situação de risco do L4-29 (o ramo tem só 15 commits próprios sobre uma base já 336 commits velha). Trilha `entrega` estava FORA DO AR na medição de hoje. |
| `L4-25-cenarios-e-se` | 3 | pendente | 0 |  | L4-03-e-versao-de-rede, L4-07-fluxo-de-potencia | — |
| `L4-26-inspecao-de-campo-do-ativo` | 3 | pendente | 0 |  | L2-07-campo, L4-06-b-estrutura-postes | — |
| `L4-27-curto-circuito-e-protecao` | 3 | entregue | 2 | 8 | L4-05-c-pandapower-e-matpower | — |
| `L4-28-identificadores-e-numeracao` | 3 | refutado | 3 | 8 | L4-01-a-pacote-de-ativos | artefato ausente em master (auditoria HARD-03 07/09): rede de utilidades ausente |
| `L4-29-regras-de-atributo-de-rede` | 3 | parcial | 2 | 8 | L2-10-relacoes-regras, L4-04-b-atualizar-e-exportar-subrede | trabalho completo (motor de regras cálculo/restrição/validação sem ponto fixo e falha fechada, 6 funções de rede nos 2 avaliadores = 49 funções/393 vetores, 18 testes de API verdes, paridade escrita) existe em wt/swL402, mas NÃO está em wt/lancamento — diverge 336 commits atrás / só 15 à frente, e as 15 tocam os avaliadores Python/JS de expressão (infraestrutura compartilhada por toda a plataforma), evoluídos muito desde então: mesclar hoje é risco real de quebrar a linguagem de expressão inteira, não cabe em 20 min. Trilha `entrega` (127.0.0.1:8190) estava FORA DO AR na medição de hoje — não deu para confirmar lá. |
| `L4-parcelas-01-modelo-de-parcelas` | 3 | parcial | 2 | 8 | L0-04-ingest-vetor, L2-03-edicao, L2-13-versionamento-sync | modelo de parcelas orientado a registro: 6 tabelas com RLS, COGO com raio com sinal, retirada sem apagar (linha partilhada fica), ficha com linhagem nos 2 sentidos, import real de 11.473 lotes do SIG interno medido, validação de sobreposição por consulta, paridade parcel fabric com fontes datadas; visões com security_invoker |
| `L4-parcelas-02-fluxos-cogo` | 3 | parcial | 2 | 8 | L4-parcelas-01-modelo-de-parcelas | trabalho completo (fluxos divide/merge/clip/build/seeds/assign + fachada ParcelFabricServer + DXF com e2e e 41 testes verdes) existe em wt/il4parcelas — mesma situação do L4-parcelas-03: diverge 355 commits atrás / 45 à frente, ramo checked out agora por outra sessão. Bloqueio antigo também nomeado continua valendo à parte (captura de tela: google-chrome headless quebra nesta máquina, defeito conhecido da casa) — mas o achado novo de hoje é que o item inteiro nem está mesclado. |
| `L4-30-manual-e-tour-de-rede` | 4 | pendente | 0 |  | L4-04-d-diagrama-esquematico, L4-08-queda-de-tensao-e-carregamento | — |
| `L4-parcelas-03-ajuste-e-qualidade` | 4 | parcial | 2 | 8 | L4-parcelas-02-fluxos-cogo | trabalho completo (LSA com 3 bugs corrigidos e solução analítica como portão, camada de qualidade conferida no corpus de 11.473 lotes, suíte de 54 testes verde) existe em wt/il4parcelas, mas NÃO está em wt/lancamento — diverge 355 commits atrás / 45 à frente, E o ramo está CHECKED OUT agora por outra sessão (git worktree ativo em /home/dev/plataforma/enterprise/wt/il4parcelas ou equivalente) — mesclar hoje arriscaria colidir com trabalho em progresso de outro agente na mesma área. Trilha `entrega` estava FORA DO AR na medição de hoje. |

### L5 builder (63 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L5-01-a-layout-paginas` | 1 | entregue | 2 | 8 | — | — |
| `L5-01-b-widgets-mapa` | 1 | pendente | 1 | cx2 | L5-07-fontes-vistas-mensagens, L2-02-simbologia | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L5-01-c-widgets-dado` | 1 | parcial | 2 | 8 | L5-07-fontes-vistas-mensagens, L2-04-servicos-esri-ogc | tabela/gráfico/filtro/lista/consulta/seleção/info/adicionar dado sobre vista; camada consultada no servidor (where do CQL2, outStatistics, distintos, ids, exportação paginada); p95 113 ms por página com 100 mil feições; 5 agregações batem com SQL; filtro e seleção combinam por AND; edição no app fica para o L5-03; ramo contém wt/cx2l507 e wt/il204gogcap |
| `L5-01-e-acoes-configuraveis` | 1 | parcial | 2 | 8 | L5-07-fontes-vistas-mensagens | painel Acoes por widget (gatilho->alvo->acao->relacao/condicao, validacao nos dois lados: evento/alvo incompativel, gatilho repetido, referencia quebrada), acoes do usuario (exportar filtradas, ver na tabela, zoom, criar item), app do portao montado so pelo painel no e2e, 30 acoes em cadeia p95 0,47 ms; 'lista' = tabela das escolas (widget lista e do L5-01-c); tipo selecao ainda fora desta base |
| `L5-02-a-editor-de-nos` | 1 | pendente | 1 | plataforma-48 | L2-05-geoprocessamento, L3-01-motor-servico | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L5-02-b-execucao-proveniencia` | 1 | pendente | 0 |  | L5-02-a-editor-de-nos, L0-05-jobs | — |
| `L5-03-a-construtor-elementos` | 1 | pendente | 1 | plataforma-48 | L2-03-edicao, L2-07-campo | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L5-03-b-logica-condicional-calculo-restricao` | 1 | pendente | 0 |  | L5-03-a-construtor-elementos, L5-11-expressoes-no-navegador | — |
| `L5-05-documento-versoes` | 1 | entregue | 0 |  | — | — |
| `L5-06-motor-widgets` | 1 | parcial | 2 | 7 | — | motor de widgets pronto no ramo wt/cx506: 6 manifestos validados no make check, import() só dos citados (e2e mede 3 módulos), erro nomeado p/ tipo desconhecido/config inválida/módulo apagado, HTML inerte sem erro de console, chrome de edição no mesmo módulo; medidas gravadas; na fila de junção |
| `L5-07-fontes-vistas-mensagens` | 1 | parcial | 2 | 8 | L5-06-motor-widgets, L2-04-servicos-esri-ogc | esquema 3 do app (fontes/vistas/mensagens), validador Python+JS em paridade, barramento com corte de ciclo, widgets lendo vista, painel no construtor, estado na URL; e2e seleção->tabela/gráfico/2ª fonte; p95 1,4 ms com 10 mil feições; fonte de camada OGC só exercitável após L2-04; ramo contém wt/cx506 |
| `L5-08-editor-arrasto` | 1 | entregue | 1 | 3 | L5-06-motor-widgets | — |
| `L5-11-expressoes-no-navegador` | 1 | parcial | 2 | 8 | L2-10-relacoes-regras | Perfis (7), feicao e geometria na linguagem: 49 funcoes, 339+57+11 vetores identicos em Python e Node, corte por tempo nomeado nos dois lados, manual gerado do codigo; ligacao com tela fica para os itens de tela |
| `L5-14-publicacao-links-embed` | 1 | refutado | 2 | 9 | L1-02-tiles-token | adversario T9 L5-1: camadas_citadas so aceita familia camada; app com raster/mosaico recebe token sem tiles:ler:<raster_id>; xfail test_l5_adv1_publicacao_raster_fora_do_escopo.py |
| `L5-26-construtor-popup` | 1 | pendente | 1 | fable | L5-11-expressoes-no-navegador | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `UX-07-telas-do-construtor-e-aplicativo` | 1 | parcial | 1 | 8 | — | cx506+cx501d juntados; widgets plat-w-*; construtor com escolha/publicar/estados; /executar e /aplicativo com estados; e2e 3 widgets por arrasto → publica → abre; suítes L5 e do mapa verdes |
| `L5-01-app-builder` | 2 | pendente | 0 |  | L2-06-paineis, L2-02-simbologia, L0-14-identidade-visual | — |
| `L5-01-d-widgets-pagina-menu` | 2 | parcial | 2 | 8 | L5-06-motor-widgets | 12 widgets de página/menu sobre o motor do L5-06, desenhados pelo executor de páginas; 10 vetores XSS sem execução por e2e; iframe com sandbox + lista de domínios; QR local (/api/qr.svg); paridade escrita (doc EXB inacessível, lista do item); ramo wt/cx501d sobre master + wt/cx506 |
| `L5-01-f-modelos-app-galeria` | 2 | pendente | 0 |  | L5-01-b-widgets-mapa, L5-01-c-widgets-dado | — |
| `L5-02-c-agendamento-variaveis` | 2 | pendente | 0 |  | L5-02-b-execucao-proveniencia | — |
| `L5-02-d-exportar-python-importar-json` | 2 | pendente | 0 |  | L5-02-b-execucao-proveniencia, L7-08-sdk-api-webhooks | — |
| `L5-02-f-fluxo-como-ferramenta-e-api` | 2 | pendente | 0 |  | L5-02-b-execucao-proveniencia, L2-04-servicos-esri-ogc | — |
| `L5-02-fluxos` | 2 | pendente | 0 |  | L2-05-geoprocessamento, L3-01-motor-servico, L0-05-jobs | — |
| `L5-03-c-dominios-listas-cascata` | 2 | pendente | 0 |  | L5-03-a-construtor-elementos, L2-10-relacoes-regras | — |
| `L5-03-d-repeticoes-relacionadas-anexos` | 2 | pendente | 0 |  | L5-03-a-construtor-elementos, L2-10-relacoes-regras | — |
| `L5-03-e-xlsform-ida-e-volta-idiomas` | 2 | pendente | 0 |  | L5-03-b-logica-condicional-calculo-restricao, L5-03-c-dominios-listas-cascata | — |
| `L5-04-a-blocos-de-conteudo` | 2 | parcial | 2 | 8 | L5-14-publicacao-links-embed | narrativa por blocos: tipo narrativa + paleta no editor do L5-08 (11 blocos), leitor para /executar e /p/, mapa com vista salva (bbox+proporção, deriva 0,12 % em 5 mapas × 2 viewports), texto alternativo obrigatório no publish (422 com lista), publicado por link (L5-14) — e2e 4/4, API 4/4, unit 5/5; ramo junta il514public + cx501d; parcial: camadas do mapa na página anônima (escopo de tile por token, pendência L5-14/L1-02); consertos da linhagem do mapa (PUBLIC em funções de tile, teste do nginx, expurgo) |
| `L5-09-desfazer-refazer-rascunho` | 2 | entregue | 1 | 5 | — | — |
| `L5-10-temas-marca` | 2 | parcial | 2 | 8 | L5-06-motor-widgets, L0-07-admin-org | temas de marca completos: 6 padroes, tema de inquilino (GET /api/temas, PUT /api/org/tema) e tema por documento (esquema v3), editor /temas com arrasto/previa/contraste WCAG/exportar-importar, executor aplica cadeia sem recarrega (e2e 2/2), injecao recusada por formato; unit+api verdes por segmento (suite completa sofreu timeouts de carga com 4 trilhas em paralelo; 2 flakes fora do item: expressao L2-10-c ordem-dependente e lixeira/miniatura esperando job) |
| `L5-12-acessibilidade-i18n-construtores` | 2 | entregue | 1 | 5 | — | — |
| `L5-15-vista-movel-responsivo` | 2 | entregue | 1 | 5 | — | — |
| `L5-17-painel-elementos-avancados` | 2 | pendente | 1 | plataforma-48 | L2-06-paineis, L5-07-fontes-vistas-mensagens | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L5-18-painel-parametros-url-vistas` | 2 | pendente | 0 |  | L5-17-painel-elementos-avancados, L5-14-publicacao-links-embed | — |
| `L5-20-sites-paginas-publicas` | 2 | refutado | 3 | 9 | L5-14-publicacao-links-embed | adversario T9 L5-2: cartao_incorporado hardcoda sandbox allow-scripts+allow-same-origin+allow-popups (isolamento de mentira); xfail test_l5_adv2_site_iframe_sandbox_de_mentira.py |
| `L5-21-dados-abertos-catalogo-publico` | 2 | pendente | 1 | plataforma-48 | L5-20-sites-paginas-publicas, L0-09-metadado-catalogo, L6-01-acervo-casa | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L5-23-apps-instantaneos-motor-galeria` | 2 | pendente | 0 |  | L5-01-f-modelos-app-galeria, L5-14-publicacao-links-embed | — |
| `L5-24-apps-instantaneos-modelos-1` | 2 | pendente | 0 |  | L5-23-apps-instantaneos-motor-galeria, L2-11-geocodificacao-rota | — |
| `L5-27-simbologia-por-arrasto` | 2 | pendente | 1 | plataforma-48 | L2-02-simbologia | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L5-29-construtor-relatorio-pdf` | 2 | pendente | 0 |  | L5-26-construtor-popup, L2-12-impressao-layout | — |
| `L5-31-construtor-de-camada-esquema` | 2 | refutado | 2 | 9 | L0-04-ingest-vetor, L2-04-servicos-esri-ogc | adversario T9 L5-2: _avaliar_mudanca normaliza nome com set() novo por mudanca; duas mudancas que normalizam igual sao aceitas e aplicar estoura DuplicateColumn cru; xfail test_l5_adv2_esquema_colisao_normalizacao.py |
| `L5-33-a-diagrama-de-trabalho` | 2 | pendente | 0 |  | L5-02-a-editor-de-nos, L5-03-a-construtor-elementos, L5-11-expressoes-no-navegador | — |
| `L5-33-b-modelos-e-trabalhos` | 2 | pendente | 0 |  | L5-33-a-diagrama-de-trabalho, L7-08-sdk-api-webhooks | — |
| `L5-39-paridade-l5-e-manual` | 2 | pendente | 0 |  | L5-01-f-modelos-app-galeria, L5-02-f-fluxo-como-ferramenta-e-api, L5-03-e-xlsform-ida-e-volta-idiomas, L5-17-painel-elementos-avancados, L5-26-construtor-popup | — |
| `UX-31-fluxos-lacunas-1609` | 2 | pendente | 0 | 9 | UX-01-sistema-de-design | — |
| `L5-02-e-iteradores-condicionais` | 3 | pendente | 0 |  | L5-02-b-execucao-proveniencia, L5-11-expressoes-no-navegador | — |
| `L5-03-form-builder` | 3 | refutado | 2 | 9 | L2-03-edicao, L2-07-campo | adversario T9 L5-1: validar_atributos e validar_dados_livre tratam obrigatorio ausente so como None; string vazia passa; xfail test_l5_adv1_form_obrigatorio_string_vazia.py |
| `L5-04-b-imersivos-sidecar-tour-swipe` | 3 | pendente | 0 |  | L5-04-a-blocos-de-conteudo, L5-01-b-widgets-mapa | — |
| `L5-04-c-temas-capa-colecao` | 3 | parcial | 2 | 8 | L5-04-a-blocos-de-conteudo, L5-10-temas-marca | 4 de 5 cláusulas feitas (navegável, avisa+corrigir, og: só na pública, refutação do anônimo); tema PENDENTE por dependência L5-10 ausente de master; API 5/5 e e2e 1/1 verdes na trilha il504ctemas |
| `L5-13-edicao-concorrente` | 3 | refutado | 3 | 9 | L0-02-tenant-auth | adversario T9 L5-1: mesclagem.mesclar identifica ligacao pelo JSON inteiro; dois lados mudando a mesma ligacao viram duas adicoes sem conflito; xfail test_mesclagem_adversario.py |
| `L5-19-painel-expressoes-de-dado-tempo-real` | 3 | pendente | 0 |  | L5-17-painel-elementos-avancados, L2-14-tempo-real, L5-11-expressoes-no-navegador | — |
| `L5-22-sites-dominio-proprio-tema` | 3 | pendente | 1 | plataforma-48 | L5-20-sites-paginas-publicas, L7-01-instalador-limpo | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L5-25-apps-instantaneos-modelos-2` | 3 | pendente | 0 |  | L5-23-apps-instantaneos-motor-galeria, L1-04-serie-temporal, L2-03-edicao | — |
| `L5-28-galeria-simbolos-rampas-estilos` | 3 | pendente | 0 |  | L5-27-simbologia-por-arrasto | — |
| `L5-30-relatorio-lote-agendado` | 3 | pendente | 0 |  | L5-29-construtor-relatorio-pdf, L5-02-c-agendamento-variaveis | — |
| `L5-32-vistas-de-camada` | 3 | parcial | 2 | 8 | L5-31-construtor-de-camada-esquema | Vista de camada como VIEW PostgreSQL com security_invoker: filtro congelado, campos ocultos ausentes da relacao, 403 em vista so leitura, compartilhamento publico nao expoe a mae; e2e da tela escrito mas nao executavel na trilha |
| `L5-33-c-atribuicao-avancada-indicadores` | 3 | pendente | 0 |  | L5-33-b-modelos-e-trabalhos, L2-06-paineis | — |
| `L5-34-captura-rapida-designer-pwa` | 3 | pendente | 0 |  | L2-07-campo, L2-14-tempo-real | — |
| `L5-36-widgets-personalizados-sdk` | 3 | parcial | 2 | 8 | L5-06-motor-widgets, L5-07-fontes-vistas-mensagens, L0-07-admin-org | Construído e testado na trilha plat_til536widget: migração+API+front (carregador com re-conferência sha256 via crypto.subtle, sandbox iframe+CSP, modo normal por blob) + pacote de exemplo + empacotador + ADR + manual + 15 testes unit/API/eventos verdes + 3 e2e no chromium verdes + medida FCP 2412 ms com contexto da máquina (carga 5,3). Ressalvas: dependência L0-07 sem ramo — widget externo vive em tabela plat.widget_externo com RLS e API (não em web/ext/ no disco, que não passaria por log de acesso nem RLS), adaptação na junção; blob não resolve especificador raiz-relativo, o carregador reescreve '/static/' para absoluto no texto verificado; cronômetro do manual com testador humano ainda não correu; openapi regenerado varreu rotas de ramos mesclados que estavam atrasadas. |
| `L5-37-pacotes-modelos-entre-inquilinos` | 3 | refutado | 3 | 9 | L5-14-publicacao-links-embed | adversario T9 L5-2: _Saneador incrementa em starttag e so decrementa em endtag; tag autofechada apaga todo o texto seguinte (confirmado pela API); xfail test_l5_adv2_pacote_sanitizador_perde_conteudo.py |
| `L5-04-storymap` | 4 | pendente | 0 |  | — | — |
| `L5-16-agente-escreve-configuracao` | 4 | pendente | 1 | plataforma-48 | L5-01-app-builder | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L5-35-missao-operacao-ao-vivo` | 4 | pendente | 0 |  | L5-34-captura-rapida-designer-pwa, L2-14-tempo-real, L5-33-b-modelos-e-trabalhos | — |
| `L5-38-importadores-configuracao-esri` | 4 | pendente | 0 |  | L5-26-construtor-popup, L5-27-simbologia-por-arrasto, L5-17-painel-elementos-avancados, L2-08-migracao-agol | — |

### L6 conectores (32 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L6-01-a-registro` | 1 | refutado | 2 | 9 | — | adversario T9 L6: _COLUNA_NEGADA e match exato; cpf_titular/nr_cpf/proprietario_nome saem expostas; xfail test_advl6_linha_l6_conectores.py |
| `L6-01-b-view-so-leitura` | 1 | parcial | 1 | 3 | L6-01-a-registro, L0-02-tenant-auth | Publicacao sem copia ENTREGUE e medida: view definer em plat_acervo com lista branca, porteiro plat.acervo_pode_ler no WHERE, GRANT SELECT so da view a plat_app (papel dono plat_acervo_publicador). 17 testes passam. Provado PELO BANCO com a role da aplicacao: SELECT direto em public.car_area_imovel negado, INSERT/UPDATE/DELETE na view negados, ACL da view = {SELECT}, varredura pg_class/aclexplode = zero GRANT de public a plat_app. Sem assinatura: 403 na API, 0 linha na view, One-Time Filter com o no do indice (never executed). Consulta de mapa 1,534 ms (portao pede <=100 ms) sobre 8.406.837 linhas por COUNT(*) exato -- o '7,36 mi' do portao e reltuples, as duas medidas estao gravadas. REFUTADO por medicao (ADR 0018): SECURITY INVOKER e incompativel com 'nenhum GRANT direto a plat_app' (o banco recusa) e security_barrier derruba o indice GiST (Seq Scan, 2min10s x 1,5ms) porque && nao e LEAKPROOF. PENDENTE por dependencia inexistente: Martin (porta 8151 reservada, servico ausente), FeatureServer/OGC API de feicao (L2-04) e 'e2e adiciona ao mapa' (L2-01-mapa-web). Nota: no registro vivo a fonte do CAR esta sem licenca escrita, entao em producao o publicador ainda nao a publicaria (D17, depende de L6-01-g). |
| `L6-01-f-lgpd` | 1 | refutado | 2 | 9 | L6-01-a-registro | adversario T9 L6: scanner automatico de conteudo (regex CPF/CNPJ no make check) nunca construido; xfail test_advl6_linha_l6_conectores.py |
| `L6-01-g-licenca-curada` | 1 | parcial | 2 | 3 | L6-01-a-registro | 29/40 fontes confirmadas (ver decisoes_do_dono D39); gap = orgaos sem portal CKAN/DCAT vivo ou so rodape generico gov.br |
| `L6-02-a-modelo-conexao-e-seguranca` | 1 | entregue | 4 | 3 | — | — |
| `L6-01-acervo-casa` | 2 | pendente | 0 |  | — | — |
| `L6-01-c-tela-acervo` | 2 | refutado | 2 | 8 | L6-01-b-view-so-leitura | artefato ausente em master (auditoria HARD-03 07/09): sem página/JS de tela do acervo em web/ (só API app/acervo) |
| `L6-01-d-ficha-fonte` | 2 | parcial | 1 | 3 | L6-01-a-registro | backend completo e evidenciado: os 10 campos de procedencia ja existiam (item anterior); somados endpoints confirmados/vivos (plat.acervo_endpoint, migracao 040) e completude_texto x/10; 14 testes em tests/api/test_acervo.py incl. 20 fontes campo a campo + campo ausente nunca fabricado. PENDENTE: tela/e2e (L6-01-c, papel frontend nao executado nesta passagem) e adversario independente. |
| `L6-01-e-assinatura-e-uso` | 2 | refutado | 2 | 8 | L6-01-b-view-so-leitura | artefato ausente em master (auditoria HARD-03 07/09): sem rota/coluna de assinatura+uso do acervo em master |
| `L6-02-b-wms-wmts` | 2 | refutado | 2 | 8 | — | artefato ausente em master (auditoria HARD-03 07/09): sem rota/adaptador WMS-WMTS em app (só nome de tipo em proveniencia) |
| `L6-02-c-wfs-ogcapi` | 2 | entregue | 3 | 3 | — | — |
| `L6-02-d-arcgis-rest-externo` | 2 | refutado | 2 | 8 | — | artefato ausente em master (auditoria HARD-03 07/09): arcgis só no geocodificador; sem adaptador de fonte externa |
| `L6-02-g-pmtiles-xyz-tilejson` | 2 | refutado | 2 | 8 | — | artefato ausente em master (auditoria HARD-03 07/09): sem rota de tiles de conexão (basemap PMTiles é outro item) |
| `L6-02-h-csv-url-geojson-kml` | 2 | refutado | 2 | 8 | L0-04-ingest-vetor | artefato ausente em master (auditoria HARD-03 07/09): sem adaptador de conexão CSV/GeoJSON/KML em app |
| `L6-02-k-agendamento` | 2 | refutado | 2 | 9 | L0-05-jobs | adversario T9 L6: corrida checar-e-agir no teto de agendas por usuario (2 ativas contra cota 1, reproduzido com 2 conexoes); xfail test_advl6_linha_l6_conectores.py |
| `L6-02-m-catalogo-endpoints-brasil` | 2 | parcial | 2 | 8 | L6-02-b-wms-wmts, L6-02-d-arcgis-rest-externo | catálogo de conectores públicos: plat.endpoint_publico + job retestar semanal (vivo = assinatura do protocolo, 200 com HTML = morto) + /api/endpoints-publicos e adicionar num clique + tela; medido 78 verdes de 100 (script + medidas), e2e adicionou 10 pela tela, morto vai para fora do ar |
| `L6-03-paridade-conectores` | 2 | parcial | 3 | 8 | L6-02-m-catalogo-endpoints-brasil | cláusula fechada — adversário conferiu as linhas e provou 2 falsas: "armazém em nuvem" e "NoSQL" diziam fora(decisão) sem decisão nenhuma no registro (D18-D41 não falam disso; L3L6_CONCEITO não tem seção 14) e STAC citava teste em ramo wt/stac sem o arquivo. Corrigido: declaração honesta "nenhum item do backlog pede; nenhuma decisão do dono cobre", pasta fora(L7-11), citação STAC em wt/il101apgsta (conferida por git cat-file); guard endurecido para cobrir exatamente essa mentira (fora exige item/decisão/"nenhum item"; todo tests/ citado em qualquer célula existe em master ou no ramo da linha); 36 passed. 9 linhas não reproduzíveis pelo adversário por falta de .env nos outros ramos — não é falha de linha. |
| `L6-04-acervo-no-motor` | 2 | refutado | 2 | 8 | L6-01-b-view-so-leitura, L3-01-c-extracao-fator | artefato ausente em master (auditoria HARD-03 07/09): sem integração acervo->AMC em app/amc de master |
| `L6-01-a-procedencia-acervo` | 3 | entregue | 0 |  | — | — |
| `L6-01-h-frescor-verificacao` | 3 | entregue | 1 | 3 | L6-01-a-registro, L0-05-jobs | — |
| `L6-01-i-raster-e-arquivos` | 3 | parcial | 2 | 8 | L1-02-tiles-token, L6-01-a-registro | acervo de ARQUIVO no catálogo: vista plat.acervo_arquivo (321 arquivos, 26 raster, 100% com sha256), job acervo.expor_arquivo com sha256 conferido antes de ingerir, raster por referência servindo ladrilho por token (0 byte copiado), vetor ingerido uma vez para PostGIS; 10 rasters e 30 arquivos expostos, ladrilho em 3.156 ms; guardrail 2 GB por arquivo e 3 GB por lote (D21); refutação de 1 bit recusa por hash sem criar item; ⚠ nenhuma das 27 fontes de arquivo tem licença escrita (D17) — item nasce privado e uso_restrito |
| `L6-02-conectores-vivos` | 3 | parcial | 1 | 8 | — | mecanismo completo (cadastro por URL, descoberta wms/wmts/wfs/ogc_api/esri_rest com nome/titulo/crs/extensao, plat.conexao_camada com RLS, proxy de tile wms/wmts/esri_rest, tela com formulario+ficha de camadas+preview) e provado ao vivo (GeoSampa WMS: 8 camadas descobertas, tile 82-730KB real pelo proxy, e2e playwright 0 erro de console); falta ligar a camada ao MapLibre de verdade (web/js/mapa/mapa.js, arquivo de outra trilha nesta rodada) e testar contra ANA/ANM (só IBGE+GeoSampa provados ao vivo) |
| `L6-02-e-stac-externo` | 3 | pendente | 0 |  | L1-03-conectores-sensores | — |
| `L6-02-f-geoparquet-duckdb` | 3 | pendente | 1 | plataforma-48 | L2-15-analitica-grande | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L6-02-i-google-sheets` | 3 | parcial | 2 | 8 | L6-02-h-csv-url-geojson-kml | CLAUSULA FECHADA (aguarda fila): rodada completa 100% verde de tests/api/conexao/test_google_sheets.py — 8 passed em DUAS rodadas consecutivas na trilha il602igoogl (19,6 s e 230,9 s; carga 3,5), as 5 cláusulas do bloqueio agora na mesma corrida. A contenção de banco nomeada no bloqueio não era carga de máquina: era corrida real em plat.camada_schema_garantir (CREATE SCHEMA + GRANT concorrentes na 1ª carga do mesmo inquilino com worker de 2 processos → tuple concurrently updated); consertada com pg_advisory_xact_lock por slug na migração 20260908T2210 (commits 65f23637/cf8367c0 no ramo wt/il602igoogl). Observação de ambiente: o .env da trilha precisa de PLAT_GIT_SHA exportado (o versao.py do worker em subprocesso recusa subir sem ele). |
| `L6-02-j-bancos-externos` | 3 | refutado | 5 | 9 | — | adversario T9 L6: whitelist de tabela so olha FROM/JOIN; funcao na projecao passa; pg_ls_logdir/waldir fora do denylist; xfail test_advl6_linha_l6_conectores.py |
| `L6-02-l-saude` | 3 | parcial | 0 |  | — | mecanismo completo: historico plat.conexao_saude_historico, estado_saude agregado (ok/degradado/fora/nunca_testada), periodico de 15 min reteste todas as conexoes, tela /conexoes com selo vivo e 'testar agora'; falta so 'mapa mostra aviso' - nenhum conector desenha camada externa no mapa ainda (depende de L6-02-b+), entao nao ha onde avisar |
| `L6-02-n-etl-na-entrada` | 3 | pendente | 0 |  | L6-02-k-agendamento, L5-02-fluxos | — |
| `L6-02-o-importacao-exportacao-formatos` | 3 | parcial | 1 | 7 | L0-04-ingest-vetor | Exportacao em lote entregue e provada: 4 formatos novos (geojsonseq, filegdb.zip, mbtiles, pmtiles) sobre os 11 do L0-04-h, escrow do inquilino (20 camadas em 5,66 s sob carga 14,7) e avisos de fidelidade antes de gerar; refutacao do adversario (campo >10 chars + data no shapefile) passa. PARCIAL por duas razoes escritas: (1) 'FileGDB abre no QGIS' provado pelo driver OpenFileGDB que o QGIS delega ao GDAL, nao pelo aplicativo (nao ha QGIS na maquina); (2) a IMPORTACAO nao ganhou formato novo - o lote repete os 4 conversores do L0-04; KML/XLSX/FileGDB/CAD de entrada sao dos itens L0-04-e e L0-04-f. 31 testes do item verdes, tests/api/exportacao 22/22 sem regressao. |
| `L6-05-proveniencia-camada-externa` | 3 | refutado | 1 | 9 | — | adversario T9 L6: STAC nunca cai para links[].rel==license; xfail test_advl6_linha_l6_conectores.py |
| `L6-01-j-multi-servidor` | 4 | refutado | 2 | 8 | L6-01-a-registro | artefato ausente em master (auditoria HARD-03 07/09): sem implementação multi-servidor em app/acervo de master |
| `L6-06-descoberta-csw` | 4 | parcial | 2 | 8 | L6-02-b-wms-wmts | descoberta CSW 2.0.2: /api/csw/buscar (texto+bbox, ISO 19139 por GET KVP) e /api/csw/conexoes (1 clique -> conexão WMS/WFS/WMTS com ficha do ISO; sem serviço ligado = 422); tela /conexoes; medido na INDE: 52 registros, 2 conexões, saúde 2/2; estaduais não verificados |

### L7 operação (82 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `HARD-01-varredura-de-seguranca-continua` | 1 | parcial | 2 | 8 | — | make seguranca (bandit+pip-audit+npm+gitleaks+trivy) em make check, ZAP baseline em seguranca-zap, exceções com prazo, doc gerado; CSP/XFO/server_tokens no nginx; ZAP fora do check (precisa trilha) |
| `HARD-02-testes-de-carga-e-caos` | 1 | parcial | 2 | 8 | — | cláusula caos de processo de trilha fechada (4d5db42a): worker de trilha morto no meio é ceifado pelo worker novo (reinicios=1, retoma, cancela limpo) e API de trilha morta no meio não perde o job nem a sessão (mesmo cookie, reinicios=0, cancela pela API nova); 2 passed em 95,1 s e 94,3 s na trilha l02caos. Falta: p95 por rota (medir pós-parada da superfície) e caos de banco (wt/cx4h08, na fila) |
| `HARD-03-adversario-por-linha-em-lote` | 1 | refutado | 6 | 9 | — | adversario T9 L7-2: 5 itens ficaram entregues por turnos sem laudo adversarial previo; audita_ramo.sh nao confere ambiente-de-prova x producao; xfail test_l7_adv2_hard03_entregue_sem_laudo_previo.py |
| `L7-01-d-instalador-extensoes` | 1 | parcial | 2 | 8 | — | db/extensoes.txt com as 4 extensoes; install.sh, laco/trilha_ambiente.sh e app/backup/drill.py leem o mesmo arquivo e conferem em pg_extension; base so com PostGIS termina com as 4 e o dump restaura nela com a tabela item; sem unaccent a tabela item nao nasce e a conferencia reprova nomeando a extensao. install.sh inteiro nao e rodado por teste (grava em /etc/plat e mexe em unidade de producao). |
| `L7-19-b-journal-sem-segredo` | 1 | pendente | 0 |  | L7-19-segredos-e-certificados | depende de D41 (purga destrutiva do journal e rotacao global que derruba trilhas — decisao do dono) |
| `L7-31-a-segredos-trilha` | 1 | pendente | 0 |  | — | — |
| `L7-01-a-compose-perfis` | 2 | refutado | 2 | 9 | — | adversario T9 L7-1: docker-compose appliance tem healthcheck em 1 de 7 servicos; xfail |
| `L7-01-b-instalacao-conteiner-limpo` | 2 | pendente | 2 | 8 | L7-01-a-compose-perfis | não construível nesta máquina agora: a prova em contêiner Ubuntu 24.04 exige systemd privilegiado + postgresql-16-postgis + nginx + venv + chromium do playwright (imagem >3 GB, acima do teto D21 com disco a 93 %) e install.sh termina com certbot --nginx e conferência https://<dominio>/saude, que exigem domínio público com DNS (impossível dentro do contêiner sem mudar o instalador). As duas quebras do adversário T1 já estão corrigidas em master (PYTHONNOUSERSITE=1 em todo Python do install.sh linhas 33-36; senha por stdin linha 261) e o nginx -t antes de trocar sites-enabled também (escrever_nginx, 385-407). Falta só a prova em contêiner + docs/INSTALACAO.md: refazer quando D21 liberar disco e o instalador ganhar um modo sem certbot. |
| `L7-01-instalador-limpo` | 2 | pendente | 0 |  | L2-04-servicos-esri-ogc, L1-02-tiles-token | — |
| `L7-03-a-antivirus-upload` | 2 | refutado | 3 | 9 | L0-04-ingest-vetor, L2-03-edicao | adversario T9 L7-1: endereco_clamd inexistente, SVG/HTML banidos em vez de sanitizados, sem politica por rota (tests/seguranca/test_upload.py 8/9); xfail |
| `L7-03-b-rate-limit-abuso` | 2 | parcial | 1 | 5 | L0-02-tenant-auth, L1-02-tiles-token | Camadas 1 (nginx por IP) e 3 (fail2ban, jail dedicada) provadas com pedidos reais, na porta direta e via nginx; camada 2 (Postgres por inquilino) provada com testes automatizados + refutação (50 IPs x 1 token; 1 IP x 50 tokens); X-Forwarded-For forjado provado imune (herda --forwarded-allow-ips já existente). Adversário independente achou corrida real em plat.limite_taxa_verificar sob concorrência (SELECT count + INSERT sem trava) -- CORRIGIDA nesta mesma passagem com pg_advisory_xact_lock, reprovada com 5 rodadas de 200 chamadas concorrentes, 0 furos. Cláusula 'tile acima do limite do plano devolve 429' fica parcial: não existe rota HTTP de ladrilho nesta base (L1-02-tiles-token entregue mas não mesclado, app/imagens/ ausente); a zona de borda plat_tiles já protege /tiles/ mesmo sem a rota e o mecanismo da camada 2 já suporta o escopo tiles (testado direto na função SQL) -- falta só a fiação na rota real quando aquele ramo mesclar. |
| `L7-03-c-ssrf-conectores` | 2 | pendente | 1 | plataforma-48 | L6-02-conectores-vivos | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L7-03-d-injecao-consulta` | 2 | parcial | 2 | 8 | L2-04-servicos-esri-ogc | 180 payloads (where/outFields/orderBy/groupBy/outStatistics/having/objectIds/OGC) contra camada real: 0 5xx, 8 ms máx, canário intacto; estático por AST + bandit B608 fixado; 2 defeitos de 500 corrigidos em motor.py (_executar). Ramo inclui merge de wt/esriogc (dependência na fila). ZAP baseline não rodou (sem imagem, disco 94 %, D21) |
| `L7-03-e-cabecalhos-csp-tls` | 2 | refutado | 3 | 9 | — | adversario T9 L7-1: Referrer-Policy duplicado, Permissions-Policy conflitante nginx x app, unsafe-inline em /entrar, security.txt Contact vazio; xfail |
| `L7-03-f-dependencias-cve-log-correcoes` | 2 | refutado | 2 | 3 | — | sem plat.vulnerabilidade, sem docs/CORRECOES.md, sem timer, sem /status e fora do make check; osv-scanner, trivy e gitleaks ausentes; a refutacao do item nao tem relogio para cronometrar |
| `L7-03-seguranca` | 2 | refutado | 1 | 9 | L2-04-servicos-esri-ogc | adversario T9 L7-1: queryAttachments do FeatureServer -> 500 (escopo nunca conferido; _autenticar 2 args vs 17 chamadores com 3 args em rotas_edicao_esri/rotas_sync_esri/versionamento) ; xfail tests/api/adversario/test_l7_adv1_* |
| `L7-06-a-metricas-exporters` | 2 | refutado | 2 | 9 | L0-05-jobs, L1-02-tiles-token | adversario T9 L7-1: registrar_requisicao/registrar_tile/registrar_job_processado sem chamador; /metrics sem plat_http_requests_total apos trafego; xfail |
| `L7-06-b-alertas` | 2 | refutado | 2 | 9 | L7-06-a-metricas-exporters | adversario T9 L7-1: regra de alerta de 5xx nunca dispara (metrica nunca alimentada); xfail |
| `L7-06-c-logs-consulta-req-id` | 2 | refutado | 2 | 9 | L7-06-a-metricas-exporters | adversario T9 L7-2: fonte nginx da juncao de logs e fantasma (tag journal plat_nginx nunca configurada) e token de servico completo cai em texto claro no log_format de producao; xfail test_l7_adv2_logs_nginx_fonte_fantasma.py |
| `L7-06-observabilidade` | 2 | pendente | 0 |  | L0-06-backup-status | — |
| `L7-15-processo-release` | 2 | refutado | 1 | 3 | L7-31-ambiente-homologacao, L7-16-assinatura-pacote | PLAT_RELEASE_CHECK_CMD/HOMOLOG_CMD produzem pacote com manifesto 'passou' sem rodar nada e publicar_release.sh aprova; PLAT_VERIFICAR_SCRIPT desliga a verificacao; etiqueta nao assinada; regressao e repeticao de versao aprovadas |
| `L7-16-assinatura-pacote` | 2 | refutado | 1 | 3 | — | ferramenta de assinatura grava a propria chave publica no arquivo de confianca do verificador: pacote forjado aceito no caminho padrao; PLAT_CHAVES_CONFIAVEIS troca a lista; .sig nao amarra nome/versao/validade |
| `L7-19-segredos-e-certificados` | 2 | refutado | 3 | 9 | — | adversario T9 L7-1: rpc_secret/admin_token do Garage em claro no garage.toml de producao, fora do LoadCredential e da rotacao; xfail tests/api/adversario/test_l7_adv1_* |
| `L7-20-trilha-auditoria` | 2 | entregue | 1 | 3 | L0-02-tenant-auth | — |
| `L7-31-ambiente-homologacao` | 2 | refutado | 1 | 3 | — | PLAT_GARAGE_ADMIN_TOKEN identico ao de producao (sha256 igual) enumera e administra buckets plat-*; schemas de dado d_<slug> compartilhados; executemany/bytes escapam da reescrita; sem install.sh --ambiente, sem AMBIENTES.md, sem unidade e sem MemoryPeak |
| `L7-33-modo-somente-leitura` | 2 | refutado | 2 | 8 | L0-02-tenant-auth, L0-05-jobs | artefato ausente em master (auditoria HARD-03 07/09): 0 plat.sistema/modo_somente_leitura; 'somente_leitura' é cursor RO, não modo global |
| `L7-34-saude-profunda` | 2 | refutado | 2 | 8 | L0-05-jobs, L1-02-tiles-token | artefato ausente em master (auditoria HARD-03 07/09): rota /saude/profunda inexistente em master |
| `L7-35-atualizacao-versao-assinada` | 2 | pendente | 0 |  | L7-15-processo-release, L7-16-assinatura-pacote, L7-33-modo-somente-leitura, L0-06-backup-status | — |
| `D21 (dono)` | 3 | pendente | 0 |  | — | — |
| `L7-01-c-dado-demonstracao` | 3 | refutado | 2 | 8 | L0-04-ingest-vetor | artefato ausente em master (auditoria HARD-03 07/09): 0 plat demo/demo_semear/dado_demonstracao em master |
| `L7-02-a-k6-cenarios` | 3 | pendente | 0 |  | L7-31-ambiente-homologacao, L2-04-servicos-esri-ogc, L1-02-tiles-token | — |
| `L7-02-b-pool-e-limites-por-inquilino` | 3 | pendente | 0 |  | L7-02-a-k6-cenarios | — |
| `L7-02-carga` | 3 | pendente | 0 |  | L7-01-instalador-limpo | — |
| `L7-03-g-asvs-nivel2-pentest` | 3 | pendente | 0 |  | L7-03-e-cabecalhos-csp-tls, L7-03-b-rate-limit-abuso, L7-03-c-ssrf-conectores, L7-03-d-injecao-consulta, L7-03-a-antivirus-upload, L7-03-f-dependencias-cve-log-correcoes, L7-19-segredos-e-certificados | — |
| `L7-04-a-manual-capturas-geradas` | 3 | refutado | 3 | 9 | L5-01-app-builder | adversario T9 L7-2: make manual (comando do portao) nao existe no Makefile; xfail test_l7_adv2_make_manual_e_videos_ausentes.py |
| `L7-04-b-tour-primeiro-acesso` | 3 | pendente | 0 |  | L7-10-a-i18n-pt-en-es | — |
| `L7-04-c-manual-admin-runbooks` | 3 | pendente | 0 |  | L7-35-atualizacao-versao-assinada, L7-24-drill-restauracao, L7-07-c-ensaio-failover, L7-19-segredos-e-certificados | — |
| `L7-04-manual-e-tour` | 3 | pendente | 0 |  | L5-01-app-builder | — |
| `L7-06-d-paineis` | 3 | refutado | 2 | 9 | L7-06-a-metricas-exporters | adversario T9 L7-2: painel Visao geral consulta plat_http_requests_total/plat_jobs_processados_total que nunca ganham serie; xfail test_l7_adv2_paineis_dependem_de_metrica_sem_serie.py |
| `L7-07-a-replica-postgres` | 3 | pendente | 0 |  | L7-23-pgbackrest-pitr | — |
| `L7-07-alta-disponibilidade` | 3 | pendente | 0 |  | L7-01-instalador-limpo, L0-06-backup-status | — |
| `L7-07-b-replica-garage` | 3 | parcial | 2 | 8 | L7-01-a-compose-perfis | cluster de 3 nós rf=3 (binário local, segredos em arquivo, zonas): 1.000 objetos com nó parado → resync 5,2 s, scrub 0 erros, blocos em disco iguais, 1.000 sha256 conferidos com o nó escritor desligado; 256 MiB em 4,7 s; 2 nós rf=2 = leitura sim, escrita 503 por quórum (medido); runbook + timer de scrub. Fora: 10 GB (D21), 2 contêineres docker (processos locais), homologação |
| `L7-07-c-ensaio-failover` | 3 | pendente | 0 |  | L7-07-a-replica-postgres, L7-07-b-replica-garage, L7-33-modo-somente-leitura, L7-26-cdn-tiles | — |
| `L7-08-a-webhooks-eventos` | 3 | pendente | 0 |  | L0-10-eventos-historico, L0-05-jobs, L7-03-c-ssrf-conectores | — |
| `L7-08-b-sdk-python` | 3 | refutado | 2 | 8 | L2-04-servicos-esri-ogc, L7-08-d-portal-api-chaves | artefato ausente em master (auditoria HARD-03 07/09): só no ramo wt/il708bsdkpy; nenhum arquivo sdk em master |
| `L7-08-c-sdk-js` | 3 | parcial | 2 | 8 | L7-08-b-sdk-python | SDK JS (ES module só fetch, mesmo modelo do Python) + ajudantes MapLibre (fonte/camada/estilo/catalogo/transformRequest/enquadrar) + 10 exemplos HTML com CSP default-src 'none' que são o e2e (13 verdes no Chromium, 0 violação de CSP, token revogado com a mensagem exata) + 13 testes Node; paridade contra o ArcGIS Maps SDK for JavaScript; feições por camada/tiles dinâmicos ficam para o L2-04 |
| `L7-08-d-portal-api-chaves` | 3 | refutado | 2 | 8 | L0-02-tenant-auth | artefato ausente em master (auditoria HARD-03 07/09): sem página de portal/API em web/ de master |
| `L7-08-sdk-api-webhooks` | 3 | pendente | 0 |  | L2-04-servicos-esri-ogc | — |
| `L7-09-a-medidor-diario` | 3 | pendente | 1 | plataforma-48 | L0-07-admin-org, L1-02-tiles-token, L0-05-jobs | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L7-09-b-planos-limites-relatorio` | 3 | pendente | 0 |  | L7-09-a-medidor-diario, L0-07-admin-org | — |
| `L7-09-medicao-cobranca` | 3 | pendente | 0 |  | L0-07-admin-org, L1-02-tiles-token | — |
| `L7-10-a-i18n-pt-en-es` | 3 | pendente | 1 | plataforma-48 | L5-01-app-builder, L0-07-admin-org | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L7-10-b-acessibilidade-wcag21aa` | 3 | pendente | 1 | plataforma-48 | L5-01-app-builder | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L7-10-i18n-acessibilidade` | 3 | pendente | 0 |  | L5-01-app-builder, L0-14-identidade-visual | — |
| `L7-12-a-classificacao-retencao` | 3 | pendente | 0 |  | L0-03-h-lixeira-protecao-status, L7-26-cdn-tiles | — |
| `L7-12-b-registro-tratamento-dpa-incidente` | 3 | pendente | 0 |  | L7-12-a-classificacao-retencao, L7-22-sla-e-incidentes, L7-27-origem-br-soberania | — |
| `L7-12-lgpd-governanca` | 3 | pendente | 0 |  | L0-07-admin-org | — |
| `L7-14-instalacoes-apt-desta-linha` | 3 | refutado | 1 | 3 | — | portao ainda e texto de espera e o item esta entregue; a lista fechada nao cobre nginx/certbot/openssl/curl/postgresql-client que install.sh exige; caminho apt-get nunca exercitado |
| `L7-17-capacidade-planejamento` | 3 | pendente | 0 |  | L7-09-a-medidor-diario, L7-06-d-paineis | — |
| `L7-18-custo-por-inquilino` | 3 | pendente | 0 |  | L7-09-a-medidor-diario | — |
| `L7-21-pagina-status` | 3 | pendente | 0 |  | L0-06-e-status, L7-34-saude-profunda, L7-06-a-metricas-exporters, L7-24-drill-restauracao | — |
| `L7-22-sla-e-incidentes` | 3 | pendente | 0 |  | L7-07-c-ensaio-failover, L7-23-pgbackrest-pitr, L7-21-pagina-status | — |
| `L7-23-pgbackrest-pitr` | 3 | pendente | 0 |  | L7-31-ambiente-homologacao, L7-01-a-compose-perfis | — |
| `L7-24-drill-restauracao` | 3 | pendente | 0 |  | L0-06-backup-status, L7-23-pgbackrest-pitr | — |
| `L7-25-exportacao-inquilino` | 3 | pendente | 1 | plataforma-48 | L0-06-d-exportar-inquilino, L0-05-jobs, L2-08-migracao-agol | reivindicado em 08/09 por sessao que morreu; devolvido a fila em 2026-09-17T21:48:25Z |
| `L7-26-cdn-tiles` | 3 | refutado | 2 | 8 | L1-02-tiles-token | artefato ausente em master (auditoria HARD-03 07/09): docs/CDN.md inexistente em master |
| `L7-27-origem-br-soberania` | 3 | pendente | 0 |  | L7-26-cdn-tiles, L7-23-pgbackrest-pitr, L7-12-a-classificacao-retencao | — |
| `L7-29-roteiro-demonstracao` | 3 | refutado | 3 | 9 | L7-01-c-dado-demonstracao, L3-01-motor-servico, L4-02-tracado, L5-01-app-builder, L6-01-acervo-casa | adversario T9 L7-2: docs/DEMO.md lista o proprio item como nao entregue; dependencia L7-01-c refutada; xfail test_l7_adv2_demo_se_declara_nao_entregue.py |
| `L7-30-teste-parceiro-pro-agol` | 3 | pendente | 0 |  | L2-04-servicos-esri-ogc, L1-02-tiles-token, L7-08-d-portal-api-chaves | D20: credencial AGOL/Portal e agenda do parceiro (decisão do dono) |
| `L7-03-b-antivirus-anexos` | 4 | refutado | 2 | 3 | — | polyglot GIF/JPEG/PNG + script aceito (o docstring afirma o contrario); qualquer Content-Type fora de TIPOS_PERMITIDOS desliga a varredura e o GET devolve com esse mesmo tipo; so 8 KiB examinados; zip nao aberto |
| `L7-04-d-videos-por-tarefa` | 4 | refutado | 3 | 9 | L7-04-a-manual-capturas-geradas | adversario T9 L7-2: make videos ausente; roteiro confere contra MANUAL.md escrito a mao; xfail test_l7_adv2_make_manual_e_videos_ausentes.py |
| `L7-05-producao-final` | 4 | pendente | 0 |  | D21 (dono), L0-02-e-varredura-cruzada-rls, L0-02-tenant-auth, L0-03-e-compartilhamento, L0-03-f-tela-conteudo, L0-03-h-lixeira-protecao-status, L0-03-j-transferencia-dono, L0-03-k-favoritos-notificacoes, L0-03-l-versoes-item, L0-04-a-upload-arquivo, L0-04-b-inspecao, L0-04-c-tabela-camada, L0-04-d-formatos-base, L0-04-f-fgdb-parquet-fgb-gml, L0-04-g-atualizar-dados, L0-04-ingest-vetor, L0-04-j-camada-vista, L0-05-a-fila-postgres, L0-05-b-progresso-cancelamento, L0-05-c-tela-tarefas, L0-05-e-worker-em-container, L0-05-jobs, L0-06-b-pitr-pgbackrest, L0-06-backup-status, L0-06-c-restore-drill, L0-06-d-exportar-inquilino, L0-06-e-status, L0-07-a-configuracoes-org, L0-07-admin-org, L0-07-c-cotas-uso, L0-07-e-relatorios, L0-07-f-console-plataforma, L0-08-a-oidc, L0-08-b-saml, L0-08-c-govbr, L0-08-d-ldap, L0-08-e-mapeamento-provisionamento, L0-08-sso, L0-09-a-procedencia, L0-09-b-editor-iso-mgb, L0-09-c-xml-iso-validacao, L0-09-d-ogc-records-csw, L0-09-metadado-catalogo, L0-10-eventos-historico, L0-11-arquivos-objetos, L0-12-contrato-api-e-limites, L0-13-dado-demonstracao, L0-14-cli-admin, L1-01-b-validacao-e-isolamento-da-entrada, L1-01-c-conversao-cog-perfis-miniatura-estatisticas, L1-01-e-upload-grande-retomavel, L1-01-f-formatos-de-entrada, L1-01-g-raster-categorico-colormap-e-tabela-de-atributos, L1-01-h-ingestao-em-lote-por-manifesto-e-cli, L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo, L1-02-a-servico-titiler-por-inquilino, L1-02-b-token-de-servico-com-escopo-por-lista, L1-02-c-wmts-xyz-tilejson-validados, L1-02-d-cache-nginx-cdn-e-bancada-de-carga, L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro, L1-02-f-predefinicoes-de-renderizacao-e-legenda, L1-02-g-wms-1-3-0-raster, L1-02-h-ponto-estatisticas-e-histograma, L1-02-i-ogc-api-tiles-e-maps, L1-02-tiles-token, L1-03-a-quadro-de-conectores-e-tela-sensores, L1-03-b-sentinel-2, L1-03-c-sentinel-1-sar, L1-03-conectores-sensores, L1-03-d-landsat, L1-03-e-mapbiomas, L1-03-f-cog-globais-por-vsicurl, L1-03-h-clima-nasa-power-e-copernicus-cds, L1-03-k-planetary-computer-e-stac-de-terceiros, L1-03-l-item-referenciado-sem-copia, L1-03-n-comerciais-com-chave-do-cliente, L1-03-p-drone-ortomosaico-e-fotos-brutas, L1-03-q-lidar-copc-mdt-mds, L1-04-a-controle-de-tempo-cortina-e-lado-a-lado, L1-04-c-grafico-de-indice-por-poligono, L1-04-e-diferenca-entre-datas-e-tendencia, L1-04-serie-temporal, L1-05-a-registro-de-modelo-e-proveniencia, L1-05-b-trabalhador-gpu-remoto, L1-05-c-mudanca-s2-calibrada, L1-05-d-camadas-leves-edificacoes-e-vegetacao-em-faixa, L1-05-e-pacote-de-modelo-importavel, L1-05-f-amostras-e-rotulos-para-treino, L1-05-ia-na-entrada, L1-06-rasters-do-acervo-em-cog, L1-07-mosaico-por-colecao-e-pegadas, L1-08-regras-de-mosaico-e-selecao-de-pixel, L1-09-mascara-de-nuvem, L1-10-camada-congelada-pmtiles, L1-12-linguagem-de-expressao-de-banda, L1-13-cadeia-de-funcoes-raster-ao-vivo, L1-14-analise-raster-em-lote-gera-item-novo, L1-15-estatistica-zonal, L1-16-derivados-de-terreno-e-terrain-rgb, L1-18-pansharpening-e-ortorretificacao-rpc, L1-19-multidimensional-netcdf-zarr, L1-20-exportacao-recorte-e-massa, L1-21-wcs-2-0-1, L1-23-cota-e-medicao-por-tb, L1-24-imagens-orientadas, L1-25-servico-de-imagem-esri-compativel, L1-27-ficha-de-metadado-e-licenca-da-imagem, L1-29-teste-no-arcgis-real-do-parceiro, L1-30-paridade-image-server-documento-vivo, L2-01-b-martin-tiles-vetoriais, L2-01-c-lista-camadas-legenda, L2-01-d-popup-runtime, L2-01-e-mapas-base, L2-01-f-navegacao-medicao-coordenadas, L2-01-g-tabela-atributos, L2-01-h-selecao-filtros, L2-01-i-graficos-de-camada, L2-01-k-desenho-anotacoes, L2-01-l-exportacao-do-mapa, L2-02-a-modelo-estilo, L2-02-b-classificacao-servidor, L2-02-c-editor-simbologia-vetor, L2-02-d-rotulos, L2-02-e-simbolos-sprites-glifos, L2-02-f-estilo-raster, L2-02-simbologia, L2-03-a-api-edicao-transacional, L2-03-c-formulario-atributos-runtime, L2-03-d-historico-restauracao, L2-03-e-anexos, L2-03-edicao, L2-03-f-edicao-em-lote-calculo-campo, L2-04-a-leitor-rls-martin, L2-04-b-featureserver-catalogo-metadados, L2-04-c-featureserver-query, L2-04-d-featureserver-edicao-anexos, L2-04-e-vector-tile-server-tilejson, L2-04-f-mapserver-identify-legend-geometryserver, L2-04-g-ogc-api-features-crs-cql2, L2-04-h-wfs-2-gml, L2-04-i-wms-wmts-sld, L2-04-j-conformidade-clientes-e-paridade, L2-04-k-sync-replicas-esri, L2-04-servicos-esri-ogc, L2-05-a-catalogo-ferramentas-gpserver, L2-05-b-vetor-basico, L2-05-c-sobreposicao-agregacao, L2-05-d-grades-densidade-padroes-interpolacao, L2-05-e-raster-basico, L2-05-f-rede-isocrona-rota-ferramentas, L2-05-geoprocessamento, L2-06-b-elementos-basicos, L2-06-c-acoes-seletores-filtros-cruzados, L2-06-d-atualizacao-viva-sse, L2-06-e-estatisticas-servidor, L2-06-paineis, L2-07-a-pwa-instalavel-cache, L2-07-b-formulario-de-coleta-xlsform, L2-07-c-fila-sincronizacao-idempotente, L2-07-campo, L2-07-d-mapa-offline-por-area, L2-07-e-odk-central-ponte, L2-08-a-leitor-portal-inventario, L2-08-b-clonar-camadas-hospedadas, L2-08-c-converter-web-map-e-estilo, L2-08-d-relatorio-migracao-e-exportacao-reversa, L2-08-migracao-agol, L2-09-3d, L2-09-a-terreno-terrain-rgb-relevo, L2-09-b-cena-extrusao-slides, L2-09-c-modelos-gltf-ifc-3dtiles, L2-09-d-analise-3d-visibilidade, L2-10-a-dominios-subtipos, L2-10-b-relacionamentos, L2-10-c-linguagem-expressao, L2-10-d-regras-de-atributo, L2-10-relacoes-regras, L2-11-a-geocodificacao-csv, L2-11-b-geocodificador-brasil, L2-11-c-rota-matriz-isocrona, L2-11-geocodificacao-rota, L2-12-a-motor-render-servidor, L2-12-b-layouts-elementos-exportacao, L2-12-c-series-de-mapas-lote, L2-12-impressao-layout, L2-13-a-versoes-ramo-reconciliar, L2-13-b-replicas-sincronizacao, L2-13-versionamento-sync, L2-14-a-ingestao-de-fluxos, L2-14-b-camada-viva-historico, L2-14-c-regras-alertas-incidentes, L2-14-tempo-real, L2-15-a-geoparquet-bucket-catalogo, L2-15-analitica-grande, L2-15-b-consultas-duckdb-em-escala, L2-16-a-sdk-python-geo, L2-16-b-jupyter-por-inquilino-isolado, L2-16-c-script-vira-ferramenta, L2-16-notebooks-scripts, L2-17-crs-transformacoes, L2-18-camada-de-consulta-sql, L2-19-paridade-l2-e-manual, L3-01-a-modelo-dado, L3-01-b-unidades, L3-01-c-extracao-fator, L3-01-d-transformacoes, L3-01-f-explicacao, L3-01-g-tela-motor, L3-01-i-exportacao-metodo, L3-01-j-equivalencia-motor-logistico, L3-01-motor-servico, L3-02-a-monte-carlo-pesos, L3-02-b-sensibilidade-sobol-oat, L3-02-d-comparacao-cenarios, L3-02-robustez, L3-03-ahp-pares, L3-04-restricoes, L3-05-localizar-regioes, L3-06-criterios-de-feicao, L3-08-pareto, L3-09-backtest-decisao-real, L3-10-corredor-custo-minimo, L3-11-fator-de-rede, L3-12-integracao-fluxo-e-api, L3-13-resultado-como-camada, L3-17-similaridade, L3-18-paridade-esri-amc, L3-20-narrativa-de-resultado, L4-01-a-pacote-de-ativos, L4-01-b-topologia-derivada, L4-01-c-importador-bdgd, L4-01-d-atributos-de-rede, L4-01-modelo-rede, L4-02-a-conectado-e-subrede, L4-02-b-montante-jusante, L4-02-c-isolamento, L4-02-d-lacos-e-caminho-curto, L4-02-e-configuracoes-de-tracado, L4-02-f-resultados-e-exportacao, L4-02-tracado, L4-03-a-regras-de-conectividade, L4-03-b-terminais, L4-03-c-edicao-topologica-no-mapa, L4-03-d-areas-sujas-e-validacao, L4-03-e-versao-de-rede, L4-03-edicao-rede, L4-04-a-controladores-e-tiers, L4-04-b-atualizar-e-exportar-subrede, L4-04-c-sumarios-por-subrede, L4-04-d-diagrama-esquematico, L4-04-e-diagrama-camadas-e-contencao, L4-04-subredes-diagramas, L4-05-a-exportar-opendss, L4-05-b-cim-iec-61970-61968, L4-05-c-pandapower-e-matpower, L4-05-conectores-rede, L4-05-d-epanet-inp, L4-05-e-gas-e-esgoto, L4-05-f-transmissao-sindat-sigel, L4-05-g-osm-power, L4-05-h-inspire-utility-networks, L4-06-a-contencao, L4-06-b-estrutura-postes, L4-06-c-objetos-nao-espaciais, L4-06-d-categorias-e-restricoes, L4-06-estruturas-regras-avancadas, L4-07-fluxo-de-potencia, L4-08-queda-de-tensao-e-carregamento, L4-09-perdas-tecnicas-por-segmento, L4-10-continuidade-dec-fec, L4-11-gd-conectada-e-hospedagem, L4-12-inspecao-vegetacao-na-faixa, L4-13-integracao-telemetria, L4-14-balanco-de-energia-por-alimentador, L4-15-serie-temporal-da-rede, L4-16-api-rest-compativel-un, L4-17-migracao-de-un-e-rede-geometrica, L4-18-rede-simples-trace-network, L4-19-planejamento-de-linha-nova, L4-20-consumidores-e-enderecos, L4-21-qualidade-e-saude-da-rede, L4-22-desempenho-em-escala, L4-23-isolamento-por-inquilino-na-rede, L4-24-cartografia-de-rede, L4-25-cenarios-e-se, L4-26-inspecao-de-campo-do-ativo, L4-28-identificadores-e-numeracao, L4-29-regras-de-atributo-de-rede, L4-30-manual-e-tour-de-rede, L4-parcelas-01-modelo-de-parcelas, L4-parcelas-02-fluxos-cogo, L4-parcelas-03-ajuste-e-qualidade, L5-01-app-builder, L5-01-b-widgets-mapa, L5-01-c-widgets-dado, L5-01-d-widgets-pagina-menu, L5-01-e-acoes-configuraveis, L5-01-f-modelos-app-galeria, L5-02-a-editor-de-nos, L5-02-b-execucao-proveniencia, L5-02-c-agendamento-variaveis, L5-02-d-exportar-python-importar-json, L5-02-e-iteradores-condicionais, L5-02-f-fluxo-como-ferramenta-e-api, L5-02-fluxos, L5-03-a-construtor-elementos, L5-03-b-logica-condicional-calculo-restricao, L5-03-c-dominios-listas-cascata, L5-03-d-repeticoes-relacionadas-anexos, L5-03-e-xlsform-ida-e-volta-idiomas, L5-03-form-builder, L5-04-a-blocos-de-conteudo, L5-04-b-imersivos-sidecar-tour-swipe, L5-04-c-temas-capa-colecao, L5-04-storymap, L5-06-motor-widgets, L5-07-fontes-vistas-mensagens, L5-10-temas-marca, L5-11-expressoes-no-navegador, L5-13-edicao-concorrente, L5-14-publicacao-links-embed, L5-16-agente-escreve-configuracao, L5-17-painel-elementos-avancados, L5-18-painel-parametros-url-vistas, L5-19-painel-expressoes-de-dado-tempo-real, L5-20-sites-paginas-publicas, L5-21-dados-abertos-catalogo-publico, L5-22-sites-dominio-proprio-tema, L5-23-apps-instantaneos-motor-galeria, L5-24-apps-instantaneos-modelos-1, L5-25-apps-instantaneos-modelos-2, L5-26-construtor-popup, L5-27-simbologia-por-arrasto, L5-28-galeria-simbolos-rampas-estilos, L5-29-construtor-relatorio-pdf, L5-30-relatorio-lote-agendado, L5-31-construtor-de-camada-esquema, L5-32-vistas-de-camada, L5-33-a-diagrama-de-trabalho, L5-33-b-modelos-e-trabalhos, L5-33-c-atribuicao-avancada-indicadores, L5-34-captura-rapida-designer-pwa, L5-35-missao-operacao-ao-vivo, L5-36-widgets-personalizados-sdk, L5-37-pacotes-modelos-entre-inquilinos, L5-38-importadores-configuracao-esri, L5-39-paridade-l5-e-manual, L6-01-a-registro, L6-01-acervo-casa, L6-01-b-view-so-leitura, L6-01-c-tela-acervo, L6-01-d-ficha-fonte, L6-01-e-assinatura-e-uso, L6-01-f-lgpd, L6-01-g-licenca-curada, L6-01-i-raster-e-arquivos, L6-01-j-multi-servidor, L6-02-b-wms-wmts, L6-02-conectores-vivos, L6-02-d-arcgis-rest-externo, L6-02-e-stac-externo, L6-02-f-geoparquet-duckdb, L6-02-g-pmtiles-xyz-tilejson, L6-02-h-csv-url-geojson-kml, L6-02-i-google-sheets, L6-02-j-bancos-externos, L6-02-k-agendamento, L6-02-l-saude, L6-02-m-catalogo-endpoints-brasil, L6-02-n-etl-na-entrada, L6-02-o-importacao-exportacao-formatos, L6-03-paridade-conectores, L6-04-acervo-no-motor, L6-05-proveniencia-camada-externa, L6-06-descoberta-csw, L7-01-a-compose-perfis, L7-01-b-instalacao-conteiner-limpo, L7-01-c-dado-demonstracao, L7-01-instalador-limpo, L7-02-a-k6-cenarios, L7-02-b-pool-e-limites-por-inquilino, L7-02-carga, L7-03-a-antivirus-upload, L7-03-b-antivirus-anexos, L7-03-b-rate-limit-abuso, L7-03-c-ssrf-conectores, L7-03-d-injecao-consulta, L7-03-e-cabecalhos-csp-tls, L7-03-f-dependencias-cve-log-correcoes, L7-03-g-asvs-nivel2-pentest, L7-03-seguranca, L7-04-a-manual-capturas-geradas, L7-04-b-tour-primeiro-acesso, L7-04-c-manual-admin-runbooks, L7-04-d-videos-por-tarefa, L7-04-manual-e-tour, L7-06-a-metricas-exporters, L7-06-b-alertas, L7-06-c-logs-consulta-req-id, L7-06-d-paineis, L7-06-observabilidade, L7-07-a-replica-postgres, L7-07-alta-disponibilidade, L7-07-b-replica-garage, L7-07-c-ensaio-failover, L7-08-a-webhooks-eventos, L7-08-b-sdk-python, L7-08-c-sdk-js, L7-08-d-portal-api-chaves, L7-08-sdk-api-webhooks, L7-09-a-medidor-diario, L7-09-b-planos-limites-relatorio, L7-09-medicao-cobranca, L7-10-a-i18n-pt-en-es, L7-10-b-acessibilidade-wcag21aa, L7-10-i18n-acessibilidade, L7-11-a-appliance-licenca, L7-11-appliance-cliente, L7-11-b-appliance-sem-internet, L7-11-c-telemetria-opcional, L7-12-a-classificacao-retencao, L7-12-b-registro-tratamento-dpa-incidente, L7-12-lgpd-governanca, L7-13-a-chamados, L7-13-c-laco-agentico-suporte, L7-13-suporte-chamados, L7-14-extensoes-fdw, L7-14-instalacoes-apt-desta-linha, L7-15-processo-release, L7-16-assinatura-pacote, L7-17-capacidade-planejamento, L7-18-custo-por-inquilino, L7-19-segredos-e-certificados, L7-21-pagina-status, L7-22-sla-e-incidentes, L7-23-pgbackrest-pitr, L7-24-drill-restauracao, L7-25-exportacao-inquilino, L7-26-cdn-tiles, L7-27-origem-br-soberania, L7-28-iso27001-controles, L7-29-roteiro-demonstracao, L7-30-teste-parceiro-pro-agol, L7-31-ambiente-homologacao, L7-32-postgres-manutencao-versao, L7-33-modo-somente-leitura, L7-34-saude-profunda, L7-35-atualizacao-versao-assinada, L0-05-e-justica-entre-inquilinos, L0-14-identidade-visual, L0-15-marca, L4-01-h-alinhamento-inspire-gnm | — |
| `L7-11-a-appliance-licenca` | 4 | pendente | 0 |  | L7-16-assinatura-pacote, L7-33-modo-somente-leitura, L7-25-exportacao-inquilino | — |
| `L7-11-appliance-cliente` | 4 | pendente | 0 |  | L7-01-instalador-limpo | — |
| `L7-11-b-appliance-sem-internet` | 4 | refutado | 3 | 9 | L7-01-a-compose-perfis | adversario T9 L7-1: docs/APPLIANCE.md admite rede --internal nao executada; xfail |
| `L7-11-c-telemetria-opcional` | 4 | parcial | 2 | 8 | L7-11-b-appliance-sem-internet | telemetria desligada por padrão com opt-in do superadmin: prévia == JSON enviado (13 campos fixos, só agregados), 0 chamadas de rede desligada (medido), receptor recusa chave desconhecida/campo a mais/chave de outro appliance, job diário, APPLIANCE.md §5; painel de suporte = GET /api/telemetria/appliances (sem tela). Ramo com merge de wt/cx5l711b |
| `L7-13-a-chamados` | 4 | refutado | 3 | 9 | L7-04-manual-e-tour, L7-03-a-antivirus-upload, L0-07-admin-org | adversario T9 L7-2: _verificar_anexo so varre dados[:65536] com teto de 8 MB — PNG terminando no byte 65536 esconde script; xfail test_l7_adv2_chamados_anexo_janela_de_varredura_truncada.py |
| `L7-13-c-laco-agentico-suporte` | 4 | pendente | 0 |  | L7-13-a-chamados, L7-31-ambiente-homologacao, L7-15-processo-release, L7-06-c-logs-consulta-req-id | — |
| `L7-13-suporte-chamados` | 4 | pendente | 0 |  | L7-04-manual-e-tour | — |
| `L7-14-extensoes-fdw` | 4 | pendente | 0 |  | L7-01-a-compose-perfis | oracle_fdw: licença do Instant Client (decisão do dono) |
| `L7-28-iso27001-controles` | 4 | pendente | 0 |  | L7-03-g-asvs-nivel2-pentest, L7-19-segredos-e-certificados, L7-24-drill-restauracao | — |
| `L7-32-postgres-manutencao-versao` | 4 | pendente | 0 |  | L7-23-pgbackrest-pitr | — |

## Decisões do dono

| id | data | pergunta | estado |
|---|---|---|---|
| D18 | 2026-09-05 | nome público do produto (codinome interno: plat) | aberta |
| D19 | 2026-09-05 | URL interna: subdomínio (plat.iagrointel.com, como os dois SIGs de teste interno) × caminho não-adivinhável em iagrointel.com | seguido o precedente da casa (os dois SIGs de teste interno): subdomínio plat.iagrointel.com, DNS-only + certbot, noindex; reversível |
| D20 | 2026-09-05 | credencial AGOL/Portal de teste do parceiro para L2-08 (migração) e teste real Pro/AGOL contra nossos serviços | aberta |
| D21 | 2026-09-05 | disco: os dois servidores estão a 98 %. O laço trabalha com ≤ 3 GB; qualquer dado de rede/imagem além disso exige decisão (apagar cópias declaradas em acervo.objeto = 242 GB, ou volume novo) | aberta |
| D22 | 2026-09-05 | reiniciar o Postgres compartilhado para ligar archive_mode=on (PITR/pgBackRest, L0-06-b): janela e autorização | aberta |
| D23 | 2026-09-05 | DWG: LibreDWG (GPL, fora do processo web, já usado no GPU box) basta, ou aceitar o binário do ODA File Converter (licença própria) no servidor? | aberta |
| D24 | 2026-09-05 | compartilhamento público anônimo: permitido por inquilino (padrão desligado) ou nunca? Impacta OGC Records/CSW externo e o link por token | aberta |
| D25 | 2026-09-05 | gov.br: qual órgão/credencial de teste e quem assina o ofício | aberta |
| D26 | 2026-09-05 | Garage: reusar o daemon plataforma-garage com buckets próprios ou subir plat-garage separado (mesmo disco) | aberta |
| D27 | 2026-09-05 | mapa base vetorial de instalação: PMTiles do Protomaps (OSM/ODbL) para o Brasil inteiro ocupa gigabytes (tamanho medido antes de baixar) com o disco a 98 %; recorte por UF na demonstração, ou volume novo? Sem mapa base próprio a demo depende do proxy de tiles do OSM, que a política de uso não permite em produção | aberta |
| D28 | 2026-09-05 | dados abertos de endereço e de rede viária por UF (CNEFE do IBGE e .pbf do Geofabrik) para geocodificação e rota: volume por UF medido antes; quais UFs na demonstração e onde ficam (mesmo disco a 98 %) | aberta |
| D29 | 2026-09-05 | ODK Central self-host em docker (RAM e disco) para a integração opcional, ou registrar a integração só contra o sandbox público do ODK | aberta |
| D30 | 2026-09-05 | pool de renderização headless (chromium): quantas páginas quentes e MemoryMax, dado que a máquina tem 3 GB disponíveis; sem isso impressão, WMS vetorial e MapServer export ficam com 1 página e fila | aberta |
| D31 | 2026-09-05 | broker MQTT próprio (mosquitto, apt) na máquina ou só cliente de brokers externos do cliente | aberta |
| D32 | 2026-09-05 | conversão IFC → glTF roda no GPU box (onde a casa já tem IfcOpenShell e o acervo de IFC) por job remoto, ou instala-se IfcOpenShell aqui (pip, tamanho a medir) | aberta |
| D33 | 2026-09-05 | TimescaleDB para dado de tempo real DO CLIENTE: a TSL proíbe uso como serviço (DOC 22); a linha assume partição nativa + BRIN e NÃO usa a extensão em objetos do inquilino. Confirmar ou pedir parecer jurídico | aberta |
| D34 | 2026-09-05 | SQL livre do usuário (camada de consulta L2-18 e DuckDB L2-15-b) é aceito no produto com as restrições descritas, ou só por administrador do inquilino | aberta |
| D35 | 2026-09-05 | campo offline: PWA própria (L2-07) como caminho principal, com QField/QFieldCloud e ODK como alternativas por GeoPackage/XLSForm, ou o inverso (a spec 17.2 dizia QFieldCloud + ODK; o estado do laço diz PWA própria) | aberta |
| D36 | 2026-09-05 | QGIS em contêiner docker (imagem oficial, tamanho a medir) só para a conformidade de clientes; instalar ou registrar o teste como pendente | aberta |
| D37 | 2026-09-05 | servidor dedicado para o laço/plat (Hetzner AX52 ~€64 ou CPX51 ~€60 via API): fecha a ressalva 'máquina nova' do P5 e dobra as trilhas (RAM aqui = 2-3 GB livres) | adiada pelo dono 05/09 16:20 ('crack on here for now, we will buy it after'); chave da API não está em nenhuma das 3 máquinas — quando comprar, gravar em ~/.hcloud.env (600) e o gerente provisiona |
| D38 | 2026-09-06 | multi-setor de rede (água, gás, rodovia — não só elétrica) e alcance internacional/baixo recurso: a arquitetura JÁ suporta (C3 do L4_CONCEITO.md: esquema da rede é DADO — pacote de ativos versionado, não código; água/gás/telecom já têm formato de importação declarado). A pergunta real é PRIORIZAÇÃO: investir agora em ingestão de dado real de um 2º setor (água é o candidato mais forte — padrão INSPIRE Water Network existe, EPANET/WNTR já no ADR, 2 bi de pessoas sem água segura é o gancho internacional) ou manter o fosso em elétrica (376 fontes, BDGD, PRODIST, OpenDSS) e só abrir setor novo com demanda real medida? Rodovia como REDE DE UTILIDADE não está no escopo hoje (temos routing/corredor de LT, não trânsito/pavimento — teria de nascer como linha própria, tema INSPIRE Transport Networks); construção NÃO é rede — é BIM/IFC, já existe como projeto separado (GABARITO) e não deve ser confundido com L4. | DECIDIDA 06/09/2026: alinhar o pacote de ativos (C3) ao INSPIRE Generic Network Model (não só ao Esri UPDM), para exportabilidade fora do Brasil. Água segue como 2º setor candidato, mas SEM data de início (aguarda demanda real). Rodovia pública = nova linha (L8), não item de L4. Infraestrutura PRIVADA de loteamento/condomínio (FGR-shaped) = combinar com L4-parcelas + GABARITO, não com L8. |
| D39 | 2026-09-06 | L6-01-g-licenca-curada fechou em 29/40 fontes com licenca ESCRITA testada por HTTP (nao 40). Aceitar 29 como 'parcial' e seguir para o resto da linha L6, retomando este item quando aparecer nova fonte com geometria + portal com licenca real (ex.: IBGE se o WAF liberar, ou convenio de acesso)? Ou o dono quer abrir contato direto com algum orgao (ANP/ANM/SGB/IBGE) para conseguir o termo escrito que a pesquisa automatizada nao achou? | aberta |
| D40 | 2026-09-06 | A suite de testes (tests/api/conftest.py::sessao_plat) depende do superadmin REAL do inquilino `plataforma` para qualquer teste que use a fixture `ids` (quase toda a suite). Isso ja causou 3 bloqueios de login (423) e 1 divergencia de segredo TOTP (401 codigo_invalido) no mesmo dia, por corrida entre trilhas concorrentes ligando/testando 2FA no mesmo usuario real. trilha_ambiente.sh (ferramenta nova, schema por trilha) resolve para quem adotar, mas quem roda contra o schema padrao continua exposto. Aceitar continuar migrando gradualmente para trilha_ambiente.sh (sem tocar o usuario real), ou autorizar um superadmin de teste DEDICADO (schema padrao, so para a suite, nunca usado em operacao) para eliminar o problema de vez? Recomendacao de dev-41 (sessao wt/*): a suite deveria criar um superadmin de teste PROPRIO, dedicado so a testes, e nunca mais tocar o usuario real de operacao - opcao preferida por ela, registrada aqui porque a tentativa dela de gravar isso como D37 no mesmo estado.json colidiu com uma escrita minha (D37 ja existia com outro conteudo, sobre o servidor Hetzner - a escrita dela nao persistiu; achado real de corrida sem lock nas edicoes concorrentes deste arquivo). | aberta |
| D41 | 2026-09-07 | autoriza a purga destrutiva de /var/log/journal (73 linhas com segredos reais de operacoes passadas) seguida da rotacao de TODOS os segredos expostos? A rotacao derruba as trilhas ate serem recriadas (elas consomem o cofre) — janela coordenada entre as duas sessoes | aberta |

## Medidas disponíveis (`tests/medidas/`)

| arquivo | gerado em | git_sha | medidas |
|---|---|---|---|
| `F8-isolamento-d-slug.json` | 2026-09-07T03:00:19Z | `fac1db70f584` | 2 |
| `HARD-01-seguranca.json` |  | `874d7df5` | 0 |
| `L0-01-repo.json` | 2026-09-06T00:25:55Z | `65a9fc2c0869` | 36 |
| `L0-02-e.json` | 2026-09-06T12:23:52Z | `e30515b57814` | 2 |
| `L0-02-g-checagem-privilegio-papel-id.json` | 2026-09-06T15:59:45Z | `90d03c07da0c` | 9 |
| `L0-02-tenant-auth.json` | 2026-09-06T13:00:50Z | `e2d5f9164f6b` | 36 |
| `L0-03-catalogo.json` | 2026-09-06T16:24:31Z | `90d03c07da0c` | 15 |
| `L0-03-e.json` | 2026-09-06T19:28:29Z | `90d03c07da0c` | 7 |
| `L0-04-a-upload-arquivo.json` | 2026-09-06T15:06:39Z | `9a69cebb2476` | 1 |
| `L0-04-b-inspecao.json` | 2026-09-06T18:13:13Z | `90d03c07da0c` | 3 |
| `L0-04-c-tabela-camada.json` | 2026-09-06T18:13:13Z | `90d03c07da0c` | 2 |
| `L0-04-d-formatos-base.json` | 2026-09-06T16:23:39Z | `1409076da35d` | 6 |
| `L0-04-e-formatos-cad.json` | 2026-09-06T16:42:49Z | `8a9f347eac8d` | 14 |
| `L0-04-h-exportar.json` | 2026-09-07T02:02:35Z | `2382a8e7c5dd` | 4 |
| `L0-04-i-fonte-registrada.json` | 2026-09-07T02:24:39Z | `2382a8e7c5dd` | 7 |
| `L0-04-k-rota-formatos-encoberta.json` |  | `` | 5 |
| `L0-05-e-justica-entre-inquilinos.json` | 2026-09-07T21:46:09Z | `6d9ecb76f345` | 11 |
| `L0-05-e-worker-em-container.json` | 2026-09-06T16:23:39Z | `1409076da35d` | 7 |
| `L0-05-jobs.json` | 2026-09-06T00:27:09Z | `65a9fc2c0869` | 25 |
| `L0-06-a-dump-logico.json` | 2026-09-07T19:52:27Z | `0bc2d4daac50` | 19 |
| `L0-06-c-restore-drill.json` | 2026-09-07T22:28:29Z | `3d72ad0d9861` | 11 |
| `L0-06-d-exportar-inquilino.json` | 2026-09-07T22:43:12Z | `c3d32d404e57` | 8 |
| `L0-06-e-status.json` |  | `` | 0 |
| `L0-07-e-relatorios.json` | 2026-09-08T01:57:13Z | `78f3f67699b1` | 6 |
| `L0-07-f-console-plataforma.json` | 2026-09-08T01:22:32Z | `9ac92cde4a8b` | 3 |
| `L0-08-a-oidc.json` | 2026-09-07T02:31:03Z | `2382a8e7c5dd` | 1 |
| `L0-08-b-saml.json` | 2026-09-07T21:01:49Z | `08a3addf6283` | 3 |
| `L0-08-c-govbr.json` | 2026-09-08T06:04:30Z | `3ebd0981a10e` | 2 |
| `L0-08-d-ldap.json` | 2026-09-06T11:05:40Z | `19c4cb309029` | 2 |
| `L0-08-e-mapeamento-provisionamento.json` | 2026-09-08T05:54:53Z | `0adb54daae58` | 2 |
| `L0-09-a-procedencia.json` | 2026-09-06T16:21:13Z | `90d03c07da0c` | 6 |
| `L0-09-b-editor-iso-mgb.json` | 2026-09-07T02:20:00Z | `de57dd2` | 10 |
| `L0-09-c-xml-iso-validacao.json` |  | `` | 0 |
| `L0-09-metadado-catalogo.json` | 2026-09-06T12:30:34Z | `e30515b57814` | 3 |
| `L0-13-dado-demonstracao.json` | 2026-09-08T21:37:06Z | `f697cf77ff41` | 7 |
| `L0-14-cli-admin.json` | 2026-09-07T23:17:17Z | `5e89faa4` | 7 |
| `L0-14.json` | 2026-09-06T19:35:49Z | `90d03c07da0c` | 10 |
| `L1-01-a.json` | 2026-09-06T19:39:56Z | `90d03c07da0c` | 3 |
| `L1-01-b.json` | 2026-09-08T13:20:20Z | `4de723c86fe1` | 86 |
| `L1-01-d-adversario.json` |  | `` | 0 |
| `L1-01-d.json` |  | `` | 0 |
| `L1-01-f-formatos-de-entrada.json` | 2026-09-09T00:02:22Z | `bc71718b44d0` | 3 |
| `L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo.json` | 2026-09-08T21:51:50Z | `c89228222ec6` | 5 |
| `L1-02-d-cache-nginx-e-carga.json` |  | `` | 0 |
| `L1-02-i-ogc-api-tiles-e-maps.json` |  | `` | 8 |
| `L1-02-tiles-token.json` | 2026-09-07T03:15:03Z | `c59b2396e38f` | 17 |
| `L1-07-mosaico-por-colecao-e-pegadas.json` |  | `68e94508913b` | 7 |
| `L2-01-a-documento-mapa.json` | 2026-09-06T16:09:25Z | `90d03c07da0c` | 1 |
| `L2-01-a.json` | 2026-09-06T16:01:14Z | `90d03c07da0c` | 3 |
| `L2-01-b-martin-tiles-vetoriais.json` |  | `` | 0 |
| `L2-01-c-lista-camadas-legenda.json` |  | `` | 0 |
| `L2-01-d-popup-runtime.json` | 2026-09-07T18:31:55Z | `52cd0194a32f` | 2 |
| `L2-01-e.json` | 2026-09-07T18:02:05Z | `d2e9973de90e` | 7 |
| `L2-01-g-tabela-atributos.json` | 2026-09-07T20:27:11Z | `715af996458c` | 9 |
| `L2-01-h-selecao-filtros.json` |  | `` | 0 |
| `L2-01-i-graficos-de-camada.json` | 2026-09-08T00:59:57Z | `979462b5d22d` | 15 |
| `L2-01-j-comparacao-cortina-tempo.json` | 2026-09-10T19:29:53Z | `e7459676480f` | 2 |
| `L2-01-k-desenho-anotacoes.json` | 2026-09-07T18:46:13Z | `5fd1a941` | 5 |
| `L2-01-l-exportacao-do-mapa.json` | 2026-09-07T20:26:20Z | `500292445074` | 5 |
| `L2-01-mapa-web.json` | 2026-09-07T03:29:26Z | `f183b1a2ea41` | 20 |
| `L2-02-b-classificacao-servidor.json` |  | `` | 1 |
| `L2-02-c-editor-simbologia-vetor.json` | 2026-09-07T21:04:23Z | `d500839aaa4a` | 2 |
| `L2-02-d-rotulos.json` |  | `` | 10 |
| `L2-02-e-simbolos-sprites-glifos.json` | 2026-09-07T17:53:22Z | `20e34773221b` | 8 |
| `L2-02-f-estilo-raster.json` | 2026-09-07T15:22:00Z | `1c1927c58780` | 8 |
| `L2-03-a-api-edicao-transacional.json` | 2026-09-07T02:28:59Z | `1ade59ea0ffe` | 1 |
| `L2-03-a.json` | 2026-09-06T19:23:23Z | `90d03c07da0c` | 1 |
| `L2-03-edicao.json` |  | `` | 0 |
| `L2-03-f-edicao-em-lote-calculo-campo.json` | 2026-09-08T07:17:58Z | `f6156fc95842` | 6 |
| `L2-04-a-leitor-rls-martin.json` | 2026-09-06T16:26:43Z | `90d03c07da0c` | 11 |
| `L2-04-b-featureserver-catalogo-metadados.json` |  | `` | 0 |
| `L2-04-c-consulta-espacial-p95.json` |  | `` | 0 |
| `L2-04-c-featureserver-query.json` |  | `` | 0 |
| `L2-04-d-featureserver-edicao-anexos.json` |  | `` | 0 |
| `L2-04-e-vector-tile-server-tilejson.json` | 2026-09-07T16:53:24Z | `7b2687f88f54` | 7 |
| `L2-04-f-mapserver-identify-legend-geometryserver.json` | 2026-09-08T06:34:03Z | `00b45d5fe64a` | 8 |
| `L2-04-h-wfs-2-gml.json` | 2026-09-08T01:15:25Z | `7450563e63cc` | 7 |
| `L2-04-i-wms-wmts-sld.json` | 2026-09-08T12:33:34Z | `4d885ef22774` | 16 |
| `L2-04-j-conformidade-clientes-e-paridade.json` |  | `` | 0 |
| `L2-04-k-sync-replicas-esri.json` | 2026-09-08T21:58:56Z | `1959c4b1ebba` | 2 |
| `L2-04-servicos-esri-ogc.json` |  | `` | 0 |
| `L2-05-b-vetor-basico.json` |  | `` | 0 |
| `L2-05-c-sobreposicao-agregacao.json` |  | `` | 0 |
| `L2-05-d-grades-densidade-padroes-interpolacao.json` |  | `` | 0 |
| `L2-05-e-raster-basico.json` |  | `` | 0 |
| `L2-05-f-rede-isocrona-rota-ferramentas.json` | 2026-09-08T01:39:37Z | `3d97c0d48351` | 4 |
| `L2-06-a-modelo-painel-fontes.json` | 2026-09-09T03:01:16Z | `b99460784bc2` | 2 |
| `L2-06-b-elementos-basicos.json` | 2026-09-08T12:25:22Z | `33764410ac3d` | 6 |
| `L2-06-c-acoes-seletores-filtros-cruzados.json` | 2026-09-09T03:01:21Z | `b99460784bc2` | 10 |
| `L2-06-d-atualizacao-viva-sse.json` | 2026-09-08T10:44:31Z | `6b4d2c1bdf80` | 1 |
| `L2-06-e-estatisticas-servidor.json` | 2026-09-08T19:20:34Z | `575754fbc1de` | 6 |
| `L2-07-a-pwa-instalavel-cache.json` | 2026-09-07T13:56:18Z | `0f1669c80312` | 11 |
| `L2-07-b-formulario-de-coleta-xlsform.json` | 2026-09-07T20:32:47Z | `1a769c413687` | 4 |
| `L2-07-e-odk-central-ponte.json` | 2026-09-08T11:31:58Z | `ec3a310be29c` | 6 |
| `L2-08-a-leitor-portal-inventario-adversario.json` | 2026-09-06T18:06:12Z | `0a11a61349a1` | 3 |
| `L2-08-a-leitor-portal-inventario.json` | 2026-09-06T16:06:54Z | `2fe849d88a4a` | 9 |
| `L2-08-b-clonar-camadas-hospedadas.json` | 2026-09-07T21:35:32Z | `77411ed09942` | 4 |
| `L2-09-a-terreno-terrain-rgb-relevo.json` |  | `` | 0 |
| `L2-09-b-cena-extrusao-slides.json` | 2026-09-08T11:20:48Z | `a61254c04365` | 7 |
| `L2-09-c-modelos-gltf-ifc-3dtiles.json` | 2026-09-08T12:58:32Z | `51bdfbbb91b0` | 7 |
| `L2-09-d-analise-3d-visibilidade.json` | 2026-09-08T18:14:56Z | `610896979710` | 9 |
| `L2-10-a-dominios-subtipos.json` | 2026-09-06T18:41:11Z | `90d03c07da0c` | 21 |
| `L2-10-b-relacionamentos.json` | 2026-09-07T14:40:39Z | `2f4574eb8aa5` | 11 |
| `L2-10-c-expressao.json` | 2026-09-06T14:28:04Z | `4a0524ff5c58` | 13 |
| `L2-10-d-regras-de-atributo.json` | 2026-09-08T10:36:19Z | `4d7493efe60d` | 8 |
| `L2-11-a-geocodificacao-csv.json` | 2026-09-08T20:20:03Z | `942ec20c986f` | 4 |
| `L2-11-a.json` | 2026-09-06T16:35:53Z | `90d03c07da0c` | 11 |
| `L2-11-b-geocodificador-brasil.json` | 2026-09-06T15:34:16Z | `e407d1a4f013` | 9 |
| `L2-12-a-motor-render-servidor.json` |  | `` | 0 |
| `L2-13-a-versoes-ramo-reconciliar-protocolo.json` | 2026-09-08T13:23:26Z | `` | 0 |
| `L2-13-a-versoes-ramo-reconciliar.json` | 2026-09-08T13:26:32Z | `50758da0b514` | 12 |
| `L2-13-b-replicas-sincronizacao.json` | 2026-09-08T12:55:57Z | `4dc968688c39` | 4 |
| `L2-14-a-ingestao-de-fluxos.json` | 2026-09-08T13:11:59Z | `7cc812400f09` | 16 |
| `L2-15-a-geoparquet-bucket-catalogo.json` | 2026-09-07T17:49:15Z | `102997ba080e` | 1 |
| `L2-16-a-sdk-python-geo.json` | 2026-09-08T20:22:37Z | `610896979710` | 1 |
| `L2-16-b-jupyter-por-inquilino-isolado.json` | 2026-09-09T00:18:01Z | `9233f6e2c826` | 8 |
| `L2-16-c-script-vira-ferramenta.json` | 2026-09-09T02:30:00Z | `bfd18d99` | 7 |
| `L2-17-crs-transformacoes.json` | 2026-09-08T19:33:49Z | `99dacd935a73` | 7 |
| `L3-01-a.json` | 2026-09-06T19:23:04Z | `90d03c07da0c` | 11 |
| `L3-01-b.json` | 2026-09-06T16:20:00Z | `0b0d47a182a1` | 12 |
| `L3-01-c-extracao-fator.json` |  | `` | 1 |
| `L3-01-d-transformacoes.json` | 2026-09-07T16:27:30Z | `95597d5c56b4` | 64 |
| `L3-01-e-combinacao.json` | 2026-09-07T10:12:16Z | `afc909f55a75` | 2 |
| `L3-01-f-explicacao.json` | 2026-09-07T13:01:45Z | `c0741beb3183` | 4 |
| `L3-01-g-tela-motor.json` | 2026-09-08T12:12:54Z | `84279ad77dcc` | 2 |
| `L3-01-h-presets.json` | 2026-09-08T17:46:26Z | `610896979710` | 1 |
| `L3-01-i-exportacao-metodo.json` | 2026-09-08T18:33:45Z | `610896979710` | 4 |
| `L3-01-j.json` | 2026-09-07T20:05:32Z | `8c7c5ef85dff` | 26 |
| `L3-02-a-monte-carlo-pesos.json` | 2026-09-07T12:44:34Z | `31c7a4d11850` | 1 |
| `L3-02-b-sensibilidade-sobol-oat.json` | 2026-09-08T10:34:27Z | `0d3f673ac96b` | 4 |
| `L3-02-c-smaa.json` | 2026-09-08T10:28:43Z | `0d3f673ac96b` | 3 |
| `L3-04-restricoes.json` |  | `` | 7 |
| `L3-05-localizar-regioes.json` | 2026-09-08T12:48:25Z | `33be09441f2f` | 5 |
| `L3-06-criterios-de-feicao.json` |  | `` | 14 |
| `L3-07-agregacao.json` | 2026-09-07T16:34:25Z | `95597d5c56b4` | 16 |
| `L3-08-pareto.json` | 2026-09-08T11:36:06Z | `33be09441f2f` | 6 |
| `L3-09-backtest-decisao-real.json` | 2026-09-08T13:01:03Z | `33be09441f2f` | 9 |
| `L3-10-corredor-custo-minimo.json` | 2026-09-08T15:57:10Z | `88eeccaf3c8d` | 9 |
| `L3-14-cobertura-dado-ausente.json` |  | `` | 0 |
| `L3-15-metadado-fator.json` |  | `` | 0 |
| `L3-16-desempenho-escala.json` | 2026-09-07T19:19:52Z | `471a7cf1e9b0` | 9 |
| `L3-17-similaridade.json` | 2026-09-07T12:45:05Z | `325b004a38bd` | 8 |
| `L3-19-multiescala.json` | 2026-09-06T18:32:18Z | `90d03c07da0c` | 8 |
| `L3-20-narrativa-de-resultado.json` | 2026-09-08T18:53:19Z | `610896979710` | 6 |
| `L3-adversario-uniao-achados.json` |  | `` | 0 |
| `L4-01-a-pacote-de-ativos-adversario.json` | 2026-09-06T18:06:16Z | `0a11a61349a1` | 6 |
| `L4-01-a-pacote-de-ativos.json` | 2026-09-06T16:20:00Z | `1d0040b8d465b9d844eee58564cda43d32b4965b` | 15 |
| `L4-01-a.json` | 2026-09-06T18:40:00Z | `` | 0 |
| `L4-01-b-topologia-derivada.json` | 2026-09-07T02:06:10Z | `e368425f2b2d62536423bdc684754719c78c009f` | 11 |
| `L4-01-d-atributos-de-rede.json` | 2026-09-10T23:19:35Z | `` | 8 |
| `L4-01-e-dicionario-unidades-bdgd.json` |  | `` | 0 |
| `L4-01-f-alcance-do-tracado-rede-real.json` |  | `` | 0 |
| `L4-01-h-alinhamento-inspire-gnm.json` | 2026-09-07T01:52:08Z | `c45afa719d04e4fde74d48a21e1306af12e12608` | 7 |
| `L4-02-a-conectado-e-subrede.json` |  | `` | 0 |
| `L4-02-b-montante-jusante.json` |  | `` | 0 |
| `L4-02-c-isolamento.json` |  | `` | 0 |
| `L4-02-d-lacos-e-caminho-curto.json` |  | `` | 0 |
| `L4-02-e-configuracoes-de-tracado.json` |  | `` | 0 |
| `L4-03-a-regras-de-conectividade.json` | 2026-09-07T01:55:00Z | `ac7da355c84c6534fef98bce05e5a3552e935ea7` | 8 |
| `L4-03-d-areas-sujas-e-validacao.json` | 2026-09-07T13:20:00Z | `12edbce60d62748860fe6e8e216fb44bef1118b3` | 12 |
| `L4-04-a-controladores-e-tiers.json` | 2026-09-07T21:03:16Z | `dee045fd19bd` | 5 |
| `L4-04-b-atualizar-e-exportar-subrede.json` | 2026-09-07T22:07:05Z | `dffb1b6b79882e046969d34c3d6a4318dda201cd` | 12 |
| `L4-04-c-sumarios-por-subrede.json` | 2026-09-07T23:08:10Z | `7faf15623e025ae1301e75a5e337e3147d478486` | 12 |
| `L4-04-c-unificar-subrede-sintetica.json` | 2026-09-08T02:47:46Z | `9beaf63541e4` | 3 |
| `L4-04-c-unificar-subrede.json` | 2026-09-08T02:47:34Z | `7a12cd420e76d78235317c8eb7c65b3070af7b88` | 10 |
| `L4-04-d-diagrama-esquematico.json` | 2026-09-08T12:01:55Z | `81d6a9fdc9c985388b4c08657d0ec65da97215e9` | 12 |
| `L4-05-a-exportar-opendss.json` | 2026-09-16T08:46:33Z | `27b245ae2eac9f649837f182c6326c431f59cb37` | 6 |
| `L4-05-c-pandapower-e-matpower.json` |  | `` | 0 |
| `L4-05-d-epanet-inp.json` | 2026-09-07T18:04:02Z | `0ac39f7e2de0` | 16 |
| `L4-05-e-gas-e-esgoto.json` |  | `` | 0 |
| `L4-05-g-osm-power.json` |  | `` | 0 |
| `L4-06-d-categorias-e-restricoes.json` | 2026-09-07T01:54:37Z | `35e675650e98cae27e089003debed8cd547c613f` | 7 |
| `L4-18-rede-simples-trace-network.json` | 2026-09-07T20:03:42Z | `b71c0e853deb` | 9 |
| `L4-20-consumidores-e-enderecos.json` | 2026-09-08T19:12:55Z | `610896979710` | 3 |
| `L4-23-isolamento-por-inquilino-na-rede.json` | 2026-09-07T13:11:02Z | `c239e09b978d` | 5 |
| `L4-27-curto-circuito-e-protecao.json` | 2026-09-08T11:06:02Z | `3294fb325c22e4991a76305df08e2a7a686e1b18` | 11 |
| `L4-28-identificadores-e-numeracao.json` | 2026-09-06T22:15:00Z | `` | 0 |
| `L4-29-regras-de-atributo-de-rede.json` | 2026-09-08T19:58:30Z | `610896979710` | 3 |
| `L4-parcelas-01-modelo-de-parcelas.json` | 2026-09-08T21:13:13Z | `610896979710` | 3 |
| `L4-parcelas-02-fluxos-cogo.json` | 2026-09-08T23:09:42Z | `610896979710` | 3 |
| `L4-parcelas-03-ajuste-e-qualidade.json` | 2026-09-09T02:58:13Z | `7e3a18ddaff5` | 3 |
| `L5-01-a-layout-paginas.json` | 2026-09-07T13:59:10Z | `06f42417aea7` | 7 |
| `L5-01-c-widgets-dado.json` | 2026-09-08T11:57:59Z | `58147bf0383c` | 7 |
| `L5-01-e-acoes-configuraveis.json` | 2026-09-08T11:24:29Z | `a7fc3da0a2e4` | 7 |
| `L5-03-form-builder.json` | 2026-09-10T22:02:03Z | `bb4ea4c081b8` | 1 |
| `L5-04-a-blocos-de-conteudo.json` | 2026-09-08T02:05:15Z | `9ac92cde4a8b` | 4 |
| `L5-04-c-temas-capa-colecao.json` | 2026-09-08T20:42:11Z | `610896979710` | 11 |
| `L5-05-documento-versoes.json` | 2026-09-07T15:29:29Z | `ec2f1ecb2ff7` | 1 |
| `L5-06-motor-widgets.json` | 2026-09-07T19:25:15Z | `2063fbdf0ad6` | 2 |
| `L5-07-fontes-vistas-mensagens.json` | 2026-09-08T11:03:19Z | `81cd80e2b9d2` | 7 |
| `L5-08-editor-arrasto.json` | 2026-09-07T15:32:56Z | `dfe958009bda` | 6 |
| `L5-09-desfazer-refazer-rascunho.json` | 2026-09-07T15:21:47Z | `e37443b01b38` | 9 |
| `L5-11-expressoes-no-navegador.json` | 2026-09-08T13:30:20Z | `84263e122105` | 9 |
| `L5-12-acessibilidade-i18n-construtores.json` | 2026-09-07T15:34:35Z | `dfe958009bda` | 6 |
| `L5-13-edicao-concorrente.json` | 2026-09-08T11:11:05Z | `36665b9a6d91` | 7 |
| `L5-14-publicacao-links-embed.json` | 2026-09-07T15:14:49Z | `325b004a38bd` | 1 |
| `L5-15-vista-movel-responsivo.json` | 2026-09-07T15:33:08Z | `2e75bab10bde` | 7 |
| `L5-20-sites-paginas-publicas.json` | 2026-09-08T12:06:31Z | `4486c56bf9cb` | 6 |
| `L5-31-construtor-de-camada-esquema.json` | 2026-09-07T15:25:01Z | `325b004a38bd` | 2 |
| `L5-32-vistas-de-camada.json` | 2026-09-08T11:50:11Z | `29c8fbc1a591` | 2 |
| `L5-36-widgets-personalizados-sdk.json` | 2026-09-09T04:07:05Z | `41b613c37e67` | 2 |
| `L5-37-pacotes-modelos-entre-inquilinos.json` | 2026-09-08T11:16:43Z | `02760fb91cd6` | 3 |
| `L6-01-b-view-so-leitura.json` | 2026-09-06T16:09:43Z | `90d03c07da0c` | 7 |
| `L6-01-c-tela-acervo.json` | 2026-09-07T18:11:16Z | `0f0af7c5af43` | 14 |
| `L6-01-e-assinatura-e-uso.json` | 2026-09-07T01:56:32Z | `67e2695f40d1` | 5 |
| `L6-01-h-frescor-verificacao.json` | 2026-09-06T17:54:54Z | `90d03c07da0c` | 8 |
| `L6-01-i-raster-e-arquivos.json` | 2026-09-08T12:17:02Z | `b9cff07c90ab` | 8 |
| `L6-01-j-multi-servidor.json` | 2026-09-07T02:35:39Z | `90d03c07da0c` | 5 |
| `L6-02-a-credencial-chamadores.json` |  | `` | 0 |
| `L6-02-a-credencial-redirect.json` | 2026-09-06T15:54:24Z | `` | 6 |
| `L6-02-b-wms-wmts.json` |  | `` | 8 |
| `L6-02-c-wfs-ogcapi.json` | 2026-09-06T16:27:50Z | `90d03c07da0c` | 6 |
| `L6-02-d-arcgis-rest-externo.json` |  | `` | 13 |
| `L6-02-h-csv-url-geojson-kml.json` | 2026-09-06T16:29:09Z | `90d03c07da0c` | 11 |
| `L6-02-i-google-sheets.json` | 2026-09-06T22:21:27Z | `976427944ee5` | 7 |
| `L6-02-j-bancos-externos.json` | 2026-09-08T06:35:31Z | `937865411946` | 6 |
| `L6-02-k-agendamento.json` | 2026-09-07T17:05:00Z | `642cf206344e` | 13 |
| `L6-02-m-catalogo-endpoints-brasil.json` | 2026-09-07T21:50:44Z | `a23565190ce4` | 12 |
| `L6-02-o-importacao-exportacao-formatos.json` | 2026-09-07T18:48:28Z | `086408f7e849` | 4 |
| `L6-03-paridade-conectores.json` | 2026-09-07T21:59:33Z | `5e89faa4268e` | 2 |
| `L6-04-acervo-no-motor.json` | 2026-09-07T13:18:19Z | `92c7b2975d77` | 15 |
| `L6-06-descoberta-csw.json` | 2026-09-07T21:13:01Z | `9376e14718f5` | 6 |
| `L7-01-a-compose-perfis.json` | 2026-09-07T16:10:00Z | `642cf206344e` | 0 |
| `L7-01-c-dado-demonstracao.json` | 2026-09-07T16:16:07Z | `642cf206344e` | 5 |
| `L7-01-c-dado-demonstracao.semeadura.json` |  | `` | 0 |
| `L7-01-d-instalador-extensoes.json` | 2026-09-07T22:44:38Z | `4391f30d7b48` | 4 |
| `L7-03-a-antivirus-upload.json` | 2026-09-07T22:29:21Z | `5e89faa4268e` | 3 |
| `L7-03-b-rate-limit-abuso.json` | 2026-09-07T15:10:00Z | `325b004a38bd77d4b592a6b10093dfc6557e9fac (medido sobre este commit, antes do commit do item)` | 9 |
| `L7-03-d-injecao-consulta.json` | 2026-09-07T22:44:50Z | `70fe3e489b83` | 7 |
| `L7-03-e-cabecalhos-csp-tls.json` |  | `` | 5 |
| `L7-04-a-manual-capturas-geradas.json` | 2026-09-08T19:18:39Z | `610896979710` | 4 |
| `L7-04-d-videos-por-tarefa.json` |  | `` | 0 |
| `L7-06-a-metricas-exporters.json` | 2026-09-07T14:30:00Z | `325b004a38bd77d4b592a6b10093dfc6557e9fac` | 6 |
| `L7-06-b-alertas.alertas_prometheus.json` |  | `` | 0 |
| `L7-06-b-alertas.json` |  | `b120b1c401d9ec3e6ec44d9b859492768187f563` | 10 |
| `L7-06-c-logs-consulta-req-id.json` |  | `` | 0 |
| `L7-06-d-paineis.json` |  | `` | 0 |
| `L7-07-b-replica-garage.json` | 2026-09-08T01:52:11Z | `5e89faa4268e` | 13 |
| `L7-08-b-sdk-python.json` |  | `` | 11 |
| `L7-08-c-sdk-js.json` | 2026-09-08T06:59:28Z | `2d7004dcd3eb` | 22 |
| `L7-08-d-portal-api-chaves.json` | 2026-09-06T18:06:41Z | `90d03c07da0c` | 14 |
| `L7-11-b-appliance-sem-internet.json` | 2026-09-08T02:50:11Z | `9ac92cde4a8b` | 9 |
| `L7-11-c-telemetria-opcional.json` | 2026-09-08T06:05:00Z | `9ac92cde4a8b` | 3 |
| `L7-13-a-chamados.json` | 2026-09-08T23:23:22Z | `610896979710` | 1 |
| `L7-19.json` |  | `` | 32 |
| `L7-20-trilha-auditoria.json` | 2026-09-06T18:07:29Z | `90d03c07da0c` | 12 |
| `L7-26-cdn-tiles.json` |  | `` | 0 |
| `L7-29-roteiro-demonstracao.json` | 2026-09-08T20:29:08Z | `610896979710` | 15 |
| `L7-31-homologacao.json` | 2026-09-06T11:00:00Z | `pendente-do-commit-deste-item` | 7 |
| `L7-33-modo-somente-leitura.json` | 2026-09-07T14:34:21Z | `88ed424c53b2` | 1 |
| `L7-34-saude-profunda.json` | 2026-09-07T14:56:00Z | `ca97dcb` | 15 |
| `UX-03.json` | 2026-09-07T23:15:06Z | `` | 1 |
| `UX-10-acervo-sem-tela.json` | 2026-09-08T02:41:35Z | `3315d92ab839` | 4 |
| `UX-12-categorias-sem-controle.json` | 2026-09-08T06:01:10Z | `798c21042da2` | 4 |
| `UX-13-conexoes-sem-controle.json` | 2026-09-08T06:16:13Z | `f69ae0e68ba5` | 4 |
| `UX-14-geocodificador-sem-tela.json` | 2026-09-08T10:31:22Z | `8a352d4c11ce` | 4 |
| `UX-15-geocodificador-esri-sem-controle.json` | 2026-09-08T10:48:23Z | `82b3e16ba970` | 5 |
| `UX-16-ingestao-sem-tela.json` | 2026-09-08T11:07:25Z | `a7433b01aa04` | 4 |
| `UX-17-login-sem-controle.json` | 2026-09-08T11:32:24Z | `c3375706181c` | 5 |
| `UX-18-plataforma-sem-tela.json` | 2026-09-08T11:39:03Z | `aa1ed7c813c6` | 4 |
| `_prova_garage_chave_s3.json` |  | `` | 0 |
| `_prova_segredos_bruta.json` |  | `` | 0 |
| `adv-g3-tela.json` |  | `` | 0 |
| `adv-g3-vertices.json` |  | `` | 0 |
| `corrida-camada-schema.json` | 2026-09-07T02:47:32Z | `90d03c07da0c` | 1 |
| `fk-por-inquilino.json` | 2026-09-06T19:17:23Z | `76d44dbd7661` | 7 |
| `semente_dado_demo.json` |  | `` | 0 |

Todo número em documento sai desses arquivos, com o comando que o gerou.

## Ledger (últimos registros)

- {"quando": "2026-09-16T07:17:43Z", "item": "L7-13-a-chamados", "estado": "refutado", "nota": "adversario T9 L7-2: _verificar_anexo so varre dados[:65536] com teto de 8 MB — PNG terminando no byte 65536 esconde script; xfail test_l7_adv2_chamados_anexo_janela_de_varredura_truncada.py", "commit": "d51341a97", "sessao": "worktrees-2"}
- {"quando": "2026-09-17T21:48:25Z", "turno": 9, "evento": "reversao da promocao em massa de 11/09 (erro declarado pelo dono): 154 itens de entregue para o estado anterior; 30 itens tentando mortos devolvidos a pendente", "sessao": "fable-coordenador"}
- {"quando": "2026-09-17T22:26:59Z", "turno": 9, "evento": "remedicao L0-L3 contra master b81e2c788e65: 15 refutados provados verdes e promovidos COM sha e comando de prova", "sessao": "fable-coordenador"}

## Notas do estado

Texto do `estado.json` com nomes de cliente/parceiro neutralizados pelo script.

- 2026-09-05: laço criado a pedido do dono ('no token limit, no time limit, production, sem marcador de pendência, drag-and-drop everything, utility networks'). Ativos reutilizados: SIG de teste interno (tenant/RLS/FeatureServer), plataforma/pipeline (COG/STAC/TiTiler/Garage), motor logístico (25 fatores), tracado-lt motor (322 camadas), geoapp (conectores globais keyless), BDGD 2024 (101 distribuidoras), acervo.* (376 fontes).
- 2026-09-05 T1: DNS A plat.iagrointel.com (DNS-only) criado via API Cloudflare; certbot emitiu certificado (expira 2026-12-04); bloco nginx inicial 503 com X-Robots-Tag noindex; venv do repo com pytest 9.1.1 + pytest-playwright.
- 2026-09-05 T1: pergunta do dono 'isso é TUDO para produção?'. Resposta: não — acrescentados 19 itens (admin/org, SSO, metadado ISO/CSW, relações e regras de atributo, geocodificação e rota, impressão, versionamento e sync, tempo real, analítica grande, notebooks, estruturas de rede, observabilidade, alta disponibilidade, SDK/webhooks, medição e cobrança, i18n/acessibilidade, appliance, LGPD, suporte); cada item ainda se subdivide em -a/-b quando trabalhado. Produção final depende de todos.
- 2026-09-05 T1 (esri, handoff 21_esri.md, 92 URLs testadas): doc 'latest' da Esri é a 12.1; usar série 11.4 versionada como alvo. Para L0-02: ADR tem de declarar limiares de senha (Esri: ≥8 com letra e número, lockout 5 tentativas/15 min), expiração de sessão/token (generateToken máx. 14 d, padrão 120 min), MFA TOTP por membro. Para L0-03: acrescentar sub-itens pastas hierárquicas, favoritos, proteção contra exclusão, status authoritative/deprecated e LIXEIRA (Enterprise não tem — irritação nº 5 da migração); 'link por token' tem de negar após revogação. Paridade-alvo L0-02 (16 linhas) e L0-03 (18 linhas) já escrita no handoff para o adversário cobrar.
- 2026-09-05 T1 13:2x: limite de sessão da API (429, reset 15h UTC) derrubou 4 agentes no meio (cronista com .md sem commit; decomposição L1 e L2 sem saída; L3L6 com JSON de 61 itens pronto e conceito parcial). Conta trocada pelo dono (/login) e agentes relançados/retomados. Regra: decompositor grava JSON incrementalmente antes do conceito; o driver segue medindo sem modelo quando o modelo falta.
- 2026-09-05 T2: decomposição integrada — 444 itens novos (7 esboços de dependência externa), total 501; conceitos em laco/decomposicao/*_CONCEITO.md (L0 20 · L1 20 · L2 20 · L3L6 27 · L4 17 · L5 25 · L7 18 decisões). L7-05 depende de todos.
- 2026-09-05 T2 ~18:25: 4ª interrupção por limite de API (reset 22h UTC) derrubou backend+frontend do catálogo, backend e adversário dos jobs; relogado 20:00 e retomados do disco. Recorrência: ~1 a cada 2 h com 5-7 agentes; o trabalho nunca se perdeu porque tudo vai a disco.
- 2026-09-05 T2 20:30: PLAT_SEMENTE_DEMO retirado do .env deste servidor (decisão do gerente) — a função plat.jobs_semear_demo (014) fica desligada por padrão e o e2e dos 1.000 jobs PULA com razão escrita; ligar só em ambiente de desenvolvimento pelo install.sh.
- 2026-09-06 10:51: achado do L0-10 para o item LDAP (ainda em construcao): funcoes ldap.* sem REVOKE EXECUTE FROM PUBLIC; migracao 025_provedor_ldap.sql ainda sem commit no momento da checagem - conferir quando LDAP fechar.
- 2026-09-06 11:04: disco conferido apos alerta do L2-11-c - queda de 12->7,7GiB NAO e de agentes deste laco (so 2 containers pequenos, plat-worker-container e plat-osrm-guarulhos); resto (compasso-*, iagro-grafana/prometheus, osrm-edpes/segundo SIG de teste interno/buslog) e de outros projetos no mesmo servidor compartilhado, nao tocado.
- 2026-09-06 13:42: migracao 030_conexao.sql tinha sha registrado divergente do arquivo (bloqueava db/migrar.sh para TODAS as trilhas) - reconciliado: tabela ja batia com o arquivo atual (idempotente), sha re-registrado, migrar.sh volta a rodar limpo (34 iguais, 1 aplicada por outra trilha, 0 pendentes).
- 2026-09-06 13:48: falso alarme investigado - make check-rapido (check2.log) deu 36 failed/165 errors, TODOS em test_cruzado.py por esgotamento de cota de token do usuario demo (usuario_id=1 bateu no limite de 20 tokens ativos): uma trilha em andamento (L6-02-l/L6-05, conexao/ingestao) criou 16 tokens 'smoke-ingestao' manualmente em rajada de 3 min sem revogar. Nao e regressao de codigo. Revogados os 16 tokens leaked (usuario_id=1 volta a 1 token ativo); make check deve rodar limpo agora. Nenhuma mudanca de codigo necessaria - script de smoke manual de outra trilha deveria revogar apos uso, mas nao bloqueia entrega do item.
- 2026-09-06 14:04: migracao 030_conexao reconfirmada convergente (36 iguais, 0 pendentes) apos o agente L6-02-l ter aplicado 036 manualmente - nao e mais bloqueio.
- 2026-09-06 14:05: suite completa (nao-lento) rodada pelo agente L6-02-l/L6-05 apos fila do flock esvaziar: 30 falhas, NENHUMA relacionada a conexao/proveniencia (confirmado por grep). Falhas pertencem a outras trilhas ja em andamento/commitadas: amc_versao_* (SECURITY DEFINER com GRANT PUBLIC vazando - pego pelo proprio teste de guarda), /api/importacoes e /ogc/records (gap de cobertura cruzada A->B), contrato do endpoint /saude, app.limites.PERFIL_IDIOMAS (trilha de config da organizacao). Precisa de agente dedicado para investigar e fechar antes do proximo make check completo - registrado como pendencia, nao bloqueia o laco.
- 2026-09-06 14:14: OUTRA SESSAO Claude (dev-41, socket uds:/tmp/cc-socks/1641034.sock) trabalha no MESMO laco em worktrees separados (/home/dev/plataforma/wt/{garage,stac,valida,amc}, ramos wt/*), ainda nao mergeados em master. Ela commitou c311aa7 em master (conserto real: RealDictCursor ao inves de CursorSchemaAmbiente nas 12 conexoes cruas da suite fazia SQL com 'plat.' literal ignorar PLAT_SCHEMA - isolamento de homologacao/trilha nao valia para a suite; verificado no git log, sem-op em producao) e construiu laco/trilha_ambiente.sh (schema plat_t<nome> proprio por trilha, sem disputar o flock do .pytest.lock - mesma maquina do L7-31/make homolog, parametrizada). COLISAO DE MIGRACAO JA ACONTECEU: minha 043_acervo_licenca.sql (commit do L6-01-g) e o wt/garage dela (042 local, viraria 043 no merge) bateram - avisei por SendMessage, tail atual e 043, proximo livre 044 mas confirmar de novo na hora de cada merge. Arquivos quentes compartilhados: app/main.py, app/jobs/tipos.py, CHANGELOG.md - ultimo toque foi meu cb8fa15. Disco: / 44G livres (91%), /mnt/pgdata 43G livres (94%). Vou adotar trilha_ambiente.sh para agentes novos que so precisam pytest unidade/API, mantendo flock so para quem precisa do schema plat de producao ou e2e contra o servico vivo.
- 2026-09-06 14:18: coordenacao com dev-41 (outra sessao, wt/*): sem numero de migracao reservado (garage e amc confirmam de novo na hora do merge, nenhum agora); adversarios reprovaram L1-01-b-validacao-raster (SSRF via VRT aninhado, XML>1MiB, NaN quebra jsonb) e ja tinhamos L2-10-c-linguagem-expressao refutado (confirmado igual dos dois lados). Bloqueio de login (tenant plataforma id=3, totp_ativo=true de proposito - superadmin real) aconteceu de novo por falta de PLAT_SECRET em algum teste - desbloqueado de novo (UPDATE bloqueado_ate=NULL). Suspeita de origem do 401 codigo_invalido: fixture de sessao batendo em tenant plataforma por engano ou corrida entre trilhas no mesmo usuario real - nao e regressao de codigo nosso, test_acervo.py usa plat.auth_login() direto (sem HTTP/TOTP).
- 2026-09-06 14:23: achado independente sobre o 401 codigo_invalido que dev-41 isolou (sessao_plat/conftest.py): CREDENCIAIS_TOTP era caminho fixo (tests/credenciais_totp.txt), NAO seguia PLAT_CREDENCIAIS_ARQUIVO como CREDENCIAIS - ou seja mesmo sob trilha_ambiente.sh (que so parametriza credenciais.txt, nao credenciais_totp.txt) a corrida continuaria na 1a vez que cada trilha ligasse 2FA. Corrigido: PLAT_CREDENCIAIS_TOTP_ARQUIVO no mesmo padrao, commit a34e745 (arquivo unico, verificado por import direto que o override funciona e o default fica identico). ATENCAO: no processo de commitar isso eu errei - rodei 'git commit -m' sem escopo de arquivo e ele varreu TODO o indice compartilhado, incluindo 11 arquivos ja staged pelo agente L0-02-g-perfil-usuario (ainda rodando) que nao tinha terminado. Corrigido na hora com git reset --soft HEAD~1 (sem perda, HEAD nao tinha avancado) + git restore --staged nos 11 arquivos dele + git commit tests/api/conftest.py -m '...' (commit escopado so no meu arquivo). Nenhum dado perdido, mas fica registrado: em arvore compartilhada, commit tem de ser SEMPRE escopado por pathspec (git commit -- <arquivo>), nunca 'git commit -m' generico depois de um 'git add' pontual, porque outro agente pode ter coisa staged ao mesmo tempo.
- 2026-09-06 14:35: dev-41 achou 2a ocorrencia da mesma classe de bug do c311aa7: CursorSchemaAmbiente.execute so reescreve query tipo str, entao psycopg2.extras.execute_values (unico uso hoje: app/amc/unidades.py::gravar_feicoes) manda bytes e fura o isolamento de schema fora de producao (homolog/trilha), batendo em plat de producao com 'permission denied' disfarcado de erro de inquilino. Inofensivo em producao (schema padrao). Conserto vem no merge de wt/amc (deles) - registrado no SKILL.md como regra dura. Tambem confirmaram 1.000.175 celulas de grade AMC geradas de verdade (30,97s, desvio 0,201%) com os 43GB que liberaram - a extrapolacao declarada em L3-01-b-unidades vira medida quando isso mergear (nao mudo o estado do item ate o merge de verdade acontecer). 3o bloqueio de login do superadmin plataforma hoje (desbloqueado de novo por eles) - confirma que a dependencia da suite no superadmin real e um problema recorrente; combinei adotar trilha_ambiente.sh para agentes que rodem pytest, isso deve parar de acontecer para o meu lado gradualmente.
- 2026-09-06 14:40: RAM recuperada por dev-41 (disponivel 326MB -> 6,6GB, swap 8,2GB->4,5GB usados, fechando 13 sessoes paradas ha 12+ dias com autorizacao do dono, log em /home/dev/SESSOES_FECHADAS_20260906.md) - confirmado por free -h. Teto conjunto sobe para 4-5 por lado; subi o 4o agente (L0-07-d-smtp-convites).
- 2026-09-06 15:51: ADVERSARIO independente (papel novo desta sessao) atacou a linha L0-02 (identidade/sessao/2FA) ao vivo contra plat-api real (127.0.0.1:8150, bypass do rate-limit do nginx que ja e defesa separada) - 8 vetores testados (cookie cruzado, cookie+bearer, replay de TOTP entre desafios, dois desafios concorrentes, codigo de recuperacao de uso unico, desafio forjado, bloqueio por senha errada, escalada de escopo admin:inquilino via token) - TODOS PASSARAM, 0 achados. Pendencia nomeada para proxima rodada: corrida real entre 2 requests simultaneas no mesmo desafio (nao testada). Laudo completo em handoffs/T3/L0-02-ADVERSARIO.md. Usuarios de teste zt-adv-* apagados apos o ataque.
- 2026-09-06 15:54: ADVERSARIO independente atacou a linha isolamento-entre-inquilinos (containment de link publico entre itens irmaos do mesmo inquilino, revogacao imediata de link) - 3 vetores, 0 achados. Laudo em handoffs/T3/L0-02-e-ISOLAMENTO-ADVERSARIO.md. Pendencia nomeada: rotas de listagem/faceta e item publico por D24 ainda nao atacadas.
- 2026-09-06 15:59: ADVERSARIO independente atacou L0-07-d-smtp-convites (convite de membro + redefinicao de senha) - 6 vetores (uso unico do convite, cancelamento, token forjado, alteracao de email no link, rate limit de redefinicao, dominio de email) - TODOS PASSARAM, 0 achados. Laudo em handoffs/T3/L0-07-d-ADVERSARIO.md. Pendencias nomeadas: dominio de email restrito de verdade nao testado, e2e de navegador do item ainda pendente (RAM).
