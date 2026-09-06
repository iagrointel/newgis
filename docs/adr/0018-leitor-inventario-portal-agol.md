# ADR 0018 — Leitor de inventário de Portal/AGOL (item L2-08-a-leitor-portal-inventario)

Estado: aceito (esri + backend + frontend, turno T3, setembro de 2026). Base: `laco/estado.json`
(item L2-08-a, linha L2-08 migração AGOL) e ADR 0012 (modelo de conexão externa e defesa de SSRF).

## Contexto

A linha L2-08 é a ferramenta de migração: dado o Portal for ArcGIS ou o ArcGIS Online de um cliente, clonar
o que entra e dizer com todas as letras o que não entra. Este item é a PRIMEIRA metade, e só ela: **ler**.
Nada é escrito no portal do cliente, nada é convertido ainda. A clonagem de camada hospedada é o L2-08-b, a
conversão de web map é o L2-08-c e o relatório de migração com exportação reversa é o L2-08-d.

Ler antes de converter não é cerimônia: sem o retrato do portal não há como orçar a migração, escolher a
ordem, nem mostrar ao cliente o que fica de fora. E o retrato precisa ser um DADO gravado, não uma tela que
consulta o portal ao vivo — o portal do cliente tem limite de uso, cai, muda de token e some no meio.

## Decisões

### 1. O inventário é um job, e o job é RETOMÁVEL por dado, não por memória

`plat.migracao_inventario.retomada` guarda a fase e a página (`{"fase": "itens", "start": 601}`), e cada
item, grupo e usuário tem chave única por inventário. Uma tentativa nova pula o que já está gravado sem
emitir pedido HTTP e continua a busca da página onde parou. Medido contra o servidor de teste: um corte de
rede no 30º pedido custou 177 pedidos na retomada, contra 203 do inventário inteiro.

A alternativa — guardar o progresso na memória do processo — perde tudo quando o worker morre, que é
exatamente o caso que o portão exige provar. A outra alternativa — refazer do zero a cada tentativa — num
portal de 10 mil itens transforma uma queda de rede em horas de releitura e em pressão sobre o limite de uso
do cliente.

### 2. Erro de rede NÃO é falha do inventário

`ErroRede` (corte, tempo esgotado, 5xx, 429 insistente) deixa o inventário em `rodando` e sobe para a fila
tentar de novo. Só erro que repetir não conserta (`nao_e_portal`, `credencial_recusada`, `url_insegura`)
vira `FalhaDefinitiva` e marca `falhou`. Sem essa separação, um soluço de rede marcaria como fracassada uma
leitura de 9.900 itens de 10 mil.

### 3. Token em CABEÇALHO (`X-Esri-Authorization`), nunca em `?token=`

A API do Portal aceita as duas formas. A query é a mais comum nos exemplos da Esri e é a errada aqui: a URL
aparece em log de job, em log de acesso do servidor, em mensagem de erro e em relatório de proveniência. Com
o cabeçalho, "o token nunca aparece em log" deixa de ser um filtro de texto que alguém pode esquecer de
aplicar e passa a ser uma propriedade do transporte. O teste confere as duas pontas: nenhuma coluna de texto
de nenhuma tabela do schema contém o token, e o servidor de teste registra que nenhum pedido trouxe `token`
na query.

### 4. LGPD por ESQUEMA: a tabela de usuário não tem onde guardar dado pessoal

`plat.migracao_usuario` tem `login`, `papel`, `nivel` e `desativado`. Não tem e-mail, nome, telefone nem
descrição — e o portal DEVOLVE esses campos. A ausência é estrutural: não existe coluna onde caberia. Uma
regra de aplicação ("não grave o e-mail") depende de todo código futuro lembrar dela; uma coluna que não
existe não depende de ninguém. O mesmo vale para membro de grupo, que é gravado como lista de logins.

### 5. Classificação prévia: `desconhecido` existe, e é a resposta certa mais vezes do que parece

A tabela de `app/migracao/classificacao.py` mapeia tipo Esri → `migra` / `migra_parcial` / `nao_migra`, com
motivo escrito em toda linha. Tipo fora da tabela devolve `desconhecido`, nunca `nao_migra`: o catálogo de
tipos da Esri cresce a cada versão, e dizer "não migra" sobre um tipo que ninguém leu é afirmar mais do que
se mediu. `typeKeywords` manda no `type` em dois casos medidos: "Hosted Service" separa a camada hospedada
(que a L2-08-b clona) do serviço publicado no ArcGIS Server do cliente (que entra só como referência), e
"Utility Network"/"Parcel Fabric" derrubam para `nao_migra` qualquer serviço.

### 6. Um pedido por item, não sete

`item/data`, `item/resources` e `relatedItems` só são pedidos para os tipos em que existem e interessam
(documento e serviço). Perguntar os três para todo item multiplicaria por sete o tempo e a pressão sobre o
limite de uso do portal do cliente, sem trazer nada para um CSV ou um pacote do ArcGIS Pro. Medido: 10 mil
itens simples custaram 107 pedidos e 8,4 s.

### 7. Conserto pós-adversário (turno 3): a credencial só vai para a origem do portal

O adversário independente (`laco/handoffs/T3/ataque-L4-portal-ADVERSARIO.md`, B1/B1b) mediu que
`ClientePortal` mandava `X-Esri-Authorization` para QUALQUER host presente no campo `url` de um item — e
que o cabeçalho acompanhava um 302 até um terceiro host. O campo `url` de um item é escrito por qualquer
membro da organização do cliente ao registrar um item; a credencial do inventário é de administrador. O
conserto (`ClientePortal._cabecalhos(alvo)`) só inclui o token quando `alvo` tem a mesma origem
(esquema+host+porta) de `self.base`, recalculado a cada salto de redirecionamento — nunca comparado ao
salto anterior, sempre à origem configurada. A função `seguranca._mesma_origem_de_confianca` foi copiada
(mesma lógica) do conserto equivalente que o item de conexão externa fez para o mesmo problema em
`buscar_seguro`; não foi reinventada. Efeito colateral aceito e documentado: um portal enterprise com
serviços federados em HOST DIFERENTE do portal (comum em AGOL, onde o portal é `org.maps.arcgis.com` e o
serviço hospedado vive em `servicesN.arcgis.com`) não recebe token do inventário — o serviço só é lido se
for público. É o padrão seguro por omissão; ampliar para uma lista de hosts de confiança do portal
(equivalente ao "trusted servers" da Esri) fica para quando D20 (credencial de um Portal real) destravar a
prova. Os achados B2-B7 (item malformado, página grande, retomada que perde item, injeção de fórmula no
CSV, `size:-1`, inventário órfão de editor sem privilégio) estão descritos e consertados no handoff
`laco/handoffs/T3/L2-08-a-CONSERTO.md`.

## O que fica de fora deste item

- Prova contra Portal real: pendente da decisão D20 do dono. `tests/migracao/PORTAL_DE_TESTE.md` registra a
  pendência, o que a prova contra o servidor de teste sustenta e o que ela não sustenta.
- Clonagem (L2-08-b), conversão de web map e estilo (L2-08-c), relatório de migração completo com exportação
  reversa e XLSForm (L2-08-d). A tabela de classificação deste item é o insumo do L2-08-d, não o substituto.
- Renovação automática de token expirado no meio de um inventário longo: hoje o token expirado vira
  `credencial_recusada` e o inventário para com mensagem clara.
