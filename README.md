# HomeLabPilot

**HomeLabPilot reúne un panel web y un servidor MCP para consultar y operar tu ecosistema multimedia desde un único lugar.**

Conecta servicios como Radarr, Sonarr, Lidarr, Prowlarr, Bazarr y qBittorrent, además de otras aplicaciones compatibles. Puedes utilizar la interfaz web o conectar un cliente MCP. También incluye un espacio de chat con **Codex CLI**.

## Qué incluye

- Panel web con catálogo de aplicaciones, estado de conexiones y herramientas para los servicios integrados.
- Servidor MCP con permisos diferenciados para lectura, operaciones y administración.
- Integraciones con aplicaciones multimedia, automatización, fotografías, juegos y otros servicios.
- Previsualización y confirmación explícita para operaciones sensibles.
- Chat con Codex CLI en un contenedor aislado y con acceso MCP de solo lectura.

Consulta [Integraciones](docs/INTEGRATIONS.md) para ver el alcance técnico y [Seguridad](docs/SECURITY.md) para conocer los permisos y protecciones.

## Instalación con Docker Compose

Necesitas Docker Engine y Docker Compose en el equipo donde ejecutarás HomeLabPilot.

1. Clona el repositorio y entra en la carpeta:

   ```bash
   git clone https://github.com/rubenseglop/mcp-HomeLabPilot.git
   cd mcp-HomeLabPilot
   ```

2. Crea tu configuración y genera un token MCP:

   ```bash
   cp .env.example .env
   openssl rand -hex 32
   ```

3. Edita `.env` y configura, como mínimo:

   - `MCP_AUTH_TOKEN`: pega el token generado.
   - `HOMELABPILOT_WEB_USERNAME` y `HOMELABPILOT_WEB_PASSWORD`: credenciales para el panel web.
   - Las URL y claves API de las aplicaciones que quieras conectar.

   No compartas ni subas el archivo `.env` a Git.

4. Inicia los servicios:

   ```bash
   docker compose up -d --build
   ```

5. Abre el panel en:

   ```
   http://localhost:8765
   ```

Por defecto, el puerto se publica solo en loopback. Para acceder desde otros equipos de la LAN, configura `HOMELABPILOT_BIND_ADDRESS=0.0.0.0` en `.env` y recrea el contenedor. No expongas el puerto directamente a Internet.

**Importante:** las URL de las aplicaciones deben ser accesibles desde dentro del contenedor de HomeLabPilot. Si están en otras redes Docker, conecta el servicio a esas redes o utiliza direcciones alcanzables desde el contenedor.

## Conectar un cliente MCP

El endpoint HTTP es:

```
http://YOUR_DOCKER_HOST:8765/mcp
```

Autenticación: `Authorization: Bearer YOUR_MCP_AUTH_TOKEN`.

Configura el cliente MCP con esa URL y el token generado. El servidor valida también el encabezado `Host`; añade los nombres de host utilizados a `HOMELABPILOT_MCP_ALLOWED_HOSTS` en `.env`.

## Chat con Codex

El chat integrado utiliza Codex CLI dentro del contenedor aislado de agentes. Tras iniciar el stack, autentica Codex desde el host:

```bash
docker compose exec homelabpilot-agents codex login --device-auth
```

Después abre **AI Chat** en el panel. El agente utiliza un proxy MCP de solo lectura y no tiene acceso al socket Docker del host ni a las carpetas multimedia.

## Configuración y permisos

- Copia las variables que necesites desde `.env.example`; no hace falta configurar aplicaciones que no utilices.
- El nivel de permisos MCP se controla con `HOMELABPILOT_MCP_PERMISSION_LEVEL`: `read`, `operations` o `admin`.
- Para cifrar la configuración persistente, define una clave estable en `HOMELABPILOT_CONFIG_ENCRYPTION_KEY`.
- La gestión Docker es opcional y está desactivada por defecto.

Lee [Seguridad](docs/SECURITY.md) antes de habilitar operaciones administrativas o acceso remoto.

## Desarrollo

Requiere Python 3.11 o superior:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest
```

Para ejecutar el servidor localmente, configura las variables de entorno de `.env` y ejecuta:

```bash
homelabpilot-mcp
```

---

HomeLabPilot es un proyecto en desarrollo. Las funciones disponibles dependen de las integraciones implementadas y de las API de cada servicio.
