import numpy as np
import json
import pandas as pd
import time
import datetime
from bitget.v1.mix.market_api import MarketApi
from bitget.v1.mix.account_api import AccountApi
from bitget.v1.mix.order_api import OrderApi

# =============================================================================
# 1) CONFIGURACIÓN INICIAL Y CONEXIÓN A LAS API
# =============================================================================

api_key = "bg_aa37923b26ef877b6da55850f7414e09"
secret_key = "663ace63046a0fa7c5098d2315a69a6aa10fb8f829a92e447dd8e231e8c0fe74"
passphrase = "Queputamierdaesestosalu2"

account_api = AccountApi(api_key, secret_key, passphrase)
market_api  = MarketApi(api_key, secret_key, passphrase)
order_api   = OrderApi(api_key, secret_key, passphrase)

timeframe_map_bitget = {
    "1m":  "1m",
    "3m":  "3m",
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "1H",
    "4h":  "4H",
    "6h":  "6H",
    "12h": "12H",
    "1d":  "1D"
}

timeframe_sleep_map = {
    "1m":  60,
    "3m":  180,
    "5m":  300,
    "15m": 900,
    "30m": 1800,
    "1h":  3600,
    "4h":  14400,
    "6h":  21600,
    "12h": 43200,
    "1d":  86400
}

# =============================================================================
# 2) VARIABLES GLOBALES
# =============================================================================

position = None  # "long", "short" o None

# Trailing stop en la posición => 2.0%
trailing_data = {
    "peak_ratio": None,
    "trailing_drop": 0.02
}

# Trailing stop diario del equity
daily_stop_data = {
    "start_equity": 0.0,
    "peak_equity": 0.0,
    "trailing_drawdown": 0.1
}
dailyStop = False
current_date = datetime.date.today()

# =============================================================================
# 3) OBTENER SALDO DISPONIBLE DEL USUARIO
# =============================================================================

params_balance = {"productType": "umcbl"}

try:
    print("Consultando saldo disponible en Bitget (umcbl)...\n")
    resp_balance = account_api.accounts(params_balance)
    if isinstance(resp_balance, str):
        resp_balance = json.loads(resp_balance)
    
    balances_list = []
    if resp_balance.get("code") == "00000" and isinstance(resp_balance.get("data"), list):
        balances_list = resp_balance["data"]
        if len(balances_list) == 0:
            print("No se encontraron balances para este tipo de producto.")
        else:
            for bal in balances_list:
                margin_coin = bal.get("marginCoin")
                available = bal.get("available")
                equity = bal.get("equity")
                print(f"Moneda: {margin_coin}")
                print(f"Saldo disponible: {available}")
                print(f"Saldo total (equity): {equity}\n")
    else:
        print(f"Error o datos no encontrados en la respuesta: {resp_balance}")
except Exception as e:
    print(f"Error consultando balances: {e}")

# =============================================================================
# 4) ELECCIÓN DE PAR Y TIMEFRAME
# =============================================================================

params_contracts = {"productType": "umcbl"}
response = market_api.contracts(params_contracts)

if isinstance(response, str):
    try:
        response = json.loads(response)
    except json.JSONDecodeError:
        print("Lectura de datos de pares: incorrecto => Respuesta no es JSON válido.")
        raise SystemExit("No se pudo obtener la lista de pares correctamente.")

if response.get("code") == "00000":
    print("Lectura de datos de pares: correcto")
    contratos = response.get("data", [])
else:
    print(f"Lectura de datos de pares: incorrecto => {response}")
    raise SystemExit("No se pudo obtener la lista de pares correctamente.")

pares_futuros = [c['symbol'] for c in contratos]

print("\n== Pares de Futuros Disponibles (umcbl) ==\n")
for i, par in enumerate(pares_futuros, start=1):
    print(f"{i}. {par}")

