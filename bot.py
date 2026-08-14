```python
# ============================================================
# BOT DE SEÑALES V4
# Telegram + Yahoo Finance + TA + Backtesting
#
# IMPORTANTE:
# - NO pongas el token directamente aquí.
# - Railway:
#     TELEGRAM_BOT_TOKEN = token_nuevo_de_BotFather
#
# Temporalidades:
#     1m / 2m / 5m
#
# Mercados:
#     REAL / OTC
#
# NOTA OTC:
# Yahoo Finance NO proporciona el feed OTC específico
# de Pocket Option. El motor OTC de esta versión utiliza
# el par real como PROXY. No debe interpretarse como
# precio OTC real.
# ============================================================

import os
import json
import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange

from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.error import Conflict, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "ERROR: No existe TELEGRAM_BOT_TOKEN. "
        "Configúrala en Railway > Variables."
    )

TIMEZONE = os.getenv(
    "BOT_TIMEZONE",
    "UTC"
)

STATS_FILE = Path(
    os.getenv(
        "STATS_FILE",
        "stats.json"
    )
)

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO"
).upper()


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(
        logging,
        LOG_LEVEL,
        logging.INFO
    ),
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "signal_bot_v4"
)


# ============================================================
# ACTIVOS
# ============================================================

PARES_REALES = {
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
# TEMPORALIDADES
# ============================================================

TEMPORALIDADES = {
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
# CONFIGURACIÓN DEL MODELO
# ============================================================

MIN_HISTORY = 100

STRUCTURE_WINDOW = 20

STRONG_SCORE = 78

GOOD_SCORE = 65


# ============================================================
# RESULTADO
# ============================================================

@dataclass
class SignalResult:

    direction: str

    score: int

    opposing_score: int

    quality: str

    asset: str

    market: str

    timeframe: str

    timestamp: str

    reasons: list

    warnings: list


# ============================================================
# UTILIDADES
# ============================================================

def now_utc():

    return datetime.now(
        timezone.utc
    )


def clean_dataframe(
    df: pd.DataFrame
) -> pd.DataFrame:

    if df is None or df.empty:

        raise RuntimeError(
            "Yahoo Finance no devolvió datos."
        )

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
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:

        raise RuntimeError(
            f"Faltan columnas: {missing}"
        )

    df = df[
        required
    ].copy()

    for column in required:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df.replace(
        [
            np.inf,
            -np.inf
        ],
        np.nan,
        inplace=True
    )

    df.dropna(
        inplace=True
    )

    return df


# ============================================================
# DESCARGA DE DATOS
# ============================================================

def download_market_data(
    asset: str,
    timeframe: str
) -> pd.DataFrame:

    if asset not in PARES_REALES:

        raise ValueError(
            f"Activo no soportado: {asset}"
        )

    if timeframe not in TEMPORALIDADES:

        raise ValueError(
            f"Temporalidad no soportada: {timeframe}"
        )

    config = (
        TEMPORALIDADES[
            timeframe
        ]
    )

    ticker = PARES_REALES[
        asset
    ]

    logger.info(
        "Descargando %s | %s | %s",
        asset,
        ticker,
        timeframe,
    )

    df = yf.download(
        ticker,
        period=config["period"],
        interval=config["interval"],
        progress=False,
        auto_adjust=False,
        threads=False,
    )

    df = clean_dataframe(
        df
    )

    if len(df) < MIN_HISTORY:

        raise RuntimeError(
            f"Datos insuficientes: "
            f"{len(df)} velas."
        )

    return df


# ============================================================
# INDICADORES
# ============================================================

def add_indicators(
    df: pd.DataFrame
) -> pd.DataFrame:

    data = df.copy()

    close = data["Close"]

    # EMA
    data["EMA9"] = EMAIndicator(
        close=close,
        window=9
    ).ema_indicator()

    data["EMA21"] = EMAIndicator(
        close=close,
        window=21
    ).ema_indicator()

    data["EMA50"] = EMAIndicator(
        close=close,
        window=50
    ).ema_indicator()

    data["EMA200"] = EMAIndicator(
        close=close,
        window=200
    ).ema_indicator()

    # RSI
    data["RSI"] = RSIIndicator(
        close=close,
        window=14
    ).rsi()

    # MACD
    macd = MACD(
        close=close,
        window_fast=12,
        window_slow=26,
        window_sign=9
    )

    data["MACD"] = macd.macd()

    data["MACD_SIGNAL"] = (
        macd.macd_signal()
    )

    data["MACD_HIST"] = (
        macd.macd_diff()
    )

    # Bollinger
    bb = BollingerBands(
        close=close,
        window=20,
        window_dev=2
    )

    data["BB_HIGH"] = (
        bb.bollinger_hband()
    )

    data["BB_MID"] = (
        bb.bollinger_mavg()
    )

    data["BB_LOW"] = (
        bb.bollinger_lband()
    )

    # ATR
    atr = AverageTrueRange(
        high=data["High"],
        low=data["Low"],
        close=close,
        window=14
    )

    data["ATR"] = (
        atr.average_true_range()
    )

    # ADX
    adx = ADXIndicator(
        high=data["High"],
        low=data["Low"],
        close=close,
        window=14
    )

    data["ADX"] = adx.adx()

    data["DI_PLUS"] = (
        adx.adx_pos()
    )

    data["DI_MINUS"] = (
        adx.adx_neg()
    )

    # Stochastic
    stoch = StochasticOscillator(
        high=data["High"],
        low=data["Low"],
        close=close,
        window=14,
        smooth_window=3
    )

    data["STOCH"] = (
        stoch.stoch()
    )

    data["STOCH_SIGNAL"] = (
        stoch.stoch_signal()
    )

    data.replace(
        [
            np.inf,
            -np.inf
        ],
        np.nan,
        inplace=True
    )

    data.dropna(
        inplace=True
    )

    return data


# ============================================================
# ESTRUCTURA
# ============================================================

def market_structure(
    df: pd.DataFrame
) -> dict:

    current = df.iloc[-1]

    previous = df.iloc[-2]

    recent = df.tail(
        STRUCTURE_WINDOW
    )

    previous_recent = (
        df.iloc[
            -STRUCTURE_WINDOW * 2:
            -STRUCTURE_WINDOW
        ]
    )

    bullish = 0

    bearish = 0

    reasons = []

    # Tendencia de máximos
    if len(previous_recent) > 5:

        current_high = (
            recent["High"].max()
        )

        previous_high = (
            previous_recent["High"].max()
        )

        current_low = (
            recent["Low"].min()
        )

        previous_low = (
            previous_recent["Low"].min()
        )

        if (
            current_high >
            previous_high
            and
            current_low >
            previous_low
        ):

            bullish += 12

            reasons.append(
                "Estructura de máximos/mínimos alcista"
            )

        elif (
            current_high <
            previous_high
            and
            current_low <
            previous_low
        ):

            bearish += 12

            reasons.append(
                "Estructura de máximos/mínimos bajista"
            )

    # Vela actual
    if current["Close"] > current["Open"]:

        bullish += 5

    elif current["Close"] < current["Open"]:

        bearish += 5

    # Momentum de cierre
    if current["Close"] > previous["Close"]:

        bullish += 5

    elif current["Close"] < previous["Close"]:

        bearish += 5

    return {
        "bullish": bullish,
        "bearish": bearish,
        "reasons": reasons,
    }


# ============================================================
# SCORE
# ============================================================

def calculate_scores(
    df: pd.DataFrame,
    context: Optional[pd.DataFrame]
) -> dict:

    current = df.iloc[-1]

    previous = df.iloc[-2]

    call = 0

    put = 0

    call_reasons = []

    put_reasons = []

    warnings = []

    # --------------------------------------------------------
    # EMA 9/21
    # --------------------------------------------------------

    if current["EMA9"] > current["EMA21"]:

        call += 12

        call_reasons.append(
            "EMA9 > EMA21"
        )

    else:

        put += 12

        put_reasons.append(
            "EMA9 < EMA21"
        )

    # --------------------------------------------------------
    # EMA 50
    # --------------------------------------------------------

    if current["Close"] > current["EMA50"]:

        call += 10

        call_reasons.append(
            "Precio sobre EMA50"
        )

    else:

        put += 10

        put_reasons.append(
            "Precio bajo EMA50"
        )

    # --------------------------------------------------------
    # EMA 200
    # --------------------------------------------------------

    if current["Close"] > current["EMA200"]:

        call += 8

        call_reasons.append(
            "Precio sobre EMA200"
        )

    else:

        put += 8

        put_reasons.append(
            "Precio bajo EMA200"
        )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi = float(
        current["RSI"]
    )

    if 52 <= rsi <= 68:

        call += 10

        call_reasons.append(
            f"RSI alcista {rsi:.1f}"
        )

    elif 32 <= rsi <= 48:

        put += 10

        put_reasons.append(
            f"RSI bajista {rsi:.1f}"
        )

    elif rsi > 75:

        warnings.append(
            f"RSI sobrecomprado {rsi:.1f}"
        )

        call -= 5

    elif rsi < 25:

        warnings.append(
            f"RSI sobrevendido {rsi:.1f}"
        )

        put -= 5

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    macd = float(
        current["MACD"]
    )

    signal = float(
        current["MACD_SIGNAL"]
    )

    prev_macd = float(
        previous["MACD"]
    )

    if (
        macd > signal
        and macd >= prev_macd
    ):

        call += 12

        call_reasons.append(
            "MACD confirma impulso alcista"
        )

    elif (
        macd < signal
        and macd <= prev_macd
    ):

        put += 12

        put_reasons.append(
            "MACD confirma impulso bajista"
        )

    # --------------------------------------------------------
    # ADX
    # --------------------------------------------------------

    adx = float(
        current["ADX"]
    )

    di_plus = float(
        current["DI_PLUS"]
    )

    di_minus = float(
        current["DI_MINUS"]
    )

    if adx >= 25:

        if di_plus > di_minus:

            call += 10

            call_reasons.append(
                f"ADX fuerte {adx:.1f}"
            )

        else:

            put += 10

            put_reasons.append(
                f"ADX fuerte {adx:.1f}"
            )

    elif adx < 18:

        warnings.append(
            f"ADX bajo: {adx:.1f}"
        )

    # --------------------------------------------------------
    # BOLLINGER
    # --------------------------------------------------------

    if (
        current["Close"]
        > current["BB_MID"]
    ):

        call += 6

        call_reasons.append(
            "Precio sobre media Bollinger"
        )

    else:

        put += 6

        put_reasons.append(
            "Precio bajo media Bollinger"
        )

    # --------------------------------------------------------
    # STOCHASTIC
    # --------------------------------------------------------

    stoch = float(
        current["STOCH"]
    )

    stoch_signal = float(
        current["STOCH_SIGNAL"]
    )

    if (
        stoch >
        stoch_signal
        and
        stoch < 80
    ):

        call += 6

        call_reasons.append(
            "Stochastic alcista"
        )

    elif (
        stoch <
        stoch_signal
        and
        stoch > 20
    ):

        put += 6

        put_reasons.append(
            "Stochastic bajista"
        )

    # --------------------------------------------------------
    # ESTRUCTURA
    # --------------------------------------------------------

    structure = market_structure(
        df
    )

    call += structure[
        "bullish"
    ]

    put += structure[
        "bearish"
    ]

    for reason in structure[
        "reasons"
    ]:

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

            call += 12

            call_reasons.append(
                "Contexto superior alcista"
            )

        elif (
            c["Close"] < c["EMA21"]
            and
            c["EMA21"] < c["EMA50"]
        ):

            put += 12

            put_reasons.append(
                "Contexto superior bajista"
            )

        else:

            warnings.append(
                "Contexto superior mixto"
            )

    call = max(
        0,
        min(
            100,
            call
        )
    )

    put = max(
        0,
        min(
            100,
            put
        )
    )

    return {
        "call": call,
        "put": put,
        "call_reasons": call_reasons,
        "put_reasons": put_reasons,
        "warnings": warnings,
    }


# ============================================================
# GENERADOR
# ============================================================

def generate_signal(
    asset: str,
    market: str,
    timeframe: str,
    df: pd.DataFrame,
    context: Optional[pd.DataFrame]
) -> SignalResult:

    scores = calculate_scores(
        df,
        context
    )

    call_score = int(
        scores["call"]
    )

    put_score = int(
        scores["put"]
    )

    # ELECCIÓN FORZADA
    if call_score >= put_score:

        direction = "CALL"

        score = call_score

        opposing = put_score

        reasons = (
            scores["call_reasons"]
        )

    else:

        direction = "PUT"

        score = put_score

        opposing = call_score

        reasons = (
            scores["put_reasons"]
        )

    # Calidad
    if score >= STRONG_SCORE:

        quality = "MUY ALTA"

    elif score >= GOOD_SCORE:

        quality = "ALTA"

    elif score >= 50:

        quality = "MEDIA"

    else:

        quality = "BAJA"

    return SignalResult(
        direction=direction,
        score=score,
        opposing_score=opposing,
        quality=quality,
        asset=asset,
        market=market,
        timeframe=timeframe,
        timestamp=now_utc().isoformat(),
        reasons=reasons[:8],
        warnings=scores[
            "warnings"
        ][:6],
    )


# ============================================================
# ANÁLISIS
# ============================================================

def analyze(
    asset: str,
    market: str,
    timeframe: str
) -> SignalResult:

    logger.info(
        "Analizando %s | %s | %s",
        market,
        asset,
        timeframe
    )

    # Principal
    raw = download_market_data(
        asset,
        timeframe
    )

    main_df = add_indicators(
        raw
    )

    if len(main_df) < 60:

        raise RuntimeError(
            "No hay suficiente histórico "
            "después de calcular indicadores."
        )

    # Contexto independiente
    context_tf = (
        TEMPORALIDADES[
            timeframe
        ]["context"]
    )

    context_raw = download_market_data(
        asset,
        context_tf
    )

    context_df = add_indicators(
        context_raw
    )

    return generate_signal(
        asset,
        market,
        timeframe,
        main_df,
        context_df,
    )


# ============================================================
# BACKTEST
# ============================================================

def backtest(
    asset: str,
    timeframe: str,
    market: str
) -> dict:

    logger.info(
        "Backtest iniciado: %s %s %s",
        market,
        asset,
        timeframe
    )

    raw = download_market_data(
        asset,
        timeframe
    )

    df = add_indicators(
        raw
    )

    horizon = (
        TEMPORALIDADES[
            timeframe
        ]["expiry"]
    )

    wins = 0

    losses = 0

    signals = 0

    # Últimas 300 velas máximo
    start = max(
        60,
        len(df) - 400
    )

    end = (
        len(df) - horizon
    )

    for i in range(
        start,
        end
    ):

        window = df.iloc[
            :i + 1
        ]

        scores = calculate_scores(
            window,
            None
        )

        call = scores["call"]

        put = scores["put"]

        if call >= put:

            direction = "CALL"

        else:

            direction = "PUT"

        current_close = float(
            df["Close"].iloc[i]
        )

        future_close = float(
            df["Close"].iloc[
                i + horizon
            ]
        )

        if direction == "CALL":

            win = (
                future_close
                > current_close
            )

        else:

            win = (
                future_close
                < current_close
            )

        signals += 1

        if win:

            wins += 1

        else:

            losses += 1

    winrate = (
        wins / signals * 100
        if signals
        else 0
    )

    return {
        "asset": asset,
        "market": market,
        "timeframe": timeframe,
        "signals": signals,
        "wins": wins,
        "losses": losses,
        "winrate": round(
            winrate,
            2
        ),
        "generated_at": (
            now_utc().isoformat()
        ),
    }


# ============================================================
# ESTADÍSTICAS
# ============================================================

def load_stats():

    if not STATS_FILE.exists():

        return []

    try:

        with open(
            STATS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return []


def save_stats(
    data
):

    try:

        with open(
            STATS_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

    except Exception:

        logger.exception(
            "No se pudieron guardar estadísticas."
        )


# ============================================================
# HORARIOS
# ============================================================

def calculate_entry_expiration(
    timeframe: str
):

    minutes = (
        TEMPORALIDADES[
            timeframe
        ]["expiry"]
    )

    now = datetime.now(
        timezone.utc
    )

    base = now.replace(
        second=0,
        microsecond=0
    )

    next_candle = base

    while next_candle <= now:

        next_candle += timedelta(
            minutes=minutes
        )

    expiration = (
        next_candle
        + timedelta(
            minutes=minutes
        )
    )

    return (
        next_candle,
        expiration
    )


# ============================================================
# TELEGRAM STARTUP
# ============================================================

async def post_init(
    application: Application
):

    logger.info(
        "Conectando con Telegram..."
    )

    me = await application.bot.get_me()

    logger.info(
        "Bot conectado: @%s",
        me.username
    )

    await application.bot.set_my_commands([
        BotCommand(
            "start",
            "Abrir menú"
        ),
        BotCommand(
            "cancel",
            "Cancelar"
        ),
        BotCommand(
            "status",
            "Estado del bot"
        ),
    ])

    logger.info(
        "Comandos registrados."
    )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.info(
        "/start recibido | user=%s",
        update.effective_user.id
        if update.effective_user
        else "unknown"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "📊 MERCADO REAL",
                callback_data="market_real"
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 MERCADO OTC",
                callback_data="market_otc"
            )
        ],

    ]

    text = (
        "🤖 *BOT DE SEÑALES V4*\n\n"

        "Sistema de análisis técnico "
        "multi-timeframe.\n\n"

        "⏱ *Temporalidades:*\n"
        "• 1 minuto\n"
        "• 2 minutos\n"
        "• 5 minutos\n\n"

        "📊 *Motores:*\n"
        "• EMA 9/21/50/200\n"
        "• RSI\n"
        "• MACD\n"
        "• ADX\n"
        "• ATR\n"
        "• Bollinger\n"
        "• Stochastic\n"
        "• Estructura de mercado\n"
        "• Confirmación multi-timeframe\n\n"

        "Selecciona un mercado:"
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
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
# STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    stats = load_stats()

    text = (
        "🟢 *BOT ONLINE*\n\n"
        f"Registros de backtest: `{len(stats)}`\n"
        f"Temporalidades: `1m / 2m / 5m`\n"
        f"Mercados: `Real / OTC`\n"
        f"Timezone interno: `{TIMEZONE}`"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# MOSTRAR ACTIVOS
# ============================================================

async def show_assets(
    query,
    market: str
):

    buttons = []

    assets = list(
        PARES_REALES.keys()
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

    market_name = (
        "Mercado Real"
        if market == "real"
        else "Mercado OTC"
    )

    await query.message.edit_text(
        f"📊 *{market_name}*\n\n"
        "Selecciona el activo:",
        reply_markup=InlineKeyboardMarkup(
            buttons
        ),
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# MOSTRAR TEMPORALIDADES
# ============================================================

async def show_timeframes(
    query,
    market: str,
    asset: str
):

    buttons = []

    for key, config in (
        TEMPORALIDADES.items()
    ):

        buttons.append([
            InlineKeyboardButton(
                config["label"],
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
                f"market_{market}"
            )
        )
    ])

    await query.message.edit_text(
        f"💎 *{asset}*\n\n"
        "Selecciona la temporalidad:",
        reply_markup=InlineKeyboardMarkup(
            buttons
        ),
        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# FORMATEAR SEÑAL
# ============================================================

def format_signal(
    result: SignalResult
) -> str:

    emoji = (
        "🟢"
        if result.direction == "CALL"
        else "🔴"
    )

    reasons = "\n".join(
        f"• {reason}"
        for reason in result.reasons
    )

    warnings = ""

    if result.warnings:

        warning_lines = "\n".join(
            f"• {warning}"
            for warning in result.warnings
        )

        warnings = (
            "\n\n⚠️ *Advertencias*\n"
            f"{warning_lines}"
        )

    return (
        f"{emoji} *SEÑAL {result.direction}*\n\n"

        f"🏦 Mercado: `{result.market}`\n"
        f"💎 Activo: `{result.asset}`\n"
        f"⏱ Temporalidad: "
        f"`{TEMPORALIDADES[result.timeframe]['label']}`\n\n"

        f"🎯 Score: `{result.score}/100`\n"
        f"↔️ Opuesto: `{result.opposing_score}/100`\n"
        f"📊 Calidad: `{result.quality}`\n\n"

        f"🔍 *Confluencias*\n"
        f"{reasons}"

        f"{warnings}"
    )


# ============================================================
# PROCESAR SEÑAL
# ============================================================

async def process_signal(
    query,
    market: str,
    asset: str,
    timeframe: str
):

    market_name = (
        "Mercado Real"
        if market == "real"
        else "Mercado OTC"
    )

    await query.message.edit_text(
        "🔎 *ANALIZANDO...*\n\n"
        f"🏦 {market_name}\n"
        f"💎 {asset}\n"
        f"⏱ "
        f"{TEMPORALIDADES[timeframe]['label']}\n\n"
        "Descargando datos y calculando "
        "confluencias...",
        parse_mode=ParseMode.MARKDOWN
    )

    try:

        result = await asyncio.to_thread(
            analyze,
            asset,
            market_name,
            timeframe
        )

        entry, expiration = (
            calculate_entry_expiration(
                timeframe
            )
        )

        text = format_signal(
            result
        )

        text += (
            "\n\n"
            f"⏰ Entrada: "
            f"`{entry.strftime('%H:%M:%S')}`\n"

            f"⏳ Expiración: "
            f"`{expiration.strftime('%H:%M:%S')}`"
        )

        if market == "otc":

            text += (
                "\n\n"
                "⚠️ *OTC PROXY*\n"
                "Los datos utilizados proceden "
                "del par real de Yahoo Finance. "
                "Esta versión todavía NO está "
                "conectada al feed OTC real."
            )

        text += (
            "\n\n"
            "ℹ️ El score representa confluencia "
            "técnica, no un porcentaje garantizado "
            "de acierto."
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
            "Error procesando señal"
        )

        keyboard = [[
            InlineKeyboardButton(
                "🔄 Reintentar",
                callback_data=(
                    f"signal|"
                    f"{market}|"
                    f"{asset}|"
                    f"{timeframe}"
                )
            )
        ]]

        await query.message.edit_text(
            "❌ *ERROR DE DATOS*\n\n"
            f"`{str(exc)}`\n\n"
            "No se generó una señal falsa.",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
            parse_mode=ParseMode.MARKDOWN
        )


# ============================================================
# CALLBACK
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

    logger.info(
        "Callback recibido: %s",
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
    if data == "market_real":

        await show_assets(
            query,
            "real"
        )

        return

    if data == "market_otc":

        await show_assets(
            query,
            "otc"
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

        if timeframe not in TEMPORALIDADES:

            await query.message.edit_text(
                "❌ Temporalidad inválida."
            )

            return

        await process_signal(
            query,
            market,
            asset,
            timeframe
        )

        return


# ============================================================
# ERROR GLOBAL
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    error = context.error

    logger.error(
        "ERROR GLOBAL: %r",
        error
    )

    if isinstance(
        error,
        Conflict
    ):

        logger.error(
            "CONFLICT: existe otra instancia "
            "del bot haciendo polling."
        )

    elif isinstance(
        error,
        TelegramError
    ):

        logger.error(
            "TelegramError: %s",
            error
        )

    else:

        logger.exception(
            "Excepción no controlada"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "======================================"
    )

    logger.info(
        "INICIANDO SIGNAL BOT V4"
    )

    logger.info(
        "Temporalidades: 1m / 2m / 5m"
    )

    logger.info(
        "Mercados: REAL / OTC"
    )

    logger.info(
        "Railway compatible"
    )

    logger.info(
        "======================================"
    )

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Handlers
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel
        )
    )

    application.add_handler(
        CommandHandler(
            "status",
            status
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

    logger.info(
        "Handlers registrados."
    )

    logger.info(
        "Iniciando polling..."
    )

    try:

        application.run_polling(
            drop_pending_updates=True,
            bootstrap_retries=-1,
            allowed_updates=[
                "message",
                "callback_query",
            ],
        )

    except Conflict:

        logger.error(
            "======================================"
        )

        logger.error(
            "ERROR: HAY OTRA INSTANCIA DEL BOT."
        )

        logger.error(
            "Detén cualquier otro proceso "
            "que utilice este mismo token."
        )

        logger.error(
            "======================================"

        )

        raise

    except Exception:

        logger.exception(
            "El bot terminó por un error."
        )

        raise


if __name__ == "__main__":

    main()
```