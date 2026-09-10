# Consumidores como ativo terminal e endereços sem rede (item L4-20-consumidores-e-enderecos)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L4_CONCEITO.md` (rede de utilidades).

## Contexto

A linha L4 pedia a camada terminal da rede de distribuição: consumidores (unidades consumidoras e
seu consumo) cruzados com endereços do censo, mais o número de consumidores a jusante de cada trecho
de média tensão. O parâmetro de comparação da casa é a camada `end_sem_rede` do esquema de
referência (10.911 endereços), produzida fora da plataforma com o mesmo critério geométrico.

Três restrições pautaram a forma: (1) a origem do dado é um recorte de distribuidora em esquema
FORA do git (vem por `PLAT_REDE_ESQUEMA_COOP` no ambiente da trilha) — nada comitado pode citar o
nome do esquema nem conter campo identificável (nome, cpf, cnpj, telefone, endereço textual); (2) o
consumo por unidade nunca sai pela API — só agregado por transformador ou circuito, com mínimo de 5
unidades (mesma regra de agregação do restante da plataforma); (3) a camada de endereços sem rede é
gerada sobre 182 mil endereços por POST, e o tempo de resposta é parte do contrato (o teste de API
cobra a camada inteira em menos de 300 s).

## Decisão

1. **Seis tabelas `plat.rede_*` com RLS por inquilino e nada identificável**: `rede_trecho`
   (média e baixa tensão, geometria 4674 + coluna gerada `geometria_calc` 31983 para conta
   métrica), `rede_trafo`, `rede_uc` (código, circuito, transformador, situação, grupo de tensão —
   sem `pn_con`/`brr`/`cep`/`cnae`), `rede_uc_consumo` (kWh por ano, alimentando só agregados),
   `rede_endereco` e `rede_endereco_sem_rede` (situação `candidato_ligacao`/`cadastro_faltante`).

2. **Transformador sem geometria vira ponto derivado, com heurística declarada.** O snapshot da
   origem traz `eqtrmt` sem geometria; o ponto do transformador é o início do primeiro trecho de
   baixa tensão que ele alimenta. A tensão nominal fica NULL (`ten_pri`/`ten_sec` não distinguem
   uso real). A heurística está declarada no carregador e no docstring — nunca escondida.

3. **Jusante é árvore de largura por circuito, em Python, não em SQL recursivo.** Nó raiz = maior
   grau do circuito (desempate por coordenada); trecho que fecha ciclo fica fora da árvore com
   `clientes_jusante` NULL e é reportado como malha; extremidades iguais (trecho degenerado) são
   malha sobre si mesmo. A gravação é `UPDATE ... FROM (VALUES ...)` em lotes de 5.000. Teto de
   200 mil trechos e 200 mil nós (`REDE_JUSANTE_*`), com erro 422 acima.

4. **Endereço sem rede = KNN puro nos dois lados, nunca `ST_DWithin` dentro do KNN.** A primeira
   versão (subconsulta correlacionada com `ST_DWithin` + `ORDER BY <->`) não terminava em 600 s;
   o perfil mostrou o planejador escolhendo o índice btree `(tenant_id, nivel, codigo)` no
   `EXISTS` de baixa tensão e varrendo ~13 mil linhas POR ENDEREÇO (≈510 milhões de visitas,
   118 s só ali, sob RLS). A forma final junta dois `LATERAL` de vizinho mais próximo SEM filtro
   de distância (`ORDER BY geometria_calc <-> ... LIMIT 1`, que só o índice espacial serve,
   independente de estatística) e aplica os raios DEPOIS, como filtro: distância da média ≤
   `raio_rede_m` e da baixa > `raio_bt_m`. `LATERAL` em vez de CTE porque comando de modificação
   materializa CTE sempre — 182 mil endereços derramariam em arquivo temporário antes do primeiro
   INSERT. Resultado medido: 5,3 s e 10.914 endereços contra 10.911 da casa (0,03 %), papel de
   aplicação com RLS ativa. A distância de média ≤ raio de baixa (rede no portão) classifica
   `candidato_ligacao`; acima disso, `cadastro_faltante` — critério geométrico, nunca confirmação
   de campo.

5. **Leitura com escopo de token de catálogo e `x-privilegio: proprio` (RLS isola); escrita
   (gerar camada e calcular jusante) exige o privilégio `rede.editar`.** Cinco rotas em
   `/api/rede/consumidores`, com registro triplo (casos cruzados, eventos esperados,
   `openapi_extra`). Limite de página via `Query` com alias `limite` (parâmetro pydantic `Field`
   não serve a parâmetro de consulta — recusado pelo próprio FastAPI).

## Consequências

- O nome do esquema de origem só existe no ambiente da trilha; os testes pulam sem ele e a carga
  (`tests/dados/carga_rede_cooperativa.py`) é idempotente, deduplica código repetido dos dois
  lados da junção e nunca copia campo identificável.
- O cálculo de jusante é O(trechos + nós) em memória do processo; o teto protege o servidor, e a
  malha detectada é devolvida na resposta para o operador julgar (medida, não corrigida).
- Consumo agregado abaixo do mínimo devolve `ene_kwh` NULL com `motivo` — a regra aparece na
  resposta, não só na documentação.
- Medido em `tests/medidas/L4-20-consumidores-e-enderecos.json`: contagem contra a camada de
  referência da casa, tempo de geração e tempo de jusante (44.268 trechos de média).