while True:
    try:
        sel_par = int(input("\nElige el número del par: "))
        if 1 <= sel_par <= len(pares_futuros):
            par_seleccionado = pares_futuros[sel_par - 1]
            print(f"Has seleccionado: {par_seleccionado}")
            break
        else:
            print(f"Introduce un número entre 1 y {len(pares_futuros)}.")
    except ValueError:
        print("Entrada no válida. Usa un número entero.")

print("\n== Temporalidades Disponibles ==\n")
tfs = list(timeframe_map_bitget.keys())
for i, tf in enumerate(tfs, start=1):
    print(f"{i}. {tf}")

while True:
    try:
        sel_tf = int(input("\nElige el número de la temporalidad: "))
        if 1 <= sel_tf <= len(tfs):
            timeframe_str = tfs[sel_tf - 1]
            break
        else:
            print(f"Introduce un número entre 1 y {len(tfs)}.")
    except ValueError:
        print("Entrada no válida. Usa un número entero.")

bitget_granularity = timeframe_map_bitget[timeframe_str]
intervalo = timeframe_sleep_map[timeframe_str]

print(f"\nHas elegido {par_seleccionado} con velas {timeframe_str}. "
      f"\n\t => Para Bitget: granularity={bitget_granularity}"
      f"\n\t => Esperaremos {intervalo} seg entre consultas.")

# =============================================================================
# 5) CONFIGURAR APALANCAMIENTO Y CANTIDAD DE SALDO A UTILIZAR
# =============================================================================

def set_leverage_for_both_sides(account_api, symbol, margin_coin, leverage):
    lev_str = str(int(leverage))
    # Llamada para LONG
    params_long = {
        "symbol": symbol,
        "marginCoin": margin_coin,
        "leverage": lev_str,
        "holdSide": "long"
    }
    resp_long = account_api.setLeverage(params_long)
    print("Respuesta setLeverage (LONG):", resp_long)
    # Llamada para SHORT
    params_short = {
        "symbol": symbol,
        "marginCoin": margin_coin,
        "leverage": lev_str,
        "holdSide": "short"
    }
    resp_short = account_api.setLeverage(params_short)
    print("Respuesta setLeverage (SHORT):", resp_short)

try:
    user_leverage_input = input("\nIndica el apalancamiento que deseas usar (por defecto=1x): ")
    user_leverage = str(int(user_leverage_input)) if user_leverage_input.strip() else "1"
except ValueError:
    user_leverage = "1"

print(f"Intentando configurar {user_leverage}x de apalancamiento en Bitget...\n")
margin_coin = "USDT"
set_leverage_for_both_sides(account_api, par_seleccionado, margin_coin, user_leverage)

usdt_available = 0.0
for bal in balances_list:
    if bal.get("marginCoin") == "USDT":
        usdt_available = float(bal.get("available", 0))
        break
if usdt_available <= 0:
    print("No se encontró saldo en USDT o es 0. Se usará 0 para el cálculo.")

def get_contract_info(market_api, symbol):
    contracts_info = market_api.contracts({"productType": "umcbl"})
    if isinstance(contracts_info, str):
        contracts_info = json.loads(contracts_info)
    for c in contracts_info.get("data", []):
        if c.get("symbol") == symbol:
            return {
                "sizeMultiplier": float(c.get("sizeMultiplier", "0.01")),
                "minTradeNum": float(c.get("minTradeNum", "0.1"))
            }
    return {"sizeMultiplier": 0.01, "minTradeNum": 0.1}

def get_minimum_position_usdt(market_api, symbol, leverage_str):
    leverage = float(leverage_str)
    info = get_contract_info(market_api, symbol)
    sizeMultiplier = info["sizeMultiplier"]
    minTradeNum = info["minTradeNum"]

    tickers_resp = market_api.tickers({"symbol": symbol, "productType": "umcbl"})
    if isinstance(tickers_resp, str):
        tickers_resp = json.loads(tickers_resp)
    last_price = 1.0
    if tickers_resp.get("code") == "00000" and "data" in tickers_resp:
        ticker_list = tickers_resp["data"]
        if isinstance(ticker_list, list) and len(ticker_list) > 0:
            last_price = float(ticker_list[0].get("last", "1.0"))

    min_funds = (minTradeNum * sizeMultiplier * last_price) / leverage
    return min_funds

