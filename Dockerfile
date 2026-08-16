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

# Usuario no-root (buena práctica de seguridad: si algo dentro del
# contenedor se ve comprometido, no corre como root). UID/GID 1000 porque
# es el primer usuario "normal" en la gran mayoría de distros Linux —
# facilita que, en un servidor real, el propietario de ./data y ./logs en
# el host coincida sin fricción.
#
# NOTA para servidor Linux real: antes del primer `docker compose up`,
# asegúrate de que el host pueda escribir esos directorios desde este UID:
#   chown -R 1000:1000 data logs   (o `chmod -R a+rwX data logs` si prefieres
#   no atarte a un UID específico)
# En Windows con Docker Desktop esto normalmente no hace falta — la capa de
# compatibilidad de Docker Desktop maneja el mapeo de permisos sola.
RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g appuser -m -s /bin/bash appuser \
    && mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

USER appuser

# 8501 = Streamlit (dashboard). El servicio `collector` no expone puerto,
# pero no hace daño declararlo aquí ya que ambos comparten esta imagen.
EXPOSE 8501

# Comando por defecto (docker-compose.yml lo sobreescribe explícitamente
# para cada servicio: `collector` corre route_extraction, `dashboard`
# corre streamlit run streamlit_app/app.py). Este CMD es el fallback si
# alguien hace `docker run` directo sobre la imagen sin especificar comando.
CMD ["streamlit", "run", "streamlit_app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
