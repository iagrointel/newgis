# Painel do laço PLATAFORMA ENTERPRISE

Gerado por `laco/gera_painel.py` de `laco/estado.json` em 2026-09-06 14:27 UTC. Não editar à mão: rode o script.

- Estado do laço: **ATIVO** · turno 3 · autoturno True
- Produto: codinome `plat` · nome público: PENDENTE (D18 do dono)
- URL interna: https://plat.iagrointel.com (noindex; nunca linkar de lugar público)
- Repositório: `/home/dev/plataforma/enterprise` · schema `plat` · role `plat_app` · portas 8150-8159 (api 8150, martin 8151, titiler 8152, worker 8153)
- Veredito do turno 3: pendente (gerente ainda não escreveu `99_veredito.md`); handoffs presentes: L0-02-bcd-verificacao.md, L0-02-ef, L0-02-ef.md, L0-02-g-perfil-usuario.md, L0-02g-L0-05c.md, L0-03-a-modelo-item.md, L0-04-ingest-vetor.md, L0-05-bd-verificacao.md, L0-05-e-worker-container.md, L0-07-a-config-org.md, L0-08-d-ldap.md, L0-09-metadado.md, L0-10-eventos.md, L0-11-arquivos-objetos.md, L0-12-contrato-api.md, L1-01-b-ADVERSARIO.md, L1-01-b-validacao-raster.md, L1-01-d-ADVERSARIO.md, L1-01-d-garage-por-inquilino.md, L2-01-a-basemap.md, L2-04-b-parser-where.md, L2-10-c-ADVERSARIO.md, L2-10-c-expressao-extensao.md, L2-10-c-expressao.md, L2-11-c-rota.md, L3-01-a-modelo-dado.md, L3-01-b-unidades.md, L5-05-documento.md, L6-01-a-procedencia.md, L6-01-a-registro.md, L6-01-d-ficha.md, L6-01-f-lgpd.md, L6-01-g-licenca-curada.md, L6-02-a-conexao.md, L6-02-l-saude, L6-02-l-saude.md, L6-05-proveniencia, L6-05-proveniencia.md, L7-03-b-antivirus.md, L7-03-f-cve.md, L7-14-apt.md, L7-15-release.md, L7-16-assinatura.md, L7-19-segredos.md, L7-31-homologacao.md, codex-L2-10-c

## Placar

Contagem por estado dos itens do backlog (lida do `estado.json`):

| estado | itens |
|---|---|
| entregue | 41 |
| parcial | 20 |
| tentando | 0 |
| refutado | 2 |
| pendente | 443 |
| **total** | **506** |

Placar registrado no estado (`placar`, atualizado pelo gerente no fim do turno): entregues 41, parciais 20, refutados 2, total 506, turnos 3.

Por linha:

| linha | itens | entregue | parcial | tentando | refutado | pendente |
|---|---|---|---|---|---|---|
| L0 fundação | 72 | 29 | 10 | 0 | 0 | 33 |
| L1 imagens | 65 | 0 | 1 | 0 | 1 | 63 |
| L2 plataforma | 100 | 2 | 1 | 0 | 1 | 96 |
| L3 motor AMC | 34 | 1 | 1 | 0 | 0 | 32 |
| L4 rede de utilidades | 66 | 0 | 0 | 0 | 0 | 66 |
| L5 builder | 61 | 1 | 0 | 0 | 0 | 60 |
| L6 conectores | 32 | 3 | 5 | 0 | 0 | 24 |
| L7 operação | 76 | 5 | 2 | 0 | 0 | 69 |

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

### L0-09-metadado-catalogo (parcial)

- Metadado ISO 19139 por item, validado offline contra o XSD oficial (sem tocar a rede); descoberta por OGC API Records, sempre autenticado por token com escopo.

### L0-02-a-login-sessao (entregue)

- Cláusulas cobertas pela identidade já entregue (`L0-02-tenant-auth`): cookie de sessão correto, expiração de 12 h/7 d e sessão nunca aparece em log.

### L0-02-b-politica-senha-bloqueio (entregue)

- Política de senha (mínimo/composição/histórico) e bloqueio de 5 falhas/15 min com desbloqueio pelo admin, provados de novo com evidência fresca.

### L0-02-c-2fa-totp (entregue)

- 2FA por TOTP com QR, replay recusado, código de recuperação de uso único, admin pode exigir 2FA por inquilino; segredo provado cifrado no banco por consulta direta (não só no cifrador).

### L0-02-d-token-servico (entregue)

- Token de serviço com escopo, restrição de IP/Referer com curinga, expiração até 365 d, revogação em ≤ 1 s, cada uso no log de acesso.

### L0-02-e-varredura-cruzada-rls (entregue)

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

### L0-03-e-compartilhamento (entregue)

- Compartilhamento em 5 níveis com link por token; revogação nega acesso em 30 ms.

### L0-03-f-tela-conteudo (entregue)

- Tela Conteúdo (lista/grade), 0 erro de console, primeira pintura 24 ms.

### L0-03-g-detalhe-item-miniatura (entregue)

- Detalhe do item com miniatura — acesso conferido antes de responder o formato.

### L0-03-h-lixeira-protecao-status (entregue)

- Lixeira de 30 dias, proteção e status; exclusão de item protegido ou com dependente é recusada (409).

### L0-03-i-dependencias (entregue)

- Dependência entre itens bloqueia exclusão até ser desfeita.

### L0-03-j-transferencia-dono (entregue)

- Transferência de dono, inclusive apagar o usuário de origem depois de transferir tudo.

### L0-03-k-favoritos-notificacoes (entregue)

- Favoritos no item; notificações ainda não construídas.

### L0-03-l-versoes-item (entregue)

- Versões de item imutáveis por sha256 — gravar por SQL direto é negado (permission denied).

### L0-04-b-inspecao (parcial)

- Job de inspeção do arquivo enviado: formato, CRS, campos, contagem, tipo de geometria — antes de qualquer confirmação do usuário.

### L0-04-c-tabela-camada (parcial)

- Tabela própria por camada (`d_<inquilino>.c_<id>`) com RLS obrigatória, geometria tipada e SRID.

### L0-04-d-formatos-base (parcial)

- 4 formatos de entrada nesta fatia: Shapefile (zip), GeoPackage, GeoJSON, CSV com latitude/longitude.

### L0-05-a-fila-postgres (entregue)

- Cláusulas cobertas pela fila já entregue (`L0-05-jobs`): unidade viva no `/saude`, 100 jobs sem duplicata, retentativa 2/4/8 s.

### L0-05-b-progresso-cancelamento (entregue)

- Log de 10 mil linhas resumido, limite de 10 conexões SSE por usuário com fechamento em 30 min, progresso sempre grampeado em 0-100 mesmo se o chamador mandar mais.

### L0-05-c-tela-tarefas (parcial)

- Tela Tarefas (lista/filtros/detalhe/log/agendas): defeito real achado por leitura de código — a visão de detalhe assina o SSE só na abertura e nunca reassina após o fechamento forçado de 30 min do servidor, ficando muda num job de execução longa; a lista se autorrecupera, o detalhe ainda não.

### L0-05-d-periodicos (entregue)

- 5 periódicos exigidos, todos vivos: expurgo de sessão, expurgo/compactação do catálogo, e agora também expurgo de sessão vencida e ANALYZE semanal das tabelas centrais.

### L0-07-a-configuracoes-org (parcial)

- Configurações da organização: nome, cor/logotipo, cota de armazenamento e de usuários, idioma e mapa padrão, política de senha/2FA — só o admin do inquilino acessa; cota de usuários agora barra criação nova (413) e a de armazenamento reflete na hora.

### L0-08-d-ldap (entregue)

- Login por LDAP/Active Directory por inquilino, mapeamento de grupo para perfil, provisionamento automático sem guardar a senha externa; diretório fora do ar nunca impede o login local.

### L0-10-eventos-historico (entregue)

- Toda rota que muda estado grava 1 evento (cobertura 100% das 75 rotas de escrita, medida); `plat_app` não consegue apagar nem alterar evento gravado.

### L0-11-arquivos-objetos (entregue)

- Guarda arquivo de cada inquilino em bucket próprio no Garage (chave de acesso e cota próprias, mirror de `tenant.cota_bytes`), nomeado pelo sha256 do conteúdo — nunca sobrescreve, nunca serve direto do Garage.
- `POST/GET/DELETE /api/arquivos[/{sha256}]` com upload multipart (iniciar/enviar/concluir/abortar); upload de corpo bruto exige token de serviço, não cookie de sessão (a mesma regra de CSRF que protege o resto da API).
- Varredura de objeto órfão e leitura de uso/cota por inquilino; dois inquilinos nunca leem o objeto um do outro (13 testes, incluindo ataque direto contra o Garage real: chave só-leitura tentando escrever, leitura cross-bucket).

### L0-12-contrato-api-e-limites (entregue)

- Documenta o contrato de API vivo em `docs/CONTRATO_API.md` (formato de erro, paginação, sem prefixo de versão na URL — o OpenAPI é o contrato) e gera `docs/LIMITES.md` a partir dos valores reais do código, nunca digitados à mão.
- Aplica limite de corpo (10 MiB padrão) com duas defesas: `Content-Length` grande demais recusa antes de ler; corpo em pedaços que mente o tamanho é contado byte a byte e cortado do mesmo jeito.

### L1-01-d-garage-por-inquilino (parcial)

- Balde próprio por inquilino no Garage: 6 cláusulas medidas; achado real ainda aberto — ListBuckets responde 200 com o próprio balde em vez de 403, e o bloco de rede ainda não está aplicado.

### L2-10-c-linguagem-expressao (refutado)

- Núcleo da linguagem de expressão (equivalente ao Arcade): 18 funções, dois avaliadores (Python e JavaScript) que concordam byte a byte em 41 casos de teste, sem `eval`/`exec` em nenhum dos dois; dois ataques de pilha achados e fechados.

### L2-11-c-rota-matriz-isocrona (parcial)

- Rota, matriz e isócrona por um OSRM próprio e isolado (dado só de uma área de teste); isócrona por grade de pontos + envoltória côncava, já que o OSRM não tem isso nativo.

### L3-01-a-modelo-dado (entregue)

- Modelo de dado do motor multicritério: 47 casos de teste (contados com --collect-only), hash independente confere, isolamento cruzado A→B provado.

### L3-01-b-unidades (parcial)

- Grade de unidades de análise do motor multicritério: 250 m/2.000 km² em 1,14 s com 1,175% de desvio — 1 milhão de células ainda não gerado de verdade (250.986 medidas, o resto extrapolado).

### L6-01-a-registro (entregue)

- Registro do acervo da casa exposto ao catálogo — só fontes com licença escrita aparecem.

### L6-01-d-ficha-fonte (parcial)

- Ficha de procedência por fonte do acervo: 10 campos, endpoints confirmados/vivos e nota de completude x/10 — campo ausente nunca é fabricado.

### L6-01-f-lgpd (parcial)

- Gate de LGPD no acervo: fonte com PII identificável (achada por varredura manual de 219 tabelas) exige confirmação explícita de risco antes de entrar no catálogo, senão recusa com 409.

### L6-01-g-licenca-curada (parcial)

- Licença curada do acervo: 29 fontes com licença ESCRITA testada por HTTP ao vivo (URL, evidência literal, confiança), amostra de 10 reconfirmada por curl independente; as que faltam (piso do portão é 40) ficaram de fora por motivo nomeado — sem termo escrito de verdade, não por atalho.

### L6-02-a-modelo-conexao-e-seguranca (entregue)

- Modelo de conexão externa (WMS/WFS/STAC/etc.) com defesa contra SSRF: IP privado, localhost e redirecionamento para rede interna são recusados na criação, não só no uso.

### L6-02-l-saude (parcial)

- Saúde de conexão externa: histórico das últimas 30 verificações, estado agregado (ok/degradado/fora/nunca testada), reteste automático a cada 15 min de qualquer conexão parada ou nunca testada, tela própria com selo ao vivo e botão "testar agora".

### L6-05-proveniencia-camada-externa (parcial)

- Ficha de proveniência de camada externa: lê a licença de verdade que cada serviço declara (WMS/WFS, ArcGIS REST, STAC/OGC API) e publica no catálogo com o crédito exato do serviço — provado com dois serviços vivos que declaram licenças diferentes.

### L5-05-documento-versoes (entregue)

- Modelo genérico de documento de construtor (grafo com nó imutável por ULID), sobre o mesmo mecanismo de versão do catálogo; hash canônico verificável fora do banco — o hash nativo do Postgres não era reproduzível externamente.

### L7-15-processo-release (entregue)

- Processo de release do zero até a decisão humana de publicar: changelog do git, suíte inteira, homologação, pacote assinado com o manifesto de homologação embutido — impossível forjar sem a chave privada.

### L7-16-assinatura-pacote (entregue)

- Assina e verifica pacote de atualização por Ed25519 (`scripts/assinar_pacote.sh` / `verificar_pacote.sh`); 1 byte adulterado é suficiente para a verificação recusar; chave privada nunca entra no repositório, só a pública em `deploy/chaves_publicas_release.txt`.

### L7-31-ambiente-homologacao (entregue)

- Ambiente de homologação isolado no mesmo banco (schema `plat_homolog`), migrações reaplicadas de forma independente; isolamento provado ao vivo com uma tabela de teste.

### L7-03-f-dependencias-cve-log-correcoes (parcial)

- Varre `requirements.txt` com `pip-audit` (`make seguranca-deps`, ainda fora do `check` principal) e falha com CVE crítico/alto sem exceção viva registrada; achado real do dia: CVE médio em `idna`, não bloqueia.

### L7-19-segredos-e-certificados (entregue)

- `PLAT_SECRET` e a senha do worker não moram mais em arquivo legível: saem por `LoadCredential=` do systemd (`/etc/plat/segredos/`, 0600, só o processo do serviço lê).
- Rotaciona qualquer segredo sem reinstalar (`scripts/rotacionar_segredo.sh`), com prova de que a senha antiga para de funcionar; `docs/SEGURANCA.md` documenta onde cada segredo mora e quando o certificado renova.

### L6-01-a-procedencia-acervo (entregue)

- Expõe o acervo da casa (376 fontes) como camadas assináveis só-leitura em `GET /api/acervo` e `GET /api/acervo/{fonte}`; só as 68 fontes com **licença escrita** aparecem — a view em si filtra, não é uma regra de tela.
- `POST /api/acervo/{fonte}/adicionar` cria um item de catálogo tipo conexão apontando para a fonte, sem copiar dado; herda a RLS e o compartilhamento do catálogo normal.

### L7-14-instalacoes-apt-desta-linha (entregue)

- Lista fechada de 7 pacotes apt (`deploy/pacotes_apt.txt`) instalada de forma idempotente pelo `install.sh` (`dpkg -s` antes e depois); pgRouting/pgstac e ezdxf/LibreDWG ficam fora de propósito (outro item / D23 em aberto).

### L0-05-e-worker-em-container (entregue)

- Worker também roda em contêiner Docker (imagem própria, memória do processo filho nunca excede o teto do cgroup); achado crítico corrigido: dentro do contêiner o worker é PID 1, o que quebrava silenciosamente a detecção de processo-pai morto.

### L7-03-b-antivirus-anexos (parcial)

- Confere a assinatura mágica real do arquivo contra o `Content-Type` declarado em todo upload (`POST /api/arquivos`, PUT único e multipart) e recusa divergência; ClamAV de verdade ainda não instalado (disco/RAM apertados, D21) — a interface já está pronta para trocar depois.

### L2-04-b-parser-where-ast (entregue)

- Parser de filtro próprio (`app/consulta/where_ast.py`): gramática fechada, nunca `eval`/`exec`, gera SQL sempre parametrizado contra uma lista branca de colunas — usado por qualquer rota futura que aceitar um filtro do usuário.
- 39 tentativas de injeção clássica (`; DROP TABLE`, tautologia `1=1`, campo fora da lista, injeção dentro de `IN`) todas neutralizadas como texto literal ou recusadas, nunca executadas.

### L2-01-a-basemap-local-pmtiles (entregue)

- Primeiro mapa real do produto: tela `/mapa` a tela cheia com MapLibre GL JS 4.7.1 lendo um PMTiles local (`web/dados/basemap/guarulhos.pmtiles`, recorte OSM ODbL 1.0, 18,3 MiB) servido pelo próprio nginx por Range HTTP — sem Martin, sem serviço de tiles dinâmico, sem chave de terceiro.
- Navegação (zoom/pan), escala, coordenadas do cursor e seletor de camada base (uma opção hoje, mecanismo pronto para a próxima); estilo cartográfico próprio dentro da identidade "instrumento".
- e2e prova 206/Content-Range sem gzip no nginx e a captura do mapa com mais de 50 cores distintas (mapa desenhado de verdade, não tela em branco); 0 erro de console.

### L0-14-identidade-visual (parcial)

- Tela de entrada redesenhada na direção "instrumento" (fundo quase preto, acento âmbar, Big Shoulders Display para rótulos, IBM Plex Sans/Mono para texto e dado, moldura com tique de canto); tokens em `web/estilo/tokens.css` com os três temas (claro/escuro/explícito).
- As outras 8 telas ainda usam o painel anterior — só a entrada foi convertida nesta fatia; ícones, página `/estilo`, contraste AA medido e o restante das telas ficam para o resto do item.

## Fronteira: o que o produto NÃO faz ainda

Uma linha por linha do produto. O que está `pendente` não existe na tela nem na máquina.

### L0 fundação

Deve fazer: repositório, identidade e acesso, catálogo por inquilino, ingestão de vetor, fila de trabalhos, cópia de segurança, administração da organização, SSO, metadado.

