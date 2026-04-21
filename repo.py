from db import db
from datetime import datetime

class FinanzasRepo:

    # ---------------- RESUMEN ----------------
    def resumen(self, user_id):
        conn, cur = db.get_cursor()
        try:
            cur.execute("""
            WITH config AS (
                SELECT nombre, dia_corte, dias_pago FROM tarjetas
            ),
            ciclo AS (
                SELECT nombre, dia_corte, dias_pago,
                CASE 
                    WHEN EXTRACT(DAY FROM CURRENT_DATE) >= dia_corte
                    THEN make_date(EXTRACT(YEAR FROM CURRENT_DATE)::int, EXTRACT(MONTH FROM CURRENT_DATE)::int, dia_corte)
                    ELSE make_date(EXTRACT(YEAR FROM CURRENT_DATE - INTERVAL '1 month')::int,
                                   EXTRACT(MONTH FROM CURRENT_DATE - INTERVAL '1 month')::int,
                                   dia_corte)
                END AS corte
                FROM config
            ),
            rango AS (
                SELECT nombre,
                (corte + INTERVAL '1 day')::date AS inicio,
                (corte + INTERVAL '1 month')::date AS fin,
                dias_pago, corte
                FROM ciclo
            ),
            movimientos_expandidos AS (
                SELECT 
                    m.user_id,
                    m.tarjeta,
                    CASE WHEN m.tipo = 'CONTADO' THEN m.monto ELSE m.monto / m.meses END AS monto,
                    CASE WHEN m.tipo = 'CONTADO' THEN m.fecha ELSE (m.fecha + (i * INTERVAL '1 month'))::date END AS fecha
                FROM movimientos m
                LEFT JOIN generate_series(0, 48) AS i 
                    ON m.tipo = 'MSI' AND i < m.meses
                WHERE m.user_id = %s
            ),
            cargos AS (
                SELECT r.nombre, SUM(me.monto) AS total
                FROM rango r
                LEFT JOIN movimientos_expandidos me 
                ON me.tarjeta = r.nombre AND me.fecha BETWEEN r.inicio AND r.fin
                GROUP BY r.nombre
            ),
            pagos_sum AS (
                SELECT r.nombre, SUM(p.monto) AS pagado
                FROM rango r
                LEFT JOIN pagos p 
                ON p.tarjeta = r.nombre 
                AND p.fecha BETWEEN r.inicio AND r.fin
                AND p.user_id = %s
                GROUP BY r.nombre
            )
            SELECT 
                r.nombre,
                COALESCE(c.total,0) total,
                COALESCE(p.pagado,0) pagado,
                GREATEST(COALESCE(c.total,0)-COALESCE(p.pagado,0),0) pendiente,
                (r.corte + (r.dias_pago || ' days')::interval)::date fecha_limite
            FROM rango r
            LEFT JOIN cargos c ON r.nombre = c.nombre
            LEFT JOIN pagos_sum p ON r.nombre = p.nombre;
            """, (user_id, user_id))

            return cur.fetchall()

        finally:
            cur.close()
            db.release_conn(conn)

    # ---------------- DEUDA REAL ----------------
    def deuda(self, user_id, tarjeta):
        conn, cur = db.get_cursor()
        try:
            cur.execute("""
            SELECT pendiente FROM (
                SELECT 
                    r.nombre,
                    GREATEST(COALESCE(c.total,0)-COALESCE(p.pagado,0),0) pendiente
                FROM (
                    SELECT nombre FROM tarjetas WHERE nombre = %s
                ) r
                LEFT JOIN (
                    SELECT tarjeta, SUM(monto) total
                    FROM movimientos
                    WHERE user_id = %s AND tarjeta = %s
                    GROUP BY tarjeta
                ) c ON r.nombre = c.tarjeta
                LEFT JOIN (
                    SELECT tarjeta, SUM(monto) pagado
                    FROM pagos
                    WHERE user_id = %s AND tarjeta = %s
                    GROUP BY tarjeta
                ) p ON r.nombre = p.tarjeta
            ) t;
            """, (tarjeta, user_id, tarjeta, user_id, tarjeta))

            res = cur.fetchone()
            return res["pendiente"] if res else 0

        finally:
            cur.close()
            db.release_conn(conn)

    # ---------------- INSERT MOVIMIENTO ----------------
    def guardar_mov(self, user_id, tarjeta, monto, tipo, meses):
        conn, cur = db.get_cursor()
        try:
            cur.execute("""
            INSERT INTO movimientos (user_id, fecha, tarjeta, monto, tipo, meses)
            VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                user_id,
                datetime.now().date(),
                tarjeta,
                monto,
                tipo,
                meses
            ))
            conn.commit()
        except:
            conn.rollback()
            raise
        finally:
            cur.close()
            db.release_conn(conn)

    # ---------------- INSERT PAGO ----------------
    def guardar_pago(self, user_id, tarjeta, monto):
        conn, cur = db.get_cursor()
        try:
            cur.execute("""
            INSERT INTO pagos (user_id, fecha, tarjeta, monto)
            VALUES (%s,%s,%s,%s)
            """, (
                user_id,
                datetime.now().date(),
                tarjeta,
                monto
            ))
            conn.commit()
        except:
            conn.rollback()
            raise
        finally:
            cur.close()
            db.release_conn(conn)