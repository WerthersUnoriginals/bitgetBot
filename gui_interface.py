# gui_interface.py

import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import time
import pandas as pd

# Importamos la lógica del otro archivo
import main_code

class TradingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Trading Bot - Heikin Ashi + EMA(25)")

        # Marco principal
        main_frame = tk.Frame(root)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Creamos la figura para matplotlib
        self.fig = plt.Figure(figsize=(7,4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, main_frame)
        self.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Lado derecho: info de posición y logs
        side_frame = tk.Frame(main_frame)
        side_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)

        self.position_label = tk.Label(side_frame, text="Posición: None", font=("Arial", 12))
        self.position_label.pack(pady=10)

        # Tabla de trades
        self.trades_tree = ttk.Treeview(side_frame, columns=("timeOpen","side","size","priceOpen","timeClose","priceClose","PnL"), show="headings", height=12)
        for col in ("timeOpen","side","size","priceOpen","timeClose","priceClose","PnL"):
            self.trades_tree.heading(col, text=col)
            self.trades_tree.column(col, width=80)
        self.trades_tree.pack(padx=5, pady=5)

        self.update_chart()

    def update_chart(self):
        """
        Se llama cada X ms. Descarga velas, dibuja, aplica estrategia, abre/cierra posición.
        """
        # 1) Descarga Heikin Ashi + EMA
        ha_df = main_code.fetch_heikin_ashi_ema("BTCUSDT_UMCBL")  # Ejemplo
        if len(ha_df) > 2:
            # 2) Dibuja
            self.draw_chart(ha_df)

            # 3) Aplica estrategia
            signal = main_code.apply_strategy(ha_df)
            if signal:
                print("Signal =>", signal)
                # Ejemplo: si open_long => place_order("open_long", size=2.0)
                if signal.startswith("open_"):
                    ok = main_code.place_order(signal, size=2.0)
                    if ok:
                        main_code.position = "long" if signal=="open_long" else "short"
                        # Registra la operación
                        info = {
                            "timeOpen": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "side": main_code.position,
                            "size": 2.0,
                            "priceOpen": ha_df.iloc[-1]["HA_close"],
                            "timeClose": "",
                            "priceClose": "",
                            "PnL": ""
                        }
                        main_code.record_trade(info)
                        self.refresh_trades_log()

                elif signal.startswith("close_"):
                    # Buscamos la operación en main_code.trades_log y la cerramos.
                    # En un ejemplo real, sabrías cuál abrir/cerrar.
                    # Aquí supongo la última trade sin "timeClose".
                    if main_code.position:
                        main_code.position = None
                        # Actualizamos el trade log
                        if len(main_code.trades_log)>0:
                            last_trade = main_code.trades_log[-1]
                            if not last_trade["timeClose"]:
                                last_trade["timeClose"] = time.strftime("%Y-%m-%d %H:%M:%S")
                                last_trade["priceClose"] = ha_df.iloc[-1]["HA_close"]
                                # last_trade["PnL"] = calculoPnL...
                        self.refresh_trades_log()

            # Actualizar label de posición
            self.position_label.config(text=f"Posición: {main_code.position}")

        # Repetir
        self.root.after(5000, self.update_chart)

    def draw_chart(self, df):
        self.ax.clear()
        x_vals = range(len(df))
        for i in x_vals:
            color = "green" if df.loc[i,"HA_close"]>=df.loc[i,"HA_open"] else "red"
            self.ax.plot([i,i],[df.loc[i,"HA_low"],df.loc[i,"HA_high"]], color=color)
            self.ax.plot([i-0.2,i+0.2],[df.loc[i,"HA_open"],df.loc[i,"HA_open"]], color=color)
            self.ax.plot([i-0.2,i+0.2],[df.loc[i,"HA_close"],df.loc[i,"HA_close"]], color=color)
            self.ax.plot([i,i],[df.loc[i,"HA_open"],df.loc[i,"HA_close"]], color=color, linewidth=4)
        self.ax.plot(x_vals, df["HA_ema25"], color="blue", label="EMA(25)")
        self.ax.set_title("Heikin Ashi + EMA(25)")
        self.canvas.draw()

    def refresh_trades_log(self):
        """
        Vuelve a llenar el Treeview con main_code.trades_log.
        """
        for row in self.trades_tree.get_children():
            self.trades_tree.delete(row)
        for t in main_code.trades_log:
            self.trades_tree.insert("", tk.END, values=(
                t["timeOpen"],
                t["side"],
                t["size"],
                t["priceOpen"],
                t["timeClose"],
                t["priceClose"],
                t["PnL"]
            ))

def main():
    root = tk.Tk()
    gui = TradingGUI(root)
    root.mainloop()

if __name__=="__main__":
    main()
