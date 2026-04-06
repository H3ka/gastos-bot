import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# conexión DB
conn = sqlite3.connect("gastos.db", check_same_thread=False)
cursor = conn.cursor()

# crear tabla
cursor.execute("""
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT,
    monto REAL,
    nota TEXT,
    metodo TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💸 Envíame tus gastos así:\n\n"
        "categoria monto nota metodo\n\n"
        "Ejemplo:\ncomida 120 tacos efectivo\n\n"
        "CATEGORIA | GASTO | DESCRIPCION | METODO DE PAGO"
    )

# guardar gasto
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        texto = update.message.text.split()

        categoria = texto[0]
        monto = float(texto[1])

        metodo = texto[-1] if len(texto) > 2 else "efectivo"
        nota = " ".join(texto[2:-1]) if len(texto) > 3 else ""

        cursor.execute(
            "INSERT INTO gastos (categoria, monto, nota, metodo) VALUES (?, ?, ?, ?)",
            (categoria, monto, nota, metodo)
        )
        conn.commit()

        # total del día
        cursor.execute("""
            SELECT SUM(monto)
            FROM gastos
            WHERE DATE(fecha) = DATE('now')
        """)

        total = cursor.fetchone()[0]
        if total is None:
            total = 0

        await update.message.reply_text(
            f"✅ Gasto registrado:\n"
            f"Categoría: {categoria}\n"
            f"Monto: ${monto}\n"
            f"Método: {metodo}\n"
            f"Nota: {nota}\n\n"
            f"💰 Total de hoy: ${round(total, 2)}"
        )

    except:
        await update.message.reply_text(
            "⚠️ Formato inválido.\nUsa:\ncomida 120 tacos efectivo"
        )

# resumen del día
async def gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT categoria, SUM(monto)
        FROM gastos
        WHERE DATE(fecha) = DATE('now')
        GROUP BY categoria
    """)

    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("No hay gastos hoy.")
        return

    mensaje = "📊 Gastos de hoy:\n\n"
    total = 0

    for cat, monto in rows:
        mensaje += f"{cat}: ${round(monto, 2)}\n"
        total += monto

    mensaje += f"\n💰 Total: ${round(total, 2)}"

    await update.message.reply_text(mensaje)

# resumen por método de pago
async def metodos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT metodo, SUM(monto)
        FROM gastos
        WHERE DATE(fecha) = DATE('now')
        GROUP BY metodo
    """)

    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("No hay gastos hoy. ")
        return

    mensaje = "💳 Gastos por método (hoy):\n\n"
    total = 0

    for metodo, monto in rows:
        mensaje += f"{metodo}: ${round(monto, 2)}\n"
        total += monto

    mensaje += f"\n💰 Total: ${round(total, 2)}"

    await update.message.reply_text(mensaje)

# main
if __name__ == "__main__":
    import os
    TOKEN = os.getenv("TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gastos", gastos))
    app.add_handler(CommandHandler("metodos", metodos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot corriendo...")
    app.run_polling()