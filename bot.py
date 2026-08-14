import os
import json
import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import (
    EMAIndicator,
    MACD,
    ADXIndicator,
)
from ta.volatility import (
    BollingerBands,
    AverageTrueRange,
)

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)

from telegram.constants import ParseMode

from telegram.error import (
    Conflict,
    TelegramError,
)

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

if not TOKEN:
    raise RuntimeError(
        "Falta TELEGRAM_BOT_TOKEN en Railway."
    )


MIN_BARS = 120

# Score mínimo para permitir una señal
MIN_SCORE = 68

# Diferencia mínima entre dirección principal
# y dirección contraria.
MIN_EDGE = 12

# Evita demasiadas señales consecutivas
COOLDOWN_SECONDS = 20

STATS_FILE = Path(
    os.getenv(
        "STATS_FILE",
        "signal_stats.json"
    )
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "SIGNAL_BOT_V5"
)


# ============================================================
# PARES
# ============================================================

PAIRS = {

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
# TIMEFRAMES
# ============================================================

TIMEFRAMES = {

    "1m": {
        "label": "1 Minuto",
        "interval": "1m",
        "period": "7d",
        "context": "5m",
        "expiry": 1,
    },

    "2m": {
        "label": "2 Minutos",
        "interval": "2m",
        "period": "7d",
        "context": "5m",
        "expiry": 2,
    },

    "5m": {
        "label": "5 Minutos",
        "interval": "5m",
        "period": "30d",
        "context": "15m",
        "expiry": 5,
    },
}


# ============================================================
# RESULT
# ============================================================

@dataclass
class Signal:

    direction: str

    score: int

    opposite_score: int

    edge: int

    quality: str

    asset: str

    market: str

    timeframe: str

    price: float

    generated_at: str

    reasons: list

    warnings: list


# ============================================================
# STATS
# ============================================================

def load_stats():

    if not STATS_FILE.exists():
        return []

    try:

        with open(
            STATS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return []


def save_stats(data):

    try:

        with open(
            STATS_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False
            )

    except Exception:

        logger.exception(
            "No se pudieron guardar estadísticas."
        )


# ============================================================
# DATA
# ============================================================

def download_data(
    asset,
    timeframe
):

    config = TIMEFRAMES[
        timeframe
    ]

    ticker = PAIRS[
        asset
    ]

    logger.info(
        "DATA %s %s",
        asset,
        timeframe
    )

    df = yf.download(
        ticker,
        period=config["period"],
        interval=config["interval"],
        progress=False,
        auto_adjust=False,
        threads=False,
    )

    if df is None or df.empty:

        raise RuntimeError(
            f"Yahoo no devolvió datos "
            f"para {asset} {timeframe}"
        )

    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        df.columns = (
            df.columns
            .get_level_values(0)
        )

    needed = [
        "Open",
        "High",
        "Low",
        "Close",
    ]

    for column in needed:

        if column not in df.columns:

            raise RuntimeError(
                f"Falta {column}"
            )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df[
        needed
    ].dropna()

    if len(df) < MIN_BARS:

        raise RuntimeError(
            f"Datos insuficientes: "
            f"{len(df)} velas."
        )

    return df


# ============================================================
# INDICATORS
# ============================================================

def indicators(df):

    d = df.copy()

    close = d["Close"]

    d["EMA9"] = EMAIndicator(
        close,
        9
    ).ema_indicator()

    d["EMA21"] = EMAIndicator(
        close,
        21
    ).ema_indicator()

    d["EMA50"] = EMAIndicator(
        close,
        50
    ).ema_indicator()

    d["EMA200"] = EMAIndicator(
        close,
        200
    ).ema_indicator()

    d["RSI"] = RSIIndicator(
        close,
        14
    ).rsi()

    macd = MACD(
        close,
        12,
        26,
        9
    )

    d["MACD"] = macd.macd()

    d["MACD_SIGNAL"] = (
        macd.macd_signal()
    )

    d["MACD_HIST"] = (
        macd.macd_diff()
    )

    bb = BollingerBands(
        close,
        20,
        2
    )

    d["BB_HIGH"] = (
        bb.bollinger_hband()
    )

    d["BB_MID"] = (
        bb.bollinger_mavg()
    )

    d["BB_LOW"] = (
        bb.bollinger_lband()
    )

    atr = AverageTrueRange(
        d["High"],
        d["Low"],
        close,
        14
    )

    d["ATR"] = (
        atr.average_true_range()
    )

    adx = ADXIndicator(
        d["High"],
        d["Low"],
        close,
        14
    )

    d["ADX"] = adx.adx()

    d["DI_PLUS"] = adx.adx_pos()

    d["DI_MINUS"] = adx.adx_neg()

    stoch = StochasticOscillator(
        d["High"],
        d["Low"],
        close,
        14,
        3
    )

    d["STOCH"] = stoch.stoch()

    d["STOCH_SIGNAL"] = (
        stoch.stoch_signal()
    )

    d.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True
    )

    d.dropna(
        inplace=True
    )

    return d


# ============================================================
# MARKET REGIME
# ============================================================

def market_regime(df):

    x = df.iloc[-1]

    adx = float(
        x["ADX"]
    )

    ema9 = float(
        x["EMA9"]
    )

    ema21 = float(
        x["EMA21"]
    )

    ema50 = float(
        x["EMA50"]
    )

    close = float(
        x["Close"]
    )

    if adx < 16:

        return "RANGE"

    if (
        ema9 > ema21
        > ema50
        and close > ema50
    ):

        return "BULL"

    if (
        ema9 < ema21
        < ema50
        and close < ema50
    ):

        return "BEAR"

    return "MIXED"


# ============================================================
# STRUCTURE
# ============================================================

def structure_score(df):

    recent = df.tail(20)

    old = df.iloc[-40:-20]

    call = 0
    put = 0

    reasons = []

    if len(old) < 10:

        return call, put, reasons

    rh = recent["High"].max()
    oh = old["High"].max()

    rl = recent["Low"].min()
    ol = old["Low"].min()

    if rh > oh and rl > ol:

        call += 12

        reasons.append(
            "Estructura HH/HL alcista"
        )

    elif rh < oh and rl < ol:

        put += 12

        reasons.append(
            "Estructura LH/LL bajista"
        )

    return call, put, reasons


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    df,
    context
):

    x = df.iloc[-1]

    call = 0
    put = 0

    call_reasons = []
    put_reasons = []

    warnings = []

    # --------------------------------------------------------
    # EMA 9 / 21
    # --------------------------------------------------------

    if x["EMA9"] > x["EMA21"]:

        call += 10

        call_reasons.append(
            "EMA9 > EMA21"
        )

    else:

        put += 10

        put_reasons.append(
            "EMA9 < EMA21"
        )

    # --------------------------------------------------------
    # EMA50
    # --------------------------------------------------------

    if x["Close"] > x["EMA50"]:

        call += 8

        call_reasons.append(
            "Precio sobre EMA50"
        )

    else:

        put += 8

        put_reasons.append(
            "Precio bajo EMA50"
        )

    # --------------------------------------------------------
    # EMA200
    # --------------------------------------------------------

    if x["Close"] > x["EMA200"]:

        call += 6

        call_reasons.append(
            "Precio sobre EMA200"
        )

    else:

        put += 6

        put_reasons.append(
            "Precio bajo EMA200"
        )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi = float(
        x["RSI"]
    )

    if 52 <= rsi <= 68:

        call += 9

        call_reasons.append(
            f"RSI favorable {rsi:.1f}"
        )

    elif 32 <= rsi <= 48:

        put += 9

        put_reasons.append(
            f"RSI favorable {rsi:.1f}"
        )

    elif rsi >= 75:

        warnings.append(
            f"RSI sobrecomprado {rsi:.1f}"
        )

    elif rsi <= 25:

        warnings.append(
            f"RSI sobrevendido {rsi:.1f}"
        )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    if (
        x["MACD"] >
        x["MACD_SIGNAL"]
        and
        x["MACD_HIST"] > 0
    ):

        call += 12

        call_reasons.append(
            "MACD alcista"
        )

    elif (
        x["MACD"] <
        x["MACD_SIGNAL"]
        and
        x["MACD_HIST"] < 0
    ):

        put += 12

        put_reasons.append(
            "MACD bajista"
        )

    # --------------------------------------------------------
    # ADX + DI
    # --------------------------------------------------------

    adx = float(
        x["ADX"]
    )

    if adx >= 25:

        if x["DI_PLUS"] > x["DI_MINUS"]:

            call += 10

            call_reasons.append(
                f"ADX alcista {adx:.1f}"
            )

        else:

            put += 10

            put_reasons.append(
                f"ADX bajista {adx:.1f}"
            )

    elif adx < 18:

        warnings.append(
            f"Mercado débil/lateral ADX {adx:.1f}"
        )

    # --------------------------------------------------------
    # BOLLINGER
    # --------------------------------------------------------

    close = float(
        x["Close"]
    )

    high = float(
        x["BB_HIGH"]
    )

    low = float(
        x["BB_LOW"]
    )

    middle = float(
        x["BB_MID"]
    )

    if close > middle:

        call += 5

        call_reasons.append(
            "Precio sobre BB media"
        )

    else:

        put += 5

        put_reasons.append(
            "Precio bajo BB media"
        )

    # No comprar ciegamente una sobreextensión
    if close >= high:

        warnings.append(
            "Precio en/sobre banda superior"
        )

    if close <= low:

        warnings.append(
            "Precio en/bajo banda inferior"
        )

    # --------------------------------------------------------
    # STOCHASTIC
    # --------------------------------------------------------

    if (
        x["STOCH"] >
        x["STOCH_SIGNAL"]
        and
        x["STOCH"] < 80
    ):

        call += 5

        call_reasons.append(
            "Stochastic alcista"
        )

    elif (
        x["STOCH"] <
        x["STOCH_SIGNAL"]
        and
        x["STOCH"] > 20
    ):

        put += 5

        put_reasons.append(
            "Stochastic bajista"
        )

    # --------------------------------------------------------
    # STRUCTURE
    # --------------------------------------------------------

    sc, sp, sr = structure_score(
        df
    )

    call += sc
    put += sp

    for reason in sr:

        if "alcista" in reason:

            call_reasons.append(
                reason
            )

        else:

            put_reasons.append(
                reason
            )

    # --------------------------------------------------------
    # CONTEXTO SUPERIOR
    # --------------------------------------------------------

    if (
        context is not None
        and len(context) >= 60
    ):

        c = context.iloc[-1]

        if (
            c["Close"] > c["EMA21"]
            and
            c["EMA21"] > c["EMA50"]
        ):

            call += 15

            call_reasons.append(
                "Contexto superior alcista"
            )

        elif (
            c["Close"] < c["EMA21"]
            and
            c["EMA21"] < c["EMA50"]
        ):

            put += 15

            put_reasons.append(
                "Contexto superior bajista"
            )

        else:

            warnings.append(
                "Contexto superior mixto"
            )

    # --------------------------------------------------------
    # REGIME
    # --------------------------------------------------------

    regime = market_regime(
        df
    )

    if regime == "RANGE":

        warnings.append(
            "Mercado lateral"
        )

    elif regime == "BULL":

        call += 5

    elif regime == "BEAR":

        put += 5

    call = int(
        max(0, min(100, call))
    )

    put = int(
        max(0, min(100, put))
    )

    return {
        "call": call,
        "put": put,
        "call_reasons": call_reasons,
        "put_reasons": put_reasons,
        "warnings": warnings,
        "regime": regime,
    }


