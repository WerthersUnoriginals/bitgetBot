from bitget_api_connection import BitgetAPI  # Asegúrate de importar correctamente la clase

# Introduce tus credenciales aquí
API_KEY = "bg_aa37923b26ef877b6da55850f7414e09"
SECRET_KEY = "663ace63046a0fa7c5098d2315a69a6aa10fb8f829a92e447dd8e231e8c0fe74"
PASSPHRASE = "Queputamierdaesestosalu2"

# Inicializa la conexión con Bitget
bitget = BitgetAPI(api_key=API_KEY, secret_key=SECRET_KEY, passphrase=PASSPHRASE)

# Prueba de conexión
conexion = bitget.connect()
print("Conexión:", conexion)

# Obtener pares de futuros disponibles
pares = bitget.get_futures_pairs()
if isinstance(pares, list):
    print(f"Pares disponibles ({len(pares)}):", pares)
else:
    print("Error al obtener pares:", pares)

# Cerrar la sesión
desconexion = bitget.disconnect()
print("Desconexión:", desconexion)
print(f"Tamaño de SECRET_KEY: {len(SECRET_KEY)} caracteres")
print(f"SECRET_KEY (oculta parcialmente): {SECRET_KEY[:5]}...{SECRET_KEY[-5:]}")
print(f"ACCESS-PASSPHRASE: '{PASSPHRASE}'")
