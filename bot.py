import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from service import service
import psycopg2

load_dotenv()

# ---------------- CONFIG ----------------

metodos = {
    "1": "BBVA","2": "AMEX","3": "NU","4": "BANAMEX",
    "5": "MERCADOPAGO","6": "MERCADOPRESTAMO","7": "DIDICARD","8": "SUBURBIA"
}

user_state = {}

# ---------------- VALIDACIONES ----------------

def validar_monto(x):
    try:
        x = float(x)
        return round(x, 2) if 0 < x < 1_000_000 else None
    except:
        return None

def validar_meses(x):
    try:
        x = int(x)
        return x if 1 <= x <= 48 else None
    except:
        return None

def menu_tarjetas():
    return "\n".join([f"{k}. {v}" for k,v in metodos.items()])

# ---------------- COMANDOS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    service.init_user(uid)

    await update.message.reply_text(
        "💸 Envíame un monto para registrar gasto\n"
        "Ejemplo: 250.50\n\n"
        "Comandos:\n"
        "/resumen\n"
        "/deuda 1\n"
        "/pagar 1000"
    )

async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    service.init_user(uid)

    data = service.resumen(uid)

    msg = "📊 Resumen (ciclo actual)\n\n"
    total = 0

    for r in data:
        if r["total"] == 0 and r["pagado"] == 0:
            continue

        msg += (
            f"{r['nombre']}\n"
            f"Total: ${round(r['total'],2)}\n"
            f"Pagado: ${round(r['pagado'],2)}\n"
            f"Pendiente: ${round(r['pendiente'],2)}\n"
            f"Fecha límite: {r['fecha_limite']}\n\n"
        )

        total += r["pendiente"]

    msg += f"💰 Total pendiente: ${round(total,2)}"
    await update.message.reply_text(msg)

async def deuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    service.init_user(uid)

    if not context.args:
        await update.message.reply_text(
            "Uso: /deuda 1\n\nTarjetas:\n" + menu_tarjetas()
        )
        return

    tarjeta = metodos.get(context.args[0])

    if not tarjeta:
        await update.message.reply_text("❌ opción inválida")
        return

    d = service.deuda(uid, tarjeta)

    if d <= 0:
        await update.message.reply_text(f"✅ No debes en {tarjeta}")
    else:
        await update.message.reply_text(
            f"💳 {tarjeta}\nPendiente: ${round(d,2)}"
        )

async def pagar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    service.init_user(uid)

    monto = validar_monto(context.args[0]) if context.args else None

    if not monto:
        await update.message.reply_text("❌ Uso: /pagar 1000")
        return

    user_state[uid] = {
        "estado": "pagar_tarjeta",
        "monto": monto
    }

    await update.message.reply_text(
        "💳 ¿A qué tarjeta pagar?\n\n" + menu_tarjetas()
    )

# ---------------- HANDLER ----------------

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    txt = update.message.text.strip()

    service.init_user(uid)

    # ---------------- FLUJOS ----------------

    if uid in user_state:
        data = user_state[uid]
        estado = data["estado"]

        # -------- PAGO --------
        if estado == "pagar_tarjeta":
            if txt not in metodos:
                await update.message.reply_text("❌ opción inválida")
                return

            tarjeta = metodos[txt]
            res = service.pagar(uid, tarjeta, data["monto"])

            if res == "NO_DEUDA":
                await update.message.reply_text("⚠️ No tienes deuda")
            elif res != "OK":
                await update.message.reply_text(
                    f"⚠️ Excede deuda (${round(res,2)})"
                )
            else:
                await update.message.reply_text("💸 Pago registrado")

            user_state.pop(uid, None)
            return

        # -------- TIPO --------
        if estado == "tipo":
            if txt == "1":
                data["tipo"] = "CONTADO"
                data["meses"] = 1
                data["estado"] = "tarjeta"

            elif txt == "2":
                data["tipo"] = "MSI"
                data["estado"] = "meses"
                await update.message.reply_text("📆 ¿A cuántos meses? (1-48)")
                return
            else:
                await update.message.reply_text("❌ 1 o 2")
                return

            await update.message.reply_text("💳 Tarjeta:\n\n" + menu_tarjetas())
            return

        # -------- MESES --------
        if estado == "meses":
            meses = validar_meses(txt)

            if not meses:
                await update.message.reply_text("❌ Ingresa meses válidos (1-48)")
                return

            data["meses"] = meses
            data["estado"] = "tarjeta"

            await update.message.reply_text("💳 Tarjeta:\n\n" + menu_tarjetas())
            return

        # -------- TARJETA --------
        if estado == "tarjeta":
            if txt not in metodos:
                await update.message.reply_text("❌ opción inválida")
                return

            tarjeta = metodos[txt]

            service.guardar(
                uid,
                tarjeta,
                data["monto"],
                data["tipo"],
                data["meses"]
            )

            await update.message.reply_text("✅ Gasto guardado")

            user_state.pop(uid, None)
            return

    # ---------------- NUEVO INPUT ----------------

    monto = validar_monto(txt)

    if monto:
        user_state[uid] = {
            "estado": "tipo",
            "monto": monto
        }

        await update.message.reply_text(
            "💳 Tipo de compra:\n\n"
            "1. Contado\n"
            "2. MSI"
        )
        return

    await update.message.reply_text("❌ Envía solo un monto válido")

# ---------------- MAIN ----------------
def init_db():
    try:
        db_url = os.getenv("DATABASE_URL")

        if not db_url:
            raise Exception("DATABASE_URL no definida")

        # 🔥 detectar entorno correctamente
        if "localhost" in db_url or "127.0.0.1" in db_url:
            sslmode = "disable"
        else:
            sslmode = "require"

        conn = psycopg2.connect(
            db_url,
            sslmode=sslmode
        )

        cur = conn.cursor()

        with open("schema.sql", "r", encoding="utf-8") as f:
            cur.execute(f.read())

        conn.commit()
        cur.close()
        conn.close()

        print("✅ DB lista")

    except Exception as e:
        print("❌ Error init DB:", e)


if __name__ == "__main__":
    print("🚀 Bot iniciando")
    # 🔥 INIT DB AUTOMÁTICO
    init_db()
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", resumen))
    app.add_handler(CommandHandler("deuda", deuda))
    app.add_handler(CommandHandler("pagar", pagar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🚀 Bot Corriendo")
    app.run_polling()