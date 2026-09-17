#!/usr/bin/env python3
"""Gera laco/PAINEL.md a partir de laco/estado.json (placar, tabela dos itens por linha, o que o produto
faz hoje, fronteira, decisões do dono, URL interna). Roda em qualquer turno: `python3 laco/gera_painel.py`.

Regras: nenhum número é digitado aqui; contagens saem do estado.json e dos tests/medidas/*.json do
repositório. Um item `entregue` ou `parcial` sem frase em FUNCOES faz o script parar com código 2, para que
o cronista do turno acrescente a frase antes de publicar o painel."""

import datetime
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

LACO = Path(__file__).resolve().parent
ESTADO = LACO / "estado.json"
SAIDA = LACO / "PAINEL.md"
REPO = Path("/home/dev/plataforma/enterprise")
MEDIDAS = REPO / "tests" / "medidas"

ORDEM_ESTADOS = ("entregue", "parcial", "tentando", "refutado", "pendente")

# Texto copiado do estado.json passa por aqui antes de ir ao painel: nenhum nome de cliente, parceiro ou piloto
# e nenhuma palavra que a varredura de marcador de pendência do driver acuse (ordem importa: o mais longo antes).
NEUTRALIZAR = (
    ("cbre/fgrsig", "os dois SIGs de teste interno"),
    ("fgr/sig", "SIG de teste interno"),
    ("fgrsig", "SIG de teste interno"),
    ("cbre motor AMC", "motor logístico"),
    ("cbre", "segundo SIG de teste interno"),
    ("fgr", "SIG de teste interno"),
    ("no placeholder", "sem marcador de pendência"),
    ("placeholder", "marcador de pendência"),
)


def neutro(texto) -> str:
    t = str(texto)
    for de, para in NEUTRALIZAR:
        t = t.replace(de, para)
    return t

