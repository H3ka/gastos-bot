import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import os
import re

# conexión Google Sheets
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
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

#tarjetas
tarjetas = [
    "BBVA", "AMEX", "NU", "BANAMEX",
    "MERCADOPAGO", "MERCADOPRESTAMO", "DIDICARD","SUBURBIA"
]

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💸 Envíame tus gastos así: 100.00"
    )

# manejar mensajes
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    user_id = update.message.from_user.id
    texto = update.message.text.strip()
    if not update.message:
        print("no update message return")
        return

    # 🔁 si está esperando método
    if user_id in user_data_temp:
        if texto not in metodos:
            await update.message.reply_text("⚠️ Elige un número válido")
            return

        metodo = metodos[texto]
        data = user_data_temp[user_id]
        monto = data["monto"]

        # obtener mes actual
        mes_actual = meses[datetime.now().strftime("%m")]

        try:
            worksheet = client.open("gastos-bot").worksheet(metodo)

            headers = worksheet.row_values(3)
            # limpiar espacios
            headers_limpios = [h.strip().upper() for h in headers]
            col_index = headers_limpios.index(mes_actual) + 1
            print(f"Columna para {mes_actual}: {col_index}")

            col_values = worksheet.col_values(col_index)
            print(f"Valores actuales en columna {col_index}: {col_values}")
            col_values = worksheet.col_values(col_index)

            fila = 2  # empezar después del encabezado
            for i, val in enumerate(col_values[1:], start=2):
                if val == "":
                    fila = i
                    break
            else:
                fila = len(col_values) + 1

            worksheet.update_cell(fila, col_index, monto)
            print(f"Actualizado metodo {metodo} monto {monto} en fila {fila}, columna {col_index}")

            del user_data_temp[user_id]

            await update.message.reply_text(
                f"✅ Guardado en {metodo}\n"
            )

        except Exception as e:
            if user_id in user_data_temp:
                del user_data_temp[user_id]
            await update.message.reply_text("❌ Error al guardar")
            print("Error: " + str(e))

        return

    # 🟢 nuevo gasto
    try:
        monto = float(texto)

        user_data_temp[user_id] = {
            "monto": monto
        }

        await update.message.reply_text(
            "💳 ¿Con qué método pagaste?\n\n"
            "1. BBVA\n"
            "2. AMEX\n"
            "3. NU\n"
            "4. BANAMEX\n"
            "5. MERCADOPAGO\n"
            "6. MERCADOPRESTAMO\n"
            "7. DIDICARD\n"
            "8. SUBURBIA"
        )

    except:
        await update.message.reply_text("⚠️ Ingresa unicamente el monto, sin texto adicional")

async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            return
        print("Generando resumen...")
        mes_actual = meses[datetime.now().strftime("%m")]
        total_general = 0

        mensaje = f"📊 Resumen de {mes_actual}\n\n"

        for tarjeta in tarjetas:
            try:
                worksheet = client.open("gastos-bot").worksheet(tarjeta)

                # obtener encabezados y limpiar
                headers = worksheet.row_values(3)
                headers_limpios = [h.strip().upper() for h in headers]

                if mes_actual not in headers_limpios:
                    print(f"{mes_actual} no encontrado en {tarjeta}, saltando")
                    continue

                col_index = headers_limpios.index(mes_actual) + 1

                # 👇 LEER TOTAL DIRECTO (fila 4)
                total_cell = worksheet.cell(4, col_index).value
                print(f"Valor total en {tarjeta} para {mes_actual}: '{total_cell}'")

                try:
                    total_tarjeta = convertir_a_float(total_cell)
                except:
                    total_tarjeta = 0

                if total_tarjeta > 0:
                    print(f"Total para {tarjeta}: {total_tarjeta}")
                    mensaje += f"{tarjeta}: ${round(total_tarjeta, 2)}\n"
                    total_general += total_tarjeta

            except Exception as e:
                print(f"Error en {tarjeta}: {e}")
                continue

        mensaje += f"\n💰 Total general: ${round(total_general, 2)}"

        await update.message.reply_text(mensaje)
        print("Resumen generado:\n" + "MES: " + mes_actual + "Total: " + str(total_general))
    except Exception as e:
        await update.message.reply_text("❌ Error al generar resumen")
        print(e)

def convertir_a_float(valor):
    if not valor:
        return 0

    valor = str(valor).strip()

    # ignorar casos tipo "-"
    if valor in ["-", "$ -", "$ -   "]:
        return 0

    # quitar símbolos y espacios
    valor = re.sub(r"[^\d,.-]", "", valor)

    # convertir formato europeo a estándar
    valor = valor.replace(".", "").replace(",", ".")

    try:
        return float(valor)
    except:
        return 0

# main
if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("resumen", resumen))

    print("Bot corriendo...")
    app.run_polling()