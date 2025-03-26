import ccxt
import pandas as pd
import time

exchange = ccxt.binance()
# Descarga velas de 1 min para SOL/USDT
symbol = 'SOL/USDT'
timeframe = '3m'
limit = 1000  # nº máximo de velas por request (varía según API)
all_ohlc = []

# Rango inicial (timestamp en milisegundos)
# Por ej. 2 años atrás:
desde = exchange.parse8601('2025-01-01T00:00:00Z')

while True:
    # Obtiene velas
    data = exchange.fetch_ohlcv(symbol, timeframe, since=desde, limit=limit)
    if not data:
        break
    all_ohlc += data
    # Avanza la marca temporal
    desde = data[-1][0] + 1
    time.sleep(0.5)  # pequeño delay para no saturar la API

# Convierte a DataFrame
df = pd.DataFrame(all_ohlc, columns=['timestamp','open','high','low','close','volume'])

# Resample a 3 min (si deseas):
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df.set_index('timestamp', inplace=True)
df_3m = df.resample('3T').agg({
    'open': 'first',
    'high': 'max',
    'low':  'min',
    'close':'last',
    'volume':'sum'
})
df_3m.dropna(how='any', inplace=True)
df_3m.to_csv('solusdt_3m.csv')