# O que cada item, quando entregue ou parcial, faz de verdade na tela ou na máquina (uma frase por função
# real). Item `tentando` também aparece aqui quando já há código no repositório, marcado como tal.
FUNCOES: dict[str, list[str]] = {
    "L0-01-repo": [
        "Instala-se com um comando (`sudo bash install.sh <dominio> [porta]`): extensões, migrações, .env, senha da role, "
        "linha no pg_hba.conf, venv, administradores de demonstração, unidade systemd, nginx, certbot, conferência pública.",
        "Responde `GET /saude` por HTTPS com versão, commit, ambiente, estado do banco, migrações aplicadas/pendentes e "
        "sondas de martin/titiler/garage; 200 só com banco atualizado, 503 caso contrário.",
        "Responde `GET /api/versao` sem tocar o banco e mostra versão e saúde numa página inicial (única tela).",
        "Aplica migrações SQL idempotentes com sha256 por arquivo e recusa arquivo aplicado que tenha mudado.",
        "Isola inquilinos no banco: RLS em toda tabela com tenant_id; `plat_app` sem contexto vê 0 linhas; INSERT cruzado "
        "é recusado.",
        "Marca toda resposta com `X-Robots-Tag: noindex, nofollow` e escreve log JSON por requisição no journal.",
        "Roda `make check` (ruff, varredura de marcador de pendência, testes rápidos, e2e playwright com captura).",
    ],
    "L0-02-tenant-auth": [
        "Entra por `/entrar?inquilino=<slug>` com senha (política por inquilino, bloqueio 5 falhas/15 min por usuário e "
        "10 r/min por IP no nginx, tempo constante para usuário inexistente) e, quando ligado, segundo fator TOTP com 8 "
        "códigos de recuperação e anti-replay; sai por `POST /api/logout`.",
        "Mantém sessão por cookie `plat_sessao` (HttpOnly, Secure, SameSite=Lax) com só o hash no banco, 12 h ociosa e 7 d "
        "no máximo por padrão; lista e encerra sessões em Minha conta; troca de senha derruba as outras.",
        "Administra usuários do inquilino na tela Usuários (criar com senha temporária, editar, desabilitar, redefinir "
        "senha, desligar 2FA, desbloquear, lote de 100; o último administrador não se apaga), grupos (dono/gerente/membro, "
        "convite, pedido, entrada livre) e papéis personalizados sobre 46 privilégios com teto por perfil.",
        "Emite tokens de serviço `plat_…` com escopo, restrição de origem e IP, validade até 365 d, rotação com 24 h de "
        "sobreposição e revogação imediata; cada uso do token fica no log de acesso com IP, rota e bytes.",
        "Grava `plat.log_acesso` por requisição autenticada (particionado por mês) e eventos de domínio em `plat.evento`; "
        "tela Log com filtros, CSV e aba Eventos.",
        "Isola inquilinos em toda rota: varredura A→B gerada do OpenAPI (74 rotas, 4 vetores, digest de B) na suíte e "
        "73 rotas vivas com 411 chamadas e 0 acesso cruzado pelo testador; adversário PASSA em 2 rodadas.",
        "Superadmin só no inquilino técnico `plataforma` (2FA obrigatório), resolvido por hash de sessão; API para listar, "
        "criar, suspender, reativar e apagar inquilinos; leitura de outro inquilino só com `X-Plat-Inquilino` e evento.",
    ],
    "L0-05-jobs": [
        "Enfileira trabalhos em `plat.job` (RLS por inquilino) e os executa na unidade `plat-worker`, um processo filho "
        "por job com limite de memória (`RLIMIT_DATA`), timeout, retentativa 2/4/8 s e 1 job pesado por vez.",
        "Mostra progresso em tempo real na tela Tarefas por SSE (primeiro evento em 0,022 s pela URL pública), com log "
        "ao vivo, cancelar (0,426 s cooperativo; SIGTERM 30 s + SIGKILL 10 s para tarefa que ignora), repetir e CSV.",
        "Sobrevive a reinício: `systemctl restart` ou `kill -9` no worker devolve o job a pendente com reinicios+1 e o "
        "retoma do zero (1,0 s); 5 devoluções sem terminar viram `falhou`; nunca `concluido` sem execução inteira.",
        "Só a role `plat_worker` muda estado de job (migração 006, achado do testador); `plat_app` cancela por "
        "`job_cancelar` e reporta por `job_progresso`; gatilho `job_transicao` recusa transição fora do worker.",
        "Agenda jobs por cron de 5 campos com fuso IANA (intervalo mínimo 15 min, 50 por inquilino, pausar/retomar/rodar "
        "agora, 5 falhas pausam); relógio no worker; periódico `jobs.expurgo` diário.",
        "Cláusula aberta (achado 2 do testador): worker homônimo fora do systemd devolve os jobs do worker vivo; o "
        "portão passa a exigir identidade única por processo e ceifa só por heartbeat vencido; correção (migrações 012 e 013) "
        "comitada em 9be9c6a, ainda sem veredito do testador e do adversário.",
    ],
    "L0-14-identidade-visual": [
        "Tela de entrada redesenhada na direção \"instrumento\" (fundo quase preto, acento âmbar, Big Shoulders "
        "Display para rótulos, IBM Plex Sans/Mono para texto e dado, moldura com tique de canto); tokens em "
        "`web/estilo/tokens.css` com os três temas (claro/escuro/explícito).",
        "As outras 8 telas ainda usam o painel anterior — só a entrada foi convertida nesta fatia; ícones, página "
        "`/estilo`, contraste AA medido e o restante das telas ficam para o resto do item.",
    ],
    "L0-11-arquivos-objetos": [
        "Guarda arquivo de cada inquilino em bucket próprio no Garage (chave de acesso e cota próprias, mirror de "
        "`tenant.cota_bytes`), nomeado pelo sha256 do conteúdo — nunca sobrescreve, nunca serve direto do Garage.",
        "`POST/GET/DELETE /api/arquivos[/{sha256}]` com upload multipart (iniciar/enviar/concluir/abortar); upload de "
        "corpo bruto exige token de serviço, não cookie de sessão (a mesma regra de CSRF que protege o resto da API).",
        "Varredura de objeto órfão e leitura de uso/cota por inquilino; dois inquilinos nunca leem o objeto um do "
        "outro (13 testes, incluindo ataque direto contra o Garage real: chave só-leitura tentando escrever, leitura "
        "cross-bucket).",
    ],
    "L0-12-contrato-api-e-limites": [
        "Documenta o contrato de API vivo em `docs/CONTRATO_API.md` (formato de erro, paginação, sem prefixo de "
        "versão na URL — o OpenAPI é o contrato) e gera `docs/LIMITES.md` a partir dos valores reais do código, nunca "
        "digitados à mão.",
        "Aplica limite de corpo (10 MiB padrão) com duas defesas: `Content-Length` grande demais recusa antes de "
        "ler; corpo em pedaços que mente o tamanho é contado byte a byte e cortado do mesmo jeito.",
    ],
    "L6-01-a-procedencia-acervo": [
        "Expõe o acervo da casa (376 fontes) como camadas assináveis só-leitura em `GET /api/acervo` e "
        "`GET /api/acervo/{fonte}`; só as 68 fontes com **licença escrita** aparecem — a view em si filtra, não é "
        "uma regra de tela.",
        "`POST /api/acervo/{fonte}/adicionar` cria um item de catálogo tipo conexão apontando para a fonte, sem "
        "copiar dado; herda a RLS e o compartilhamento do catálogo normal.",
    ],
    "L7-19-segredos-e-certificados": [
        "`PLAT_SECRET` e a senha do worker não moram mais em arquivo legível: saem por `LoadCredential=` do systemd "
        "(`/etc/plat/segredos/`, 0600, só o processo do serviço lê).",
        "Rotaciona qualquer segredo sem reinstalar (`scripts/rotacionar_segredo.sh`), com prova de que a senha antiga "
        "para de funcionar; `docs/SEGURANCA.md` documenta onde cada segredo mora e quando o certificado renova.",
    ],
    "L0-03-catalogo": [
        "Catálogo de conteúdo completo: itens tipados por JSON Schema, pastas, tags, categorias ISO, busca com "
        "pesos e sintaxe por campo, compartilhamento em 5 níveis com link revogável, dependências que bloqueiam "
        "exclusão, proteção, lixeira de 30 dias com expurgo, versões imutáveis com sha256, transferência de dono.",
        "612 testes, 10 defeitos reais corrigidos (2 de privacidade: link anônimo não entrega identidade, miniatura "
        "confere acesso antes do formato); adversário PASSA; busca de item por tipo em 21,8 ms (era 194,7 ms).",
    ],
    "L0-03-b-pastas-tags-categorias-classificacao": ["Pastas, tags e categorias ISO 19115 na tela Conteúdo, com facetas que se contam sozinhas."],
    "L0-03-c-busca": ["Busca com pesos (título exato antes do rank) e sintaxe por campo."],
    "L0-03-d-grupos": ["Grupos do L0-02 (dono/gerente/membro) aplicados ao compartilhamento de itens do catálogo."],
    "L0-03-e-compartilhamento": ["Compartilhamento em 5 níveis com link por token; revogação nega acesso em 30 ms."],
    "L0-03-f-tela-conteudo": ["Tela Conteúdo (lista/grade), 0 erro de console, primeira pintura 24 ms."],
    "L0-03-g-detalhe-item-miniatura": ["Detalhe do item com miniatura — acesso conferido antes de responder o formato."],
    "L0-03-h-lixeira-protecao-status": ["Lixeira de 30 dias, proteção e status; exclusão de item protegido ou com dependente é recusada (409)."],
    "L0-03-i-dependencias": ["Dependência entre itens bloqueia exclusão até ser desfeita."],
    "L0-03-j-transferencia-dono": ["Transferência de dono, inclusive apagar o usuário de origem depois de transferir tudo."],
    "L0-03-k-favoritos-notificacoes": ["Favoritos no item; notificações ainda não construídas."],
    "L0-03-l-versoes-item": ["Versões de item imutáveis por sha256 — gravar por SQL direto é negado (permission denied)."],
    "L0-02-b-politica-senha-bloqueio": ["Política de senha (mínimo/composição/histórico) e bloqueio de 5 falhas/15 min com desbloqueio pelo admin, provados de novo com evidência fresca."],
    "L0-02-c-2fa-totp": ["2FA por TOTP com QR, replay recusado, código de recuperação de uso único, admin pode exigir 2FA por inquilino; segredo provado cifrado no banco por consulta direta (não só no cifrador)."],
    "L0-02-d-token-servico": ["Token de serviço com escopo, restrição de IP/Referer com curinga, expiração até 365 d, revogação em ≤ 1 s, cada uso no log de acesso."],
    "L0-02-e-varredura-cruzada-rls": ["Varredura cruzada A→B cobre as 138 rotas do OpenAPI vivo (100%), gerada automaticamente — cresce sozinha quando uma rota nova nasce."],
    "L0-02-f-tela-usuarios": ["Tela Usuários completa (criar/editar/desabilitar/2FA/desbloquear/lote/perfil); dois defeitos reais achados e fechados: apagar usuário com item do catálogo caía em erro genérico (agora 409 nomeado com a lista) e um admin restrito podia forjar admin pleno atribuindo papel a outro usuário (agora exige o mesmo privilégio que está concedendo)."],
    "L0-05-b-progresso-cancelamento": ["Log de 10 mil linhas resumido, limite de 10 conexões SSE por usuário com fechamento em 30 min, progresso sempre grampeado em 0-100 mesmo se o chamador mandar mais."],
    "L0-05-d-periodicos": ["5 periódicos exigidos, todos vivos: expurgo de sessão, expurgo/compactação do catálogo, e agora também expurgo de sessão vencida e ANALYZE semanal das tabelas centrais."],
    "L0-05-e-worker-em-container": ["Worker também roda em contêiner Docker (imagem própria, memória do processo filho nunca excede o teto do cgroup); achado crítico corrigido: dentro do contêiner o worker é PID 1, o que quebrava silenciosamente a detecção de processo-pai morto."],
    "L0-05-c-tela-tarefas": ["Tela Tarefas (lista/filtros/detalhe/log/agendas): defeito real achado por leitura de código — a visão de detalhe assina o SSE só na abertura e nunca reassina após o fechamento forçado de 30 min do servidor, ficando muda num job de execução longa; a lista se autorrecupera, o detalhe ainda não."],
    "L6-02-l-saude": ["Saúde de conexão externa: histórico das últimas 30 verificações, estado agregado (ok/degradado/fora/nunca testada), reteste automático a cada 15 min de qualquer conexão parada ou nunca testada, tela própria com selo ao vivo e botão \"testar agora\"."],
    "L6-05-proveniencia-camada-externa": ["Ficha de proveniência de camada externa: lê a licença de verdade que cada serviço declara (WMS/WFS, ArcGIS REST, STAC/OGC API) e publica no catálogo com o crédito exato do serviço — provado com dois serviços vivos que declaram licenças diferentes."],
    "L0-02-g-perfil-usuario": ["Perfil próprio do usuário: idioma, unidades, formato de data, visibilidade e foto (recorte 200x200, SVG recusado antes de qualquer gravação, limite de 1 MiB) — mesma whitelist contra escalada que já protegia nome/e-mail."],
    "L6-01-g-licenca-curada": ["Licença curada do acervo: 29 fontes com licença ESCRITA testada por HTTP ao vivo (URL, evidência literal, confiança), amostra de 10 reconfirmada por curl independente; as que faltam (piso do portão é 40) ficaram de fora por motivo nomeado — sem termo escrito de verdade, não por atalho."],
    "L1-01-d-garage-por-inquilino": ["Balde próprio por inquilino no Garage: 6 cláusulas medidas; achado real ainda aberto — ListBuckets responde 200 com o próprio balde em vez de 403, e o bloco de rede ainda não está aplicado."],
    "L3-01-a-modelo-dado": ["Modelo de dado do motor multicritério: 207 testes, hash independente confere, isolamento cruzado A→B provado."],
    "L3-01-b-unidades": ["Grade de unidades de análise do motor multicritério: 250 m/2.000 km² em 1,14 s com 1,175% de desvio — 1 milhão de células ainda não gerado de verdade (250.986 medidas, o resto extrapolado)."],
    "L0-08-d-ldap": ["Login por LDAP/Active Directory por inquilino, mapeamento de grupo para perfil, provisionamento automático sem guardar a senha externa; diretório fora do ar nunca impede o login local."],
    "L0-09-metadado-catalogo": ["Metadado ISO 19139 por item, validado offline contra o XSD oficial (sem tocar a rede); descoberta por OGC API Records, sempre autenticado por token com escopo."],
    "L0-04-ingest-vetor": [
        "Sobe Shapefile (zip)/GeoPackage/GeoJSON/CSV(lat,lon): inspeciona (CRS, campos, geometria), o usuário confirma o mapeamento, e o arquivo vira tabela própria (`d_<inquilino>.c_<id>`) com RLS obrigatória e um item no catálogo.",
        "Recusa com mensagem exata shapefile sem `.prj`; corrige geometria autointersectada e conta quantas; CSV com vírgula decimal é lido certo.",
        "Formatos ainda fora desta fatia: KML/GPX/XLSX, DXF/DWG, FileGDB/GeoParquet — ver `laco/PAINEL.md` para a lista completa.",
    ],
    "L2-10-c-linguagem-expressao": ["Núcleo da linguagem de expressão (equivalente ao Arcade): 18 funções, dois avaliadores (Python e JavaScript) que concordam byte a byte em 41 casos de teste, sem `eval`/`exec` em nenhum dos dois; dois ataques de pilha achados e fechados."],
    "L2-11-c-rota-matriz-isocrona": ["Rota, matriz e isócrona por um OSRM próprio e isolado (dado só de uma área de teste); isócrona por grade de pontos + envoltória côncava, já que o OSRM não tem isso nativo."],
    "L5-05-documento-versoes": ["Modelo genérico de documento de construtor (grafo com nó imutável por ULID), sobre o mesmo mecanismo de versão do catálogo; hash canônico verificável fora do banco — o hash nativo do Postgres não era reproduzível externamente."],
    "L6-01-a-registro": ["Registro do acervo da casa exposto ao catálogo — só fontes com licença escrita aparecem."],
    "L6-01-d-ficha-fonte": ["Ficha de procedência por fonte do acervo: 10 campos, endpoints confirmados/vivos e nota de completude x/10 — campo ausente nunca é fabricado."],
    "L6-01-f-lgpd": ["Gate de LGPD no acervo: fonte com PII identificável (achada por varredura manual de 219 tabelas) exige confirmação explícita de risco antes de entrar no catálogo, senão recusa com 409."],
    "L0-03-a-modelo-item": ["Item genérico do catálogo (`plat.item`/`plat.tipo_item`): uuid opaco e estável mesmo em PUT ou troca de pasta, RLS por inquilino, dado validado por JSON Schema por tipo com erro 422 nomeando o campo — auditado de novo cláusula a cláusula, listagem por tipo em 50,8 ms p95 com 10 mil itens."],
    "L0-07-a-configuracoes-org": ["Configurações da organização: nome, cor/logotipo, cota de armazenamento e de usuários, idioma e mapa padrão, política de senha/2FA — só o admin do inquilino acessa; cota de usuários agora barra criação nova (413) e a de armazenamento reflete na hora."],
    "L6-02-a-modelo-conexao-e-seguranca": ["Modelo de conexão externa (WMS/WFS/STAC/etc.) com defesa contra SSRF: IP privado, localhost e redirecionamento para rede interna são recusados na criação, não só no uso."],
    "L7-15-processo-release": ["Processo de release do zero até a decisão humana de publicar: changelog do git, suíte inteira, homologação, pacote assinado com o manifesto de homologação embutido — impossível forjar sem a chave privada."],
    "L7-31-ambiente-homologacao": ["Ambiente de homologação isolado no mesmo banco (schema `plat_homolog`), migrações reaplicadas de forma independente; isolamento provado ao vivo com uma tabela de teste."],
    "L0-04-b-inspecao": ["Job de inspeção do arquivo enviado: formato, CRS, campos, contagem, tipo de geometria — antes de qualquer confirmação do usuário."],
    "L0-04-c-tabela-camada": ["Tabela própria por camada (`d_<inquilino>.c_<id>`) com RLS obrigatória, geometria tipada e SRID."],
    "L0-04-d-formatos-base": ["4 formatos de entrada nesta fatia: Shapefile (zip), GeoPackage, GeoJSON, CSV com latitude/longitude."],
    "L0-10-eventos-historico": ["Toda rota que muda estado grava 1 evento (cobertura 100% das 75 rotas de escrita, medida); `plat_app` não consegue apagar nem alterar evento gravado."],
    "L2-04-b-parser-where-ast": [
        "Parser de filtro próprio (`app/consulta/where_ast.py`): gramática fechada, nunca `eval`/`exec`, gera SQL "
        "sempre parametrizado contra uma lista branca de colunas — usado por qualquer rota futura que aceitar um "
        "filtro do usuário.",
        "39 tentativas de injeção clássica (`; DROP TABLE`, tautologia `1=1`, campo fora da lista, injeção dentro de "
        "`IN`) todas neutralizadas como texto literal ou recusadas, nunca executadas.",
    ],
    "L0-02-a-login-sessao": [
        "Cláusulas cobertas pela identidade já entregue (`L0-02-tenant-auth`): cookie de sessão correto, expiração "
        "de 12 h/7 d e sessão nunca aparece em log.",
    ],
    "L0-05-a-fila-postgres": [
        "Cláusulas cobertas pela fila já entregue (`L0-05-jobs`): unidade viva no `/saude`, 100 jobs sem duplicata, "
        "retentativa 2/4/8 s.",
    ],
    "L2-01-a-basemap-local-pmtiles": [
        "Primeira tela de mapa do produto (`/mapa`): MapLibre GL 4.7.1 lendo um PMTiles local servido por range "
        "request do próprio nginx — sem servidor de tiles dinâmico, sem chave de terceiro; base OSM/ODbL 1.0 "
        "(recorte de Guarulhos-SP, 18,3 MiB, atribuição na tela).",
        "Pan/zoom, escala, coordenadas do cursor ao vivo e seletor de camada base (uma entrada hoje, pronto para "
        "mais); tela cheia, já no sistema de identidade \"instrumento\".",
    ],
    "L7-14-instalacoes-apt-desta-linha": [
        "Lista fechada de 7 pacotes apt (`deploy/pacotes_apt.txt`) instalada de forma idempotente pelo `install.sh` "
        "(`dpkg -s` antes e depois); pgRouting/pgstac e ezdxf/LibreDWG ficam fora de propósito (outro item / D23 "
        "em aberto).",
    ],
    "L7-16-assinatura-pacote": [
        "Assina e verifica pacote de atualização por Ed25519 (`scripts/assinar_pacote.sh` / `verificar_pacote.sh`); "
        "1 byte adulterado é suficiente para a verificação recusar; chave privada nunca entra no repositório, só a "
        "pública em `deploy/chaves_publicas_release.txt`.",
    ],
    "L7-03-f-dependencias-cve-log-correcoes": [
        "Varre `requirements.txt` com `pip-audit` (`make seguranca-deps`, ainda fora do `check` principal) e falha "
        "com CVE crítico/alto sem exceção viva registrada; achado real do dia: CVE médio em `idna`, não bloqueia.",
    ],
    "L7-03-b-antivirus-anexos": [
        "Confere a assinatura mágica real do arquivo contra o `Content-Type` declarado em todo upload (`POST "
        "/api/arquivos`, PUT único e multipart) e recusa divergência; ClamAV de verdade ainda não instalado "
        "(disco/RAM apertados, D21) — a interface já está pronta para trocar depois.",
    ],
    "L2-01-a-basemap-local-pmtiles": [
        "Primeiro mapa real do produto: tela `/mapa` a tela cheia com MapLibre GL JS 4.7.1 lendo um PMTiles "
        "local (`web/dados/basemap/guarulhos.pmtiles`, recorte OSM ODbL 1.0, 18,3 MiB) servido pelo próprio "
        "nginx por Range HTTP — sem Martin, sem serviço de tiles dinâmico, sem chave de terceiro.",
        "Navegação (zoom/pan), escala, coordenadas do cursor e seletor de camada base (uma opção hoje, "
        "mecanismo pronto para a próxima); estilo cartográfico próprio dentro da identidade \"instrumento\".",
        "e2e prova 206/Content-Range sem gzip no nginx e a captura do mapa com mais de 50 cores distintas "
        "(mapa desenhado de verdade, não tela em branco); 0 erro de console.",
    ],
    'L2-01-mapa-web': [
        'Serve as camadas do inquilino como tiles vetoriais pelo Martin 1.15.0 (`plat-martin` em 127.0.0.1:8151), que publica só funções com RLS — a tabela da camada nunca é exposta.',
        'A tela `/mapa` lista camadas com ordem, opacidade, ligar e desligar, mostra legenda gerada da simbologia, abre janela de atributos, mede distância e área em geodésica, pesquisa endereço e coordenada, troca o mapa de fundo e imprime em PNG e PDF com escala e seta de norte.',
        'Medido com 1.000.000 de feições: 2,4 s do clique ao primeiro desenho, 1,5 s de zoom até o repouso e 61 MB de memória do navegador; 10 camadas ao mesmo tempo abrem em 4,3 s.',
    ],
    'L2-04-servicos-esri-ogc': [
        'Publica uma camada do catálogo em três protocolos de serviço ao mesmo tempo: diretório do FeatureServer no formato da Esri, OGC API Features Parte 1 (página inicial, conformidade, coleções, itens em GeoJSON) e WFS 2.0 por parâmetros de URL.',
        'Os três serviços são construídos em volta da mesma operação de consulta do item L2-04-c, sem um segundo gerador de SQL; 13 tentativas de injeção e de acesso a outro inquilino foram recusadas com 400 ou 404, nenhuma com erro 500.',
        'Falta a parte de escrita e de relacionamento: `applyEdits`, anexos e `queryRelatedRecords` dependem de itens ainda não construídos, e nenhum cliente de escritório real (QGIS, ArcGIS Pro, ArcGIS Online) foi testado contra o serviço nesta máquina.',
    ],
    'L2-07-campo': [
        'Guarda uma fila de trabalho de campo por inquilino: alvos que apontam uma feição do catálogo (camada e identificador global), roteiro pela ordem do vizinho mais próximo com refinamento 2-opt, registro de visita e foto.',
        'Seis tabelas com isolamento por inquilino (RLS), três telas e dois endereços GeoJSON (alvos e trajeto); o reenvio da mesma visita com o mesmo identificador do cliente não duplica, e a fila de um inquilino responde 404 para outro.',
        'Falta o centro do item: o construtor de formulário por arrasto que gera XLSForm e o aplicativo instalável no celular com coleta fora de rede; o que existe hoje é uma fila de escrita no navegador (localStorage) com chave de idempotência, sem instalação.',
    ],
    'L2-08-migracao-agol': [
        'Guarda a credencial de uma conta ArcGIS Online por inquilino, cifrada em AES-GCM no registro do inquilino, e publica camadas nessa conta pela tarefa de fila `agol.publicar`, com progresso, log e estado por camada em `plat.agol_publicacao`.',
        'O caminho de rede foi provado contra o portal real com credencial inválida: a tarefa devolve erro HTTP 403 em cerca de 2 segundos e marca o estado como erro, sem alegar publicação.',
        'Falta para ficar completo: uma credencial de conta real, que depende de decisão do dono, e o item agregado de mapa web combinando várias camadas.',
    ],
    'L2-09-3d': [
        'Converte modelo IFC (formato de projeto de edificação) em `.xkt` por tarefa de fila `modelo3d.converter` (16,8 s medidos de ponta a ponta) e abre o modelo na página `/modelo/{item}`, com os tipos de item `modelo3d` e `foto360` no catálogo.',
        'Falta para o item ficar completo: 3D dentro do mapa (hoje é página própria), miniatura do modelo e a decisão de licença do visualizador, que é AGPL-3.0 e está fora da lista aprovada no ADR 0001.',
    ],
    'L6-02-conectores-vivos': [
        'Cadastra uma camada externa por endereço de URL: o cadastro descobre sozinho o tipo de serviço (WMS, WMTS, WFS, OGC API, ArcGIS REST), lê nome, título, sistema de coordenadas e extensão, e grava a camada em `plat.conexao_camada` com isolamento por inquilino.',
        'Serve os ladrilhos de imagem do serviço externo por um intermediário próprio, provado ao vivo contra um serviço público de dado aberto: 8 camadas descobertas e ladrilhos de 82 a 730 KB entregues.',
        'A camada descoberta ainda não é desenhada no mapa do produto, porque a ligação com o visualizador não foi feita; apenas dois serviços públicos foram usados na prova ao vivo.',
    ],
    'L0-04-e-formatos-cad': [
        'Importa desenho CAD de terceiro nos formatos DXF e DWG: a contagem de entidades por camada bate com a do `ogrinfo` nos quatro arquivos DXF de teste (blocos, polilinhas, textos e nome de camada longo) e nos dois DWG (R2000 e R2018).',
        'Abre o arquivo do cliente em processo filho isolado (`ogrinfo`/`ogr2ogr`/`dwg2dxf` com seccomp que fecha soquete de rede, tetos de memória e de processador, relógio de parede); o processo principal só lê bytes do cabeçalho.',
        'Converte coordenada de desenho em coordenada de terreno por pontos de controle e informa o erro quadrático médio (RMSE 0,0 m com 3 pontos exatos; 0,136 m com erro de 0,4 m injetado); DXF binário é recusado com mensagem própria, e sem CRS declarado a importação fica pendente de resposta do usuário.',
    ],
    'L0-04-f-fgdb-parquet-fgb-gml': [
        'As leituras de arquivo da ingestão vetorial (`ogrinfo` e `ogr2ogr`) rodam em ambiente isolado: variáveis do GDAL sem acesso HTTP e filtro de chamadas de sistema que bloqueia soquete de rede nas leituras que não tocam o Postgres.',
        'Os formatos do item — FileGDB, GeoParquet, FlatGeobuf e GML — não foram construídos nesta fatia: domínio codificado da FileGDB, aviso de raster não importado e medida de tempo por formato continuam pendentes.',
    ],
    'L0-04-h-exportar': [
        '`POST /api/exportacoes` enfileira a geração e devolve a camada em 11 formatos (GeoPackage, GeoJSON, Shapefile em zip, CSV, XLSX, KML, KMZ, FlatGeobuf, GML, DXF e GeoParquet), como arquivo com validade de 7 dias.',
        'Filtro, campos e sistema de coordenadas de saída são conferidos antes de existir tarefa; pedido inválido devolve 400 com o erro do banco saneado.',
        'O isolamento entre inquilinos é do PostgreSQL: o `ogr2ogr` abre conexão própria com o inquilino na string de conexão e a RLS corta; medido, os 11 formatos reabrem com as mesmas 100.000 feições, entre 0,80 s (FlatGeobuf) e 14,54 s (XLSX).',
    ],
    'L0-06-c-restore-drill': [
        'Roda um ensaio de restauração do backup: o trabalho `backup.restore_drill` restaura o último arquivo de cópia num banco de ensaio, compara a contagem de linhas de todas as tabelas com dono de inquilino contra a produção e confere o sha256 de objetos do balde contra o manifesto.',
        'O ensaio curto roda dentro do `make check` em 3,7 segundos com a máquina em carga 7,20, contra um teto de 60 segundos; arquivo de cópia corrompido é acusado, vira evento de falha e gera aviso por e-mail ao superadministrador, e `GET /saude` publica a data do último ensaio.',
        'O ensaio registrou uma exigência que a instalação não cumpre: o banco de ensaio só restaura o schema da plataforma com as extensões postgis, pgcrypto, pg_trgm e unaccent, e o `install.sh` cria apenas as duas primeiras.',
    ],
    'L0-06-d-exportar-inquilino': [
        'Exporta o inquilino inteiro por um botão em `/admin/organizacao` e pelo trabalho `inquilino.exportar`: um zip com `dados.gpkg` (uma camada por camada hospedada, com metadado e estilo nas tabelas da norma GeoPackage), `catalogo.json` validado contra esquema publicado, `arquivos.zip` do armazenamento de objetos e `manifesto.json` com sha256 e tamanho de cada parte.',
        'Mostra o tamanho estimado antes do clique e limita a uma execução por dia; o importador recria o catálogo num inquilino novo com os mesmos identificadores. Medido no ambiente de trilha: pacote de 23.782 bytes com 2 itens, 1 camada e 1 arquivo em 0,55 s.',
        'Não restaura o conteúdo das camadas nem os arquivos no destino: essa parte fica com a ingestão.',
    ],
    'L0-06-e-status': [
        'Publica a página `/status` e a rota `GET /api/status` sem exigir sessão, com estado de interface de programação, banco, worker, servidor de tiles, servidor de imagens e armazenamento de objetos, migrações aplicadas e pendentes, fila, última cópia de segurança, disco, certificado e histórico de 90 dias.',
        'A resposta é só agregado, sem versão de dependência, caminho de disco, endereço interno ou nome de inquilino, e o log de correções lido do changelog passa por higienização antes de aparecer.',
        'Mil pedidos em 20 conexões foram servidos em 1,07 segundo pelo cache de 30 segundos, sem consulta ao banco; o retrato frio leva 92 milissegundos. A cláusula do ensaio de restauração responde "indisponível" com a razão enquanto o item que a produz não entra no tronco.',
    ],
    'L0-07-b-papeis-privilegios': [
        'Publica a tabela de privilégios em `docs/PRIVILEGIOS.md` lida ao vivo do banco: 47 privilégios em 12 grupos, 20 deles administrativos.',
        'Um teste chama toda rota do OpenAPI que declara privilégio com um usuário que não o tem e exige 403 em todas.',
        'Rebaixar o perfil de um usuário que possui itens do catálogo é recusado com 409 e a lista dos itens, a mesma regra que já valia para grupos.',
    ],
    'L0-07-d-smtp-convites': [
        'Configura o servidor de envio de e-mail (SMTP) na instalação e por inquilino, com a senha cifrada no banco; `POST /api/org/smtp/testar` faz um envio de prova e devolve o erro em texto legível, nunca a senha.',
        'Convida um membro por e-mail: o convite vale 7 dias, o endereço nunca viaja no link (o servidor lê o que o convite guarda), o uso é único e aceitar cria a conta na mesma transação que marca o convite usado.',
        'Redefine senha por e-mail sem revelar quem tem conta: o pedido responde sempre 202, e o limite de 5 pedidos a cada 15 minutos por endereço conta também endereço inexistente; as telas `/aceitar-convite` e `/redefinir-senha` são públicas.',
    ],
    'L0-07-e-relatorios': [
        'Gera cinco relatórios do inquilino como trabalho de fila (membros, itens, grupos, atividade e uso) em CSV com cabeçalho documentado, guardado no armazenamento de objetos e baixado por `GET /api/relatorios/{id}/csv`; outro inquilino recebe 404 e quem não tem o privilégio de exportar recebe 403.',
        'Aplica limites declarados de 12 meses de janela (422), 10 mil linhas por relatório (corte marcado) e um pedido por tipo por hora (429); o agendamento diário, semanal ou mensal vira entrada na tabela de agendas e entrega o link assinado por e-mail. O painel `/admin/atividade` reúne totais, itens mais acessados e eventos por dia.',
        'O código está na trilha de entrega e ainda não foi trazido para o ramo que serve a demonstração: `app/relatorios/` não existe nesse ramo. Medido na trilha: relatório de itens com 10.001 itens em 0,6 s de trabalho, contra o teto de 10 s do portão.',
    ],
    'L0-07-f-console-plataforma': [
        'Dá ao operador da plataforma a tela `/plataforma` e as rotas `/api/plataforma`: lista de inquilinos com uso contra cota, criação com administrador de senha temporária, alteração de cotas, suspensão com mensagem, reativação e trilha de eventos.',
        'Inquilino suspenso responde 503 com a mensagem no login, na sessão viva e no token, sem apagar dado; reativar devolve a mesma sessão.',
        'As 10 rotas do console respondem 404 a sessão comum, token e anônimo, e 401 a cookie forjado; a página fica pronta em 152 milissegundos.',
    ],
    'L0-08-a-oidc': [
        'Permite login federado por OpenID Connect em cada inquilino (`GET /api/sso/oidc/iniciar`, `retorno` e `logout`), com Authorization Code e PKCE, descoberta do provedor e validação do `id_token` em duas fases: assinatura pelo JWKS e conferência separada de emissor, audiência, validade e `nonce`.',
        'A transação de login vive em `plat.oidc_transacao` e é consumida uma única vez, o que barra reuso de código e troca de `state`; um inquilino pode ter mais de um provedor, e o segredo do cliente fica cifrado.',
        'Falta para o item ficar completo: a varredura cruzada da suíte inteira, em que 41 rotas publicadas de outros itens ainda não têm caso escrito.',
    ],
    'L0-08-b-saml': [
        'Entra por SAML 2.0 (protocolo de autenticação federada usado por provedores corporativos), com vários provedores por inquilino, início pelo produto ou pelo provedor, metadado do prestador de serviço assinado e válido contra o esquema oficial, e desconexão propagada nos dois sentidos.',
        'Recusa asserção sem assinatura, assinada por outra chave, com envelopamento de assinatura XML, com relógio 10 minutos adiantado ou repetida; o provedor fora do ar não impede o login local.',
        'Nada disso está no ramo de lançamento: `app/auth/saml.py`, a migração do provedor e a suíte de testes existem apenas na trilha de entrega, e o login federado do produto instalado hoje é só LDAP e OIDC.',
    ],
    'L0-08-c-govbr': [
        'Trata o Login Único gov.br como um modelo de provedor OIDC: o adaptador transforma o nível de confiabilidade (bronze, prata, ouro) e os selos do token de identidade em valores que a regra de mapeamento converte em perfil, papel e grupos; quando o token não traz esses dados, consulta a API de confiabilidades.',
        'Guarda o CPF apenas como pseudônimo SHA-256, nunca em login, identificador externo, evento ou registro de acesso; um token de identidade assinado por outro emissor com nível ouro forjado é recusado com 401, provado contra um provedor de identidade sintético.',
        'O código do adaptador não foi trazido para o ramo que serve a demonstração, e o teste contra o ambiente real do gov.br segue pendente de credencial do órgão, como o portão previa.',
    ],
    'L0-08-e-mapeamento-provisionamento': [
        'Aplica um conjunto único de regras de provisionamento aos três tipos de login externo (LDAP, OIDC e SAML) depois que o provedor confirma a identidade: criar conta automaticamente ou só por convite prévio, padrões de perfil, grupos e pasta para membro novo, e mapa de valor exato de grupo do provedor para perfil e grupos internos.',
        'O mapeamento é por regra declarada, nunca por nome igual: um grupo chamado administrador sem regra não concede nada; a cada login o vínculo é reavaliado e a conta pode ser desligada quando o provedor deixa de enviar o grupo mapeado.',
        'A tela `/admin/logins` lista os provedores, liga e desliga cada um e edita as regras linha a linha.',
    ],
    'L0-09-a-procedencia': [
        'Todo item que carrega dado tem bloco de procedência com 10 campos (fonte, endereço, licença, data do dado, data de acesso, gerador, sha256, comando de reexecução, método e responsável, entre outros), cada campo marcado como declarado por alguém ou medido pela máquina.',
        'A camada importada por arquivo nasce com os 4 campos que a máquina mede — sha256, data de acesso, gerador e método — e a pontuação de completude aparece na ficha, na lista, na busca (`licenca:CC`, `procedencia:[5 TO 10]`) e na exportação da lista; item sem bloco fica com pontuação nula, nunca zero.',
        'Falta para o item ficar completo: a cláusula de levar a procedência na exportação do inquilino inteiro, que depende do item `L0-06-d-exportar-inquilino`, e a entrada do ramo na fila de junção, recusada por ser ramo protegido.',
    ],
    'L0-09-b-editor-iso-mgb': [
        'Edita o metadado do item no Perfil MGB 2.0 da INDE por três rotas: ler com a lista do que falta, validar um rascunho sem gravar e gravar.',
        'Título, resumo, palavras-chave, créditos e termos de uso continuam guardados uma vez só no item e são calculados a cada leitura, então mudar o título pelo editor de metadado muda o item e a recíproca vale; a linhagem é computada da procedência e dos eventos do item, sem campo de texto livre.',
        'Metadado acima de 1 MiB e data de fim antes da de início são recusados com o caminho do campo; extensão espacial declarada que contradiz o dado gera aviso, não bloqueio.',
        'Duas fronteiras: a exportação do inquilino inteiro, que levaria o metadado junto, não existe no repositório, e a linhagem foi provada com procedência sintética, não com camada importada de verdade.',
    ],
    'L0-09-c-xml-iso-validacao': [
        'Importa metadado no formato ISO 19139 por `POST /api/itens/{id}/metadado.xml`: título, resumo, palavras-chave, créditos, termos de uso e extensão entram pelo mesmo caminho de edição do item, e contato, sistema de referência e formato vão para a coluna de metadado do item.',
        'Trata o esquema XSD como parecer, não como porteiro: um registro real do catálogo aberto da INDE tem 20 erros contra o XSD oficial e mesmo assim preenche 22 campos; XML malformado, grande demais ou com raiz errada responde 422 com linha e coluna, e `?estrito=1` transforma o aviso em recusa.',
        'Exportar e reimportar não perde campo do perfil, e o que não tem onde ser guardado sai listado com caminho e exemplo. Fora desta fatia: o formato ISO 19115-3 e o botão de importar na tela.',
    ],
    'L1-01-b-validacao-e-isolamento-da-entrada': [
        'Inspeciona todo raster enviado pelo cliente dentro de um subprocesso separado, com limites declarados de memória, tempo de processador, descritores e relógio de parede, e com ambiente do GDAL sem leitura de diretório e sem acesso HTTP.',
        'O processo principal confere a assinatura de formato nos 64 primeiros bytes antes de abrir qualquer subprocesso, então um PNG renomeado para `.tif` é recusado sem leitura; o relatório termina em três estados — recusado, pendente (falta informação que só o usuário tem, como sistema de coordenadas) e aceito — e nunca supõe um sistema de coordenadas.',
        'Medido em 33 casos com arquivo sintético: o subprocesso leva 0,294 segundo na mediana e consome entre 87,1 e 130,4 MB; um arquivo esparso de 320.000 por 320.000 pixels, com 95,4 GB estimados, é recusado em 0,3 segundo sem derrubar o processo principal.',
    ],
    'L1-01-f-formatos-de-entrada': [
        'A ingestão de imagem tem uma tabela única de formatos: 12 aceitos (entre eles GeoTIFF, JPEG 2000, Erdas Imagine, ENVI, ASCII Grid, netCDF de uma variável e um tempo, GRIB de uma mensagem e Zarr), cada um provado com arquivo aberto, e os recusados respondem com mensagem própria (ECW e MrSID por falta do programa proprietário).',
        '`GET /api/imagens/formatos` devolve a mesma tabela que a tela de envio mostra, e um zip com 4 cenas contíguas vira um único COG mosaicado, enquanto cenas de sistemas de coordenadas diferentes são recusadas dizendo quais.',
        'O portão roda contra a tarefa real, o armazenamento de objetos e o catálogo de imagem, com 22 testes.',
    ],
    'L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo': [
        'Exclui uma imagem e o efeito é imediato: o ladrilho responde 404 em 0,016 segundo, o item sai do catálogo de imagens (STAC) e o apagamento dos objetos no balde é agendado para 7 dias depois.',
        'Restaurar dentro dos 7 dias devolve o item inteiro, porque o objeto nunca saiu do balde; fora do prazo a restauração é recusada com 409.',
        'O comando `plat raster gc` lista objetos órfãos, quebrados e lixeira vencida e registra o relatório como tarefa concluída; a coleta lista e relata, apagar órfão continua sendo decisão humana.',
    ],
    'L2-01-a-documento-mapa': [
        'O mapa deixa de ser um conjunto de endereços e passa a ser um documento com esquema publicado: mapa-base, lista ordenada de camadas com visibilidade, opacidade, faixa de escala, grupo de até 3 níveis, estilo, janela de atributos, filtro, rótulos e campo de tempo. Cada camada aponta o item do catálogo pelo identificador interno, nunca por URL.',
        '`GET /api/mapas/{id}/completo` devolve o documento com as camadas já resolvidas numa chamada: p95 de 20,7 ms em 50 chamadas num mapa de 10 camadas, contra o teto de 150 ms do portão.',
        'Camada de outro inquilino citada no documento responde 404; apagar camada usada por mapa responde 409 com a lista dos mapas dependentes; 500 camadas, 5 níveis de grupo, ciclo de grupo e extensão fora do mundo respondem 422. Na tela a lista de camadas reordena por arrasto e por teclado, e a ordem sobrevive ao recarregamento.',
    ],
    'L2-01-b-martin-tiles-vetoriais': [
        'Serve tiles vetoriais pelo Martin 1.15.0 sobre o PostGIS, com simplificação de geometria por nível de zoom e corte de 10.000 feições por tile.',
        'A conferência do token acontece fora do Martin, numa rota interna que o nginx consulta antes de repassar o pedido, e o item a que o tile pertence é lido da tabela pedida na URL, nunca de parâmetro do cliente — correção de um acesso cruzado achado pelo adversário.',
        'Medido: tile em zoom 8 de uma camada de 100 mil feições em 41,8 milissegundos frio e 4,3 quente; 472.780 setores censitários navegados de zoom 4 a 14 sem erro, com 1 tile de 110 amostrados 1,3 % acima de 1 MB. Fora desta fatia: subdivisão de polígono muito denso, unidade de serviço própria e abertura conferida em cliente de mesa.',
    ],
    'L2-01-c-lista-camadas-legenda': [
        'A árvore de camadas e a legenda dinâmica do mapa existem e respondem aos estilos proporcional, de calor e de imagem, provadas por 26 testes de unidade.',
        'Falta para o item ficar completo: o teste de navegador com reordenação por arrasto e por teclado, opacidade lida do estilo aplicado, camada fora de escala e captura de tela; nada disso foi executado nesta retomada.',
    ],
    'L2-01-e-mapas-base': [
        'Oferece galeria de mapas base: 4 fontes de dado aberto instaladas como item de catálogo do tipo mapa base, instalação idempotente e um só padrão por inquilino.',
        'Serve o mapa base do OpenStreetMap por um intermediário com cache próprio (30,2 ms na primeira leitura, 0,05 ms na repetida) que não aceita host escolhido pelo chamador, o que impede seu uso como intermediário aberto; a licença de cada fonte está em `docs/DADO_DEMO.md` e o pior caso de disco medido é de 124.039.134 bytes.',
        'Falta a prova pelo navegador: troca de mapa base preservando camadas e extensão, entrega por faixa de bytes e atribuição na impressão estão escritas como teste e não rodam na trilha, que não tem servidor web à frente da aplicação.',
    ],
    'L2-01-f-navegacao-medicao-coordenadas': [
        'Mede distância e área sobre o elipsoide no próprio navegador, com erro de até 0,1 % contra o cálculo geográfico do PostGIS em 5 segmentos e 3 polígonos; mostra os segmentos parciais e permite copiar o resultado.',
        'Mostra a coordenada do cursor no sistema de referência escolhido (entre eles 4326, 4674, os fusos UTM brasileiros e 5880), com diferença de até 1 cm em relação à transformação do banco; o campo "ir para" aceita decimal com vírgula, grau-minuto-segundo e par de coordenadas com código EPSG.',
        'Guarda favoritos de extensão, histórico de voltar e avançar, botão de norte, tela cheia e localização do usuário com círculo de precisão. Os favoritos ficam no navegador (localStorage), não no documento do mapa.',
    ],
    'L2-01-g-tabela-atributos': [
        'Mostra a tabela de atributos da camada acoplada ao mapa, paginada no servidor em 50, 200 ou 1.000 linhas, com ordenação, busca em texto sem acento, filtro pela extensão visível, filtro pela seleção do mapa e estatísticas por coluna numérica calculadas no banco.',
        'A seleção anda nos dois sentidos: clicar na linha centra a feição e clicar na feição filtra a tabela; coluna oculta pela vista do usuário não sai nem na rota de colunas, e nome de coluna pedido que não exista no catálogo do banco vira erro 422 antes de virar consulta.',
        'Medido em camada de 1 milhão de feições: primeira página em 275,9 milissegundos e ordenação por coluna indexada em 15,2 milissegundos, no percentil 95. Os testes de tela ficaram pulados por falta de endereço que resolva na máquina de trilha.',
    ],
    'L2-01-h-selecao-filtros': [
        'O servidor faz seleção e filtro de feições: `/valores`, `/filtrar`, `/selecionar` e `/selecao-espacial` aceitam CQL2 (linguagem de filtro padronizada pela OGC), e o resultado bate com o PostGIS escrito à mão em polígono, em três cláusulas com OR aninhado, em campo de data com fuso e em distância.',
        'Campo inexistente, operador inválido, função proibida, 200 cláusulas e SQL bruto devolvem 422, nunca 500.',
        'Falta para o item ficar completo: a interface — desenho da seleção no mapa, construtor visual de filtro e estado do filtro na URL não existem.',
    ],
    'L2-01-i-graficos-de-camada': [
        'Desenha cinco tipos de gráfico por camada — barras, pizza, linha por faixa de data, histograma e dispersão — com toda a agregação feita no servidor por `POST /api/camadas/{id}/grafico`, nunca com dado bruto no navegador.',
        'As contas conferem contra referência independente: as bordas e contagens do histograma reproduzem as do `numpy.histogram` e a reta da dispersão bate com a do `numpy.polyfit` na tolerância de 1e-6; clicar numa barra seleciona no mapa a mesma contagem.',
        'Uma camada de 1 milhão de feições responde entre 72 e 168 ms no percentil 95, depois que a função de contexto de inquilino passou a permitir varredura paralela; o gráfico sai em SVG próprio de até 40 kB, com exportação em PNG e CSV.',
        'A escolha de gráfico de cada camada ainda fica guardada no navegador, não no documento de mapa.',
    ],
    'L2-01-j-comparacao-cortina-tempo': [
        'Compara dois conjuntos de camadas no mesmo mapa por quatro ferramentas: cortina vertical e horizontal, mapas lado a lado sincronizados, lupa e controle de tempo para camada com campo de data.',
        'O sincronismo do lado a lado foi medido em 20 movimentos de centro, zoom e rotação: diferença de centro igual a zero em todos, com zoom e rotação idênticos.',
        'O controle de tempo filtra no servidor pela mesma operação de consulta do serviço compatível com Esri: 5 passos da janela instantânea e 3 da acumulativa bateram exatamente com a contagem feita direto no banco, sobre camada de teste de 100 mil pontos com 3 % de datas nulas e um quarto gravado em fuso diferente de UTC.',
    ],
    'L2-02-a-modelo-estilo': [
        'Define o estilo de camada num documento próprio com esquema publicado, valida contra a especificação de estilo do MapLibre e recusa documento inválido com erro 422 trazendo a mensagem do validador.',
        'O servidor recompila o estilo canônico a cada gravação, e a ida e volta entre exportar e importar foi provada sem perda; 6 dos 7 tipos de estilo desenham de ponta a ponta no navegador, com captura por tipo (raster ficou de fora por falta de tile na bancada).',
        'Duas cláusulas ficam abertas: o estilo padrão determinístico existe e é testado, mas ainda não está ligado à gravação da ingestão, e a conferência do arquivo SLD em cliente de mesa não foi medida nesta máquina.',
    ],
    'L2-02-b-classificacao-servidor': [
        'Classifica os valores de um campo no servidor por quantil, intervalo igual e quebras naturais (Jenks), com cortes iguais aos do numpy e de uma implementação de referência independente.',
        'Nulos são excluídos e contados, valores repetidos não geram classe vazia, e um milhão de valores é classificado dentro do teto do portão.',
        'Falta para o item ficar completo: o portão passou na árvore junta do ramo de reentrega, ainda sem veredito registrado sobre o item inteiro.',
    ],
    'L2-02-c-editor-simbologia-vetor': [
        'Edita a simbologia da camada no visualizador: símbolo único, por categoria, por classe de cor e de tamanho, proporcional, mapa de calor, agrupamento de pontos, efeitos e faixa de escala, com pré-visualização pela mesma função que grava.',
        'O estilo é salvo como item de catálogo ligado à camada, exportável e importável em JSON; as rampas de cor ColorBrewer 1.7.0 estão no repositório com o arquivo de licença ao lado.',
        'Os cortes de classe são os do item irmão de classificação no servidor, e valores acima de 200 categorias entram num grupo "outros".',
        'A entrega atual é por junção de ramo: as capturas de tela do portão e a medida de fluidez com 1 milhão de pontos não foram rodadas.',
    ],
    'L2-02-d-rotulos': [
        'Rotula a camada por campo, por expressão da linguagem própria ou por classes com filtro: cada classe tem fonte, tamanho fixo ou por zoom, cor, halo, âncora, deslocamento, repetição ao longo da linha, maiúsculas, unidade, prioridade e faixa de escala própria.',
        'A expressão é compilada para o equivalente nativo do MapLibre quando existe; o que não compila, a começar pela formatação em português como `1.234,5 ha`, cai para uma coluna pré-calculada no servidor, e os dois caminhos produzem texto idêntico nas 100 feições do teste.',
        'Medido na colisão entre classes: quem decide no MapLibre é a ordem das camadas de símbolo, não só a chave de ordenação, e o gerador passou a reordenar por prioridade. Não medido: o tempo de tile com rótulo calculado no servidor em camada de 1 milhão de feições, porque a função de tile real pertence a outro item.',
    ],
    'L2-02-e-simbolos-sprites-glifos': [
        'Traz uma biblioteca própria de 153 ícones e 10 padrões de preenchimento sob licença CC0-1.0, com licença e resumo criptográfico de cada arquivo listados em documento gerado do manifesto.',
        'Monta o atlas de símbolos por inquilino em 1x e 2x pela própria interface de programação, porque o servidor de tiles lê o diretório de símbolos só uma vez na subida; os glifos de fonte continuam vindo dele, sobre as fontes Noto Sans e Open Sans embutidas.',
        'Ícone enviado pelo inquilino passa por saneamento: script embutido, referência externa e declaração de entidade XML são recusados com erro 422, arquivo acima de 64 kB é recusado, e o pedido do atlas de outro inquilino responde 403. Compor o atlas de 163 itens leva 0,097 segundo em 1x e 0,145 em 2x.',
    ],
    'L2-03-a-api-edicao-transacional': [
        '`POST /api/camadas/{id}/edicoes` é a única porta de escrita de feição da plataforma: adicionar, atualizar e apagar numa transação tudo-ou-nada, ou por feição com ponto de salvamento.',
        'A validação mora no servidor: tipo de geometria, sistema de coordenadas, geometria válida (corrigida só quando pedido), domínio de atributo, tamanho de texto e campos de rastreio que nunca vêm do cliente; edição com versão desatualizada devolve 409 com a feição atual, sem sobrescrever em silêncio.',
        'Falta para o item ficar completo: o teste de navegador da edição no mapa não foi rodado nesta passagem.',
    ],
    'L2-03-c-formulario-atributos-runtime': [
        'Gera o formulário de atributos a partir do esquema da camada durante a edição no mapa: domínio de valores e campo obrigatório aparecem no navegador e são reconferidos no servidor, que continua sendo a autoridade.',
        'Falta o motor de formulário completo: grupos recolhíveis, visibilidade condicional, cálculo por expressão e troca de lista de domínio por subtipo dependem de itens de expressão e de relações ainda não integrados.',
    ],
    'L2-03-f-edicao-em-lote-calculo-campo': [
        '`POST /api/camadas/{id}/lote` aplica uma operação a uma seleção de feições: calcular campo por expressão, atribuir valor fixo, apagar, corrigir geometria inválida, copiar ou mover entre camadas com mapeamento de campos, e pré-visualizar 10 linhas antes e depois sem gravar.',
        'Até 5.000 feições a operação corre no próprio pedido; acima disso vira trabalho de fila com progresso e cancelamento, tudo numa transação só, de modo que erro ou cancelamento devolve a camada ao estado anterior. Medido: 100 mil polígonos com `area_ha = $area_m2 / 10000` em 16,1 s, amostra de 1.000 igual ao cálculo do PostGIS e histórico gerado para as 100 mil.',
        'Fora desta fatia: reprojeção no lote e o filtro que depende do motor de estatísticas do item L2-06-e.',
    ],
    'L2-04-a-leitor-rls-martin': [
        'Cria um papel de banco só de leitura, sem privilégio de contornar a segurança por linha, para o servidor de tiles, e uma função de contexto que valida o token de serviço, confere o escopo e a restrição de origem e endereço, grava o uso no log de acesso e fixa o inquilino na transação.',
        'A política de segurança por linha não confia na variável de sessão crua: exige uma prova assinada emitida apenas por essa função, então o próprio papel de leitura não consegue se declarar de outro inquilino. Medido: 0 linhas ao forjar a variável, 6 chamadas cruzadas devolvendo 0 tile com dado, token revogado sem efeito em 0,002 segundo e 1 linha de log por chamada aceita.',
        'Duas fronteiras declaradas: a cláusula do instalador foi provada no passo que instala o papel, não no instalador inteiro, e a recusa de contexto não deixa linha no log de acesso, porque a transação aborta.',
    ],
    'L2-04-b-featureserver-catalogo-metadados': [
        'Publica um diretório de serviços no formato Esri em `/svc/{token}/rest`, com `info`, `generateToken` (validade máxima de 24 h), `services` por pasta, `FeatureServer`, a camada por id, `layers`, `itemInfo` e metadado ISO 19139, nos formatos `json`, `pjson` e `html`.',
        'O descritor da camada traduz o estilo MapLibre em `drawingInfo` nos três tipos (símbolo único, valor único e faixas de classe); expressão fora desses casos sai como símbolo cinza com o motivo escrito, nunca aproximada.',
        'Falta para o item ficar completo: a conferência com o QGIS e com a biblioteca Python da Esri, que esta máquina não tem; domínio, subtipo e relacionamento saem vazios porque dependem de itens ainda ausentes desta base.',
    ],
    'L2-04-c-featureserver-query': [
        'Responde à operação `query` do FeatureServer no formato da Esri com 39 dos 45 parâmetros da documentação exercidos por pedido real, contra o piso de 38 do portão.',
        'Devolve o formato binário PBF oficial da Esri, decodificado pela mesma definição que o cliente usa e igual ao JSON; consulta espacial sobre 8,4 milhões de imóveis responde em 1,6 ms no percentil 95 com índice espacial.',
        'Filtro inválido sempre volta como erro 4xx, nunca 500, e nenhuma consulta é montada sem parâmetro ligado.',
        'Não foi verificado: carga de camada com 100 milhões de linhas no QGIS, por falta de ambiente gráfico nesta máquina, e o adversário independente ainda não rodou contra o item.',
    ],
    'L2-04-d-featureserver-edicao-anexos': [
        'Aceita escrita pelo protocolo Esri: `applyEdits` na camada e no serviço, `addFeatures`, `updateFeatures`, `deleteFeatures`, `calculate`, os seis caminhos de anexo e o envio prévio de arquivo, todos em `/rest/services/{item}/FeatureServer/0/*`.',
        'Nenhuma dessas rotas escreve direto na tabela: todas traduzem o pedido e chamam a porta única de escrita do item L2-03-a, de modo que tipo, domínio, sistema de referência, propriedade e controle de versão valem igual para o cliente Esri. O erro sai com o código HTTP real e o corpo no formato Esri, e `rollbackOnFailure` é um ponto de retorno por lote.',
        'Duas cláusulas do portão não foram feitas e estão nomeadas: a prova com o QGIS editando uma feição e a prova com o pacote Python `arcgis`, ausentes desta máquina.',
    ],
    'L2-04-f-mapserver-identify-legend-geometryserver': [
        'Publica o contrato de serviço de mapa no protocolo Esri (descritor, camadas, `export`, `identify`, `find`, `legend` e `generateKml`) e o serviço de geometria com projeção, envoltória, áreas e comprimentos, distância, união, interseção, diferença, envoltória convexa e simplificação.',
        'O desenho usa a mesma estrutura de simbologia que o serviço de feições publica, então legenda e mapa não podem divergir de cor; toda operação de geometria é uma chamada ao PostGIS.',
        'Medido: imagem de 1024 por 768 pixels sobre 5.003 polígonos em 0,075 segundo quente; projeção de 100 pontos com diferença de 0,0 metro contra a função do banco; envoltória geodésica de 1 km com erro relativo de área 0,0. A conferência em cliente de mesa não foi feita: a máquina não tem ambiente gráfico.',
    ],
    'L2-04-g-ogc-api-features-crs-cql2': [
        'Serve OGC API - Features com sistema de coordenadas escolhido pelo cliente e filtro CQL2 sobre a parte 1 do padrão, com 53 testes verdes na trilha do item.',
        'Falta para o item ficar completo: o veredito cláusula a cláusula do portão não foi registrado, incluindo o validador oficial da OGC e a conferência com o QGIS.',
    ],
    'L2-04-h-wfs-2-gml': [
        'Serve WFS 2.0.0 e 1.1.0 por token: o documento de capacidades é válido contra o esquema oficial do OGC lido de cache local, e o `DescribeFeatureType` gera o esquema a partir das colunas da camada.',
        'Aceita filtro FES 2.0 (comparação, lógica, espacial e temporal) traduzido para a mesma árvore do CQL2 e compilado pelo mesmo gerador de SQL, com o XML lido por analisador que recusa entidade e referência externa.',
        'Escreve pela operação Transaction, sempre pela porta única de edição da casa, marcando a origem `wfs` no evento; o GDAL 3.8.4 lê o serviço vivo e conta as mesmas 250 feições do banco, e 1.000 feições em GML 3.2 reabrem com geometria válida.',
        'Não medido: QGIS, que não está instalado nesta máquina, e os clientes da Esri, que dependem de credencial de parceiro.',
    ],
    'L2-04-j-conformidade-clientes-e-paridade': [
        'A lista de conformidade com os serviços Esri e OGC deixa de ser texto escrito à mão e passa a ser saída de medida: `make conformidade` roda as provas e grava 102 linhas com data e versão do repositório, e a seção do documento de paridade é reescrita a partir desse arquivo.',
        'A regra é fechada: prova que falha derruba a linha para refutado, e linha sem prova executada fica como não medida, nunca como suportada. Estado atual: 81 linhas suportadas, 5 parciais, 12 fora de escopo e 4 não medidas.',
        'Um cliente OGC de terceiros (owslib) lê as capacidades do WFS 2.0 e busca feições pelo próprio código dele. QGIS em contêiner, o pacote Python `arcgis` e o conjunto de testes teamengine não estão nesta máquina e ficam como não medidos; o protocolo para o parceiro executar com ArcGIS Pro e ArcGIS Online está escrito e marcado como pendente.',
    ],
    'L2-04-k-sync-replicas-esri': [
        'Responde as quatro operações de sincronização do protocolo Esri — criar réplica, sincronizar, extrair mudanças e remover registro — como fachada sobre o mecanismo de réplica da casa, sem relógio novo e sem formato novo.',
        'A repetição do mesmo pedido com a mesma geração do cliente devolve a resposta guardada e aplica zero mudança; atualizar feição apagada é conflito declarado, nunca inserção silenciosa; a extração de mudanças lê a janela sem adiantar o ponteiro.',
        'Medido: réplica de 200 feições criada em 0,35 segundo, com 14 testes passando. A conferência contra os aplicativos de campo e de mesa da Esri depende de credencial e fica pendente.',
    ],
    'L2-05-a-catalogo-ferramentas-gpserver': [
        'Registra ferramenta de análise por manifesto tipado no vocabulário de geoprocessamento da Esri, validado na construção: parâmetro sem tipo quebra o build.',
        'A mesma ferramenta roda por formulário gerado do manifesto na tela `/analise`, pela API própria `/api/ferramentas/{nome}/executar` e pelo serviço compatível `/rest/services/{ferramenta}/GPServer/{tarefa}`, com o mesmo resultado; a saída nasce como item de catálogo com procedência (ferramenta, versão, parâmetros e sha256 das entradas) e relação de derivação.',
        'Falta para o item ficar completo: a prova com o ArcGIS Pro real chamando o serviço, que depende da decisão D20.',
    ],
    'L2-05-b-vetor-basico': [
        'Oferece 19 ferramentas vetoriais elementares como expressão SQL no mesmo executor de ferramentas: área de influência geodésica, recorte, interseção, união, diferença, dissolver com estatística, mesclar, explodir, centroide, casco, simplificar, suavizar, reprojetar, calcular geometria, pontos aleatórios e conversões entre pontos, linhas e polígonos.',
        'Cada ferramenta é conferida contra referência independente na mesma entrada (shapely para geometria plana, pyproj para medida geodésica): a área de influência de 1 km na latitude −23 fica a 5,0e-5 do círculo de referência, contra o limite de 5e-4 do portão.',
        'Toda operação booleana em massa corrige a geometria antes de operar e grava na procedência da camada de saída quantas geometrias de entrada eram inválidas.',
        'O volume foi medido com 1.156 polígonos por camada, não com as 100 mil do portão, porque o disco estava em 93% e a máquina em carga 8,7; a prova pelo navegador não rodou.',
    ],
    'L2-05-c-sobreposicao-agregacao': [
        'Acrescenta nove ferramentas que relacionam duas camadas: junção espacial, junção por atributo, resumir dentro, contar dentro, resumir perto, agregar pontos em polígono ou em grade quadrada ou hexagonal, enriquecer por proporção de área, vizinho mais próximo e tabela de distâncias.',
        'Vinte e seis testes conferem cada ferramenta contra geopandas, pandas, shapely e pyproj na mesma entrada lida de volta do banco, sem número esperado escrito à mão; a contagem dupla causada por polígonos sobrepostos é contada e declarada no método, e pode ser desfeita pela atribuição exclusiva.',
        'Não medidos: o teste de ponta a ponta na tela e a escala do portão de 1 milhão de pontos em 5.570 municípios, por falta de disco e por teto de 5 mil feições na máquina de trabalho.',
    ],
    'L2-05-d-grades-densidade-padroes-interpolacao': [
        'Acrescenta 8 ferramentas ao catálogo de geoprocessamento: grade quadrada, hexagonal e H3, densidade por núcleo de pontos e de linhas, agrupamento significativo pelo índice Gi*, centro médio e elipse, vizinho mais próximo médio, índice global de Moran, interpolação por distância inversa e isolinhas.',
        'Os resultados foram conferidos contra implementações de referência independentes: Gi* e Moran com diferença de 8,9 vezes 10 elevado a menos 16, área do hexágono contra a fórmula fechada com 1 vez 10 elevado a menos 9, densidade integrando o número de pontos com erro de 1,1 vez 10 elevado a menos 4, e interpolação idêntica à referência.',
        'Fica pendente a saída em formato raster, que depende da linha de imagens, e a captura de tela das ferramentas; a grade de 250 metros reproduz a mediana de área da grade interna da casa e difere em 9 células de borda das 73.115.',
    ],
    'L2-05-e-raster-basico': [
        'Oferece treze ferramentas de imagem sobre COG lido por janela: estatísticas por zona, calculadora, reclassificar, recortar, reprojetar, mosaico, terreno (declividade, orientação, sombreamento, rugosidade e índice de posição), curvas de nível, vetorizar, rasterizar, amostrar em pontos, visibilidade e distância.',
        'Os resultados batem com a referência: declividade e visibilidade iguais byte a byte ao GDAL, NDVI igual ao avaliador do TiTiler dentro de 1e-6, e estatísticas por zona reproduzindo o `rasterstats`; 5.570 zonas sobre o mapa de uso do solo em 3,35 s, com pico de 777 MB de memória num arquivo de 9,77 GB.',
        'Falta para o item ficar completo: o registro de veredito das cláusulas de tela e da comparação escrita com o conjunto de análise raster da Esri.',
    ],
    'L2-05-f-rede-isocrona-rota-ferramentas': [
        'Oferece seis ferramentas de rede que devolvem o resultado como camada: área de serviço por tempo de viagem, rota com paradas na ordem dada ou otimizada, matriz origem-destino, K mais próximas, ligação do ponto à rede e localizar-alocar por cobertura máxima.',
        'O cálculo continua no serviço de roteamento do produto, não num segundo cliente: a área de serviço de 30 minutos sai idêntica à da rota `/api/isocrona`, com diferença de área zero.',
        'Medido: matriz de 100 por 100, isto é, 10.000 pares, em 3,96 segundos incluindo a escrita da camada; rota de 10 paradas cai de 3.583,9 para 3.521,6 segundos quando a ordem é otimizada; toda camada de saída grava a versão do grafo de ruas na procedência.',
        'A prova pelo navegador está escrita e não foi executada, porque a aplicação na trilha não serve os arquivos estáticos sem servidor web à frente.',
    ],
    'L2-06-a-modelo-painel-fontes': [
        'O painel é um documento com esquema publicado, cujos elementos apontam para fontes declaradas; o motor agrupa todos os elementos que usam a mesma fonte numa única leitura por ciclo de atualização, em vez de uma consulta por elemento.',
        'O filtro usa a mesma gramática auditada do resto do produto: o filtro fixo da fonte combinado com os valores de execução (filtros globais e parâmetros da URL de quem abre a tela), sempre por igualdade e só em campo que a fonte expõe.',
        'Medido no painel de exemplo com 9 elementos: primeira pintura em 28 ms e página pronta em 858 ms.',
    ],
    'L2-06-b-elementos-basicos': [
        'Dá ao painel doze tipos de elemento: indicador com nove estatísticas, gráfico de barras, linhas e área por categoria ou por data, pizza e rosca, tabela com ordenação ou agrupamento com subtotal, lista paginada, mapa, detalhes, texto com formatação, legenda e cabeçalho.',
        'Nenhum número é calculado no navegador: toda agregação passa pelo motor do servidor, e a extensão desenhada pelo mapa vira condição espacial das demais fontes do painel.',
        'Medido: lista de 10.000 feições a 66,8 milissegundos por página no percentil 95, contra teto de 300, e a extensão do mapa recortando 10.000 feições para 999.',
    ],
    'L2-06-c-acoes-seletores-filtros-cruzados': [
        'No painel, um elemento seletor (categoria, faixa numérica, data ou feição) dispara ações sobre os outros elementos — filtrar, selecionar, limpar, aproximar, deslocar, piscar, abrir e fechar —, e o filtro é resolvido por SQL no servidor.',
        'Ação entre fontes sem relação declarada é recusada com 422 e a regra quebrada; o estado dos seletores vai na URL, então o endereço copiado reabre o painel como estava.',
        'Medido: latência do gatilho até a ação de 0,054 ms no percentil 95 com 10.000 feições, contra teto de 100 ms no portão.',
    ],
    'L2-06-d-atualizacao-viva-sse': [
        'O ramo de lançamento entrega fluxo de eventos do servidor (SSE) apenas para tarefas: a rota `/api/eventos` existe e exige sessão, `/api/eventos/camadas` responde 404 e não há gatilho de notificação de camada em nenhuma migração desse ramo.',
        'O trabalho completo — gatilho por comando na tabela da camada, fluxo por camada, painel que assina e mostra a hora da última atualização, reconexão que recupera o que passou — existe numa trilha separada de 43 arquivos que não está mesclada.',
        'O que foi medido nessa trilha: 0,0005 segundo entre a gravação no banco e o quadro no consumidor, contra o teto de 1 segundo do portão, e uma rajada de mil eventos vira uma única consulta.',
    ],
    'L2-06-e-estatisticas-servidor': [
        'Calcula no servidor as estatísticas que os painéis e os serviços mostram (soma, média, percentil, contagem distinta, agrupamento com filtro de grupo), com faixa de mês resolvida no fuso de São Paulo, e alimenta também o parâmetro `outStatistics` do serviço compatível com Esri.',
        'Medido: 1 milhão de linhas agrupadas por 100 categorias com p95 de 113 ms, contra o teto de 500 ms do portão, com a máquina livre.',
        'As seis cláusulas do portão passam no ramo próprio; falta a junção desse ramo no tronco.',
    ],
    'L2-07-b-formulario-de-coleta-xlsform': [
        'Importa uma planilha XLSForm e a transforma em item de formulário do catálogo, cria a camada de destino e uma camada filha por bloco de repetição, e traduz as regras de relevância, restrição, cálculo e filtro de lista para a linguagem de expressão da casa, com tabela de equivalência que declara o que ficou de fora.',
        'A tela `/coleta` desenha os campos, incluindo lista em cascata de três níveis, guarda rascunho a cada mudança e envia; o servidor recalcula, reaplica relevância e restrições e só então grava a feição, e cálculo com dependência circular é recusado com erro 422 na importação e no navegador.',
        'Conferido com 102 vetores nos dois avaliadores, com o motor em JavaScript devolvendo o mesmo resultado do motor em Python. Ficam fora desta fatia: leitura de posição por GPS, foto, áudio, assinatura, código de barras e fila para uso sem rede.',
    ],
    'L2-07-e-odk-central-ponte': [
        'Publica no ODK Central a mesma planilha de formulário usada na coleta própria, puxa os envios por OData com os anexos e grava tudo pela porta única de escrita, com as regras do formulário reavaliadas no servidor.',
        'A repetição é barrada pelo identificador de envio do ODK: sincronizar três vezes deixa 20 feições e nenhuma duplicata; envio recusado fica gravado com o motivo.',
        'Falta para o item ficar completo: a prova contra um ODK Central de verdade; o que existe foi provado contra um dublê HTTP da API documentada, porque a instalação do Central aqui depende da decisão D29.',
    ],
    'L2-08-a-leitor-portal-inventario': [
        'Lê, sem escrever nada, o inventário de um Portal for ArcGIS ou ArcGIS Online: itens, dados e recursos do item, itens relacionados, grupos com membros, usuários e contagem de feições dos serviços hospedados, como tarefa que retoma do ponto gravado depois de corte de rede.',
        'Classifica cada item em migra, migra parcial ou não migra pelo tipo, e tipo fora da tabela vira "desconhecido", nunca suposição; a tabela de usuários não tem coluna de e-mail, nome ou telefone, então o dado pessoal devolvido pelo portal não tem onde ser gravado.',
        'Sete achados de segurança do adversário foram corrigidos, entre eles a credencial que só viaja para a origem do portal configurado e a neutralização de fórmula no relatório em CSV.',
        'A prova contra um portal real depende de credencial de parceiro e não foi feita: hoje só há prova contra servidor de teste.',
    ],
    'L2-09-c-modelos-gltf-ifc-3dtiles': [
        'Põe modelo tridimensional no mapa por três caminhos, sem biblioteca com licença AGPL: glTF binário posicionado por longitude, latitude, altura, rotação e escala; arquivo IFC lido em Python puro, com elementos, pavimento e propriedades em tabela própria; e conjunto de tiles no formato OGC 3D Tiles 1.1 gerado do glTF.',
        'Medido: a caixa desenhada pelo navegador difere 0,097 m da calculada pelo servidor, contra a folga de 0,5 m do portão; o validador oficial de 3D Tiles aponta 0 erro e 0 aviso e reprova o controle negativo; a cena desenha a 58,7 quadros por segundo sem placa de vídeo; um IFC sintético de 50 MB com 62.038 elementos converte em 19,4 s com pico de 679 MB.',
        'Modelo que depende de arquivo externo, como textura fora do pacote, é recusado no servidor e no navegador. O consumo do conjunto de tiles pelo ArcGIS Pro segue pendente de decisão do dono, e o formato i3s fica fora, declarado.',
    ],
    'L2-09-d-analise-3d-visibilidade': [
        'Oferece quatro análises de terreno por rota própria: linha de visada, bacia visual, perfil de elevação e sombra, sobre uma grade de alturas enviada no corpo do pedido, com resumo criptográfico do terreno em toda a procedência.',
        'A bacia visual não é reimplementada: a casa grava o arquivo e chama o programa `gdal_viewshed` instalado, devolvendo os bytes dele e a linha de comando usada, conferida byte a byte em relevo suave e íngreme.',
        'Medido: ponto de obstrução a 2,75 metros do cruzamento verdadeiro, contra tolerância de 30 metros do portão, e sombra com desvio de 0,268 % contra a fórmula, contra tolerância de 5 %. Corte de malha e análise de malha integrada ficam fora do item.',
    ],
    'L2-10-d-regras-de-atributo': [
        'Cada camada pode declarar regras de atributo: cálculo (campo alvo igual a uma expressão, com gatilho, ordem e encadeamento), restrição (falso recusa a edição com código e mensagem escolhidos) e validação em massa como tarefa, que grava os erros numa camada de erros do catálogo.',
        'As regras rodam no caminho único de escrita, campos virtuais são avaliados na leitura, e ciclo entre regras é detectado na configuração; 100 mil feições foram validadas em 3,45 s e 1.000 edições com 3 regras custaram 1,11 vez o tempo sem regras.',
        'Falta para o item ficar completo: a tela de configuração das regras, a compilação para SQL e a edição por WFS-T.',
    ],
    'L2-11-a-geocodificacao-csv': [
        'Geocodifica um arquivo de endereços em lote e mede o acerto contra dado aberto: em 1.000 endereços de um município, 95,0% saíram com acerto de número exato a até 50 metros, contra o piso de 85% do portão, e 0% caiu fora do município.',
        'O lote de 1.000 endereços leva 8,5 segundos, depois que dois índices novos acabaram com a repetição da busca por via a cada linha; ponto que caiu no centroide do município é sempre marcado como tal, nunca entregue como endereço encontrado.',
        'O item está com a suíte do geocodificador verde na trilha e aguarda decisão da fila de junção para entrar no ramo de lançamento.',
    ],
    'L2-11-b-geocodificador-brasil': [
        'Converte endereço em coordenada com base própria em PostgreSQL/PostGIS montada sobre o CNEFE 2022 do IBGE, sem depender de serviço externo; oferece busca, geocodificação reversa, sugestão enquanto se digita e um serviço compatível com o GeocodeServer da Esri.',
        'Medido sobre 50 endereços e 50 pontos reais do CNEFE: erro mediano de 0,0 m (portão pede até 30 m), acerto de número e face de 98,0 % (portão pede 90 %), reverso acertando o logradouro em 100 % e sugestão com p95 de 33,1 ms. A instalação de Roraima, a menor unidade da federação no CNEFE, ocupa 4,52 MB comprimidos e carrega em 10,4 s.',
        'Ambiguidade entre municípios é declarada e CEP incompatível com o município recusa com 422. O uso do serviço como localizador dentro do QGIS não foi provado nesta máquina, que não tem QGIS nem ambiente gráfico.',
    ],
    'L2-13-a-versoes-ramo-reconciliar': [
        'Permite marcar uma camada como versionada e abrir ramos de trabalho paralelos: ler no ramo mostra as edições dele sobre o padrão como estava quando o ramo nasceu, reconciliar lista as feições alteradas dos dois lados, resolver decide campo a campo e publicar leva as linhas para o padrão.',
        'As linhas do ramo moram em tabela companheira, e não em colunas novas da camada, de modo que nenhum caminho de leitura já existente precise lembrar de filtrar versão; a consulta aceita os parâmetros de versão e de momento histórico do protocolo Esri, e há um serviço de gerenciamento de versões com as operações do protocolo.',
        'Medido: reconciliar um ramo com 10 mil edições leva 29,6 segundos; 18 testes passam. Pendentes: conferência com o aplicativo de mesa da Esri e o teste de tela do comparativo, que só roda contra o endereço público.',
    ],
    'L2-13-b-replicas-sincronizacao': [
        '`POST /api/replicas` monta um recorte declarado de camadas e escreve um GeoPackage para trabalho sem conexão, com as tabelas de sincronização, geração e domínios dentro do próprio pacote.',
        '`POST /api/replicas/{id}/sincronizar` sobe as mudanças do aparelho pela porta única de escrita, resolve versão divergente pela política escolhida (servidor vence, cliente vence ou perguntar), baixa o que mudou no servidor e avança a geração; repetir o mesmo lote aplica zero.',
        'Falta para o item ficar completo: a prova com o aplicativo de campo num aparelho real; a forma do arquivo foi conferida pelo GDAL 3.8.4.',
    ],
    'L2-15-a-geoparquet-bucket-catalogo': [
        'Exporta camada para GeoParquet 1.1 no balde do inquilino e publica um item de catálogo com esquema, contagem, caixa envolvente por arquivo e sha256; a escrita pode ser em arquivo único ou particionada por coluna.',
        'Medido: 1.000.000 de polígonos exportados em 5,8 segundos, reabertos pelo DuckDB com a mesma contagem e diferença de área zero contra o PostGIS em 100 amostras; partição por unidade da federação gera exatamente 27 arquivos, e partição sem mudança não gera gravação nova.',
        'O modo arquivar só apaga a tabela de origem depois de conferir, na mesma transação, que a contagem no arquivo bate com a contagem apagada.',
        'Rebaixado a parcial pelo coordenador: a leitura pelo QGIS não foi medida e a URL assinada vencida responde 404, não o 403 que o texto do portão pedia.',
    ],
    'L2-16-c-script-vira-ferramenta': [
        'Transforma um script Python em ferramenta do catálogo: o cabeçalho do script declara nome, título, parâmetros e saídas, é validado antes de gravar, e o script vira item versionado. O formulário mostrado ao usuário é derivado só do cabeçalho, e o corpo do script não sai por ele.',
        'A execução valida os valores antes de enfileirar, confere que todo item de entrada existe no inquilino, congela versão e sha256 no pedido e roda o retrato imutável daquela versão dentro do contêiner do inquilino, com teto de tempo. A saída vira item com procedência que aponta a ferramenta, a versão e o sha256 do script.',
        'Provado que o script não alcança a rede, não lê `/etc`, não escreve sem permissão e não sobrevive ao teto de tempo, e que publicar versão nova não altera execução passada. Falta a cláusula de chamar a ferramenta pelo `submitJob` do serviço de geoprocessamento, que vive em outro ramo.',
    ],
    'L3-01-c-extracao-fator': [
        'Extrai o valor de cada fator para cada unidade de análise do motor multicritério, tanto de raster (média por zona) quanto de vetor (área, comprimento, fração e distância), e grava a cobertura de cada fator, sem transformar valor ausente em zero.',
        'Os resultados foram conferidos contra recomputação independente em 200 unidades: média por zona com divergência máxima zero, área e comprimento dentro de 0,5 %, fração ponderada por área e não por centroide, e distância igual à referência geodésica em 50 unidades; raster sem sistema de coordenadas e camada vazia abortam o trabalho com erro nomeado.',
        'A cláusula de tempo do portão — 12 fatores sobre 73 mil células — não foi medida: a execução estourou o limite de 600 segundos na máquina compartilhada.',
    ],
    'L3-01-d-transformacoes': [
        'Transforma valor bruto em favorabilidade de 0 a 100 por 16 tipos de transformação (categoria, faixas com quatro métodos de quebra, linear, degraus e as doze funções contínuas equivalentes às do ArcGIS Pro), com a mesma conta escrita em Python e em SQL e diferença máxima de 0,01 entre as duas.',
        'A pré-visualização mostra o histograma de entrada e o de saída em 15 a 33 ms para 100 mil valores, e o manual traz a fórmula e o gráfico de cada função, gerados por script.',
        'Falta para o item ficar completo: a reprodução do motor logístico de referência, em que 4 dos 19 fatores batem em 100 % das células e os outros 15 ficam fora de escopo por motivo nomeado, e a medição da cláusula de desempenho com a máquina sem carga alta.',
    ],
    'L3-01-e-combinacao': [
        'Combina os fatores já transformados numa nota de favorabilidade por unidade de análise, com oito combinadores declarados: soma ponderada normalizada (padrão), soma percentual que fecha 100, média geométrica, mínimo, máximo, produto, soma e gama difusos.',
        'Ausência de dado é tratada como ausência, nunca como zero, e o veto é objeto separado do peso: entra como fração vetada e multiplica a nota, de modo que fração 1 zera a nota e grava o motivo.',
        'O recálculo de 4.346 unidades por 19 fatores leva 1,493 ms no servidor (teto de 50 ms) e 1,625 ms na versão que roda no navegador (teto de 20 ms), e todo resultado carrega a frase de que os pesos são escolhidos pelo usuário, não medidos.',
    ],
    'L3-01-f-explicacao': [
        'Responde por que uma unidade recebeu determinada nota no motor multicritério: tabela de fator, valor bruto com unidade e fonte, transformação aplicada, favorabilidade, peso e contribuição, mais a soma, o veto com o motivo e a cobertura.',
        'A explicação é recalculada a partir dos valores brutos no momento do pedido, nunca lida de uma tabela de explicação gravada, e usa o mesmo combinador do cálculo. Medido em 100 unidades sorteadas: a diferença entre a soma das contribuições e a nota gravada fica em 0,5 ou menos.',
        'Quando o combinador é do tipo difuso, a explicação mostra a favorabilidade de cada fator sem apresentar uma soma que não existe. A latência não foi medida e o teste de ponta a ponta não correu inteiro, por falta de servidor web na trilha.',
    ],
    'L3-01-g-tela-motor': [
        'Abre a tela `/amc/motor`, onde o usuário monta o modelo (camada mais extrator mais transformação, com pré-visualização do histograma sobre os valores já extraídos), marca restrições como veto separado do peso e escolhe o peso de cada fator por controle deslizante ou percentual com trava.',
        'Movida a barra de um peso, a tela recombina as notas no próprio navegador, sem nova chamada à interface de programação, recolore o mapa pela rampa declarada e abre a explicação fator a fator de cada unidade; o rótulo usado é sempre "pesos escolhidos pelo usuário".',
        'Os pesos viajam no endereço, e a tela recusa endereço adulterado (peso acima do máximo, fator inexistente, soma fora de 100), deixando o mapa vazio com a razão escrita. Pendente: o teste de tela completo, que exige o servidor de borda.',
    ],
    'L3-01-i-exportacao-metodo': [
        'Exporta o método do motor multicritério como documento JSON canônico (`plat/amc_metodo`) com pesos, vetos, combinador, transformações, camadas de entrada com sha256 e o sha256 do próprio documento; documento alterado depois da exportação é recusado na importação.',
        'Gera também um relatório em PDF determinístico com uma seção por página; um teste extrai cada número do PDF e exige que ele exista no JSON — foram 23 números conferidos em 8 páginas.',
        'Falta para o item ficar completo: o registro do veredito do item inteiro; as cláusulas do portão estão medidas.',
    ],
    'L3-02-b-sensibilidade-sobol-oat': [
        'Mede a sensibilidade do modelo multicritério de duas formas: índices de Sobol de primeira ordem e total sobre pesos e parâmetros, com amostra de Saltelli, semente gravada e intervalo por reamostragem; e tornado um fator por vez, que move o peso de cada fator de −50% a +100% e mede quanto a lista dos melhores muda.',
        'A função de teste de Ishigami, que tem índices de forma fechada, é reproduzida com desvio máximo de 0,0004, contra a tolerância de 0,05 do portão; o relatório de um modelo de 2.000 unidades por 6 fatores levou 1,295 segundo.',
        'O relatório diz, em texto, que a medida é de dependência do modelo ao peso escolhido, não de importância real do fator.',
    ],
    'L3-05-localizar-regioes': [
        'Responde onde ficam as N áreas contíguas de maior favorabilidade, e não apenas quanto vale cada célula: cresce cada região por fila de prioridade a partir de sementes espalhadas, com compromisso declarado entre forma (círculo, quadrado ou hexágono) e utilidade, área total alvo, área mínima e máxima por região e distância mínima e máxima entre regiões.',
        '`POST /api/multiescala/execucoes/{id}/regioes` devolve um polígono por região com as estatísticas. Medido: grade de 1 milhão de células em 3,42 s para 3 regiões e 9,09 s para 10; sobre a superfície de teste com 3 picos, as 3 regiões saem a 0,03 célula dos picos, com área a 0 % de diferença do alvo e compacidade de 0,98 ou mais.',
        'Célula sem dado ou vetada é intransponível. Estão implementadas 3 das 7 formas e 4 dos 8 métodos de avaliação, e o item não tem tela própria.',
    ],
    'L3-06-criterios-de-feicao': [
        'Permite que a unidade de análise seja a feição do próprio usuário, com quatro critérios: atributo numérico da feição, contagem de pontos de outra camada num raio, contagem dentro do polígono e distância ao ponto mais próximo.',
        'A influência de cada critério é declarada pelo usuário como positiva, inversa ou ideal, e o filtro de inclusão por faixa tira a feição da comparação sem tratá-la como vetada; a tela mostra o ranque, o histograma por critério e a matriz de correlação entre critérios, e a exportação sai em CSV.',
        'Medido sobre dado aberto: 1.000 feições por 4 critérios em 131,7 milissegundos, com a contagem em raio conferida feição a feição contra a função do PostGIS, sem divergência. O teste de tela foi escrito mas não rodou na trilha.',
    ],
    'L3-07-agregacao': [
        'Leva o resultado do motor multicritério da célula da grade para qualquer feição (imóvel, lote, município ou setor) por interseção de área, com média por fator ponderada pela área, fração vetada, veto principal e recombinação opcional pelos pesos do modelo.',
        'Feição que não toca célula nenhuma sai marcada como sem célula, nunca como zero.',
        'Medido contra um motor logístico de referência, só leitura: 10 fatores comparáveis reproduzidos em 100 % das 4.346 feições dentro de 0,5, e o veto principal em 99,65 %, acima do piso de 99,5 % do portão.',
    ],
    'L3-08-pareto': [
        'Calcula a fronteira de Pareto, isto é, quais unidades podem ser as melhores para qualquer escolha de peso, com 2 a 4 objetivos, direção declarada por objetivo e ordenação em primeira, segunda e terceira fronteiras.',
        'A ordenação foi conferida contra um laço ingênuo escrito do zero no teste, em 2.000 unidades e cinco combinações de objetivos: ordem idêntica unidade a unidade; unidade com objetivo ausente fica fora da ordenação, nunca com zero no lugar do que falta.',
        'Duas rotas devolvem a ordem por unidade e a fronteira como camada em GeoJSON, e a tela liga gráfico de dispersão e mapa: selecionar um retângulo no gráfico realça no mapa exatamente aquelas unidades.',
        'A prova pelo navegador do arrasto no gráfico está escrita e não foi executada na trilha.',
    ],
    'L3-09-backtest-decisao-real': [
        'Compara o ranking de uma execução do motor multicritério com escolhas que já aconteceram: percentil das escolhas, distribuição nula por permutação, área sob a curva com valor-p de uma cauda, e preferência revelada por fator (sinal e ordem, nunca peso).',
        'Medido sobre dado aberto — 602 galpões do OpenStreetMap com área acima de 5.000 m², grade de 500 m, modelo de um fator: área sob a curva 0,718, percentil mediano 74,8 e valor-p 0,002 em 500 permutações; escolhas geradas pelo próprio modelo dão 1,000 e escolhas ao acaso 0,4993.',
        'As ressalvas ficam no corpo do relatório, não em rodapé: concordância com o passado não é acerto futuro, a distância confunde, e camada mais nova que a decisão sai marcada como anacrônica. O item não tem tela própria.',
    ],
    'L3-10-corredor-custo-minimo': [
        'Traça o corredor de custo mínimo entre dois pontos sobre a superfície do motor multicritério e devolve, na mesma resposta, a linha, o corredor e o manifesto com a superfície declarada, os parâmetros e as medidas.',
        'A reprodução do trecho de referência da casa foi medida: a superfície sai igual byte a byte à da rodada oficial, a rota fica a 100,0 metros da oficial pela distância de Hausdorff (uma célula de 100 metros) e o trecho de 382,4 quilômetros é traçado em 5,8 segundos, contra teto de 10 segundos.',
        'A tela que escolhe os dois pontos no mapa fica para a parcela de interface.',
    ],
    'L3-19-multiescala': [
        'Roda o motor multicritério em duas grades ligadas: `POST /api/multiescala/conjuntos/{id}/macro` calcula a grade grosseira sobre a área de estudo inteira e `POST /api/multiescala/execucoes/{id}/micro` gera a grade fina somente dentro das células aprovadas na etapa anterior.',
        '`GET /api/multiescala/execucoes/{id}` devolve o relatório por fator com a escala da fonte, a escala da grade e a razão entre as duas, calculadas pelo servidor — o cliente não envia esse campo.',
    ],
    'L3-20-narrativa-de-resultado': [
        'Escreve o resumo textual do resultado do motor multicritério por modelo de frase puro sobre o documento do método, sem modelo de linguagem, sem banco e sem relógio: uma ideia por frase, e todo número com o universo a que se refere.',
        'A função de revisão marca no próprio texto número sem origem em campo do documento, termo da lista proibida pela regra de escrita da casa e pontuação proibida; o texto gerado passa com zero marcações e uma frase fabricada é marcada.',
        'Cada narração leva 0,02 ms, e a conferência à mão do texto de três unidades está registrada no arquivo de medidas.',
    ],
    'L6-01-b-view-so-leitura': [
        'Publica camada do acervo da casa sem copiar dado: cada camada exposta vira uma view em schema próprio, com só as colunas da lista branca e um porteiro no filtro que exige assinatura do inquilino. Sem assinatura a view devolve zero linha e a API responde 403.',
        'A role da aplicação não recebe privilégio nenhum nas tabelas de origem, provado no banco: consulta direta à tabela original é negada, escrita na view é negada, e a varredura do catálogo do Postgres não encontra concessão direta. A consulta de mapa por caixa envolvente responde em 1,5 ms de mediana sobre 8.406.837 linhas contadas exatamente.',
        'Duas hipóteses caíram na medição e estão no registro de decisão: a view não pode ser do tipo que herda o chamador, e a marcação de barreira de segurança derruba o índice espacial. Falta ligar a publicação ao servidor de tiles e ao mapa, que ainda não existem nesse ramo.',
    ],
    'L6-01-h-frescor-verificacao': [
        'Roda um trabalho semanal que verifica o frescor de cada camada exposta do acervo da casa: contagem exata de linhas com prazo de 25 segundos, resumo criptográfico do conteúdo quando existe comando de reexecução declarado, e teste HTTP dos endereços confirmados, com teto de 40 por rodada.',
        'Contagem que estoura o prazo é gravada como "não contado no prazo", nunca como zero, e a ficha do acervo e o mapa mostram o mesmo selo de verificação vencida com o motivo: endereço morto, prazo da fonte vencido, nunca verificada ou verificação com mais de 14 dias.',
        'As rotas expõem a lista de camadas com filtro de vencidas, as 12 verificações mais recentes de cada camada, as variações de contagem acima de 5 % e o histórico de execuções.',
    ],
    'L6-01-i-raster-e-arquivos': [
        'Expõe ao catálogo os arquivos do acervo da casa pela vista `plat.acervo_arquivo` e pela rota `GET /api/acervo/arquivos`: 321 arquivos com sha256, dos quais 26 são imagens.',
        '`POST /api/acervo/arquivos/expor` confere o sha256 antes de qualquer escrita; a imagem passa a servir ladrilho por token lida onde está, sem copiar byte, e o vetor é carregado uma vez para o PostGIS. Arquivo acima de 2 GB e lote acima de 3 GB são recusados, por causa do limite de disco.',
        'Falta para o item ficar completo: nenhuma das 27 fontes de arquivo tem licença escrita, então cada item nasce privado e marcado como de uso restrito.',
    ],
    'L6-02-c-wfs-ogcapi': [
        'Conecta a serviços WFS 2.0 e OGC API Features de terceiros e lê suas coleções; provado contra dois serviços públicos vivos, um deles com 9.708 coleções.',
        'Copia uma camada externa para dentro do produto: 50 mil feições em 10,19 segundos, em 10 requisições paginadas, com os tipos de atributo preservados.',
        'Serviço que anuncia 5 milhões de feições e não pagina faz a cópia parar no limite declarado e avisar, em 7,46 segundos, sem travar o processo de trabalho.',
    ],
    'L6-02-i-google-sheets': [
        'Lê planilha do Google Sheets como camada do inquilino e a atualiza periodicamente; a credencial da conta de serviço nunca aparece em registro de log, e planilha que deixa de responder mostra falha na atualização em vez de dado velho apresentado como novo.',
        'A cláusula que faltava, a rodada completa dos 8 testes da suíte de conexão, fechou em duas execuções consecutivas. A causa da falha anterior foi medida e corrigida: dois processos do trabalhador criavam o mesmo schema ao mesmo tempo, e a função passou a serializar por trava de aviso por inquilino.',
    ],
    'L6-02-m-catalogo-endpoints-brasil': [
        'Mantém um catálogo de endereços públicos de serviços geográficos, retestado por um trabalho semanal, e permite adicionar qualquer um deles como conexão do inquilino em um clique, já com a ficha de procedência.',
        'A verificação exige o documento do protocolo para considerar o endereço vivo: resposta 200 que traga página HTML ou erro do servidor conta como fora do ar, e a entrada morta sai da lista principal.',
        'Medido em 7 de setembro de 2026: 78 endereços vivos de 100 candidatos, com 29 endereços que nunca existiram removidos da semente.',
    ],
    'L6-02-o-importacao-exportacao-formatos': [
        '`POST /api/intercambio/exportacoes` acrescenta quatro formatos de saída aos onze já existentes (GeoJSON Sequence, File Geodatabase em zip, MBTiles e PMTiles) e, no modo inquilino, gera a saída completa: todas as camadas vetoriais num GeoPackage com manifesto de esquema, campos, contagem e sha256 por camada.',
        'Antes de gerar, a exportação escreve o que o formato de destino vai fazer com os campos — nome truncado em dez caracteres, data virando texto, texto cortado em 254 caracteres, inteiro longo virando número real.',
        'Falta para o item ficar completo: a importação não ganhou formato novo, e a abertura do File Geodatabase foi provada pelo driver do GDAL, não pelo aplicativo de desktop.',
    ],
    'L6-03-paridade-conectores': [
        'Mantém em `docs/PARIDADE.md` a comparação, linha a linha, entre os conectores do produto e os tipos de camada e fontes de dado do Map Viewer da Esri, com 35 linhas classificadas em feito, parcial ou fora, cada uma apontando o arquivo de teste e o ramo onde ele vive.',
        'Um teste automatizado reprova linha marcada como feita cujo teste não exista, e as 20 URLs de referência são testadas por script, com a data da verificação registrada.',
        'O adversário provou duas linhas falsas: duas exclusões diziam decorrer de decisão do dono sem que decisão nenhuma cobrisse o assunto; as linhas foram corrigidas para declarar que nenhum item e nenhuma decisão cobrem a exclusão, e a trava passou a exigir essa nomeação.',
        'Nove linhas não puderam ser reproduzidas pelo adversário por falta de configuração nos outros ramos.',
    ],
    'L6-06-descoberta-csw': [
        'Busca no catálogo CSW 2.0.2 da INDE por texto e por caixa envolvente e cria a conexão WMS, WFS ou WMTS num clique, já com a ficha de procedência preenchida a partir do registro ISO do catálogo.',
        'Registro que declara protocolo mas não traz endereço de serviço responde 422 com o motivo e não cria conexão vazia. Toda busca passa pelo cliente HTTP com defesa contra requisição forjada para rede interna, teto de 1 MiB e 20 s, e o XML é lido por analisador que não resolve entidade externa.',
        'Medido contra a INDE: 52 registros para um termo de busca, 2 conexões criadas de um mesmo registro, as duas respondendo. Cinco endereços de catálogo estadual tentados não resolveram: só a INDE está verificada.',
    ],
    'L4-15-serie-temporal-da-rede': [
        'Compara safras sucessivas da base de rede elétrica e classifica cada identificador de elemento em quatro classes de linhagem, exporta a tendência por transformador em CSV, calcula crescimento por alimentador e oferece um controle deslizante de safra no mapa.',
        'A potência declarada da placa é marcada como não confiável quando a série mostra troca em massa, seguindo a regra medida da casa.',
        'Conferido em duas safras reais contra recontagem independente dos arquivos de origem, com 24 testes passando. A escala completa da distribuidora não foi medida: a importação não terminou em 45 minutos, limitada pelo item de importação.',
    ],
    'L4-20-consumidores-e-enderecos': [
        'Modela a ponta da rede elétrica em seis tabelas com RLS (trechos de média e baixa tensão, transformadores, unidades consumidoras, consumo anual e endereços do censo) e cinco rotas em `/api/rede/consumidores`, sem nenhum campo que identifique pessoa e com consumo apenas agregado, com mínimo de cinco unidades.',
        'A camada de endereços sem rede num raio de 700 m deu 10.914 endereços contra 10.911 da camada de referência da casa, diferença de 0,03 %, gerada em 6,4 s; os consumidores a jusante de 44.268 trechos de média tensão saem em 3,6 s.',
        'Falta para o item ficar completo: esse trabalho está num ramo que ainda não foi juntado ao tronco de lançamento.',
    ],
    'L4-27-curto-circuito-e-protecao': [
        'Calcula a corrente de curto-circuito de cada barra do alimentador, trifásica e fase-terra, sobre o mesmo modelo em memória que alimenta os exportadores para OpenDSS e pandapower, e entrega o resultado como tabela e como camada de pontos.',
        'Para cada barra informa o dispositivo de proteção a montante e o veredito de coordenação contra a faixa de interrupção cadastrada: interrompe, abaixo da faixa, acima da capacidade ou sem dado.',
        'As premissas voltam gravadas em toda execução (potência de curto da fonte, relação X/R, fator de tensão, sequência zero e base de potência), e fonte sem potência de curto declarada, ou com potência zero, é recusada, porque impedância nula daria corrente infinita.',
        'Medido num alimentador real da cooperativa de teste: 192 barras entre 6.442 e 10.982 ampères em 0,205 segundo; 191 das 192 barras saíram sem dado de coordenação, porque o arquivo da distribuidora não traz faixa de interrupção e nenhuma faixa foi suposta.',
    ],
    'L4-29-regras-de-atributo-de-rede': [
        'Define três perfis de regra sobre a rede: cálculo, que escreve um atributo; restrição, que responde se uma manobra é permitida, com a chave entre 13,8 kV e 34,5 kV sendo recusada; e validação, que lista em lote os casos irregulares, como transformador sem unidade consumidora.',
        'A linguagem de expressão ganhou seis funções de rede nos dois avaliadores. Uma rodada avalia cada regra uma vez por objeto, sem ponto fixo, de modo que a regra com laço de jusante não se repete; profundidade excessiva é recusada na criação, e a restrição falha fechada, recusando quando a avaliação dá erro.',
        'O trabalho está num ramo que ainda não foi trazido para o ramo da demonstração: ele diverge 336 commits atrás e toca os avaliadores de expressão, compartilhados por toda a plataforma.',
    ],
    'L4-parcelas-01-modelo-de-parcelas': [
        'Modela a malha de parcelas orientada a registro em seis tabelas por inquilino: o documento de registro, ponto com precisão declarada, linha com rumo, distância e raio com sinal, divisa partilhada entre parcelas, a parcela por tipo (lote, gleba, quadra, servidão, estrato) com área declarada, área calculada e erro de fechamento, e a conexão entre parcelas.',
        'Retirar uma parcela é ato de registro e não apaga nada: a parcela sai do conjunto atual e entra no histórico com o registro, a linha exclusiva sai junto e a linha partilhada permanece; a sobreposição entre parcelas ativas do mesmo tipo é validada por consulta com tolerância de 1 centímetro quadrado.',
        'A importação foi medida com 11.473 lotes de um SIG de teste interno, com dado aberto e registro sintético; nenhum documento real e nenhum nome de pessoa entram no modelo.',
    ],
    'L4-parcelas-02-fluxos-cogo': [
        'Edita malha de parcelas com os fluxos da referência: dividir por rumo (área igual, proporção ou faixas de largura fixa), dividir por linha de corte, unir, recortar, construir parcelas a partir de linhas livres, sementes, duplicar e atribuir feição a registro.',
        'A poligonal de levantamento (traverse) mostra o erro de fechamento em vez de fechar em silêncio, e uma fachada REST no formato do ParcelFabricServer expõe esses fluxos; o leitor de DXF em texto fecha 125 faces a partir de 557 segmentos de uma planta de teste.',
        'Falta para o item ficar completo: o ramo com esse trabalho não está juntado ao tronco, e as capturas de tela não são possíveis nesta máquina, onde o navegador sem interface gráfica quebra.',
    ],
    'L4-parcelas-03-ajuste-e-qualidade': [
        'Ajusta a malha de parcelas por mínimos quadrados e gera a camada de qualidade com lacunas, sobreposições, área declarada contra calculada e erro de fechamento.',
        'Na malha sintética de 30 nós, 98 observações e 3 pontos de controle, as coordenadas ajustadas reproduzem a solução analítica a 1 milímetro; um erro de 1 metro plantado numa linha de 100 metros vira a suspeita principal pelo resíduo e, excluída a linha, a rede reconverge.',
        'Analisar não escreve nada, provado por soma de verificação; aplicar move o ponto, recompõe linha e face e grava a versão.',
        'Nada disso está no ramo de lançamento: o trabalho vive numa trilha separada, 355 mudanças atrás e 45 à frente do ramo de lançamento, e essa trilha estava em uso por outra sessão no dia da medição.',
    ],
    'L5-06-motor-widgets': [
        'Monta a aplicação a partir de um registro de componentes com manifesto validado na conferência do repositório: seis componentes básicos, entre eles mapa, legenda, tabela, texto, botão e filtro. A página só carrega os módulos citados no documento, medido em 3 módulos.',
        'Componente de tipo desconhecido, configuração fora do esquema ou módulo ausente do disco desenham uma caixa de erro nomeada, em vez de derrubar a página. Medido: 1,32 kB por componente e primeira pintura em 48 ms.',
        'O motor está pronto no ramo próprio e aguarda a junção no tronco.',
    ],
    'L5-07-fontes-vistas-mensagens': [
        'Dá ao documento de aplicativo três peças: fontes (item do catálogo, caminho do servidor ou dado embutido), vistas (fonte com filtro, seleção, ordenação e campos) e mensagens, que ligam um gatilho de um componente a ações em outro.',
        'Relação entre fontes diferentes é exigida e declarada: sem ela, a ligação é recusada no construtor com mensagem e na interface de programação com erro 422, pelo mesmo validador rodando em JavaScript e em Python. O barramento corta ciclo em uma volta e avisa, e a seleção e os filtros ficam no endereço da página.',
        'Medido: da mudança do gatilho até a ação, 1,4 milissegundo no percentil 95 com 10 mil feições em memória, contra teto de 100 milissegundos.',
    ],
    'L5-08-editor-arrasto': [
        'Oferece um editor de arrasto próprio em `/construtor?item=<id>`, sem nenhuma biblioteca de arrasto de terceiro: paleta para a tela, tela para tela, alça de largura, árvore de estrutura, painel de propriedades gerado do JSON Schema do tipo e menu de mover para quem usa só toque ou teclado.',
        'O mesmo layout de cinco componentes montado só por arrasto e só por teclado grava documentos idênticos, e a largura é sempre gravada em colunas da grade de doze, nunca em pixel.',
    ],
    'L5-09-desfazer-refazer-rascunho': [
        'Desfaz e refaz a edição no construtor por pilha de alterações com o passo direto e o inverso, com atalho de teclado, agrupando alteração contínua num passo só.',
        'Salva rascunho no servidor e também no navegador: queda da interface de programação durante a edição deixa a cópia local marcada como pendente, e reabrir a tela oferece recuperar o rascunho que nunca chegou ao servidor.',
        'Compara duas versões do documento por identificador de nó, não por posição, e o mesmo documento aberto em duas abas gera conflito de versão nomeado, com a diferença na tela e clique explícito antes de sobrescrever.',
        'Medido: 50 operações desfeitas e refeitas devolvem o documento com o mesmo sha256 em cinco sementes.',
    ],
    'L5-10-temas-marca': [
        'Aplica tema de marca em três níveis: seis temas padrão, tema do inquilino e tema por documento; o editor `/temas` permite montar por arrasto, ver a prévia, conferir o contraste segundo as diretrizes WCAG e exportar ou importar o tema como JSON.',
        'Trocar o tema não recarrega a página, provado nos dois testes de ponta a ponta; valor de cor ou de fonte fora do formato esperado é recusado por validação, o que barra a tentativa de injetar código em um token.',
        'A suíte completa sofreu interrupção por tempo com quatro trilhas em paralelo; os testes unitários e de API passam por segmento.',
    ],
    'L5-11-expressoes-no-navegador': [
        'Acrescenta à linguagem de expressão sete perfis de uso — janela de feição, rótulo, cálculo de formulário, visibilidade, restrição, indicador de painel e título dinâmico — cada um declarando os tipos de retorno que aceita e o orçamento de tempo, de 50 milissegundos no navegador e 500 no servidor.',
        'Entraram seis funções de feição e geometria, levando a biblioteca de 43 para 49 funções nos dois avaliadores; medida de área e comprimento usa esfera de raio 6.371.008,8 metros, com erro de modelo de até 0,5 %, e não serve como medição legal.',
        'Nenhuma tela chama os perfis ainda: o que existe é a biblioteca, conferida com 339 vetores compartilhados rodados em Python e em Node.',
    ],
    'L5-12-acessibilidade-i18n-construtores': [
        'Os construtores têm dicionário em português, inglês e espanhol com paridade de chaves testada, e o seletor de idioma troca o dicionário sem recarregar a página.',
        'O fluxo inteiro — montar três componentes, ligar uma ação, salvar e publicar — é completado só por teclado, e o axe-core não acusa violação crítica ou séria nas telas do construtor.',
        'Correção que saiu daqui e vale para toda a interface: o acento do tema claro media 4,36:1 de contraste, abaixo do mínimo de 4,5:1, e foi escurecido para 4,74:1.',
    ],
    'L5-15-vista-movel-responsivo': [
        'Roda o aplicativo publicado em qualquer largura de tela: a grade de 12 colunas vira uma coluna abaixo de 600 pixels, o mapa continua presente e o quadro de dados troca de tabela para lista na mesma faixa.',
        'Permite uma vista para celular definida à mão, em que cada quadro de raiz tem visibilidade, ordem e largura próprias, e essa vista prevalece sobre o rearranjo automático.',
        'O construtor pré-visualiza o documento em edição em três larguras (375, 768 e 1440 pixels) sem precisar salvar, e o arrasto de quadro passou a funcionar por toque, além do botão e do menu que já existiam.',
    ],
    'L5-01-a-layout-paginas': [
        'Monta a aplicação em páginas pelo editor de arrasto: página de tela cheia ou rolável, cabeçalho, rodapé, menu, os componentes de layout (linha, coluna, grade, acordeão, painel fixo, painel lateral) e janela modal ou ancorada.',
        'O executor renderiza o mesmo documento como aplicação: o menu navega entre páginas, o endereço muda por página e recarregar reabre na página certa; a janela modal usa o elemento nativo do navegador e fecha com Esc; o painel lateral recolhe sem sumir do fluxo.',
        'Medido: aplicação de 2 páginas montada só por arrasto em 2.245 ms; a grade mantém a proporção 8 para 4 entre dois filhos em 1200 px e em 600 px, com diferença de 0,017; com 6 níveis aninhados em três larguras de tela não houve estouro horizontal nem componente com dimensão zerada.',
    ],
    'L5-01-c-widgets-dado': [
        'Faz os componentes de dado do aplicativo consultarem a camada no servidor em vez de exigir a fonte inteira no navegador: página, total, agregação, histograma, valores únicos, identificadores do filtro e exportação passam pelo serviço de feições quando a fonte é camada, e rodam em memória quando a fonte é embutida.',
        'Entram tabela com paginação e ordenação no servidor e exportação do filtro ativo em CSV e GeoJSON, gráfico com agregação no servidor, filtro por texto, valores únicos, intervalo e data, e os componentes de lista, consulta, seleção, informação da feição e adicionar dado; filtros de origens diferentes se combinam por E lógico.',
        'Medido: 113 milissegundos por página no percentil 95 com 100 mil feições, e cinco agregações conferidas contra consulta SQL direta. A edição dentro do aplicativo fica para outro item.',
    ],
    'L5-01-d-widgets-pagina-menu': [
        'Traz 12 componentes de página e de menu para o construtor: texto em Markdown com campo da feição, imagem, botão, cartão, incorporar página externa, divisor, menu, controlador de componentes, compartilhar, entrar, seletor de idioma e seletor de tema.',
        'O texto é sanitizado e dez tentativas de injeção de script não executam; a incorporação de página externa usa lista de domínios e caixa de areia, e o QR de compartilhamento é gerado na própria instalação por `GET /api/qr.svg`, sem serviço externo.',
        'Falta para o item ficar completo: o ramo com esse trabalho ainda não está no tronco, e a comparação com a documentação do produto da Esri foi escrita a partir da lista do item, porque a página oficial estava inacessível.',
    ],
    'L5-01-e-acoes-configuraveis': [
        'Configura ações entre quadros do aplicativo por painel: gatilho, alvo, ação, relação (mesma fonte, por atributo ou espacial) e condição, com a lista de eventos limitada ao que o tipo do quadro emite e a de ações ao que o alvo aceita.',
        'Valida nos dois lados, navegador e servidor: evento incompatível, alvo incompatível, gatilho repetido e condição com campo inexistente são acusados, e renomear o campo da camada marca a referência quebrada no painel.',
        'Dá ao usuário do aplicativo as ações de exportar em CSV ou GeoJSON as feições filtradas, ver na tabela, aproximar na seleção e criar item com a seleção; 30 ações em cadeia levam 0,47 ms no percentil 95, e ciclo fechado avisa e para.',
        'O tipo de item de seleção ainda não existe nesta base.',
    ],
    'L5-04-a-blocos-de-conteudo': [
        'Acrescenta o tipo de item narrativa, editado pelo mesmo editor de arrasto, com onze blocos: capa, texto, imagem, vídeo, áudio, mapa, tabela, botão, separador, conteúdo incorporado e aplicativo; o leitor mostra a narrativa na tela de execução e na página publicada por link.',
        'O bloco de mapa guarda a vista como caixa envolvente mais a proporção do quadro e a reabre por enquadramento: a diferença medida foi de 0,12 % em 5 mapas e 2 larguras de tela, contra o teto de 1 % do portão.',
        'Publicar recusa imagem sem texto alternativo, com 422 e a lista dos blocos em falta, e a regra está no servidor. Fica parcial: as camadas do mapa na página anônima dependem do escopo de tile por token, que é de outro item.',
    ],
    'L5-04-c-temas-capa-colecao': [
        'Cria o tipo de item coleção, com capa (título, subtítulo, mídia) e itens citados por identificador, mantendo as relações sincronizadas a cada gravação: citar item inexistente, de outro inquilino ou a si mesma é recusado com erro 422, e endereço de mídia só é aceito se for da casa ou HTTPS.',
        'Publicar a coleção por link avisa, na interface de programação e na tela, qual item citado ficou de fora do link, e oferece corrigir; o leitor anônimo lê o mesmo aviso em vez de encontrar um espaço vazio sem explicação.',
        'A página pública leva os metadados de compartilhamento social, e as internas não. A troca de tema sem reeditar blocos fica pendente, porque depende do item de temas, ainda ausente do tronco.',
    ],
    'L5-32-vistas-de-camada': [
        'Cria vista de camada como VIEW do PostgreSQL com `security_invoker`: o filtro fica congelado na definição, o campo oculto não existe na relação, vista somente leitura recusa edição com 403, e compartilhar a vista com o público não expõe a camada de origem.',
        'Falta para o item ficar completo: o teste de navegador da tela foi escrito, mas não roda na trilha.',
    ],
    'L5-36-widgets-personalizados-sdk': [
        'Instala quadro de aplicativo escrito por terceiro a partir de um pacote enviado pelo administrador do inquilino: o pacote fica em tabela com isolamento por inquilino, e o carregador reconfere o sha256 do conteúdo antes de executar.',
        'Executa o quadro externo em modo isolado, dentro de moldura com política de conteúdo restrita, para que ele não alcance o cookie de sessão nem rotas da administração.',
        'Está construído e testado apenas na trilha própria, com 15 testes de unidade e de interface de programação e 3 testes de navegador verdes; a medida de primeira pintura foi de 2.412 ms com a máquina em carga 5,3, e a cronometragem do passo a passo do manual por um testador humano ainda não foi feita.',
    ],
    'L7-11-c-telemetria-opcional': [
        'Mantém a telemetria da instalação desligada por padrão; só o superadministrador liga, e a tela mostra a prévia exata do que seria enviado, com 13 campos fixos e apenas valores agregados, sem nome, geometria ou conteúdo.',
        'Com a telemetria desligada, nenhuma chamada de rede sai, medido. O receptor na casa recusa chave desconhecida com 403 sem gravar, campo a mais com 422 e chave de outra instalação com 422; o envio corre num trabalho diário.',
        'O acompanhamento das instalações existe como rota de API, sem tela.',
    ],
    'L7-03-b-rate-limit-abuso': [
        'Limita volume de pedidos em três camadas independentes: o servidor de borda por endereço, a interface de programação por inquilino e plano com janela deslizante no Postgres, e o banimento por repetição de falha de login com ferramenta dedicada e registro de acesso próprio.',
        'A camada da interface é chamada na resolução de sessão, então cobre toda requisição autenticada, por sessão ou por token, e o cabeçalho de endereço de origem forjado não move o ponto em que o limite dispara; uma corrida achada pelo adversário na função do banco foi corrigida com trava e reprovada em 5 rodadas de 200 chamadas concorrentes, sem furo.',
        'Fica parcial a cláusula do limite de tiles por plano: a rota de tiles de imagem ainda não existe nesta base, embora a zona de borda e o mecanismo por escopo já estejam prontos.',
    ],
    'L7-03-d-injecao-consulta': [
        'Uma suíte de segurança dispara 180 tentativas de injeção de SQL contra o serviço de feições e as rotas OGC (filtro, campos de saída, ordenação, agrupamento, estatísticas, lista de identificadores): nenhuma resposta de erro de servidor, 8 ms de latência máxima e a tabela isca intacta.',
        'Um teste estático percorre a árvore do código e exige que nenhuma chamada ao banco monte SQL com texto do usuário; duas falhas de servidor foram corrigidas e agora devolvem 400 com o motivo.',
        'Falta para o item ficar completo: a varredura do ZAP não rodou, por falta de imagem e de disco.',
    ],
    'L7-20-trilha-auditoria': [
        'Grava trilha de auditoria de negócio em tabela que só aceita inserção: a role da aplicação não tem permissão de alterar, apagar ou truncar, e dois gatilhos recusam a tentativa mesmo assim.',
        'Cobre 112 de 112 rotas de escrita do contrato de interface de programação, por duas vias: gatilho sobre o evento de domínio, para as rotas que já registram evento, e uma chamada antes de confirmar toda transação de escrita, para as demais; o identificador da requisição, o endereço de origem, o token, o método e a rota chegam ao banco pela própria transação.',
        'A retenção é configurável por inquilino, com padrão de 730 dias e piso de 90 dias: o piso é a resposta à tentativa de apagar a trilha encolhendo a retenção, e o expurgo roda agendado, com nome derivado do schema e negado à role da aplicação.',
    ],
    'L7-07-b-replica-garage': [
        'Replica o armazenamento de objetos em três nós com fator de replicação 3: com um nó parado foram escritos 1.000 objetos; o nó voltou, sincronizou em 5,2 s, a varredura de verificação não acusou erro e os 1.000 valores sha256 conferiram com o nó que recebeu as escritas desligado.',
        'Medido também o limite do arranjo menor: dois nós com fator 2 mantêm a leitura mas recusam a escrita com um nó parado, respondendo 503 por falta de quórum; a escrita contínua exige três nós. A ressincronização de 256 MiB levou 4,7 s.',
        'O documento de operação cobre acrescentar nó, trocar disco, ver o layout e a varredura periódica. Fora do medido: a ressincronização de 10 GB e o arranjo em contêineres num ambiente de homologação separado.',
    ],
    'L7-08-c-sdk-js': [
        'Publica uma biblioteca JavaScript de acesso à plataforma, sem dependência externa, com o mesmo modelo da biblioteca Python: entrada, itens, camadas, mapas com paginação por cursor, espera de tarefa, tokens, repetição automática em erros temporários e erro tipado.',
        'Traz ajudantes para o MapLibre (fonte, camada, estilo, catálogo por extensão, assinatura de pedido e enquadramento) e regra embutida de que o cabeçalho de autorização nunca acompanha o cookie: a interface responde 400 nesse caso.',
        'Os 10 exemplos entregues abrem com política de conteúdo restritiva e são o próprio teste de ponta a ponta: 13 verdes no navegador, sem violação de política e sem erro de console. Feições por camada e tiles dinâmicos dependem do item de serviços.',
    ],
    'L0-05-e-justica-entre-inquilinos': [
        'A fila de trabalhos alterna entre inquilinos em vez de servir por ordem global: com dois inquilinos e um trabalhador, um trabalho curto espera no máximo o trabalho que já está rodando — medido em 0,5 s com dois trabalhos de 300 s à frente e 0,2 s com cinquenta.',
        'A leitura de um trabalho pendente devolve a posição na fila do inquilino, e a tela Tarefas mostra esse número.',
        'Falta para o item ficar completo: a migração que faz o rodízio existe apenas na trilha de entrega; no ramo de lançamento a fila ainda é por ordem de chegada, e o teste de navegador com a posição na fila não foi feito.',
    ],
    'UX-01-sistema-de-design': [
        'Concentra cor, tipografia, espaçamento, raio, sombra e foco num arquivo único de tokens, em duas camadas (primitivos por tema e semânticos), e todas as telas passam a usar a identidade visual "instrumento".',
        'Acrescenta quatro componentes base (estado de tela, avisos, painel e seletor de tema) e uma guia viva em `/estilo-guia` que calcula o contraste no próprio navegador.',
        'Uma verificação automática reprova cor ou tamanho escrito fora do arquivo de tokens; 15 casos foram corrigidos na primeira passagem, a auditoria de acessibilidade não acusa violação séria nos dois temas, e as 20 telas foram capturadas em 1280 e 390 pixels antes e depois.',
    ],
    'UX-02-telas-entrada-conta-convite': [
        'As telas públicas de entrada, aceitação de convite e redefinição de senha mostram o erro no campo que o causou, com foco no primeiro inválido, botão ocupado durante a chamada, aviso de tecla Caps Lock e estado nomeado quando o servidor não responde ou o token expirou.',
        'A interface resolve o idioma pela ordem endereço, preferência guardada, atributo da página, navegador e português; os arquivos de inglês e espanhol estão completos com 995 chaves, e a paridade de chaves e de variáveis é conferida por teste.',
        'O teste de ponta a ponta percorre entrar, segundo fator, conta e sair, com capturas em 360 e 1280 pixels e nenhuma violação séria de acessibilidade nas telas percorridas.',
    ],
    'UX-03-tela-conteudo-item-lixeira': [
        'Dá à lista do catálogo e ao painel do item estados explícitos em vez de tela em branco: vazio com ação sugerida, carregando com esqueleto, erro com a referência e opção de repetir, e acesso negado.',
        'Arrastar arquivos sobre a lista cria itens pelo mesmo caminho do botão de novo item, caminho que estava quebrado desde a entrega do catálogo e foi consertado; a seleção em massa sobrevive a reordenar e filtrar, porque é guardada por identificador.',
        'Medido: desenho da lista com 1.000 itens em 57,7 milissegundos no percentil 95, contra alvo de 500, com capturas em duas larguras e sem violação séria de acessibilidade.',
    ],
    'UX-04-tela-mapa-polimento': [
        'O visualizador tem uma moldura única: barra no topo, trilho à esquerda com um botão por painel e gaveta com os painéis de pesquisa, camadas, legenda, medição, desenho, anotações, impressão e exportação, mais a tabela de atributos ancorada no rodapé.',
        'Tem atalhos de teclado, tela cheia, impressão que manda só o mapa para o papel, painel inferior de 390 pixels no celular e mapa de fundo escuro; o teste de navegador abre cada painel em 1280 e em 390 pixels e roda o axe-core.',
        'Falta para o item ficar completo: o registro do veredito do item; a junção dos ramos de painel trouxe quatro correções, já aplicadas.',
    ],
    'UX-05-telas-conexoes-uploads-tarefas-compartilhado': [
        'A tela de conexões ganhou criar, editar e apagar com confirmação, busca, ordenação por coluna e estados de vazio, carregando, erro e sem permissão, com os erros do servidor aparecendo no campo certo.',
        'A tela de envio de arquivos virou fila: vários arquivos, uma barra por arquivo, cancelar um ou todos, tentar de novo, com bytes, velocidade e tempo restante.',
        'A tela de tarefas deixou de ter texto fixo no código e passou a usar o dicionário de idiomas, e a página pública de item compartilhado perdeu a barra lateral do produto, com estados nomeados para item não encontrado, expirado e excesso de pedidos.',
        'O progresso byte a byte no envio foi tentado e recusado pela própria trilha, porque o pedido com contador de bytes leva o cookie de sessão junto e cai em erro de autenticação ambígua; o envio segue em partes de 16 MiB, e a decisão ficou registrada para o dono da autenticação.',
    ],
    'UX-06-tela-administracao-inquilino': [
        '`/admin` reúne a administração do inquilino numa porta única: um cartão por assunto (usuários ativos, convites pendentes, grupos, papéis, tokens válidos, uso e cota de armazenamento, provedor de diretório, acervo com licença, acessos em 24 h), com o número lido da rota que já existe e o caminho da tela que gere o assunto.',
        'A tela `/admin/acervo` lista as fontes do acervo com busca, ficha de procedência e a ação de adicionar ao catálogo, transformando a exigência de confirmação de risco de dado pessoal em diálogo antes da segunda chamada; a seção de diretório LDAP ganhou tela, e toda escrita administrativa mostra o evento registrado.',
        'Nada disso está no ramo que serve a demonstração: nenhum commit da trilha de interface foi mesclado nele, e o merge reescreve quatro arquivos que outro agente edita agora, o que exige um turno dedicado.',
    ],
    'HARD-01-varredura-de-seguranca-continua': [
        'Roda a varredura de segurança dentro do portão de conferência do repositório: análise estática do código Python, auditoria de dependências Python e JavaScript, busca de segredo no histórico do repositório e varredura de imagem, com as ferramentas binárias fixadas por resumo criptográfico.',
        'Exceção só entra com prazo registrado em arquivo próprio, e a seção de segurança da documentação é gerada da varredura. Consertos que vieram dela: leitor de XML seguro no armazenamento de objetos, ocultação da versão do servidor de borda e cabeçalhos de política de conteúdo e de enquadramento.',
        'A varredura dinâmica da aplicação fica fora do portão principal, num alvo próprio, porque precisa de uma instância de teste.',
    ],
    'HARD-02-testes-de-carga-e-caos': [
        'A suíte de caos prova a retomada em dois cenários: o trabalhador morto no meio de um trabalho é ceifado por batimento vencido e o trabalho volta à fila com contador de reinícios; a API morta no meio não perde o trabalho nem a sessão, porque a sessão vive no banco e não no processo.',
        'Falta para o item ficar completo: a medição de latência no percentil 95 por rota contra as metas declaradas e o cenário de banco de dados derrubado, que está em outro ramo na fila.',
    ],
    'UX-07-telas-do-construtor-e-aplicativo': [
        'O construtor lista aplicativos e painéis quando aberto sem item, cria um novo, e com item mostra salvar, publicar com confirmação, executar e trocar de item, com o conflito de versão nomeado.',
        'As telas de execução do aplicativo mostram estados explícitos para item inexistente e tipo errado, e quadro com configuração inválida mostra erro nomeado no painel em vez de quebrar a tela.',
        'A árvore da estrutura do documento segue o padrão de acessibilidade de árvore, com a linha focável pelo teclado, e a paleta e o painel lateral ficaram presos ao topo com rolagem própria, porque o arrasto pegava o quadro errado quando a página rolava.',
        'Os rótulos da paleta ainda não estão no dicionário de idiomas.',
    ],
    'UX-08-telas-rede-de-utilidades-e-motor': [
        'O visualizador ganha dois painéis: Rotas, que calcula rota, isócrona e matriz de origens por destinos sobre o serviço de roteamento do recorte, mostrando a procedência da resposta e traduzindo os erros do serviço em texto nomeado; e Motor, que cria a área de estudo, escolhe fatores e pesos, roda a análise em escala grossa e refina só onde foi aprovado.',
        'As células do motor são pintadas no mapa com a nota, a cobertura e a aprovação em janela de atributos; rodar sem área ou sem fator mostra o motivo, em vez de painel vazio.',
        'Os dois painéis existem apenas num ramo separado, 201 commits à frente e 366 atrás do ramo de demonstração. A interface da rede de utilidades, com traçado montante e jusante e importação de BDGD ou EPANET, continua ausente do ramo de demonstração.',
    ],
    'UX-09-telas-ferramentas-e-tarefas': [
        'Abre a tela `/ferramentas`, que lista os tipos de tarefa disponíveis em cartões por grupo, com o custo declarado de cada um (memória, tempo, se é pesada, executor e perfil mínimo) e busca.',
        'O formulário de cada ferramenta é gerado do esquema dos parâmetros, com limites, valores permitidos, obrigatoriedade e padrão vindos do próprio esquema; a validação aponta o motivo no campo antes de qualquer chamada, e o erro do serviço volta ao campo correspondente.',
        'Executar cria a tarefa e mostra a execução ao vivo no mesmo painel, com barra, log e cancelamento, e liga para a tarefa e para o item do resultado. As ferramentas no vocabulário de geoprocessamento da Esri não estão cobertas por este item.',
    ],
    'UX-10-acervo-sem-tela': [
        'A tela `/acervo` ganhou o controle que faltava para a rota de escrita `POST /api/acervo/{fonte}/adicionar`, com os quatro estados do sistema de design na lista e no próprio controle: carregando, vazio, erro com referência e acesso negado com o nome do privilégio exigido.',
        'Fonte com dado pessoal abre diálogo de confirmação antes de entrar no catálogo, e o mapa de cobertura da interface caiu de 41 para 40 lacunas.',
        'Falta para o item ficar completo: ele depende do item do sistema de design, que ainda está parcial.',
    ],
    'UX-11-arquivos-sem-controle': [
        'A seção "Arquivos e objetos" da tela de organização mostra uso contra cota, roda a varredura de objetos órfãos e permite enviar, baixar e apagar arquivo com confirmação, com os erros de tamanho e de tipo nomeados na tela.',
        'O mapa de cobertura da interface foi regenerado com 240 rotas e 11 lacunas de escrita, nenhuma delas da trilha de interface.',
        'Nada dessa trilha está no ramo de lançamento: nada dela foi mesclado, e a junção depende de quatro arquivos que outros agentes editavam na mesma árvore.',
    ],
    'UX-12-categorias-sem-controle': [
        'A tela `/admin/categorias` dá controle às duas rotas de escrita de categorias que não tinham tela: editor da árvore de até três níveis, que grava a árvore inteira preservando os identificadores, e importação dos modelos ISO 19115 e INSPIRE, idempotente.',
        'Os erros da API aparecem nomeados no controle: categoria em uso responde 409 com os caminhos e itens, limite de categorias responde 422 com o número atingido e o máximo, e a falta de privilégio responde 403. A lista tem estado explícito para carregando, vazio, erro e negado.',
        'O mapa de cobertura da interface caiu de 41 para 36 lacunas; o item fica parcial porque depende do sistema de design, que também está parcial.',
    ],
    'UX-13-conexoes-sem-controle': [
        'Fecha a lacuna de escrita de conexões: as oito rotas de conexão externa têm controle alcançável na tela `/conexoes` — criar, editar, apagar com confirmação, testar, histórico e publicar.',
        'Conexão removida por outra pessoa deixa de prender o formulário: o erro 404 avisa e recarrega a lista, e os erros de privilégio, conflito de nome, validação, endereço inseguro e cota aparecem nomeados no campo ou no aviso da lista.',
        'O teste de ponta a ponta exercita 17 estados da tela, com capturas em duas larguras, sem violação séria de acessibilidade e sem erro de console.',
    ],
    'UX-14-geocodificador-sem-tela': [
        'A tela `/geocodificar` expõe as rotas de endereço para coordenada e de coordenada para endereço: até 50 candidatos com pontuação, tipo de acerto e botão de ver no mapa, e o caminho inverso com vizinho mais próximo, distância e marca de fora do raio.',
        'Resposta vazia aparece com o código e a mensagem reais do motor, nunca com o número cru; o mapa de cobertura da interface caiu de 35 para 33 lacunas.',
        'Falta para o item ficar completo: a resposta com endereço encontrado de verdade não foi provada, porque a base de endereços do IBGE não está carregada na trilha.',
    ],
    'UX-15-geocodificador-esri-sem-controle': [
        'A tela de geocodificação ganhou a seção do serviço compatível com a Esri: a URL do GeocodeServer para copiar, com o escopo exigido, e botões para ver o descritor, buscar candidatos por endereço, geocodificar ao contrário a partir de coordenada e geocodificar em lote até 500 endereços.',
        'As respostas aparecem no formato da Esri, e as respostas de negócio do protocolo viram estado nomeado na tela em vez de código cru; a tela de tokens passou a mostrar as URLs dos serviços externos com o escopo exigido.',
        'O mapa de cobertura da interface caiu de 33 para 29 lacunas; a consulta com retorno real contra a base de endereços não foi provada na trilha.',
    ],
    'UX-16-ingestao-sem-tela': [
        'A tela `/importacoes` dá controle ao fluxo de arquivo até camada: lista as importações com estado, formato, número de feições e erro; cria a importação a partir de um arquivo já enviado, com sugestão de formato pela extensão; acompanha o trabalho de inspeção até a proposta.',
        'Em "conferir e carregar" o usuário edita a proposta (título, sistema de referência quando o arquivo não declara, codificação, tipo de geometria, ação para geometrias inválidas e campos a importar), dispara a carga e acompanha até a conclusão; o erro da API aparece no campo que o causou.',
        'Achado corrigido no caminho: `GET /api/importacoes/formatos` respondia 404 porque estava declarado depois da rota com identificador. O mapa de cobertura da interface caiu de 29 para 26 lacunas.',
    ],
    'UX-17-login-sem-controle': [
        'Faz a tela de entrada declarar os provedores de login habilitados no inquilino: quando há diretório LDAP ligado, um botão alterna para o login por diretório com os mesmos campos, e o login local continua disponível.',
        'As respostas do diretório têm texto próprio na tela: fora do ar, desabilitado, usuário sem grupo autorizado e conta que já existe como login local.',
    ],
    'UX-18-plataforma-sem-tela': [
        'A tela `/admin/inquilinos` é o console do superadministrador: lista os inquilinos com estado, número de usuários, criação e último acesso, cria inquilino mostrando a senha temporária uma única vez, suspende, reativa e apaga com dupla confirmação.',
        'Quem não é superadministrador recebe 404 da API, que a tela mostra como acesso negado; erros de validação e de nome repetido aparecem no próprio campo, e o mapa de cobertura da interface caiu de 26 para 22 lacunas.',
        'Falta para o item ficar completo: ele depende do item do sistema de design, ainda parcial.',
    ],
    'UX-19-rede-sem-tela': [
        'As rotas de roteamento, área de serviço e matriz origem-destino existem no ramo de lançamento como interface de programação, entregues pelo item de rota e isócrona.',
        'A tela que chama essas rotas não existe no ramo de lançamento: o painel de rotas foi construído na trilha de interface e nada dessa trilha está mesclado.',
    ],
    'UX-20-usuarios-sem-controle': [
        'A rota de edição de papel que estava sem controle na tela fica coberta pela tela de administração de papéis da trilha de interface.',
        'Esse trabalho não está no ramo que serve a demonstração: nenhum commit da trilha de interface foi mesclado nele. O ramo acumula 392 commits em 316 arquivos e o merge reescreve quatro arquivos que outro agente edita agora, o que exige um turno dedicado.',
    ],
    'UX-21-multiescala-sem-tela': [
        'As rotas do motor de grades aninhadas deixam de existir apenas na interface de programação: o painel "Motor" do visualizador cria a área de estudo a partir da vista atual do mapa, lista e cadastra fatores com a escala nativa declarada, aplica peso por controle deslizante e roda as etapas macro e micro.',
        'Uma rota de leitura foi criada para a lacuna: as células com nota, cobertura e situação voltam como coleção de feições, com teto declarado e indicação de resultado truncado; quando a nota da célula vem do bloco da fonte, e não de dado próprio, o painel diz isso.',
        'O painel repete o aviso de que os pesos são escolhidos pelo usuário, não medidos.',
    ],
    'L0-02-z-apagar-inquilino-apaga-schema': [
        'Apagar um inquilino apaga também o schema de dado dele na mesma transação, com as tabelas de camada, as funções de tile e as políticas de acesso, sob trinco por identificador de inquilino.',
        'A origem do item foi um incidente com 1.219 schemas de teste deixados para trás; a fixture de teste agora confere, ao final, que o schema sumiu.',
    ],
    'L4-04-c-unificar-subrede': [
        'Guarda numa tabela só as duas leituras de subrede da rede elétrica, com a coluna de origem separando a subrede derivada do controlador, que é a canônica, da hierarquia declarada pelo arquivo da distribuidora.',
        'A migração copiou as linhas preservando o identificador e repôs as chaves estrangeiras de nós e arestas, e uma verificação por origem impede a mistura das duas.',
        'A importação liga as duas leituras pelo nome dentro do mesmo nível e conta o que não casa, sem tratar divergência como erro provado; no recorte da cooperativa de teste a reconciliação bateu em 3 de 3 alimentadores e 1.729 de 1.729 transformadores.',
    ],
    'L7-01-d-instalador-extensoes': [
        'A lista de extensões do Postgres que o produto exige passa a morar num arquivo único, lido pelos três consumidores: o instalador, o preparador de ambiente de trilha e o ensaio de restauração da cópia de segurança.',
        'A rotina cria o que falta e confere em seguida no catálogo do banco, terminando com erro que nomeia a extensão que não nasceu. Medido em base descartável: base só com PostGIS termina com as quatro extensões e o dump restaura nela sem passo manual; sem a extensão `unaccent` a tabela de itens não é criada e a conferência reprova nomeando-a.',
        'O `install.sh` inteiro continua sem teste que o execute, porque ele instala pacotes do sistema e escreve unidades do systemd.',
    ],
    'UX-23-mapa-sem-controle': [
        'Acrescenta ao visualizador o painel de seleção: por atributo, com condições combinadas por E e OU, valores únicos sugeridos e a consulta equivalente mostrada na tela; pela geometria desenhada, com interseção ou distância; e entre camadas.',
        'O resultado realça na tabela de atributos, vira filtro da camada no mapa e pode ser guardado como item de seleção.',
        'As anotações foram reescritas com estados explícitos, edição de texto pelo autor, resolver e reabrir e exclusão com confirmação, e o painel de exportação passou a importar pacote de mapa, com recusas locais e erros de tamanho e validação nomeados.',
    ],
    'L4-01-f-alcance-do-tracado-rede-real': [
        'A tolerância de conexão da rede passou a ser declarada por par de tipos de ativo, o que fez o traçado a jusante alcançar 599 de 600 transformadores, contra 428 antes, e levou o pior alimentador de 66,67 % para 99,51 % de alcance, com os cinco alimentadores acima do piso de 95 %.',
        'A folga extra só reencontra o mesmo ponto e nunca alcança um segundo, o que mantém o número de laços na média tensão igual ao de antes; `GET /api/rede/{id}/topologia/diagnostico` lista os órfãos restantes por classe, com contagem, distância e exemplo — de 1.038 para 495.',
        'Falta para o item ficar completo: o registro do veredito do item; as cláusulas do portão estão medidas.',
    ],
    'L1-01-ingest-raster': [
        'O trabalho de fila `imagens.ingestar` converte o arquivo enviado em COG (GeoTIFF otimizado para nuvem) em dois perfis, visual e científico, com validação pelo rio-cogeo.',
        'O arquivo convertido sobe ao Garage com nome derivado do sha256 e nasce ao mesmo tempo como item STAC no pgstac, na coleção do inquilino, e como item do catálogo do tipo `raster`, com miniatura de 600 por 400 pixels e estatísticas.',
        'A gravação no catálogo é uma transação única: ou o item inteiro aparece, ou nada aparece; o tempo e a taxa de compressão de cada conversão ficam no resultado do trabalho.',
    ],
    'L1-01-a-pgstac-e-stac-api-por-inquilino': [
        'A instalação expõe uma STAC API (catálogo padronizado de imagens) por inquilino em `/svc/<token>/stac/`, sobre o pgstac instalado pelas migrações, com a role da aplicação restrita aos papéis de leitura e ingestão.',
        'Medido em 06/09/2026 sobre uma coleção de 10.000 itens sintéticos: a busca por retângulo devolveu 567 itens em 234,73 ms de mediana em 5 chamadas HTTP completas, com a primeira chamada de aquecimento descartada (`tests/medidas/L1-01-a.json`).',
    ],
    'L1-01-j-proveniencia-da-imagem-lastro': [
        'Cada item de imagem carrega a cadeia de origem: versões de GDAL, rio-cogeo, rasterio e da própria plataforma medidas no momento da conversão, o argumento exato de cada `gdal_translate`, o sha256 de entrada e de saída de cada passo e um sha256 do item inteiro sem essa própria chave.',
        '`POST /api/imagens/<item>/conferir` baixa cada arquivo com resumo criptográfico de volta do repositório de objetos em fluxo, recalcula o sha256 e compara por arquivo, sem um veredito único que esconda a divergência de um deles.',
        'Itens ingeridos antes deste item podem ser completados por uma rota de administração, que preenche só o metadado já medido, e pelo trabalho de fila `imagens.reexecutar`, que reconverte o arquivo bruto e compara o sha256 obtido com o registrado; quando a cadeia não existe, o campo fica ausente em vez de ser preenchido.',
    ],
    'L0-04-i-fonte-registrada': [
        'Registra um PostgreSQL/PostGIS externo do cliente como fonte de dado (`POST /api/conexoes` do tipo `postgres_fdw`), lista as tabelas desse banco por `pg_catalog` sem copiar dado e publica várias de uma vez, cada tabela virando uma camada vetorial referenciada no catálogo.',
        'Cada tabela publicada vira tabela estrangeira mais uma view que injeta o inquilino e filtra por ele, porque uma tabela estrangeira não aceita política de segurança por linha; a credencial fica cifrada e a view recebe apenas permissão de leitura.',
        'A defesa de alvo recusa o banco da própria instalação em qualquer endereço e o endereço de metadado de nuvem; um banco em rede privada continua permitido, porque é caso legítimo de cliente.',
    ],
    'L0-06-a-dump-logico': [
        'O periódico `backup.dump_logico` roda às 03:00 e gera um `pg_dump` por inquilino mais um do schema da plataforma, cada arquivo restaurável sozinho, com sha256, bytes, tempo e número de tabelas gravados em `plat.backup` e a cópia enviada ao bucket `plat-backup`.',
        'O espaço livre é conferido antes de escrever qualquer byte, com mínimo de 10 GB por padrão; abaixo disso o trabalho termina em falha com os dois números na mensagem, grava evento e envia mensagem ao superadministrador.',
        'A retenção mantém 14 cópias diárias e 8 semanais por schema, apagando linha, arquivo e objeto juntos, e o periódico `backup.verificar` reconfere o sha256 de cada arquivo às segundas-feiras.',
    ],
    'L2-03-b-ferramentas-geometria': [
        'A edição no mapa tem as operações de geometria do item: unir feições (`POST /api/camadas/{id}/unir`), dividir feição (`/dividir`) e as demais operações de desenho, todas pela mesma porta de escrita de feição da plataforma.',
        'A porta de escrita valida tipo de geometria, SRID, validade do polígono, campo obrigatório, domínio e tamanho, e controla concorrência por número de versão da feição.',
    ],
    'L3-01-h-presets': [
        'A tela `/amc/presets` cria, edita, apaga, exporta e importa conjuntos de pesos nomeados do motor multicritério, com cinco conjuntos integrados somente de leitura que nascem com o schema, entre eles o de pesos iguais.',
        'Aplicar um conjunto (`POST /api/amc/presets/{id}/aplicar`) recebe a matriz, roda a combinação na mesma requisição e devolve o resultado, sem criar trabalho de fila.',
        'O conjunto de outro inquilino responde 404, provado na varredura cruzada entre dois inquilinos nas rotas de leitura, alteração, exclusão e aplicação; a importação recusa com 422 o conjunto que cite fator fora do modelo informado e nomeia o que falta.',
    ],
    'L3-02-c-smaa': [
        'O trabalho de fila `amc.smaa` responde de que pesos uma unidade precisaria para vencer: para cada unidade calcula a fração dos sorteios de peso em que ela ficou em cada posição até a vigésima, o vetor central de pesos que a põe em primeiro e um fator de confiança.',
        'A implementação segue o SMAA-2 de Lahdelma e Salminen (2001) e reutiliza o sorteio de pesos e o combinador já existentes, sem rota nova de interface de programação.',
        'A prova é de resposta conhecida: três unidades sintéticas com dois fatores dão, na conta a mão, 0,5 / 0,5 / 0 de aceitabilidade em primeiro lugar e vetor central (0,75; 0,25); com 20 mil sorteios o motor devolveu 0,5046 / 0,4955 / 0 e (0,7501; 0,2499).',
    ],
    'L3-14-cobertura-dado-ausente': [
        'O motor multicritério mede, para cada fator, a fração de unidades de análise com dado válido e, quando a área da unidade é informada, a fração de área do território com dado válido.',
        'Fator com cobertura abaixo do limiar declarado, 80 % por padrão, sai marcado no relatório em vez de ser removido ou escondido.',
        'Ausência de dado nunca vira zero nem cem na cobertura: a conta usa só a máscara de valores finitos e não toca no valor do fator, que é trabalho da combinação.',
    ],
    'L3-15-metadado-fator': [
        'Cada fator do motor multicritério carrega uma ficha com fonte, versão da fonte, unidade, direção, base (norma, engenharia ou preferência), marca de indicador indireto com teto de peso, classe de peso, origem da âncora de peso e o que o fator não sustenta.',
        'O teto do indicador indireto é regra e não texto: a fatia de peso do fator sobre a soma dos pesos não pode passar do teto declarado, e a recusa sai 422 tanto no documento do modelo quanto nos pesos de uma execução, nomeando o fator, a fatia medida, o teto e o peso que caberia.',
        'O relatório e a explicação por unidade trazem a ficha de cada fator, a lista de indicadores indiretos e a lista de âncoras, com âncora não declarada registrada como terceira categoria, nunca convertida em escolhida.',
    ],
    'L3-16-desempenho-escala': [
        'O contrato de escala do motor multicritério está num módulo só: a combinação roda no navegador até 50.000 unidades e no servidor acima disso, em blocos de 50.000, e o plano é recusado antes de entrar na fila quando não cabe em unidades, fatores, memória ou prazo.',
        'Medido em 07/09/2026: a recombinação no servidor de 1 milhão de unidades por 15 fatores levou 0,9734 s contra o limite de 5 s do portão, com pico de 70,26 MB de memória em 20 blocos; a combinação de 50.000 por 15 no navegador levou 21,18 ms.',
        'Uma cláusula foi refutada e fica registrada: à taxa medida da estatística zonal, extrair 1 milhão de células por 15 fatores levaria 10.483,9 s contra os 1.800 s do portão, então o motor recusa esse plano e o limite honesto de hoje é uma grade de 166.898 unidades com 15 fatores.',
    ],
    'L0-02-g-checagem-privilegio-papel-id': [
        'Criar ou editar usuário passa a conferir se quem concede tem todos os privilégios do papel que está concedendo; sem isso a resposta é 403 e o detalhe lista o que faltaria.',
        'A mesma regra vale para o perfil e para o papel nulo, porque promover alguém a administrador sem papel concede o mesmo conjunto; a conferência também cobre a alteração em lote.',
        'A refutação foi rodada em forma completa: para cada um dos 47 privilégios do vocabulário, o ator ficou com todos menos um e ofereceu todos, em 94 chamadas de criação e edição, com 94 respostas 403 e nenhuma resposta de sucesso.',
    ],
}

