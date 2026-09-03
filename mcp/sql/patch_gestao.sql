-- Gestão Apura — escopo de campanha + memória (S1).
-- Idempotente. Requer ctl.campanha (patch_apura).

ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS ambiente_status text NOT NULL DEFAULT 'legado';
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS ano_ref int;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS cd_cargo int;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS sg_uf text;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS sq_candidato bigint;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS nm_candidato text;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS nm_urna text;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS sg_partido text;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS nr_candidato int;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS escopo_json jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS atualizado_em timestamptz NOT NULL DEFAULT now();

COMMENT ON COLUMN ctl.campanha.ambiente_status IS 'legado | rascunho | configurando | pronto';

CREATE TABLE IF NOT EXISTS ctl.campanha_memoria (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campanha_id  uuid NOT NULL REFERENCES ctl.campanha(id) ON DELETE CASCADE,
  tipo         text NOT NULL,
  titulo       text NOT NULL,
  corpo        text NOT NULL DEFAULT '',
  fonte        text NOT NULL DEFAULT '',
  nivel        text NOT NULL DEFAULT 'indicio',
  meta_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_em    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campanha_memoria_campanha
  ON ctl.campanha_memoria (campanha_id, tipo);

COMMENT ON TABLE ctl.campanha_memoria IS 'Blocos indexados da campanha (perfil, dossie, base de verdade). S1 vazia.';

GRANT SELECT, INSERT, UPDATE ON ctl.campanha TO agente;
GRANT SELECT, INSERT, UPDATE, DELETE ON ctl.campanha_memoria TO agente;
