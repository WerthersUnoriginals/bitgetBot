# simulacion.py

import pandas as pd
import numpy as np

# Parámetros principales de la estrategia
BANK_INICIAL = 1000.0       # USDT
APALANCAMIENTO = 1.0        # 2x
COMISION = 0.00005          # 0.005% = 0.00005 (Por operación de apertura o cierre)
ATRMULT = 0.71              # Multiplicador ATR para Stop
VWMA_PERIOD = 22
HMA_PERIOD  = 74
ATR_PERIOD  = 17

# =========================
# FUNCIONES DE INDICADORES
# =========================

def calc_vwma(series_close, series_volume, length=22):
    """
    VWMA(n) = (Sum( close_i * vol_i ) de i=0 a n-1) / (Sum( vol_i ) de i=0 a n-1)
    Se implementa con rolling sums.
    """
    cv = series_close * series_volume
    vwma = cv.rolling(length).sum() / series_volume.rolling(length).sum()
    return vwma

def wma(series, length):
    """
    Calcula la Weighted Moving Average (WMA) con ponderaciones lineales.
    """
    # Generamos pesos = 1,2,...,length
    # Rolling con apply (raw=True para acelerar)
    weights = np.arange(1, length+1)  # [1..length]
    def _calc(x):
        return (x * weights).sum() / weights.sum()
    return series.rolling(length).apply(_calc, raw=True)

def calc_hma(series_close, length=74):
    """
    HMA(n) = WMA(2 * WMA(price, n/2) - WMA(price, n), sqrt(n))
    """
    half = int(length // 2)
    sqrt_n = int(np.sqrt(length))
    
    wma_half = wma(series_close, half)
    wma_full = wma(series_close, length)
    
    raw_hull = 2.0 * wma_half - wma_full
    hull = wma(raw_hull, sqrt_n)
    return hull

def calc_atr(df, length=17):
    """
    Calcula ATR básico usando:
      TR = max( high-low, abs(high - close_prev), abs(low - close_prev) )
      ATR = RMA (media móvil exponencial) del TR con periodo = length
    """
    high = df["high"]
    low  = df["low"]
    close= df["close"]
    close_prev = close.shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR como EMA de TR
    atr = tr.ewm(span=length, adjust=False).mean()
    return atr


# =========================
# LÓGICA PRINCIPAL DE BACKTEST
# =========================
def main():
    # Carga datos desde CSV
    # Ajusta la ruta/nombre de archivo según tu fichero
    df = pd.read_csv("solusdt_3m.csv")  # <-- cambia a tu archivo
    # Asegúrate de que las columnas se llamen: timestamp, open, high, low, close, volume
    # Si no es así, renómbralas.

    # A veces, conviene ordenar por fecha
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Calculamos indicadores
    df["vwma"] = calc_vwma(df["close"], df["volume"], VWMA_PERIOD)
    df["hma"]  = calc_hma(df["close"], HMA_PERIOD)
    df["atr"]  = calc_atr(df, ATR_PERIOD)

    # Inicializamos estado
    capital = BANK_INICIAL
    estado  = "flat"  # "long", "short", o "flat"
    precio_entrada = 0.0
    cantidad = 0.0  # cuántos SOL en posición
    # Nota: Se asume 1 sola posición a la vez, con todo el bank.

    # Bucle sobre cada vela
    for i in range(len(df)):
        # Obtenemos valores de la vela actual
        close_actual = df.loc[i, "close"]
        vwma_val = df.loc[i, "vwma"]
        hma_val  = df.loc[i, "hma"]
        atr_val  = df.loc[i, "atr"]

        # Evitar cálculos hasta que haya valores válidos de indicadores (NaN al inicio)
        if pd.isna(vwma_val) or pd.isna(hma_val) or pd.isna(atr_val):
            continue

        # Condiciones de entrada
        open_long_cond  = (close_actual > vwma_val) and (close_actual > hma_val)
        open_short_cond = (close_actual < vwma_val) and (close_actual < hma_val)

        # Condiciones de cierre
        close_long_cond  = (close_actual < (hma_val - ATRMULT * atr_val))
        close_short_cond = (close_actual > (hma_val + ATRMULT * atr_val))

        if estado == "flat":
            # Si no estamos en posición, buscar entrada
            if open_long_cond:
                # Nominal = capital * apalancamiento
                nominal = capital * APALANCAMIENTO
                # Cuántos SOL compramos
                precio_entrada = close_actual
                cantidad = nominal / close_actual
                # Comisión de apertura
                comision_apertura = nominal * COMISION
                capital -= comision_apertura
                estado = "long"

            elif open_short_cond:
                nominal = capital * APALANCAMIENTO
                precio_entrada = close_actual
                cantidad = nominal / close_actual
                comision_apertura = nominal * COMISION
                capital -= comision_apertura
                estado = "short"

        elif estado == "long":
            # Si estamos en LONG, ver si hay que cerrar por stop
            if close_long_cond:
                # Ganancia
                pnl = (close_actual - precio_entrada) * cantidad
                # Comisión de cierre (basada en el nominal actual)
                nominal_cierre = close_actual * cantidad  # valor actual de la posición
                comision_cierre = nominal_cierre * COMISION
                # Actualizar capital
                capital += pnl
                capital -= comision_cierre
                # Salimos
                estado = "flat"
                precio_entrada = 0.0
                cantidad = 0.0

        elif estado == "short":
            # Si estamos en SHORT, ver si hay que cerrar por stop
            if close_short_cond:
                pnl = (precio_entrada - close_actual) * cantidad
                # nominal de cierre
                nominal_cierre = close_actual * cantidad
                comision_cierre = nominal_cierre * COMISION
                capital += pnl
                capital -= comision_cierre
                estado = "flat"
                precio_entrada = 0.0
                cantidad = 0.0

    # Al terminar el bucle
    ganancia_abs = capital - BANK_INICIAL
    ganancia_pct = (ganancia_abs / BANK_INICIAL) * 100.0
    print("Capital final: {:.2f} USDT".format(capital))
    print("Ganancia absoluta: {:.2f} USDT".format(ganancia_abs))
    print("Ganancia %: {:.2f}%".format(ganancia_pct))


if __name__ == "__main__":
    main()
