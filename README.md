# Bruncas Comercial

Aplicacion Streamlit para consultar datos comerciales reales desde SisCor.

## Objetivo inicial

- Conectar a la base SQL Server de SisCor.
- Mostrar indicadores comerciales basicos.
- Explorar ventas, clientes, productos, pedidos y stock.

## Ejecucion local

1. Crear un entorno virtual.
2. Instalar dependencias desde `requirements.txt`.
3. Copiar `.streamlit/secrets.example.toml` a `.streamlit/secrets.toml`.
4. Completar credenciales locales.
5. Ejecutar:

```powershell
streamlit run app.py
```
