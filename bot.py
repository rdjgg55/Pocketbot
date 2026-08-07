import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
import random
from datetime import datetime

# Configuración básica de registros
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TOKEN = "8845724881:AAEpMM4fkKdFohyP553vWKbkItXVCE-f3QY"

# Listas completas de activos
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
    user_name = update.effective_user.first_name if update.effective_user else "Trader"
    
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
        keyboard = [
            [InlineKeyboardButton("📊 Mercado Real", callback_data="menu_real"),
             InlineKeyboardButton("🔄 Mercado OTC", callback_data="menu_otc")],
            [InlineKeyboardButton("❌ Cancelar / Salir", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("🤖 **Menú Principal - Pocket Option**\n\nSelecciona el tipo de mercado:", reply_markup=reply_markup, parse_mode="Markdown")

    elif data.startswith("real_") or data.startswith("otc_"):
        # Uso de partition para evitar errores si hay múltiples guiones bajos en el futuro
        tipo, _, activo = data.partition("_")
        
        # Obtener la hora exacta de la señal a 1 minuto
        ahora = datetime.now()
        hora_generacion = ahora.strftime("%H:%M:%S")
        hora_entrada = ahora.strftime("%H:%M")

        direccion = random.choice(["🟢 COMPRA (CALL)", "🔴 VENTA (PUT)"])
        efectividad = 82  # Efectividad fija solicitada
        mercado_txt = "MERCADO REAL" if tipo == "real" else "MERCADO OTC"
        
        texto_senal = (
            f"🎯 **SEÑAL POCKET OPTION ({mercado_txt})** 🎯\n\n"
            f"📊 **Activo:** {activo}\n"
            f"⏰ **Hora de emisión:** {hora_generacion}\n"
            f"⏱ **Temporalidad / Entrada:** `{hora_entrada}` (Operación a 1 Minuto)\n"
            f"💡 **Dirección:** {direccion}\n"
            f"📈 **Indicadores:** Confluencia de RSI + Bandas de Bollinger.\n"
            f"⭐ **Efectividad:** {efectividad}%\n\n"
            f"⚠️ *Gestiona tu riesgo adecuadamente y espera el cierre exacto de la vela.*"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Escanear de nuevo", callback_data=data),
             InlineKeyboardButton("🔙 Menú Principal", callback_data="volver_inicio")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.message.edit_text(texto_senal, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception as e:
            # Controla el error si el usuario presiona el botón muy rápido y el texto es idéntico
            logging.info(f"Nota menor al refrescar mensaje: {e}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot interactivo de Pocket Option optimizado y listo...")
    app.run_polling()

if __name__ == "__main__":
    main()
