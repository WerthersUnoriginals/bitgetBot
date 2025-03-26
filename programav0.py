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

# Credenciales de Bitget
api_key = "bg_aa37923b26ef877b6da55850f7414e09"
secret_key = "663ace63046a0fa7c5098d2315a69a6aa10fb8f829a92e447dd8e231e8c0fe74"
passphrase = "Queputamierdaesestosalu2"

# Instanciar las API
account_api = AccountApi(api_key, secret_key, passphrase)
market_api = MarketApi(api_key, secret_key, passphrase)
order_api = OrderApi(api_key, secret_key, passphrase)

# Mapeo de timeframe a string Bitget (para "granularity")
timeframe_map_bitget = {
    "1m":  "1m",
    "3m":  "3m",
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "1H",   # Bitget usa mayúscula H
    "4h":  "4H",
    "6h":  "6H",
    "12h": "12H",
    "1d":  "1D"
}

# Mapeo para time.sleep, en segundos
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

# Trailing stop en la posición
trailing_data = {
    "peak_ratio": None,    # pico máximo PnL relativo a la posición
    "trailing_drop": 0.02  # p.ej. 2%
}

# Trailing stop diario del equity
daily_stop_data = {
    "start_equity": 0.0,       # equity al inicio del día
    "peak_equity": 0.0,        # pico máximo de equity durante el día
    "trailing_drawdown": 0.02  # retroceso del 2% desde el pico => dailyStop
}
dailyStop = False
current_date = datetime.date.today()

# =============================================================================
# 3) OBTENER SALDO DISPONIBLE DEL USUARIO (PARA MOSTRARLO AL INICIO)
# =============================================================================

params_balance = {"productType": "umcbl"}

try:
    print("Consultando saldo disponible en Bitget (umcbl)...\n")
    resp_balance = account_api.accounts(params_balance)
    if isinstance(resp_balance, str):
        resp_balance = json.loads(resp_balance)
    
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
    response = json.loads(response)

if 'data' not in response or not isinstance(response['data'], list):
    print("No se pudieron obtener los contratos. Revisa tu conexión o API.")
    exit()

contratos = response['data']
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

# Granularity para Bitget
bitget_granularity = timeframe_map_bitget[timeframe_str]
# Intervalo (segundos) para time.sleep
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
margin_coin = "USDT"  # para umcbl
set_leverage_for_both_sides(account_api, par_seleccionado, margin_coin, user_leverage)

# Extraer saldo disponible en USDT
usdt_available = 0.0
if 'balances_list' in locals():
    for bal in balances_list:
        if bal.get("marginCoin") == "USDT":
            usdt_available = float(bal.get("available", 0))
            break
if usdt_available <= 0:
    print("No se encontró saldo en USDT o es 0. Se usará 0 para el cálculo.")

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
        user_funds_input = input("\nIntroduce la cantidad fija de USDT que deseas usar: ")
        user_funds = float(user_funds_input) if user_funds_input.strip() else 10.0
    except ValueError:
        user_funds = 10.0
        print("Valor no válido. Se usará 10.0 USDT por defecto.")

print(f"\nSe usará {user_funds:.2f} USDT por operación.\n")

# =============================================================================
# 6) FUNCIONES DE DESCARGA DE VELAS E INDICADORES
# =============================================================================