Não faz ainda (43 de 72 itens não entregues; pendentes 33): `L0-02-tenant-auth`, `L0-04-a-upload-arquivo`, `L0-04-b-inspecao`, `L0-04-c-tabela-camada`, `L0-04-d-formatos-base`, `L0-04-ingest-vetor`, `L0-13-dado-demonstracao`, `L0-14-identidade-visual`, `L0-02-g-checagem-privilegio-papel-id`, `L0-04-e-formatos-cad`, `L0-04-f-fgdb-parquet-fgb-gml`, `L0-04-g-atualizar-dados`, `L0-04-h-exportar`, `L0-05-c-tela-tarefas`, `L0-05-e-justica-entre-inquilinos`, `L0-05-jobs`, `L0-06-a-dump-logico`, `L0-06-c-restore-drill`, `L0-06-d-exportar-inquilino`, `L0-06-e-status`, `L0-07-a-configuracoes-org`, `L0-07-admin-org`, `L0-07-b-papeis-privilegios`, `L0-07-c-cotas-uso`, `L0-07-d-smtp-convites`, `L0-07-f-console-plataforma`, `L0-09-a-procedencia`, `L0-14-cli-admin`, `L0-15-marca`, `L0-04-j-camada-vista`, `L0-06-b-pitr-pgbackrest`, `L0-06-backup-status`, `L0-07-e-relatorios`, `L0-08-a-oidc`, `L0-08-b-saml`, `L0-08-e-mapeamento-provisionamento`, `L0-08-sso`, `L0-09-b-editor-iso-mgb`, `L0-09-c-xml-iso-validacao`, `L0-09-d-ogc-records-csw`, `L0-09-metadado-catalogo`, `L0-04-i-fonte-registrada`, `L0-08-c-govbr`.

### L1 imagens

Deve fazer: COG/STAC/tiles por inquilino, token de acesso, conectores Sentinel/NASA/Copernicus/MapBiomas, série temporal, IA na entrada.

Não faz ainda (65 de 65 itens não entregues; pendentes 63): `L1-01-a-pgstac-e-stac-api-por-inquilino`, `L1-01-b-validacao-e-isolamento-da-entrada`, `L1-01-c-conversao-cog-perfis-miniatura-estatisticas`, `L1-01-d-garage-por-inquilino`, `L1-01-ingest-raster`, `L1-02-a-servico-titiler-por-inquilino`, `L1-02-b-token-de-servico-com-escopo-por-lista`, `L1-02-c-wmts-xyz-tilejson-validados`, `L1-02-d-cache-nginx-cdn-e-bancada-de-carga`, `L1-02-f-predefinicoes-de-renderizacao-e-legenda`, `L1-02-tiles-token`, `L1-03-a-quadro-de-conectores-e-tela-sensores`, `L1-03-b-sentinel-2`, `L1-07-mosaico-por-colecao-e-pegadas`, `L1-12-linguagem-de-expressao-de-banda`, `L1-01-e-upload-grande-retomavel`, `L1-01-f-formatos-de-entrada`, `L1-01-g-raster-categorico-colormap-e-tabela-de-atributos`, `L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo`, `L1-01-j-proveniencia-da-imagem-lastro`, `L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro`, `L1-02-g-wms-1-3-0-raster`, `L1-02-h-ponto-estatisticas-e-histograma`, `L1-03-c-sentinel-1-sar`, `L1-03-conectores-sensores`, `L1-03-d-landsat`, `L1-03-e-mapbiomas`, `L1-03-f-cog-globais-por-vsicurl`, `L1-03-k-planetary-computer-e-stac-de-terceiros`, `L1-03-l-item-referenciado-sem-copia`, `L1-04-c-grafico-de-indice-por-poligono`, `L1-05-a-registro-de-modelo-e-proveniencia`, `L1-05-b-trabalhador-gpu-remoto`, `L1-08-regras-de-mosaico-e-selecao-de-pixel`, `L1-09-mascara-de-nuvem`, `L1-13-cadeia-de-funcoes-raster-ao-vivo`, `L1-14-analise-raster-em-lote-gera-item-novo`, `L1-15-estatistica-zonal`, `L1-16-derivados-de-terreno-e-terrain-rgb`, `L1-20-exportacao-recorte-e-massa`, `L1-23-cota-e-medicao-por-tb`, `L1-25-servico-de-imagem-esri-compativel`, `L1-27-ficha-de-metadado-e-licenca-da-imagem`, `L1-29-teste-no-arcgis-real-do-parceiro`, `L1-30-paridade-image-server-documento-vivo`, `L1-01-h-ingestao-em-lote-por-manifesto-e-cli`, `L1-02-i-ogc-api-tiles-e-maps`, `L1-03-h-clima-nasa-power-e-copernicus-cds`, `L1-03-n-comerciais-com-chave-do-cliente`, `L1-03-p-drone-ortomosaico-e-fotos-brutas`, `L1-03-q-lidar-copc-mdt-mds`, `L1-04-a-controle-de-tempo-cortina-e-lado-a-lado`, `L1-04-e-diferenca-entre-datas-e-tendencia`, `L1-04-serie-temporal`, `L1-05-c-mudanca-s2-calibrada`, `L1-06-rasters-do-acervo-em-cog`, `L1-10-camada-congelada-pmtiles`, `L1-21-wcs-2-0-1`, `L1-24-imagens-orientadas`, `L1-05-d-camadas-leves-edificacoes-e-vegetacao-em-faixa`, `L1-05-e-pacote-de-modelo-importavel`, `L1-05-ia-na-entrada`, `L1-19-multidimensional-netcdf-zarr`, `L1-05-f-amostras-e-rotulos-para-treino`, `L1-18-pansharpening-e-ortorretificacao-rpc`.

### L2 plataforma

Deve fazer: mapa web, simbologia, edição, serviços Esri-compatíveis e OGC, geoprocessamento, painéis, campo, migração de AGOL, 3D, relações e regras, geocodificação e rota, impressão, versionamento e sincronização, tempo real, analítica grande, notebooks.

Não faz ainda (98 de 100 itens não entregues; pendentes 96): `L2-01-a-documento-mapa`, `L2-01-b-martin-tiles-vetoriais`, `L2-01-c-lista-camadas-legenda`, `L2-01-d-popup-runtime`, `L2-01-e-mapas-base`, `L2-01-g-tabela-atributos`, `L2-01-h-selecao-filtros`, `L2-01-mapa-web`, `L2-02-a-modelo-estilo`, `L2-02-b-classificacao-servidor`, `L2-02-c-editor-simbologia-vetor`, `L2-02-d-rotulos`, `L2-02-simbologia`, `L2-03-a-api-edicao-transacional`, `L2-03-b-ferramentas-geometria`, `L2-03-c-formulario-atributos-runtime`, `L2-03-edicao`, `L2-04-a-leitor-rls-martin`, `L2-04-b-featureserver-catalogo-metadados`, `L2-04-c-featureserver-query`, `L2-04-d-featureserver-edicao-anexos`, `L2-04-g-ogc-api-features-crs-cql2`, `L2-04-j-conformidade-clientes-e-paridade`, `L2-04-servicos-esri-ogc`, `L2-05-a-catalogo-ferramentas-gpserver`, `L2-05-b-vetor-basico`, `L2-05-c-sobreposicao-agregacao`, `L2-06-e-estatisticas-servidor`, `L2-10-a-dominios-subtipos`, `L2-10-c-linguagem-expressao`, `L2-01-f-navegacao-medicao-coordenadas`, `L2-01-i-graficos-de-camada`, `L2-01-j-comparacao-cortina-tempo`, `L2-01-k-desenho-anotacoes`, `L2-01-l-exportacao-do-mapa`, `L2-02-e-simbolos-sprites-glifos`, `L2-02-f-estilo-raster`, `L2-03-d-historico-restauracao`, `L2-03-e-anexos`, `L2-03-f-edicao-em-lote-calculo-campo`, `L2-04-e-vector-tile-server-tilejson`, `L2-04-h-wfs-2-gml`, `L2-05-d-grades-densidade-padroes-interpolacao`, `L2-05-e-raster-basico`, `L2-05-f-rede-isocrona-rota-ferramentas`, `L2-05-geoprocessamento`, `L2-06-a-modelo-painel-fontes`, `L2-06-b-elementos-basicos`, `L2-06-c-acoes-seletores-filtros-cruzados`, `L2-06-d-atualizacao-viva-sse`, `L2-06-paineis`, `L2-07-a-pwa-instalavel-cache`, `L2-07-b-formulario-de-coleta-xlsform`, `L2-07-c-fila-sincronizacao-idempotente`, `L2-08-a-leitor-portal-inventario`, `L2-08-b-clonar-camadas-hospedadas`, `L2-08-c-converter-web-map-e-estilo`, `L2-08-d-relatorio-migracao-e-exportacao-reversa`, `L2-08-migracao-agol`, `L2-10-b-relacionamentos`, `L2-10-d-regras-de-atributo`, `L2-10-relacoes-regras`, `L2-11-a-geocodificacao-csv`, `L2-11-b-geocodificador-brasil`, `L2-11-c-rota-matriz-isocrona`, `L2-11-geocodificacao-rota`, `L2-12-a-motor-render-servidor`, `L2-17-crs-transformacoes`, `L2-19-paridade-l2-e-manual`, `L2-04-f-mapserver-identify-legend-geometryserver`, `L2-04-i-wms-wmts-sld`, `L2-04-k-sync-replicas-esri`, `L2-07-campo`, `L2-07-d-mapa-offline-por-area`, `L2-09-3d`, `L2-09-a-terreno-terrain-rgb-relevo`, `L2-09-b-cena-extrusao-slides`, `L2-09-c-modelos-gltf-ifc-3dtiles`, `L2-12-b-layouts-elementos-exportacao`, `L2-12-impressao-layout`, `L2-13-a-versoes-ramo-reconciliar`, `L2-13-b-replicas-sincronizacao`, `L2-13-versionamento-sync`, `L2-14-a-ingestao-de-fluxos`, `L2-14-b-camada-viva-historico`, `L2-14-c-regras-alertas-incidentes`, `L2-14-tempo-real`, `L2-15-a-geoparquet-bucket-catalogo`, `L2-15-analitica-grande`, `L2-15-b-consultas-duckdb-em-escala`, `L2-18-camada-de-consulta-sql`, `L2-07-e-odk-central-ponte`, `L2-09-d-analise-3d-visibilidade`, `L2-12-c-series-de-mapas-lote`, `L2-16-a-sdk-python-geo`, `L2-16-b-jupyter-por-inquilino-isolado`, `L2-16-c-script-vira-ferramenta`, `L2-16-notebooks-scripts`.

### L3 motor AMC

Deve fazer: motor multicritério explicável como serviço, com robustez medida.

Não faz ainda (33 de 34 itens não entregues; pendentes 32): `L3-01-b-unidades`, `L3-01-c-extracao-fator`, `L3-01-d-transformacoes`, `L3-01-e-combinacao`, `L3-01-f-explicacao`, `L3-01-g-tela-motor`, `L3-01-j-equivalencia-motor-logistico`, `L3-01-motor-servico`, `L3-14-cobertura-dado-ausente`, `L3-01-h-presets`, `L3-01-i-exportacao-metodo`, `L3-04-restricoes`, `L3-06-criterios-de-feicao`, `L3-07-agregacao`, `L3-12-integracao-fluxo-e-api`, `L3-13-resultado-como-camada`, `L3-18-paridade-esri-amc`, `L3-02-a-monte-carlo-pesos`, `L3-02-b-sensibilidade-sobol-oat`, `L3-02-c-smaa`, `L3-02-d-comparacao-cenarios`, `L3-02-robustez`, `L3-03-ahp-pares`, `L3-05-localizar-regioes`, `L3-09-backtest-decisao-real`, `L3-10-corredor-custo-minimo`, `L3-11-fator-de-rede`, `L3-15-metadado-fator`, `L3-16-desempenho-escala`, `L3-08-pareto`, `L3-17-similaridade`, `L3-19-multiescala`, `L3-20-narrativa-de-resultado`.

### L4 rede de utilidades

Deve fazer: modelo de rede, traçado, edição com regras, sub-redes e diagramas, conectores BDGD/CIM, estruturas e regras avançadas.

Não faz ainda (66 de 66 itens não entregues; pendentes 66): `L4-01-a-pacote-de-ativos`, `L4-01-b-topologia-derivada`, `L4-01-c-importador-bdgd`, `L4-01-modelo-rede`, `L4-02-a-conectado-e-subrede`, `L4-02-b-montante-jusante`, `L4-02-c-isolamento`, `L4-02-tracado`, `L4-03-a-regras-de-conectividade`, `L4-03-c-edicao-topologica-no-mapa`, `L4-03-d-areas-sujas-e-validacao`, `L4-04-a-controladores-e-tiers`, `L4-04-b-atualizar-e-exportar-subrede`, `L4-05-a-exportar-opendss`, `L4-07-fluxo-de-potencia`, `L4-08-queda-de-tensao-e-carregamento`, `L4-23-isolamento-por-inquilino-na-rede`, `L4-01-d-atributos-de-rede`, `L4-02-d-lacos-e-caminho-curto`, `L4-02-e-configuracoes-de-tracado`, `L4-03-b-terminais`, `L4-03-e-versao-de-rede`, `L4-03-edicao-rede`, `L4-04-c-sumarios-por-subrede`, `L4-04-d-diagrama-esquematico`, `L4-05-b-cim-iec-61970-61968`, `L4-05-c-pandapower-e-matpower`, `L4-05-d-epanet-inp`, `L4-05-f-transmissao-sindat-sigel`, `L4-06-a-contencao`, `L4-06-b-estrutura-postes`, `L4-06-d-categorias-e-restricoes`, `L4-09-perdas-tecnicas-por-segmento`, `L4-10-continuidade-dec-fec`, `L4-11-gd-conectada-e-hospedagem`, `L4-12-inspecao-vegetacao-na-faixa`, `L4-13-integracao-telemetria`, `L4-16-api-rest-compativel-un`, `L4-21-qualidade-e-saude-da-rede`, `L4-22-desempenho-em-escala`, `L4-24-cartografia-de-rede`, `L4-01-h-alinhamento-inspire-gnm`, `L4-02-f-resultados-e-exportacao`, `L4-04-e-diagrama-camadas-e-contencao`, `L4-04-subredes-diagramas`, `L4-05-conectores-rede`, `L4-05-e-gas-e-esgoto`, `L4-05-g-osm-power`, `L4-05-h-inspire-utility-networks`, `L4-06-c-objetos-nao-espaciais`, `L4-06-estruturas-regras-avancadas`, `L4-14-balanco-de-energia-por-alimentador`, `L4-15-serie-temporal-da-rede`, `L4-17-migracao-de-un-e-rede-geometrica`, `L4-18-rede-simples-trace-network`, `L4-19-planejamento-de-linha-nova`, `L4-20-consumidores-e-enderecos`, `L4-25-cenarios-e-se`, `L4-26-inspecao-de-campo-do-ativo`, `L4-27-curto-circuito-e-protecao`, `L4-28-identificadores-e-numeracao`, `L4-29-regras-de-atributo-de-rede`, `L4-parcelas-01-modelo-de-parcelas`, `L4-parcelas-02-fluxos-cogo`, `L4-30-manual-e-tour-de-rede`, `L4-parcelas-03-ajuste-e-qualidade`.

### L5 builder

Deve fazer: construtores arrasta-e-solta de aplicação, fluxo, formulário e narrativa.

Não faz ainda (60 de 61 itens não entregues; pendentes 60): `L5-01-a-layout-paginas`, `L5-01-b-widgets-mapa`, `L5-01-c-widgets-dado`, `L5-01-e-acoes-configuraveis`, `L5-02-a-editor-de-nos`, `L5-02-b-execucao-proveniencia`, `L5-03-a-construtor-elementos`, `L5-03-b-logica-condicional-calculo-restricao`, `L5-06-motor-widgets`, `L5-07-fontes-vistas-mensagens`, `L5-08-editor-arrasto`, `L5-11-expressoes-no-navegador`, `L5-14-publicacao-links-embed`, `L5-26-construtor-popup`, `L5-01-app-builder`, `L5-01-d-widgets-pagina-menu`, `L5-01-f-modelos-app-galeria`, `L5-02-c-agendamento-variaveis`, `L5-02-d-exportar-python-importar-json`, `L5-02-f-fluxo-como-ferramenta-e-api`, `L5-02-fluxos`, `L5-03-c-dominios-listas-cascata`, `L5-03-d-repeticoes-relacionadas-anexos`, `L5-03-e-xlsform-ida-e-volta-idiomas`, `L5-04-a-blocos-de-conteudo`, `L5-09-desfazer-refazer-rascunho`, `L5-10-temas-marca`, `L5-12-acessibilidade-i18n-construtores`, `L5-15-vista-movel-responsivo`, `L5-17-painel-elementos-avancados`, `L5-18-painel-parametros-url-vistas`, `L5-20-sites-paginas-publicas`, `L5-21-dados-abertos-catalogo-publico`, `L5-23-apps-instantaneos-motor-galeria`, `L5-24-apps-instantaneos-modelos-1`, `L5-27-simbologia-por-arrasto`, `L5-29-construtor-relatorio-pdf`, `L5-31-construtor-de-camada-esquema`, `L5-33-a-diagrama-de-trabalho`, `L5-33-b-modelos-e-trabalhos`, `L5-39-paridade-l5-e-manual`, `L5-02-e-iteradores-condicionais`, `L5-03-form-builder`, `L5-04-b-imersivos-sidecar-tour-swipe`, `L5-04-c-temas-capa-colecao`, `L5-13-edicao-concorrente`, `L5-19-painel-expressoes-de-dado-tempo-real`, `L5-22-sites-dominio-proprio-tema`, `L5-25-apps-instantaneos-modelos-2`, `L5-28-galeria-simbolos-rampas-estilos`, `L5-30-relatorio-lote-agendado`, `L5-32-vistas-de-camada`, `L5-33-c-atribuicao-avancada-indicadores`, `L5-34-captura-rapida-designer-pwa`, `L5-36-widgets-personalizados-sdk`, `L5-37-pacotes-modelos-entre-inquilinos`, `L5-04-storymap`, `L5-16-agente-escreve-configuracao`, `L5-35-missao-operacao-ao-vivo`, `L5-38-importadores-configuracao-esri`.

### L6 conectores

Deve fazer: acervo da casa e conectores vivos.

