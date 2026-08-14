import os
import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.volatility import BollingerBands

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "Falta TELEGRAM_BOT_TOKEN. "
        "Añádelo en Railway > Variables."
    )

MIN_SCORE = 75
MIN_CANDLES = 80

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("SIGNAL_V6")


# ============================================================
# PARES REALES
# ============================================================

REAL_PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "USD/CHF": "USDCHF=X",
    "NZD/USD": "NZDUSD=X",
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "AUD/JPY": "AUDJPY=X",
    "EUR/AUD": "EURAUD=X",
    "GBP/AUD": "GBPAUD=X",
    "CHF/JPY": "CHFJPY=X",
    "EUR/CAD": "EURCAD=X",
    "GBP/CAD": "GBPCAD=X",
    "AUD/NZD": "AUDNZD=X",
    "EUR/NZD": "EURNZD=X",
}


# ============================================================
# PARES OTC
# ============================================================

OTC_PAIRS = [
    "EUR/USD-OTC",
    "GBP/USD-OTC",
    "USD/JPY-OTC",
    "AUD/USD-OTC",
    "USD/CAD-OTC",
    "USD/CHF-OTC",
    "NZD/USD-OTC",
    "EUR/GBP-OTC",
    "EUR/JPY-OTC",
    "GBP/JPY-OTC",
    "AUD/JPY-OTC",
    "EUR/AUD-OTC",
    "GBP/AUD-OTC",
    "CHF/JPY-OTC",
    "EUR/CAD-OTC",
    "GBP/CAD-OTC",
]


TIMEFRAMES = {
    "1m": 1,
    "2m": 2,
    "5m": 5,
}


# ============================================================
# DESCARGA DE DATOS REALES
# ============================================================

def get_real_data(pair, timeframe):

    symbol = REAL_PAIRS.get(pair)

    if not symbol:
        return pd.DataFrame()

    try:

        df = yf.download(
            symbol,
            period="5d",
            interval="1m",
            progress=False,
            auto_adjust=False,
        )

        if df.empty:
            return pd.DataFrame()

        # Compatibilidad con versiones de yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        if not all(
            column in df.columns
            for column in columns
        ):
            return pd.DataFrame()

        df = df[columns].copy()
        df.dropna(inplace=True)

        # El feed base es 1 minuto.
        if timeframe == "2m":

            df = df.resample("2min").agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            })

        elif timeframe == "5m":

            df = df.resample("5min").agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            })

        df.dropna(inplace=True)

        return df

    except Exception:

        logger.exception(
            "Error obteniendo datos de %s",
            pair
        )

        return pd.DataFrame()


# ============================================================
# FUENTE OTC
# ============================================================

def get_otc_data(pair, timeframe):

    """
    IMPORTANTE:

    Esta función NO utiliza Forex REAL como sustituto del OTC.

    Hasta conectar un feed OTC compatible con Pocket Option,
    devuelve DataFrame vacío.

    Esto evita generar señales falsas.
    """

    return pd.DataFrame()


# ============================================================
# INDICADORES
# ============================================================

def add_indicators(df):

    if df.empty or len(df) < MIN_CANDLES:
        return pd.DataFrame()

    df = df.copy()

    close = df["Close"]

    # ----------------------------
    # EMA
    # ----------------------------

    df["EMA9"] = EMAIndicator(
        close=close,
        window=9
    ).ema_indicator()

    df["EMA21"] = EMAIndicator(
        close=close,
        window=21
    ).ema_indicator()

    df["EMA50"] = EMAIndicator(
        close=close,
        window=50
    ).ema_indicator()

    # ----------------------------
    # RSI
    # ----------------------------

    df["RSI"] = RSIIndicator(
        close=close,
        window=14
    ).rsi()

    # ----------------------------
    # MACD
    # ----------------------------

    macd = MACD(
        close=close,
        window_fast=12,
        window_slow=26,
        window_sign=9
    )

    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()
    df["MACD_HIST"] = macd.macd_diff()

    # ----------------------------
    # ADX
    # ----------------------------

    adx = ADXIndicator(
        high=df["High"],
        low=df["Low"],
        close=close,
        window=14
    )

    df["ADX"] = adx.adx()
    df["DI_PLUS"] = adx.adx_pos()
    df["DI_MINUS"] = adx.adx_neg()

    # ----------------------------
    # Bollinger
    # ----------------------------

    bb = BollingerBands(
        close=close,
        window=20,
        window_dev=2
    )

    df["BB_HIGH"] = bb.bollinger_hband()
    df["BB_LOW"] = bb.bollinger_lband()

    df.dropna(inplace=True)

    return df


# ============================================================
# MOTOR DE ANÁLISIS
# ============================================================

