# Guia comentada de DataMovil Comercial

Esta guia explica como esta armada la aplicacion para que puedas ir aprendiendo el proyecto sin tocar la base de datos de SisCor.

## Idea general

La app tiene dos formas de trabajar:

1. **Modo local / oficina**
   - La app lee SisCor directamente.
   - La VPN debe estar conectada.
   - Solo se hacen consultas de lectura.
   - No se modifican facturas, clientes, productos, stock ni ninguna tabla.

2. **Modo Streamlit Cloud**
   - La app no entra directo a SisCor.
   - Usa archivos cifrados dentro de `data/`.
   - Los archivos cifrados se abren con la clave guardada en los secretos de Streamlit.

## Archivos principales

### `app.py`

Es el archivo principal de la aplicacion Streamlit.

Hace estas tareas:

- configura la pagina
- define el estilo visual
- muestra la pantalla de login
- arma la barra lateral
- define filtros de fecha y zona
- muestra vista administrador
- muestra vista vendedor
- calcula indicadores visuales
- arma radar de acciones
- genera plan diario recomendado
- genera resumen ejecutivo para compartir

El flujo principal es:

```text
usuario inicia sesion
        |
        v
se cargan fechas, zonas y objetivos
        |
        v
se aplican filtros de periodo y zona
        |
        v
si es vendedor: muestra vista vendedor
si es admin: muestra vista administrador
```

### `src/auth.py`

Maneja usuarios y contrasenas.

Lee usuarios desde:

- secretos de Streamlit Cloud, o
- `.streamlit/users.toml` en la compu local

Cada usuario tiene:

- `username`
- `password`
- `name`
- `role`
- `zones`

Si el usuario tiene rol `admin` o zona `*`, puede ver todo.

### `src/siscor_db.py`

Es el modulo mas delicado e importante.

Su responsabilidad es traer datos comerciales desde SisCor o desde snapshots cifrados.

Contiene funciones como:

- `kpis`: ventas, comprobantes, clientes y ticket promedio
- `ventas_por_zona`: venta por vendedor/zona
- `ventas_por_dia`: evolucion diaria
- `top_clientes`: principales clientes
- `top_productos`: principales productos
- `clientes_a_recuperar`: clientes que bajaron o dejaron de comprar
- `productos_a_impulsar`: productos con caida contra el mes anterior
- `estrategia_cliente`: resumen y estrategia sugerida para un cliente puntual

Punto clave:

```text
Todas las consultas a SisCor son SELECT.
No hay INSERT, UPDATE ni DELETE.
```

### `src/objectives.py`

Maneja los objetivos mensuales.

Lee:

- `data/objetivos.csv` en local, o
- `data/objetivos.csv.enc` en Streamlit Cloud

Calcula:

- cumplimiento contra objetivo
- ritmo esperado del mes
- proyeccion de cierre
- brecha contra objetivo
- venta diaria necesaria
- estado del vendedor/zona

### `scripts/export_snapshot.py`

Exporta datos desde SisCor a archivos locales.

Genera:

- `data/facturas.csv`
- `data/factura_items.csv`

Se usa para crear el snapshot que despues se cifra.

Importante:

```text
Este script tambien es solo lectura.
Solo consulta datos de SisCor.
```

### `scripts/encrypt_snapshot.py`

Cifra los archivos de datos para que puedan subirse a GitHub sin publicar informacion comercial abierta.

Genera:

- `data/facturas.csv.enc`
- `data/factura_items.csv.enc`
- `data/objetivos.csv.enc`
- `data/snapshot.key`

La clave `snapshot.key` no debe publicarse en GitHub.

En Streamlit Cloud, esa clave se guarda como secreto:

```toml
[data]
mode = "snapshot"
snapshot_key = "..."
```

## Vista administrador

El administrador ve:

- KPIs generales
- objetivos y ritmo del mes
- ranking por zona
- radar de acciones
- plan diario recomendado
- resumen ejecutivo para compartir
- clientes a recuperar
- productos foco
- ventas por zona
- evolucion mensual

Tambien puede cambiar a **Vista vendedor** para revisar exactamente lo que vera cada vendedor.

## Vista vendedor

El vendedor ve solo su zona.

La pantalla incluye:

- avance del mes
- objetivo
- cumplimiento
- ritmo
- proyeccion de cierre
- brecha
- clientes a recuperar
- productos foco
- estrategia por cliente

Para telemarketing, la app adapta los textos:

- usa llamada
- usa WhatsApp
- usa contacto
- evita recomendaciones de visita presencial

## Filtros

Los filtros estan en la barra lateral:

- vista: administrador o vendedor
- periodo: mes en curso, ultimos 30 dias o rango
- zonas o vendedor simulado

Los filtros se convierten en:

```python
desde_sql = fecha_desde.isoformat()
hasta_sql = fecha_hasta.isoformat()
zonas_filtro = tuple(...)
```

Luego esos valores se pasan a las funciones de `src/siscor_db.py`.

## Seguridad

Reglas importantes del proyecto:

- no modificar SisCor
- no subir archivos CSV reales a GitHub
- no subir claves ni contrasenas
- usar snapshots cifrados para Streamlit Cloud
- usar conexion directa solo en entorno controlado/VPN

## Como abrir la app local

1. Conectar OpenVPN.
2. Abrir PowerShell en la carpeta del proyecto.
3. Ejecutar:

```powershell
.\.venv\Scripts\streamlit.exe run app.py --server.address 127.0.0.1 --server.port 8501
```

4. Entrar en:

```text
http://127.0.0.1:8501
```

## Como actualizar datos para Streamlit Cloud

Flujo manual actual:

```powershell
.\.venv\Scripts\python.exe scripts\export_snapshot.py
.\.venv\Scripts\python.exe scripts\encrypt_snapshot.py
git add data/*.enc
git commit -m "Refresh encrypted snapshot"
git push origin codex/public-encrypted:principal
```

Luego Streamlit Cloud toma los cambios desde GitHub.

## Lo mas importante para aprender

Si quieres entender el proyecto, estudialo en este orden:

1. `app.py`
2. `src/siscor_db.py`
3. `src/objectives.py`
4. `src/auth.py`
5. `scripts/export_snapshot.py`
6. `scripts/encrypt_snapshot.py`

La idea es que primero entiendas la pantalla, despues las consultas, despues los calculos y al final la publicacion.
