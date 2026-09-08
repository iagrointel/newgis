# Decomposição profunda do backlog — brief comum (05/09/2026)

Ordem do dono: "o backlog real passa de 200 itens; cave o conceito agora para não refazer depois; sem limite de tokens
nem de tempo". Você recebe UMA linha do produto e devolve DOIS arquivos:

1. `laco/decomposicao/<linha>.json` — lista de itens no MESMO esquema do backlog em `laco/estado.json`:
   {"id","linha","prioridade"(1-5),"estado":"pendente","dependencias":[ids],"hipotese","portao_de_pronto","refutacao",
    "papeis":[...],"tamanho":"P|M|G","tentativas":0,"turno":null,"bloqueio":null,"pai": id do item existente que ele detalha ou null}
   - ids no padrão `<Lx>-<nn>-<slug>` continuando a numeração da linha (os existentes ficam; você acrescenta e pode
     propor `-a/-b` como filhos de um existente via campo `pai`); dependências podem apontar para ids de OUTRAS linhas
     que já existem no estado.json ou que você declara em `dependencias_externas_propostas`.
   - PORTÃO DE PRONTO = cláusulas verificáveis por comando/teste/e2e/medição, nunca adjetivo. REFUTAÇÃO = o que um
     adversário faz para derrubar. Um item = 1 a 3 dias de trabalho de uma pessoa (tamanho P/M/G).
   - Cubra: TUDO que o ArcGIS Enterprise 11.4 (Portal, Server, Data Store, Image Server, Notebook Server, GeoEvent/
     Velocity, Workflow Manager, Utility Network, Parcel Fabric, Indoors, Knowledge, Insights, Hub/Sites, Dashboards,
     Experience Builder, Instant Apps, StoryMaps, Survey123, Field Maps, QuickCapture, Pro publishing) e o GeoServer/
     QGIS Server oferecem NA SUA LINHA — doc oficial datada, URL testada por HTTP — mais o que a spec da casa
     (`/home/dev/plataforma/DOC.md` seções 17-22) e os ativos existentes (fgr/sig, plataforma/pipeline, cbre motor,
     tracado-lt motor, geoapp, BDGD, acervo.*) já dão de graça. Marque em cada item `origem`: "esri", "geoserver",
     "casa", "spec", "usuario".
2. `laco/decomposicao/<linha>_CONCEITO.md` — as DECISÕES DE CONCEITO da linha que, se erradas, obrigam a refazer
   (modelo de dado, identificadores, formato de estilo, linguagem de expressão, modelo de job, contrato de API,
   armazenamento, CRS, versionamento, isolamento por inquilino, extensibilidade). Para cada decisão: opções, o que
   custa mudar depois, recomendação com motivo medido ou com doc oficial, e o que ela obriga nas outras linhas.

Regras: só ler (nunca editar) /home/dev/fgr, /home/dev/cbre, /home/dev/geoapp, /home/dev/rs-coop; não instalar nada;
sem downloads; disco a 98 %; sem emoji; português; sem placeholder; sem nome de cliente/parceiro/piloto no que escrever
(diga "SIG de teste interno", "motor logístico", "motor de LT"); nunca preço Esri. Regras do laço em
/home/dev/.claude/skills/plataforma-enterprise/SKILL.md. Estado atual (57 itens) em /home/dev/plataforma/laco/estado.json.
Meta de profundidade: a sua linha sozinha deve render entre 25 e 60 itens. Termine com resumo de 10 linhas.
