# Ataque G5 — laudo do adversário independente (turno 3)

Adversário: sessão isolada, base própria `plat_tadv5` (nunca o `plat` de produção). Nada consertado —
só medido e derrubado. Reproduções abaixo rodam do `/home/dev/plataforma/enterprise` com
`set -a; source /home/dev/plataforma/laco/var/trilha/adv5.env; set +a`.

## Veredito item a item

| item | veredito |
|---|---|
| L2-01-a-basemap-local-pmtiles | NÃO REFUTADO (parte mecânica) · FRONTEIRA no e2e WebGL |
| L2-04-b-parser-where-ast | NÃO REFUTADO |
| L2-11-c-rota-matriz-isocrona | NÃO REFUTADO na fatia entregue · FRONTEIRA grande (item é `parcial`) |
| L5-05-documento-versoes | NÃO REFUTADO |
| **L6-02-a-modelo-conexao-e-seguranca** | **REFUTADO (segurança real)** |
| L6-01-a-procedencia-acervo | NÃO REFUTADO |
| L6-01-a-registro | NÃO REFUTADO · FRONTEIRA (ramo fantasma nunca exercido em dado real) |
| L6-02-l-saude | NÃO REFUTADO no backend · FRONTEIRA no aviso visível do mapa (e2e) |
| L6-05-proveniencia-camada-externa | NÃO REFUTADO · FRONTEIRA na legenda (e2e) |

1 item derrubado (L6-02-a), achado de SEGURANÇA REAL.

## Suposições transversais (ataquei primeiro)

1. **"Toda URL de terceiro passa por um único caminho de busca auditado contra SSRF" — HELD como isolamento,
   mas CAI como proteção da credencial.** `app/conexao/seguranca.buscar_seguro` é de fato o único caminho
   (testar, job de saúde, sonda de proveniência L6-05 — todos importam dele). Só que esse caminho único
   reenvia os cabeçalhos do chamador (inclusive `Authorization: Bearer <credencial decifrada>`) em TODO
   salto de redirecionamento, cross-origin inclusive. Um defeito, dois chamadores credenciados vazam
   (ver L6-02-a). É o caso de "uma suposição cair e derrubar vários pontos de uma vez".
2. **"Contagem exata, nunca `reltuples`" — HELD.** `plat.acervo_camada.linhas_exatas` vem de `COUNT(*)` sob
   `statement_timeout` de 25 s; `linhas_estimadas` (reltuples) é coluna à parte; linha só vira `exposta`
   após COUNT concluir. Medido em produção (só leitura): 0 linhas expostas com `linhas_exatas` nulo, 0 com
   `linhas_exatas=0 AND est>0`.
3. **"Quando o dado falta, campo `None`, nunca default" — HELD.** L6-05 lê licença do serviço ou `None`;
   procedência-acervo filtra fonte sem licença (68/376); basemap tem sha256 real batendo com o arquivo.
4. **"Sob orçamento de tempo, trunca com estado honesto" — HELD, com efeito colateral.** `acervo_sync` marca
   `nao_processada_no_prazo` ao estourar 270 s; nunca reporta sucesso falso. Efeito: o ramo de detecção de
   fantasma (`fantasmas`) NUNCA disparou em dado real — `prodes_yearly_all_indexed` (fantasma conhecido)
   está `bloqueada/nao_processada_no_prazo`, excluído por outra razão que não o ramo de fantasma.
5. **"Isolamento por inquilino (RLS)" — HELD (não atacado a fundo).** RLS presente em `plat.item_versao`
   (tenant_id), `plat.conexao`, item. Não fiz cruzamento A×B novo; confio no que a suíte já cobre.

## Achados por item (comando + saída real)

### L6-02-a-modelo-conexao-e-seguranca — REFUTADO (segurança)

