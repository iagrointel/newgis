-- 20260907T1602_amc_transformacoes: implementação SQL/PL-pgSQL da biblioteca declarativa de
-- transformações valor bruto -> favorabilidade 0-100 (item L3-01-d-transformacoes). Espelha
-- app/amc/transformacoes.py função a função, com a MESMA convenção de nomes de parâmetro (em
-- português) e a mesma escolha declarada de fórmula para as funções contínuas do Rescale by
-- Function (ver docstring do módulo Python: Esri documenta propósito e parâmetro, não a fórmula
-- fechada). Idempotente (CREATE OR REPLACE). Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- Duas entradas, uma por natureza de valor bruto: `plat.amc_transformar_num` (double precision,
-- todos os tipos numéricos) e `plat.amc_transformar_cat` (text, só `categoria`). Um valor NULL de
-- entrada sempre devolve NULL — nunca 0, nunca a nota de `abaixo`.
--
-- IMPORTANTE (documentado também no Python): `faixas` com `metodo` != 'manual' e `ms_grande`/
-- `ms_pequena` sem `media`/`desvio` gravados exigem uma amostra para resolver quebras/estatísticas.
-- Isto AQUI só sabe aplicar a versão já RESOLVIDA (quebras explícitas, media/desvio explícitos) —
-- é responsabilidade de quem materializa (o job) congelar essa resolução ANTES de chamar em massa,
-- exatamente como o Python resolve com `resolver_quebras`/`resolver_estatisticas`.

CREATE OR REPLACE FUNCTION plat.amc_transformar_cat(valor text, t jsonb) RETURNS double precision
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  nota jsonb;
BEGIN
  IF valor IS NULL THEN RETURN NULL; END IF;
  nota := (t -> 'notas') -> valor;
  IF nota IS NOT NULL THEN RETURN (nota)::text::double precision; END IF;
  IF t ? 'outros' AND (t -> 'outros') IS NOT NULL THEN RETURN (t ->> 'outros')::double precision; END IF;
  RETURN NULL;
END;
$$;

-- remapeamento de saída (saida_min/saida_max, padrão 0/100), aplicado à fração 0-1 já calculada pela curva
CREATE OR REPLACE FUNCTION plat._amc_saida(frac double precision, t jsonb) RETURNS double precision
LANGUAGE sql IMMUTABLE AS $$
  SELECT coalesce((t ->> 'saida_min')::double precision, 0.0)
       + frac * (coalesce((t ->> 'saida_max')::double precision, 100.0) - coalesce((t ->> 'saida_min')::double precision, 0.0))
$$;

CREATE OR REPLACE FUNCTION plat.amc_transformar_num(valor double precision, t jsonb) RETURNS double precision
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  tipo text := t ->> 'tipo';
  minimo double precision; maximo double precision; meio double precision; metade double precision;
  deslocamento double precision; fator double precision; expoente double precision; base double precision;
  midpoint double precision; spread double precision; p double precision; k double precision; razao double precision;
  media double precision; desvio double precision; mult_media double precision; mult_desvio double precision;
  frac double precision; frac_clip double precision; curva double precision; denom double precision;
  decrescente boolean;
  quebras double precision[]; notas double precision[]; i int; idx int; ate_i double precision;
  abaixo double precision; acima double precision;
