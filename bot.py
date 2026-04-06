import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

conn = sqlite3.connect("gastos.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT,
    monto REAL,
    nota TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💸 Envíame tus gastos así:\n\ncomida 120 tacos")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        texto = update.message.text.split()

        categoria = texto[0]
        monto = float(texto[1])
        nota = " ".join(texto[2:]) if len(texto) > 2 else ""

        cursor.execute(
            "INSERT INTO gastos (categoria, monto, nota) VALUES (?, ?, ?)",
            (categoria, monto, nota)
        )
        conn.commit()

        await update.message.reply_text(
            f"✅ Gasto registrado:\nCategoría: {categoria}\nMonto: ${monto}\nNota: {nota}"
        )

    except:
        await update.message.reply_text("⚠️ Usa: categoria monto nota")

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
        mensaje += f"{cat}: ${monto}\n"
        total += monto

    mensaje += f"\nTotal: ${total}"
    await update.message.reply_text(mensaje)

if __name__ == "__main__":
    import os
    TOKEN = os.getenv("TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gastos", gastos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()