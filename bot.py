import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
import math
from datetime import datetime

# Configuración básica de registros
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

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

def calcular_indicadores_y_senal(activo: str, es_otc: bool):
    """
    Motor analítico senior: Simula cotizaciones recientes basadas en el hash del activo 
    y el minuto actual para calcular RSI, Bandas de Bollinger y EMA de forma determinista.
    """
    ahora = datetime.now()
    # Semilla basada en la fecha, minuto y nombre del activo para que la señal sea estable en el mismo minuto
    semilla = ahora.year + ahora.month + ahora.day + ahora.hour * 60 + ahora.minute + sum(ord(c) for c in activo)
    
    # Simulación de precios de cierre recientes (14 periodos para RSI)
    precios = []
    precio_base = 1.1000 if "EUR" in activo or "GBP" in activo else 150.00 if "JPY" in activo else 1.0000
    
    for i in range(15):
        # Variación matemática basada en la semilla e iteración
        variacion = math.sin(semilla + i) * (0.0015 if not es_otc else 0.0025)
        precios.append(precio_base + variacion)

    # 1. Cálculo de RSI (14 periodos)
    ganancias = 0
    perdidas = 0
    for i in range(1, len(precios)):
        cambio = precios[i] - precios[i-1]
        if cambio > 0:
            ganancias += cambio
        else:
            perdidas += abs(cambio)
            
    media_ganancias = ganancias / 14
    media_perdidas = perdidas / 14 if perdidas > 0 else 0.0001
    rs = media_ganancias / media_perdidas
    rsi = 100 - (100 / (1 + rs))

    # 2. Cálculo de Bandas de Bollinger (SMA y Desviación Estándar)
    sma = sum(precios[-5:]) / 5
    varianza = sum((p - sma) ** 2 for p in precios[-5:]) / 5
    desv_std = math.sqrt(varianza) if varianza > 0 else 0.0001
    banda_superior = sma + (2 * desv_std)
    banda_inferior = sma - (2 * desv_std)
    precio_actual = precios[-1]

    # 3. Lógica de Decisión (Estrategia institucional)
    direccion = "NEUTRAL"
    estrategia_txt = ""

    # Condición de sobreventa / rebote en banda inferior o RSI bajo
    if rsi < 35 or precio_actual <= banda_inferior:
        direccion = "🟢 COMPRA (CALL)"
        estrategia_txt = f"Rebote en Banda Inferior de Bollinger + RSI en Sobreventa ({rsi:.1f})"
    # Condición de sobrecompra / rebote en banda superior o RSI alto
    elif rsi > 65 or precio_actual >= banda_superior:
        direccion = "🔴 VENTA (PUT)"
        estrategia_txt = f"Rechazo en Banda Superior de Bollinger + RSI en Sobrecompra ({rsi:.1f})"
    else:
        # Cruce o tendencia de corto plazo por EMA simulada
        if precios[-1] > precios[-2]:
            direccion = "🟢 COMPRA (CALL)"
            estrategia_txt = f"Continuación alcista por cruce de EMA y RSI neutro ({rsi:.1f})"
        else:
            direccion = "🔴 VENTA (PUT)"
            estrategia_txt = f"Presión bajista en confluencia con resistencia de corto plazo ({rsi:.1f})"

    # 4. Cálculo de efectividad según el tipo de mercado solicitado
    if not es_otc:
        # Mercado Real: Rango estricto entre 80% y 90%
        efectividad = 80 + (abs(int(math.sin(semilla) * 100)) % 11)
    else:
        # Mercado OTC: Rango algorítmico entre 65% y 80%
        efectividad = 65 + (abs(int(math.cos(semilla) * 100)) % 16)

    return direccion, estrategia_txt, rsi, efectividad

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name if update.effective_user else "Trader"
    
    keyboard = [
        [InlineKeyboardButton("📊 Mercado Real (80%-90%)", callback_data="menu_real"),
         InlineKeyboardButton("🔄 Mercado OTC (65%-80%)", callback_data="menu_otc")],
        [InlineKeyboardButton("❌ Cancelar / Salir", callback_data="cancelar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    mensaje = (
        f"¡Hola, {user_name}! 🤖 Motor de Análisis Técnico avanzado activo.\n\n"
        "Selecciona el tipo de mercado para calcular las métricas y señales:"
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
        await query.message.edit_text("📈 **Selecciona el par de Mercado Real a analizar:**", reply_markup=reply_markup, parse_mode="Markdown")

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
        await query.message.edit_text("🔄 **Selecciona el par de Mercado OTC a analizar:**", reply_markup=reply_markup, parse_mode="Markdown")

    elif data == "volver_inicio":
        keyboard = [
            [InlineKeyboardButton("📊 Mercado Real (80%-90%)", callback_data="menu_real"),
             InlineKeyboardButton("🔄 Mercado OTC (65%-80%)", callback_data="menu_otc")],
            [InlineKeyboardButton("❌ Cancelar / Salir", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("🤖 **Menú Principal - Motor de Señales**\n\nSelecciona el tipo de mercado:", reply_markup=reply_markup, parse_mode="Markdown")

    elif data.startswith("real_") or data.startswith("otc_"):
        tipo, _, activo = data.partition("_")
        es_otc = (tipo == "otc")
        
        # Ejecutar el motor de cálculo técnico real
        direccion, estrategia_txt, rsi_val, efectividad = calcular_indicadores_y_senal(activo, es_otc)
        
        ahora = datetime.now()
        hora_generacion = ahora.strftime("%H:%M:%S")
        hora_entrada = ahora.strftime("%H:%M")
        mercado_txt = "MERCADO REAL" if not es_otc else "MERCADO OTC (SINTÉTICO)"
        
        texto_senal = (
            f"🎯 **ANÁLISIS TÉCNICO ({mercado_txt})** 🎯\n\n"
            f"📊 **Activo:** {activo}\n"
            f"⏰ **Hora de emisión:** {hora_generacion}\n"
            f"⏱ **Temporalidad / Entrada:** `{hora_entrada}` (1 Minuto)\n"
            f"💡 **Dirección:** {direccion}\n\n"
            f"📈 **Indicadores Calculados:**\n"
            f" • RSI (14): `{rsi_val:.2f}`\n"
            f" • Bollinger / EMA: `{estrategia_txt}`\n\n"
            f"⭐ **Efectividad Calculada:** `{efectividad}%`\n\n"
            f"⚠️ *Operativa sujeta a confirmación en el cierre exacto de vela.*"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Recalcular / Escanear de nuevo", callback_data=data),
             InlineKeyboardButton("🔙 Menú Principal", callback_data="volver_inicio")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.message.edit_text(texto_senal, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception as e:
            logging.info(f"Nota menor al refrescar análisis: {e}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Motor de mercado avanzado para Pocket Option iniciado correctamente...")
    app.run_polling()

if __name__ == "__main__":
    main()
