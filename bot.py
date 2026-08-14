import os
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange

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

TOKEN = os.getenv("8845724881:AAEpMM4fkKdFohyP553vWKbkItXVCE-f3QY")

if not TOKEN:
    raise RuntimeError(
        "No existe TELEGRAM_BOT_TOKEN. "
        "Configura el token como variable de entorno."
    )

TIMEZONE = os.getenv("BOT_TIMEZONE", "UTC")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("signal_bot")


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
        "expiry_minutes": 1,
        "context_tf": "5m",
    },

    "2m": {
        "label": "2 Minutos",
        "interval": "2m",
        "period": "7d",
        "expiry_minutes": 2,
        "context_tf": "5m",
    },

    "5m": {
        "label": "5 Minutos",
        "interval": "5m",
        "period": "30d",
        "expiry_minutes": 5,
        "context_tf": "15m",
    },
}


# ============================================================
# PARÁMETROS DEL MODELO
# ============================================================

MIN_SIGNAL_SCORE = 58
STRONG_SIGNAL_SCORE = 78

MIN_HISTORY = 100

# Número de velas usadas para estructura
STRUCTURE_WINDOW = 20

# Payout mínimo hipotético para calcular expectativa.
# No se usa para inventar señales.
DEFAULT_PAYOUT = 0.80


# ============================================================
# MODELOS
# ============================================================

@dataclass
class SignalResult:
    direction: str
    score: int
    confidence: str
    reasons: list
    warnings: list
    market: str
    asset: str
    timeframe: str
    timestamp: datetime


# ============================================================
# UTILIDADES
# ============================================================

def safe_float(value, default=np.nan):
    try:
        return float(value)
    except Exception:
        return default


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:

    if df is None or df.empty:
        raise RuntimeError("No se recibieron datos.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close"]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"Faltan columnas: {missing}"
        )

    df = df[required].copy()

    for col in required:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True
    )

    df.dropna(inplace=True)

    return df


# ============================================================
# DESCARGA DE DATOS
# ============================================================

def descargar_datos(
    activo: str,
    timeframe: str,
) -> pd.DataFrame:

    if activo not in PARES_REALES:
        raise ValueError(
            f"Activo no soportado: {activo}"
        )

    if timeframe not in TEMPORALIDADES:
        raise ValueError(
            f"Temporalidad no soportada: {timeframe}"
        )

    config = TEMPORALIDADES[timeframe]

    ticker = PARES_REALES[activo]

    logger.info(
        "Descargando %s | %s",
        activo,
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

    df = clean_dataframe(df)

    if len(df) < MIN_HISTORY:
        raise RuntimeError(
            f"Datos insuficientes: "
            f"{len(df)} velas."
        )

    return df


# ============================================================
# RESAMPLE PARA CONTEXTO
# ============================================================

def resample_ohlc(
    df: pd.DataFrame,
    rule: str
) -> pd.DataFrame:

    result = df.resample(rule).agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
    })

    result.dropna(inplace=True)

    return result


# ============================================================
# INDICADORES
# ============================================================

