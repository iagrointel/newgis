# ADR 20260906T1747 — conserto do grupo G4: dono/privilégio de objeto, teto de cota da plataforma, expurgo de
rastro com filtro de inquilino, contrato comitado conferido

Contexto: ataque adversarial independente (`laco/handoffs/T3/ataque-g4-ADVERSARIO.md`, ramo `wt/adv4`,
commit `e1ff144`) refutou seis itens do grupo G4 com 24 achados. Este ADR cobre as cinco decisões dos
achados atribuídos a esta trilha (`wt/g4fix`): G4-01, G4-04, G4-05, G4-06, G4-07, G4-08, G4-09 e G4-10. Os
demais achados (G4-02/03/11 a 24) pertencem a outros itens/trilhas e não são tocados aqui.

## D1. Objeto genérico (`plat.arquivo`) tem DONO; quem não é dono precisa de privilégio administrativo

`GET`/`DELETE /api/arquivos/{sha256}` exigiam só `autenticado()` — nenhuma checagem de posse nem de
privilégio (G4-06, G4-07). Um perfil `visualizador` lia e apagava o logotipo da organização, que outro
usuário havia gravado. A regra adotada é a mesma que o catálogo já usa para item de outro membro: **o dono
do objeto (`plat.arquivo.criado_por`) faz o que quiser com o que é dele; quem não é dono precisa do
privilégio administrativo do verbo** (`conteudo.ver_tudo` para ler, `conteudo.apagar_tudo` para apagar).
Implementado em `app/rotas_arquivos.py::_exigir_dono_ou_privilegio`, chamado nas duas rotas depois de
resolver a linha. `criado_por` já existia em `plat.arquivo`; o que faltava era a checagem na rota, não a
coluna.

## D2. Apagar objeto é SECURITY DEFINER com o inquilino como ARGUMENTO, nunca GUC (G4-09)

`objetos.apagar()` é chamado fora de qualquer sessão HTTP (rota, mas também tarefas do worker e
destruidores do catálogo), então um `UPDATE` direto em `plat.arquivo` caía na política RLS `p_arquivo`
(`tenant_id = plat.tenant_atual()`), que sem GUC de sessão casava zero linhas — o `UPDATE` "funcionava"
(sem erro) e não mudava nada. A linha ficava viva apontando para um objeto já apagado no Garage, e a
varredura de órfãos (`GET /api/arquivos/_varredura`) acusava **toda exclusão legítima** como "sem objeto",
o que tornava o sinal inútil. Conserto: `plat.arquivo_apagado_marcar(p_tenant_id, p_chave)`, `SECURITY
DEFINER`, resolve o inquilino pelo SLUG da própria chave (mesmo caminho que já autoriza a leitura/escrita
do bucket) e marca `apagado_em` com o inquilino como parâmetro explícito, nunca lido de `current_setting`.
Mesmo padrão que `plat.arquivo_bucket_resolver` já usava — este ADR generaliza o padrão: **função de
manutenção chamada fora de sessão HTTP nunca depende de GUC de tenant; o inquilino é sempre argumento
explícito**, e quem chama essa função continua sendo só `plat_app`/`plat_worker` via `GRANT` nomeado.

## D3. Cada apagar/enviar de objeto grava evento (parte de G4-08, medido junto)

`DELETE /api/arquivos/{sha256}` não gravava nenhum evento (contador de `/api/eventos` não mudava depois de
um 204). Como a cobertura declarada aceitava lista vazia como "sem evento" para essa rota, o guardião
aprovava a destruição silenciosa. Conserto: `registrar_evento(..., "arquivos/apagar", ...)` depois do
apagar físico e de marcar a linha, e `arquivos/enviar` no fim do envio multipart — os dois tipos novos
entraram no vocabulário (`plat.evento_tipo`) pela migração deste conserto.

## D4. Teto de cota é decisão da PLATAFORMA; o inquilino só escolhe abaixo do próprio teto (G4-04, G4-05)

`OrgEntrada.cota_bytes`/`cota_usuarios` tinham só piso (`ge`); a rota é do admin do INQUILINO
(`PUT /api/org`), então o próprio inquilino de demonstração conseguia levar a cota a `9×10¹⁸` bytes e
`10⁹` usuários com `200 OK`, e o valor chegava ao bucket do Garage. Decisão: duas colunas novas em
`plat.tenant` — `cota_bytes_teto` (padrão 20 GiB) e `cota_usuarios_teto` (padrão 2000) — que só a
plataforma grava, por `PUT /api/plataforma/inquilinos/{id}/cotas` (superadmin,
`plat.tenant_cotas_teto_definir`, que por sua vez respeita um teto ABSOLUTO da instalação: 1 TiB / 100.000
usuários, `app/limites.py::ORG_COTA_BYTES_TETO_MAX`/`ORG_COTA_USUARIOS_TETO_MAX`). A defesa é em três
camadas independentes, cada uma suficiente sozinha:

1. **Esquema** — `OrgEntrada` ganhou `le=ORG_COTA_BYTES_TETO_MAX`/`le=ORG_COTA_USUARIOS_TETO_MAX`: um
   pedido absurdo (`9×10¹⁸`) nem chega a validar contra o teto do inquilino, cai em `422 validacao`.
2. **Rota** — `org_gravar` lê o teto vigente do inquilino e recusa com `422 cota_acima_do_teto` (e o campo
   e o teto no corpo do erro) antes de gravar.