BEGIN
  IF valor IS NULL OR valor = 'NaN'::double precision THEN RETURN NULL; END IF;

  IF tipo = 'linear' THEN
    minimo := (t ->> 'minimo')::double precision; maximo := (t ->> 'maximo')::double precision;
    decrescente := coalesce(t ->> 'direcao', 'crescente') = 'decrescente';
    IF maximo = minimo THEN RETURN plat._amc_saida(0.5, t); END IF;
    frac := (valor - minimo) / (maximo - minimo);
    frac_clip := CASE WHEN decrescente THEN 1.0 - frac ELSE frac END;
    curva := plat._amc_saida(least(greatest(frac_clip, 0.0), 1.0), t);
    IF frac < 0.0 AND t ? 'abaixo' AND (t -> 'abaixo') IS NOT NULL THEN RETURN (t ->> 'abaixo')::double precision; END IF;
    IF frac > 1.0 AND t ? 'acima' AND (t -> 'acima') IS NOT NULL THEN RETURN (t ->> 'acima')::double precision; END IF;
    RETURN curva;

  ELSIF tipo = 'linear_simetrica' THEN
    minimo := (t ->> 'minimo')::double precision; maximo := (t ->> 'maximo')::double precision;
    meio := (minimo + maximo) / 2.0; metade := (maximo - minimo) / 2.0;
    IF metade = 0 THEN
      RETURN CASE WHEN valor = meio THEN plat._amc_saida(1.0, t) ELSE NULL END;
    END IF;
    frac := abs(valor - meio) / metade;
    IF frac > 1.0 THEN
      abaixo := (t ->> 'abaixo')::double precision; acima := (t ->> 'acima')::double precision;
      IF abaixo IS NOT NULL THEN RETURN abaixo; END IF;
      IF acima IS NOT NULL THEN RETURN acima; END IF;
    END IF;
    RETURN plat._amc_saida(least(greatest(1.0 - frac, 0.0), 1.0), t);

  ELSIF tipo = 'degraus' THEN
    SELECT array_agg((b ->> 'ate')::double precision ORDER BY (b ->> 'ate')::double precision),
           array_agg((b ->> 'nota')::double precision ORDER BY (b ->> 'ate')::double precision)
      INTO quebras, notas
      FROM jsonb_array_elements(t -> 'bandas') AS b;
    idx := 1;
    WHILE idx <= array_length(quebras, 1) AND valor > quebras[idx] LOOP idx := idx + 1; END LOOP;
    IF idx <= array_length(quebras, 1) THEN RETURN notas[idx]; END IF;
    IF t ? 'acima' AND (t -> 'acima') IS NOT NULL THEN RETURN (t ->> 'acima')::double precision; END IF;
    RETURN NULL;

  ELSIF tipo = 'faixas' THEN
    SELECT array_agg(x::double precision ORDER BY ordinality)
      INTO quebras FROM jsonb_array_elements_text(t -> 'quebras') WITH ORDINALITY AS q(x, ordinality);
    SELECT array_agg(x::double precision ORDER BY ordinality)
      INTO notas FROM jsonb_array_elements_text(t -> 'notas') WITH ORDINALITY AS q(x, ordinality);
    idx := 1;
    WHILE idx <= array_length(quebras, 1) AND valor > quebras[idx] LOOP idx := idx + 1; END LOOP;
    RETURN notas[idx];

  ELSIF tipo = 'potencia' THEN
    minimo := (t ->> 'minimo')::double precision; maximo := (t ->> 'maximo')::double precision;
    deslocamento := coalesce((t ->> 'deslocamento')::double precision, 0.0);
    expoente := coalesce((t ->> 'expoente')::double precision, 1.0);
    frac := CASE WHEN maximo = minimo THEN 0.0 ELSE (valor - deslocamento - minimo) / (maximo - minimo) END;
    frac_clip := least(greatest(frac, 0.0), 1.0);
    curva := power(frac_clip, expoente);
    IF frac < 0.0 AND t ? 'abaixo' AND (t -> 'abaixo') IS NOT NULL THEN RETURN (t ->> 'abaixo')::double precision; END IF;
    IF frac > 1.0 AND t ? 'acima' AND (t -> 'acima') IS NOT NULL THEN RETURN (t ->> 'acima')::double precision; END IF;
    RETURN plat._amc_saida(curva, t);

  ELSIF tipo = 'logaritmo' THEN
    minimo := (t ->> 'minimo')::double precision; maximo := (t ->> 'maximo')::double precision;
    deslocamento := coalesce((t ->> 'deslocamento')::double precision, 0.0);
    fator := coalesce((t ->> 'fator')::double precision, 1.0);
    frac := CASE WHEN maximo = minimo THEN 0.0 ELSE (valor + deslocamento - minimo) / (maximo - minimo) END;
    frac_clip := least(greatest(frac, 0.0), 1.0);
    curva := CASE WHEN fator <= 0 THEN frac_clip ELSE ln(1 + fator * frac_clip) / ln(1 + fator) END;
    IF frac < 0.0 AND t ? 'abaixo' AND (t -> 'abaixo') IS NOT NULL THEN RETURN (t ->> 'abaixo')::double precision; END IF;
    IF frac > 1.0 AND t ? 'acima' AND (t -> 'acima') IS NOT NULL THEN RETURN (t ->> 'acima')::double precision; END IF;
    RETURN plat._amc_saida(curva, t);

  ELSIF tipo = 'exponencial' THEN
    minimo := (t ->> 'minimo')::double precision; maximo := (t ->> 'maximo')::double precision;
    deslocamento := coalesce((t ->> 'deslocamento')::double precision, 0.0);
    base := coalesce((t ->> 'base')::double precision, exp(1.0));
    frac := CASE WHEN maximo = minimo THEN 0.0 ELSE (valor - minimo) / (maximo - minimo) END;
    frac_clip := least(greatest(frac, 0.0), 1.0);
    denom := power(base, 1 + deslocamento) - power(base, deslocamento);
    curva := CASE WHEN denom = 0 THEN frac_clip
                  ELSE (power(base, frac_clip + deslocamento) - power(base, deslocamento)) / denom END;
    IF frac < 0.0 AND t ? 'abaixo' AND (t -> 'abaixo') IS NOT NULL THEN RETURN (t ->> 'abaixo')::double precision; END IF;
    IF frac > 1.0 AND t ? 'acima' AND (t -> 'acima') IS NOT NULL THEN RETURN (t ->> 'acima')::double precision; END IF;
    RETURN plat._amc_saida(curva, t);

  ELSIF tipo IN ('crescimento_logistico', 'decaimento_logistico') THEN
    minimo := (t ->> 'minimo')::double precision; maximo := (t ->> 'maximo')::double precision;
    p := coalesce((t ->> 'y_intercepto_percentual')::double precision, 1.0);
    meio := (minimo + maximo) / 2.0;
    razao := (100.0 - p) / p;
    k := CASE WHEN maximo = minimo THEN 0.0 ELSE 2.0 * ln(razao) / (maximo - minimo) END;
    curva := 1.0 / (1.0 + exp(-k * (valor - meio)));
    IF tipo = 'decaimento_logistico' THEN curva := 1.0 - curva; END IF;
    IF valor < minimo AND t ? 'abaixo' AND (t -> 'abaixo') IS NOT NULL THEN RETURN (t ->> 'abaixo')::double precision; END IF;
    IF valor > maximo AND t ? 'acima' AND (t -> 'acima') IS NOT NULL THEN RETURN (t ->> 'acima')::double precision; END IF;
    RETURN plat._amc_saida(curva, t);

  ELSIF tipo = 'gaussiana' THEN
    midpoint := (t ->> 'midpoint')::double precision; spread := (t ->> 'spread')::double precision;
    curva := exp(-spread * (valor - midpoint) ^ 2);
    RETURN plat._amc_saida(curva, t);

  ELSIF tipo = 'proxima' THEN
    midpoint := (t ->> 'midpoint')::double precision; spread := (t ->> 'spread')::double precision;
    curva := exp(-spread * (valor - midpoint) ^ 4);
    RETURN plat._amc_saida(curva, t);

  ELSIF tipo = 'grande' THEN
    midpoint := (t ->> 'midpoint')::double precision; spread := (t ->> 'spread')::double precision;
    curva := 1.0 / (1.0 + exp(-spread * (valor - midpoint)));
    RETURN plat._amc_saida(curva, t);

  ELSIF tipo = 'pequena' THEN
    midpoint := (t ->> 'midpoint')::double precision; spread := (t ->> 'spread')::double precision;
    curva := 1.0 / (1.0 + exp(spread * (valor - midpoint)));
    RETURN plat._amc_saida(curva, t);

  ELSIF tipo IN ('ms_grande', 'ms_pequena') THEN
    IF t ? 'media' AND t ? 'desvio' THEN
      media := (t ->> 'media')::double precision; desvio := (t ->> 'desvio')::double precision;
    ELSE
      RAISE EXCEPTION 'amc_transformar_num: % precisa de media/desvio já resolvidos (resolver_estatisticas)', tipo;
    END IF;
    mult_media := coalesce((t ->> 'multiplicador_media')::double precision, 1.0);
    mult_desvio := coalesce((t ->> 'multiplicador_desvio')::double precision, 1.0);
    midpoint := media * mult_media;
    spread := mult_desvio / (CASE WHEN desvio > 0 THEN desvio ELSE 1.0 END);
    IF tipo = 'ms_grande' THEN
      curva := 1.0 / (1.0 + exp(-spread * (valor - midpoint)));
    ELSE
      curva := 1.0 / (1.0 + exp(spread * (valor - midpoint)));
    END IF;
    RETURN plat._amc_saida(curva, t);

  ELSE
    RAISE EXCEPTION 'amc_transformar_num: tipo desconhecido ou não numérico: %', tipo;
  END IF;
END;
$$;

COMMENT ON FUNCTION plat.amc_transformar_num(double precision, jsonb) IS
  'valor bruto numérico -> favorabilidade (item L3-01-d); espelha app.amc.transformacoes.transformar em Python; '
  'faixas com metodo != manual e ms_grande/ms_pequena sem media/desvio exigem a versão já resolvida.';
COMMENT ON FUNCTION plat.amc_transformar_cat(text, jsonb) IS
  'valor bruto categórico (tipo categoria) -> favorabilidade (item L3-01-d).';
