-- Opção A: Executar diretamente no Databricks SQL Warehouse ou Notebook
CREATE TABLE IF NOT EXISTS space_portal.admin_users (
    email STRING
) USING delta;

INSERT INTO space_portal.admin_users (email) VALUES
('renan.ferreira@grupobimbo.com'),
('vitor.saes@grupobimbo.com'),
('bruno.fellipe@grupobimbo.com');

-- Opção B: Executar diretamente no banco de dados PostgreSQL / Lakebase (usado pelo backend da aplicação)
CREATE TABLE IF NOT EXISTS space_portal.admin_users (
    email VARCHAR(256) PRIMARY KEY
);

INSERT INTO space_portal.admin_users (email) VALUES
('renan.ferreira@grupobimbo.com'),
('vitor.saes@grupobimbo.com'),
('bruno.fellipe@grupobimbo.com'),
('pedro.madureira@grupobimbo.com'),
('helio.cillo@grupobimbo.com'),
('lecivaldo.santana@grupobimbo.com'),
('caio.dasilva@grupobimbo.com'),
('maria.carolina@grupobimbo.com')
ON CONFLICT (email) DO NOTHING;
