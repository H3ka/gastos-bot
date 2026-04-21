from repo import FinanzasRepo

repo = FinanzasRepo()

class FinanzasService:

    # ---------------- INIT USER ----------------
    def init_user(self, user_id):
        # crea usuario si no existe (idempotente)
        conn, cur = repo.db.get_cursor() if hasattr(repo, "db") else (None, None)
        try:
            # mejor delegarlo a repo si quieres más limpio
            cur.execute("""
                INSERT INTO usuarios (id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
            """, (user_id,))
            conn.commit()
        except:
            if conn:
                conn.rollback()
        finally:
            if cur:
                cur.close()
            if conn:
                repo.db.release_conn(conn)

    # ---------------- RESUMEN ----------------
    def resumen(self, user_id):
        return repo.resumen(user_id)

    # ---------------- DEUDA ----------------
    def deuda(self, user_id, tarjeta):
        data = repo.resumen(user_id)
        for r in data:
            if r["nombre"] == tarjeta:
                return r["pendiente"]
        return 0

    # ---------------- PAGAR ----------------
    def pagar(self, user_id, tarjeta, monto):
        deuda = self.deuda(user_id, tarjeta)

        if deuda <= 0:
            return "NO_DEUDA"

        if monto > deuda:
            return deuda

        repo.guardar_pago(user_id, tarjeta, monto)
        return "OK"

    # ---------------- GUARDAR ----------------
    def guardar(self, user_id, tarjeta, monto, tipo, meses):
        repo.guardar_mov(user_id, tarjeta, monto, tipo, meses)


service = FinanzasService()