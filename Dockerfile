# Dockerfile — BD_BI_TFM2
#
# Imagen compartida por los servicios `collector` y `dashboard` de
# docker-compose.yml (cada uno la usa con un `command:` distinto). Basado
# en el Dockerfile original de urban-mobility-analytics1; sin cambios
# estructurales, sólo se apoya en el requirements.txt fusionado.

FROM python:3.11-slim

WORKDIR /app

# Copiar requirements primero para aprovechar la cache de capas de Docker
# (si sólo cambia el código, no hace falta reinstalar dependencias).
COPY requirements.txt .

# psycopg2-binary, scikit-learn, scipy y statsmodels traen wheels
# precompilados para este tipo de imagen, así que no hacen falta paquetes
# de compilación (gcc/build-essential) en la mayoría de los casos.
#
# PIP_ROOT_USER_ACTION=ignore: silencia el warning "Running pip as the
# root user..." — es la forma oficial que sugiere pip para contenedores
# Docker (de un solo propósito, sin gestor de paquetes del sistema en
# conflicto), no un problema real a corregir de otra forma.
ENV PIP_ROOT_USER_ACTION=ignore
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# NOTA: se probó correr como usuario no-root (appuser, UID 1000) como parte
# del endurecimiento para servidor real (ver PRODUCTION.md), pero causó
# PermissionError en despliegues que ya tenían archivos en ./logs creados
# por una versión anterior del contenedor corriendo como root — ver
# INTEGRATION_NOTES.md, bug 3.15. Se revirtió a root por simplicidad; el
# resto del endurecimiento (healthchecks, límites de recursos,
# contraseñas separadas, puertos solo en 127.0.0.1, rotación de logs,
# versiones fijadas) se mantiene sin cambios.
#
# Si más adelante quieres retomar el usuario no-root (recomendable para un
# servidor real con acceso multiusuario), la forma robusta de hacerlo sin
# repetir el mismo problema es con un entrypoint que corrija el ownership
# de los volúmenes montados ANTES de bajar privilegios, en vez de solo
# `USER appuser` al final del build (que no puede arreglar archivos que ya
# existen en un bind mount de una ejecución anterior).

# 8501 = Streamlit (dashboard). El servicio `collector` no expone puerto,
# pero no hace daño declararlo aquí ya que ambos comparten esta imagen.
EXPOSE 8501

# Comando por defecto (docker-compose.yml lo sobreescribe explícitamente
# para cada servicio: `collector` corre route_extraction, `dashboard`
# corre streamlit run streamlit_app/app.py). Este CMD es el fallback si
# alguien hace `docker run` directo sobre la imagen sin especificar comando.
CMD ["streamlit", "run", "streamlit_app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