Não faz ainda (29 de 32 itens não entregues; pendentes 24): `L6-01-b-view-so-leitura`, `L6-01-f-lgpd`, `L6-01-g-licenca-curada`, `L6-01-acervo-casa`, `L6-01-c-tela-acervo`, `L6-01-d-ficha-fonte`, `L6-01-e-assinatura-e-uso`, `L6-02-b-wms-wmts`, `L6-02-c-wfs-ogcapi`, `L6-02-d-arcgis-rest-externo`, `L6-02-g-pmtiles-xyz-tilejson`, `L6-02-h-csv-url-geojson-kml`, `L6-02-k-agendamento`, `L6-02-m-catalogo-endpoints-brasil`, `L6-03-paridade-conectores`, `L6-04-acervo-no-motor`, `L6-01-h-frescor-verificacao`, `L6-01-i-raster-e-arquivos`, `L6-02-conectores-vivos`, `L6-02-e-stac-externo`, `L6-02-f-geoparquet-duckdb`, `L6-02-i-google-sheets`, `L6-02-j-bancos-externos`, `L6-02-l-saude`, `L6-02-n-etl-na-entrada`, `L6-02-o-importacao-exportacao-formatos`, `L6-05-proveniencia-camada-externa`, `L6-01-j-multi-servidor`, `L6-06-descoberta-csw`.

### L7 operação

Deve fazer: instalador limpo, carga, segurança, manual e tour, observabilidade, alta disponibilidade, SDK e webhooks, medição e cobrança, i18n e acessibilidade, appliance no cliente, LGPD, suporte, produção final.

Não faz ainda (71 de 76 itens não entregues; pendentes 69): `L7-01-a-compose-perfis`, `L7-01-b-instalacao-conteiner-limpo`, `L7-01-instalador-limpo`, `L7-03-a-antivirus-upload`, `L7-03-b-rate-limit-abuso`, `L7-03-c-ssrf-conectores`, `L7-03-d-injecao-consulta`, `L7-03-e-cabecalhos-csp-tls`, `L7-03-f-dependencias-cve-log-correcoes`, `L7-03-seguranca`, `L7-06-a-metricas-exporters`, `L7-06-b-alertas`, `L7-06-c-logs-consulta-req-id`, `L7-06-observabilidade`, `L7-20-trilha-auditoria`, `L7-33-modo-somente-leitura`, `L7-34-saude-profunda`, `L7-35-atualizacao-versao-assinada`, `D21 (dono)`, `L7-01-c-dado-demonstracao`, `L7-02-a-k6-cenarios`, `L7-02-b-pool-e-limites-por-inquilino`, `L7-02-carga`, `L7-03-g-asvs-nivel2-pentest`, `L7-04-a-manual-capturas-geradas`, `L7-04-b-tour-primeiro-acesso`, `L7-04-c-manual-admin-runbooks`, `L7-04-manual-e-tour`, `L7-06-d-paineis`, `L7-07-a-replica-postgres`, `L7-07-alta-disponibilidade`, `L7-07-b-replica-garage`, `L7-07-c-ensaio-failover`, `L7-08-a-webhooks-eventos`, `L7-08-b-sdk-python`, `L7-08-c-sdk-js`, `L7-08-d-portal-api-chaves`, `L7-08-sdk-api-webhooks`, `L7-09-a-medidor-diario`, `L7-09-b-planos-limites-relatorio`, `L7-09-medicao-cobranca`, `L7-10-a-i18n-pt-en-es`, `L7-10-b-acessibilidade-wcag21aa`, `L7-10-i18n-acessibilidade`, `L7-12-a-classificacao-retencao`, `L7-12-b-registro-tratamento-dpa-incidente`, `L7-12-lgpd-governanca`, `L7-17-capacidade-planejamento`, `L7-18-custo-por-inquilino`, `L7-21-pagina-status`, `L7-22-sla-e-incidentes`, `L7-23-pgbackrest-pitr`, `L7-24-drill-restauracao`, `L7-25-exportacao-inquilino`, `L7-26-cdn-tiles`, `L7-27-origem-br-soberania`, `L7-29-roteiro-demonstracao`, `L7-30-teste-parceiro-pro-agol`, `L7-03-b-antivirus-anexos`, `L7-04-d-videos-por-tarefa`, `L7-05-producao-final`, `L7-11-a-appliance-licenca`, `L7-11-appliance-cliente`, `L7-11-b-appliance-sem-internet`, `L7-11-c-telemetria-opcional`, `L7-13-a-chamados`, `L7-13-c-laco-agentico-suporte`, `L7-13-suporte-chamados`, `L7-14-extensoes-fdw`, `L7-28-iso27001-controles`, `L7-32-postgres-manutencao-versao`.

## Backlog: os itens por linha

Prioridade 1 = primeiro. `dep. abertas` = dependências ainda não entregues.

