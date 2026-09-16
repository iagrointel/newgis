-- reaplicavel
-- 20260916T1130_rede_associacao_validar_vocabulario: gatilho plat.rede_associacao_validar() ainda citava o
-- vocabulário de plat.rede_regra.tipo anterior à migração 20260906T2058_rede_regras_conectividade.sql
-- (item L4-03-a-regras-de-conectividade), que trocou 'conectividade_no_trecho'/'conectividade_entre_nos'/
-- 'fixacao_estrutural'/'contencao' por 'juncao_aresta'/'juncao_juncao'/'estrutura'/'contencao'
-- (aresta_juncao_aresta é caso à parte, sem uso neste gatilho) e TRADUZIU as linhas já gravadas.
--
-- A função foi criada por 20260906T2126_rede_modelo_elementos.sql (item L4-01-modelo-rede), DEPOIS da
-- migração de vocabulário, mas com as 4 constantes de string do vocabulário ANTIGO ainda embutidas nas
-- três consultas a plat.rede_regra — bug de origem, não regressão de fusão desta linha. Consequência
-- medida ao vivo: toda associação de conectividade escrita pelo importador BDGD (dispositivo/consumidor
-- -> junção) ou pela importação de vias OSM passava a esbarrar em
-- 'associacao_sem_regra: nenhuma aresta incidente na junção tem regra de conectividade com o tipo do
-- ativo' — o EXISTS da aplicação (já no vocabulário novo) achava a regra, mas o gatilho, com o
-- vocabulário velho, nunca achava nenhuma linha e recusava a escrita.
--
-- Único ajuste: as 4 constantes de string. Nenhuma outra linha da função muda.
-- Idempotente (CREATE OR REPLACE). Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE OR REPLACE FUNCTION plat.rede_associacao_validar() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
  v_de record;
  v_para record;
  v_tipo_regra text;
  v_ok boolean;
BEGIN
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
