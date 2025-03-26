import imaplib
import email
from email.header import decode_header
import time
import json
import datetime
import threading
from bitget.v1.mix.market_api import MarketApi
from bitget.v1.mix.account_api import AccountApi
from bitget.v1.mix.order_api import OrderApi

# =============================================================================
# CONFIGURACIÓN DE EMAIL (IMAP)
# =============================================================================
IMAP_SERVER = "imap.gmail.com"
IMAP_USER = "delioelglande@gmail.com"
IMAP_PASS = "otzd ppsi isxj lgmk"

# =============================================================================
# CONFIGURACIÓN Y PARÁMETROS PARA BITGET
# =============================================================================
API_KEY = "bg_aa37923b26ef877b6da55850f7414e09"
SECRET_KEY = "663ace63046a0fa7c5098d2315a69a6aa10fb8f829a92e447dd8e231e8c0fe74"
PASSPHRASE = "Queputamierdaesestosalu2"

SYMBOL = "SPXUSDT_UMCBL"
MARGIN_COIN = "USDT"
USER_FUNDS = 2.0  # 15 USDT por operación
LEVERAGE = "5"    # Apalancamiento 10x

# =============================================================================
# CONEXIÓN A LAS API DE BITGET
# =============================================================================
account_api = AccountApi(API_KEY, SECRET_KEY, PASSPHRASE)
market_api  = MarketApi(API_KEY, SECRET_KEY, PASSPHRASE)
order_api   = OrderApi(API_KEY, SECRET_KEY, PASSPHRASE)

# =============================================================================
# VARIABLES GLOBALES
# =============================================================================
position = None         # "long", "short" o None
open_contracts = 0      # Almacenará la cantidad exacta de contratos abiertos

