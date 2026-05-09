# DataMovil en Streamlit Cloud

## Objetivo

Publicar DataMovil en Streamlit Cloud usando GitHub, sin depender de la PC de oficina prendida.

## Separar dos problemas

Streamlit Cloud resuelve:

- hosting de la app;
- link estable;
- disponibilidad sin depender de esta PC;
- despliegue desde GitHub.

Streamlit Cloud no resuelve automaticamente:

- acceso seguro a SQL Server SisCor si la base solo vive dentro de la VPN/red privada.

## Alternativas de datos

### Alternativa A - Conexion directa a SQL Server

La app en Streamlit Cloud conecta directo a SQL Server.

Requisitos:

- SQL Server accesible desde internet o desde una IP permitida.
- Usuario SQL solo lectura.
- Firewall configurado de forma segura.
- Credenciales en Streamlit Secrets, nunca en GitHub.

Ventajas:

- Datos casi en tiempo real.
- Menos piezas intermedias.

Riesgos:

- Puede exponer SQL Server si se configura mal.
- Hay que hacerlo con mucho cuidado.

Estado:

- No recomendado sin validar seguridad primero.

### Alternativa B - Datos sincronizados

Una tarea interna lee SisCor en modo solo lectura y sube solo datos comerciales necesarios a un destino que Streamlit Cloud pueda leer.

Destinos posibles:

- Google Sheets.
- CSV en Google Drive/OneDrive.
- Base gratuita en la nube, por ejemplo Supabase/Postgres.
- Archivo parquet/CSV en un repositorio privado o storage.

Ventajas:

- No se expone SQL Server.
- Streamlit Cloud funciona muy bien.
- Puede ser gratis o bajo costo.

Riesgos:

- No es tiempo real absoluto; depende de frecuencia de sincronizacion.
- Hay que crear una tarea de actualizacion.

Frecuencias posibles:

- Cada 5 minutos.
- Cada 15 minutos.
- Cada hora.
- Manual.

Estado:

- Opcion mas segura para empezar si no podemos exponer SQL.
- Implementado en el proyecto como modo `snapshot`.

## Modo snapshot implementado

El proyecto ya puede funcionar sin SQL directo usando:

```text
data/facturas.csv
data/factura_items.csv
```

Para generar esos archivos desde una PC que tenga acceso a SisCor:

```powershell
.\.venv\Scripts\python.exe scripts\export_snapshot.py
```

Ese script hace solamente consultas `SELECT` y exporta columnas comerciales necesarias.

Para ejecutar la app local en modo snapshot:

```powershell
$env:DATAMOVIL_DATA_MODE="snapshot"
.\.venv\Scripts\streamlit.exe run app.py
```

En Streamlit Cloud, agregar en Secrets:

```toml
[data]
mode = "snapshot"
```

Importante:

- `data/*.csv` esta ignorado por Git por seguridad.
- Si se decide subir snapshots a GitHub, el repositorio debe ser privado.
- La frecuencia de actualizacion depende de cuan seguido se regenere/suba el snapshot.

### Alternativa C - API intermedia

Crear una pequena API dentro de la red/VPN que exponga solo endpoints comerciales.

Ventajas:

- Control fino de datos.
- No se expone SQL Server completo.

Riesgos:

- Requiere alojar y mantener otra pieza.
- Si depende de una PC apagable, volvemos al mismo problema.

Estado:

- Buena opcion profesional si tenemos un host interno 24/7.

### Alternativa D - Cloudflare Tunnel persistente

Una maquina interna crea un tunel saliente hacia Cloudflare y Streamlit Cloud o vendedores acceden por un link.

Ventajas:

- No abre puertos del router.
- Funciono como prueba temporal.

Riesgos:

- Si la maquina interna se apaga, se cae.
- Para produccion requiere configuracion persistente.

Estado:

- Sirve para pruebas o si existe una maquina interna siempre encendida.

## Preparacion para GitHub

No subir:

- `.streamlit/secrets.toml`
- `.streamlit/users.toml`
- `.venv/`
- logs de Cloudflare
- archivos `.ovpn`
- claves o certificados

Subir:

- `app.py`
- `src/`
- `requirements.txt`
- `.streamlit/secrets.example.toml`
- `.streamlit/users.example.toml`
- documentacion

## Secrets necesarios en Streamlit Cloud

Ejemplo:

```toml
[siscor]
server = "SERVIDOR"
database = "d_bruncas"
username = "datamovil_lectura"
password = "CLAVE"
driver = "ODBC Driver 17 for SQL Server"

[users.admin]
password = "CAMBIAR"
name = "Administrador"
role = "admin"
zones = ["*"]

[users.david]
password = "CAMBIAR"
name = "David"
role = "seller"
zones = ["DAVID"]
```

## Proxima decision tecnica

Antes de publicar, decidir:

1. Conexion directa a SQL, si se puede hacer segura.
2. Datos sincronizados, si priorizamos seguridad y costo bajo.

Recomendacion senior:

Empezar con datos sincronizados cada 5 o 15 minutos si no hay una forma segura de exponer SQL Server. Para vendedores, eso suele ser suficiente para medir desempeno durante el dia sin poner SisCor en riesgo.
