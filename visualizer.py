import json
import asyncio
import time
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf

from matplotlib.animation import FuncAnimation
from bitget.v1.mix.account_api import AccountApi
from bitget.v1.mix.market_api import MarketApi
# Ojo: Bitget no siempre provee librería oficial WebSocket para Python.
# Podrías usar websockets o la librería "bitget_ws" si existiese.

import websockets  # pip install websockets

api_key = "TU_API_KEY"
secret_key = "TU_SECRET_KEY"
passphrase = "TU_PASSPHRASE"

account_api = AccountApi(api_key, secret_key, passphrase)
market_api  = MarketApi(api_key, secret_key, passphrase)

# Diccionario para convertir timeframe a "orden" de canal en WS (dependerá de la doc. Bitget)
# Por ejemplo, en Bitget, a veces el canal para 1m es "candle1m", 3m -> "candle3m", etc.
timeframe_ws_channel = {
    "1m":  "candle1m",
    "3m":  "candle3m",
    "5m":  "candle5m",
    "15m": "candle15m",
    "30m": "candle30m",
    "1h":  "candle1H",
    "4h":  "candle4H",
    "6h":  "candle6H",
    "12h": "candle12H",
    "1d":  "candle1D"
}

# Aquí guardaremos todas las velas de forma local, en un DataFrame (o diccionario).
# Se irá actualizando al suscribirnos por WS.
candles_df = pd.DataFrame(columns=["date","open","high","low","close","volume"])

# Parámetros globales
current_symbol = ""
granularity_str = ""
ws_url = "wss://ws.bitgetapi.com/mix/v1/stream"  # Ajusta según la doc. Bitget
stop_ws = False  # Para detener el loop de websockets
last_candle_key = None

###############################################################################
# 1) Función que lanza la suscripción WebSocket y actualiza localmente las velas
###############################################################################
async def run_websocket(symbol: str, tf_str: str):
    """
    Se conecta al websocket, suscribe al canal de velas, y actualiza 'candles_df' global.
    Dependiendo de la doc. real de Bitget, los parámetros de suscripción pueden variar.
    """
    global candles_df, last_candle_key, stop_ws

    # Nombre de canal según timeframe
    ws_channel = timeframe_ws_channel[tf_str]
    
    # Prepara un mensaje de suscripción. (Ejemplo, la doc puede ser distinta).
    # Revisar doc oficial: https://bitgetlimited.github.io/apidoc/en/mix.html#websocket
    # Sustituye "symbol" y la parte de "channel" con el real. 
    subscribe_msg = {
        "op": "subscribe",
        "args": [
            {
                "instType": "MC",            # Mix Contract
                "channel": ws_channel,       # "candle1m", "candle5m", etc.
                "instId": symbol             # e.g. "BTCUSDT_UMCBL"
            }
        ]
    }

    async for websocket in websockets.connect(ws_url):
        try:
            # Enviamos suscripción
            await websocket.send(json.dumps(subscribe_msg))
            print(f"[WS] Suscrito a {ws_channel} para {symbol}")
            
            # Esperamos mensajes
            while not stop_ws:
                msg_raw = await websocket.recv()
                msg = json.loads(msg_raw)

                # Verificamos si es un "data" de velas
                # Según la doc, la estructura vendrá en 'data' o algo similar:
                # {
                #    "action": "snapshot" / "update",
                #    "arg": { "instType":..., "channel":..., "instId":... },
                #    "data": [ [timestamp, open, high, low, close, volume], ... ]
                # }
                if "data" in msg:
                    data_array = msg["data"]
                    # data_array puede traer 1 o varias velas. Ej:
                    # [
                    #   [ "1684466400000", "26790", "26795", "26785", "26790", "123.45" ],
                    #   ...
                    # ]
                    for item in data_array:
                        # item[0] = timestamp en ms
                        # item[1..5] = open, high, low, close, volume
                        ts = int(item[0])
                        o = float(item[1])
                        h = float(item[2])
                        l = float(item[3])
                        c = float(item[4])
                        v = float(item[5])

                        dt = datetime.datetime.utcfromtimestamp(ts / 1000.0)

                        # Generamos una "clave" para la vela => dt para la timeframe
                        # (Si la doc oficial indica que la vela es la ya cerrada, estará con un timestamp distinto)
                        candle_key = dt

                        # Actualizar o insertar en candles_df
                        # 1) Si la vela ya existía => actualizamos high, low, close, volume
                        # 2) Si no existía => es una nueva, la insertamos.
                        #   (El exchange mandará la vela cerrada o en formación, varía según canal.)
                        existing_idx = candles_df.index[candles_df["date"] == candle_key]
                        if len(existing_idx) > 0:
                            idx = existing_idx[0]
                            # Actualizamos
                            candles_df.loc[idx,"open"]   = o
                            candles_df.loc[idx,"high"]   = h
                            candles_df.loc[idx,"low"]    = l
                            candles_df.loc[idx,"close"]  = c
                            candles_df.loc[idx,"volume"] = v
                        else:
                            # Insertamos al final
                            new_row = {
                                "date": candle_key,
                                "open": o,
                                "high": h,
                                "low": l,
                                "close": c,
                                "volume": v
                            }
                            candles_df = pd.concat([candles_df, pd.DataFrame([new_row])], ignore_index=True)

                        # Mantenemos track del candle_key + close si hiciera falta
                        last_candle_key = candle_key

                # else: podrían llegar pings, etc.
        except websockets.ConnectionClosed as e:
            print("[WS] Conexión cerrada, intentando reconectar...", e)
            # Reintentamos conectarnos
            continue
        except Exception as e:
            print("[WS] Error en loop de WS:", e)
            # Reintentamos conectarnos
            continue

        if stop_ws:
            print("[WS] stop_ws=True => salimos del loop.")
            break