# =============================================================================
# FUNCIONES DE LOGGING
# =============================================================================
def log_operation(action, details=""):
    """Registra la operación en un archivo de log."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"{now} - {action} - {details}\n"
    try:
        with open("trading_log.txt", "a") as f:
            f.write(log_line)
    except Exception as e:
        print("Error al escribir en el log:", e)

# =============================================================================
# FUNCIONES PARA OBTENER PARÁMETROS DEL CONTRATO
# =============================================================================
def get_contract_parameters(market_api, symbol):
    """
    Consulta la API para obtener el sizeMultiplier y el minTradeNum para el par dado.
    Si no se encuentran, se usan valores por defecto.
    Además, muestra estos valores por consola.
    """
    contracts_info = market_api.contracts({"productType": "umcbl"})
    if isinstance(contracts_info, str):
        contracts_info = json.loads(contracts_info)

    # Valores por defecto
    sizeMultiplier = 0.01
    minTradeNum = 0.1
    if contracts_info.get("code") == "00000" and "data" in contracts_info:
        for c in contracts_info["data"]:
            if c.get("symbol") == symbol:
                sizeMultiplier = float(c.get("sizeMultiplier", "0.01"))
                minTradeNum = float(c.get("minTradeNum", "0.1"))
                break

    print(f"[INFO] Parámetros para {symbol}: sizeMultiplier = {sizeMultiplier}, minTradeNum = {minTradeNum}")
    return sizeMultiplier, minTradeNum

# =============================================================================
# FUNCIONES PARA COLOCAR ÓRDENES EN BITGET
# =============================================================================
def place_order_bitget_v2(order_api, symbol, margin_coin, side, size,
                          order_type="market", price=None,
                          openType="isolated", leverage="5"):
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
        print("Respuesta de placeOrder:", resp)

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
    """
    Cálculo de la cantidad de contratos equivalentes a 'user_funds' USDT,
    teniendo en cuenta el apalancamiento.
    Se muestran los parámetros sizeMultiplier y minTradeNum antes de proceder.
    """
    # Obtiene y muestra los parámetros del contrato
    sizeMultiplier, minTradeNum = get_contract_parameters(market_api, symbol)

    tickers_resp = market_api.tickers({"symbol": symbol, "productType": "umcbl"})
    if isinstance(tickers_resp, str):
        tickers_resp = json.loads(tickers_resp)

    last_price = None
    if tickers_resp.get("code") == "00000" and "data" in tickers_resp:
        ticker_list = tickers_resp["data"]
        if isinstance(ticker_list, list) and len(ticker_list) > 0:
            # Busca en la lista el ticker que corresponda al símbolo seleccionado
            for ticker in ticker_list:
                if ticker.get("symbol") == symbol:
                    last_price = float(ticker.get("last", 1.0))
                    break

    if last_price is None:
        print(f"[WARN] No se encontró ticker para {symbol}. Se usa valor por defecto 1.0 USDT")
        last_price = 1.0

    print(f"[INFO] Último precio para {symbol}: {last_price} USDT")
    
    # Si el precio es inferior a 10 USDT, se ajusta el sizeMultiplier
    if last_price < 10:
        sizeMultiplier *= 1
        print(f"[INFO] Precio inferior a 10 USDT, ajustando sizeMultiplier a {sizeMultiplier}")

    valor_contrato = sizeMultiplier * last_price
    notional = user_funds * float(user_leverage)
    min_order_value = 5.0

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
                             openType="isolated", leverage="10"):
    """
    Coloca una orden en Bitget de forma sencilla usando user_funds en USDT,
    apalancamiento y tipo de orden (market, limit, etc.).
    Antes de calcular la cantidad de contratos, se muestran los parámetros del contrato.
    
    Ahora retorna el valor de contratos utilizados si la orden es exitosa,
    o 0 en caso contrario.
    """
    lev_float = float(leverage)
    contracts = calculate_contracts_for_usdt(market_api, symbol, user_funds, lev_float)
    if contracts <= 0:
        print("[ABORTAR] Contratos = 0. No se envía la orden al exchange.")
        return 0

    contracts = round(contracts, 6)
    success = place_order_bitget_v2(
        order_api, symbol, margin_coin, side,
        contracts, order_type, price,
        openType, leverage
    )
    if success:
        return contracts
    else:
        return 0

# =============================================================================
# FUNCIONES PARA LEER ALERTAS POR EMAIL
# =============================================================================
def check_email_alerts():
    """
    Busca correos no leídos en la bandeja de entrada,
    extrae la alerta (JSON o texto) y llama a process_alert().
    """
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("inbox")
        status, messages = mail.search(None, 'UNSEEN')
        if status != "OK":
            mail.logout()
            return

        email_ids = messages[0].split()
        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])
            subject, encoding = decode_header(msg.get("Subject"))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else "utf-8")

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    print("DEBUG content_type:", part.get_content_type())
                    if part.get_content_type() in ["text/plain", "text/html"]:
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

            alert_text = body.strip().lower()
            print("Alerta recibida por email:", alert_text)

            process_alert(alert_text)
            # Marcar como leído
            mail.store(email_id, '+FLAGS', '\\Seen')

        mail.logout()
    except Exception as e:
        print("Error al revisar el correo:", e)

def process_alert(alert_text):
    """
    Procesa la alerta recibida (JSON o texto plano).
    Si es una apertura/cierre de posición, ejecuta la orden correspondiente.
    
    Para cerrar la posición se usa el valor de contratos almacenado al abrir.
    """
    global position, open_contracts

    try:
        data = json.loads(alert_text)
        action = data.get("action", "").lower()
    except Exception as e:
        print("Error al parsear JSON, se usará texto plano:", e)
        action = alert_text.strip().lower()

    if action == "open_long":
        if position is None:
            contracts = place_order_with_usdt_v2(
                order_api, market_api,
                symbol=SYMBOL,
                margin_coin=MARGIN_COIN,
                side="open_long",
                user_funds=USER_FUNDS,
                order_type="market",
                openType="isolated",
                leverage=LEVERAGE
            )
            if contracts:
                position = "long"
                open_contracts = contracts
                print(f"Posición long abierta con {open_contracts} contratos.")
                log_operation("open_long", f"Operación ejecutada para {SYMBOL} con {USER_FUNDS} USDT, leverage {LEVERAGE}")
    elif action == "close_long":
        if position == "long":
            if open_contracts > 0:
                success = place_order_bitget_v2(
                    order_api, SYMBOL, MARGIN_COIN, "close_long",
                    open_contracts, "market", None,
                    "isolated", LEVERAGE
                )
                if success:
                    print("Posición long cerrada.")
                    log_operation("close_long", f"Cierre de operación en {SYMBOL} con {open_contracts} contratos")
                    position = None
                    open_contracts = 0
            else:
                print("No se tiene almacenado el tamaño de la posición para cerrar.")
        else:
            print("No hay posición long para cerrar.")
    elif action == "open_short":
        if position is None:
            contracts = place_order_with_usdt_v2(
                order_api, market_api,
                symbol=SYMBOL,
                margin_coin=MARGIN_COIN,
                side="open_short",
                user_funds=USER_FUNDS,
                order_type="market",
                openType="isolated",
                leverage=LEVERAGE
            )
            if contracts:
                position = "short"
                open_contracts = contracts
                print(f"Posición short abierta con {open_contracts} contratos.")
                log_operation("open_short", f"Operación ejecutada para {SYMBOL} con {USER_FUNDS} USDT, leverage {LEVERAGE}")
    elif action == "close_short":
        if position == "short":
            if open_contracts > 0:
                success = place_order_bitget_v2(
                    order_api, SYMBOL, MARGIN_COIN, "close_short",
                    open_contracts, "market", None,
                    "isolated", LEVERAGE
                )
                if success:
                    print("Posición short cerrada.")
                    log_operation("close_short", f"Cierre de operación en {SYMBOL} con {open_contracts} contratos")
                    position = None
                    open_contracts = 0
            else:
                print("No se tiene almacenado el tamaño de la posición para cerrar.")
        else:
            print("No hay posición short para cerrar.")
    else:
        print("Acción desconocida:", action)

# =============================================================================
# FUNCIÓN CERRAR POSICIÓN A LAS 20:00
# =============================================================================
def force_close_at_1930():
    """
    Si son las 20:00 (hora local), cierra cualquier posición abierta (long o short).
    """
    global position, open_contracts
    now = datetime.datetime.now()  # Hora local del servidor
    if now.hour == 20 and now.minute == 0:
        if position == "long":
            print("[FORCE CLOSE] Son las 20:00, cerrando posición LONG...")
            success = place_order_bitget_v2(
                order_api, SYMBOL, MARGIN_COIN, "close_long",
                open_contracts, "market", None,
                "isolated", LEVERAGE
            )
            if success:
                position = None
                open_contracts = 0
                print("Posición long forzada cerrada a las 20:00")
                log_operation("force_close_long", f"Cierre de operación forzada en {SYMBOL} a las 20:00")
        elif position == "short":
            print("[FORCE CLOSE] Son las 20:00, cerrando posición SHORT...")
            success = place_order_bitget_v2(
                order_api, SYMBOL, MARGIN_COIN, "close_short",
                open_contracts, "market", None,
                "isolated", LEVERAGE
            )
            if success:
                position = None
                open_contracts = 0
                print("Posición short forzada cerrada a las 20:00.")
                log_operation("force_close_short", f"Cierre de operación forzada en {SYMBOL} a las 20:00")

# =============================================================================
# HILOS DE VERIFICACIÓN
# =============================================================================
def background_checks():
    """
    Se ejecuta de fondo cada minuto.
    - Verifica si se debe forzar el cierre a las 20:00.
    """
    while True:
        force_close_at_1930()
        time.sleep(60)

def email_checks_loop():
    """
    Bucle que revisa el correo cada 2 segundos para buscar alertas nuevas.
    """
    while True:
        check_email_alerts()
        time.sleep(2)

# =============================================================================
# BLOQUE PRINCIPAL
# =============================================================================
if __name__ == "__main__":
    print("Iniciando bot de trading con alertas vía email y Bitget...")
    threading.Thread(target=background_checks, daemon=True).start()
    threading.Thread(target=email_checks_loop, daemon=True).start()

    while True:
        time.sleep(1)