### L0 fundação (72 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L0-01-repo` | 1 | entregue | 1 | 1 | — | — |
| `L0-02-a-login-sessao` | 1 | entregue | 0 |  | — | — |
| `L0-02-b-politica-senha-bloqueio` | 1 | entregue | 0 |  | — | — |
| `L0-02-d-token-servico` | 1 | entregue | 0 |  | — | — |
| `L0-02-e-varredura-cruzada-rls` | 1 | entregue | 1 | 3 | — | — |
| `L0-02-f-tela-usuarios` | 1 | entregue | 1 | 3 | — | — |
| `L0-02-tenant-auth` | 1 | parcial | 1 | 2 | — | P3 (suíte inteira verde) depende da trilha B; P9 cronista em curso |
| `L0-03-a-modelo-item` | 1 | entregue | 1 | 3 | — | — |
| `L0-03-b-pastas-tags-categorias-classificacao` | 1 | entregue | 0 |  | — | — |
| `L0-03-c-busca` | 1 | entregue | 0 |  | — | — |
| `L0-03-catalogo` | 1 | entregue | 1 | 2 | L0-02-tenant-auth | — |
| `L0-03-d-grupos` | 1 | entregue | 0 |  | — | — |
| `L0-03-e-compartilhamento` | 1 | entregue | 0 |  | — | — |
| `L0-03-f-tela-conteudo` | 1 | entregue | 0 |  | — | — |
| `L0-03-g-detalhe-item-miniatura` | 1 | entregue | 0 |  | — | — |
| `L0-04-a-upload-arquivo` | 1 | pendente | 0 |  | — | — |
| `L0-04-b-inspecao` | 1 | parcial | 1 | 3 | L0-04-a-upload-arquivo | — |
| `L0-04-c-tabela-camada` | 1 | parcial | 1 | 3 | L0-04-b-inspecao | — |
| `L0-04-d-formatos-base` | 1 | parcial | 1 | 3 | L0-04-c-tabela-camada | — |
| `L0-04-ingest-vetor` | 1 | parcial | 1 | 3 | — | — |
| `L0-05-a-fila-postgres` | 1 | entregue | 0 |  | — | — |
| `L0-05-b-progresso-cancelamento` | 1 | entregue | 0 |  | — | — |
| `L0-10-eventos-historico` | 1 | entregue | 0 |  | — | — |
| `L0-11-arquivos-objetos` | 1 | entregue | 0 |  | — | — |
| `L0-12-contrato-api-e-limites` | 1 | entregue | 0 |  | — | — |
| `L0-13-dado-demonstracao` | 1 | pendente | 0 |  | L0-04-d-formatos-base | — |
| `L0-14-identidade-visual` | 1 | parcial | 1 | 2 | L0-02-tenant-auth | — |
| `L0-02-c-2fa-totp` | 2 | entregue | 0 |  | — | — |
| `L0-02-g-checagem-privilegio-papel-id` | 2 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L0-03-h-lixeira-protecao-status` | 2 | entregue | 0 |  | — | — |
| `L0-03-i-dependencias` | 2 | entregue | 0 |  | — | — |
| `L0-03-j-transferencia-dono` | 2 | entregue | 0 |  | — | — |
| `L0-04-e-formatos-cad` | 2 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L0-04-f-fgdb-parquet-fgb-gml` | 2 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L0-04-g-atualizar-dados` | 2 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L0-04-h-exportar` | 2 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L0-05-c-tela-tarefas` | 2 | parcial | 1 | 3 | — | TESTADOR T3: mecanismo em grande parte ja construido/testado pelo L0-05-jobs (pai): lista/filtros/detalhe/log/parametros/link de resultado/cancelar/agendas CRUD/admin-ve-tudo-usuario-ve-so-as-suas/1a pintura <=1s com 1000 jobs/visualizador so-leitura -- ver tests/e2e/test_tarefas.py (7 testes) + tests/api/jobs/*.py + capturas ja em disco (L0-05-jobs_lista.png e 8 outras). GAP REAL achado por leitura de codigo (bate quase literal com a propria refutacao do portao, 'deixa a aba aberta 2h'): web/js/jobs/detalhe.js assina o SSE 1 vez soh, na abertura (abrir(), linha ~227); o listener 'fim' (linhas ~148-152) so faz mostrarModo(null) e nunca reassina, mesmo quando o job continua rodando. Como o servidor forca o fechamento de TODO SSE aos 30 min (DURACAO_MAX_S=1800, app/jobs/eventos.py:24,142) mandando um 'fim' com o estado REAL (nao-final) + motivo 'reconecte', a tela de DETALHE fica muda/parada em qualquer job com mais de 30 min de execucao visto por /tarefas/<id> -- exatamente o cenario da refutacao. A tela de LISTA nao tem esse defeito: atualizarLinha() (web/js/jobs/lista.js:165) chama assinaturas() de novo sempre que o job chega com estado nao-final, entao ela se auto-recupera. Confirmado por leitura, nao reproduzido ao vivo (RAM da maquina ~550 MB livres + swap 100% cheio no momento desta verificacao -- rodar pytest/playwright novo era arriscado; nada foi executado, nenhum teste novo escrito). Confirmado tambem, por leitura, que 'repetir job de outro usuario' JA e bloqueado com seguranca (servico.repetir chama obter() primeiro, que aplica o filtro _filtro_dono por usuario_id p/ nao-admin -> 404; mesmo caminho de codigo do teste test_usuario_nao_admin_so_ve_os_proprios_jobs). Paginacao a 100 mil jobs (o numero mais duro da propria refutacao, o portao literal so pede 1.000) e arquitetonicamente solida (LIMIT/OFFSET+LIMITE_MAX no servidor, paginacao no cliente) mas nunca foi medida nessa escala -- pendencia registrada, nao bloqueante do portao como escrito. NAO fechar como entregue: falta consertar o reconector de detalhe.js (trilha backend/frontend) e medir 100 mil antes do veredito final. Ver handoffs/T3/L0-02g-L0-05c.md. |
| `L0-05-d-periodicos` | 2 | entregue | 0 |  | — | — |
| `L0-05-e-justica-entre-inquilinos` | 2 | pendente | 0 |  | L0-05-jobs | — |
| `L0-05-jobs` | 2 | parcial | 1 | 2 | — | 3 consertos em curso (semeadura e2e, perfil visualizador, Cache-Control) + P3 depende do commit do catálogo |
| `L0-06-a-dump-logico` | 2 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L0-06-c-restore-drill` | 2 | pendente | 0 |  | L0-06-a-dump-logico | — |
| `L0-06-d-exportar-inquilino` | 2 | pendente | 0 |  | L0-04-h-exportar | — |
| `L0-06-e-status` | 2 | pendente | 0 |  | L0-06-a-dump-logico | — |
| `L0-07-a-configuracoes-org` | 2 | parcial | 0 |  | — | GET/PUT /api/org + logotipo + cotas armazenamento/usuarios + politica senha/2FA exposta, tudo com RLS/privilegio org.configurar, 9 testes verdes, varredura cruzada e vocabulario de eventos atualizados; falta blocos de pagina inicial/galeria/banner-termo de acesso do portao completo do item |
| `L0-07-admin-org` | 2 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L0-07-b-papeis-privilegios` | 2 | pendente | 0 |  | — | — |
| `L0-07-c-cotas-uso` | 2 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L0-07-d-smtp-convites` | 2 | pendente | 0 |  | — | — |
| `L0-07-f-console-plataforma` | 2 | pendente | 0 |  | L0-07-c-cotas-uso | — |
| `L0-09-a-procedencia` | 2 | pendente | 0 |  | — | — |
| `L0-14-cli-admin` | 2 | pendente | 0 |  | L0-04-c-tabela-camada, L0-06-d-exportar-inquilino | — |
| `L0-15-marca` | 2 | pendente | 0 |  | L0-14-identidade-visual | — |
| `L0-02-g-perfil-usuario` | 3 | entregue | 3 | 3 | — | — |
| `L0-03-k-favoritos-notificacoes` | 3 | entregue | 0 |  | — | — |
| `L0-03-l-versoes-item` | 3 | entregue | 0 |  | — | — |
| `L0-04-j-camada-vista` | 3 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L0-06-b-pitr-pgbackrest` | 3 | pendente | 0 |  | L0-06-a-dump-logico | — |
| `L0-06-backup-status` | 3 | pendente | 0 |  | L0-04-ingest-vetor | — |
| `L0-07-e-relatorios` | 3 | pendente | 0 |  | L0-07-c-cotas-uso | — |
| `L0-08-a-oidc` | 3 | pendente | 0 |  | L0-07-a-configuracoes-org | — |
| `L0-08-b-saml` | 3 | pendente | 0 |  | L0-08-a-oidc | — |
| `L0-08-e-mapeamento-provisionamento` | 3 | pendente | 0 |  | L0-08-a-oidc | — |
| `L0-08-sso` | 3 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L0-09-b-editor-iso-mgb` | 3 | pendente | 0 |  | L0-09-a-procedencia | — |
| `L0-09-c-xml-iso-validacao` | 3 | pendente | 0 |  | L0-09-b-editor-iso-mgb | — |
| `L0-09-d-ogc-records-csw` | 3 | pendente | 0 |  | L0-09-b-editor-iso-mgb | — |
| `L0-09-metadado-catalogo` | 3 | parcial | 1 | 3 | — | ISO 19139 + OGC API Records entregues (offline, tenant-isolado); faltam ISO 19115-3, CSW, editor de metadado na tela, varredura cruzada automatica destas 2 rotas novas |
| `L0-04-i-fonte-registrada` | 4 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L0-05-e-worker-em-container` | 4 | entregue | 0 |  | — | — |
| `L0-08-c-govbr` | 4 | pendente | 0 |  | L0-08-a-oidc | — |
| `L0-08-d-ldap` | 4 | entregue | 0 |  | — | — |

### L1 imagens (65 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L1-01-a-pgstac-e-stac-api-por-inquilino` | 1 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L1-01-b-validacao-e-isolamento-da-entrada` | 1 | refutado | 1 | 3 | L0-05-jobs | adversário achou SSRF (VRT aninhado sai à rede e lê caminho fora do envio), leitura de só 1 MiB do XML do VRT, NoData NaN quebra a gravação do relatório em jsonb; 9 casos xfail(strict) em tests/unit/test_raster_validacao_adversario.py |
| `L1-01-c-conversao-cog-perfis-miniatura-estatisticas` | 1 | pendente | 0 |  | L1-01-b-validacao-e-isolamento-da-entrada, L1-01-d-garage-por-inquilino | — |
| `L1-01-d-garage-por-inquilino` | 1 | parcial | 1 | 3 | L0-02-tenant-auth | 6/6 cláusulas medidas; ListBuckets responde 200 com o próprio balde em vez de 403; bloco nginx escrito em deploy/ mas NÃO aplicado; adversário pendente |
| `L1-01-ingest-raster` | 1 | pendente | 0 |  | L0-05-jobs | — |
| `L1-02-a-servico-titiler-por-inquilino` | 1 | pendente | 0 |  | L1-01-a-pgstac-e-stac-api-por-inquilino, L1-01-d-garage-por-inquilino | — |
| `L1-02-b-token-de-servico-com-escopo-por-lista` | 1 | pendente | 0 |  | L0-02-tenant-auth, L1-02-a-servico-titiler-por-inquilino | — |
| `L1-02-c-wmts-xyz-tilejson-validados` | 1 | pendente | 0 |  | L1-02-b-token-de-servico-com-escopo-por-lista | — |
| `L1-02-d-cache-nginx-cdn-e-bancada-de-carga` | 1 | pendente | 0 |  | L1-02-c-wmts-xyz-tilejson-validados | — |
| `L1-02-f-predefinicoes-de-renderizacao-e-legenda` | 1 | pendente | 0 |  | L1-02-a-servico-titiler-por-inquilino, L1-12-linguagem-de-expressao-de-banda | — |
| `L1-02-tiles-token` | 1 | pendente | 0 |  | L1-01-ingest-raster, L0-02-tenant-auth | — |
| `L1-03-a-quadro-de-conectores-e-tela-sensores` | 1 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas, L0-05-jobs | — |
| `L1-03-b-sentinel-2` | 1 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores | — |
| `L1-07-mosaico-por-colecao-e-pegadas` | 1 | pendente | 0 |  | L1-01-a-pgstac-e-stac-api-por-inquilino, L1-02-b-token-de-servico-com-escopo-por-lista | — |
| `L1-12-linguagem-de-expressao-de-banda` | 1 | pendente | 0 |  | L1-02-a-servico-titiler-por-inquilino | — |
| `L1-01-e-upload-grande-retomavel` | 2 | pendente | 0 |  | L1-01-d-garage-por-inquilino, L0-05-jobs | — |
| `L1-01-f-formatos-de-entrada` | 2 | pendente | 0 |  | L1-01-b-validacao-e-isolamento-da-entrada | — |
| `L1-01-g-raster-categorico-colormap-e-tabela-de-atributos` | 2 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas | — |
| `L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo` | 2 | pendente | 0 |  | L1-01-d-garage-por-inquilino, L1-01-a-pgstac-e-stac-api-por-inquilino | — |
| `L1-01-j-proveniencia-da-imagem-lastro` | 2 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas | — |
| `L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro` | 2 | pendente | 0 |  | L1-02-b-token-de-servico-com-escopo-por-lista, L1-01-d-garage-por-inquilino | — |
| `L1-02-g-wms-1-3-0-raster` | 2 | pendente | 0 |  | L1-02-f-predefinicoes-de-renderizacao-e-legenda | — |
| `L1-02-h-ponto-estatisticas-e-histograma` | 2 | pendente | 0 |  | L1-02-a-servico-titiler-por-inquilino | — |
| `L1-03-c-sentinel-1-sar` | 2 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores | — |
| `L1-03-conectores-sensores` | 2 | pendente | 0 |  | L1-01-ingest-raster | — |
| `L1-03-d-landsat` | 2 | pendente | 0 |  | L1-03-b-sentinel-2 | — |
| `L1-03-e-mapbiomas` | 2 | pendente | 0 |  | L1-01-g-raster-categorico-colormap-e-tabela-de-atributos, L1-03-a-quadro-de-conectores-e-tela-sensores | — |
| `L1-03-f-cog-globais-por-vsicurl` | 2 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores, L1-01-g-raster-categorico-colormap-e-tabela-de-atributos | — |
| `L1-03-k-planetary-computer-e-stac-de-terceiros` | 2 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores, L1-03-l-item-referenciado-sem-copia | — |
| `L1-03-l-item-referenciado-sem-copia` | 2 | pendente | 0 |  | L1-02-a-servico-titiler-por-inquilino, L1-01-a-pgstac-e-stac-api-por-inquilino | — |
| `L1-04-c-grafico-de-indice-por-poligono` | 2 | pendente | 0 |  | L1-03-b-sentinel-2, L1-09-mascara-de-nuvem | — |
| `L1-05-a-registro-de-modelo-e-proveniencia` | 2 | pendente | 0 |  | L1-01-j-proveniencia-da-imagem-lastro | — |
| `L1-05-b-trabalhador-gpu-remoto` | 2 | pendente | 0 |  | L0-05-jobs, L1-05-a-registro-de-modelo-e-proveniencia | — |
| `L1-08-regras-de-mosaico-e-selecao-de-pixel` | 2 | pendente | 0 |  | L1-07-mosaico-por-colecao-e-pegadas, L1-09-mascara-de-nuvem | — |
| `L1-09-mascara-de-nuvem` | 2 | pendente | 0 |  | L1-03-b-sentinel-2 | — |
| `L1-13-cadeia-de-funcoes-raster-ao-vivo` | 2 | pendente | 0 |  | L1-02-f-predefinicoes-de-renderizacao-e-legenda, L1-12-linguagem-de-expressao-de-banda | — |
| `L1-14-analise-raster-em-lote-gera-item-novo` | 2 | pendente | 0 |  | L1-13-cadeia-de-funcoes-raster-ao-vivo, L0-05-jobs, L1-01-j-proveniencia-da-imagem-lastro | — |
| `L1-15-estatistica-zonal` | 2 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo | — |
| `L1-16-derivados-de-terreno-e-terrain-rgb` | 2 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo, L1-03-f-cog-globais-por-vsicurl | — |
| `L1-20-exportacao-recorte-e-massa` | 2 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo, L1-02-b-token-de-servico-com-escopo-por-lista, L0-06-backup-status | — |
| `L1-23-cota-e-medicao-por-tb` | 2 | pendente | 0 |  | L1-01-d-garage-por-inquilino, L1-02-b-token-de-servico-com-escopo-por-lista, L7-09-medicao-cobranca | — |
| `L1-25-servico-de-imagem-esri-compativel` | 2 | pendente | 0 |  | L1-02-f-predefinicoes-de-renderizacao-e-legenda, L1-02-h-ponto-estatisticas-e-histograma, L1-07-mosaico-por-colecao-e-pegadas | — |
| `L1-27-ficha-de-metadado-e-licenca-da-imagem` | 2 | pendente | 0 |  | L1-01-a-pgstac-e-stac-api-por-inquilino, L0-09-metadado-catalogo | — |
| `L1-29-teste-no-arcgis-real-do-parceiro` | 2 | pendente | 0 |  | L1-02-c-wmts-xyz-tilejson-validados, L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro, L1-01-a-pgstac-e-stac-api-por-inquilino | D20: credencial/tempo do parceiro no ArcGIS Pro/AGOL |
| `L1-30-paridade-image-server-documento-vivo` | 2 | pendente | 0 |  | L1-02-c-wmts-xyz-tilejson-validados | — |
| `L1-01-h-ingestao-em-lote-por-manifesto-e-cli` | 3 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas, L1-01-e-upload-grande-retomavel | — |
| `L1-02-i-ogc-api-tiles-e-maps` | 3 | pendente | 0 |  | L1-02-c-wmts-xyz-tilejson-validados | — |
| `L1-03-h-clima-nasa-power-e-copernicus-cds` | 3 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores, L1-19-multidimensional-netcdf-zarr | — |
| `L1-03-n-comerciais-com-chave-do-cliente` | 3 | pendente | 0 |  | L1-03-a-quadro-de-conectores-e-tela-sensores, L1-01-e-upload-grande-retomavel | chave de teste de fornecedor comercial = decisão do dono; até lá o item fecha só a parte 'sem chave' |
| `L1-03-p-drone-ortomosaico-e-fotos-brutas` | 3 | pendente | 0 |  | L1-01-c-conversao-cog-perfis-miniatura-estatisticas, L1-05-b-trabalhador-gpu-remoto | — |
| `L1-03-q-lidar-copc-mdt-mds` | 3 | pendente | 0 |  | L1-01-d-garage-por-inquilino, L1-16-derivados-de-terreno-e-terrain-rgb | — |
| `L1-04-a-controle-de-tempo-cortina-e-lado-a-lado` | 3 | pendente | 0 |  | L1-07-mosaico-por-colecao-e-pegadas, L2-01-mapa-web | — |
| `L1-04-e-diferenca-entre-datas-e-tendencia` | 3 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo, L1-09-mascara-de-nuvem | — |
| `L1-04-serie-temporal` | 3 | pendente | 0 |  | L1-02-tiles-token, L1-03-conectores-sensores | — |
| `L1-05-c-mudanca-s2-calibrada` | 3 | pendente | 0 |  | L1-05-b-trabalhador-gpu-remoto, L1-04-e-diferenca-entre-datas-e-tendencia, L1-09-mascara-de-nuvem | — |
| `L1-06-rasters-do-acervo-em-cog` | 3 | pendente | 0 |  | L1-01-h-ingestao-em-lote-por-manifesto-e-cli, L1-01-g-raster-categorico-colormap-e-tabela-de-atributos | — |
| `L1-10-camada-congelada-pmtiles` | 3 | pendente | 0 |  | L1-02-f-predefinicoes-de-renderizacao-e-legenda, L0-05-jobs | — |
| `L1-21-wcs-2-0-1` | 3 | pendente | 0 |  | L1-20-exportacao-recorte-e-massa, L1-02-g-wms-1-3-0-raster | — |
| `L1-24-imagens-orientadas` | 3 | pendente | 0 |  | L1-01-d-garage-por-inquilino, L2-01-mapa-web, L2-03-edicao | — |
| `L1-05-d-camadas-leves-edificacoes-e-vegetacao-em-faixa` | 4 | pendente | 0 |  | L1-05-b-trabalhador-gpu-remoto, L1-03-f-cog-globais-por-vsicurl | — |
| `L1-05-e-pacote-de-modelo-importavel` | 4 | pendente | 0 |  | L1-05-a-registro-de-modelo-e-proveniencia, L1-05-b-trabalhador-gpu-remoto | — |
| `L1-05-ia-na-entrada` | 4 | pendente | 0 |  | L1-03-conectores-sensores, L0-05-jobs | — |
| `L1-19-multidimensional-netcdf-zarr` | 4 | pendente | 0 |  | L1-01-f-formatos-de-entrada, L1-04-c-grafico-de-indice-por-poligono | — |
| `L1-05-f-amostras-e-rotulos-para-treino` | 5 | pendente | 0 |  | L1-05-e-pacote-de-modelo-importavel, L2-03-edicao | — |
| `L1-18-pansharpening-e-ortorretificacao-rpc` | 5 | pendente | 0 |  | L1-14-analise-raster-em-lote-gera-item-novo, L1-03-f-cog-globais-por-vsicurl | — |

### L2 plataforma (100 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L2-01-a-documento-mapa` | 1 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L2-01-b-martin-tiles-vetoriais` | 1 | pendente | 0 |  | L2-04-a-leitor-rls-martin, L0-04-c-tabela-camada | — |
| `L2-01-c-lista-camadas-legenda` | 1 | pendente | 0 |  | L2-01-a-documento-mapa, L2-01-b-martin-tiles-vetoriais | — |
| `L2-01-d-popup-runtime` | 1 | pendente | 0 |  | L2-01-a-documento-mapa, L2-04-c-featureserver-query | — |
| `L2-01-e-mapas-base` | 1 | pendente | 0 |  | L2-01-b-martin-tiles-vetoriais | — |
| `L2-01-g-tabela-atributos` | 1 | pendente | 0 |  | L2-04-c-featureserver-query, L2-01-h-selecao-filtros | — |
| `L2-01-h-selecao-filtros` | 1 | pendente | 0 |  | L2-01-a-documento-mapa, L2-04-c-featureserver-query | — |
| `L2-01-mapa-web` | 1 | pendente | 0 |  | L0-04-ingest-vetor, L0-14-identidade-visual | — |
| `L2-02-a-modelo-estilo` | 1 | pendente | 0 |  | L2-01-a-documento-mapa | — |
| `L2-02-b-classificacao-servidor` | 1 | pendente | 0 |  | L2-04-c-featureserver-query | — |
| `L2-02-c-editor-simbologia-vetor` | 1 | pendente | 0 |  | L2-02-a-modelo-estilo, L2-02-b-classificacao-servidor, L2-02-e-simbolos-sprites-glifos | — |
| `L2-02-d-rotulos` | 1 | pendente | 0 |  | L2-02-a-modelo-estilo, L2-10-c-linguagem-expressao | — |
| `L2-02-simbologia` | 1 | pendente | 0 |  | L2-01-mapa-web | — |
| `L2-03-a-api-edicao-transacional` | 1 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L2-03-b-ferramentas-geometria` | 1 | pendente | 0 |  | L2-03-a-api-edicao-transacional, L2-01-h-selecao-filtros | — |
| `L2-03-c-formulario-atributos-runtime` | 1 | pendente | 0 |  | L2-03-a-api-edicao-transacional, L2-10-a-dominios-subtipos | — |
| `L2-03-edicao` | 1 | pendente | 0 |  | L2-01-mapa-web, L0-02-tenant-auth | — |
| `L2-04-a-leitor-rls-martin` | 1 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L2-04-b-featureserver-catalogo-metadados` | 1 | pendente | 0 |  | L2-04-a-leitor-rls-martin, L2-10-a-dominios-subtipos, L2-10-b-relacionamentos | — |
| `L2-04-b-parser-where-ast` | 1 | entregue | 0 |  | — | — |
| `L2-04-c-featureserver-query` | 1 | pendente | 0 |  | L2-04-b-featureserver-catalogo-metadados | — |
| `L2-04-d-featureserver-edicao-anexos` | 1 | pendente | 0 |  | L2-04-c-featureserver-query, L2-03-a-api-edicao-transacional, L2-03-e-anexos | — |
| `L2-04-g-ogc-api-features-crs-cql2` | 1 | pendente | 0 |  | L2-04-a-leitor-rls-martin, L2-03-a-api-edicao-transacional | — |
| `L2-04-j-conformidade-clientes-e-paridade` | 1 | pendente | 0 |  | L2-04-c-featureserver-query, L2-04-d-featureserver-edicao-anexos, L2-04-g-ogc-api-features-crs-cql2 | — |
| `L2-04-servicos-esri-ogc` | 1 | pendente | 0 |  | L2-03-edicao, L0-02-tenant-auth | — |
| `L2-05-a-catalogo-ferramentas-gpserver` | 1 | pendente | 0 |  | L2-01-h-selecao-filtros | — |
| `L2-05-b-vetor-basico` | 1 | pendente | 0 |  | L2-05-a-catalogo-ferramentas-gpserver | — |
| `L2-05-c-sobreposicao-agregacao` | 1 | pendente | 0 |  | L2-05-b-vetor-basico | — |
| `L2-06-e-estatisticas-servidor` | 1 | pendente | 0 |  | L2-04-c-featureserver-query | — |
| `L2-10-a-dominios-subtipos` | 1 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L2-10-c-linguagem-expressao` | 1 | refutado | 3 | 3 | — | adversário: 26 de 304 casos novos divergem Python x JS (resto de módulo (0-7)%3 = 2 no Py e -1 no JS; texto com emoji; Numero de dígito arábico-índico); decimal.InvalidOperation crua em TextoNumero; 6 de 17 linhas 'feito' da tabela de paridade com o Arcade são falsas (Month 0-11, Now local, Abs(null), Reverse, Back/Front) |
| `L2-01-f-navegacao-medicao-coordenadas` | 2 | pendente | 0 |  | L2-01-a-documento-mapa, L2-17-crs-transformacoes | — |
| `L2-01-i-graficos-de-camada` | 2 | pendente | 0 |  | L2-01-h-selecao-filtros | — |
| `L2-01-j-comparacao-cortina-tempo` | 2 | pendente | 0 |  | L2-01-c-lista-camadas-legenda, L1-04-serie-temporal | — |
| `L2-01-k-desenho-anotacoes` | 2 | pendente | 0 |  | L2-01-a-documento-mapa, L2-02-a-modelo-estilo | — |
| `L2-01-l-exportacao-do-mapa` | 2 | pendente | 0 |  | L0-04-h-exportar, L2-01-h-selecao-filtros, L2-02-a-modelo-estilo | — |
| `L2-02-e-simbolos-sprites-glifos` | 2 | pendente | 0 |  | L2-01-b-martin-tiles-vetoriais | — |
| `L2-02-f-estilo-raster` | 2 | pendente | 0 |  | L1-02-tiles-token, L2-02-a-modelo-estilo | — |
| `L2-03-d-historico-restauracao` | 2 | pendente | 0 |  | L2-03-a-api-edicao-transacional | — |
| `L2-03-e-anexos` | 2 | pendente | 0 |  | L2-03-a-api-edicao-transacional | — |
| `L2-03-f-edicao-em-lote-calculo-campo` | 2 | pendente | 0 |  | L2-03-a-api-edicao-transacional, L2-10-c-linguagem-expressao | — |
| `L2-04-e-vector-tile-server-tilejson` | 2 | pendente | 0 |  | L2-01-b-martin-tiles-vetoriais, L2-02-a-modelo-estilo | — |
| `L2-04-h-wfs-2-gml` | 2 | pendente | 0 |  | L2-04-g-ogc-api-features-crs-cql2 | — |
| `L2-05-d-grades-densidade-padroes-interpolacao` | 2 | pendente | 0 |  | L2-05-c-sobreposicao-agregacao, L1-01-ingest-raster | — |
| `L2-05-e-raster-basico` | 2 | pendente | 0 |  | L2-05-a-catalogo-ferramentas-gpserver, L1-01-ingest-raster, L1-02-tiles-token | — |
| `L2-05-f-rede-isocrona-rota-ferramentas` | 2 | pendente | 0 |  | L2-05-a-catalogo-ferramentas-gpserver, L2-11-c-rota-matriz-isocrona | — |
| `L2-05-geoprocessamento` | 2 | pendente | 0 |  | L2-01-mapa-web, L0-05-jobs | — |
| `L2-06-a-modelo-painel-fontes` | 2 | pendente | 0 |  | L2-01-a-documento-mapa | — |
| `L2-06-b-elementos-basicos` | 2 | pendente | 0 |  | L2-06-a-modelo-painel-fontes, L2-06-e-estatisticas-servidor, L2-01-i-graficos-de-camada | — |
| `L2-06-c-acoes-seletores-filtros-cruzados` | 2 | pendente | 0 |  | L2-06-b-elementos-basicos | — |
| `L2-06-d-atualizacao-viva-sse` | 2 | pendente | 0 |  | L2-06-a-modelo-painel-fontes, L2-03-a-api-edicao-transacional | — |
| `L2-06-paineis` | 2 | pendente | 0 |  | L2-01-mapa-web, L0-14-identidade-visual | — |
| `L2-07-a-pwa-instalavel-cache` | 2 | pendente | 0 |  | L2-01-a-documento-mapa | — |
| `L2-07-b-formulario-de-coleta-xlsform` | 2 | pendente | 0 |  | L2-03-c-formulario-atributos-runtime, L2-10-c-linguagem-expressao | — |
| `L2-07-c-fila-sincronizacao-idempotente` | 2 | pendente | 0 |  | L2-07-a-pwa-instalavel-cache, L2-03-a-api-edicao-transacional, L2-13-b-replicas-sincronizacao | — |
| `L2-08-a-leitor-portal-inventario` | 2 | pendente | 0 |  | — | — |
| `L2-08-b-clonar-camadas-hospedadas` | 2 | pendente | 0 |  | L2-08-a-leitor-portal-inventario, L0-04-c-tabela-camada, L2-10-a-dominios-subtipos, L2-10-b-relacionamentos | — |
| `L2-08-c-converter-web-map-e-estilo` | 2 | pendente | 0 |  | L2-08-b-clonar-camadas-hospedadas, L2-01-a-documento-mapa, L2-02-a-modelo-estilo, L2-02-d-rotulos | — |
| `L2-08-d-relatorio-migracao-e-exportacao-reversa` | 2 | pendente | 0 |  | L2-08-c-converter-web-map-e-estilo, L5-03-e-xlsform-ida-e-volta-idiomas | — |
| `L2-08-migracao-agol` | 2 | pendente | 0 |  | L2-02-simbologia, L0-04-ingest-vetor | — |
| `L2-10-b-relacionamentos` | 2 | pendente | 0 |  | L2-10-a-dominios-subtipos, L2-03-a-api-edicao-transacional | — |
| `L2-10-d-regras-de-atributo` | 2 | pendente | 0 |  | L2-10-c-linguagem-expressao, L2-03-a-api-edicao-transacional | — |
| `L2-10-relacoes-regras` | 2 | pendente | 0 |  | L2-03-edicao | — |
| `L2-11-a-geocodificacao-csv` | 2 | pendente | 0 |  | L2-11-b-geocodificador-brasil, L0-04-d-formatos-base | — |
| `L2-11-b-geocodificador-brasil` | 2 | pendente | 0 |  | — | — |
| `L2-11-c-rota-matriz-isocrona` | 2 | parcial | 0 |  | — | rota/matriz/isocrona por OSRM isolado (Guarulhos) entregues e testadas; faltam pgRouting, /mais-proximo, perfis pe/bicicleta, NAServer Esri-compativel, teste de escala 1000x1000 |
| `L2-11-geocodificacao-rota` | 2 | pendente | 0 |  | L2-01-mapa-web | — |
| `L2-12-a-motor-render-servidor` | 2 | pendente | 0 |  | L2-01-a-documento-mapa | — |
| `L2-17-crs-transformacoes` | 2 | pendente | 0 |  | L0-04-c-tabela-camada | — |
| `L2-19-paridade-l2-e-manual` | 2 | pendente | 0 |  | L2-04-j-conformidade-clientes-e-paridade, L2-01-c-lista-camadas-legenda, L2-02-c-editor-simbologia-vetor, L2-03-b-ferramentas-geometria, L2-05-a-catalogo-ferramentas-gpserver, L2-06-b-elementos-basicos, L2-07-c-fila-sincronizacao-idempotente | — |
| `L2-01-a-basemap-local-pmtiles` | 3 | entregue | 1 | 3 | — | — |
| `L2-04-f-mapserver-identify-legend-geometryserver` | 3 | pendente | 0 |  | L2-04-c-featureserver-query, L2-12-a-motor-render-servidor | — |
| `L2-04-i-wms-wmts-sld` | 3 | pendente | 0 |  | L2-12-a-motor-render-servidor, L2-02-a-modelo-estilo, L1-02-tiles-token | — |
| `L2-04-k-sync-replicas-esri` | 3 | pendente | 0 |  | L2-13-b-replicas-sincronizacao, L2-04-d-featureserver-edicao-anexos | — |
| `L2-07-campo` | 3 | pendente | 0 |  | L2-03-edicao | — |
| `L2-07-d-mapa-offline-por-area` | 3 | pendente | 0 |  | L2-07-a-pwa-instalavel-cache, L2-01-b-martin-tiles-vetoriais, L2-13-b-replicas-sincronizacao | — |
| `L2-09-3d` | 3 | pendente | 0 |  | L2-01-mapa-web | — |
| `L2-09-a-terreno-terrain-rgb-relevo` | 3 | pendente | 0 |  | L1-01-ingest-raster, L2-01-b-martin-tiles-vetoriais | — |
| `L2-09-b-cena-extrusao-slides` | 3 | pendente | 0 |  | L2-09-a-terreno-terrain-rgb-relevo, L2-01-a-documento-mapa, L2-02-a-modelo-estilo | — |
| `L2-09-c-modelos-gltf-ifc-3dtiles` | 3 | pendente | 0 |  | L2-09-b-cena-extrusao-slides | — |
| `L2-12-b-layouts-elementos-exportacao` | 3 | pendente | 0 |  | L2-12-a-motor-render-servidor, L2-01-c-lista-camadas-legenda, L2-02-a-modelo-estilo | — |
| `L2-12-impressao-layout` | 3 | pendente | 0 |  | L2-02-simbologia | — |
| `L2-13-a-versoes-ramo-reconciliar` | 3 | pendente | 0 |  | L2-03-a-api-edicao-transacional, L2-03-d-historico-restauracao | — |
| `L2-13-b-replicas-sincronizacao` | 3 | pendente | 0 |  | L2-03-a-api-edicao-transacional, L0-04-h-exportar | — |
| `L2-13-versionamento-sync` | 3 | pendente | 0 |  | L2-03-edicao, L2-07-campo | — |
| `L2-14-a-ingestao-de-fluxos` | 3 | pendente | 0 |  | — | — |
| `L2-14-b-camada-viva-historico` | 3 | pendente | 0 |  | L2-14-a-ingestao-de-fluxos, L2-06-d-atualizacao-viva-sse, L2-01-b-martin-tiles-vetoriais | — |
| `L2-14-c-regras-alertas-incidentes` | 3 | pendente | 0 |  | L2-14-b-camada-viva-historico, L2-10-c-linguagem-expressao, L7-08-a-webhooks-eventos | — |
| `L2-14-tempo-real` | 3 | pendente | 0 |  | L2-01-mapa-web, L0-05-jobs | — |
| `L2-15-a-geoparquet-bucket-catalogo` | 3 | pendente | 0 |  | L0-04-h-exportar | — |
| `L2-15-analitica-grande` | 3 | pendente | 0 |  | L2-05-geoprocessamento | — |
| `L2-15-b-consultas-duckdb-em-escala` | 3 | pendente | 0 |  | L2-15-a-geoparquet-bucket-catalogo, L2-05-a-catalogo-ferramentas-gpserver | — |
| `L2-18-camada-de-consulta-sql` | 3 | pendente | 0 |  | L0-04-c-tabela-camada, L0-04-j-camada-vista, L2-04-a-leitor-rls-martin | — |
| `L2-07-e-odk-central-ponte` | 4 | pendente | 0 |  | L2-07-b-formulario-de-coleta-xlsform | — |
| `L2-09-d-analise-3d-visibilidade` | 4 | pendente | 0 |  | L2-09-a-terreno-terrain-rgb-relevo, L2-05-e-raster-basico | — |
| `L2-12-c-series-de-mapas-lote` | 4 | pendente | 0 |  | L2-12-b-layouts-elementos-exportacao, L2-01-h-selecao-filtros | — |
| `L2-16-a-sdk-python-geo` | 4 | pendente | 0 |  | L7-08-sdk-api-webhooks, L2-04-c-featureserver-query, L2-03-a-api-edicao-transacional | — |
| `L2-16-b-jupyter-por-inquilino-isolado` | 4 | pendente | 0 |  | L2-16-a-sdk-python-geo | — |
| `L2-16-c-script-vira-ferramenta` | 4 | pendente | 0 |  | L2-16-b-jupyter-por-inquilino-isolado, L2-05-a-catalogo-ferramentas-gpserver | — |
| `L2-16-notebooks-scripts` | 4 | pendente | 0 |  | L5-02-fluxos | — |

