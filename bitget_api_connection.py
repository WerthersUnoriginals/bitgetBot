import time
import hmac
import hashlib
import requests
import json

class BitgetAPI:
    BASE_URL = "https://api.bitget.com"

    def __init__(self, api_key=None, secret_key=None, passphrase=None):
        self.api_key = api_key.strip()
        self.secret_key = secret_key.strip()
        self.passphrase = passphrase.strip()
        self.session = requests.Session()

    def _get_timestamp(self):
        """Obtiene el timestamp en segundos"""
        return str(int(time.time()))

    def _sign(self, method, request_path, body=None):
        """Genera la firma para autenticación en Bitget"""
        timestamp = self._get_timestamp()
        body_str = json.dumps(body, separators=(",", ":")) if body else ""

        message = f"{timestamp}{method.upper()}{request_path}{body_str}"
        
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        print(f"\n[DEBUG] Firmando petición:")
        print(f"Timestamp: {timestamp}")
        print(f"Mensaje a firmar: {message}")
        print(f"Firma generada: {signature}")

        return timestamp, signature

    def _get_headers(self, method, request_path, body=None):
        """Genera los headers con la firma"""
        timestamp, signature = self._sign(method, request_path, body)

        headers = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "User-Agent": "BitgetPythonClient/1.0"  # 🔥 Agregamos un User-Agent
        }

        print(f"[DEBUG] Headers enviados: {headers}\n")
        return headers

    def connect(self):
        """Verifica la conexión con la API."""
        if not self.api_key or not self.secret_key or not self.passphrase:
            return {"status": "error", "message": "Faltan credenciales de API."}

        try:
            request_path = "/api/mix/v1/market/contracts"
            headers = self._get_headers("GET", request_path, body=None)
            response = self.session.get(self.BASE_URL + request_path, headers=headers)

            print(f"[DEBUG] Respuesta de Bitget: {response.text}")

            if response.status_code == 200:
                return {"status": "success", "message": "Conexión exitosa con Bitget."}
            else:
                return {"status": "error", "message": f"Error en la conexión: {response.text}"}
        except Exception as e:
            return {"status": "error", "message": f"Excepción: {str(e)}"}

    def get_futures_pairs(self):
        """Obtiene la lista de pares de futuros disponibles."""
        try:
            request_path = "/api/mix/v1/market/contracts"
            headers = self._get_headers("GET", request_path, body=None)
            response = self.session.get(self.BASE_URL + request_path, headers=headers)

            print(f"[DEBUG] Respuesta de Bitget: {response.text}")

            if response.status_code == 200:
                data = response.json()
                return [pair['symbol'] for pair in data['data']]
            else:
                return {"status": "error", "message": f"Error obteniendo pares: {response.text}"}
        except Exception as e:
            return {"status": "error", "message": f"Excepción: {str(e)}"}

    def disconnect(self):
        """Cierra la sesión con la API."""
        self.session.close()
        return {"status": "success", "message": "Sesión cerrada."}


