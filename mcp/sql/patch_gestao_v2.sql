-- Gestão v2 — papel coordenador + liberação de equipe
ALTER TABLE ctl.campanha ADD COLUMN IF NOT EXISTS equipe_liberada boolean NOT NULL DEFAULT false;
ALTER TABLE ctl.apura_usuario ADD COLUMN IF NOT EXISTS papel text NOT NULL DEFAULT 'equipe';
COMMENT ON COLUMN ctl.apura_usuario.papel IS 'coordenador | equipe';
COMMENT ON COLUMN ctl.campanha.equipe_liberada IS 'true = logins de equipe liberados pelo coordenador';