### L3 motor AMC (34 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L3-01-a-modelo-dado` | 1 | entregue | 1 | 3 | L0-02-tenant-auth | — |
| `L3-01-b-unidades` | 1 | parcial | 1 | 3 | — | grade 250m/2.000km2 em 1,14s e desvio 1,175%; 1 milhão de células NÃO gerado (medido 250.986, resto EXTRAPOLADO); worker de produção só conhece o tipo após o merge |
| `L3-01-c-extracao-fator` | 1 | pendente | 0 |  | L3-01-b-unidades, L1-01-ingest-raster, L0-04-ingest-vetor | — |
| `L3-01-d-transformacoes` | 1 | pendente | 0 |  | L3-01-c-extracao-fator | — |
| `L3-01-e-combinacao` | 1 | pendente | 0 |  | L3-01-d-transformacoes | — |
| `L3-01-f-explicacao` | 1 | pendente | 0 |  | L3-01-e-combinacao | — |
| `L3-01-g-tela-motor` | 1 | pendente | 0 |  | L3-01-f-explicacao, L2-01-mapa-web | — |
| `L3-01-j-equivalencia-motor-logistico` | 1 | pendente | 0 |  | L3-01-e-combinacao | — |
| `L3-01-motor-servico` | 1 | pendente | 0 |  | L2-05-geoprocessamento | — |
| `L3-14-cobertura-dado-ausente` | 1 | pendente | 0 |  | L3-01-c-extracao-fator | — |
| `L3-01-h-presets` | 2 | pendente | 0 |  | L3-01-g-tela-motor | — |
| `L3-01-i-exportacao-metodo` | 2 | pendente | 0 |  | L3-01-h-presets | — |
| `L3-04-restricoes` | 2 | pendente | 0 |  | L3-01-c-extracao-fator | — |
| `L3-06-criterios-de-feicao` | 2 | pendente | 0 |  | L3-01-c-extracao-fator | — |
| `L3-07-agregacao` | 2 | pendente | 0 |  | L3-01-e-combinacao | — |
| `L3-12-integracao-fluxo-e-api` | 2 | pendente | 0 |  | L3-01-g-tela-motor, L5-02-fluxos, L0-05-jobs | — |
| `L3-13-resultado-como-camada` | 2 | pendente | 0 |  | L3-01-e-combinacao, L2-04-servicos-esri-ogc, L1-02-tiles-token | — |
| `L3-18-paridade-esri-amc` | 2 | pendente | 0 |  | L3-01-g-tela-motor | — |
| `L3-02-a-monte-carlo-pesos` | 3 | pendente | 0 |  | L3-01-e-combinacao | — |
| `L3-02-b-sensibilidade-sobol-oat` | 3 | pendente | 0 |  | L3-02-a-monte-carlo-pesos | — |
| `L3-02-c-smaa` | 3 | pendente | 0 |  | L3-02-a-monte-carlo-pesos | — |
| `L3-02-d-comparacao-cenarios` | 3 | pendente | 0 |  | L3-01-h-presets | — |
| `L3-02-robustez` | 3 | pendente | 0 |  | L3-01-motor-servico | — |
| `L3-03-ahp-pares` | 3 | pendente | 0 |  | L3-01-h-presets | — |
| `L3-05-localizar-regioes` | 3 | pendente | 0 |  | L3-01-e-combinacao | — |
| `L3-09-backtest-decisao-real` | 3 | pendente | 0 |  | L3-01-e-combinacao, L3-02-a-monte-carlo-pesos | — |
| `L3-10-corredor-custo-minimo` | 3 | pendente | 0 |  | L3-01-e-combinacao, L3-04-restricoes | — |
| `L3-11-fator-de-rede` | 3 | pendente | 0 |  | L3-01-c-extracao-fator, L2-11-geocodificacao-rota | — |
| `L3-15-metadado-fator` | 3 | pendente | 0 |  | L3-01-d-transformacoes | — |
| `L3-16-desempenho-escala` | 3 | pendente | 0 |  | L3-01-c-extracao-fator, L3-01-e-combinacao | — |
| `L3-08-pareto` | 4 | pendente | 0 |  | L3-01-e-combinacao | — |
| `L3-17-similaridade` | 4 | pendente | 0 |  | L3-01-c-extracao-fator | — |
| `L3-19-multiescala` | 4 | pendente | 0 |  | L3-01-b-unidades | — |
| `L3-20-narrativa-de-resultado` | 4 | pendente | 0 |  | L3-01-i-exportacao-metodo | — |

### L4 rede de utilidades (66 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L4-01-a-pacote-de-ativos` | 1 | pendente | 0 |  | L0-04-ingest-vetor | — |
| `L4-01-b-topologia-derivada` | 1 | pendente | 0 |  | L4-01-a-pacote-de-ativos | — |
| `L4-01-c-importador-bdgd` | 1 | pendente | 0 |  | L4-01-b-topologia-derivada, L0-05-jobs | — |
| `L4-01-modelo-rede` | 1 | pendente | 0 |  | L0-04-ingest-vetor | — |
| `L4-02-a-conectado-e-subrede` | 1 | pendente | 0 |  | L4-01-b-topologia-derivada | — |
| `L4-02-b-montante-jusante` | 1 | pendente | 0 |  | L4-02-a-conectado-e-subrede, L4-04-a-controladores-e-tiers | — |
| `L4-02-c-isolamento` | 1 | pendente | 0 |  | L4-02-b-montante-jusante, L4-06-d-categorias-e-restricoes | — |
| `L4-02-tracado` | 1 | pendente | 0 |  | L4-01-modelo-rede | — |
| `L4-03-a-regras-de-conectividade` | 1 | pendente | 0 |  | L4-01-a-pacote-de-ativos | — |
| `L4-03-c-edicao-topologica-no-mapa` | 1 | pendente | 0 |  | L4-03-a-regras-de-conectividade, L2-03-edicao | — |
| `L4-03-d-areas-sujas-e-validacao` | 1 | pendente | 0 |  | L4-01-b-topologia-derivada, L4-03-a-regras-de-conectividade | — |
| `L4-04-a-controladores-e-tiers` | 1 | pendente | 0 |  | L4-01-d-atributos-de-rede | — |
| `L4-04-b-atualizar-e-exportar-subrede` | 1 | pendente | 0 |  | L4-04-a-controladores-e-tiers, L4-02-a-conectado-e-subrede | — |
| `L4-05-a-exportar-opendss` | 1 | pendente | 0 |  | L4-01-c-importador-bdgd, L4-04-b-atualizar-e-exportar-subrede | — |
| `L4-07-fluxo-de-potencia` | 1 | pendente | 0 |  | L4-05-a-exportar-opendss, L0-05-jobs | — |
| `L4-08-queda-de-tensao-e-carregamento` | 1 | pendente | 0 |  | L4-07-fluxo-de-potencia | — |
| `L4-23-isolamento-por-inquilino-na-rede` | 1 | pendente | 0 |  | L4-01-b-topologia-derivada, L0-02-tenant-auth | — |
| `L4-01-d-atributos-de-rede` | 2 | pendente | 0 |  | L4-01-b-topologia-derivada | — |
| `L4-02-d-lacos-e-caminho-curto` | 2 | pendente | 0 |  | L4-02-a-conectado-e-subrede | — |
| `L4-02-e-configuracoes-de-tracado` | 2 | pendente | 0 |  | L4-02-c-isolamento, L4-02-d-lacos-e-caminho-curto | — |
| `L4-03-b-terminais` | 2 | pendente | 0 |  | L4-03-a-regras-de-conectividade, L4-01-d-atributos-de-rede | — |
| `L4-03-e-versao-de-rede` | 2 | pendente | 0 |  | L4-03-d-areas-sujas-e-validacao, L2-13-versionamento-sync | — |
| `L4-03-edicao-rede` | 2 | pendente | 0 |  | L4-02-tracado, L2-03-edicao | — |
| `L4-04-c-sumarios-por-subrede` | 2 | pendente | 0 |  | L4-04-b-atualizar-e-exportar-subrede | — |
| `L4-04-d-diagrama-esquematico` | 2 | pendente | 0 |  | L4-04-b-atualizar-e-exportar-subrede, L2-01-mapa-web | — |
| `L4-05-b-cim-iec-61970-61968` | 2 | pendente | 0 |  | L4-01-a-pacote-de-ativos, L4-04-b-atualizar-e-exportar-subrede | — |
| `L4-05-c-pandapower-e-matpower` | 2 | pendente | 0 |  | L4-05-a-exportar-opendss | — |
| `L4-05-d-epanet-inp` | 2 | pendente | 0 |  | L4-01-a-pacote-de-ativos, L4-01-b-topologia-derivada | — |
| `L4-05-f-transmissao-sindat-sigel` | 2 | pendente | 0 |  | L4-01-a-pacote-de-ativos, L6-01-acervo-casa | — |
| `L4-06-a-contencao` | 2 | pendente | 0 |  | L4-03-a-regras-de-conectividade, L4-03-c-edicao-topologica-no-mapa | — |
| `L4-06-b-estrutura-postes` | 2 | pendente | 0 |  | L4-06-a-contencao | — |
| `L4-06-d-categorias-e-restricoes` | 2 | pendente | 0 |  | L4-01-a-pacote-de-ativos | — |
| `L4-09-perdas-tecnicas-por-segmento` | 2 | pendente | 0 |  | L4-07-fluxo-de-potencia | — |
| `L4-10-continuidade-dec-fec` | 2 | pendente | 0 |  | L4-04-c-sumarios-por-subrede, L6-01-acervo-casa | — |
| `L4-11-gd-conectada-e-hospedagem` | 2 | pendente | 0 |  | L4-07-fluxo-de-potencia, L4-04-c-sumarios-por-subrede | — |
| `L4-12-inspecao-vegetacao-na-faixa` | 2 | pendente | 0 |  | L4-01-c-importador-bdgd, L1-03-conectores-sensores, L0-05-jobs | — |
| `L4-13-integracao-telemetria` | 2 | pendente | 0 |  | L4-01-b-topologia-derivada, L2-14-tempo-real | — |
| `L4-16-api-rest-compativel-un` | 2 | pendente | 0 |  | L4-02-e-configuracoes-de-tracado, L4-03-d-areas-sujas-e-validacao, L4-04-b-atualizar-e-exportar-subrede, L2-04-servicos-esri-ogc | — |
| `L4-21-qualidade-e-saude-da-rede` | 2 | pendente | 0 |  | L4-03-d-areas-sujas-e-validacao, L4-04-c-sumarios-por-subrede | — |
| `L4-22-desempenho-em-escala` | 2 | pendente | 0 |  | L4-01-c-importador-bdgd, L4-02-e-configuracoes-de-tracado, L4-03-d-areas-sujas-e-validacao | — |
| `L4-24-cartografia-de-rede` | 2 | pendente | 0 |  | L2-02-simbologia, L4-01-d-atributos-de-rede | — |
| `L4-01-h-alinhamento-inspire-gnm` | 3 | pendente | 0 |  | L4-01-a-pacote-de-ativos | — |
| `L4-02-f-resultados-e-exportacao` | 3 | pendente | 0 |  | L4-02-e-configuracoes-de-tracado | — |
| `L4-04-e-diagrama-camadas-e-contencao` | 3 | pendente | 0 |  | L4-04-d-diagrama-esquematico, L4-06-a-contencao | — |
| `L4-04-subredes-diagramas` | 3 | pendente | 0 |  | L4-03-edicao-rede | — |
| `L4-05-conectores-rede` | 3 | pendente | 0 |  | L4-01-modelo-rede | — |
| `L4-05-e-gas-e-esgoto` | 3 | pendente | 0 |  | L4-05-d-epanet-inp | — |
| `L4-05-g-osm-power` | 3 | pendente | 0 |  | L4-01-a-pacote-de-ativos, L0-04-ingest-vetor | — |
| `L4-05-h-inspire-utility-networks` | 3 | pendente | 0 |  | L4-05-b-cim-iec-61970-61968 | — |
| `L4-06-c-objetos-nao-espaciais` | 3 | pendente | 0 |  | L4-06-a-contencao, L4-03-b-terminais | — |
| `L4-06-estruturas-regras-avancadas` | 3 | pendente | 0 |  | L4-03-edicao-rede | — |
| `L4-14-balanco-de-energia-por-alimentador` | 3 | pendente | 0 |  | L4-04-c-sumarios-por-subrede, L4-09-perdas-tecnicas-por-segmento | — |
| `L4-15-serie-temporal-da-rede` | 3 | pendente | 0 |  | L4-01-c-importador-bdgd | — |
| `L4-17-migracao-de-un-e-rede-geometrica` | 3 | pendente | 0 |  | L4-01-a-pacote-de-ativos, L4-05-b-cim-iec-61970-61968, L2-08-migracao-agol | — |
| `L4-18-rede-simples-trace-network` | 3 | pendente | 0 |  | L4-01-b-topologia-derivada, L4-02-a-conectado-e-subrede | — |
| `L4-19-planejamento-de-linha-nova` | 3 | pendente | 0 |  | L3-01-motor-servico, L4-01-a-pacote-de-ativos | — |
| `L4-20-consumidores-e-enderecos` | 3 | pendente | 0 |  | L4-01-c-importador-bdgd, L6-01-acervo-casa | — |
| `L4-25-cenarios-e-se` | 3 | pendente | 0 |  | L4-03-e-versao-de-rede, L4-07-fluxo-de-potencia | — |
| `L4-26-inspecao-de-campo-do-ativo` | 3 | pendente | 0 |  | L2-07-campo, L4-06-b-estrutura-postes | — |
| `L4-27-curto-circuito-e-protecao` | 3 | pendente | 0 |  | L4-05-c-pandapower-e-matpower | — |
| `L4-28-identificadores-e-numeracao` | 3 | pendente | 0 |  | L4-01-a-pacote-de-ativos | — |
| `L4-29-regras-de-atributo-de-rede` | 3 | pendente | 0 |  | L2-10-relacoes-regras, L4-04-b-atualizar-e-exportar-subrede | — |
| `L4-parcelas-01-modelo-de-parcelas` | 3 | pendente | 0 |  | L0-04-ingest-vetor, L2-03-edicao, L2-13-versionamento-sync | — |
| `L4-parcelas-02-fluxos-cogo` | 3 | pendente | 0 |  | L4-parcelas-01-modelo-de-parcelas | — |
| `L4-30-manual-e-tour-de-rede` | 4 | pendente | 0 |  | L4-04-d-diagrama-esquematico, L4-08-queda-de-tensao-e-carregamento | — |
| `L4-parcelas-03-ajuste-e-qualidade` | 4 | pendente | 0 |  | L4-parcelas-02-fluxos-cogo | — |