min_position_usdt = get_minimum_position_usdt(market_api, par_seleccionado, user_leverage)
print(f"\nPara el par {par_seleccionado} con apalancamiento {user_leverage}x, "
      f"el monto mínimo en USDT (según contrato) para abrir una orden es: {min_position_usdt:.2f} USDT.")

print("\n¿Deseas introducir una cantidad fija en USDT (1) o un porcentaje de tu saldo (2)?")
choice = input("Elige 1 o 2 (por defecto 1): ").strip()
if choice == "2":
    try:
        percent_input = input("¿Qué porcentaje de tu saldo disponible en USDT deseas usar? (0-100): ")
        percent_value = float(percent_input)
        if percent_value < 0 or percent_value > 100:
            print("Porcentaje no válido. Usaré 10% por defecto.")
            percent_value = 10.0
        user_funds = usdt_available * (percent_value / 100.0)
        print(f"Has elegido {percent_value}% de tu saldo disponible ({usdt_available:.2f} USDT).")
    except ValueError:
        user_funds = 10.0
        print(f"Valor no válido. Se usará el 10% de tu saldo por defecto => {user_funds:.2f} USDT.")
else:
    try:
        user_funds_input = input("Introduce la cantidad fija de USDT que deseas usar: ")
        user_funds = float(user_funds_input) if user_funds_input.strip() else 10.0
    except ValueError:
        user_funds = 10.0
        print("Valor no válido. Se usará 10.0 USDT por defecto.")

print(f"\nSe usará {user_funds:.2f} USDT por operación.\n")


# =============================================================================
# 6) FUNCIÓN DE OBTENCIÓN DE VELAS (MULTIPLES LLAMADAS A .candles())
# =============================================================================

