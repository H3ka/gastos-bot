import gspread
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)

from config import get_token, get_google_credentials, get_sheet

print("🔥 Iniciando bot...")

# ================= GOOGLE =================

creds = get_google_credentials()
client = gspread.authorize(creds)

sheet = client.open(get_sheet())
ws_mov = sheet.worksheet("MOVIMIENTOS")
ws_pag = sheet.worksheet("PAGOS")
ws_tar = sheet.worksheet("TARJETAS")

# ================= HELPERS =================

def norm(x):
    return x.strip().upper()

# ================= STATE =================

user_state = {}

# ================= TARJETAS =================

def get_tarjetas():
    rows = ws_tar.get_all_values()[1:]
    data = {}

    for r in rows:
        data[norm(r[0])] = {
            "corte": int(r[1]),
            "pago": int(r[2])
        }

    return data

# ================= CICLO =================

def rango_ciclo(tarjeta, tarjetas):
    hoy = datetime.now().date()
    dia = tarjetas[tarjeta]["corte"]

    if hoy.day >= dia:
        ultimo = datetime(hoy.year, hoy.month, dia).date()
    else:
        if hoy.month == 1:
            ultimo = datetime(hoy.year - 1, 12, dia).date()
        else:
            ultimo = datetime(hoy.year, hoy.month - 1, dia).date()

    if ultimo.month == 12:
        siguiente = datetime(ultimo.year + 1, 1, dia).date()
    else:
        siguiente = datetime(ultimo.year, ultimo.month + 1, dia).date()

    inicio = ultimo + timedelta(days=1)
    fin = siguiente

    return inicio, fin

def corte_actual(tarjeta, tarjetas):
    hoy = datetime.now().date()
    dia = tarjetas[tarjeta]["corte"]

    if hoy.day >= dia:
        return datetime(hoy.year, hoy.month, dia).date()
    else:
        if hoy.month == 1:
            return datetime(hoy.year - 1, 12, dia).date()
        else:
            return datetime(hoy.year, hoy.month - 1, dia).date()


def corte_anterior(corte):
    if corte.month == 1:
        return corte.replace(year=corte.year - 1, month=12)
    else:
        return corte.replace(month=corte.month - 1)


def rango_ciclo_cerrado(tarjeta, tarjetas):
    c_actual = corte_actual(tarjeta, tarjetas)
    c_anterior = corte_anterior(c_actual)

    inicio = c_anterior + timedelta(days=1)  # día después del corte anterior
    fin = c_actual                           # día de corte actual (exclusivo)

    return inicio, fin, c_actual


def fecha_limite_cerrado(tarjeta, tarjetas):
    c_actual = corte_actual(tarjeta, tarjetas)
    return c_actual + timedelta(days=tarjetas[tarjeta]["pago"])


def fecha_limite(tarjeta, tarjetas):
    hoy = datetime.now().date()
    dia = tarjetas[tarjeta]["corte"]

    if hoy.day >= dia:
        corte = datetime(hoy.year, hoy.month, dia).date()
    else:
        if hoy.month == 1:
            corte = datetime(hoy.year - 1, 12, dia).date()
        else:
            corte = datetime(hoy.year, hoy.month - 1, dia).date()

    siguiente = corte + relativedelta(months=1)

    return siguiente + timedelta(days=tarjetas[tarjeta]["pago"])

# ================= DATA =================

def get_movimientos():
    rows = ws_mov.get_all_values()[1:]
    data = []

    for r in rows:
        try:
            data.append({
                "fecha": datetime.strptime(r[0], "%Y-%m-%d").date(),
                "tarjeta": norm(r[1]),
                "monto": float(r[2].replace(",", ".")),
                "tipo": norm(r[3]),
                "meses": int(r[4])
            })
        except:
            continue

    return data

def get_pagos():
    rows = ws_pag.get_all_values()[1:]
    data = []

    for r in rows:
        try:
            data.append({
                "fecha": datetime.strptime(r[0], "%Y-%m-%d").date(),
                "tarjeta": r[1].strip().upper(),
                "monto": float(r[2].replace(",", "."))
            })
        except:
            continue

    return data

# ================= LOGICA =================

def calcular_resumen():
    tarjetas = get_tarjetas()
    movs = get_movimientos()
    pagos = get_pagos()

    resultado = {}

    for t in tarjetas:
        inicio, fin, corte = rango_ciclo_cerrado(t, tarjetas)

        total = 0

        # ===== CARGOS =====
        for m in movs:
            if m["tarjeta"] != t:
                continue

            # CONTADO
            if m["tipo"] == "CONTADO":
                if inicio <= m["fecha"] < fin:
                    total += m["monto"]

            # MSI (incluye MSI que iniciaron antes pero siguen activos)
            else:
                mensual = m["monto"] / m["meses"]

                for i in range(m["meses"]):
                    fecha_msi = m["fecha"] + relativedelta(months=i)

                    if inicio <= fecha_msi < fin:
                        total += mensual

        # ===== PAGOS DEL MISMO CICLO =====
        pagado = sum(
            p["monto"] for p in pagos
            if p["tarjeta"] == t and inicio <= p["fecha"] < fin
        )

        pendiente = max(0, total - pagado)

        if total > 0 or pagado > 0:
            resultado[t] = {
                "total": round(total, 2),
                "pagado": round(pagado, 2),
                "pendiente": round(pendiente, 2),
                "fecha": fecha_limite_cerrado(t, tarjetas),
                "corte": corte
            }

    return resultado