### L5 builder (61 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L5-01-a-layout-paginas` | 1 | pendente | 0 |  | L5-08-editor-arrasto | — |
| `L5-01-b-widgets-mapa` | 1 | pendente | 0 |  | L5-07-fontes-vistas-mensagens, L2-02-simbologia | — |
| `L5-01-c-widgets-dado` | 1 | pendente | 0 |  | L5-07-fontes-vistas-mensagens, L2-04-servicos-esri-ogc | — |
| `L5-01-e-acoes-configuraveis` | 1 | pendente | 0 |  | L5-07-fontes-vistas-mensagens, L5-08-editor-arrasto | — |
| `L5-02-a-editor-de-nos` | 1 | pendente | 0 |  | L5-08-editor-arrasto, L2-05-geoprocessamento, L3-01-motor-servico | — |
| `L5-02-b-execucao-proveniencia` | 1 | pendente | 0 |  | L5-02-a-editor-de-nos, L0-05-jobs | — |
| `L5-03-a-construtor-elementos` | 1 | pendente | 0 |  | L5-08-editor-arrasto, L2-03-edicao, L2-07-campo | — |
| `L5-03-b-logica-condicional-calculo-restricao` | 1 | pendente | 0 |  | L5-03-a-construtor-elementos, L5-11-expressoes-no-navegador | — |
| `L5-05-documento-versoes` | 1 | entregue | 0 |  | — | — |
| `L5-06-motor-widgets` | 1 | pendente | 0 |  | L2-01-mapa-web | — |
| `L5-07-fontes-vistas-mensagens` | 1 | pendente | 0 |  | L5-06-motor-widgets, L2-04-servicos-esri-ogc | — |
| `L5-08-editor-arrasto` | 1 | pendente | 0 |  | L5-06-motor-widgets | — |
| `L5-11-expressoes-no-navegador` | 1 | pendente | 0 |  | L2-10-relacoes-regras | — |
| `L5-14-publicacao-links-embed` | 1 | pendente | 0 |  | L1-02-tiles-token | — |
| `L5-26-construtor-popup` | 1 | pendente | 0 |  | L5-08-editor-arrasto, L5-11-expressoes-no-navegador, L2-01-mapa-web | — |
| `L5-01-app-builder` | 2 | pendente | 0 |  | L2-06-paineis, L2-02-simbologia, L0-14-identidade-visual | — |
| `L5-01-d-widgets-pagina-menu` | 2 | pendente | 0 |  | L5-06-motor-widgets | — |
| `L5-01-f-modelos-app-galeria` | 2 | pendente | 0 |  | L5-01-a-layout-paginas, L5-01-b-widgets-mapa, L5-01-c-widgets-dado | — |
| `L5-02-c-agendamento-variaveis` | 2 | pendente | 0 |  | L5-02-b-execucao-proveniencia | — |
| `L5-02-d-exportar-python-importar-json` | 2 | pendente | 0 |  | L5-02-b-execucao-proveniencia, L7-08-sdk-api-webhooks | — |
| `L5-02-f-fluxo-como-ferramenta-e-api` | 2 | pendente | 0 |  | L5-02-b-execucao-proveniencia, L2-04-servicos-esri-ogc | — |
| `L5-02-fluxos` | 2 | pendente | 0 |  | L2-05-geoprocessamento, L3-01-motor-servico, L0-05-jobs | — |
| `L5-03-c-dominios-listas-cascata` | 2 | pendente | 0 |  | L5-03-a-construtor-elementos, L2-10-relacoes-regras | — |
| `L5-03-d-repeticoes-relacionadas-anexos` | 2 | pendente | 0 |  | L5-03-a-construtor-elementos, L2-10-relacoes-regras | — |
| `L5-03-e-xlsform-ida-e-volta-idiomas` | 2 | pendente | 0 |  | L5-03-b-logica-condicional-calculo-restricao, L5-03-c-dominios-listas-cascata | — |
| `L5-04-a-blocos-de-conteudo` | 2 | pendente | 0 |  | L5-08-editor-arrasto, L5-14-publicacao-links-embed | — |
| `L5-09-desfazer-refazer-rascunho` | 2 | pendente | 0 |  | L5-08-editor-arrasto | — |
| `L5-10-temas-marca` | 2 | pendente | 0 |  | L5-06-motor-widgets, L0-07-admin-org | — |
| `L5-12-acessibilidade-i18n-construtores` | 2 | pendente | 0 |  | L5-08-editor-arrasto | — |
| `L5-15-vista-movel-responsivo` | 2 | pendente | 0 |  | L5-08-editor-arrasto | — |
| `L5-17-painel-elementos-avancados` | 2 | pendente | 0 |  | L2-06-paineis, L5-07-fontes-vistas-mensagens | — |
| `L5-18-painel-parametros-url-vistas` | 2 | pendente | 0 |  | L5-17-painel-elementos-avancados, L5-14-publicacao-links-embed | — |
| `L5-20-sites-paginas-publicas` | 2 | pendente | 0 |  | L5-08-editor-arrasto, L5-14-publicacao-links-embed | — |
| `L5-21-dados-abertos-catalogo-publico` | 2 | pendente | 0 |  | L5-20-sites-paginas-publicas, L0-09-metadado-catalogo, L6-01-acervo-casa | — |
| `L5-23-apps-instantaneos-motor-galeria` | 2 | pendente | 0 |  | L5-01-f-modelos-app-galeria, L5-14-publicacao-links-embed | — |
| `L5-24-apps-instantaneos-modelos-1` | 2 | pendente | 0 |  | L5-23-apps-instantaneos-motor-galeria, L2-11-geocodificacao-rota | — |
| `L5-27-simbologia-por-arrasto` | 2 | pendente | 0 |  | L2-02-simbologia, L5-08-editor-arrasto | — |
| `L5-29-construtor-relatorio-pdf` | 2 | pendente | 0 |  | L5-08-editor-arrasto, L5-26-construtor-popup, L2-12-impressao-layout | — |
| `L5-31-construtor-de-camada-esquema` | 2 | pendente | 0 |  | L5-08-editor-arrasto, L0-04-ingest-vetor, L2-04-servicos-esri-ogc | — |
| `L5-33-a-diagrama-de-trabalho` | 2 | pendente | 0 |  | L5-02-a-editor-de-nos, L5-03-a-construtor-elementos, L5-11-expressoes-no-navegador | — |
| `L5-33-b-modelos-e-trabalhos` | 2 | pendente | 0 |  | L5-33-a-diagrama-de-trabalho, L7-08-sdk-api-webhooks | — |
| `L5-39-paridade-l5-e-manual` | 2 | pendente | 0 |  | L5-01-f-modelos-app-galeria, L5-02-f-fluxo-como-ferramenta-e-api, L5-03-e-xlsform-ida-e-volta-idiomas, L5-17-painel-elementos-avancados, L5-26-construtor-popup | — |
| `L5-02-e-iteradores-condicionais` | 3 | pendente | 0 |  | L5-02-b-execucao-proveniencia, L5-11-expressoes-no-navegador | — |
| `L5-03-form-builder` | 3 | pendente | 0 |  | L2-03-edicao, L2-07-campo | — |
| `L5-04-b-imersivos-sidecar-tour-swipe` | 3 | pendente | 0 |  | L5-04-a-blocos-de-conteudo, L5-01-b-widgets-mapa | — |
| `L5-04-c-temas-capa-colecao` | 3 | pendente | 0 |  | L5-04-a-blocos-de-conteudo, L5-10-temas-marca | — |
| `L5-13-edicao-concorrente` | 3 | pendente | 0 |  | L5-09-desfazer-refazer-rascunho, L0-02-tenant-auth | — |
| `L5-19-painel-expressoes-de-dado-tempo-real` | 3 | pendente | 0 |  | L5-17-painel-elementos-avancados, L2-14-tempo-real, L5-11-expressoes-no-navegador | — |
| `L5-22-sites-dominio-proprio-tema` | 3 | pendente | 0 |  | L5-20-sites-paginas-publicas, L7-01-instalador-limpo | — |
| `L5-25-apps-instantaneos-modelos-2` | 3 | pendente | 0 |  | L5-23-apps-instantaneos-motor-galeria, L1-04-serie-temporal, L2-03-edicao | — |
| `L5-28-galeria-simbolos-rampas-estilos` | 3 | pendente | 0 |  | L5-27-simbologia-por-arrasto | — |
| `L5-30-relatorio-lote-agendado` | 3 | pendente | 0 |  | L5-29-construtor-relatorio-pdf, L5-02-c-agendamento-variaveis | — |
| `L5-32-vistas-de-camada` | 3 | pendente | 0 |  | L5-31-construtor-de-camada-esquema | — |
| `L5-33-c-atribuicao-avancada-indicadores` | 3 | pendente | 0 |  | L5-33-b-modelos-e-trabalhos, L2-06-paineis | — |
| `L5-34-captura-rapida-designer-pwa` | 3 | pendente | 0 |  | L5-08-editor-arrasto, L2-07-campo, L2-14-tempo-real | — |
| `L5-36-widgets-personalizados-sdk` | 3 | pendente | 0 |  | L5-06-motor-widgets, L5-07-fontes-vistas-mensagens, L0-07-admin-org | — |
| `L5-37-pacotes-modelos-entre-inquilinos` | 3 | pendente | 0 |  | L5-14-publicacao-links-embed | — |
| `L5-04-storymap` | 4 | pendente | 0 |  | L2-01-mapa-web | — |
| `L5-16-agente-escreve-configuracao` | 4 | pendente | 0 |  | L5-01-app-builder | — |
| `L5-35-missao-operacao-ao-vivo` | 4 | pendente | 0 |  | L5-34-captura-rapida-designer-pwa, L2-14-tempo-real, L5-33-b-modelos-e-trabalhos | — |
| `L5-38-importadores-configuracao-esri` | 4 | pendente | 0 |  | L5-26-construtor-popup, L5-27-simbologia-por-arrasto, L5-17-painel-elementos-avancados, L2-08-migracao-agol | — |