def fetch_normal_candles(market_api, symbol, granularity_str, sleep_seconds, num_candles=100):
    """
    - granularity_str: "1m","5m","1H" etc. para Bitget
    - sleep_seconds: para info (no se usa en la función en sí, pero lo pasamos para mantener estructura)
    - num_candles: cantidad de velas a descargar
    """
    end_time = int(time.time() * 1000)
    # Dependiendo de la temporalidad, calculamos un rango suficiente
    # Aun puedes usar num_candles * sleep_seconds si quieres, pero aquí un ejemplo:
    start_time = end_time - num_candles * 60_000  # p.ej. 1m * 100 => 100min
    # O ajustarlo mejor al timeframe

    params = {
        "symbol": symbol,
        "granularity": granularity_str,  # <= cadena que Bitget necesita
        "startTime": str(start_time),
        "endTime": str(end_time),
        "pageSize": str(num_candles),
        "productType": "umcbl"
    }
    resp = market_api.candles(params)
    if isinstance(resp, str):
        resp = json.loads(resp)
        print("Respuesta cruda de candles:", resp)
    if not isinstance(resp, list) or len(resp) == 0:
        print("No se obtuvieron velas o la respuesta está vacía.")
        return pd.DataFrame()

    try:
        df = pd.DataFrame(resp, columns=["timestamp", "open", "high", "low", "close", "volume", "extra"])
    except Exception as e:
        print("Error al crear el DataFrame:", e)
        return pd.DataFrame()
    
    for col in ["timestamp", "open", "high", "low", "close", "volume", "extra"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["open", "high", "low", "close"], inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    print("Cantidad de velas obtenidas:", df.shape[0])
    return df[["timestamp", "open", "high", "low", "close", "volume"]]

def compute_wma(series, period=25):
    weights = np.arange(1, period+1)
    return series.rolling(period).apply(lambda x: np.sum(x * weights) / np.sum(weights), raw=True)

def compute_indicators(df):
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df.dropna(subset=["close"], inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # EMA(100)
    df["ema100"] = df["close"].ewm(span=100, adjust=False).mean()
    # WMA(25)
    df["wma25"] = compute_wma(df["close"], 25)

    if pd.isna(df.iloc[-1]["ema100"]):
        print("Advertencia: EMA100 es NaN. Puede haber pocos datos.")
    return df

def calcular_indicadores(market_api, symbol, granularity_str, sleep_seconds):
    """
    Descarga velas con 'granularity_str' (p.ej "5m","1H") y hace compute_indicators
    """
    df = fetch_normal_candles(market_api, symbol, granularity_str, sleep_seconds, num_candles=100)
    if df.empty or len(df) < 100:
        print("No hay suficientes velas para calcular indicadores.")
        return pd.DataFrame()
    df = compute_indicators(df)
    print("\n=== Últimas 5 velas con EMA(100) y WMA(25) ===")
    print(df.tail(5))
    return df

# =============================================================================
# 7) TRADING: TRAILING STOP DIARIO DEL EQUITY
# =============================================================================

def init_daily_equity():
    """
    Captura el equity al inicio del día y lo asigna tanto a 'start_equity'
    como a 'peak_equity'. dailyStop=False
    """
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
    """
    1) Obtiene la equity actual
    2) Si equity > peak_equity => actualizamos peak_equity
    3) Si equity < peak_equity*(1 - trailing_drawdown) => dailyStop=True
    """
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

        # Actualizar pico si sube
        if current_equity > daily_stop_data["peak_equity"]:
            daily_stop_data["peak_equity"] = current_equity

        # chequear retroceso
        max_equity  = daily_stop_data["peak_equity"]
        drawdown_pct = daily_stop_data["trailing_drawdown"]  # p.ej. 0.02 => 2%
        if current_equity <= max_equity * (1 - drawdown_pct):
            print(f"[DailyStop] Retroceso en equity diario: eq actual={current_equity:.2f}, peak={max_equity:.2f}, "
                  f"drawdown={drawdown_pct*100:.1f}% => Se detienen nuevas operaciones.")
            dailyStop = True


def reset_if_new_day_trail_equity():
    """
    Si se ha cambiado de fecha, reinicializa la equity diaria.
    """
    global current_date
    now = datetime.date.today()
    if now > current_date:
        print("[Cambio de día] Se resetea dailyStop y se recalcula equity inicial (trailing).")
        init_daily_equity()


# =============================================================================
# 8) LÓGICA DE ENTRADA Y SALIDA DE LA POSICIÓN (TRAILING DE POSICIÓN)
# =============================================================================

def apply_strategy(df):
    global position
    if len(df) < 1:
        return None

    last = df.iloc[-1]
    price = last["close"]
    ema100 = last["ema100"]
    wma25 = last["wma25"]

    # EJEMPLO: media rápida > media lenta, etc.
    if position is None:
        if (wma25 > ema100) and (price > wma25):
            return "open_long"
        if (wma25 < ema100) and (price < wma25):
            return "open_short"
    elif position == "long":
        if price < wma25:
            return "close_long"
    elif position == "short":
        if price > wma25:
            return "close_short"
    return None


def check_position_trailing_stop(account_api, symbol, margin_coin):
    """
    Lógica de trailing stop en la posición:
    Se basa en (unrealizedPL / margin).
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

    ratio = upl / margin_used  # p.ej. 0.05 => +5%

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

def calculate_contracts_for_usdt(market_api, symbol, user_funds):
    contracts_info = market_api.contracts({"productType": "umcbl"})
    if isinstance(contracts_info, str):
        contracts_info = json.loads(contracts_info)

    multiplier_str = "0.001"
    minTradeNum_str = "0.001"

    if contracts_info.get("code") == "00000" and "data" in contracts_info:
        for c in contracts_info["data"]:
            if c.get("symbol") == symbol:
                multiplier_str = c.get("sizeMultiplier", "0.001")
                minTradeNum_str = c.get("minTradeNum", "0.001")
                break

    sizeMultiplier = float(multiplier_str)
    minTradeNum = float(minTradeNum_str)

    tickers_resp = market_api.tickers({"symbol": symbol, "productType": "umcbl"})
    if isinstance(tickers_resp, str):
        tickers_resp = json.loads(tickers_resp)

    last_price = 1.0
    if tickers_resp.get("code") == "00000" and "data" in tickers_resp:
        ticker_list = tickers_resp["data"]
        if isinstance(ticker_list, list) and len(ticker_list) > 0:
            first_ticker = ticker_list[0]
            last_price = float(first_ticker.get("last", 1.0))

    valor_un_contrato = sizeMultiplier * last_price
    contracts = user_funds / valor_un_contrato
    
    if contracts < minTradeNum:
        print(f"[DEBUG] Contratos calculados ({contracts:.6f}) < minTradeNum ({minTradeNum}).")
        print("No se puede abrir la orden: Contratos < minTradeNum.")
        # Forzamos la orden al mínimo
        contracts = minTradeNum

    return contracts

def place_order_with_usdt_v2(order_api, market_api, symbol, margin_coin, side,
                             user_funds, order_type="market", price=None,
                             openType="cross", leverage="10"):
    contracts = calculate_contracts_for_usdt(market_api, symbol, user_funds)
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
# 10) BUCLE PRINCIPAL
# =============================================================================

init_daily_equity()

print("\nPresiona Ctrl + C para detener...\n")

while True:
    time.sleep(intervalo)

    # 1) Verificar si cambió el día => resetear equity daily
    reset_if_new_day_trail_equity()

    # 2) Revisar trailing stop diario (equity total)
    check_daily_trailing_stop()

    # 3) Revisar trailing stop de la posición
    check_position_trailing_stop(account_api, par_seleccionado, margin_coin)

    # 4) Comprobar si dailyStop activo. Si True y la señal es de abrir, se ignora
    if dailyStop:
        print("[DailyStop] Activado. Se ignoran señales de apertura.")
    
    # 5) Descargar velas e interpretar la estrategia
    df = calcular_indicadores(market_api, par_seleccionado, bitget_granularity, intervalo)
    if df.empty or len(df) < 100:
        continue

    signal = apply_strategy(df)

    if signal:
        print(f"Señal detectada: {signal}")
        if dailyStop and "open" in signal:
            print("[DailyStop] No se abre nueva posición.")
        else:
            # Actuamos con la señal
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

    if not df.empty:
        last_row = df.iloc[-1]
        print(f"Última vela => close={last_row['close']:.2f}, "
              f"ema100={last_row['ema100']:.2f}, wma25={last_row['wma25']:.2f}, "
              f"pos={position}, dailyStop={dailyStop}, "
              f"peak_equity={daily_stop_data['peak_equity']:.2f}, "
              f"peak_ratio={trailing_data['peak_ratio']}")
