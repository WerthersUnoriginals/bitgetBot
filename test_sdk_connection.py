import json
from bitget.v1.mix.market_api import MarketApi

# Credenciales de Bitget
api_key = "bg_aa37923b26ef877b6da55850f7414e09"
secret_key = "663ace63046a0fa7c5098d2315a69a6aa10fb8f829a92e447dd8e231e8c0fe74"
passphrase = "Queputamierdaesestosalu2"

# Crear instancia de MarketApi con las credenciales
market_api = MarketApi(api_key, secret_key, passphrase)

# Parámetro necesario
params = {"productType": "umcbl"}

try:
    # Obtener la lista de contratos de futuros
    response = market_api.contracts(params)
    
    # Asegurarnos de que la respuesta es un diccionario
    if isinstance(response, str):  
        response = json.loads(response)

    # Revisamos si la clave 'data' existe y contiene la información de los pares
    if 'data' in response and isinstance(response['data'], list):
        pares_futuros = [par['symbol'] for par in response['data']]

        # Mostrar los pares de forma limpia
        print("\n✅ Lista de Pares de Futuros Disponibles en Bitget:\n")
        for i, par in enumerate(pares_futuros, start=1):
            print(f"{i}. {par}")

    else:
        print("❌ Error: No se encontraron datos en la respuesta de Bitget.")

except Exception as e:
    print(f"❌ Error al conectar: {e}")

#passphrase: Queputamierdaesestosalu2

#apikey:bg_aa37923b26ef877b6da55850f7414e09

#secret key:663ace63046a0fa7c5098d2315a69a6aa10fb8f829a92e447dd8e231e8c0fe74