3. **Banco** — gatilho `plat.tenant_cota_guarda` (BEFORE UPDATE em `plat.tenant`) reprova
   `cota_bytes > cota_bytes_teto`/pedido de usuários acima do teto mesmo por `UPDATE` direto via SQL, e
   reprova qualquer mudança do PRÓPRIO teto que não venha de `plat.tenant_cotas_teto_definir` (checagem por
   `current_setting('plat.teto_definir')`, ligado só dentro daquela função).

Rota nova, não item novo: o console de plataforma (`app/auth/rotas_plataforma.py`) já existia para
inquilinos (criar/suspender/reativar); `GET`/`PUT /inquilinos/{id}/cotas` seguem o mesmo padrão
(`superadmin=True, so_sessao=True`, `plat.tenant_cotas`/`plat.tenant_cotas_teto_definir`, ambas
`SECURITY DEFINER` que conferem a sessão de superadmin por dentro, sem depender de RLS).

## D5. Expurgo do rastro (`evento`/`log_acesso`) valida o argumento e não é poder da aplicação (G4-10)

`plat.evento_expurgar(int)`/`log_expurgar(int)` eram `SECURITY DEFINER`, sem validar o argumento e com
`EXECUTE` para `plat_app` (herdado do `GRANT` em bloco da migração 001). Com mês negativo o "limite" ia
para o futuro e a condição de corte alcançava a partição do mês CORRENTE — `evento_expurgar(-1)` a
derrubava (`DROP TABLE`) para **todos os inquilinos**. Nenhuma rota HTTP chama essa função hoje (varrido em
`app/`), então não é um caminho de ataque pronto; é a defesa em profundidade ausente — qualquer futura
injeção de SQL, ou um novo endpoint mal desenhado, teria o poder de apagar toda a auditoria da instalação.
Decisão:

1. **Validar o argumento**: `p_meses` precisa ser inteiro entre 1 e 1200; e o limite calculado nunca pode
   alcançar o mês corrente (`RAISE EXCEPTION limite_no_presente`) — a proteção não é só "número positivo", é
   "nunca corta o presente", que é a propriedade que o portão realmente quer.
2. **Tirar o poder de `plat_app`/`plat_worker`**: `REVOKE EXECUTE` das duas funções globais de ambos os
   papéis da aplicação. **Nenhum código HTTP nem job da fila expurga rastro** — quem precisa fazer retenção
   roda como `postgres`/dono do banco, fora do papel da aplicação.
3. **Expurgo por inquilino é caminho separado**: `evento_expurgar_inquilino(tenant_id, meses)` e
   `log_expurgar_inquilino(tenant_id, meses)`, também validadas, apagam LINHA (nunca `DROP TABLE`) e só do
   `tenant_id` pedido — o rastro de um inquilino nunca alcança o de outro. `EXECUTE` concedido só a
   `plat_worker` (para um periódico de retenção futuro), nunca a `plat_app`. Hoje nenhum periódico chama
   essas funções (G4-11, item L0-10, fora desta trilha); a peça que falta é o cron do worker, não a
   segurança da função.

Padrão geral: **poder de apagar em massa (partição inteira) nunca é do papel da aplicação**; poder de
apagar em escopo de UM inquilino pode ser do worker, nunca da API síncrona; e toda função de expurgo valida
o argumento antes de calcular o corte, porque "número entre parênteses" é entrada de usuário mesmo quando
quem chama é um operador.

## D6. O contrato comitado (`docs/openapi.json`) deixa de ser um retrato que ninguém confere (G4-01)

Dois guardiões da suíte leem o arquivo comitado, não o app vivo: a cobertura de evento
(`tests/api/test_eventos.py`) e a varredura cruzada de isolamento (`tests/api/test_cruzado.py`). O arquivo
estava 28 rotas atrás porque `make openapi` só ESCREVE o arquivo — nada no `check` conferia se alguém
rodou o alvo depois de adicionar uma rota. Rota nova nascia fora dos dois guardiões ao mesmo tempo.
Decisão: `docs/openapi.json` foi regerado (`make openapi`) e `tests/api/test_openapi_contrato.py` entrou na
suíte comum (`make teste`, sem marca `lento`) comparando o CONJUNTO de rotas (método, caminho) do arquivo
contra `app.openapi()` vivo — não byte a byte, porque ordem de chave e formatação dependem da versão de
FastAPI/pydantic da máquina, o que seria ruído. Diverge em qualquer direção (rota nova sem regenerar, ou
rota removida sem regenerar) e a suíte reprova nomeando a rota, apontando `make openapi`. Isso fecha o
buraco pela raiz: não conserta a cobertura de evento em si (G4-02/03, fora desta trilha), mas garante que a
PRÓXIMA rota que qualquer item adicionar não escape dos dois guardiões por o arquivo estar desatualizado.

## O que fica de fora, por quê

G4-02/03 (cobertura de evento medida contra o app vivo, e contra lista vazia), G4-11/12/13 (retenção
periódica, exportação, tela de auditoria), G4-14/15/16 (rate limit, teste de contrato, `Retry-After`),
G4-17/18 (blocos de página inicial, banner), G4-19 (`/saude` sem Garage obrigatório), G4-20 (CSW/editor de
metadado), G4-21/22 (tokens de design), G4-23 (42501 disfarçado de 403 de inquilino) e G4-24 (`executemany`
não reescreve o schema da trilha) pertencem a outros itens ou são transversais a outras trilhas — nenhum
foi tocado aqui, por instrução explícita de escopo.
