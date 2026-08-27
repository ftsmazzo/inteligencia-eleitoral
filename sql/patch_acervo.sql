-- Acervo (Trilha B) · documentos semânticos com temporalidade.
-- MVP: busca lexical (tsvector). Embedding vetorial em fase posterior.
-- Números no texto NÃO são fato; cifra só via api.* (Trilha A).

CREATE SCHEMA IF NOT EXISTS acervo;

CREATE TABLE IF NOT EXISTS acervo.documento (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo              text NOT NULL,
  titulo            text NOT NULL,
  descricao         text NOT NULL DEFAULT '',
  nivel             text NOT NULL DEFAULT 'referencia'
                    CHECK (nivel IN ('referencia', 'indicio')),
  ano_eleicao       smallint,
  vigencia_inicio   date,
  vigencia_fim      date,
  escopo            text NOT NULL DEFAULT 'BR'
                    CHECK (escopo IN ('BR', 'UF', 'mun')),
  sg_uf             char(2),
  cod_ibge          integer,
  sg_partido        text,
  nm_candidato      text,
  cargo             text,
  tags              text[] NOT NULL DEFAULT '{}',
  fonte_url         text,
  fonte_orgao       text,
  sha256            text,
  id_base_raw       text,
  meta              jsonb NOT NULL DEFAULT '{}'::jsonb,
  ativo             boolean NOT NULL DEFAULT true,
  criado_em         timestamptz NOT NULL DEFAULT now(),
  atualizado_em     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT acervo_doc_vigencia CHECK (
    vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim >= vigencia_inicio
  )
);

CREATE INDEX IF NOT EXISTS idx_acervo_doc_tipo ON acervo.documento (tipo, ano_eleicao);
CREATE INDEX IF NOT EXISTS idx_acervo_doc_vigencia ON acervo.documento (vigencia_inicio, vigencia_fim);
CREATE INDEX IF NOT EXISTS idx_acervo_doc_uf ON acervo.documento (sg_uf) WHERE sg_uf IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_acervo_doc_partido ON acervo.documento (sg_partido) WHERE sg_partido IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_acervo_doc_tags ON acervo.documento USING gin (tags);

CREATE TABLE IF NOT EXISTS acervo.chunk (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  documento_id      uuid NOT NULL REFERENCES acervo.documento(id) ON DELETE CASCADE,
  ord               integer NOT NULL DEFAULT 0,
  secao             text NOT NULL DEFAULT '',
  texto             text NOT NULL,
  token_count       integer,
  meta              jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_em         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_acervo_chunk_doc ON acervo.chunk (documento_id, ord);
CREATE INDEX IF NOT EXISTS idx_acervo_chunk_texto ON acervo.chunk USING gin (to_tsvector('portuguese', texto));

CREATE OR REPLACE FUNCTION api.acervo_norm(p text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT translate(
    lower(COALESCE(p, '')),
    'áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ',
    'aaaaaeeeeiiiiooooouuuucnaaaaaeeeeiiiiooooouuuucn'
  );
$$;

DROP FUNCTION IF EXISTS api.consultar_acervo(text, smallint, text, text, text, date, integer);

CREATE OR REPLACE FUNCTION api.consultar_acervo(
  p_query text,
  p_ano_eleicao smallint DEFAULT NULL,
  p_tipo text DEFAULT NULL,
  p_uf text DEFAULT NULL,
  p_sg_partido text DEFAULT NULL,
  p_vigente_em date DEFAULT CURRENT_DATE,
  p_limite integer DEFAULT 8,
  p_nm_candidato text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = api, acervo, ref, pg_temp
AS $$
DECLARE
  v_lim integer;
  v_linhas jsonb;
  v_q text;
  v_cand text;
BEGIN
  v_q := btrim(COALESCE(p_query, ''));
  IF v_q = '' THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'nivel', 'referencia',
      'mensagem', 'Query vazia.',
      'itens', '[]'::jsonb
    );
  END IF;
  v_lim := LEAST(GREATEST(COALESCE(p_limite, 8), 1), 30);
  v_cand := nullif(btrim(COALESCE(p_nm_candidato, '')), '');

  SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.rank DESC), '[]'::jsonb)
    INTO v_linhas
  FROM (
    SELECT
      d.id::text AS documento_id,
      c.id::text AS chunk_id,
      d.tipo,
      d.titulo,
      d.nm_candidato,
      d.nivel,
      d.ano_eleicao,
      d.vigencia_inicio,
      d.vigencia_fim,
      d.sg_uf,
      d.sg_partido,
      d.fonte_url,
      c.secao,
      left(c.texto, 1200) AS trecho,
      ts_rank(
        to_tsvector('portuguese', c.texto),
        plainto_tsquery('portuguese', v_q)
      ) AS rank
    FROM acervo.chunk c
    JOIN acervo.documento d ON d.id = c.documento_id
    WHERE d.ativo IS TRUE
      AND (p_tipo IS NULL OR d.tipo = p_tipo)
      AND (p_ano_eleicao IS NULL OR d.ano_eleicao = p_ano_eleicao)
      AND (p_uf IS NULL OR d.sg_uf IS NULL OR d.sg_uf = upper(p_uf) OR d.escopo = 'BR')
      AND (
        p_sg_partido IS NULL
        OR d.sg_partido IS NULL
        OR upper(d.sg_partido) = ANY (COALESCE(api.siglas_equivalentes(p_sg_partido), ARRAY[upper(btrim(p_sg_partido))]))
      )
      AND (
        v_cand IS NULL
        OR api.acervo_norm(d.nm_candidato) LIKE '%' || api.acervo_norm(v_cand) || '%'
        OR api.acervo_norm(d.titulo) LIKE '%' || api.acervo_norm(v_cand) || '%'
      )
      AND (d.vigencia_inicio IS NULL OR d.vigencia_inicio <= COALESCE(p_vigente_em, CURRENT_DATE))
      AND (d.vigencia_fim IS NULL OR d.vigencia_fim >= COALESCE(p_vigente_em, CURRENT_DATE))
      AND to_tsvector('portuguese', c.texto) @@ plainto_tsquery('portuguese', v_q)
    ORDER BY rank DESC
    LIMIT v_lim
  ) t;

  IF v_linhas = '[]'::jsonb THEN
    RETURN jsonb_build_object(
      'status', 'vazio',
      'nivel', 'referencia',
      'mensagem', 'Nenhum trecho no acervo para este filtro temporal/temático.',
      'nota_metodologica', 'Busca lexical. Cifra no trecho é pista, não fato. Planos carregados hoje: presidente 2026. Use ano_eleicao=2026 e nm_candidato quando perguntar de um candidato.',
      'itens', v_linhas
    );
  END IF;

  RETURN jsonb_build_object(
    'status', 'ok',
    'nivel', 'referencia',
    'nota_metodologica', 'Trilha B: trechos com vigência filtrada. Número no texto não substitui api.eleitos/votacao.',
    'itens', v_linhas
  );
END;
$$;

GRANT USAGE ON SCHEMA acervo TO agente;
GRANT SELECT ON ALL TABLES IN SCHEMA acervo TO agente;
GRANT EXECUTE ON FUNCTION api.acervo_norm(text) TO agente;
GRANT EXECUTE ON FUNCTION api.consultar_acervo(text, smallint, text, text, text, date, integer, text) TO agente;
