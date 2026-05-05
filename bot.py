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

# ================= GOOGLE =================

creds = get_google_credentials()
client = gspread.authorize(creds)

sheet = client.open(get_sheet())
ws_mov = sheet.worksheet("MOVIMIENTOS")
ws_pag = sheet.worksheet("PAGOS")
ws_tar = sheet.worksheet("TARJETAS")

# ================= STATE =================

user_state = {}

# ================= TARJETAS =================

def get_tarjetas():
    rows = ws_tar.get_all_values()[1:]
    data = {}

    for r in rows:
        data[r[0].strip().upper()] = {
            "corte": int(r[1]),
            "pago": int(r[2])
        }

    return data

# ================= FECHAS =================

def obtener_corte_actual(tarjeta, tarjetas):
    hoy = datetime.now().date()
    dia = tarjetas[tarjeta]["corte"]

    if hoy.day >= dia:
        return datetime(hoy.year, hoy.month, dia).date()
    else:
        return (datetime(hoy.year, hoy.month, 1) - timedelta(days=1)).replace(day=dia).date()

def obtener_corte_anterior(corte):
    if corte.month == 1:
        return corte.replace(year=corte.year - 1, month=12)
    return corte.replace(month=corte.month - 1)

def siguiente_corte(tarjeta, tarjetas):
    return obtener_corte_actual(tarjeta, tarjetas) + relativedelta(months=1)

def rango_ciclo_cerrado(tarjeta, tarjetas):
    corte = obtener_corte_actual(tarjeta, tarjetas)
    corte_anterior = obtener_corte_anterior(corte)

    inicio = corte_anterior + timedelta(days=1)
    fin = corte

    return inicio, fin, corte

def rango_ciclo_proximo(tarjeta, tarjetas):
    corte = obtener_corte_actual(tarjeta, tarjetas)
    sig = corte + relativedelta(months=1)

    inicio = corte + timedelta(days=1)
    fin = sig

    return inicio, fin, sig

def fecha_limite_cerrado(tarjeta, tarjetas):
    corte = obtener_corte_actual(tarjeta, tarjetas)
    return corte + timedelta(days=tarjetas[tarjeta]["pago"])

def fecha_limite_proximo(tarjeta, tarjetas):
    sig = siguiente_corte(tarjeta, tarjetas)
    return sig + timedelta(days=tarjetas[tarjeta]["pago"])

# ================= DATA =================

def parse_date(value):
    return datetime.fromisoformat(value).date()

def get_movimientos():
    rows = ws_mov.get_all_values()[1:]
    data = []

    for r in rows:
        try:
            data.append({
                "fecha": parse_date(r[0]),
                "tarjeta": r[1].strip().upper(),
                "monto": float(r[2].replace(",", ".")),
                "tipo": r[3],
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
                "fecha": parse_date(r[0]),
                "tarjeta": r[1].strip().upper(),
                "monto": float(r[2].replace(",", "."))
            })
        except:
            continue

    return data

# ================= LOGICA =================

def calcular_cerrado():
    tarjetas = get_tarjetas()
    movs = get_movimientos()
    pagos = get_pagos()

    resultado = {}

    for t in tarjetas:
        inicio, fin, corte = rango_ciclo_cerrado(t, tarjetas)
        corte_anterior = obtener_corte_anterior(corte)
        limite = fecha_limite_cerrado(t, tarjetas)

        total = 0

        for m in movs:
            if m["tarjeta"] != t:
                continue

            # 🔥 TODO ya es date → comparación segura
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
            if p["tarjeta"] == t and corte_anterior < p["fecha"] <= limite
        )

        pendiente = max(0, total - pagado)

        if total > 0 or pagado > 0:
            resultado[t] = {
                "pendiente": round(pendiente, 2),
                "corte": corte,
                "limite": limite
            }

    return resultado

def calcular_proximo():
    tarjetas = get_tarjetas()
    movs = get_movimientos()

    resultado = {}

    for t in tarjetas:
        inicio, fin, corte = rango_ciclo_proximo(t, tarjetas)

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

        if total > 0:
            resultado[t] = {
                "pendiente": round(total, 2),
                "corte": corte,
                "limite": fecha_limite_proximo(t, tarjetas)
            }

    return resultado

# ================= UI =================

def teclado_tarjetas():
    tarjetas = list(get_tarjetas().keys())

    keyboard = [
        [InlineKeyboardButton(t, callback_data=f"tarjeta|{t}")]
        for t in tarjetas
    ]

    return InlineKeyboardMarkup(keyboard)

# ================= BOT =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.clear()
    await update.message.reply_text("💳 Ingresa un monto para registrar gasto")

async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cerrado = calcular_cerrado()
    proximo = calcular_proximo()

    msg = "📊 Estado de cuenta\n\n"
    total_cerrado = 0

    for t, d in cerrado.items():
        msg += (
            f"💳 {t}\n"
            f"🧾 Corte: {d['corte']}\n"
            f"📅 Límite: {d['limite']}\n"
            f"💰 Pendiente: ${d['pendiente']}\n\n"
        )
        total_cerrado += d["pendiente"]

    msg += f"💰 Total a pagar: ${round(total_cerrado,2)}\n\n"
    msg += "📈 Próximo corte\n\n"

    total_prox = 0

    for t, d in proximo.items():
        msg += (
            f"💳 {t}\n"
            f"🧾 Corte: {d['corte']}\n"
            f"📅 Límite: {d['limite']}\n"
            f"💰 Pendiente: ${d['pendiente']}\n\n"
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

    await update.message.reply_text("Selecciona tarjeta:", reply_markup=teclado_tarjetas())

async def botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")

    if data[0] == "tarjeta":
        tarjeta = data[1]

        if user_state.get("estado") == "pago":
            cerrado = calcular_cerrado()
            deuda = cerrado.get(tarjeta, {}).get("pendiente", 0)

            if deuda <= 0:
                await query.edit_message_text("⚠️ No debes en esta tarjeta")
                user_state.clear()
                return

            if user_state["monto"] > deuda:
                await query.edit_message_text(f"⚠️ Excede deuda (${deuda})")
                return

            ws_pag.append_row([
                datetime.now().strftime("%Y-%m-%d"),
                tarjeta,
                user_state["monto"]
            ])

            user_state.clear()
            await query.edit_message_text("💸 Pago registrado")
            return

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    try:
        monto = float(text)
        user_state.update({"monto": monto, "estado": "tipo"})
        await update.message.reply_text("1 Contado\n2 MSI")
    except:
        await update.message.reply_text("❌ Ingresa un número válido")

async def comando_invalido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("❌ Comando no válido")

# ================= MAIN =================

if __name__ == "__main__":
    app = ApplicationBuilder().token(get_token()).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", resumen))
    app.add_handler(CommandHandler("pagar", pagar))

    app.add_handler(CallbackQueryHandler(botones))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(MessageHandler(filters.COMMAND, comando_invalido))

    print("Bot iniciado...")
    app.run_polling()