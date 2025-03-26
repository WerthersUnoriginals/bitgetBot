# grafico_prev.py
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pandas as pd
import datetime

# Aquí, la idea es que "get_current_candles()" sea una función
# que se conecte a tu bot o a un fichero CSV / JSON
def get_current_candles():
    """
    Debe devolver un DataFrame con las columnas:
      time, open, high, low, close, volume, hma100, vwma10, ema199
      + cualquier otra columna relevante (posiciones abiertas, etc.)
    """
    # EJEMPLO: leer un csv en disco que tu bot escribe
    try:
        df = pd.read_csv("candles.csv")
        return df
    except:
        return pd.DataFrame()

fig, ax = plt.subplots()

# Aquí guardamos referencias a las líneas de velas e indicadores
candlestick_lines = []
hma_line, = ax.plot([], [], label="HMA(100)", color='blue')
vwma_line, = ax.plot([], [], label="VWMA(10)", color='green')
ema_line, = ax.plot([], [], label="EMA(100)", color='magenta')
pos_marker = None  # referencia a un scatter o line para posición

def animate(frame):
    """
    Esta función se llama cada X ms (cuando FuncAnimation actualiza la gráfica).
    """
    df = get_current_candles()
    if df.empty:
        return

    # Convertir 'time' a numeric si no lo está
    # Ej: df['time'] = pd.to_datetime(df['time'])
    # o df['time'] = range(len(df)) si no tienes fecha real.

    ax.clear()  # Limpia el subplot para redibujar

    # DIBUJAR LAS VELAS (tipo "candlestick" simplificado)
    # O bien usar mplfinance o un candlestick manual:
    for idx, row in df.iterrows():
        # x = idx (posición en el eje X)
        # dibujar lineas verticales (high-low) y body (open-close)
        color = 'green' if row['close'] >= row['open'] else 'red'
        ax.plot([idx, idx], [row['low'], row['high']], color='black')
        ax.plot([idx - 0.2, idx + 0.2],
                [row['open'], row['open']], color=color, linewidth=4)
        ax.plot([idx - 0.2, idx + 0.2],
                [row['close'], row['close']], color=color, linewidth=4)

    # DIBUJAR INDICADORES
    ax.plot(df.index, df['hma100'], label="HMA(100)", color='blue')
    ax.plot(df.index, df['vwma10'], label="VWMA(10)", color='green')
    ax.plot(df.index, df['ema100'], label="EMA(100)", color='magenta')

    # MARCAR POSICIÓN ABIERTA (si existe)
    # Suponiendo que tu DF tenga columnas 'pos_price' y 'pos_side', y la pos_side sea "long" o "short"
    if 'pos_price' in df.columns and df['pos_price'].iloc[-1] != 0:
        # Toma la última vela y dibuja un scatter
        pos_price = df['pos_price'].iloc[-1]
        pos_side  = df['pos_side'].iloc[-1]
        # En X usas len(df)-1 (la última vela)
        ax.scatter([len(df)-1], [pos_price],
                   color='blue' if pos_side=='long' else 'red',
                   marker='^' if pos_side=='long' else 'v',
                   s=100, zorder=5)

    ax.set_title("Gráfico en Tiempo Real")
    ax.legend()

    # Ajustar límites para que se vea bien
    ax.set_xlim([0, len(df)+1])
    # min y max de high y low
    y_min = df['low'].min() * 0.99
    y_max = df['high'].max() * 1.01
    ax.set_ylim([y_min, y_max])

ani = animation.FuncAnimation(fig, animate, interval=2000)  
# interval=2000 -> cada 2 segundos llama a animate

plt.show()
