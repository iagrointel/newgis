# Handoff — item L6-01-d-ficha-fonte (arquiteto + backend, passagem única)

**Objetivo.** Conferir se a ficha completa de cada fonte do acervo (licença, frescor, sha256,
comando de reexecução, domínio, contagem) já está exposta por `GET /api/acervo/{fonte_id}`; fechar
com evidência se sim, completar o que faltar se não.

## O que fiz

Li `app/acervo/rotas.py`/`modelos.py` (migração 021, item anterior L6-01-a-procedencia-acervo)
antes de escrever qualquer coisa: os 10 campos de procedência da hipótese do item (url, licença,
frescor, data_dado, script_gerador, sha256, método, confiança, limites, próxima_verificação) **já
estavam todos expostos** — nada para completar aí. `limites` já É "o que este dado não sustenta"
em conteúdo real (lido em `acervo.fonte.limites`: "só fluxo, sem estoque RAIS", "0 vendidos lidos;
só o tempo resolve") — não dupliquei sob outro nome.

O gap real, contra a hipótese COMPLETA do item (não só a lista curta do pedido): faltava
"endpoints confirmados e vivos (`acervo.endpoint`)" e "completude x/10 exibida" (só existia como
número cru). Somei:

- `plat.acervo_endpoint` (migração 040): view sobre `acervo.endpoint`, mesma regra D17 (join com
  `acervo.fonte`, só licença escrita), `vivo = confirmado AND http = '200'` (definição que a casa
  já usa fora da plataforma).
- `AcervoFicha.endpoints`/`endpoints_total`/`endpoints_confirmados_vivos` — total contado à parte
  da lista (que trunca em 200), nunca mentindo por truncamento.
- `AcervoFicha.completude_texto` ("4,5/10"), `None` (nunca "0/10") quando falta base de cálculo.

## Evidência (comando + saída literal)

Migração numerada ao vivo — três tentativas por colisão com trilhas concorrentes na mesma janela
(034/035 → 036/037 → 040/041, `ls db/migracoes` + `SELECT nome FROM plat.versao_migracao`
reconferidos a cada colisão). Aplicada manualmente (`db/migrar.sh` não completava por causa de
`030_conexao.sql` DIVERGENTE de outra trilha, que para o script no primeiro item da lista):

```
$ sudo -u postgres psql -d iagro_sat -c "SELECT nome FROM plat.versao_migracao WHERE nome IN ('040_acervo_endpoint');"
        nome
---------------------
 040_acervo_endpoint
```

Suíte (sob `flock laco/.pytest.lock`):
```
tests/api/test_acervo.py ..............                                   [100%]
```
14 testes, incluindo os dois novos:
- `test_ficha_confere_20_fontes_campo_a_campo_incluindo_endpoints_e_completude`: os 10 campos +
  endpoints_total/confirmados_vivos + completude_texto para 20 fontes licenciadas, um a um contra
  `acervo.fonte`/`acervo.endpoint` (nunca contra número digitado).
- `test_campo_ausente_na_ficha_nunca_e_fabricado`: fonte com `sha256 IS NULL` (33 de 68 licenciadas
  medido 06/09/2026) devolve `None`, nunca `''`.

`make openapi` roda sem erro; **`docs/openapi.json` NÃO foi incluído no commit** — regenerá-lo
agora capturava rotas de OUTRAS trilhas concorrentes ainda não commitadas (787 inserções contra 13
esperadas); commitar isso teria deixado o repositório inconsistente para quem só puxasse este
commit. Fica para quem fizer a integração final do turno regenerar de novo.

## Riscos

Nenhum dado do acervo foi copiado ou alterado; `acervo.*` permanece só-leitura pela plataforma
(GRANT SELECT apenas). A tabela `plat.acervo_endpoint` é uma VIEW, sem estado próprio — nada a
migrar/reverter além de `DROP VIEW` se um dia for descontinuada.

## Pendências (por que o item ficou `parcial`, não `entregue`)

- **Sem tela** — `GET /api/acervo`/`GET /api/acervo/{fonte_id}` só existem como API; a navegação
  (L6-01-c) não foi construída nesta passagem (papel `frontend` do item não foi executado —
  esta sessão rodou só arquiteto+backend, por pedido explícito de quem chamou).
- **Sem e2e no navegador** (o portão do item pede isso) — decorre diretamente da ausência de tela.
- **Sem adversário independente do turno** — mesma situação do item-pai (L6-01-a-procedencia-acervo,
  já registrada como pendência lá).

## Para o próximo papel

Frontend: construir L6-01-c (lista + ficha) consumindo os campos já prontos, incluindo
`endpoints`/`completude_texto`/`risco_pii` (este último do item irmão L6-01-f-lgpd, já na mesma
resposta). Regra de exibição a seguir: campo `None` vira o texto "não registrado" na tela — a API
nunca fabrica isso, é responsabilidade de quem exibe.

## Resumo (6 linhas)

Os 10 campos de procedência já estavam prontos desde o item anterior — nada duplicado. Somei
endpoints confirmados/vivos (`plat.acervo_endpoint`, migração 040) e completude "x/10" por extenso.
Testado campo a campo contra `acervo.fonte`/`acervo.endpoint` para 20 fontes, com teste dedicado a
provar que campo ausente nunca é fabricado. `docs/openapi.json` deliberadamente fora do commit
(contaminado por trilhas concorrentes). Estado: `parcial` — falta tela/e2e (L6-01-c) e adversário
independente; mecanismo de dados e API estão completos e evidenciados.
