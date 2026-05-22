from multiprocessing import context

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
ws_config = sheet.worksheet("CONFIG")

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

def get_config():
    rows = ws_config.get_all_values()[1:]

    data = {}

    for r in rows:
        try:
            data[r[0].strip()] = float(r[1])
        except:
            data[r[0].strip()] = 0

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
    hoy = datetime.now().date()

    dia_corte = tarjetas[tarjeta]["corte"]

    # último corte
    if hoy.day >= dia_corte:
        corte_actual = datetime(hoy.year, hoy.month, dia_corte).date()
    else:
        if hoy.month == 1:
            corte_actual = datetime(hoy.year - 1, 12, dia_corte).date()
        else:
            corte_actual = datetime(hoy.year, hoy.month - 1, dia_corte).date()

    # corte anterior
    if corte_actual.month == 1:
        corte_anterior = datetime(corte_actual.year - 1, 12, dia_corte).date()
    else:
        corte_anterior = datetime(corte_actual.year, corte_actual.month - 1, dia_corte).date()

    # 🔥 ESTE ES EL FIX
    inicio = corte_anterior
    fin = corte_actual - timedelta(days=1)

    return inicio, fin, corte_actual

def rango_ciclo_proximo(tarjeta, tarjetas):
    hoy = datetime.now().date()

    dia_corte = tarjetas[tarjeta]["corte"]

    # corte actual
    if hoy.day >= dia_corte:
        corte_actual = datetime(hoy.year, hoy.month, dia_corte).date()
    else:
        if hoy.month == 1:
            corte_actual = datetime(hoy.year - 1, 12, dia_corte).date()
        else:
            corte_actual = datetime(hoy.year, hoy.month - 1, dia_corte).date()

    # siguiente corte
    if corte_actual.month == 12:
        siguiente = datetime(corte_actual.year + 1, 1, dia_corte).date()
    else:
        siguiente = datetime(corte_actual.year, corte_actual.month + 1, dia_corte).date()

    # 🔥 FIX
    inicio = corte_actual
    fin = siguiente - timedelta(days=1)

    return inicio, fin, siguiente

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
            tipo = str(r[3]).strip().upper()

            # normalizar
            if "MSI" in tipo:
                tipo = "MSI"
            else:
                tipo = "CONTADO"

            data.append({
                "fecha": datetime.strptime(r[0], "%Y-%m-%d").date(),
                "tarjeta": r[1].strip().upper(),
                "monto": float(str(r[2]).replace(",", ".")),
                "tipo": tipo,
                "meses": int(float(r[4]))
            })

        except Exception as e:
            print("ERROR MOV:", r, e)
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

    IGNORAR = ["EFECTIVO", "DEBITO"]

    for t in tarjetas:
        if t in IGNORAR:
            continue

        inicio, fin, corte = rango_ciclo_cerrado(t, tarjetas)
        corte_anterior = obtener_corte_anterior(corte)
        limite = fecha_limite_cerrado(t, tarjetas)

        total = 0

        for m in movs:
            if m["tarjeta"] != t:
                continue

            # 🔥 TODO ya es date → comparación segura
            if m["tipo"] == "CONTADO":
                if inicio <= m["fecha"] <= fin:
                    total += m["monto"]
            elif m["tipo"] == "MSI":
                mensual = m["monto"] / m["meses"]
                for i in range(m["meses"]):
                    fecha_msi = m["fecha"] + relativedelta(months=i)
                    if inicio <= fecha_msi <= fin:
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

    IGNORAR = ["EFECTIVO", "DEBITO"]
    
    for t in tarjetas:
        if t in IGNORAR:
            continue
        inicio, fin, corte = rango_ciclo_proximo(t, tarjetas)

        total = 0

        for m in movs:
            if m["tarjeta"] != t:
                continue

            if m["tipo"] == "CONTADO":
                if inicio <= m["fecha"] <= fin:
                    total += m["monto"]
            elif m["tipo"] == "MSI":
                mensual = m["monto"] / m["meses"]
                for i in range(m["meses"]):
                    fecha_msi = m["fecha"] + relativedelta(months=i)
                    if inicio <= fecha_msi <= fin:
                        total += mensual

        if total > 0:
            resultado[t] = {
                "pendiente": round(total, 2),
                "corte": corte,
                "limite": fecha_limite_proximo(t, tarjetas)
            }

    return resultado

