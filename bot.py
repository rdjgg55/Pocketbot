import os
import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.volatility import BollingerBands

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

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
        "Configúrala en Railway > Variables."
    )

MIN_SCORE = 75
MIN_CANDLES = 80

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("SIGNAL_BOT_V6")


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
# CONVERTIR OTC → PAR REAL
# ============================================================

def otc_to_real(pair):

    """
    EUR/USD-OTC -> EUR/USD
    GBP/JPY-OTC -> GBP/JPY
    """

    return pair.replace("-OTC", "")


# ============================================================
# OBTENER DATOS
# ============================================================

def get_price_data(pair, timeframe):

    # --------------------------------------------------------
    # Si es OTC usamos el equivalente REAL como referencia.
    # --------------------------------------------------------

    clean_pair = otc_to_real(pair)

    symbol = REAL_PAIRS.get(clean_pair)

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

        # Compatibilidad yfinance
        if isinstance(
            df.columns,
            pd.MultiIndex
        ):
            df.columns = (
                df.columns
                .get_level_values(0)
            )

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        if not all(
            c in df.columns
            for c in required
        ):
            return pd.DataFrame()

        df = df[required].copy()

        df.dropna(
            inplace=True
        )

        # ----------------------------------------------------
        # 1 MIN
        # ----------------------------------------------------

        if timeframe == "1m":
            return df

        # ----------------------------------------------------
        # 2 MIN
        # ----------------------------------------------------

        if timeframe == "2m":

            df = df.resample(
                "2min"
            ).agg({

                "Open": "first",

                "High": "max",

                "Low": "min",

                "Close": "last",

                "Volume": "sum",

            })

        # ----------------------------------------------------
        # 5 MIN
        # ----------------------------------------------------

        elif timeframe == "5m":

            df = df.resample(
                "5min"
            ).agg({

                "Open": "first",

                "High": "max",

                "Low": "min",

                "Close": "last",

                "Volume": "sum",

            })

        df.dropna(
            inplace=True
        )

        return df

    except Exception:

        logger.exception(
            "Error obteniendo datos para %s",
            pair
        )

        return pd.DataFrame()


# ============================================================
# INDICADORES
# ============================================================

def calculate_indicators(df):

    if (
        df.empty
        or len(df) < MIN_CANDLES
    ):
        return pd.DataFrame()

    df = df.copy()

    close = df["Close"]

    # ========================================================
    # EMA
    # ========================================================

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

    # ========================================================
    # RSI
    # ========================================================

    df["RSI"] = RSIIndicator(
        close=close,
        window=14
    ).rsi()

    # ========================================================
    # MACD
    # ========================================================

    macd = MACD(
        close=close,
        window_fast=12,
        window_slow=26,
        window_sign=9
    )

    df["MACD"] = macd.macd()

    df["MACD_SIGNAL"] = (
        macd.macd_signal()
    )

    df["MACD_HIST"] = (
        macd.macd_diff()
    )

    # ========================================================
    # ADX
    # ========================================================

    adx = ADXIndicator(
        high=df["High"],
        low=df["Low"],
        close=close,
        window=14
    )

    df["ADX"] = adx.adx()

    df["DI_PLUS"] = adx.adx_pos()

    df["DI_MINUS"] = adx.adx_neg()

    # ========================================================
    # BOLLINGER
    # ========================================================

    bb = BollingerBands(
        close=close,
        window=20,
        window_dev=2
    )

    df["BB_HIGH"] = (
        bb.bollinger_hband()
    )

    df["BB_LOW"] = (
        bb.bollinger_lband()
    )

    df.dropna(
        inplace=True
    )

    return df


# ============================================================
# MOTOR DE SEÑALES
# ============================================================