def analyze(df):

    if df.empty:
        return {
            "signal": False,
            "reason": "NO_DATA"
        }

    df = add_indicators(df)

    if df.empty:
        return {
            "signal": False,
            "reason": "INSUFFICIENT_DATA"
        }

    current = df.iloc[-1]
    previous = df.iloc[-2]

    call_score = 0
    put_score = 0

    # ========================================================
    # TENDENCIA EMA
    # ========================================================

    if (
        current["EMA9"]
        > current["EMA21"]
        > current["EMA50"]
    ):
        call_score += 20

    elif (
        current["EMA9"]
        < current["EMA21"]
        < current["EMA50"]
    ):
        put_score += 20

    # ========================================================
    # PRECIO VS EMA50
    # ========================================================

    if current["Close"] > current["EMA50"]:
        call_score += 10

    elif current["Close"] < current["EMA50"]:
        put_score += 10

    # ========================================================
    # RSI
    # ========================================================

    rsi = float(current["RSI"])

    if 52 <= rsi <= 68:
        call_score += 15

    elif 32 <= rsi <= 48:
        put_score += 15

    # ========================================================
    # MACD
    # ========================================================

    if (
        current["MACD"] > current["MACD_SIGNAL"]
        and current["MACD_HIST"] > 0
    ):
        call_score += 15

    elif (
        current["MACD"] < current["MACD_SIGNAL"]
        and current["MACD_HIST"] < 0
    ):
        put_score += 15

    # ========================================================
    # ADX
    # ========================================================

    if current["ADX"] >= 20:

        if current["DI_PLUS"] > current["DI_MINUS"]:
            call_score += 15

        elif current["DI_MINUS"] > current["DI_PLUS"]:
            put_score += 15

    # ========================================================
    # VELA
    # ========================================================

    if current["Close"] > current["Open"]:
        call_score += 10

    elif current["Close"] < current["Open"]:
        put_score += 10

    # ========================================================
    # MOMENTUM MACD
    # ========================================================

    if (
        current["MACD_HIST"] > 0
        and current["MACD_HIST"]
        > previous["MACD_HIST"]
    ):
        call_score += 10

    elif (
        current["MACD_HIST"] < 0
        and current["MACD_HIST"]
        < previous["MACD_HIST"]
    ):
        put_score += 10

    # ========================================================
    # DECISIÓN
    # ========================================================

    score = max(
        call_score,
        put_score
    )

    if score < MIN_SCORE:

        return {
            "signal": False,
            "reason": "WEAK_CONFLUENCE",
            "call_score": call_score,
            "put_score": put_score,
        }

    if call_score > put_score:

        return {
            "signal": True,
            "direction": "CALL",
            "score": call_score,
        }

    if put_score > call_score:

        return {
            "signal": True,
            "direction": "PUT",
            "score": put_score,
        }

    return {
        "signal": False,
        "reason": "TIE"
    }


# ============================================================
# OBTENER DATOS SEGÚN MERCADO
# ============================================================

def get_market_analysis(
    market,
    pair,
    timeframe
):

    if market == "real":

        df = get_real_data(
            pair,
            timeframe
        )

    else:

        df = get_otc_data(
            pair,
            timeframe
        )

    return analyze(df)


# ============================================================
# HORA DE ENTRADA
# ============================================================

def next_entry(timeframe):

    now = datetime.now(
        timezone.utc
    )

    minutes = TIMEFRAMES[
        timeframe
    ]

    timestamp = int(
        now.timestamp()
    )

    interval = minutes * 60

    next_timestamp = (
        timestamp // interval + 1
    ) * interval

    return datetime.fromtimestamp(
        next_timestamp,
        timezone.utc
    )


