# DataMovil Comercial - Despliegue 24/7

## Decision recomendada

Para que los vendedores entren desde cualquier lugar y la app no dependa de la PC de oficina, DataMovil debe correr en un servidor encendido 24/7.

La opcion recomendada es:

1. Servidor/VPS propio.
2. OpenVPN instalado en ese servidor.
3. DataMovil corriendo en ese servidor.
4. Link publico fijo con HTTPS.
5. Login de DataMovil por usuario/zona.
6. Base SisCor siempre en modo solo lectura.

Flujo:

```text
Vendedor movil
  -> link publico HTTPS
  -> servidor DataMovil 24/7
  -> OpenVPN
  -> SQL Server SisCor 10.8.0.1,50672
```

## Por que no usar la PC actual

La PC actual sirve para desarrollo y pruebas, pero no para produccion:

- Si se apaga, la app deja de existir.
- Los links temporales cambian.
- Windows puede bloquear accesos por firewall.
- No es un servidor 24/7.

## Por que no alcanza con OpenVPN en los celulares

Los celulares pueden llegar al servidor VPN `10.8.0.1`, pero no necesariamente pueden llegar a otros clientes de la VPN, como esta PC `10.8.0.7`.

Por eso la app del tecnico en `10.8.0.1:8443` funciona y DataMovil en `10.8.0.7:8501` no funciono desde el movil.

## Requisitos del servidor

### Opcion simple

Un VPS Windows chico:

- Windows Server.
- 2 CPU.
- 4 GB RAM.
- 40 GB disco.
- Python 3.12.
- Microsoft ODBC Driver 17 o 18 for SQL Server.
- OpenVPN Connect o OpenVPN Community.
- Cloudflare Tunnel o proxy HTTPS.

### Opcion economica

Un VPS Linux tambien sirve, pero requiere instalar el driver ODBC de Microsoft y configurar OpenVPN por consola. Es mas tecnico.

## Datos que necesitamos

- Acceso al VPS: usuario/clave o escritorio remoto.
- Un perfil OpenVPN para el servidor, idealmente exclusivo para DataMovil.
- Confirmar si el perfil OpenVPN permite llegar a:

```text
10.8.0.1:50672
```

- Definir dominio o subdominio, por ejemplo:

```text
datamovil.bruncas.com
```

- Lista definitiva de usuarios:

```text
usuario | nombre | zona | rol
```

## Importante sobre OpenVPN

No conviene usar el mismo `.ovpn` en muchos equipos al mismo tiempo si el servidor OpenVPN no permite multiples conexiones con el mismo certificado.

Lo correcto es pedir o crear un perfil exclusivo para:

```text
datamovil_server.ovpn
```

## Seguridad minima

- No publicar SQL Server en internet.
- No usar `sa` en produccion si se puede evitar.
- Crear un usuario SQL solo lectura para DataMovil.
- Usar HTTPS para el link externo.
- Cambiar las contrasenas simples de prueba.
- Mantener el archivo `.streamlit/users.toml` fuera de Git.
- Restringir cada vendedor a su zona.

## Pasos de despliegue en Windows Server

1. Copiar el proyecto al servidor.
2. Instalar Python 3.12.
3. Crear entorno virtual:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

4. Instalar Microsoft ODBC Driver for SQL Server.
5. Instalar OpenVPN.
6. Importar/conectar el perfil OpenVPN del servidor.
7. Probar conexion a SisCor:

```powershell
sqlcmd -S 10.8.0.1,50672 -d d_bruncas -U USUARIO_SOLO_LECTURA -P CLAVE -Q "SELECT DB_NAME();"
```

8. Completar `.streamlit/secrets.toml` con credenciales del SQL.
9. Completar `.streamlit/users.toml` con usuarios reales.
10. Iniciar DataMovil:

```powershell
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
```

11. Publicar con Cloudflare Tunnel o proxy HTTPS.
12. Probar desde celular con datos moviles.

## Estado actual

- App funcional en desarrollo.
- Login por usuario/zona implementado.
- Consultas comerciales en solo lectura.
- PROVEEDORES excluido del tablero.
- FC/ND suman, NC resta, PC queda fuera del total comercial.
- Falta despliegue 24/7.

