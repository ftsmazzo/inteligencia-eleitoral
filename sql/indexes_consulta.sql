-- Índices de consulta (candidato, partido). Aplicar após a urna.

CREATE INDEX IF NOT EXISTS idx_cand_partido ON eleicao.candidatura (ano, sg_partido, cd_cargo);
CREATE INDEX IF NOT EXISTS idx_cand_urna ON eleicao.candidatura USING gin (nm_urna gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_vot_2014_sq ON eleicao.votacao_2014 (sq_candidato);
CREATE INDEX IF NOT EXISTS idx_vot_2016_sq ON eleicao.votacao_2016 (sq_candidato);
CREATE INDEX IF NOT EXISTS idx_vot_2018_sq ON eleicao.votacao_2018 (sq_candidato);
CREATE INDEX IF NOT EXISTS idx_vot_2020_sq ON eleicao.votacao_2020 (sq_candidato);
CREATE INDEX IF NOT EXISTS idx_vot_2022_sq ON eleicao.votacao_2022 (sq_candidato);
CREATE INDEX IF NOT EXISTS idx_vot_2024_sq ON eleicao.votacao_2024 (sq_candidato);

CREATE INDEX IF NOT EXISTS idx_vot_2014_pt ON eleicao.votacao_2014 (sg_partido, cd_cargo);
CREATE INDEX IF NOT EXISTS idx_vot_2016_pt ON eleicao.votacao_2016 (sg_partido, cd_cargo);
CREATE INDEX IF NOT EXISTS idx_vot_2018_pt ON eleicao.votacao_2018 (sg_partido, cd_cargo);
CREATE INDEX IF NOT EXISTS idx_vot_2020_pt ON eleicao.votacao_2020 (sg_partido, cd_cargo);
CREATE INDEX IF NOT EXISTS idx_vot_2022_pt ON eleicao.votacao_2022 (sg_partido, cd_cargo);
CREATE INDEX IF NOT EXISTS idx_vot_2024_pt ON eleicao.votacao_2024 (sg_partido, cd_cargo);