### L6 conectores (32 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L6-01-a-registro` | 1 | entregue | 1 | 3 | — | — |
| `L6-01-b-view-so-leitura` | 1 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L6-01-f-lgpd` | 1 | parcial | 1 | 3 | — | gate implementado e testado exatamente no escopo pedido: plat.acervo_lgpd curado a mao (migracao 041) apos varredura real de 219 tabelas das 68 fontes licenciadas; unica marcada = onr (matriculas, url_mat aponta pra doc de cartorio com nome do titular); POST /adicionar recusa 409 sem confirma_risco_pii, evento acervo/adicionar_recusado_pii registrado em transacao propria. PENDENTE (portao completo do backlog, maior que o pedido desta passagem): varredura automatica de TODA view exposta (incl. plat.acervo_camada) por regex de conteudo, nao so por nome; sem adversario independente. |
| `L6-01-g-licenca-curada` | 1 | parcial | 2 | 3 | — | 29/40 fontes confirmadas (ver decisoes_do_dono D39); gap = orgaos sem portal CKAN/DCAT vivo ou so rodape generico gov.br |
| `L6-02-a-modelo-conexao-e-seguranca` | 1 | entregue | 1 | 3 | — | — |
| `L6-01-acervo-casa` | 2 | pendente | 0 |  | L2-01-mapa-web | — |
| `L6-01-c-tela-acervo` | 2 | pendente | 0 |  | L6-01-b-view-so-leitura, L2-01-mapa-web | — |
| `L6-01-d-ficha-fonte` | 2 | parcial | 1 | 3 | — | backend completo e evidenciado: os 10 campos de procedencia ja existiam (item anterior); somados endpoints confirmados/vivos (plat.acervo_endpoint, migracao 040) e completude_texto x/10; 14 testes em tests/api/test_acervo.py incl. 20 fontes campo a campo + campo ausente nunca fabricado. PENDENTE: tela/e2e (L6-01-c, papel frontend nao executado nesta passagem) e adversario independente. |
| `L6-01-e-assinatura-e-uso` | 2 | pendente | 0 |  | L6-01-b-view-so-leitura | — |
| `L6-02-b-wms-wmts` | 2 | pendente | 0 |  | L2-01-mapa-web | — |
| `L6-02-c-wfs-ogcapi` | 2 | pendente | 0 |  | — | — |
| `L6-02-d-arcgis-rest-externo` | 2 | pendente | 0 |  | — | — |
| `L6-02-g-pmtiles-xyz-tilejson` | 2 | pendente | 0 |  | L2-01-mapa-web | — |
| `L6-02-h-csv-url-geojson-kml` | 2 | pendente | 0 |  | L0-04-ingest-vetor | — |
| `L6-02-k-agendamento` | 2 | pendente | 0 |  | L0-05-jobs | — |
| `L6-02-m-catalogo-endpoints-brasil` | 2 | pendente | 0 |  | L6-02-b-wms-wmts, L6-02-c-wfs-ogcapi, L6-02-d-arcgis-rest-externo | — |
| `L6-03-paridade-conectores` | 2 | pendente | 0 |  | L6-02-m-catalogo-endpoints-brasil | — |
| `L6-04-acervo-no-motor` | 2 | pendente | 0 |  | L6-01-b-view-so-leitura, L3-01-c-extracao-fator | — |
| `L6-01-a-procedencia-acervo` | 3 | entregue | 0 |  | — | — |
| `L6-01-h-frescor-verificacao` | 3 | pendente | 0 |  | L0-05-jobs | — |
| `L6-01-i-raster-e-arquivos` | 3 | pendente | 0 |  | L1-02-tiles-token | — |
| `L6-02-conectores-vivos` | 3 | pendente | 0 |  | L2-01-mapa-web | — |
| `L6-02-e-stac-externo` | 3 | pendente | 0 |  | L1-03-conectores-sensores | — |
| `L6-02-f-geoparquet-duckdb` | 3 | pendente | 0 |  | L2-15-analitica-grande | — |
| `L6-02-i-google-sheets` | 3 | pendente | 0 |  | L6-02-h-csv-url-geojson-kml | — |
| `L6-02-j-bancos-externos` | 3 | pendente | 0 |  | — | — |
| `L6-02-l-saude` | 3 | parcial | 0 |  | — | mecanismo completo: historico plat.conexao_saude_historico, estado_saude agregado (ok/degradado/fora/nunca_testada), periodico de 15 min reteste todas as conexoes, tela /conexoes com selo vivo e 'testar agora'; falta so 'mapa mostra aviso' - nenhum conector desenha camada externa no mapa ainda (depende de L6-02-b+), entao nao ha onde avisar |
| `L6-02-n-etl-na-entrada` | 3 | pendente | 0 |  | L6-02-k-agendamento, L5-02-fluxos | — |
| `L6-02-o-importacao-exportacao-formatos` | 3 | pendente | 0 |  | L0-04-ingest-vetor | — |
| `L6-05-proveniencia-camada-externa` | 3 | parcial | 0 |  | — | mecanismo completo: app/conexao/proveniencia.py le licenca/atribuicao real de WMS/WMTS/WFS (AccessConstraints/Title), ArcGIS REST (copyrightText), STAC/OGC API (license); POST /api/conexoes/{id}/publicar cria item de catalogo com a ficha; provado com 2 servicos vivos distintos (Esri e Element84 STAC) devolvendo textos de licenca diferentes e verificados por curl; falta so 'atribuicao aparece na legenda do mapa' - hoje aparece no campo creditos do item, nao ha legenda de mapa ainda |
| `L6-01-j-multi-servidor` | 4 | pendente | 0 |  | — | — |
| `L6-06-descoberta-csw` | 4 | pendente | 0 |  | L6-02-b-wms-wmts, L6-02-c-wfs-ogcapi | — |

### L7 operação (76 itens)

| id | prio | estado | tent. | turno | dep. abertas | bloqueio |
|---|---|---|---|---|---|---|
| `L7-01-a-compose-perfis` | 2 | pendente | 0 |  | L1-01-ingest-raster, L2-01-mapa-web | — |
| `L7-01-b-instalacao-conteiner-limpo` | 2 | pendente | 0 |  | L7-01-a-compose-perfis | — |
| `L7-01-instalador-limpo` | 2 | pendente | 0 |  | L2-04-servicos-esri-ogc, L1-02-tiles-token | — |
| `L7-03-a-antivirus-upload` | 2 | pendente | 0 |  | L0-04-ingest-vetor, L1-01-ingest-raster, L2-03-edicao | — |
| `L7-03-b-rate-limit-abuso` | 2 | pendente | 0 |  | L0-02-tenant-auth, L1-02-tiles-token | — |
| `L7-03-c-ssrf-conectores` | 2 | pendente | 0 |  | L6-02-conectores-vivos | — |
| `L7-03-d-injecao-consulta` | 2 | pendente | 0 |  | L2-04-servicos-esri-ogc | — |
| `L7-03-e-cabecalhos-csp-tls` | 2 | pendente | 0 |  | L2-01-mapa-web | — |
| `L7-03-f-dependencias-cve-log-correcoes` | 2 | parcial | 1 | 3 | — | ClamAV real não instalado (D21 disco/RAM); CVE scan cobre pip-audit, não trivy/osv-scanner ainda |
| `L7-03-seguranca` | 2 | pendente | 0 |  | L2-04-servicos-esri-ogc | — |
| `L7-06-a-metricas-exporters` | 2 | pendente | 0 |  | L0-05-jobs, L1-02-tiles-token | — |
| `L7-06-b-alertas` | 2 | pendente | 0 |  | L7-06-a-metricas-exporters | — |
| `L7-06-c-logs-consulta-req-id` | 2 | pendente | 0 |  | L7-06-a-metricas-exporters | — |
| `L7-06-observabilidade` | 2 | pendente | 0 |  | L0-06-backup-status | — |
| `L7-15-processo-release` | 2 | entregue | 0 |  | — | — |
| `L7-16-assinatura-pacote` | 2 | entregue | 0 |  | — | — |
| `L7-19-segredos-e-certificados` | 2 | entregue | 0 |  | — | — |
| `L7-20-trilha-auditoria` | 2 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L7-31-ambiente-homologacao` | 2 | entregue | 0 |  | — | — |
| `L7-33-modo-somente-leitura` | 2 | pendente | 0 |  | L0-02-tenant-auth, L0-05-jobs | — |
| `L7-34-saude-profunda` | 2 | pendente | 0 |  | L0-05-jobs, L1-02-tiles-token | — |
| `L7-35-atualizacao-versao-assinada` | 2 | pendente | 0 |  | L7-33-modo-somente-leitura, L0-06-backup-status | — |
| `D21 (dono)` | 3 | pendente | 0 |  | — | — |
| `L7-01-c-dado-demonstracao` | 3 | pendente | 0 |  | L0-04-ingest-vetor, L1-01-ingest-raster | — |
| `L7-02-a-k6-cenarios` | 3 | pendente | 0 |  | L2-04-servicos-esri-ogc, L1-02-tiles-token | — |
| `L7-02-b-pool-e-limites-por-inquilino` | 3 | pendente | 0 |  | L7-02-a-k6-cenarios | — |
| `L7-02-carga` | 3 | pendente | 0 |  | L7-01-instalador-limpo | — |
| `L7-03-g-asvs-nivel2-pentest` | 3 | pendente | 0 |  | L7-03-e-cabecalhos-csp-tls, L7-03-b-rate-limit-abuso, L7-03-c-ssrf-conectores, L7-03-d-injecao-consulta, L7-03-a-antivirus-upload, L7-03-f-dependencias-cve-log-correcoes | — |
| `L7-04-a-manual-capturas-geradas` | 3 | pendente | 0 |  | L5-01-app-builder | — |
| `L7-04-b-tour-primeiro-acesso` | 3 | pendente | 0 |  | L7-10-a-i18n-pt-en-es | — |
| `L7-04-c-manual-admin-runbooks` | 3 | pendente | 0 |  | L7-35-atualizacao-versao-assinada, L7-24-drill-restauracao, L7-07-c-ensaio-failover | — |
| `L7-04-manual-e-tour` | 3 | pendente | 0 |  | L5-01-app-builder | — |
| `L7-06-d-paineis` | 3 | pendente | 0 |  | L7-06-a-metricas-exporters | — |
| `L7-07-a-replica-postgres` | 3 | pendente | 0 |  | L7-23-pgbackrest-pitr | — |
| `L7-07-alta-disponibilidade` | 3 | pendente | 0 |  | L7-01-instalador-limpo, L0-06-backup-status | — |
| `L7-07-b-replica-garage` | 3 | pendente | 0 |  | L7-01-a-compose-perfis | — |
| `L7-07-c-ensaio-failover` | 3 | pendente | 0 |  | L7-07-a-replica-postgres, L7-07-b-replica-garage, L7-33-modo-somente-leitura, L7-26-cdn-tiles | — |
| `L7-08-a-webhooks-eventos` | 3 | pendente | 0 |  | L0-05-jobs, L7-03-c-ssrf-conectores | — |
| `L7-08-b-sdk-python` | 3 | pendente | 0 |  | L2-04-servicos-esri-ogc, L7-08-d-portal-api-chaves | — |
| `L7-08-c-sdk-js` | 3 | pendente | 0 |  | L7-08-b-sdk-python, L2-01-mapa-web | — |
| `L7-08-d-portal-api-chaves` | 3 | pendente | 0 |  | L0-02-tenant-auth | — |
| `L7-08-sdk-api-webhooks` | 3 | pendente | 0 |  | L2-04-servicos-esri-ogc | — |
| `L7-09-a-medidor-diario` | 3 | pendente | 0 |  | L0-07-admin-org, L1-02-tiles-token, L0-05-jobs | — |
| `L7-09-b-planos-limites-relatorio` | 3 | pendente | 0 |  | L7-09-a-medidor-diario, L0-07-admin-org | — |
| `L7-09-medicao-cobranca` | 3 | pendente | 0 |  | L0-07-admin-org, L1-02-tiles-token | — |
| `L7-10-a-i18n-pt-en-es` | 3 | pendente | 0 |  | L5-01-app-builder, L5-12-acessibilidade-i18n-construtores, L0-07-admin-org | — |
| `L7-10-b-acessibilidade-wcag21aa` | 3 | pendente | 0 |  | L5-01-app-builder, L5-12-acessibilidade-i18n-construtores, L2-01-mapa-web | — |
| `L7-10-i18n-acessibilidade` | 3 | pendente | 0 |  | L5-01-app-builder, L0-14-identidade-visual | — |
| `L7-12-a-classificacao-retencao` | 3 | pendente | 0 |  | L7-20-trilha-auditoria, L7-26-cdn-tiles | — |
| `L7-12-b-registro-tratamento-dpa-incidente` | 3 | pendente | 0 |  | L7-12-a-classificacao-retencao, L7-22-sla-e-incidentes, L7-27-origem-br-soberania | — |
| `L7-12-lgpd-governanca` | 3 | pendente | 0 |  | L0-07-admin-org | — |
| `L7-14-instalacoes-apt-desta-linha` | 3 | entregue | 0 |  | — | — |
| `L7-17-capacidade-planejamento` | 3 | pendente | 0 |  | L7-09-a-medidor-diario, L7-06-d-paineis | — |
| `L7-18-custo-por-inquilino` | 3 | pendente | 0 |  | L7-09-a-medidor-diario | — |
| `L7-21-pagina-status` | 3 | pendente | 0 |  | L0-06-e-status, L7-34-saude-profunda, L7-06-a-metricas-exporters, L7-24-drill-restauracao | — |
| `L7-22-sla-e-incidentes` | 3 | pendente | 0 |  | L7-07-c-ensaio-failover, L7-23-pgbackrest-pitr, L7-21-pagina-status | — |
| `L7-23-pgbackrest-pitr` | 3 | pendente | 0 |  | L7-01-a-compose-perfis | — |
| `L7-24-drill-restauracao` | 3 | pendente | 0 |  | L0-06-a-dump-logico, L0-06-backup-status, L7-23-pgbackrest-pitr | — |
| `L7-25-exportacao-inquilino` | 3 | pendente | 0 |  | L0-06-d-exportar-inquilino, L0-05-jobs, L2-08-migracao-agol | — |
| `L7-26-cdn-tiles` | 3 | pendente | 0 |  | L1-02-tiles-token | — |
| `L7-27-origem-br-soberania` | 3 | pendente | 0 |  | L7-26-cdn-tiles, L7-23-pgbackrest-pitr, L7-12-a-classificacao-retencao | — |
| `L7-29-roteiro-demonstracao` | 3 | pendente | 0 |  | L7-01-c-dado-demonstracao, L3-01-motor-servico, L4-02-tracado, L5-01-app-builder, L6-01-acervo-casa | — |
| `L7-30-teste-parceiro-pro-agol` | 3 | pendente | 0 |  | L2-04-servicos-esri-ogc, L1-02-tiles-token, L7-08-d-portal-api-chaves | D20: credencial AGOL/Portal e agenda do parceiro (decisão do dono) |
| `L7-03-b-antivirus-anexos` | 4 | parcial | 1 | 3 | — | ClamAV real não instalado (D21 disco/RAM); CVE scan cobre pip-audit, não trivy/osv-scanner ainda |
| `L7-04-d-videos-por-tarefa` | 4 | pendente | 0 |  | L7-04-a-manual-capturas-geradas | — |
| `L7-05-producao-final` | 4 | pendente | 0 |  | D21 (dono), L0-02-tenant-auth, L0-04-a-upload-arquivo, L0-04-b-inspecao, L0-04-c-tabela-camada, L0-04-d-formatos-base, L0-04-e-formatos-cad, L0-04-f-fgdb-parquet-fgb-gml, L0-04-g-atualizar-dados, L0-04-h-exportar, L0-04-i-fonte-registrada, L0-04-ingest-vetor, L0-04-j-camada-vista, L0-05-c-tela-tarefas, L0-05-jobs, L0-06-a-dump-logico, L0-06-b-pitr-pgbackrest, L0-06-backup-status, L0-06-c-restore-drill, L0-06-d-exportar-inquilino, L0-06-e-status, L0-07-a-configuracoes-org, L0-07-admin-org, L0-07-b-papeis-privilegios, L0-07-c-cotas-uso, L0-07-d-smtp-convites, L0-07-e-relatorios, L0-07-f-console-plataforma, L0-08-a-oidc, L0-08-b-saml, L0-08-c-govbr, L0-08-e-mapeamento-provisionamento, L0-08-sso, L0-09-a-procedencia, L0-09-b-editor-iso-mgb, L0-09-c-xml-iso-validacao, L0-09-d-ogc-records-csw, L0-09-metadado-catalogo, L0-13-dado-demonstracao, L0-14-cli-admin, L1-01-a-pgstac-e-stac-api-por-inquilino, L1-01-b-validacao-e-isolamento-da-entrada, L1-01-c-conversao-cog-perfis-miniatura-estatisticas, L1-01-d-garage-por-inquilino, L1-01-e-upload-grande-retomavel, L1-01-f-formatos-de-entrada, L1-01-g-raster-categorico-colormap-e-tabela-de-atributos, L1-01-h-ingestao-em-lote-por-manifesto-e-cli, L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo, L1-01-ingest-raster, L1-01-j-proveniencia-da-imagem-lastro, L1-02-a-servico-titiler-por-inquilino, L1-02-b-token-de-servico-com-escopo-por-lista, L1-02-c-wmts-xyz-tilejson-validados, L1-02-d-cache-nginx-cdn-e-bancada-de-carga, L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro, L1-02-f-predefinicoes-de-renderizacao-e-legenda, L1-02-g-wms-1-3-0-raster, L1-02-h-ponto-estatisticas-e-histograma, L1-02-i-ogc-api-tiles-e-maps, L1-02-tiles-token, L1-03-a-quadro-de-conectores-e-tela-sensores, L1-03-b-sentinel-2, L1-03-c-sentinel-1-sar, L1-03-conectores-sensores, L1-03-d-landsat, L1-03-e-mapbiomas, L1-03-f-cog-globais-por-vsicurl, L1-03-h-clima-nasa-power-e-copernicus-cds, L1-03-k-planetary-computer-e-stac-de-terceiros, L1-03-l-item-referenciado-sem-copia, L1-03-n-comerciais-com-chave-do-cliente, L1-03-p-drone-ortomosaico-e-fotos-brutas, L1-03-q-lidar-copc-mdt-mds, L1-04-a-controle-de-tempo-cortina-e-lado-a-lado, L1-04-c-grafico-de-indice-por-poligono, L1-04-e-diferenca-entre-datas-e-tendencia, L1-04-serie-temporal, L1-05-a-registro-de-modelo-e-proveniencia, L1-05-b-trabalhador-gpu-remoto, L1-05-c-mudanca-s2-calibrada, L1-05-d-camadas-leves-edificacoes-e-vegetacao-em-faixa, L1-05-e-pacote-de-modelo-importavel, L1-05-f-amostras-e-rotulos-para-treino, L1-05-ia-na-entrada, L1-06-rasters-do-acervo-em-cog, L1-07-mosaico-por-colecao-e-pegadas, L1-08-regras-de-mosaico-e-selecao-de-pixel, L1-09-mascara-de-nuvem, L1-10-camada-congelada-pmtiles, L1-12-linguagem-de-expressao-de-banda, L1-13-cadeia-de-funcoes-raster-ao-vivo, L1-14-analise-raster-em-lote-gera-item-novo, L1-15-estatistica-zonal, L1-16-derivados-de-terreno-e-terrain-rgb, L1-18-pansharpening-e-ortorretificacao-rpc, L1-19-multidimensional-netcdf-zarr, L1-20-exportacao-recorte-e-massa, L1-21-wcs-2-0-1, L1-23-cota-e-medicao-por-tb, L1-24-imagens-orientadas, L1-25-servico-de-imagem-esri-compativel, L1-27-ficha-de-metadado-e-licenca-da-imagem, L1-29-teste-no-arcgis-real-do-parceiro, L1-30-paridade-image-server-documento-vivo, L2-01-a-documento-mapa, L2-01-b-martin-tiles-vetoriais, L2-01-c-lista-camadas-legenda, L2-01-d-popup-runtime, L2-01-e-mapas-base, L2-01-f-navegacao-medicao-coordenadas, L2-01-g-tabela-atributos, L2-01-h-selecao-filtros, L2-01-i-graficos-de-camada, L2-01-j-comparacao-cortina-tempo, L2-01-k-desenho-anotacoes, L2-01-l-exportacao-do-mapa, L2-01-mapa-web, L2-02-a-modelo-estilo, L2-02-b-classificacao-servidor, L2-02-c-editor-simbologia-vetor, L2-02-d-rotulos, L2-02-e-simbolos-sprites-glifos, L2-02-f-estilo-raster, L2-02-simbologia, L2-03-a-api-edicao-transacional, L2-03-b-ferramentas-geometria, L2-03-c-formulario-atributos-runtime, L2-03-d-historico-restauracao, L2-03-e-anexos, L2-03-edicao, L2-03-f-edicao-em-lote-calculo-campo, L2-04-a-leitor-rls-martin, L2-04-b-featureserver-catalogo-metadados, L2-04-c-featureserver-query, L2-04-d-featureserver-edicao-anexos, L2-04-e-vector-tile-server-tilejson, L2-04-f-mapserver-identify-legend-geometryserver, L2-04-g-ogc-api-features-crs-cql2, L2-04-h-wfs-2-gml, L2-04-i-wms-wmts-sld, L2-04-j-conformidade-clientes-e-paridade, L2-04-k-sync-replicas-esri, L2-04-servicos-esri-ogc, L2-05-a-catalogo-ferramentas-gpserver, L2-05-b-vetor-basico, L2-05-c-sobreposicao-agregacao, L2-05-d-grades-densidade-padroes-interpolacao, L2-05-e-raster-basico, L2-05-f-rede-isocrona-rota-ferramentas, L2-05-geoprocessamento, L2-06-a-modelo-painel-fontes, L2-06-b-elementos-basicos, L2-06-c-acoes-seletores-filtros-cruzados, L2-06-d-atualizacao-viva-sse, L2-06-e-estatisticas-servidor, L2-06-paineis, L2-07-a-pwa-instalavel-cache, L2-07-b-formulario-de-coleta-xlsform, L2-07-c-fila-sincronizacao-idempotente, L2-07-campo, L2-07-d-mapa-offline-por-area, L2-07-e-odk-central-ponte, L2-08-a-leitor-portal-inventario, L2-08-b-clonar-camadas-hospedadas, L2-08-c-converter-web-map-e-estilo, L2-08-d-relatorio-migracao-e-exportacao-reversa, L2-08-migracao-agol, L2-09-3d, L2-09-a-terreno-terrain-rgb-relevo, L2-09-b-cena-extrusao-slides, L2-09-c-modelos-gltf-ifc-3dtiles, L2-09-d-analise-3d-visibilidade, L2-10-a-dominios-subtipos, L2-10-b-relacionamentos, L2-10-c-linguagem-expressao, L2-10-d-regras-de-atributo, L2-10-relacoes-regras, L2-11-a-geocodificacao-csv, L2-11-b-geocodificador-brasil, L2-11-c-rota-matriz-isocrona, L2-11-geocodificacao-rota, L2-12-a-motor-render-servidor, L2-12-b-layouts-elementos-exportacao, L2-12-c-series-de-mapas-lote, L2-12-impressao-layout, L2-13-a-versoes-ramo-reconciliar, L2-13-b-replicas-sincronizacao, L2-13-versionamento-sync, L2-14-a-ingestao-de-fluxos, L2-14-b-camada-viva-historico, L2-14-c-regras-alertas-incidentes, L2-14-tempo-real, L2-15-a-geoparquet-bucket-catalogo, L2-15-analitica-grande, L2-15-b-consultas-duckdb-em-escala, L2-16-a-sdk-python-geo, L2-16-b-jupyter-por-inquilino-isolado, L2-16-c-script-vira-ferramenta, L2-16-notebooks-scripts, L2-17-crs-transformacoes, L2-18-camada-de-consulta-sql, L2-19-paridade-l2-e-manual, L3-01-b-unidades, L3-01-c-extracao-fator, L3-01-d-transformacoes, L3-01-e-combinacao, L3-01-f-explicacao, L3-01-g-tela-motor, L3-01-h-presets, L3-01-i-exportacao-metodo, L3-01-j-equivalencia-motor-logistico, L3-01-motor-servico, L3-02-a-monte-carlo-pesos, L3-02-b-sensibilidade-sobol-oat, L3-02-c-smaa, L3-02-d-comparacao-cenarios, L3-02-robustez, L3-03-ahp-pares, L3-04-restricoes, L3-05-localizar-regioes, L3-06-criterios-de-feicao, L3-07-agregacao, L3-08-pareto, L3-09-backtest-decisao-real, L3-10-corredor-custo-minimo, L3-11-fator-de-rede, L3-12-integracao-fluxo-e-api, L3-13-resultado-como-camada, L3-14-cobertura-dado-ausente, L3-15-metadado-fator, L3-16-desempenho-escala, L3-17-similaridade, L3-18-paridade-esri-amc, L3-19-multiescala, L3-20-narrativa-de-resultado, L4-01-a-pacote-de-ativos, L4-01-b-topologia-derivada, L4-01-c-importador-bdgd, L4-01-d-atributos-de-rede, L4-01-modelo-rede, L4-02-a-conectado-e-subrede, L4-02-b-montante-jusante, L4-02-c-isolamento, L4-02-d-lacos-e-caminho-curto, L4-02-e-configuracoes-de-tracado, L4-02-f-resultados-e-exportacao, L4-02-tracado, L4-03-a-regras-de-conectividade, L4-03-b-terminais, L4-03-c-edicao-topologica-no-mapa, L4-03-d-areas-sujas-e-validacao, L4-03-e-versao-de-rede, L4-03-edicao-rede, L4-04-a-controladores-e-tiers, L4-04-b-atualizar-e-exportar-subrede, L4-04-c-sumarios-por-subrede, L4-04-d-diagrama-esquematico, L4-04-e-diagrama-camadas-e-contencao, L4-04-subredes-diagramas, L4-05-a-exportar-opendss, L4-05-b-cim-iec-61970-61968, L4-05-c-pandapower-e-matpower, L4-05-conectores-rede, L4-05-d-epanet-inp, L4-05-e-gas-e-esgoto, L4-05-f-transmissao-sindat-sigel, L4-05-g-osm-power, L4-05-h-inspire-utility-networks, L4-06-a-contencao, L4-06-b-estrutura-postes, L4-06-c-objetos-nao-espaciais, L4-06-d-categorias-e-restricoes, L4-06-estruturas-regras-avancadas, L4-07-fluxo-de-potencia, L4-08-queda-de-tensao-e-carregamento, L4-09-perdas-tecnicas-por-segmento, L4-10-continuidade-dec-fec, L4-11-gd-conectada-e-hospedagem, L4-12-inspecao-vegetacao-na-faixa, L4-13-integracao-telemetria, L4-14-balanco-de-energia-por-alimentador, L4-15-serie-temporal-da-rede, L4-16-api-rest-compativel-un, L4-17-migracao-de-un-e-rede-geometrica, L4-18-rede-simples-trace-network, L4-19-planejamento-de-linha-nova, L4-20-consumidores-e-enderecos, L4-21-qualidade-e-saude-da-rede, L4-22-desempenho-em-escala, L4-23-isolamento-por-inquilino-na-rede, L4-24-cartografia-de-rede, L4-25-cenarios-e-se, L4-26-inspecao-de-campo-do-ativo, L4-27-curto-circuito-e-protecao, L4-28-identificadores-e-numeracao, L4-29-regras-de-atributo-de-rede, L4-30-manual-e-tour-de-rede, L4-parcelas-01-modelo-de-parcelas, L4-parcelas-02-fluxos-cogo, L4-parcelas-03-ajuste-e-qualidade, L5-01-a-layout-paginas, L5-01-app-builder, L5-01-b-widgets-mapa, L5-01-c-widgets-dado, L5-01-d-widgets-pagina-menu, L5-01-e-acoes-configuraveis, L5-01-f-modelos-app-galeria, L5-02-a-editor-de-nos, L5-02-b-execucao-proveniencia, L5-02-c-agendamento-variaveis, L5-02-d-exportar-python-importar-json, L5-02-e-iteradores-condicionais, L5-02-f-fluxo-como-ferramenta-e-api, L5-02-fluxos, L5-03-a-construtor-elementos, L5-03-b-logica-condicional-calculo-restricao, L5-03-c-dominios-listas-cascata, L5-03-d-repeticoes-relacionadas-anexos, L5-03-e-xlsform-ida-e-volta-idiomas, L5-03-form-builder, L5-04-a-blocos-de-conteudo, L5-04-b-imersivos-sidecar-tour-swipe, L5-04-c-temas-capa-colecao, L5-04-storymap, L5-06-motor-widgets, L5-07-fontes-vistas-mensagens, L5-08-editor-arrasto, L5-09-desfazer-refazer-rascunho, L5-10-temas-marca, L5-11-expressoes-no-navegador, L5-12-acessibilidade-i18n-construtores, L5-13-edicao-concorrente, L5-14-publicacao-links-embed, L5-15-vista-movel-responsivo, L5-16-agente-escreve-configuracao, L5-17-painel-elementos-avancados, L5-18-painel-parametros-url-vistas, L5-19-painel-expressoes-de-dado-tempo-real, L5-20-sites-paginas-publicas, L5-21-dados-abertos-catalogo-publico, L5-22-sites-dominio-proprio-tema, L5-23-apps-instantaneos-motor-galeria, L5-24-apps-instantaneos-modelos-1, L5-25-apps-instantaneos-modelos-2, L5-26-construtor-popup, L5-27-simbologia-por-arrasto, L5-28-galeria-simbolos-rampas-estilos, L5-29-construtor-relatorio-pdf, L5-30-relatorio-lote-agendado, L5-31-construtor-de-camada-esquema, L5-32-vistas-de-camada, L5-33-a-diagrama-de-trabalho, L5-33-b-modelos-e-trabalhos, L5-33-c-atribuicao-avancada-indicadores, L5-34-captura-rapida-designer-pwa, L5-35-missao-operacao-ao-vivo, L5-36-widgets-personalizados-sdk, L5-37-pacotes-modelos-entre-inquilinos, L5-38-importadores-configuracao-esri, L5-39-paridade-l5-e-manual, L6-01-acervo-casa, L6-01-b-view-so-leitura, L6-01-c-tela-acervo, L6-01-d-ficha-fonte, L6-01-e-assinatura-e-uso, L6-01-f-lgpd, L6-01-g-licenca-curada, L6-01-h-frescor-verificacao, L6-01-i-raster-e-arquivos, L6-01-j-multi-servidor, L6-02-b-wms-wmts, L6-02-c-wfs-ogcapi, L6-02-conectores-vivos, L6-02-d-arcgis-rest-externo, L6-02-e-stac-externo, L6-02-f-geoparquet-duckdb, L6-02-g-pmtiles-xyz-tilejson, L6-02-h-csv-url-geojson-kml, L6-02-i-google-sheets, L6-02-j-bancos-externos, L6-02-k-agendamento, L6-02-l-saude, L6-02-m-catalogo-endpoints-brasil, L6-02-n-etl-na-entrada, L6-02-o-importacao-exportacao-formatos, L6-03-paridade-conectores, L6-04-acervo-no-motor, L6-05-proveniencia-camada-externa, L6-06-descoberta-csw, L7-01-a-compose-perfis, L7-01-b-instalacao-conteiner-limpo, L7-01-c-dado-demonstracao, L7-01-instalador-limpo, L7-02-a-k6-cenarios, L7-02-b-pool-e-limites-por-inquilino, L7-02-carga, L7-03-a-antivirus-upload, L7-03-b-antivirus-anexos, L7-03-b-rate-limit-abuso, L7-03-c-ssrf-conectores, L7-03-d-injecao-consulta, L7-03-e-cabecalhos-csp-tls, L7-03-f-dependencias-cve-log-correcoes, L7-03-g-asvs-nivel2-pentest, L7-03-seguranca, L7-04-a-manual-capturas-geradas, L7-04-b-tour-primeiro-acesso, L7-04-c-manual-admin-runbooks, L7-04-d-videos-por-tarefa, L7-04-manual-e-tour, L7-06-a-metricas-exporters, L7-06-b-alertas, L7-06-c-logs-consulta-req-id, L7-06-d-paineis, L7-06-observabilidade, L7-07-a-replica-postgres, L7-07-alta-disponibilidade, L7-07-b-replica-garage, L7-07-c-ensaio-failover, L7-08-a-webhooks-eventos, L7-08-b-sdk-python, L7-08-c-sdk-js, L7-08-d-portal-api-chaves, L7-08-sdk-api-webhooks, L7-09-a-medidor-diario, L7-09-b-planos-limites-relatorio, L7-09-medicao-cobranca, L7-10-a-i18n-pt-en-es, L7-10-b-acessibilidade-wcag21aa, L7-10-i18n-acessibilidade, L7-11-a-appliance-licenca, L7-11-appliance-cliente, L7-11-b-appliance-sem-internet, L7-11-c-telemetria-opcional, L7-12-a-classificacao-retencao, L7-12-b-registro-tratamento-dpa-incidente, L7-12-lgpd-governanca, L7-13-a-chamados, L7-13-c-laco-agentico-suporte, L7-13-suporte-chamados, L7-14-extensoes-fdw, L7-17-capacidade-planejamento, L7-18-custo-por-inquilino, L7-20-trilha-auditoria, L7-21-pagina-status, L7-22-sla-e-incidentes, L7-23-pgbackrest-pitr, L7-24-drill-restauracao, L7-25-exportacao-inquilino, L7-26-cdn-tiles, L7-27-origem-br-soberania, L7-28-iso27001-controles, L7-29-roteiro-demonstracao, L7-30-teste-parceiro-pro-agol, L7-32-postgres-manutencao-versao, L7-33-modo-somente-leitura, L7-34-saude-profunda, L7-35-atualizacao-versao-assinada, L0-05-e-justica-entre-inquilinos, L0-14-identidade-visual, L0-15-marca, L4-01-h-alinhamento-inspire-gnm, L0-02-g-checagem-privilegio-papel-id | — |
| `L7-11-a-appliance-licenca` | 4 | pendente | 0 |  | L7-33-modo-somente-leitura, L7-25-exportacao-inquilino | — |
| `L7-11-appliance-cliente` | 4 | pendente | 0 |  | L7-01-instalador-limpo | — |
| `L7-11-b-appliance-sem-internet` | 4 | pendente | 0 |  | L7-01-a-compose-perfis | — |
| `L7-11-c-telemetria-opcional` | 4 | pendente | 0 |  | L7-11-b-appliance-sem-internet | — |
| `L7-13-a-chamados` | 4 | pendente | 0 |  | L7-04-manual-e-tour, L7-03-a-antivirus-upload, L0-07-admin-org | — |
| `L7-13-c-laco-agentico-suporte` | 4 | pendente | 0 |  | L7-13-a-chamados, L7-06-c-logs-consulta-req-id | — |
| `L7-13-suporte-chamados` | 4 | pendente | 0 |  | L7-04-manual-e-tour | — |
| `L7-14-extensoes-fdw` | 4 | pendente | 0 |  | L7-01-a-compose-perfis | oracle_fdw: licença do Instant Client (decisão do dono) |
| `L7-28-iso27001-controles` | 4 | pendente | 0 |  | L7-03-g-asvs-nivel2-pentest, L7-24-drill-restauracao | — |
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
| D38 | 2026-09-06 | multi-setor de rede (água, gás, rodovia — não só elétrica) e alcance internacional/baixo recurso: a arquitetura JÁ suporta (C3 do L4_CONCEITO.md: esquema da rede é DADO — pacote de ativos versionado, não código; água/gás/telecom já têm formato de importação declarado). A pergunta real é PRIORIZAÇÃO: investir agora em ingestão de dado real de um 2º setor (água é o candidato mais forte — padrão INSPIRE Water Network existe, EPANET/WNTR já no ADR, 2 bi de pessoas sem água segura é o gancho internacional) ou manter o fosso em elétrica (376 fontes, BDGD, PRODIST, OpenDSS) e só abrir setor novo com demanda real medida? Rodovia como REDE DE UTILIDADE não está no escopo hoje (temos routing/corredor de LT, não trânsito/pavimento — teria de nascer como linha própria, tema INSPIRE Transport Networks); construção NÃO é rede — é BIM/IFC, já existe como projeto separado (GABARITO) e não deve ser confundido com L4. | DECIDIDA 06/09/2026: alinhar o pacote de ativos (C3) ao INSPIRE Generic Network Model (não só ao Esri UPDM), para exportabilidade fora do Brasil. Água segue como 2º setor candidato, mas SEM data de início (aguarda demanda real). Rodovia pública = nova linha (L8), não item de L4. Infraestrutura PRIVADA de loteamento/condomínio (incorporadora de teste-shaped) = combinar com L4-parcelas + GABARITO, não com L8. |
| D39 | 2026-09-06 | L6-01-g-licenca-curada fechou em 29/40 fontes com licenca ESCRITA testada por HTTP (nao 40). Aceitar 29 como 'parcial' e seguir para o resto da linha L6, retomando este item quando aparecer nova fonte com geometria + portal com licenca real (ex.: IBGE se o WAF liberar, ou convenio de acesso)? Ou o dono quer abrir contato direto com algum orgao (ANP/ANM/SGB/IBGE) para conseguir o termo escrito que a pesquisa automatizada nao achou? | aberta |

