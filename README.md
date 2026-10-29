# Bruncas Comercial

Aplicacion Streamlit para consultar datos comerciales reales desde SisCor.

## Modulos

- `app.py`: Bruncas Comercial.
- `app_analitica.py`: Bruncas Analitica.
- `app_calle.py`: Efectividad semanal de Calle.

Los tres modulos usan consultas de lectura. Los datos, usuarios y credenciales privadas se mantienen fuera de GitHub.

## Objetivo inicial

- Conectar a la base SQL Server de SisCor.
- Mostrar indicadores comerciales basicos.
- Explorar ventas, clientes, productos, pedidos y stock.

## Ejecucion local

### Instalacion asistida en Windows

Después de descargar el repositorio, ejecutar con doble clic:

```text
INSTALAR_EN_NUEVA_COMPUTADORA.bat
```

El instalador crea el entorno de Python, instala las dependencias y crea los accesos directos. No copia ni publica credenciales: al terminar todavía deben configurarse `.streamlit/secrets.toml`, `.streamlit/users.toml` y la clave privada del snapshot.

### Instalacion manual

1. Crear un entorno virtual.
2. Instalar dependencias desde `requirements.txt`.
3. Copiar `.streamlit/secrets.example.toml` a `.streamlit/secrets.toml`.
4. Completar credenciales locales.
5. Ejecutar:

```powershell
streamlit run app.py
```

Para iniciar los otros modulos:

```powershell
streamlit run app_analitica.py --server.port 8511
streamlit run app_calle.py --server.port 8512
```

En Windows se pueden crear accesos directos ejecutando una sola vez:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_bruncas_analitica_shortcut.ps1
powershell -ExecutionPolicy Bypass -File scripts\install_efectividad_calle_shortcut.ps1
```

El itinerario de vendedores publicado está cifrado. El Excel original y la clave `data/snapshot.key` nunca deben subirse a GitHub.
