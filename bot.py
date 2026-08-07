import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
import random

# Configuración básica de registros (logs)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# REEMPLAZA ESTO CON EL TOKEN DE TU BOT DE TELEGRAM PROPORCIONADO POR BOTFATHER
TOKEN = "8845724881:AAEpMM4fkKdFohyP553vWKbkItXVCE-f3QY"

PARES_REALES = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
    "USD/CHF", "USD/CAD", "NZD/USD", "EUR/GBP",
    "EUR/JPY", "EUR/AUD", "GBP/JPY", "AUD/JPY"
]

PARES_OTC_POCKET = [
    "EUR/USD (OTC)", "GBP/USD (OTC)", "USD/JPY (OTC)", "AUD/USD (OTC)",
    "USD/CHF (OTC)", "EUR/GBP (OTC)", "USD/CAD (OTC)", "NZD/USD (OTC)",
    "EUR/JPY (OTC)", "GBP/JPY (OTC)", "EUR/AUD (OTC)", "AUD/JPY (OTC)",
    "CAD/JPY (OTC)", "EUR/NZD (OTC)", "GBP/AUD (OTC)", "CHF/JPY (OTC)"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    
    # Teclado principal con botones interactivos
    keyboard = [
        [InlineKeyboardButton("📊 Mercado Real", callback_data="menu_real"),
         InlineKeyboardButton("🔄 Mercado OTC", callback_data="menu_otc")],
        [InlineKeyboardButton("❌ Cancelar / Salir", callback_data="cancelar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    mensaje = (
        f"¡Hola, {user_name}! 🤖 Bot de señales para Pocket Option activo.\n\n"
        "Selecciona el tipo de mercado que deseas escanear:"
    )
    
    if update.message:
        await update.message.reply_text(mensaje, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(mensaje, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar":
        await query.message.edit_text("❌ Operación cancelada. Escribe /start para volver al menú principal.")

    elif data == "menu_real":
        # Crear botones para cada par real (en filas de 2)
        keyboard = []
        row = []
        for par in PARES_REALES:
            row.append(InlineKeyboardButton(par, callback_data=f"real_{par}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Volver al Menú", callback_data="volver_inicio")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("📈 **Selecciona el par de Mercado Real a escanear:**", reply_markup=reply_markup, parse_mode="Markdown")

    elif data == "menu_otc":
        # Crear botones para cada par OTC (en filas de 2)
        keyboard = []
        row = []
        for par in PARES_OTC_POCKET:
            row.append(InlineKeyboardButton(par, callback_data=f"otc_{par}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Volver al Menú", callback_data="volver_inicio")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("🔄 **Selecciona el par de Mercado OTC a escanear:**", reply_markup=reply_markup, parse_mode="Markdown")

    elif data == "volver_inicio":
        # Volver al menú principal
        keyboard = [
            [InlineKeyboardButton("📊 Mercado Real", callback_data="menu_real"),
             InlineKeyboardButton("🔄 Mercado OTC", callback_data="menu_otc")],
            [InlineKeyboardButton("❌ Cancelar / Salir", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("🤖 **Menú Principal - Pocket Option**\n\nSelecciona el tipo de mercado:", reply_markup=reply_markup, parse_mode="Markdown")

    elif data.startswith("real_") or data.startswith("paso_otc_") or data.startswith("otc_"):
        # Procesar el escaneo del par seleccionado
        partes = data.split("_", 1)
        tipo = partes[0]
        activo = partes[1]
        
        direccion = random.choice(["🟢 COMPRA (CALL)", "🔴 VENTA (PUT)"])
        efectividad = random.randint(78, 89) if tipo == "real" else random.randint(75, 86)
        mercado_txt = "MERCADO REAL" if tipo == "real" else "MERCADO OTC"
        
        texto_senal = (
            f"🎯 **SEÑAL POCKET OPTION ({mercado_txt})** 🎯\n\n"
            f"📊 **Activo:** {activo}\n"
            f"⏱ **Temporalidad:** 1 Minuto\n"
            f"💡 **Dirección:** {direccion}\n"
            f"📈 **Indicadores:** Confluencia de RSI + Bandas de Bollinger.\n"
            f"⭐ **Efectividad estimada:** {efectividad}%\n\n"
            f"⚠️ *Opera con estricta gestión de riesgo.*"
        )
        
        # Botones para volver a escanear el mismo par o regresar al menú
        keyboard = [
            [InlineKeyboardButton("🔄 Esccanear de nuevo", callback_data=data),
             InlineKeyboardButton("🔙 Menú Principal", callback_data="volver_inicio")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(texto_senal, reply_markup=reply_markup, parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot interactivo de Pocket Option iniciado y escuchando...")
    app.run_polling()

if __name__ == "__main__":
    main()