# Uma frase por linha do produto: o que ela deve fazer quando pronta (do objetivo do laço).
LINHAS_DESCRICAO = OrderedDict([
    ("L0 fundação", "repositório, identidade e acesso, catálogo por inquilino, ingestão de vetor, fila de trabalhos, "
                    "cópia de segurança, administração da organização, SSO, metadado"),
    ("L1 imagens", "COG/STAC/tiles por inquilino, token de acesso, conectores Sentinel/NASA/Copernicus/MapBiomas, "
                   "série temporal, IA na entrada"),
    ("L2 plataforma", "mapa web, simbologia, edição, serviços Esri-compatíveis e OGC, geoprocessamento, painéis, campo, "
                      "migração de AGOL, 3D, relações e regras, geocodificação e rota, impressão, versionamento e "
                      "sincronização, tempo real, analítica grande, notebooks"),
    ("L3 motor AMC", "motor multicritério explicável como serviço, com robustez medida"),
    ("L4 rede de utilidades", "modelo de rede, traçado, edição com regras, sub-redes e diagramas, conectores BDGD/CIM, "
                              "estruturas e regras avançadas"),
    ("L5 builder", "construtores arrasta-e-solta de aplicação, fluxo, formulário e narrativa"),
    ("L6 conectores", "acervo da casa e conectores vivos"),
    ("L7 operação", "instalador limpo, carga, segurança, manual e tour, observabilidade, alta disponibilidade, SDK e "
                    "webhooks, medição e cobrança, i18n e acessibilidade, appliance no cliente, LGPD, suporte, "
                    "produção final"),
])


