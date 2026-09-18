-- reaplicavel
-- 20260918T0100_rede_associacao_validar_desenho_feicao: o gatilho plat.rede_associacao_validar() só
-- entende o desenho de NÓ/ARESTA (de_no_id/para_no_id/para_aresta_id, importadores BDGD/OSM) e recusa
-- TODA linha do desenho de FEIÇÃO (de_feicao_id/para_feicao_id/regra_id, escrito por applyEdits — item
-- L4-03-a-regras-de-conectividade): `NEW.de_no_id` é NULL nessas linhas, o SELECT inicial não acha nada
-- e a função levanta 'associacao_de_fora_da_rede'. Medido ao vivo:
-- tests/api/test_regras_conectividade.py::test_associacao_de_contencao_permitida_e_a_invertida_e_recusada
-- — psycopg2.errors.RaiseException: associacao_de_fora_da_rede na PRIMEIRA associação de contenção.
-- É o terceiro ponto em que a união dos dois desenhos (documentada em
-- 20260916T1145_rede_associacao_conectividade_nullable.sql) ficou incompleta: 1130 trocou o vocabulário,
-- 1145 destravou NOT NULL e o CHECK de tipo, mas ninguém desviou o gatilho das linhas de feição.
--
-- Ajuste: linha do desenho de FEIÇÃO (de_feicao_id preenchido, de_no_id NULL) passa direto. NÃO é
-- validação a menos: applyEdits (app/rede_utilidades/rotas_regras.py) AVALIA o motor de regras antes do
-- INSERT quando rede.regras_ativas está ligada — a regra casada vai em regra_id, com FK composta para
-- plat.rede_regra — e quando está desligada (comporta de carga em massa, ato de rede.administrar) a
-- linha entra com regra_id NULL de propósito, e a validação em lote (POST .../validar) reavalia tudo
-- depois. Reimplementar a avaliação aqui dentro duplicaria o motor (terminais, aresta-junção-aresta,
-- pontas ordenadas de associação) em plpgsql para ganho zero. Linha com os DOIS pares NULL ou com
-- de_no_id preenchido cai no caminho de NÓ/ARESTA como antes — lixo continua recusado.
-- Idempotente (CREATE OR REPLACE). Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE OR REPLACE FUNCTION plat.rede_associacao_validar() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
  v_de record;
  v_para record;
  v_tipo_regra text;
  v_ok boolean;
BEGIN
  -- desenho de FEIÇÃO (applyEdits): regra já avaliada pela aplicação; ver cabeçalho da migração
  IF NEW.de_feicao_id IS NOT NULL AND NEW.de_no_id IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT rede_id, papel, tipo_id INTO v_de FROM plat.rede_no
   WHERE tenant_id = NEW.tenant_id AND id = NEW.de_no_id;
  IF NOT FOUND OR v_de.rede_id <> NEW.rede_id THEN
    RAISE EXCEPTION 'associacao_de_fora_da_rede: o nó de origem precisa ser da mesma rede';
  END IF;
  IF v_de.tipo_id IS NULL THEN
    RAISE EXCEPTION 'associacao_sem_tipo: o nó de origem da associação precisa ter tipo de ativo (junção anônima não inicia associação)';
  END IF;

  v_tipo_regra := CASE NEW.tipo
    WHEN 'conectividade' THEN NULL  -- decidido abaixo pela forma do alvo
    WHEN 'contencao' THEN 'contencao'
    WHEN 'fixacao' THEN 'estrutura'
  END;

  IF NEW.para_aresta_id IS NOT NULL THEN
    -- forma junction-edge direta: regra entre o tipo da aresta e o tipo do ativo
    SELECT rede_id, tipo_id INTO v_para FROM plat.rede_aresta
     WHERE tenant_id = NEW.tenant_id AND id = NEW.para_aresta_id;
    IF NOT FOUND OR v_para.rede_id <> NEW.rede_id THEN
      RAISE EXCEPTION 'associacao_aresta_fora_da_rede: a aresta alvo precisa ser da mesma rede';
    END IF;
    SELECT EXISTS (
      SELECT 1 FROM plat.rede_regra r
       WHERE r.rede_id = NEW.rede_id AND r.tipo = COALESCE(v_tipo_regra, 'juncao_aresta')
         AND ((r.de_tipo_id = v_para.tipo_id AND r.para_tipo_id = v_de.tipo_id)
           OR (r.de_tipo_id = v_de.tipo_id AND r.para_tipo_id = v_para.tipo_id))
    ) INTO v_ok;
    IF NOT v_ok THEN
      RAISE EXCEPTION 'associacao_sem_regra: o catálogo não tem regra de % entre o tipo do ativo e o tipo da aresta',
        COALESCE(v_tipo_regra, 'juncao_aresta');
    END IF;
    RETURN NEW;
  END IF;

  SELECT rede_id, papel, tipo_id INTO v_para FROM plat.rede_no
   WHERE tenant_id = NEW.tenant_id AND id = NEW.para_no_id;
  IF NOT FOUND OR v_para.rede_id <> NEW.rede_id THEN
    RAISE EXCEPTION 'associacao_para_fora_da_rede: o nó alvo precisa ser da mesma rede';
  END IF;
  IF NEW.de_no_id = NEW.para_no_id THEN
    RAISE EXCEPTION 'associacao_reflexiva: a associação não pode ligar o nó a ele mesmo';
  END IF;

  IF NEW.tipo = 'conectividade' AND v_para.tipo_id IS NULL THEN
    -- alvo é junção anônima: a regra é conferida contra os tipos das arestas que nela incidem
    SELECT EXISTS (
      SELECT 1 FROM plat.rede_aresta a
       JOIN plat.rede_regra r ON r.rede_id = NEW.rede_id AND r.tipo = 'juncao_aresta'
         AND ((r.de_tipo_id = a.tipo_id AND r.para_tipo_id = v_de.tipo_id)
           OR (r.de_tipo_id = v_de.tipo_id AND r.para_tipo_id = a.tipo_id))
       WHERE a.tenant_id = NEW.tenant_id AND a.rede_id = NEW.rede_id
         AND (a.no_origem_id = NEW.para_no_id OR a.no_destino_id = NEW.para_no_id)
    ) INTO v_ok;
    IF NOT v_ok THEN
      RAISE EXCEPTION 'associacao_sem_regra: nenhuma aresta incidente na junção tem regra de conectividade com o tipo do ativo';
    END IF;
  ELSE
    -- ativo-ativo (juncao_juncao) ou contenção/estrutura entre tipos
    SELECT EXISTS (
      SELECT 1 FROM plat.rede_regra r
       WHERE r.rede_id = NEW.rede_id AND r.tipo = COALESCE(v_tipo_regra, 'juncao_juncao')
         AND ((r.de_tipo_id = v_para.tipo_id AND r.para_tipo_id = v_de.tipo_id)
           OR (r.de_tipo_id = v_de.tipo_id AND r.para_tipo_id = v_para.tipo_id))
    ) INTO v_ok;
    IF NOT v_ok THEN
      RAISE EXCEPTION 'associacao_sem_regra: o catálogo não tem regra de % entre os dois tipos de ativo',
        COALESCE(v_tipo_regra, 'juncao_juncao');
    END IF;
  END IF;
  RETURN NEW;
END;
$fn$;
