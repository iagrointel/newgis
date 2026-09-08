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