# ============================================================
# MENÚ PRINCIPAL
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [

        [
            InlineKeyboardButton(
                "📊 REAL",
                callback_data="market|real"
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 OTC",
                callback_data="market|otc"
            )
        ],

    ]

    await update.message.reply_text(
        "🤖 SIGNAL BOT V6\n\n"
        "Selecciona el mercado:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# LISTA DE PARES
# ============================================================

async def show_pairs(
    query,
    market
):

    pairs = (
        list(REAL_PAIRS.keys())
        if market == "real"
        else OTC_PAIRS
    )

    keyboard = []

    for i in range(
        0,
        len(pairs),
        2
    ):

        row = [
            InlineKeyboardButton(
                pairs[i],
                callback_data=(
                    f"pair|{market}|{pairs[i]}"
                )
            )
        ]

        if i + 1 < len(pairs):

            row.append(
                InlineKeyboardButton(
                    pairs[i + 1],
                    callback_data=(
                        f"pair|{market}|{pairs[i + 1]}"
                    )
                )
            )

        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(
            "🏠 Menú",
            callback_data="home"
        )
    ])

    title = (
        "📊 Selecciona un par REAL:"
        if market == "real"
        else "🔄 Selecciona un par OTC:"
    )

    await query.message.edit_text(
        title,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# TEMPORALIDADES
# ============================================================

async def show_timeframes(
    query,
    market,
    pair
):

    keyboard = [

        [
            InlineKeyboardButton(
                "1 MIN",
                callback_data=(
                    f"scan|{market}|{pair}|1m"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "2 MIN",
                callback_data=(
                    f"scan|{market}|{pair}|2m"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "5 MIN",
                callback_data=(
                    f"scan|{market}|{pair}|5m"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🔙 Volver",
                callback_data=(
                    f"market|{market}"
                )
            )
        ]

    ]

    await query.message.edit_text(
        f"💎 {pair}\n\n"
        "Selecciona la temporalidad:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# ESCANEAR
# ============================================================

async def scan(
    query,
    market,
    pair,
    timeframe
):

    await query.message.edit_text(
        "🔎 Analizando mercado..."
    )

    result = get_market_analysis(
        market,
        pair,
        timeframe
    )

    # ========================================================
    # SIN DATOS
    # ========================================================

    if result.get("reason") == "NO_DATA":

        keyboard = [

            [
                InlineKeyboardButton(
                    "🔄 Reintentar",
                    callback_data=(
                        f"scan|{market}|{pair}|{timeframe}"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "🏠 Menú",
                    callback_data="home"
                )
            ]

        ]

        if market == "otc":

            message = (
                "⚪ OTC SIN DATOS\n\n"
                "El feed OTC todavía no está "
                "conectado.\n\n"
                "No se utilizarán datos REAL "
                "para fabricar una señal OTC."
            )

        else:

            message = (
                "⚪ SIN DATOS\n\n"
                "No fue posible obtener datos "
                "del mercado."
            )

        await query.message.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    # ========================================================
    # SIN OPORTUNIDAD
    # ========================================================

    if not result.get("signal"):

        keyboard = [

            [
                InlineKeyboardButton(
                    "🔄 Escanear otra vez",
                    callback_data=(
                        f"scan|{market}|{pair}|{timeframe}"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "🔙 Cambiar par",
                    callback_data=(
                        f"market|{market}"
                    )
                )
            ]

        ]

        await query.message.edit_text(
            "⚪ SIN OPORTUNIDAD\n\n"
            "La confluencia actual no supera "
            "el filtro mínimo.",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    # ========================================================
    # SEÑAL
    # ========================================================

    direction = result[
        "direction"
    ]

    entry = next_entry(
        timeframe
    )

    entry_text = entry.strftime(
        "%H:%M:%S UTC"
    )

    duration = {
        "1m": "1 minuto",
        "2m": "2 minutos",
        "5m": "5 minutos",
    }[timeframe]

    emoji = (
        "🟢"
        if direction == "CALL"
        else "🔴"
    )

    message = (
        f"{emoji} {direction}\n\n"
        f"⏰ Entrada: {entry_text}\n"
        f"⏱ Tiempo: {duration}"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "🔄 Escanear",
                callback_data=(
                    f"scan|{market}|{pair}|{timeframe}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🔙 Cambiar par",
                callback_data=(
                    f"market|{market}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 Menú",
                callback_data="home"
            )
        ]

    ]

    await query.message.edit_text(
        message,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# CALLBACKS
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    try:
        await query.answer()
    except Exception:
        pass

    data = query.data

    # --------------------------------------------------------
    # HOME
    # --------------------------------------------------------

    if data == "home":

        keyboard = [

            [
                InlineKeyboardButton(
                    "📊 REAL",
                    callback_data="market|real"
                )
            ],

            [
                InlineKeyboardButton(
                    "🔄 OTC",
                    callback_data="market|otc"
                )
            ]

        ]

        await query.message.edit_text(
            "🤖 SIGNAL BOT V6\n\n"
            "Selecciona el mercado:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    # --------------------------------------------------------
    # MARKET
    # --------------------------------------------------------

    if data.startswith("market|"):

        _, market = data.split(
            "|",
            1
        )

        await show_pairs(
            query,
            market
        )

        return

    # --------------------------------------------------------
    # PAIR
    # --------------------------------------------------------

    if data.startswith("pair|"):

        _, market, pair = data.split(
            "|",
            2
        )

        await show_timeframes(
            query,
            market,
            pair
        )

        return

    # --------------------------------------------------------
    # SCAN
    # --------------------------------------------------------

    if data.startswith("scan|"):

        _, market, pair, timeframe = data.split(
            "|",
            3
        )

        await scan(
            query,
            market,
            pair,
            timeframe
        )

        return


# ============================================================
# ERRORES
# ============================================================

async def error_handler(
    update,
    context
):

    logger.exception(
        "Error del bot: %s",
        context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "===================================="
    )

    logger.info(
        "SIGNAL BOT V6 INICIANDO"
    )

    logger.info(
        "REAL: habilitado"
    )

    logger.info(
        "OTC: esperando fuente OTC"
    )

    logger.info(
        "===================================="
    )

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    app.add_error_handler(
        error_handler
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()