###############################################################################
# 2) Generador de DataFrame final para dibujar con mplfinance
###############################################################################
def get_candles_df_for_mpf():
    """
    Toma el global 'candles_df', lo ordena por fecha, y le pone set_index('date').
    Devuelve una copia para que no haya conflictos en vivo.
    """
    global candles_df
    if candles_df.empty:
        return pd.DataFrame(columns=["open","high","low","close","volume"])

    df_copy = candles_df.copy()
    df_copy.sort_values("date", inplace=True)
    df_copy.reset_index(drop=True, inplace=True)
    df_copy.set_index("date", inplace=True)
    return df_copy

###############################################################################
# 3) Lógica para indicadores
###############################################################################
def compute_wma(series, period=25):
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda x: np.sum(x * weights) / np.sum(weights), raw=True)

def compute_hma(series, period):
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    wma_half = compute_wma(series, half_period)
    wma_full = compute_wma(series, period)
    diff = 2 * wma_half - wma_full
    return compute_wma(diff, sqrt_period)

def compute_indicators(df):
    if len(df) < 1:
        return df
    df["vwma10"] = (
        (df["close"] * df["volume"]).rolling(window=10).sum()
        / df["volume"].rolling(window=10).sum()
    )
    df["hma70"] = compute_hma(df["close"], 70)
    df["ema99"] = df["close"].ewm(span=99, adjust=False).mean()
    return df

###############################################################################
# 4) Función de dibujado (FuncAnimation)
###############################################################################
fig = None