def calcular_proximo_corte():
    tarjetas = get_tarjetas()
    movs = get_movimientos()
    pagos = get_pagos()

    resultado = {}

    for t in tarjetas:
        inicio, fin = rango_ciclo(t, tarjetas)  # 👈 ciclo actual

        total = 0

        for m in movs:
            if m["tarjeta"] != t:
                continue

            if m["tipo"] == "CONTADO":
                if inicio <= m["fecha"] < fin:
                    total += m["monto"]

            else:
                mensual = m["monto"] / m["meses"]

                for i in range(m["meses"]):
                    fecha_msi = m["fecha"] + relativedelta(months=i)

                    if inicio <= fecha_msi < fin:
                        total += mensual

        pagado = sum(
            p["monto"] for p in pagos
            if p["tarjeta"] == t and inicio <= p["fecha"] < fin
        )

        pendiente = max(0, total - pagado)

        if pendiente > 0:
            resultado[t] = {
                "pendiente": round(pendiente, 2)
            }

    return resultado

# ================= UI =================

def teclado_tarjetas():
    tarjetas = list(get_tarjetas().keys())

    keyboard = []
    row = []

    for t in tarjetas:
        row.append(InlineKeyboardButton(t, callback_data=f"tarjeta|{t}"))

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)

# ================= BOT =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.clear()
    await update.message.reply_text("💸 Mándame un monto")

async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cerrado = calcular_resumen()
    proximo = calcular_proximo_corte()

    msg = "📊 Estado de cuenta (cerrado)\n\n"
    total_cerrado = 0

    for t, d in cerrado.items():
        msg += (
            f"{t}\n"          
            f"Pendiente: ${d['pendiente']}\n"
            f"Fecha de corte: {d['fecha']}\n\n"
        )
        total_cerrado += d["pendiente"]

    msg += f"💰 Total cerrado: ${round(total_cerrado,2)}\n\n"

    msg += "📈 Próximo corte (en curso)\n\n"
    total_prox = 0

    for t, d in proximo.items():
        msg += (
            f"{t}\n"
            f"Pendiente: ${d['pendiente']}\n"
            f"Fecha de corte: {d['fecha']}\n\n"
        )
        total_prox += d["pendiente"]

    msg += f"💸 Total próximo: ${round(total_prox,2)}"

    await update.message.reply_text(msg)

async def pagar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto = float(context.args[0])
    except:
        await update.message.reply_text("Uso: /pagar 1000")
        return

    user_state["estado"] = "pago"
    user_state["monto"] = monto

    await update.message.reply_text(
        "Selecciona tarjeta:",
        reply_markup=teclado_tarjetas()
    )

async def botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")

    if data[0] == "tarjeta":
        tarjeta = norm(data[1])

        # ===== PAGO =====
        if user_state.get("estado") == "pago":
            ws_pag.append_row([
                datetime.now().strftime("%Y-%m-%d"),
                tarjeta,
                user_state["monto"]
            ])

            user_state.clear()
            await query.edit_message_text("💸 Pago guardado")
            return

        # ===== GUARDAR MOVIMIENTO =====
        if user_state.get("estado") == "tarjeta":
            ws_mov.append_row([
                datetime.now().strftime("%Y-%m-%d"),
                tarjeta,
                user_state["monto"],
                user_state["tipo"],
                user_state["meses"]
            ])

            user_state.clear()
            await query.edit_message_text("✅ Guardado")
            return

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if user_state:

        if user_state.get("estado") == "tipo":
            if text == "1":
                user_state.update({"tipo": "CONTADO", "meses": 1, "estado": "tarjeta"})
                await update.message.reply_text("Selecciona tarjeta:", reply_markup=teclado_tarjetas())
                return

            elif text == "2":
                user_state.update({"tipo": "MSI", "estado": "meses"})
                await update.message.reply_text("Meses:")
                return

        elif user_state.get("estado") == "meses":
            try:
                user_state["meses"] = int(text)
                user_state["estado"] = "tarjeta"
                await update.message.reply_text("Selecciona tarjeta:", reply_markup=teclado_tarjetas())
            except:
                await update.message.reply_text("❌ número inválido")
            return

    try:
        monto = float(text)
        user_state.update({"monto": monto, "estado": "tipo"})
        await update.message.reply_text("1 Contado\n2 MSI")
    except:
        await update.message.reply_text("❌ manda un número")

async def comando_invalido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("❌ Comando no válido")

# ================= MAIN =================

if __name__ == "__main__":
    app = (
        ApplicationBuilder()
        .token(get_token())
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", resumen))
    app.add_handler(CommandHandler("pagar", pagar))

    app.add_handler(CallbackQueryHandler(botones))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(MessageHandler(filters.COMMAND & filters.TEXT, comando_invalido))

    print("🚀 Bot corriendo...")
    app.run_polling()