def calcular_gastos_reales():
    movs = get_movimientos()

    efectivo = 0
    debito = 0

    for m in movs:
        if m["tarjeta"] == "EFECTIVO":
            efectivo += m["monto"]

        elif m["tarjeta"] == "DEBITO":
            debito += m["monto"]

    return {
        "efectivo": round(efectivo, 2),
        "debito": round(debito, 2),
        "total": round(efectivo + debito, 2)
    }

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

 # ================= REGISTRAR PAGO =================

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

    # ================= REGISTRAR GASTO =================

        if user_state.get("estado") == "tarjeta":

            ws_mov.append_row([
                datetime.now().strftime("%Y-%m-%d"),
                tarjeta,
                user_state["monto"],
                user_state["tipo"],
                user_state["meses"]
            ])

            monto = user_state["monto"]

            user_state.clear()

            await query.edit_message_text(
                f"✅ Gasto registrado\n💳 {tarjeta}\n💰 ${monto}"
            )

            return

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    estado = user_state.get("estado")

    # ================= ESPERANDO MONTO =================

    if estado is None:
        try:
            monto = float(text)

            user_state["monto"] = monto
            user_state["estado"] = "tipo"

            await update.message.reply_text(
                "Selecciona tipo:\n\n1️⃣ Contado\n2️⃣ MSI"
            )

        except:
            await update.message.reply_text("❌ Ingresa un monto válido")

        return

    # ================= ESPERANDO TIPO =================

    if estado == "tipo":

        if text == "1":
            user_state["tipo"] = "CONTADO"
            user_state["meses"] = 1
            user_state["estado"] = "tarjeta"

            await update.message.reply_text(
                "Selecciona tarjeta:",
                reply_markup=teclado_tarjetas()
            )

            return

        elif text == "2":
            user_state["tipo"] = "MSI"
            user_state["estado"] = "meses"

            await update.message.reply_text(
                "¿A cuántos meses?"
            )

            return

        else:
            await update.message.reply_text(
                "❌ Escribe 1 para Contado o 2 para MSI"
            )

            return

    # ================= ESPERANDO MESES =================

    if estado == "meses":

        try:
            meses = int(text)

            if meses <= 0:
                raise Exception()

            user_state["meses"] = meses
            user_state["estado"] = "tarjeta"

            await update.message.reply_text(
                "Selecciona tarjeta:",
                reply_markup=teclado_tarjetas()
            )

        except:
            await update.message.reply_text(
                "❌ Ingresa un número válido de meses"
            )

        return

async def comando_invalido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("❌ Comando no válido")

async def flujo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = get_config()

    sueldo = config.get("sueldo", 0)
    gastos_fijos = config.get("gastos_fijos", 0)
    ahorro = config.get("ahorro_objetivo", 0)

    proximo = calcular_proximo()

    deuda = sum(
        d["pendiente"]
        for d in proximo.values()
    )
    gastos = calcular_gastos_reales()

    saldos = calcular_saldos()

    gasto_real = gastos["total"]

    disponible = sueldo - deuda - gastos_fijos - ahorro - gasto_real

    dias_restantes = 30
    diario = disponible / dias_restantes

    msg = (
        "💰 Flujo mensual\n\n"
        f"💵 Sueldo: ${round(sueldo,2)}\n"
        f"🏠 Gastos fijos: ${round(gastos_fijos,2)}\n"
        f"📈 Ahorro objetivo: ${round(ahorro,2)}\n"
        f"💳 Próximos pagos: ${round(deuda,2)}\n\n"
        f"💵 Efectivo/Débito: ${round(gasto_real,2)}\n\n"
        f"🏦 Saldo débito: ${saldos['debito']}\n"
        f"💵 Saldo efectivo: ${saldos['efectivo']}\n\n"
        "━━━━━━━━━━━━━━\n\n"
        f"💸 Disponible real: ${round(disponible,2)}\n"
        f"📅 Disponible diario: ${round(diario,2)}\n\n"
    )

    if disponible < 0:
        msg += "⚠️ Estás en déficit"
    else:
        msg += "✅ Flujo saludable"

    await update.message.reply_text(msg)

def calcular_saldos():
    config = get_config()
    movs = get_movimientos()

    saldo_debito = config.get("saldo_debito", 0)
    saldo_efectivo = config.get("saldo_efectivo", 0)

    for m in movs:

        # DEBITO
        if m["tarjeta"] == "DEBITO":
            saldo_debito -= m["monto"]

        # EFECTIVO
        elif m["tarjeta"] == "EFECTIVO":
            saldo_efectivo -= m["monto"]

    return {
        "debito": round(saldo_debito, 2),
        "efectivo": round(saldo_efectivo, 2)
    }

# ================= MAIN =================

if __name__ == "__main__":
    app = ApplicationBuilder().token(get_token()).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", resumen))
    app.add_handler(CommandHandler("pagar", pagar))
    app.add_handler(CommandHandler("flujo", flujo))

    app.add_handler(CallbackQueryHandler(botones))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(MessageHandler(filters.COMMAND, comando_invalido))


    async def error_handler(update, context):
        print(context.error)

    app.add_error_handler(error_handler)
    print("Bot iniciado...")
    app.run_polling(drop_pending_updates=True)