Os 8 casos do portão e a defesa de rebinding AGUENTAM: os 26 testes de `tests/unit/test_conexao_seguranca.py`
passam (`26 passed`), incluindo redirect→interno recusado no salto e conexão pinada no IP já validado
(`connect_tcp` recebe o IP pinado, nunca re-resolve o host). Provei o pin com sonda offline: com
`getaddrinfo` devolvendo IP público na 1ª chamada e `127.0.0.1` depois, `socket.create_connection` foi
chamado com `('8.8.8.8', 80)` — PINNED-OK. IPv4-mapeado (`::ffff:127.0.0.1`), CGNAT e NAT64 caem como
`privado/reservado` no Python 3.12.3.

ACHADO: `buscar_seguro` reenvia `Authorization` em salto de redirect para um HOST de outra origem.
Prova determinística e offline (monkeypatch de `getaddrinfo` e `cliente_pinado`; `host-a.teste` →
`8.8.8.8`, `host-b.teste` → `9.9.9.9`, ambos públicos; A responde 302 → B):
```
hop host=host-a.teste   Authorization='Bearer CREDENCIAL-DA-CASA'
hop host=host-b.teste   Authorization='Bearer CREDENCIAL-DA-CASA'
CROSS-HOST LEAK
```
`requests`/`httpx` retiram `Authorization` quando o host muda; aqui não há retirada nenhuma.
`/api/conexoes/{id}/testar` (app/conexao/rotas.py) e o job `conexoes.saude_verificar`
(app/conexao/tarefas.py) decifram a credencial e a passam em `cabecalhos={"Authorization": ...}`; o laço de
redirect de `buscar_seguro` repassa `headers=cabecalhos or {}` em cada salto sem retirar a credencial ao
mudar de origem (requests/httpx retiram, por padrão). Um host público configurado com open-redirect, ou um
destino que responda 302 para fora, exfiltra o Bearer da casa. O portão diz "credencial nunca aparece em
resposta de API nem em log" — verdade —, mas o MODELO de segurança da conexão (hipótese do item:
"redirecionamento revalidado", credencial protegida) falha por um vetor que o portão não enumerou.
Teste-prova: `tests/adversario/test_g5_adversario.py::test_credencial_nao_vaza_em_redirect_cross_origin`
(`xfail(strict=True)`, determinístico offline; hoje `1 xfailed`; commit e62f3db9).
Conserto sugerido (não aplicado): retirar `Authorization`/cookies quando o `Location` muda de
esquema+host+porta.

### L2-04-b-parser-where-ast — NÃO REFUTADO
`app.consulta.where_ast.compilar_where` com lista branca `{"nome":"c.nome_cidade","pop":"c.populacao"}`.
`; DROP`, `-- `, `/* */`, `UNION ... FROM x.y`, `)` sobrando e campo fora da lista: TODOS recusados
(`caractere_invalido`/`sintaxe_invalida`/`campo_nao_permitido`). Valor com aspa escapada
(`'O''Brien'`, `'a''; DELETE...'`) vira UM parâmetro `%s`, nunca texto de SQL. `IN (1,2,3)` → `%s,%s,%s`.
Nenhum caminho de texto do usuário chega ao SQL sem parâmetro.

### L6-01-a-registro — NÃO REFUTADO
Só leitura em produção: `farma.djen_pub_termo` não tem coluna de geometria (não é candidata) → AUSENTE do
registro; `public.prodes_yearly_all_indexed` → `bloqueada` (não exposta). Nenhuma linha exposta é fantasma
(`estado='exposta' AND linhas_exatas=0 AND linhas_estimadas>0` = 0). Coluna de contagem é `COUNT(*)`, não
reltuples. FRONTEIRA/observação: o ramo `tabela_fantasma_estimativa_sem_dado` tem `fantasmas=0` em todas as
execuções — prodes é excluído por `nao_processada_no_prazo`, não pelo ramo de fantasma; o ramo de detecção
específico nunca foi exercido por dado real. Além disso o script atinge o teto de 270 s e deixa 81 tabelas
`nao_processada_no_prazo`: cumpre "≤ 5 min" truncando, não processando o universo.

