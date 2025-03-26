import time
import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import messagebox, Toplevel, ttk
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import requests
import hmac
import hashlib
import json
import threading

# ========================================
# Configuración inicial y variables globales
# ========================================

API_KEY = ""
API_SECRET = ""
PASSPHRASE = ""
BASE_URL = "https://api.bitget.com"

# Variables de configuración de trading
SYMBOL = "BTCUSDC"        # Se reasignará al guardar la configuración (GUI)
TIMEFRAME = "5m"          # Lo usaremos como string, pero se convertirá a segundos para la API
USDC_AMOUNT = 50.0
LEVERAGE = 10

# Diccionario para convertir string (ej. "5m") a segundos que usa Bitget
timeframe_map = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400
}

LOG_FILE = "trading_log.xlsx"

# Control de conexión y operación
connected = False
running = False
position = None  # Variable global para manejar estado de la posición (None, 'long', 'short')

# ========================================
# Función para generar la firma
# ========================================
def generate_signature(timestamp, method, request_path, body):
    """
    Genera la firma HMAC SHA256 requerida por la API de Bitget.
    """
    message = timestamp + method + request_path + (body if body else "")
    signature = hmac.new(API_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return signature

# ========================================
# Función para obtener pares de trading con USDC
# ========================================
def get_usdc_pairs():
    url = f"{BASE_URL}/api/mix/v1/market/contracts?productType=cmcbl"
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        if "data" in data and isinstance(data["data"], list):
            return [s["symbol"] for s in data["data"] if s.get("quoteCoin") == "USDC"]
        else:
            return []
    except requests.exceptions.RequestException:
        return []

# ========================================
# Función para conectar al exchange
# (Asignamos aquí las credenciales globales
#  y actualizamos estados de la GUI)
# ========================================
def connect_exchange():
    global connected, API_KEY, API_SECRET, PASSPHRASE

    # Leemos y asignamos los valores de los Entry de la GUI
    API_KEY = api_key_entry.get().strip()
    API_SECRET = api_secret_entry.get().strip()
    PASSPHRASE = passphrase_entry.get().strip()

    # Simulamos la conexión, en tu uso real,
    # verifica credenciales con la API
    connected = True
    connection_status.config(text="Conectado", fg="green")
    messagebox.showinfo("Conexión", "Conectado al exchange correctamente")
    update_symbols_list()

# ========================================
# Función para desconectar del exchange
# ========================================
def disconnect_exchange():
    global connected
    connected = False
    connection_status.config(text="Desconectado", fg="red")
    messagebox.showinfo("Conexión", "Desconectado del exchange correctamente")

# ========================================
# Función para actualizar la lista de símbolos
# ========================================
def update_symbols_list():
    symbols = get_usdc_pairs()
    symbol_dropdown["values"] = symbols
    if symbols:
        symbol_dropdown.current(0)
    else:
        messagebox.showwarning("Advertencia", "No se encontraron símbolos para negociar en USDC.")

# ========================================
# Función para obtener datos de mercado y calcular EMA 25
# ========================================
def get_market_data():
    """
    Llama a la API de Bitget para obtener velas,
    agrega una columna con EMA25
    y retorna la vela más reciente (última fila).
    """
    global SYMBOL, TIMEFRAME

    # Convertimos el timeframe que el usuario eligió a segundos
    granularity = timeframe_map.get(TIMEFRAME, 300)  # 300 por defecto (5m)
    
    url = f"{BASE_URL}/api/mix/v1/market/candles?symbol={SYMBOL}&granularity={granularity}"
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            # data["data"] normalmente se recibe como lista de listas
            # Columnas esperadas: [timestamp, open, high, low, close, volume]
            df = pd.DataFrame(data["data"], columns=["timestamp", "open", "high", "low", "close", "volume"])

            # Convertimos a float las columnas necesarias
            df["close"] = df["close"].astype(float)

            # Invertimos el DataFrame para que la fila 0 sea la más antigua y -1 la más reciente
            df = df.iloc[::-1].reset_index(drop=True)

            # Calculamos la EMA 25
            df["ema25"] = df["close"].ewm(span=25, adjust=False).mean()

            # Devolvemos la última fila, que ahora sí es la más reciente
            return df.iloc[-1]
        
            print("Respuesta de la API de velas:", data)

        else:
            return None
    except requests.exceptions.RequestException:
        return None

# ========================================
# Función para enviar una orden al exchange
# (Abrir o cerrar posición)
# ========================================
def place_order(side):
    """
    side: "buy" para abrir LONG o cerrar SHORT,
          "sell" para abrir SHORT o cerrar LONG.
    """
    timestamp = str(int(time.time() * 1000))
    endpoint = "/api/mix/v1/order/placeOrder"
    url = f"{BASE_URL}{endpoint}"

    body = {
        "symbol": SYMBOL,
        "side": side,
        "orderType": "market",  # Orden de mercado
        "size": str(USDC_AMOUNT),  # Cantidad en USDC (según la API, verifica que sea correcto)
        "leverage": str(LEVERAGE),
        "marginCoin": "USDC"
        # Para cerrar posición a veces es necesario "reduceOnly": True. Depende de la API y tipo de cuenta.
    }

    body_json = json.dumps(body)

    signature = generate_signature(timestamp, "POST", endpoint, body_json)

    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": signature,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, data=body_json)
        result = response.json()
        if result.get("code") == "00000":
            print(f"Orden {side.upper()} ejecutada correctamente.")
        else:
            print(f"Error al ejecutar la orden: {result}")
    except requests.exceptions.RequestException as e:
        print(f"Error en la solicitud de orden: {e}")

# ========================================
# Estrategia de trading basada en EMA 25
# ========================================
def trading_strategy():
    global position, running, connected

    if not running or not connected:
        return
    
    market_data = get_market_data()
    if market_data is None:
        print("No se pudo obtener datos de mercado.")
        return
    
    price = market_data["close"]
    ema25 = market_data["ema25"]

    # Lógica simple: si no hay posición, abrimos LONG si price > EMA, SHORT si price < EMA
    # Si hay posición LONG y price < EMA, cerramos (vendemos).
    # Si hay posición SHORT y price > EMA, cerramos (compramos).
    if position is None:
        if price > ema25:
            position = "long"
            print("Abriendo posición LONG")
            place_order("buy")
        elif price < ema25:
            position = "short"
            print("Abriendo posición SHORT")
            place_order("sell")
    elif position == "long" and price < ema25:
        print("Cerrando posición LONG")
        place_order("sell")  # Cierra LONG vendiendo
        position = None
    elif position == "short" and price > ema25:
        print("Cerrando posición SHORT")
        place_order("buy")   # Cierra SHORT comprando
        position = None

    # Esto solo para visualizar la firma en consola (ejemplo de prueba)
    test_signature = generate_signature(str(int(time.time() * 1000)), "POST", "/api/mix/v1/order/placeOrder", "{}")
    print(f"Firma generada (test): {test_signature}")
    print(f"Precio actual: {price}, EMA 25: {ema25}, Posición: {position}")

# ========================================
# Función para iniciar operaciones en un hilo separado
# ========================================
def start_trading():
    global running, connected

    if connected:
        running = True
        trading_status.config(text="Operando", fg="green")
        messagebox.showinfo("Trading", "El bot ha iniciado operaciones.")
        
        def trading_loop():
            while running:
                trading_strategy()
                time.sleep(60)  # Ejecutar cada 1 minuto
        
        # Iniciamos el loop de trading en un hilo separado
        trading_thread = threading.Thread(target=trading_loop, daemon=True)
        trading_thread.start()
    else:
        messagebox.showwarning("Error", "Debe conectarse al exchange antes de operar.")

# ========================================
# Función para detener operaciones
# ========================================
def stop_trading():
    global running
    running = False
    trading_status.config(text="Detenido", fg="red")
    messagebox.showinfo("Trading", "El bot ha detenido las operaciones.")

# ========================================
# Función para guardar configuración
# (Se asignan los valores del GUI a las globales)
# ========================================
def save_settings():
    global SYMBOL, TIMEFRAME, USDC_AMOUNT, LEVERAGE

    SYMBOL = symbol_dropdown.get().strip()
    TIMEFRAME = timeframe_dropdown.get().strip()
    
    try:
        USDC_AMOUNT = float(amount_entry.get())
    except ValueError:
        USDC_AMOUNT = 50.0  # Valor por defecto o maneja el error como prefieras

    try:
        LEVERAGE = int(leverage_dropdown.get())
    except ValueError:
        LEVERAGE = 10       # Valor por defecto o maneja el error como prefieras

    messagebox.showinfo("Configuración", "Los ajustes han sido guardados correctamente.")

# ========================================
# Interfaz gráfica (GUI)
# ========================================
def start_gui():
    global api_key_entry, api_secret_entry, passphrase_entry
    global amount_entry, symbol_dropdown, timeframe_dropdown, leverage_dropdown
    global connection_status, trading_status

    root = tk.Tk()
    root.title("Configuración del Trading Bot - Bitget")
    root.configure(bg="#2C3E50")
    root.geometry("500x750")

    # Etiquetas
    labels = [
        "API Key:",
        "API Secret:",
        "Passphrase:",
        "Símbolo:",
        "Timeframe:",
        "Cantidad USDC:",
        "Apalancamiento:"
    ]

    # Entradas de texto y Combobox
    api_key_entry = tk.Entry(root, width=30)
    api_secret_entry = tk.Entry(root, width=30, show="*")
    passphrase_entry = tk.Entry(root, width=30, show="*")
    amount_entry = tk.Entry(root, width=30)

    symbol_var = tk.StringVar()
    symbol_dropdown = ttk.Combobox(root, textvariable=symbol_var, values=[], width=28)

    timeframe_var = tk.StringVar()
    timeframe_dropdown = ttk.Combobox(root, textvariable=timeframe_var,
                                      values=["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"],
                                      width=28)
    timeframe_dropdown.current(2)  # Por defecto "5m"

    leverage_var = tk.StringVar()
    leverage_dropdown = ttk.Combobox(root, textvariable=leverage_var,
                                     values=[str(i) for i in range(1, 126)],
                                     width=28)
    leverage_dropdown.current(9)  # Por defecto 10

    entries = [api_key_entry, api_secret_entry, passphrase_entry,
               symbol_dropdown, timeframe_dropdown, amount_entry, leverage_dropdown]

    # Renderizamos la interfaz
    for i, label in enumerate(labels):
        tk.Label(root, text=label, fg="white", bg="#2C3E50",
                 font=("Arial", 10, "bold")).grid(row=i, column=0, padx=10, pady=5, sticky="w")
        entries[i].grid(row=i, column=1, padx=10, pady=5)

    # Estado de conexión
    connection_status = tk.Label(root, text="Desconectado", fg="red",
                                 bg="#2C3E50", font=("Arial", 10, "bold"))
    connection_status.grid(row=len(labels), columnspan=2, pady=5)

    # Botón Conectar
    connect_button = tk.Button(root, text="Conectar", command=connect_exchange,
                               bg="#27AE60", fg="white", font=("Arial", 10, "bold"))
    connect_button.grid(row=len(labels)+1, columnspan=2, pady=5)

    # Botón Desconectar
    disconnect_button = tk.Button(root, text="Desconectar", command=disconnect_exchange,
                                  bg="#E74C3C", fg="white", font=("Arial", 10, "bold"))
    disconnect_button.grid(row=len(labels)+2, columnspan=2, pady=5)

    # Estado de trading
    trading_status = tk.Label(root, text="Detenido", fg="red",
                              bg="#2C3E50", font=("Arial", 10, "bold"))
    trading_status.grid(row=len(labels)+3, columnspan=2, pady=5)

    # Botón Iniciar Operaciones
    start_button = tk.Button(root, text="Iniciar Operaciones", command=start_trading,
                             bg="#F1C40F", fg="black", font=("Arial", 10, "bold"))
    start_button.grid(row=len(labels)+4, columnspan=2, pady=5)

    # Botón Detener Operaciones
    stop_button = tk.Button(root, text="Detener Operaciones", command=stop_trading,
                            bg="#E67E22", fg="white", font=("Arial", 10, "bold"))
    stop_button.grid(row=len(labels)+5, columnspan=2, pady=5)

    # Botón Guardar Configuración
    save_button = tk.Button(root, text="Guardar Configuración", command=save_settings,
                            bg="#3498DB", fg="white", font=("Arial", 10, "bold"))
    save_button.grid(row=len(labels)+6, columnspan=2, pady=5)

    root.mainloop()

# ========================================
# Punto de entrada principal
# ========================================
if __name__ == "__main__":
    start_gui()