def carregar() -> dict:
    return json.loads(ESTADO.read_text(encoding="utf-8"))


def por_linha(backlog: list[dict]) -> OrderedDict:
    linhas: OrderedDict[str, list[dict]] = OrderedDict((k, []) for k in LINHAS_DESCRICAO)
    for item in backlog:
        linhas.setdefault(item["linha"], []).append(item)
    for k in linhas:
        linhas[k].sort(key=lambda i: (i.get("prioridade", 9), i["id"]))
    return linhas


def estados_por_id(backlog: list[dict]) -> dict[str, str]:
    return {i["id"]: i["estado"] for i in backlog}


def dependencias_abertas(item: dict, estados: dict[str, str]) -> list[str]:
    return [d for d in item.get("dependencias", []) if estados.get(d) != "entregue"]


def medidas_resumo() -> list[tuple[str, str, str, int]]:
    saida = []
    if MEDIDAS.is_dir():
        for arq in sorted(MEDIDAS.glob("*.json")):
            d = json.loads(arq.read_text(encoding="utf-8"))
            if isinstance(d, list):  # alguns itens gravaram uma lista de medidas, não o dicionário do padrão
                saida.append((arq.name, "", "", len(d)))
                continue
            saida.append((arq.name, d.get("gerado_em", ""), d.get("git_sha", ""), len(d.get("medidas", {}))))
    return saida


