import os
import time

while True:
    print("Actualizando datos...")

    os.system("python src/api_extraction.py")

    print("Datos actualizados correctamente.")
    print("Esperando 2 minutos...\n")

    time.sleep(120)