-- item L2-04-a-leitor-rls-martin — achado por dois workers, confirmado via job_log: o expurgo
-- (app/catalogo/destruidores.py::_camada_vetorial) chama `plat.camada_tile_apagar(schema, tabela)`
-- ANTES do DROP TABLE físico. Para uma camada hospedada de trabalho/cache, `schema` chega como
-- 'plat_trabalho' (dados->>'schema' do item) — mas a checagem `p_schema !~ '^d_[a-z0-9_]{1,60}$'`
-- da 20260906T1546 levantava `nome_de_tabela_invalido` para QUALQUER coisa fora de `d_<slug>`, e essa
-- exceção abortava o destruidor inteiro antes de chegar ao DROP TABLE — tests/api/catalogo/
-- test_lixeira.py::test_expurgo_com_relogio_simulado_apaga_tabela_fisica e
-- tests/api/catalogo/test_uso_bytes_simetrico.py falhavam com a tabela física ainda viva.
--
-- 'plat_trabalho' é schema de trabalho LEGÍTIMO para uma camada hospedada de teste/cache (as duas
-- suítes criam a tabela ali de propósito). Não é bug de quem chama: `plat.camada_tile_garantir`
-- (mesma migração) só cria função de tile para `d_<slug>` de inquilino — NUNCA para `plat_trabalho`,
-- em nenhum ambiente, produção incluída —, então para uma camada de trabalho não existe função de
-- tile nenhuma para apagar; a função só precisa devolver `false` sem levantar exceção.
--
-- Os DOIS testes passam o schema de formas diferentes e as duas são legítimas: test_uso_bytes_
-- simetrico.py manda o literal hardcoded 'plat_trabalho' (nunca reescrito por app/schema_ambiente.py,
-- que troca só texto de CONSULTA, nunca valor de bind); test_lixeira.py manda o valor JÁ RESOLVIDO do
-- ambiente (`_TRAB = os.environ["PLAT_SCHEMA_TRABALHO"]`), que numa trilha É o schema físico real
-- (medido nesta trilha: 'plat_trabalho_tuniao'). A função precisa aceitar as duas: o literal de
-- produção E o schema de trabalho físico DESTA instalação — nunca o de outra.
--
-- `current_schema()` dentro desta função (SET search_path = plat, public, reescrito por trilha para
-- plat_t<trilha>, public) sempre devolve o `plat`/`plat_t<trilha>` desta instalação em runtime — é
-- IMMUTABLE não sobre o schema em si (que muda por instalação), mas sobre a RELAÇÃO entre o `plat`
-- da instalação e o `plat_trabalho` dela, que é sempre a mesma troca de sufixo que
-- app/schema_ambiente.py faz para SCHEMA_TRABALHO_PADRAO. `substring(current_schema() FROM 5)` pega
-- tudo depois de 'plat' ('' em produção, '_tuniao' nesta trilha) e cola em 'plat_trabalho'.
--
-- `'plat_' || 'trabalho'` (não o literal `'plat_trabalho'`) pelo MESMO motivo do `'p' || 'lat'` de
-- `camada_schema_prefixo` (20260907T0245): o tradutor de trilha (`app/schema_ambiente.py::_TRABALHO`,
-- reusado por `laco/trilha_reescrever.py` para reescrever o TEXTO desta migração) casa a palavra
-- inteira `plat_trabalho` e trocaria o literal por `plat_trabalho_t<trilha>` — só que o parâmetro
-- hardcoded em Python nunca é reescrito, então precisa sobreviver como o literal de produção em
-- QUALQUER instalação. Escrito por inteiro no arquivo, esta mesma migração comparou certo em
-- produção e ERRADO em toda trilha (medido ao aplicar nesta trilha antes de partir a string).
--
-- Correção: aceita 'plat_trabalho' (literal de produção, protegido do tradutor) OU o schema de
-- trabalho físico desta instalação (calculado a partir de current_schema(), nunca hardcoded) — sem
-- checar FORMATO de tabela nem consultar dono nenhum, porque não há convenção de nome nem "dono" de
-- schema de trabalho para checar (as duas suítes usam tabela `zt_expurgo_<hex>`/`zt_simetrico_<hex>`,
-- fora do padrão `c_<16 hex>` da ingestão — achado ao rodar: a checagem original de p_tabela era
-- INCONDICIONAL, então mesmo aceitando o schema a função ainda levantava `nome_de_tabela_invalido`
-- pelo NOME da tabela; por isso o ramo de trabalho retorna ANTES de qualquer checagem de p_tabela).
-- Para `d_<slug>` a função reaproveita a MESMA checagem de posse de `camada_tile_garantir`
-- (`plat.tenant` escopado à instalação via `plat.camada_schema_prefixo()`, padrão consolidado pela
-- 20260911T1440) — rejeita 'd_' de outra instalação, e SÓ para este ramo o nome da tabela continua
-- preso ao padrão `c_<16 hex>` da ingestão. 'plat', 'public' e qualquer string fora dos casos
-- legítimos continuam caindo no `ELSE` e levantando `nome_de_tabela_invalido`, exatamente como antes.
CREATE OR REPLACE FUNCTION plat.camada_tile_apagar(p_schema text, p_tabela text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE nome text; tid int; trab text;
BEGIN
  trab := 'plat_' || 'trabalho' || substring(current_schema() FROM 5);
  IF p_schema = 'plat_' || 'trabalho' OR p_schema = trab THEN
    RETURN false;  -- cache/trabalho: camada_tile_garantir nunca cria função de tile aqui; nome livre
  END IF;
  IF p_schema !~ '^d_[a-z0-9_]{1,60}$' OR p_tabela !~ '^c_[0-9a-f]{16}$' THEN
    RAISE EXCEPTION 'nome_de_tabela_invalido';
  END IF;
  SELECT id INTO tid FROM plat.tenant WHERE plat.camada_schema_prefixo() || slug = p_schema;
  IF tid IS NULL THEN RAISE EXCEPTION 'schema_sem_inquilino'; END IF;
  nome := 't_' || substr(p_tabela, 3);
  IF to_regprocedure(format('%I.%I(integer,integer,integer,json)', p_schema, nome)) IS NULL THEN
    RETURN false;
  END IF;
  EXECUTE format('DROP FUNCTION %I.%I(integer,integer,integer,json)', p_schema, nome);
  RETURN true;
END $$;
