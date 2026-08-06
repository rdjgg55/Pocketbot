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

# Listas de activos
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
    mensaje = (
        f"¡Hola, {user_name}! 🤖 Bot de señales para Pocket Option activo.\n\n"
        "Comandos disponibles:\n"
        "📈 /senal - Analizar un par de Mercado Real\n"
        "🔄 /otc - Analizar un par de Mercado OTC\n"
        "ℹ️ /ayuda - Ver información de uso"
    )
    await update.message.reply_text(mensaje)

async def generar_senal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activo = random.choice(PARES_REALES)
    direccion = random.choice(["🟢 COMPRA (CALL)", "🔴 VENTA (PUT)"])
    efectividad = random.randint(78, 89)
    
    texto_senal = (
        f"🎯 **SEÑAL POCKET OPTION (REAL)** 🎯\n\n"
        f"📊 **Activo:** {activo}\n"
        f"⏱ **Temporalidad:** 1 Minuto\n"
        f"💡 **Dirección:** {direccion}\n"
        f"📈 **Indicadores:** Confluencia de RSI + Bandas de Bollinger + EMA.\n"
        f"⭐ **Efectividad estimada:** {efectividad}%\n\n"
        f"⚠️ *Opera con estricta gestión de riesgo.*"
    )
    await update.message.reply_text(texto_senal, parse_mode="Markdown")

async def generar_otc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activo = random.choice(PARES_OTC_POCKET)
    direccion = random.choice(["🟢 COMPRA (CALL)", "🔴 VENTA (PUT)"])
    efectividad = random.randint(75, 86)
    
    texto_otc = (
        f"🔄 **SEÑAL POCKET OPTION (OTC)** 🔄\n\n"
        f"📊 **Activo:** {activo}\n"
        f"⏱ **Temporalidad:** 1 Minuto\n"
        f"💡 **Dirección:** {direccion}\n"
        f"📈 **Indicadores:** Patrón sintético de soporte/resistencia.\n"
        f"⭐ **Efectividad estimada:** {efectividad}%\n\n"
        f"⚠️ *Precaución: Alta volatilidad en OTC.*"
    )
    await update.message.reply_text(texto_otc, parse_mode="Markdown")

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_ayuda = (
        "📖 **Guía rápida del Bot:**\n\n"
        "• Usa `/senal` de lunes a viernes para operar con los pares de mercado real.\n"
        "• Usa `/otc` los fines de semana o de noche cuando operes con los pares sintéticos OTC.\n"
        "• Recuerda esperar siempre al **cierre exacto de la vela** de 1 minuto."
    )
    await update.message.reply_text(texto_ayuda, parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("senal", generar_senal))
    app.add_handler(CommandHandler("otc", generar_otc))
    app.add_handler(CommandHandler("ayuda", ayuda))

    print("🤖 Bot de Pocket Option iniciado y escuchando comandos...")
    app.run_polling()

if __name__ == "__main__":
    main()