### L5-05-documento-versoes — NÃO REFUTADO
`documento.validar_grafo` (função pura): nó com id repetido → `422 grafo_invalido/id_duplicado`; ligação
para id inexistente → `referencia_pendente`; id não-ULID → `ulid`; grafo válido → aceito.
`plat.item_versao` é append-only (`REVOKE INSERT,UPDATE,DELETE ... FROM plat_app`; gatilho só INSERT).
Adulterar `corpo` direto no banco é pego por `GET /api/itens/{id}/integridade`, que recomputa
`sha256 = encode(digest(corpo::text,'sha256'),'hex')` e lista `versoes_corrompidas`. O `/saude` NÃO checa
integridade (só banco/migrações/fila), mas o portão pede "/saude OU a tela" — o endpoint de integridade
cumpre a segunda opção.

### L6-01-a-procedencia-acervo — NÃO REFUTADO
Só leitura: `acervo.fonte`=376, com licença escrita=68; `plat.acervo_ficha`=68 linhas, 0 sem licença.
A ficha preenche procedência a partir de `acervo.*` e o filtro D17 (só fonte com licença) está na view.

### L6-05-proveniencia-camada-externa — NÃO REFUTADO
`app/conexao/proveniencia.py`: licença vem de AccessConstraints (WMS/WMTS/WFS via defusedxml),
copyrightText (ArcGIS), ou `license` (STAC/OGC), senão `None` — nunca um default. `confianca='declarado'`
só quando há licença/fonte lida. FRONTEIRA: "atribuição aparece na legenda" é e2e de mapa (L6-02-b, que
desenha a camada, ainda não existe).

### L2-01-a-basemap-local-pmtiles — NÃO REFUTADO (parte mecânica)
`web/dados/basemap/guarulhos.pmtiles`: 19.181.534 bytes (≤ 50 MB), magic `PMTiles`, sha256
`86aa490c...a475` bate com `PROVENIENCIA.md`; nginx serve com `gzip off` (deploy/nginx.conf); ODbL/bbox/
ferramenta declarados. FRONTEIRA: canvas WebGL desenhando (readPixels > 50 cores), 0 erro de console e
reação dos controles são e2e de navegador — não executável aqui (chrome headless quebra nesta máquina).

### L2-11-c-rota-matriz-isocrona — NÃO REFUTADO na fatia entregue (item `parcial`)
Entregue: OSRM isolado `plat-osrm-guarulhos` (contêiner ativo) + `/api/rota`, `/api/matriz`, `/api/isocrona`.
FRONTEIRA/gaps abertos (coerentes com `parcial`, declarados no handoff): pgRouting NÃO instalado
(`pg_extension` só tem postgis 3.6.3 — `pgr_version()` falharia); teto de matriz é 625
(`ROTA_MATRIZ_MAX_PADRAO`), abaixo do 1.000×1.000 do portão; isócrona vai a 180 min, não os 6 h da
refutação; 5.000×5.000 e comparação com networkx não construídos. Não refutei porque não há alegação de
que essas partes estejam prontas.

### L6-02-l-saude — NÃO REFUTADO no backend
`plat.conexao_saude_candidatas`, `plat.conexao_saude_registrar`, `plat.v_conexao_saude` e
`plat.conexao_saude_historico` existem; o job testa não-testadas + vencidas há > 30 min; URL inválida →
`buscar_seguro.ok=False` → saúde vermelha em um ciclo. FRONTEIRA: "aviso visível no mapa quando a fixture
cai" é e2e Playwright — não executável (sem navegador).

## Fronteira honesta (o que NÃO provei)
- Nenhum e2e de navegador (WebGL do basemap, aviso de mapa da saúde, legenda de L6-05): sem navegador nesta
  máquina.
- L2-11-c em escala (1.000×1.000, 5.000×5.000, 6 h) e pgRouting×networkx: infraestrutura ausente e item
  `parcial`.
- RLS A×B não recruzado neste laço (confio na cobertura existente).
- A exfiltração de credencial exige que o host configurado redirecione para outra origem (open-redirect ou
  302 deliberado); não é auto-explorável sem esse destino — mas o reenvio cross-host é incondicional no
  código, provado offline. Não montei o cenário end-to-end pela rota HTTP (`/testar`) com um inquilino real,
  só no nível de `buscar_seguro`, que é onde os dois chamadores (rota e job) entram.