def fetch_candles_bitget(market_api, symbol, granularity_str, product_type,
                         total_candles=300, max_per_call=200):
    """
    Obtiene 'total_candles' velas (o más) usando la API .candles()
    que tiene un límite (por ej. 200 velas). Haremos múltiples solicitudes,
    moviendo la ventana [startTime, endTime] hacia atrás.
    """

    all_candles = []
    end_time = int(time.time() * 1000)  # en ms

    # Para estimar la duración de cada vela según granularity:
    seconds_per_candle_map = {
        "1m":  60,
        "3m":  180,
        "5m":  300,
        "15m": 900,
        "30m": 1800,
        "1H":  3600,
        "4H":  14400,
        "6H":  21600,
        "12H": 43200,
        "1D":  86400
    }
    sec_per_candle = seconds_per_candle_map.get(granularity_str, 60)

    while len(all_candles) < total_candles:
        start_time = end_time - (max_per_call * sec_per_candle * 1000)

        params = {
            "symbol": symbol,
            "granularity": granularity_str,
            "startTime": str(start_time),
            "endTime": str(end_time),
            "pageSize": str(max_per_call),
            "productType": product_type
        }

        resp = market_api.candles(params)
        if isinstance(resp, str):
            try:
                resp = json.loads(resp)
            except:
                print("Error: respuesta no es JSON válido al obtener velas con 'candles'.")
                break

        if isinstance(resp, dict) and "data" in resp:
            data_chunk = resp["data"]
        elif isinstance(resp, list):
            data_chunk = resp
        else:
            print("Respuesta inesperada al pedir velas:", resp)
            data_chunk = []

        if not data_chunk:
            # Si no hay más velas, salimos
            break

        # Normalmente, 'candles' devuelve la + reciente primero.  
        # Invertimos para tener orden ascendente temporal:
        data_chunk.reverse()

        all_candles.extend(data_chunk)

        # Actualizamos end_time:
        oldest_ts = data_chunk[0][0]
        end_time = int(oldest_ts) - 1

        if len(all_candles) >= total_candles:
            break

        time.sleep(0.2)

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume", "extra"])
    
    for col in ["timestamp", "open", "high", "low", "close", "volume", "extra"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df.dropna(subset=["open", "high", "low", "close"], inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df[["timestamp", "open", "high", "low", "close", "volume"]]


# =============================================================================
# INDICADORES
# =============================================================================

def compute_wma(series, period=25):
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda x: np.sum(x * weights) / np.sum(weights), raw=True)

def compute_hma(series, period):
    """Hull Moving Average (HMA)"""
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    wma_half = compute_wma(series, half_period)
    wma_full = compute_wma(series, period)
    diff = 2 * wma_half - wma_full
    hma = compute_wma(diff, sqrt_period)
    return hma

def compute_atr(df, period=14):
    """
    Cálculo de ATR(14) por defecto (fórmula clásica con media exponencial).
    """
    df["range1"] = df["high"] - df["low"]
    df["range2"] = (df["high"] - df["close"].shift(1)).abs()
    df["range3"] = (df["low"]  - df["close"].shift(1)).abs()
    df["true_range"] = df[["range1", "range2", "range3"]].max(axis=1)
    # ATR con una media exponencial:
    df["atr"] = df["true_range"].ewm(span=period, adjust=False).mean()
    return df

def compute_indicators(df):
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df.dropna(subset=["close"], inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # VWMA(10)
    df["vwma10"] = (
        (df["close"] * df["volume"]).rolling(window=10).sum()
        / df["volume"].rolling(window=10).sum()
    )

    # HMA(70)
    df["hma70"] = compute_hma(df["close"], 70)

    # EMA(99)
    df["ema99"] = df["close"].ewm(span=99, adjust=False).mean()

    # ATR(14)
    df = compute_atr(df, period=14)

    # Eliminamos NaN extra generados en el cálculo inicial de ATR
    df.dropna(inplace=True)

    return df

def calcular_indicadores(market_api, symbol, granularity_str, tf_sleep, n_candles=300):
    """
    Se obtienen n_candles velas para tener suficiente historial al calcular HMA(70)+EMA(99)+ATR.
    """
    df = fetch_candles_bitget(
        market_api=market_api,
        symbol=symbol,
        granularity_str=granularity_str,
        product_type="umcbl",
        total_candles=n_candles,
        max_per_call=200
    )
    if df.empty or len(df) < 100:
        print("No hay suficientes velas para calcular indicadores.")
        return pd.DataFrame()

    df = compute_indicators(df)
    return df

# =============================================================================
# 7) TRAILING STOP DIARIO
# =============================================================================

def init_daily_equity():
    global daily_stop_data, dailyStop, current_date
    current_date = datetime.date.today()
    dailyStop = False
    eq_resp = account_api.accounts({"productType": "umcbl"})
    if isinstance(eq_resp, str):
        eq_resp = json.loads(eq_resp)
    if eq_resp.get("code") == "00000" and "data" in eq_resp:
        eq_found = 0.0
        for bal in eq_resp["data"]:
            if bal.get("marginCoin") == "USDT":
                eq_found = float(bal.get("equity", 0))
                break
        daily_stop_data["start_equity"] = eq_found
        daily_stop_data["peak_equity"]  = eq_found
        print(f"[init_daily_equity] start_equity={eq_found:.2f}, peak_equity={eq_found:.2f}")
    else:
        daily_stop_data["start_equity"] = 0.0
        daily_stop_data["peak_equity"]  = 0.0
        print("No se pudo determinar el equity inicial.")

def check_daily_trailing_stop():
    global dailyStop, daily_stop_data
    if dailyStop:
        return
    eq_resp = account_api.accounts({"productType": "umcbl"})
    if isinstance(eq_resp, str):
        eq_resp = json.loads(eq_resp)
    if eq_resp.get("code") == "00000" and "data" in eq_resp:
        current_equity = 0.0
        for bal in eq_resp["data"]:
            if bal.get("marginCoin") == "USDT":
                current_equity = float(bal.get("equity", 0))
                break
        if current_equity > daily_stop_data["peak_equity"]:
            daily_stop_data["peak_equity"] = current_equity
        max_equity  = daily_stop_data["peak_equity"]
        drawdown_pct = daily_stop_data["trailing_drawdown"]
        if current_equity <= max_equity * (1 - drawdown_pct):
            print(f"[DailyStop] Retroceso en equity diario: eq actual={current_equity:.2f}, peak={max_equity:.2f}, "
                  f"drawdown={drawdown_pct*100:.1f}% => Se detienen nuevas operaciones.")
            dailyStop = True

def reset_if_new_day_trail_equity():
    global current_date
    now = datetime.date.today()
    if now > current_date:
        print("[Cambio de día] Se resetea dailyStop y se recalcula equity inicial (trailing).")
        init_daily_equity()

# =============================================================================
# 8) LÓGICA DE ESTRATEGIA Y TRAILING DE POSICIÓN
# =============================================================================

def apply_strategy(df):
    """
    Estrategia:
      - Señal de entrada LONG => price > vwma10 > hma70 > ema99 => open_long
      - Señal de entrada SHORT => price < vwma10 < hma70 < ema99 => open_short

      - StopLoss LONG => close < (hma70 - 0.5 * ATR) => close_long
      - StopLoss SHORT => close > (hma70 + 0.5 * ATR) => close_short
    """
    global position
    if len(df) < 1:
        return None

    last = df.iloc[-1]
    price  = last["close"]
    vwma10 = last["vwma10"]
    hma70  = last["hma70"]
    ema99  = last["ema99"]
    atr    = last["atr"]

    # Multiplicador para el "colchón" de ATR
    atr_multiplier = 0.5
    buffer_atr = atr_multiplier * atr

    if position is None:
        # Abrir LONG
        if (price > vwma10) and (vwma10 > hma70) and (hma70 > ema99):
            return "open_long"
        # Abrir SHORT
        if (price < vwma10) and (vwma10 < hma70) and (hma70 < ema99):
            return "open_short"

    elif position == "long":
        # StopLoss LONG => se activa si el CIERRE de la vela < (hma70 - buffer)
        if price < (hma70 - buffer_atr):
            return "close_long"

    elif position == "short":
        # StopLoss SHORT => se activa si el CIERRE de la vela > (hma70 + buffer)
        if price > (hma70 + buffer_atr):
            return "close_short"

    return None

def check_position_trailing_stop(account_api, symbol, margin_coin):
    """
    Trailing Stop basado en 'trailing_data["trailing_drop"]', 
    que usa ratio = upl/margin_used.
    Si el ratio retrocede X% desde su pico => cierra.
    """
    global position, trailing_data
    if position is None:
        trailing_data["peak_ratio"] = None
        return
    pos_resp = account_api.singlePosition({"symbol": symbol, "marginCoin": margin_coin})
    if isinstance(pos_resp, str):
        pos_resp = json.loads(pos_resp)
    if pos_resp.get("code") != "00000":
        return
    data_list = pos_resp.get("data", [])
    if not data_list:
        return
    pos_info = data_list[0]
    upl = float(pos_info.get("unrealizedPL", 0))
    margin_used = float(pos_info.get("margin", 0))
    if margin_used <= 0:
        return

    ratio = upl / margin_used
    if trailing_data["peak_ratio"] is None:
        trailing_data["peak_ratio"] = ratio
        return
    else:
        if ratio > trailing_data["peak_ratio"]:
            trailing_data["peak_ratio"] = ratio
        drop_amount = trailing_data["peak_ratio"] - ratio
        if drop_amount >= trailing_data["trailing_drop"]:
            print(f"[TRAILING STOP pos] ratio actual={ratio:.4f}, peak={trailing_data['peak_ratio']:.4f}, "
                  f"drop={drop_amount:.4f} >= {trailing_data['trailing_drop']}. Cerramos posición.")
            if position == "long":
                close_side = "close_long"
            else:
                close_side = "close_short"

            posSize = pos_info.get("available", 0)
            if posSize:
                ok = place_order_bitget_v2(
                    order_api,
                    symbol,
                    margin_coin,
                    close_side,
                    size=posSize,
                    order_type="market",
                    openType="cross",
                    leverage=user_leverage
                )
                if ok:
                    position = None
                    trailing_data["peak_ratio"] = None

# =============================================================================
# 9) FUNCIONES DE ORDEN (v2)
# =============================================================================

def place_order_bitget_v2(order_api, symbol, margin_coin, side, size,
                          order_type="market", price=None,
                          openType="cross", leverage="10"):
    params = {
        "symbol": symbol,
        "marginCoin": margin_coin,
        "side": side,
        "orderType": order_type,
        "size": str(size),
        "timeInForceValue": "normal",
        "openType": openType,
        "leverage": leverage
    }
    if order_type == "limit" and price is not None:
        params["price"] = str(price)
    try:
        resp = order_api.placeOrder(params)
        if isinstance(resp, str):
            resp = json.loads(resp)
        print("placeOrder respuesta:", resp)
        if resp.get("code") == "00000":
            print("Orden colocada con éxito.")
            return True
        else:
            print("Error al colocar la orden:", resp)
            return False
    except Exception as e:
        print("Excepción al colocar la orden:", e)
        return False

def calculate_contracts_for_usdt(market_api, symbol, user_funds, user_leverage):
    contracts_info = market_api.contracts({"productType": "umcbl"})
    if isinstance(contracts_info, str):
        contracts_info = json.loads(contracts_info)

    sizeMultiplier = 0.01
    minTradeNum = 0.1
    if contracts_info.get("code") == "00000" and "data" in contracts_info:
        for c in contracts_info["data"]:
            if c.get("symbol") == symbol:
                sizeMultiplier = float(c.get("sizeMultiplier", "0.01"))
                minTradeNum = float(c.get("minTradeNum", "0.1"))
                break

    tickers_resp = market_api.tickers({"symbol": symbol, "productType": "umcbl"})
    if isinstance(tickers_resp, str):
        tickers_resp = json.loads(tickers_resp)

    last_price = 1.0
    if tickers_resp.get("code") == "00000" and "data" in tickers_resp:
        ticker_list = tickers_resp["data"]
        if isinstance(ticker_list, list) and len(ticker_list) > 0:
            first_ticker = ticker_list[0]
            last_price = float(first_ticker.get("last", 1.0))

    valor_contrato = sizeMultiplier * last_price
    notional = user_funds * float(user_leverage)

    min_order_value = 5.0  # USDT mínimo de orden
    if notional < min_order_value:
        print(f"[DEBUG] Fondos insuficientes: notional {notional:.2f} USDT < {min_order_value} USDT mínimo.")
        return 0

    contracts = notional / valor_contrato
    if contracts < minTradeNum:
        print(f"[DEBUG] Contratos calculados ({contracts:.6f}) < minTradeNum ({minTradeNum}). Se ajusta al mínimo.")
        contracts = minTradeNum
    return contracts

def place_order_with_usdt_v2(order_api, market_api, symbol, margin_coin, side,
                             user_funds, order_type="market", price=None,
                             openType="cross", leverage="10"):
    lev_float = float(leverage)
    contracts = calculate_contracts_for_usdt(market_api, symbol, user_funds, lev_float)
    if contracts <= 0:
        print("[ABORTAR] Contratos = 0. No se envía la orden al exchange.")
        return False
    contracts = round(contracts, 6)
    return place_order_bitget_v2(
        order_api, symbol, margin_coin, side,
        contracts, order_type, price,
        openType, leverage
    )

# =============================================================================
# NUEVA FUNCIÓN: SINCRONIZACIÓN CON CIERRE DE VELA
# =============================================================================

def sync_to_candle_close(interval_secs):
    """
    Espera hasta que el tiempo (local) sea múltiplo de `interval_secs`.
    Por ejemplo, si estamos en 5m (300s) y han pasado 2 min de la vela,
    espera 3 min más para que la vela actual finalice.
    """
    now_ts = int(time.time())
    remainder = now_ts % interval_secs
    if remainder != 0:
        wait_time = interval_secs - remainder
        print(f"Sincronizando con la vela. Faltan {wait_time} seg para el cierre de la vela actual...")
        time.sleep(wait_time)
    print("¡Listo! Comenzamos con una vela nueva.")


# =============================================================================
# 10) BUCLE PRINCIPAL
# =============================================================================

init_daily_equity()

# Sincronizamos con la vela actual antes de empezar el while
sync_to_candle_close(intervalo)

print("\nPresiona Ctrl + C para detener...\n")

while True:
    reset_if_new_day_trail_equity()
    check_daily_trailing_stop()
    check_position_trailing_stop(account_api, par_seleccionado, margin_coin)

    if dailyStop:
        print("[DailyStop] Activado. Se ignoran señales de apertura.")

    # Obtenemos ~300 velas
    df = calcular_indicadores(
        market_api, 
        par_seleccionado, 
        bitget_granularity, 
        intervalo, 
        n_candles=300
    )
    if df.empty or len(df) < 70:
        # Si no hay suficientes velas, esperamos al siguiente ciclo
        time.sleep(intervalo)
        continue

    # Aplicamos la estrategia (posible señal de open/close)
    signal = apply_strategy(df)
    if signal:
        print(f"Señal detectada: {signal}")

        if dailyStop and "open" in signal:
            print("[DailyStop] No se abre nueva posición.")
        else:
            # Ejecutamos la orden según la señal
            if signal == "open_long":
                ok = place_order_with_usdt_v2(
                    order_api, market_api,
                    symbol=par_seleccionado,
                    margin_coin="USDT",
                    side="open_long",
                    user_funds=user_funds,
                    order_type="market",
                    openType="cross",
                    leverage=user_leverage
                )
                if ok:
                    position = "long"
                    trailing_data["peak_ratio"] = 0.0

            elif signal == "close_long":
                ok = place_order_with_usdt_v2(
                    order_api, market_api,
                    symbol=par_seleccionado,
                    margin_coin="USDT",
                    side="close_long",
                    user_funds=user_funds,
                    order_type="market",
                    openType="cross",
                    leverage=user_leverage
                )
                if ok:
                    position = None
                    trailing_data["peak_ratio"] = None

            elif signal == "open_short":
                ok = place_order_with_usdt_v2(
                    order_api, market_api,
                    symbol=par_seleccionado,
                    margin_coin="USDT",
                    side="open_short",
                    user_funds=user_funds,
                    order_type="market",
                    openType="cross",
                    leverage=user_leverage
                )
                if ok:
                    position = "short"
                    trailing_data["peak_ratio"] = 0.0

            elif signal == "close_short":
                ok = place_order_with_usdt_v2(
                    order_api, market_api,
                    symbol=par_seleccionado,
                    margin_coin="USDT",
                    side="close_short",
                    user_funds=user_funds,
                    order_type="market",
                    openType="cross",
                    leverage=user_leverage
                )
                if ok:
                    position = None
                    trailing_data["peak_ratio"] = None

    # Información de debug de la última vela
    if not df.empty:
        last_row = df.iloc[-1]
        print(
            f"Última vela => close={last_row['close']:.4f}, "
            f"vwma10={last_row.get('vwma10', 'NA'):.4f}, "
            f"hma70={last_row.get('hma70', 'NA'):.4f}, "
            f"ema99={last_row.get('ema99', 'NA'):.4f}, "
            f"atr={last_row.get('atr', 'NA'):.4f}, "
            f"pos={position}, dailyStop={dailyStop}, "
            f"peak_equity={daily_stop_data['peak_equity']:.2f}, "
            f"peak_ratio={trailing_data['peak_ratio']}"
        )

    # Esperamos hasta la siguiente vela
    time.sleep(intervalo)