def update_chart(frame):
    global fig

    # 1) Obtenemos DF de las velas actual
    df_mpf = get_candles_df_for_mpf()
    if df_mpf.empty or len(df_mpf) < 2:
        return

    # 2) Reseteamos
    plt.clf()

    # 3) Calculamos indicadores
    df_mpf = df_mpf.assign(
        open=pd.to_numeric(df_mpf["open"], errors="coerce"),
        high=pd.to_numeric(df_mpf["high"], errors="coerce"),
        low =pd.to_numeric(df_mpf["low"],  errors="coerce"),
        close=pd.to_numeric(df_mpf["close"],errors="coerce"),
        volume=pd.to_numeric(df_mpf["volume"], errors="coerce")
    )
    df_mpf = compute_indicators(df_mpf)

    # 4) Construimos "addplot" para los indicadores
    apds = []
    if "vwma10" in df_mpf.columns:
        apds.append(mpf.make_addplot(df_mpf["vwma10"], color="lime", width=0.7))
    if "hma70" in df_mpf.columns:
        apds.append(mpf.make_addplot(df_mpf["hma70"], color="orange", width=0.7))
    if "ema99" in df_mpf.columns:
        apds.append(mpf.make_addplot(df_mpf["ema99"], color="blue", width=0.7))

    # 5) Dibujamos con mplfinance (sin ejes externos)
    mpf.plot(
        df_mpf,
        type="candle",
        style="binance",
        addplot=apds,
        volume=False,
        show_nontrading=False,
        block=False
    )
    plt.title(f"{current_symbol} - {granularity_str} (WebSocket Real-Time)")

    # 6) Revisamos posición abierta y ponemos texto en la figura actual
    pos_text = ""
    try:
        pos_resp = account_api.singlePosition({"symbol": current_symbol, "marginCoin": "USDT"})
        if isinstance(pos_resp, str):
            pos_resp = json.loads(pos_resp)
        if pos_resp.get("code") == "00000":
            data_list = pos_resp.get("data", [])
            if data_list:
                pos_info = data_list[0]
                size = float(pos_info.get("available", 0))
                holdSide = pos_info.get("holdSide", "").lower()
                if size > 0:
                    if holdSide == "long":
                        pos_text = f"Posición abierta: LONG ({size:.4f} contratos)"
                    elif holdSide == "short":
                        pos_text = f"Posición abierta: SHORT ({size:.4f} contratos)"
    except Exception as e:
        print("[ERROR posición] =>", e)

    ax = plt.gca()
    ax.text(
        0.01, 0.95,
        pos_text,
        transform=ax.transAxes,
        fontsize=9,
        color="red",
        verticalalignment="top",
        bbox=dict(facecolor="white", alpha=0.4)
    )

###############################################################################
# 5) main() => Lanza el WS en un hilo de asyncio y la ventana de matplotlib
###############################################################################
import threading
import asyncio

def main():
    global current_symbol, granularity_str, fig

    print("== Pares de Futuros UMCBL disponibles ==")
    resp = market_api.contracts({"productType": "umcbl"})
    if isinstance(resp, str):
        resp = json.loads(resp)

    if resp.get("code") == "00000":
        data_list = resp.get("data", [])
        symbols = [d["symbol"] for d in data_list]
    else:
        print("Error en la respuesta de pares:", resp)
        return

    for i, s in enumerate(symbols, start=1):
        print(f"{i}. {s}")

    # Selección de par
    while True:
        try:
            sel = int(input("\nElige el número del par: "))
            if 1 <= sel <= len(symbols):
                current_symbol = symbols[sel - 1]
                print(f"Has elegido: {current_symbol}")
                break
            else:
                print(f"Elige entre 1 y {len(symbols)}")
        except:
            print("Entrada no válida")

    # Selección de timeframe
    print("\n== Temporalidades Disponibles ==\n")
    tf_keys = list(timeframe_ws_channel.keys())  # ["1m","3m","5m","15m","30m","1h","4h","6h","12h","1d"]
    for i, tf in enumerate(tf_keys, start=1):
        print(f"{i}. {tf}")

    while True:
        try:
            sel = int(input("\nElige el número de la temporalidad: "))
            if 1 <= sel <= len(tf_keys):
                granularity_str = tf_keys[sel - 1]
                break
            else:
                print(f"Elige entre 1 y {len(tf_keys)}")
        except:
            print("Entrada no válida")

    print(f"\nIniciando WebSocket para {current_symbol}, tf={granularity_str}")

    # Lanzamos la corrutina en un hilo aparte
    def ws_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_websocket(current_symbol, granularity_str))

    t = threading.Thread(target=ws_thread, daemon=True)
    t.start()

    # Preparamos la animación con matplotlib
    fig = plt.gcf()
    ani = FuncAnimation(fig, update_chart, interval=3000)  # refresca cada 3s
    plt.show()

    # Al cerrar plt, pedimos fin del ws
    global stop_ws
    stop_ws = True
    t.join()
    print("Programa finalizado.")

if __name__ == "__main__":
    main()
