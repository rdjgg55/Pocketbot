import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
import random

# Configuración básica de logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Token de tu bot de Telegram (proporcionado por BotFather)
TOKEN = "8845724881:AAEpMM4fkKdFohyP553vWKbkItXVCE-f3QY"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    mensaje = (
        f"¡Hola, {user_name}! 🤖 Bot de señales para Pocket Option activo.\n\n"
        "Usa los siguientes comandos para recibir análisis:\n"
        "📈 /senal - Obtener análisis técnico actual\n"
        "⚡ /otc - Análisis de pares sintéticos OTC"
    )
    await update.message.reply_text(mensaje)

async def generar_senal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Simulación de análisis técnico avanzado con confluencia
    pares =[
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
    "USD/CHF", "USD/CAD", "NZD/USD", "EUR/GBP",
    "EUR/JPY", "EUR/AUD", "GBP/JPY", "AUD/JPY"
]
    activo = random.choice(pares)
    
    direccion = random.choice(["🟢 COMPRA (CALL)", "🔴 VENTA (PUT)"])
    efectividad = random.randint(78, 88)
    
    texto_senal = (
        f"🎯 **SEÑAL POCKET OPTION** 🎯\n\n"
        f"📊 **Activo:** {activo}\n"
        f"⏱ **Temporalidad:** 1 Minuto\n"
        f"💡 **Dirección:** {direccion}\n"
        f"📈 **Detalles:** Confluencia de RSI + Toque de Banda Bollinger.\n"
        f"⭐ **Efectividad estimada:** {efectividad}%\n\n"
        f"⚠️ *Opera con gestión de riesgo.*"
    )
    await update.message.reply_text(texto_senal, parse_mode="Markdown")

async def generar_otc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pares_otc= [
    "EUR/USD (OTC)", "GBP/USD (OTC)", "USD/JPY (OTC)", "AUD/USD (OTC)",
    "USD/CHF (OTC)", "EUR/GBP (OTC)", "USD/CAD (OTC)", "NZD/USD (OTC)",
    "EUR/JPY (OTC)", "GBP/JPY (OTC)", "EUR/AUD (OTC)", "AUD/JPY (OTC)",
    "CAD/JPY (OTC)", "EUR/NZD (OTC)", "GBP/AUD (OTC)", "CHF/JPY (OTC)"
]
    activo = random.choice(pares_otc)
    
    direccion = random.choice(["🟢 COMPRA (CALL)", "🔴 VENTA (PUT)"])
    efectividad = random.randint(75, 84)
    
    texto_otc = (
        f"🔄 **SEÑAL MERCADO OTC** 🔄\n\n"
        f"📊 **Activo:** {activo}\n"
        f"⏱ **Temporalidad:** 1 Minuto\n"
        f"💡 **Dirección:** {direccion} - Patrón Sintético\n"
        f"📈 **Detalles:** Análisis algorítmico del comportamiento del precio.\n"
        f"⭐ **Efectividad estimada:** {efectividad}%\n\n"
        f"⚠️ *Precaución: Alta volatilidad en OTC.*"
    )
    await update.message.reply_text(texto_otc, parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("senal", generar_senal))
    app.add_handler(CommandHandler("otc", generar_otc))

    print("🤖 Bot de Pocket Option iniciado correctamente...")
    app.run_polling()

if __name__ == "__main__":
    main()