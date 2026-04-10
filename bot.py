import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
from config import get_token, get_google_credentials
import re
import traceback

try:
    print("🔥 Iniciando bot...")

    # conexión Google Sheets
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = get_google_credentials(scope, ServiceAccountCredentials)
    client = gspread.authorize(creds)

    # estado temporal
    user_data_temp = {}

    # mapa de métodos
    metodos = {
        "1": "BBVA",
        "2": "AMEX",
        "3": "NU",
        "4": "BANAMEX",
        "5": "MERCADOPAGO",
        "6": "MERCADOPRESTAMO",
        "7": "DIDICARD",
        "8": "SUBURBIA"
    }

    # meses
    meses = {
        "01": "ENERO", "02": "FEBRERO", "03": "MARZO",
        "04": "ABRIL", "05": "MAYO", "06": "JUNIO",
        "07": "JULIO", "08": "AGOSTO", "09": "SEPTIEMBRE",
        "10": "OCTUBRE", "11": "NOVIEMBRE", "12": "DICIEMBRE"
    }

    MESES_LIST = [
        "ENERO","FEBRERO","MARZO","ABRIL","MAYO","JUNIO",
        "JULIO","AGOSTO","SEPTIEMBRE","OCTUBRE","NOVIEMBRE","DICIEMBRE"
    ]

    # tarjetas
    tarjetas = [
        "BBVA", "AMEX", "NU", "BANAMEX",
        "MERCADOPAGO", "MERCADOPRESTAMO", "DIDICARD","SUBURBIA"
    ]

    # ---------------- UTILIDADES ----------------

    def obtener_mes_actual():
        return meses[datetime.now().strftime("%m")]

    def obtener_mes_siguiente(mes_actual, offset):
        idx = MESES_LIST.index(mes_actual)
        return MESES_LIST[(idx + offset) % 12]

    def agregar_gasto(metodo, mes, monto):
        worksheet = client.open("gastos-bot").worksheet(metodo)

        headers = worksheet.row_values(3)
        headers_limpios = [h.strip().upper() for h in headers]

        col_index = headers_limpios.index(mes) + 1

        col_values = worksheet.col_values(col_index)

        fila = 2
        for i, val in enumerate(col_values[1:], start=2):
            if val == "":
                fila = i
                break
        else:
            fila = len(col_values) + 1

        worksheet.update_cell(fila, col_index, monto)

    # ---------------- BOT ----------------

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("💸 Envíame solo el monto (ej: 1200)")

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

        if not update.message:
            return

        user_id = update.message.from_user.id
        texto = update.message.text.strip()

        # ---------------- FLUJO ----------------

        if user_id in user_data_temp:
            estado = user_data_temp[user_id].get("estado")

            # -------- TIPO --------
            if estado == "tipo":
                if texto == "1":
                    user_data_temp[user_id]["tipo"] = "contado"
                    user_data_temp[user_id]["estado"] = "metodo"

                    await update.message.reply_text(
                        "💳 Método:\n1 BBVA\n2 AMEX\n3 NU\n4 BANAMEX\n5 MERCADOPAGO\n6 MERCADOPRESTAMO\n7 DIDICARD\n8 SUBURBIA"
                    )

                elif texto == "2":
                    user_data_temp[user_id]["tipo"] = "msi"
                    user_data_temp[user_id]["estado"] = "meses"

                    await update.message.reply_text("📆 ¿A cuántos meses?")

                else:
                    await update.message.reply_text("❌ Opción inválida")

                return

            # -------- MESES --------
            if estado == "meses":
                if not texto.isdigit():
                    await update.message.reply_text("❌ Ingresa un número válido")
                    return

                meses_val = int(texto)

                if meses_val <= 0:
                    await update.message.reply_text("❌ Meses inválidos")
                    return

                user_data_temp[user_id]["meses"] = meses_val
                user_data_temp[user_id]["estado"] = "metodo"

                await update.message.reply_text(
                    "💳 Método:\n1 BBVA\n2 AMEX\n3 NU\n4 BANAMEX\n5 MERCADOPAGO\n6 MERCADOPRESTAMO\n7 DIDICARD\n8 SUBURBIA"
                )
                return

            # -------- MÉTODO --------
            if estado == "metodo":
                if texto not in metodos:
                    await update.message.reply_text("⚠️ Elige un número válido")
                    return

                metodo = metodos[texto]
                data = user_data_temp[user_id]

                monto = data["monto"]
                tipo = data["tipo"]
                mes_actual = obtener_mes_actual()

                try:
                    if tipo == "contado":
                        agregar_gasto(metodo, mes_actual, monto)

                    elif tipo == "msi":
                        meses_val = data["meses"]
                        monto_mensual = round(monto / meses_val, 2)

                        for i in range(meses_val):
                            mes = obtener_mes_siguiente(mes_actual, i)
                            agregar_gasto(metodo, mes, monto_mensual)

                    del user_data_temp[user_id]

                    await update.message.reply_text(
                        f"✅ Guardado en {metodo}\n💰 ${monto}\n El pago fue registrado a {tipo}"
                    )

                except Exception as e:
                    if user_id in user_data_temp:
                        del user_data_temp[user_id]

                    await update.message.reply_text("❌ Error al guardar")
                    print(e)

                return

        # ---------------- NUEVO MONTO ----------------

        try:
            monto = float(texto)

            user_data_temp[user_id] = {
                "monto": monto,
                "estado": "tipo"
            }

            await update.message.reply_text(
                "¿Tipo de compra?\n1. Contado\n2. MSI"
            )

        except:
            await update.message.reply_text("⚠️ Ingresa solo el monto")

    # ---------------- RESUMEN ----------------

    async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not update.message:
                return

            mes_actual = obtener_mes_actual()
            total_general = 0

            mensaje = f"📊 Resumen de {mes_actual}\n\n"

            for tarjeta in tarjetas:
                try:
                    worksheet = client.open("gastos-bot").worksheet(tarjeta)

                    headers = worksheet.row_values(3)
                    headers_limpios = [h.strip().upper() for h in headers]

                    if mes_actual not in headers_limpios:
                        continue

                    col_index = headers_limpios.index(mes_actual) + 1

                    total_cell = worksheet.cell(4, col_index).value

                    total_tarjeta = convertir_a_float(total_cell)

                    if total_tarjeta > 0:
                        mensaje += f"{tarjeta}: ${round(total_tarjeta, 2)}\n"
                        total_general += total_tarjeta

                except:
                    continue

            mensaje += f"\n💰 Total general: ${round(total_general, 2)}"

            await update.message.reply_text(mensaje)

        except Exception as e:
            await update.message.reply_text("❌ Error al generar resumen")
            print(e)

    # ---------------- UTIL ----------------

    def convertir_a_float(valor):
        if not valor:
            return 0

        valor = str(valor).strip()

        if valor in ["-", "$ -", "$ -   "]:
            return 0

        valor = re.sub(r"[^\d,.-]", "", valor)
        valor = valor.replace(".", "").replace(",", ".")

        try:
            return float(valor)
        except:
            return 0

    # ---------------- MAIN ----------------

    if __name__ == "__main__":
        TOKEN = get_token()

        app = ApplicationBuilder().token(TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("resumen", resumen))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        print("🚀 Bot corriendo...")
        app.run_polling()

except Exception as e:
    print("💥 ERROR CRÍTICO:")
    traceback.print_exc()