def analyze_market(
    pair,
    timeframe
):

    df = get_price_data(
        pair,
        timeframe
    )

    if df.empty:

        return {
            "signal": False,
            "reason": "NO_DATA"
        }

    df = calculate_indicators(
        df
    )

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
    # 1. TENDENCIA EMA
    # ========================================================

    bullish = (
        current["EMA9"]
        > current["EMA21"]
        > current["EMA50"]
    )

    bearish = (
        current["EMA9"]
        < current["EMA21"]
        < current["EMA50"]
    )

    if bullish:
        call_score += 20

    elif bearish:
        put_score += 20

    # ========================================================
    # 2. PRECIO VS EMA50
    # ========================================================

    if (
        current["Close"]
        > current["EMA50"]
    ):

        call_score += 10

    elif (
        current["Close"]
        < current["EMA50"]
    ):

        put_score += 10

    # ========================================================
    # 3. RSI
    # ========================================================

    rsi = float(
        current["RSI"]
    )

    if 52 <= rsi <= 68:

        call_score += 15

    elif 32 <= rsi <= 48:

        put_score += 15

    # ========================================================
    # 4. MACD
    # ========================================================

    if (
        current["MACD"]
        > current["MACD_SIGNAL"]
        and current["MACD_HIST"] > 0
    ):

        call_score += 15

    elif (
        current["MACD"]
        < current["MACD_SIGNAL"]
        and current["MACD_HIST"] < 0
    ):

        put_score += 15

    # ========================================================
    # 5. ADX
    # ========================================================

    if current["ADX"] >= 20:

        if (
            current["DI_PLUS"]
            > current["DI_MINUS"]
        ):

            call_score += 15

        elif (
            current["DI_MINUS"]
            > current["DI_PLUS"]
        ):

            put_score += 15

    # ========================================================
    # 6. VELA
    # ========================================================

    if (
        current["Close"]
        > current["Open"]
    ):

        call_score += 10

    elif (
        current["Close"]
        < current["Open"]
    ):

        put_score += 10

    # ========================================================
    # 7. MOMENTUM
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
            "call": call_score,
            "put": put_score,
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
# HORA DE ENTRADA
# ============================================================

def get_entry_time(timeframe):

    now = datetime.now(
        timezone.utc
    )

    minutes = TIMEFRAMES[
        timeframe
    ]

    seconds = minutes * 60

    current_timestamp = int(
        now.timestamp()
    )

    next_timestamp = (
        current_timestamp // seconds + 1
    ) * seconds

    return datetime.fromtimestamp(
        next_timestamp,
        timezone.utc
    )


# ============================================================
# /START
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
        ]

    ]

    await update.message.reply_text(
        "🤖 SIGNAL BOT V6\n\n"
        "Selecciona el mercado:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# SELECCIÓN DE PARES
# ============================================================

async def show_pairs(
    query,
    market
):

    if market == "real":

        pairs = list(
            REAL_PAIRS.keys()
        )

        title = (
            "📊 Selecciona un par REAL:"
        )

    else:

        pairs = OTC_PAIRS

        title = (
            "🔄 Selecciona un par OTC:"
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
                "⏱ 1 MIN",
                callback_data=(
                    f"scan|{market}|{pair}|1m"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⏱ 2 MIN",
                callback_data=(
                    f"scan|{market}|{pair}|2m"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⏱ 5 MIN",
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
# ESCANEO
# ============================================================

async def scan_signal(
    query,
    market,
    pair,
    timeframe
):

    await query.message.edit_text(
        "🔎 Buscando oportunidad..."
    )

    result = analyze_market(
        pair,
        timeframe
    )

    # ========================================================
    # SIN DATOS
    # ========================================================

    if result.get(
        "reason"
    ) == "NO_DATA":

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

        message = (
            "⚪ SIN DATOS\n\n"
            "No se pudieron obtener datos "
            "para el análisis."
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

    if not result.get(
        "signal"
    ):

        keyboard = [

            [
                InlineKeyboardButton(
                    "🔄 Escanear nuevamente",
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
            "No existe suficiente "
            "confluencia en este momento.",
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

    entry = get_entry_time(
        timeframe
    )

    entry_text = entry.strftime(
        "%H:%M:%S UTC"
    )

    duration = {
        "1m": "1 minuto",
        "2m": "2 minutos",
        "5m": "5 minutos",
    }[
        timeframe
    ]

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
# CALLBACK HANDLER
# ============================================================

async def button_handler(
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

    if data.startswith(
        "market|"
    ):

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

    if data.startswith(
        "pair|"
    ):

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

    if data.startswith(
        "scan|"
    ):

        _, market, pair, timeframe = data.split(
            "|",
            3
        )

        await scan_signal(
            query,
            market,
            pair,
            timeframe
        )

        return


# ============================================================
# MANEJO DE ERRORES
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
        "======================================"
    )

    logger.info(
        "SIGNAL BOT V6 INICIANDO"
    )

    logger.info(
        "REAL: ACTIVO"
    )

    logger.info(
        "OTC: MODO REFERENCIA REAL"
    )

    logger.info(
        "TIMEFRAMES: 1m / 2m / 5m"
    )

    logger.info(
        "======================================"
    )

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    application.add_error_handler(
        error_handler
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()