def calcular_indicadores(
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
    data["MACD_SIGNAL"] = macd.macd_signal()
    data["MACD_HIST"] = macd.macd_diff()

    # Bollinger
    bb = BollingerBands(
        close=close,
        window=20,
        window_dev=2
    )

    data["BB_HIGH"] = bb.bollinger_hband()
    data["BB_MID"] = bb.bollinger_mavg()
    data["BB_LOW"] = bb.bollinger_lband()

    # ATR
    atr = AverageTrueRange(
        high=data["High"],
        low=data["Low"],
        close=close,
        window=14
    )

    data["ATR"] = atr.average_true_range()

    # ADX
    adx = ADXIndicator(
        high=data["High"],
        low=data["Low"],
        close=close,
        window=14
    )

    data["ADX"] = adx.adx()
    data["DI_PLUS"] = adx.adx_pos()
    data["DI_MINUS"] = adx.adx_neg()

    # Stochastic
    stoch = StochasticOscillator(
        high=data["High"],
        low=data["Low"],
        close=close,
        window=14,
        smooth_window=3
    )

    data["STOCH"] = stoch.stoch()
    data["STOCH_SIGNAL"] = stoch.stoch_signal()

    data.dropna(inplace=True)

    return data


# ============================================================
# ESTRUCTURA DEL MERCADO
# ============================================================

def analizar_estructura(
    df: pd.DataFrame
) -> dict:

    recent = df.tail(STRUCTURE_WINDOW)

    current = df.iloc[-1]

    previous = df.iloc[-2]

    recent_high = recent["High"].max()
    recent_low = recent["Low"].min()

    result = {
        "bullish": 0,
        "bearish": 0,
        "reasons": [],
    }

    # Máximo reciente
    if current["Close"] > recent_high:
        result["bullish"] += 15
        result["reasons"].append(
            "Ruptura alcista de máximo reciente"
        )

    # Mínimo reciente
    if current["Close"] < recent_low:
        result["bearish"] += 15
        result["reasons"].append(
            "Ruptura bajista de mínimo reciente"
        )

    # Dirección de la vela actual
    if current["Close"] > current["Open"]:
        result["bullish"] += 5
    elif current["Close"] < current["Open"]:
        result["bearish"] += 5

    # Comparación con vela anterior
    if current["Close"] > previous["Close"]:
        result["bullish"] += 5
    elif current["Close"] < previous["Close"]:
        result["bearish"] += 5

    return result


# ============================================================
# MOTOR DE SCORE
# ============================================================

def calcular_score(
    df: pd.DataFrame,
    context_df: Optional[pd.DataFrame] = None
) -> dict:

    current = df.iloc[-1]
    previous = df.iloc[-2]

    call = 0
    put = 0

    call_reasons = []
    put_reasons = []

    warnings = []

    # --------------------------------------------------------
    # 1. EMA 9 / 21
    # --------------------------------------------------------

    if current["EMA9"] > current["EMA21"]:

        call += 12

        call_reasons.append(
            "EMA9 por encima de EMA21"
        )

    elif current["EMA9"] < current["EMA21"]:

        put += 12

        put_reasons.append(
            "EMA9 por debajo de EMA21"
        )

    # --------------------------------------------------------
    # 2. EMA 50
    # --------------------------------------------------------

    if current["Close"] > current["EMA50"]:

        call += 10

        call_reasons.append(
            "Precio sobre EMA50"
        )

    elif current["Close"] < current["EMA50"]:

        put += 10

        put_reasons.append(
            "Precio bajo EMA50"
        )

    # --------------------------------------------------------
    # 3. EMA 200
    # --------------------------------------------------------

    if current["Close"] > current["EMA200"]:

        call += 8

        call_reasons.append(
            "Precio sobre EMA200"
        )

    elif current["Close"] < current["EMA200"]:

        put += 8

        put_reasons.append(
            "Precio bajo EMA200"
        )

    # --------------------------------------------------------
    # 4. RSI
    # --------------------------------------------------------

    rsi = safe_float(current["RSI"])

    if 52 <= rsi <= 68:

        call += 10

        call_reasons.append(
            f"RSI favorable para CALL ({rsi:.1f})"
        )

    elif 32 <= rsi <= 48:

        put += 10

        put_reasons.append(
            f"RSI favorable para PUT ({rsi:.1f})"
        )

    elif rsi > 75:

        warnings.append(
            f"RSI extremadamente alto ({rsi:.1f})"
        )

        call -= 5

    elif rsi < 25:

        warnings.append(
            f"RSI extremadamente bajo ({rsi:.1f})"
        )

        put -= 5

    # --------------------------------------------------------
    # 5. MACD
    # --------------------------------------------------------

    macd = safe_float(current["MACD"])
    macd_signal = safe_float(
        current["MACD_SIGNAL"]
    )

    previous_macd = safe_float(
        previous["MACD"]
    )

    previous_signal = safe_float(
        previous["MACD_SIGNAL"]
    )

    if (
        macd > macd_signal
        and macd >= previous_macd
        and macd_signal >= previous_signal
    ):

        call += 12

        call_reasons.append(
            "MACD confirma impulso alcista"
        )

    elif (
        macd < macd_signal
        and macd <= previous_macd
        and macd_signal <= previous_signal
    ):

        put += 12

        put_reasons.append(
            "MACD confirma impulso bajista"
        )

    # --------------------------------------------------------
    # 6. ADX
    # --------------------------------------------------------

    adx = safe_float(current["ADX"])

    if adx >= 25:

        if current["DI_PLUS"] > current["DI_MINUS"]:

            call += 10

            call_reasons.append(
                f"ADX fuerte ({adx:.1f}) + DI alcista"
            )

        elif current["DI_MINUS"] > current["DI_PLUS"]:

            put += 10

            put_reasons.append(
                f"ADX fuerte ({adx:.1f}) + DI bajista"
            )

    elif adx < 18:

        warnings.append(
            f"Mercado con poca fuerza (ADX {adx:.1f})"
        )

    # --------------------------------------------------------
    # 7. BOLLINGER
    # --------------------------------------------------------

    close = current["Close"]

    if close > current["BB_MID"]:

        call += 6

        call_reasons.append(
            "Precio sobre media Bollinger"
        )

    elif close < current["BB_MID"]:

        put += 6

        put_reasons.append(
            "Precio bajo media Bollinger"
        )

    # --------------------------------------------------------
    # 8. STOCHASTIC
    # --------------------------------------------------------

    stoch = safe_float(
        current["STOCH"]
    )

    stoch_signal = safe_float(
        current["STOCH_SIGNAL"]
    )

    if stoch > stoch_signal and stoch < 80:

        call += 6

        call_reasons.append(
            "Stochastic confirma impulso"
        )

    elif stoch < stoch_signal and stoch > 20:

        put += 6

        put_reasons.append(
            "Stochastic confirma impulso bajista"
        )

    # --------------------------------------------------------
    # 9. ESTRUCTURA
    # --------------------------------------------------------

    structure = analizar_estructura(df)

    call += structure["bullish"]
    put += structure["bearish"]

    for reason in structure["reasons"]:

        if "alcista" in reason.lower():

            call_reasons.append(reason)

        elif "bajista" in reason.lower():

            put_reasons.append(reason)

    # --------------------------------------------------------
    # 10. CONTEXTO DE MAYOR TEMPORALIDAD
    # --------------------------------------------------------

    if context_df is not None and len(context_df) >= 50:

        context = context_df.iloc[-1]

        context_close = context["Close"]
        context_ema21 = context["EMA21"]
        context_ema50 = context["EMA50"]

        if (
            context_close > context_ema21
            and context_ema21 > context_ema50
        ):

            call += 12

            call_reasons.append(
                "Temporalidad superior alcista"
            )

        elif (
            context_close < context_ema21
            and context_ema21 < context_ema50
        ):

            put += 12

            put_reasons.append(
                "Temporalidad superior bajista"
            )

        else:

            warnings.append(
                "Temporalidad superior sin tendencia limpia"
            )

    call = max(0, min(100, call))
    put = max(0, min(100, put))

    return {
        "call": call,
        "put": put,
        "call_reasons": call_reasons,
        "put_reasons": put_reasons,
        "warnings": warnings,
    }


# ============================================================
# GENERADOR DE SEÑAL
# ============================================================

def generar_senal(
    activo: str,
    timeframe: str,
    market: str,
    df: pd.DataFrame,
    context_df: Optional[pd.DataFrame],
) -> SignalResult:

    scores = calcular_score(
        df,
        context_df
    )

    call_score = scores["call"]
    put_score = scores["put"]

    # --------------------------------------------------------
    # ELECCIÓN FORZADA
    # --------------------------------------------------------

    if call_score >= put_score:

        direction = "CALL"

        score = call_score

        reasons = scores["call_reasons"]

    else:

        direction = "PUT"

        score = put_score

        reasons = scores["put_reasons"]

    # --------------------------------------------------------
    # CALIDAD
    # --------------------------------------------------------

    if score >= STRONG_SIGNAL_SCORE:

        confidence = "MUY ALTA"

    elif score >= MIN_SIGNAL_SCORE:

        confidence = "ALTA"

    elif score >= 45:

        confidence = "MEDIA"

    else:

        confidence = "BAJA"

    timestamp = datetime.now(
        ZoneInfo(TIMEZONE)
    )

    return SignalResult(
        direction=direction,
        score=int(score),
        confidence=confidence,
        reasons=reasons[:8],
        warnings=scores["warnings"][:5],
        market=market,
        asset=activo,
        timeframe=timeframe,
        timestamp=timestamp,
    )


# ============================================================
# ANÁLISIS COMPLETO
# ============================================================

def analizar_activo(
    activo: str,
    timeframe: str,
    market: str,
) -> SignalResult:

    # --------------------------------------------------------
    # Datos del timeframe principal
    # --------------------------------------------------------

    df = descargar_datos(
        activo,
        timeframe
    )

    df = calcular_indicadores(df)

    if len(df) < MIN_HISTORY:
        raise RuntimeError(
            "No hay suficiente histórico después "
            "de calcular indicadores."
        )

    # --------------------------------------------------------
    # Temporalidad superior
    # --------------------------------------------------------

    config = TEMPORALIDADES[timeframe]

    context_rule = config["context_tf"]

    raw_context = resample_ohlc(
        df,
        context_rule
    )

    if len(raw_context) >= 100:

        context_df = calcular_indicadores(
            raw_context
        )

    else:

        context_df = None

    # --------------------------------------------------------
    # Generar señal
    # --------------------------------------------------------

    return generar_senal(
        activo=activo,
        timeframe=timeframe,
        market=market,
        df=df,
        context_df=context_df,
    )


# ============================================================
# BACKTEST
# ============================================================

def backtest_simple(
    df: pd.DataFrame,
    horizon: int,
) -> dict:

    data = calcular_indicadores(
        df.copy()
    )

    results = []

    # Necesitamos espacio futuro
    max_index = len(data) - horizon

    if max_index <= 50:

        return {
            "signals": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0.0,
        }

    for i in range(50, max_index):

        window = data.iloc[:i + 1].copy()

        result = calcular_score(
            window,
            None
        )

        call_score = result["call"]
        put_score = result["put"]

        if call_score >= put_score:

            direction = "CALL"

        else:

            direction = "PUT"

        current_close = data["Close"].iloc[i]

        future_close = data["Close"].iloc[
            i + horizon
        ]

        if direction == "CALL":

            win = future_close > current_close

        else:

            win = future_close < current_close

        results.append(
            1 if win else 0
        )

    if not results:

        return {
            "signals": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0.0,
        }

    wins = sum(results)

    losses = len(results) - wins

    winrate = (
        wins / len(results)
    ) * 100

    return {
        "signals": len(results),
        "wins": wins,
        "losses": losses,
        "winrate": round(winrate, 2),
    }


# ==================
