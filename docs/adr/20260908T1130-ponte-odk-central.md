# Ponte opcional com o ODK Central (item L2-07-e-odk-central-ponte)

Estado: aceito. Data: setembro de 2026. Item: `L2-07-e-odk-central-ponte`.
Fontes: docs.getodk.org (central-intro, central-api, central-submissions, central-entities, central-api-odata-
endpoints), lidas em 2026-09-08.

## Contexto

O ODK Central (Apache-2.0) já é o servidor de coleta de campo de muitas equipes, e o ODK Collect (Android) já
está instalado nos aparelhos delas. A plataforma tem formulário próprio (L2-07-b) e terá PWA de campo
(L2-07-a/c/d). A ponte existe para que uma equipe que já usa Collect/Central não precise trocar de aplicativo
para que o dado caia nas camadas da plataforma.

## Decisões

1. **A ponte é uma CONEXÃO, não um serviço novo.** Tipo `odk_central` em `plat.conexao` (L6-02-a): URL validada
   contra SSRF na entrada, credencial cifrada com AES-GCM, saúde no mesmo painel das outras conexões. Nenhuma
   chamada ao Central usa `httpx` direto — tudo passa por `app.conexao.seguranca.buscar_seguro`.

2. **A credencial é um TOKEN do Central, nunca e-mail e senha.** O Central aceita `Authorization: Bearer` tanto
   para sessão (`POST /v1/sessions`) quanto para App User. Guardar e-mail e senha do Central significaria
   guardar uma credencial que pode criar projeto e usuário lá dentro; guardar o token deixa a revogação com
   quem administra o Central. Trocar o token é editar a conexão.

3. **`buscar_seguro` passou a aceitar corpo de envio** (`corpo_envio`), porque publicar formulário é um POST com
   a planilha. Com corpo, um `301/302/303` (que um navegador transformaria em GET) NÃO é seguido: vira
   `redirecionamento_muda_metodo`. Mudar o método de uma escrita autenticada por ordem do destino é decisão de
   quem chama, não do cliente — e é a mesma família do achado G5 (credencial que atravessa origem).

4. **Idempotência pelo `instanceID` do ODK** (`__id` do OData), em `plat.odk_envio` com chave
   `(ponte_id, instance_id)`. Vale para a rota e para o job, porque os dois chamam a mesma função. Envio
   recusado é GRAVADO com o motivo e não volta como novo: some em silêncio, nunca.

5. **Cada envio corre em SAVEPOINT.** Um envio recusado não pode derrubar os outros nem deixar a transação
   abortada: 19 gravados e 1 explicado vale mais que nada gravado.

6. **A escrita é a mesma porta do formulário** (`app.coleta.respostas.responder`): as regras `relevant`,
   `constraint` e `calculation` do documento valem igual para o que vem do Central. Dado do Collect não entra
   por uma porta mais frouxa que o dado da nossa própria tela.

7. **Entities viram lista de escolhas** com as propriedades da entidade como colunas; a cascata é o
   `choice_filter` do L2-07-b sobre essas colunas. Não há tipo novo de lista.

8. **O job age como o dono da ponte**, com os privilégios lidos do banco a cada execução
   (`plat.privilegios_de`). Conta desabilitada ou privilégio retirado interrompe o job na hora.

## Prova: dublê HTTP, não ODK Central de verdade

**O Central não está instalado nesta máquina e não foi possível instalá-lo:** ele se distribui por docker
(central-install), docker não sobe neste servidor e o disco está em 96 % de uso — a pilha do Central (node,
postgres próprio, nginx, enketo) não caberia. A decisão D29 do dono (instalar ou não) segue aberta.

A integração é provada contra um **dublê HTTP da API do Central** (`tests/odk_central_duble.py`), montado sobre
`httpx.MockTransport`, respondendo nos mesmos caminhos, com os mesmos parâmetros e as mesmas formas de resposta
que a documentação publica. Só o DNS e o transporte são trocados nos testes: `validar_url` (SSRF) roda de
verdade, e é por isso que a refutação "aponta a conexão para host interno" continua sendo prova.

**O que o dublê NÃO prova**, e tem de ser refeito contra um Central real antes de qualquer uso com cliente:
- que o Central aceita ESTA planilha (a conversão XLSForm→XForm é feita lá dentro, por pyxform-http);
- os limites reais de paginação e de tamanho de anexo do Central em produção;
- o comportamento de `$expand=*` com repetição aninhada em repetição (o documento do L2-07-b só tem um nível);
- autenticação por App User com escopo de projeto;
- webhook do Central (não implementado: a ponte puxa, não recebe empurrão).

## Consequências

- Uma equipe pode coletar no ODK Collect e ver as feições na plataforma, sem PWA.
- Quem depende disso passa a depender de um servidor de terceiro: a saúde da conexão é o lugar onde essa
  dependência aparece, e a ponte é sempre opcional.
- `plat.conexao` ganhou um tipo no CHECK; a lista do banco e a de `app/limites.py` continuam tendo de mudar
  juntas.
