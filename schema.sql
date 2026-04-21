-- =============================
-- EXTENSIONES (opcional pero pro)
-- =============================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================
-- USUARIOS
-- =============================
CREATE TABLE IF NOT EXISTS usuarios (
    id BIGINT PRIMARY KEY,
    creado_en TIMESTAMP DEFAULT NOW()
);

-- =============================
-- TARJETAS (CONFIG GLOBAL)
-- =============================
CREATE TABLE IF NOT EXISTS tarjetas (
    nombre TEXT PRIMARY KEY,
    dia_corte INT NOT NULL CHECK (dia_corte BETWEEN 1 AND 31),
    dias_pago INT NOT NULL CHECK (dias_pago BETWEEN 1 AND 60)
);

-- =============================
-- MOVIMIENTOS (GASTOS)
-- =============================
CREATE TABLE IF NOT EXISTS movimientos (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    tarjeta TEXT NOT NULL,
    monto NUMERIC(12,2) NOT NULL CHECK (monto > 0),
    tipo TEXT NOT NULL CHECK (tipo IN ('CONTADO','MSI')),
    meses INT NOT NULL CHECK (meses BETWEEN 1 AND 48),

    -- FK
    CONSTRAINT fk_mov_user FOREIGN KEY (user_id)
        REFERENCES usuarios(id) ON DELETE CASCADE,

    CONSTRAINT fk_mov_tarjeta FOREIGN KEY (tarjeta)
        REFERENCES tarjetas(nombre) ON DELETE RESTRICT
);

-- =============================
-- PAGOS
-- =============================
CREATE TABLE IF NOT EXISTS pagos (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    tarjeta TEXT NOT NULL,
    monto NUMERIC(12,2) NOT NULL CHECK (monto > 0),

    CONSTRAINT fk_pago_user FOREIGN KEY (user_id)
        REFERENCES usuarios(id) ON DELETE CASCADE,

    CONSTRAINT fk_pago_tarjeta FOREIGN KEY (tarjeta)
        REFERENCES tarjetas(nombre) ON DELETE RESTRICT
);

-- =============================
-- ÍNDICES (RENDIMIENTO PRO)
-- =============================

-- Movimientos
CREATE INDEX IF NOT EXISTS idx_mov_user_fecha 
ON movimientos(user_id, fecha);

CREATE INDEX IF NOT EXISTS idx_mov_user_tarjeta 
ON movimientos(user_id, tarjeta);

CREATE INDEX IF NOT EXISTS idx_mov_tipo 
ON movimientos(tipo);

-- Pagos
CREATE INDEX IF NOT EXISTS idx_pago_user_fecha 
ON pagos(user_id, fecha);

CREATE INDEX IF NOT EXISTS idx_pago_user_tarjeta 
ON pagos(user_id, tarjeta);

-- =============================
-- DATOS INICIALES TARJETAS
-- =============================
INSERT INTO tarjetas (nombre, dia_corte, dias_pago) VALUES
('BBVA', 3, 23),
('AMEX', 3, 23),
('NU', 15, 25),
('BANAMEX', 8, 28),
('MERCADOPAGO', 7, 18),
('MERCADOPRESTAMO', 11, 11),
('DIDICARD', 17, 4),
('SUBURBIA', 14, 14)
ON CONFLICT (nombre) DO NOTHING;

-- =============================
-- SEGURIDAD BÁSICA (OWASP)
-- =============================

-- evitar inserts inválidos
ALTER TABLE movimientos
    ADD CONSTRAINT chk_tipo_valido CHECK (tipo IN ('CONTADO','MSI'));

-- evitar meses inconsistentes
ALTER TABLE movimientos
    ADD CONSTRAINT chk_meses_vs_tipo CHECK (
        (tipo = 'CONTADO' AND meses = 1)
        OR (tipo = 'MSI' AND meses > 1)
    );

-- =============================
-- VISTA OPCIONAL (DEBUG / PRO)
-- =============================
CREATE OR REPLACE VIEW vista_deuda AS
SELECT 
    m.user_id,
    m.tarjeta,
    SUM(m.monto) AS total_gastado,
    COALESCE(p.total_pagado,0) AS total_pagado,
    SUM(m.monto) - COALESCE(p.total_pagado,0) AS deuda
FROM movimientos m
LEFT JOIN (
    SELECT user_id, tarjeta, SUM(monto) total_pagado
    FROM pagos
    GROUP BY user_id, tarjeta
) p
ON m.user_id = p.user_id AND m.tarjeta = p.tarjeta
GROUP BY m.user_id, m.tarjeta, p.total_pagado;