## Medidas disponíveis (`tests/medidas/`)

| arquivo | gerado em | git_sha | medidas |
|---|---|---|---|
| `L0-01-repo.json` | 2026-09-06T00:25:55Z | `65a9fc2c0869` | 36 |
| `L0-02-e.json` | 2026-09-06T12:23:52Z | `e30515b57814` | 2 |
| `L0-02-tenant-auth.json` | 2026-09-06T13:00:50Z | `e2d5f9164f6b` | 36 |
| `L0-03-catalogo.json` | 2026-09-06T00:48:46Z | `94a669c6601f` | 12 |
| `L0-05-jobs.json` | 2026-09-06T00:27:09Z | `65a9fc2c0869` | 25 |
| `L0-08-d-ldap.json` | 2026-09-06T11:05:40Z | `19c4cb309029` | 2 |
| `L0-09-metadado-catalogo.json` | 2026-09-06T12:30:34Z | `e30515b57814` | 3 |
| `L2-10-c-expressao.json` | 2026-09-06T13:26:04Z | `9df2cff208eb` | 11 |
| `L5-05-documento-versoes.json` | 2026-09-06T12:29:01Z | `e30515b57814` | 1 |
| `L7-31-homologacao.json` | 2026-09-06T11:00:00Z | `pendente-do-commit-deste-item` | 7 |

Todo número em documento sai desses arquivos, com o comando que o gerou.

## Ledger (últimos registros)

- {"quando": "2026-09-06T14:18:58Z", "item": "L6-01-g-licenca-curada", "estado": "parcial", "nota": "29 fontes com geometria + licença ESCRITA testada por HTTP AO VIVO (plat.acervo_licenca, migração 043; scripts/acervo_licenca_sync.py), cada uma com URL/endpoint, evidência literal extraída da resposta e confiança documentada — nenhuma inventada. Amostra adversária de 10/29 reconfirmada manualmente por curl independente do script (10/10 OK). Portão pede >= 40; ficou em 29 (falta 11). Pesquisadas e NÃO incluídas por motivo concreto (ver handoff): IBGE (WAF bloqueia todo acesso não-navegador, inclusive curl com UA de browser, em www.ibge.gov.br e ftp.ibge.gov.br só diz 'todos os arquivos são públicos' sem termo de uso — mesmo padrão que a casa já classificava como não-declarado), ANP/ANM/SGB-CPRM/ICMBio/INCRA/IPHAN/DECEA/CONAB/DNIT/INMET/ONS/CEMADEN/Embrapa (sem portal CKAN/DCAT ativo encontrado; WFS GetCapabilities com AccessConstraints/Fees = NONE; ou só o rodapé genérico do template gov.br 'Creative Commons Atribuição-SemDerivações 3.0', que é sobre o CONTEÚDO EDITORIAL do site, não sobre os dados geográficos — decidido não contar como licença de dado). Estados ambientais com WFS (IAT-PR, IMASUL-MS, IDEMA-RN, SUDEMA-PB, SEMAD-GO, SEMA-RS, SEMA-MT, IPAAM-AM, INEA-RJ, IMA-SC etc.) testados via ArcGIS REST copyrightText (vazio) e via portais dados.<uf>.gov.br quando existentes (GO/RS/ES/SC/PB/RO/AC) sem dataset correspondente à camada ambiental específica. SICAR: termo carregado por JS, não estático (inacessível a HTTP simples), mantém 'nao-declarada'. Discrepância encontrada: MapBiomas está gravado com CC-BY-SA 4.0 em acervo.fonte.licenca (nota antiga da casa), mas o texto AO VIVO do rodapé diz CC BY 4.0 — usado o valor ao vivo, registrado como achado no handoff.", "commit": null, "sessao": "a44f35ad"}
- {"quando": "2026-09-06T14:26:23Z", "item": "L0-02-g-perfil-usuario", "estado": "entregue", "nota": "Migração 042 + PUT /api/eu (idioma/unidades/formato_data/visibilidade) + POST/DELETE /api/eu/foto (recorte 200x200 Pillow, SVG recusado). Testado via API (script equivalente ao pytest, ver bloqueio TOTP do superadmin plataforma) e e2e playwright real (captura L0-02-tenant-auth_perfil.png, verificada visualmente). Todas as clausulas do portao passam.", "commit": "b49559b", "sessao": "worktrees-2"}
- {"turno": 3, "item": "L0-02-g-perfil-usuario", "quando": "2026-09-06 14:27", "construido": "migracao 042 (5 colunas em plat.usuario); PUT /api/eu com idioma/unidades/formato_data/visibilidade na whitelist; POST/DELETE /api/eu/foto (Pillow recorte 200x200, SVG recusado com 415 antes de gravar, >1MiB recusado); foto na barra lateral sem reload; testes de api+e2e com captura; 2 casos novos na varredura cruzada", "medicoes": {}, "portao": "entregue", "commits": ["b49559b"], "proximo_passo": "idioma/unidades/formato_data ainda sem consumidor em outras telas; visibilidade_perfil sem tela de perfil-de-terceiro que leia; rodar suite oficial quando TOTP do superadmin plataforma for resolvido"}

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