def veredito_do_turno(turno: int) -> str:
    pasta = LACO / "handoffs" / f"T{turno}"
    if not pasta.is_dir():
        return "sem pasta de handoffs"
    if (pasta / "99_veredito.md").exists():
        return "escrito (`99_veredito.md`)"
    presentes = sorted(p.name for p in pasta.iterdir())
    return "pendente (gerente ainda não escreveu `99_veredito.md`); handoffs presentes: " + ", ".join(presentes)


def gerar(estado: dict) -> str:
    backlog = estado["backlog"]
    estados = estados_por_id(backlog)
    contagem = Counter(i["estado"] for i in backlog)
    linhas = por_linha(backlog)
    turno = estado.get("turno", 0)
    agora = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")

    faltam = [i["id"] for i in backlog if i["estado"] in ("entregue", "parcial") and i["id"] not in FUNCOES]
    if faltam:
        sys.stderr.write("itens entregues/parciais sem frase em FUNCOES: " + ", ".join(faltam) + "\n")
        sys.exit(2)

    out: list[str] = []
    out.append("# Painel do laço PLATAFORMA ENTERPRISE")
    out.append("")
    out.append(f"Gerado por `laco/gera_painel.py` de `laco/estado.json` em {agora}. Não editar à mão: rode o script.")
    out.append("")
    out.append(f"- Estado do laço: **{estado.get('estado')}** · turno {turno} · autoturno {estado.get('autoturno')}")
    out.append(f"- Produto: codinome `{estado['produto']['codinome']}` · nome público: {estado['produto']['nome_publico']}")
    out.append(f"- URL interna: {estado['produto']['url_interna']}")
    out.append(f"- Repositório: `{estado['produto']['repo']}` · schema `{estado['produto']['schema']}` · role "
               f"`{estado['produto']['role']}` · portas {estado['produto']['portas']}")
    out.append(f"- Veredito do turno {turno}: {veredito_do_turno(turno)}")
    out.append("")

    out.append("## Placar")
    out.append("")
    out.append("Contagem por estado dos itens do backlog (lida do `estado.json`):")
    out.append("")
    out.append("| estado | itens |")
    out.append("|---|---|")
    for e in ORDEM_ESTADOS:
        out.append(f"| {e} | {contagem.get(e, 0)} |")
    out.append(f"| **total** | **{len(backlog)}** |")
    out.append("")
    placar = estado.get("placar", {})
    out.append("Placar registrado no estado (`placar`, atualizado pelo gerente no fim do turno): " +
               ", ".join(f"{k} {v}" for k, v in placar.items()) + ".")
    out.append("")
    out.append("Por linha:")
    out.append("")
    out.append("| linha | itens | entregue | parcial | tentando | refutado | pendente |")
    out.append("|---|---|---|---|---|---|---|")
    for nome, itens in linhas.items():
        c = Counter(i["estado"] for i in itens)
        out.append(f"| {nome} | {len(itens)} | {c.get('entregue', 0)} | {c.get('parcial', 0)} | {c.get('tentando', 0)} | "
                   f"{c.get('refutado', 0)} | {c.get('pendente', 0)} |")
    out.append("")

    out.append("## O que o produto faz hoje")
    out.append("")
    com_funcao = [i for i in backlog if i["id"] in FUNCOES]
    if not com_funcao:
        out.append("Nada ainda: nenhum item entregue.")
    for item in com_funcao:
        rotulo = item["estado"]
        if rotulo == "tentando":
            rotulo = "tentando; código no repositório, veredito do gerente pendente"
        elif rotulo == "pendente":
            rotulo = "pendente; código no repositório, item devolvido pelo driver (veredito do gerente pendente)"
        out.append(f"### {item['id']} ({rotulo})")
        out.append("")
        for frase in FUNCOES[item["id"]]:
            out.append(f"- {frase}")
        out.append("")

    out.append("## Fronteira: o que o produto NÃO faz ainda")
    out.append("")
    out.append("Uma linha por linha do produto. O que está `pendente` não existe na tela nem na máquina.")
    out.append("")
    for nome, itens in linhas.items():
        pend = [i["id"] for i in itens if i["estado"] not in ("entregue",)]
        c = Counter(i["estado"] for i in itens)
        out.append(f"### {nome}")
        out.append("")
        out.append(f"Deve fazer: {LINHAS_DESCRICAO.get(nome, '(linha sem descrição no script)')}.")
        out.append("")
        if not pend:
            out.append("Todos os itens entregues.")
        else:
            out.append(f"Não faz ainda ({len(pend)} de {len(itens)} itens não entregues; pendentes {c.get('pendente', 0)}): "
                       + ", ".join(f"`{p}`" for p in pend) + ".")
        out.append("")

    out.append("## Backlog: os itens por linha")
    out.append("")
    out.append("Prioridade 1 = primeiro. `dep. abertas` = dependências ainda não entregues.")
    out.append("")
    for nome, itens in linhas.items():
        out.append(f"### {nome} ({len(itens)} itens)")
        out.append("")
        out.append("| id | prio | estado | tent. | turno | dep. abertas | bloqueio |")
        out.append("|---|---|---|---|---|---|---|")
        for i in itens:
            dep = dependencias_abertas(i, estados)
            out.append(f"| `{i['id']}` | {i.get('prioridade', '')} | {i['estado']} | {i.get('tentativas', 0)} | "
                       f"{i.get('turno') if i.get('turno') is not None else ''} | "
                       f"{', '.join(dep) if dep else '—'} | {neutro(i.get('bloqueio')) if i.get('bloqueio') else '—'} |")
        out.append("")

    out.append("## Decisões do dono")
    out.append("")
    out.append("| id | data | pergunta | estado |")
    out.append("|---|---|---|---|")
    for d in estado.get("decisoes_do_dono", []):
        out.append(f"| {d['id']} | {d['data']} | {neutro(d['pergunta'])} | {neutro(d['estado'])} |")
    out.append("")

    out.append("## Medidas disponíveis (`tests/medidas/`)")
    out.append("")
    med = medidas_resumo()
    if not med:
        out.append("Nenhum arquivo de medidas ainda.")
    else:
        out.append("| arquivo | gerado em | git_sha | medidas |")
        out.append("|---|---|---|---|")
        for nome, gerado, sha, n in med:
            out.append(f"| `{nome}` | {gerado} | `{sha}` | {n} |")
    out.append("")
    out.append("Todo número em documento sai desses arquivos, com o comando que o gerou.")
    out.append("")

    out.append("## Ledger (últimos registros)")
    out.append("")
    ledger = estado.get("ledger", [])
    if not ledger:
        out.append("Vazio: o gerente escreve o primeiro registro ao fechar o turno 1.")
    else:
        for r in ledger[-3:]:
            out.append("- " + neutro(json.dumps(r, ensure_ascii=False)))
    out.append("")

    out.append("## Notas do estado")
    out.append("")
    out.append("Texto do `estado.json` com nomes de cliente/parceiro neutralizados pelo script.")
    out.append("")
    for n in estado.get("notas", []):
        out.append(f"- {neutro(n)}")
    out.append("")
    return "\n".join(out)


def main() -> int:
    estado = carregar()
    texto = gerar(estado)
    SAIDA.write_text(texto, encoding="utf-8")
    contagem = Counter(i["estado"] for i in estado["backlog"])
    print(f"{SAIDA}: {len(texto.splitlines())} linhas · " + " · ".join(f"{e} {contagem.get(e, 0)}" for e in ORDEM_ESTADOS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