# ============================================================
# GENERATE SIGNAL
# ============================================================

def generate_signal(
    asset,
    market,
    timeframe,
    df,
    context
):

    scores = calculate_score(
        df,
        context
    )

    call = scores["call"]
    put = scores["put"]

    if call >= put:

        direction = "CALL"

        score = call

        opposite = put

        reasons = scores[
            "call_reasons"
        ]

    else:

        direction = "PUT"

        score = put

        opposite = call

        reasons = scores[
            "put_reasons"
        ]

    edge = score - opposite

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    if (
        score >= 82
        and edge >= 20
    ):

        quality = "MUY ALTA"

    elif (
        score >= 74
        and edge >= 16
    ):

        quality = "ALTA"

    elif (
        score >= MIN_SCORE
        and edge >= MIN_EDGE
    ):

        quality = "MEDIA"

    else:

        quality = "BAJA"

    price = float(
        df["Close"].iloc[-1]
    )

    return Signal(
        direction=direction,
        score=score,
        opposite_score=opposite,
        edge=edge,
        quality=quality,
        asset=asset,
        market=market,
        timeframe=timeframe,
        price=price,
        generated_at=(
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        reasons=reasons[:10],
        warnings=scores[
            "warnings"
        ][:8],
    )


# ============================================================
# ANALYSIS
# ============================================================

def analyze(
    asset,
    market,
    timeframe
):

    main_raw = download_data(
        asset,
        timeframe
    )

    main = indicators(
        main_raw
    )

    context_tf = TIMEFRAMES[
        timeframe
    ]["context"]

    context_raw = download_data(
        asset,
        context_tf
    )

    context = indicators(
        context_raw
    )

    signal = generate_signal(
        asset,
        market,
        timeframe,
        main,
        context
    )

    return signal


# ============================================================
# ENTRY
# ============================================================

def calculate_entry(
    timeframe
):

    minutes = TIMEFRAMES[
        timeframe
    ]["expiry"]

    now = datetime.now(
        timezone.utc
    )

    current = now.replace(
        second=0,
        microsecond=0
    )

    # Siguiente múltiplo de timeframe
    minute = current.minute

    remainder = (
        minute % minutes
    )

    if remainder == 0:

        entry = current + timedelta(
            minutes=minutes
        )

    else:

        entry = current + timedelta(
            minutes=minutes - remainder
        )

    expiration = (
        entry
        + timedelta(
            minutes=minutes
        )
    )

    return entry, expiration


# ============================================================
# FORMAT SIGNAL
# ============================================================

def signal_text(
    signal
):

    emoji = (
        "🟢"
        if signal.direction == "CALL"
        else "🔴"
    )

    reasons = "\n".join(
        f"• {x}"
        for x in signal.reasons
    )

    warnings = ""

    if signal.warnings:

        warnings = (
            "\n\n⚠️ *Filtros*\n"
            +
            "\n".join(
                f"• {x}"
                for x in signal.warnings
            )
        )

    entry, expiration = (
        calculate_entry(
            signal.timeframe
        )
    )

    text = (

        f"{emoji} *SEÑAL {signal.direction}*\n\n"

        f"💎 Activo: `{signal.asset}`\n"

        f"🏦 Mercado: `{signal.market}`\n"

        f"⏱ Temporalidad: "
        f"`{TIMEFRAMES[signal.timeframe]['label']}`\n\n"

        f"💵 Precio analizado: "
        f"`{signal.price}`\n"

        f"🎯 Score: "
        f"`{signal.score}/100`\n"

        f"↔️ Score contrario: "
        f"`{signal.opposite_score}/100`\n"

        f"📐 Ventaja: "
        f"`{signal.edge}`\n"

        f"⭐ Calidad: "
        f"`{signal.quality}`\n\n"

        f"🔍 *Confirmaciones*\n"
        f"{reasons}"

        f"{warnings}"

        f"\n\n"
        f"⏰ Entrada UTC: "
        f"`{entry.strftime('%H:%M:%S')}`\n"

        f"⏳ Expiración UTC: "
        f"`{expiration.strftime('%H:%M:%S')}`"

        f"\n\n"
        "⚠️ *El score no es una probabilidad "
        "garantizada de ganar.*"
    )

    if signal.market == "OTC":

        text += (
            "\n\n"
            "⚠️ *OTC PROXY*\n"
            "Esta señal usa datos del mercado "
            "real como referencia. No representa "
            "el feed OTC propietario de Pocket Option."
        )

    return text


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.info(
        "/start recibido de %s",
        update.effective_user.id
        if update.effective_user
        else "unknown"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "📊 MERCADO REAL",
                callback_data="market|REAL"
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 MERCADO OTC",
                callback_data="market|OTC"
            )
        ],

        [
            InlineKeyboardButton(
                "📈 ESTADÍSTICAS",
                callback_data="stats"
            )
        ],

    ]

    await update.message.reply_text(
        (
            "🤖 *SIGNAL BOT V5*\n\n"

            "Motor multi-indicador + "
            "multi-timeframe.\n\n"

            "⏱ *Temporalidades*\n"
            "• 1 minuto\n"
            "• 2 minutos\n"
            "• 5 minutos\n\n"

            "🎯 El sistema filtra señales "
            "con baja confluencia.\n\n"

            "Selecciona el mercado:"
        ),
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# MARKET
# ============================================================

async def show_market(
    query,
    market
):

    buttons = []

    assets = list(
        PAIRS.keys()
    )

    for i in range(
        0,
        len(assets),
        2
    ):

        row = []

        for asset in assets[
            i:i + 2
        ]:

            row.append(
                InlineKeyboardButton(
                    asset,
                    callback_data=(
                        f"asset|{market}|{asset}"
                    )
                )
            )

        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            "🏠 Menú",
            callback_data="home"
        )
    ])

    await query.message.edit_text(
        (
            f"📊 *MERCADO {market}*\n\n"
            "Selecciona el par:"
        ),
        reply_markup=InlineKeyboardMarkup(
            buttons
        ),
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# TIMEFRAME
# ============================================================

async def show_timeframes(
    query,
    market,
    asset
):

    buttons = []

    for key, cfg in TIMEFRAMES.items():

        buttons.append([
            InlineKeyboardButton(
                cfg["label"],
                callback_data=(
                    f"signal|"
                    f"{market}|"
                    f"{asset}|"
                    f"{key}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "🔙 Volver",
            callback_data=(
                f"market|{market}"
            )
        )
    ])

    await query.message.edit_text(
        (
            f"💎 *{asset}*\n\n"
            "Selecciona temporalidad:"
        ),
        reply_markup=InlineKeyboardMarkup(
            buttons
        ),
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# PROCESS
# ============================================================

async def process_signal(
    query,
    market,
    asset,
    timeframe
):

    await query.message.edit_text(
        (
            "🔎 *ANALIZANDO MERCADO...*\n\n"

            f"💎 `{asset}`\n"
            f"🏦 `{market}`\n"
            f"⏱ `{TIMEFRAMES[timeframe]['label']}`\n\n"

            "Descargando datos...\n"
            "Calculando indicadores...\n"
            "Confirmando tendencia...\n"
            "Analizando contexto..."
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    try:

        signal = await asyncio.to_thread(
            analyze,
            asset,
            market,
            timeframe
        )

        # ----------------------------------------------------
        # FILTRO DE CALIDAD
        # ----------------------------------------------------

        if (
            signal.score < MIN_SCORE
            or
            signal.edge < MIN_EDGE
        ):

            text = (

                "🟡 *NO HAY SEÑAL DE ALTA CONFIANZA*\n\n"

                f"💎 `{asset}`\n"
                f"🏦 `{market}`\n"
                f"⏱ `{TIMEFRAMES[timeframe]['label']}`\n\n"

                f"CALL: `{signal.score if signal.direction == 'CALL' else signal.opposite_score}`\n"
                f"PUT: `{signal.score if signal.direction == 'PUT' else signal.opposite_score}`\n\n"

                "El sistema detectó una dirección "
                "preferente, pero la ventaja no es "
                "suficiente para emitir una entrada."
            )

            keyboard = [[
                InlineKeyboardButton(
                    "🔄 Analizar otra vez",
                    callback_data=(
                        f"signal|"
                        f"{market}|"
                        f"{asset}|"
                        f"{timeframe}"
                    )
                )
            ]]

            keyboard.append([
                InlineKeyboardButton(
                    "🏠 Menú",
                    callback_data="home"
                )
            ])

            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
                parse_mode=ParseMode.MARKDOWN
            )

            return

        text = signal_text(
            signal
        )

        keyboard = [

            [
                InlineKeyboardButton(
                    "🔄 NUEVA SEÑAL",
                    callback_data=(
                        f"signal|"
                        f"{market}|"
                        f"{asset}|"
                        f"{timeframe}"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "⏱ Cambiar temporalidad",
                    callback_data=(
                        f"asset|"
                        f"{market}|"
                        f"{asset}"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "🏠 Menú",
                    callback_data="home"
                )
            ],

        ]

        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as exc:

        logger.exception(
            "ERROR DE ANÁLISIS"
        )

        await query.message.edit_text(
            (
                "❌ *NO SE PUDO GENERAR LA SEÑAL*\n\n"
                f"`{str(exc)}`\n\n"
                "No se generó una operación ficticia."
            ),
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================
# CALLBACK
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    logger.info(
        "CALLBACK %s",
        data
    )

    # HOME
    if data == "home":

        await start(
            update,
            context
        )

        return

    # MARKET
    if data.startswith(
        "market|"
    ):

        market = data.split(
            "|",
            1
        )[1]

        if market not in (
            "REAL",
            "OTC"
        ):

            return

        await show_market(
            query,
            market
        )

        return

    # ASSET
    if data.startswith(
        "asset|"
    ):

        parts = data.split(
            "|"
        )

        if len(parts) != 3:

            return

        market = parts[1]

        asset = parts[2]

        if asset not in PAIRS:

            return

        await show_timeframes(
            query,
            market,
            asset
        )

        return

    # SIGNAL
    if data.startswith(
        "signal|"
    ):

        parts = data.split(
            "|"
        )

        if len(parts) != 4:

            return

        market = parts[1]

        asset = parts[2]

        timeframe = parts[3]

        if asset not in PAIRS:
            return

        if timeframe not in TIMEFRAMES:
            return

        await process_signal(
            query,
            market,
            asset,
            timeframe
        )

        return

    # STATS
    if data == "stats":

        stats = load_stats()

        await query.message.edit_text(
            (
                "📊 *ESTADÍSTICAS*\n\n"
                f"Registros: `{len(stats)}`\n\n"
                "Las estadísticas se "
                "almacenan en stats.json."
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 Menú",
                        callback_data="home"
                    )
                ]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================
# STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        (
            "🟢 *BOT ONLINE*\n\n"
            "Motor: V5\n"
            "Real: habilitado\n"
            "OTC: proxy\n"
            "Temporalidades: 1m / 2m / 5m\n"
            f"Score mínimo: `{MIN_SCORE}`\n"
            f"Edge mínimo: `{MIN_EDGE}`"
        ),
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# CANCEL
# ============================================================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await start(
        update,
        context
    )


# ============================================================
# TELEGRAM STARTUP
# ============================================================

async def post_init(
    application: Application
):

    logger.info(
        "Comprobando Telegram..."
    )

    # Si había webhook configurado,
    # lo elimina para utilizar polling.
    await application.bot.delete_webhook(
        drop_pending_updates=True
    )

    me = await application.bot.get_me()

    logger.info(
        "Telegram conectado: @%s",
        me.username
    )

    await application.bot.set_my_commands([
        BotCommand(
            "start",
            "Abrir menú"
        ),
        BotCommand(
            "status",
            "Estado del bot"
        ),
        BotCommand(
            "cancel",
            "Volver al menú"
        ),
    ])

    logger.info(
        "Comandos configurados."
    )


# ============================================================
# ERRORS
# ============================================================

async def error_handler(
    update,
    context
):

    error = context.error

    if isinstance(
        error,
        Conflict
    ):

        logger.error(
            "CONFLICT: hay otra instancia "
            "usando este token."
        )

        return

    logger.exception(
        "ERROR TELEGRAM: %r",
        error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "======================================"
    )

    logger.info(
        "SIGNAL BOT V5 STARTING"
    )

    logger.info(
        "Temporalidades: 1m / 2m / 5m"
    )

    logger.info(
        "Mercados: REAL / OTC"
    )

    logger.info(
        "======================================"
    )

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "status",
            status
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel
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

    logger.info(
        "Handlers cargados."
    )

    logger.info(
        "Iniciando polling..."
    )

    app.run_polling(
        timeout=10,
        bootstrap_retries=-1,
        drop_pending_updates=True,
        allowed_updates=[
            "message",
            "callback_query",
        ],
    )


if __name__ == "__main__":

    main()