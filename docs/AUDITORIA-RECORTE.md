# Auditoria do recorte · 2026-08-26

**Fonte da verdade operacional.** Rode `python scripts/auditar_recorte.py` antes de qualquer carga, deploy ou módulo novo.

**Núcleo eleitoral:** PASSOU

## Regra de gate

1. `auditar_recorte.py` exit 0 → pode carregar complementos e redeploy MCP.
2. Exit 1 → **proibido** IBGE, social, Parlamento, entrega ao usuário.
3. `docs/INVENTARIO-INBOX.md` é índice do despejo; **status de carga** é só esta página + o script.

## Matriz (última execução)

| Bloco | Item | Status | Detalhe |
|---|---|---|---|
| raw | br_mun_votacao_nominal/2014 | ok | origem.zip ou csv |
| raw | br_mun_votacao_nominal/2018 | ok | origem.zip ou csv |
| raw | br_mun_votacao_nominal/2022 | ok | origem.zip ou csv |
| raw | br_mun_votacao_nominal/2016 | ok | origem.zip ou csv |
| raw | br_mun_votacao_nominal/2020 | ok | origem.zip ou csv |
| raw | br_mun_votacao_nominal/2024 | ok | origem.zip ou csv |
| raw | br_mun_detalhe_apuracao/2014 | ok | origem.zip ou csv |
| raw | br_mun_detalhe_apuracao/2018 | ok | origem.zip ou csv |
| raw | br_mun_detalhe_apuracao/2022 | ok | origem.zip ou csv |
| raw | br_mun_detalhe_apuracao/2016 | ok | origem.zip ou csv |
| raw | br_mun_detalhe_apuracao/2020 | ok | origem.zip ou csv |
| raw | br_mun_detalhe_apuracao/2024 | ok | origem.zip ou csv |
| raw | br_cand_nominata/2014 | ok | origem.zip ou csv |
| raw | br_cand_nominata/2018 | ok | origem.zip ou csv |
| raw | br_cand_nominata/2022 | ok | origem.zip ou csv |
| raw | br_cand_nominata/2016 | ok | origem.zip ou csv |
| raw | br_cand_nominata/2020 | ok | origem.zip ou csv |
| raw | br_cand_nominata/2024 | ok | origem.zip ou csv |
| raw | br_cand_nominata/2026 | ok | origem.zip ou csv |
| raw | br_mun_eleitorado_perfil/2014 | ok | origem.zip ou csv |
| raw | br_mun_eleitorado_perfil/2018 | ok | origem.zip ou csv |
| raw | br_mun_eleitorado_perfil/2022 | ok | origem.zip ou csv |
| raw | br_mun_eleitorado_perfil/2016 | ok | origem.zip ou csv |
| raw | br_mun_eleitorado_perfil/2020 | ok | origem.zip ou csv |
| raw | br_mun_eleitorado_perfil/2024 | ok | origem.zip ou csv |
| raw | br_mun_eleitorado_perfil/2026 | ok | origem.zip ou csv |
| raw | br_cand_coligacao/2014 | ok | origem.zip ou csv |
| raw | br_cand_coligacao/2018 | ok | origem.zip ou csv |
| raw | br_cand_coligacao/2022 | ok | origem.zip ou csv |
| raw | br_cand_coligacao/2016 | ok | origem.zip ou csv |
| raw | br_cand_coligacao/2020 | ok | origem.zip ou csv |
| raw | br_cand_coligacao/2024 | ok | origem.zip ou csv |
| raw | br_cand_coligacao/2026 | ok | origem.zip ou csv |
| raw | br_mun_malha_ibge | ok | malha presente |
| postgres | votacao/2014 | ok | n=7,900,873 uf=27 mun=5570 |
| postgres | detalhe/2014 | ok | n=39,710 uf=27 mun=5570 |
| postgres | candidatura/2014 | ok | n=26,161 uf=28 mun=0 |
| postgres | eleitorado/2014 | ok | n=1,445,208 uf=27 mun=5570 |
| postgres | coligacao/2014 | ok | n=5,782 |
| postgres | votacao/2018 | ok | n=8,676,432 uf=27 mun=5570 |
| postgres | detalhe/2018 | ok | n=39,988 uf=27 mun=5570 |
| postgres | candidatura/2018 | ok | n=29,153 uf=28 mun=0 |
| postgres | eleitorado/2018 | ok | n=1,439,696 uf=27 mun=5570 |
| postgres | coligacao/2018 | ok | n=6,192 |
| postgres | votacao/2022 | ok | n=9,375,444 uf=27 mun=5570 |
| postgres | detalhe/2022 | ok | n=39,604 uf=27 mun=5570 |
| postgres | candidatura/2022 | ok | n=29,262 uf=28 mun=0 |
| postgres | eleitorado/2022 | ok | n=1,473,272 uf=27 mun=5570 |
| postgres | coligacao/2022 | ok | n=4,710 |
| postgres | votacao/2016 | ok | n=942,557 uf=26 mun=5567 |
| postgres | detalhe/2016 | ok | n=12,959 uf=26 mun=5568 |
| postgres | candidatura/2016 | ok | n=496,977 uf=26 mun=5568 |
| postgres | eleitorado/2016 | ok | n=1,469,915 uf=26 mun=5568 |
| postgres | coligacao/2016 | ok | n=248,855 |
| postgres | votacao/2020 | ok | n=983,144 uf=26 mun=5568 |
| postgres | detalhe/2020 | ok | n=12,511 uf=26 mun=5568 |
| postgres | candidatura/2020 | ok | n=557,678 uf=26 mun=5568 |
| postgres | eleitorado/2020 | ok | n=1,445,879 uf=26 mun=5568 |
| postgres | coligacao/2020 | ok | n=138,199 |
| postgres | votacao/2024 | ok | n=717,137 uf=26 mun=5568 |
| postgres | detalhe/2024 | ok | n=12,449 uf=26 mun=5569 |
| postgres | candidatura/2024 | ok | n=463,394 uf=26 mun=5569 |
| postgres | eleitorado/2024 | ok | n=1,464,192 uf=26 mun=5569 |
| postgres | coligacao/2024 | ok | n=157,082 |
| postgres | ref.municipio | ok | n=5,571 |
