# Snapshot data

Esta carpeta puede contener archivos generados desde SisCor para publicar DataMovil en Streamlit Cloud sin conectar la nube directamente a SQL Server.

Por seguridad, los archivos `.csv` y `.parquet` estan ignorados por Git por defecto.

Archivos locales esperados para generar snapshots:

- `facturas.csv`
- `factura_items.csv`

Archivos publicados en GitHub:

- `facturas.csv.enc`
- `factura_items.csv.enc`

Los archivos `.enc` estan cifrados. La clave debe guardarse en Streamlit Secrets como
`data.snapshot_key` y no debe subirse al repositorio.

Objetivos comerciales:

- `objetivos.csv` se usa localmente para cargar metas mensuales por zona.
- Debe tener columnas `mes`, `zona`, `objetivo`.
- `objetivos.example.csv` muestra el formato esperado.
