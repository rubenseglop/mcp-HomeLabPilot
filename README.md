# HomeLabPilot

**MCP Server & AI Control Center for your Homelab**

HomeLabPilot conecta asistentes de inteligencia artificial con los servicios del homelab mediante **MCP (Model Context Protocol)**. Reúne un servidor MCP, un panel web y un espacio de chat con agentes CLI, con permisos diferenciados y controles para las operaciones sensibles.

El proyecto está desarrollado en Python y se despliega con Docker Compose. La rama principal contiene las integraciones, el catálogo de aplicaciones, los paneles web y los componentes auxiliares descritos en esta documentación.

## Qué incluye

- Servidor MCP HTTP con autenticación Bearer y catálogo de herramientas para servicios del homelab.
- Panel web con catálogo de aplicaciones, estado de conexiones y vistas de gestión para Radarr, Sonarr, Lidarr, qBittorrent y Scryer.
- Paneles de consulta para servicios adicionales; el alcance depende de cada integración.
- Herramientas de lectura y operaciones de escritura separadas por permisos.
- Previsualización firmada y confirmación explícita para operaciones sensibles.
- Catálogo de aplicaciones con 32 entradas en el código actual. Que una aplicación aparezca en el catálogo no significa que esté configurada ni que todas sus funciones hayan sido validadas en una instalación real.
- Chat con agentes CLI mediante un gateway separado y un proxy MCP de solo lectura.
- Gateway Docker opcional, desactivado por defecto y limitado a contenedores permitidos.

Consulta [Integraciones](docs/INTEGRATIONS.md), [Seguridad](docs/SECURITY.md), [la hoja de ruta de auditoría](docs/ROADMAP_AUDITORIA.md) y [la campaña de validación](docs/VALIDACION_FINAL.md).

## Instalación con Docker Compose

Necesitas Docker Engine y Docker Compose.

1. Clona el repositorio:

   ```bash
   git clone https://github.com/rubenseglop/mcp-HomeLabPilot.git
   cd mcp-HomeLabPilot
   ```

2. Crea el archivo de configuración y genera un token:

   ```bash
   cp .env.example .env
   openssl rand -hex 32
   ```

3. Edita `.env` y configura como mínimo:
   - `MCP_AUTH_TOKEN`: token generado para el endpoint MCP.
   - `HOMELABPILOT_WEB_USERNAME` y `HOMELABPILOT_WEB_PASSWORD`: acceso al panel.
   - Las URL y claves API de los servicios que quieras conectar.

   No subas ni compartas el archivo `.env`.

4. Inicia el stack:

   ```bash
   docker compose up -d --build
   ```

5. Abre el panel en `http://localhost:8765`.

Por defecto, el puerto se publica en loopback. Para acceder desde otros equipos de la LAN, configura `HOMELABPILOT_BIND_ADDRESS=0.0.0.0` y recrea el servicio. No expongas directamente el panel a Internet.

Las URL de los servicios deben ser accesibles desde el contenedor de HomeLabPilot. Si las aplicaciones están en otras redes Docker, conecta el servicio a una red compartida o utiliza direcciones alcanzables.

## Conectar un cliente MCP

Endpoint HTTP:

```
http://YOUR_DOCKER_HOST:8765/mcp
```

Autenticación mediante `Authorization: Bearer YOUR_MCP_AUTH_TOKEN`. El servidor también valida el encabezado `Host`; configura `HOMELABPILOT_MCP_ALLOWED_HOSTS` para los nombres de host que utilices.

## Chat con agentes

El chat utiliza el contenedor `homelabpilot-agents` y el gateway correspondiente. Para autenticar Codex:

```bash
docker compose exec homelabpilot-agents codex login --device-auth
```

Después abre **AI Chat** en el panel. El acceso MCP del agente pasa por un proxy con allowlist de lectura; no equivale a los permisos del MCP principal. El agente no monta el socket Docker del host ni las carpetas multimedia.

## Configuración y permisos

- Configura solo las aplicaciones que utilices.
- `HOMELABPILOT_MCP_PERMISSION_LEVEL` controla los permisos: `read`, `operations` o `admin`.
- Define una clave estable `HOMELABPILOT_CONFIG_ENCRYPTION_KEY` para cifrar la configuración persistente.
- La gestión Docker es opcional y se activa mediante el perfil Compose correspondiente.
- No compartas tokens, claves API ni cookies de sesión.

Consulta [Seguridad](docs/SECURITY.md) antes de habilitar operaciones administrativas o acceso desde la LAN.

## Desarrollo y pruebas

Requiere Python 3.11 o superior:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest
```

Para ejecutar el servidor localmente, configura las variables de entorno y ejecuta:

```bash
homelabpilot-mcp
```

## Estado del repositorio

La rama `main` es la rama principal de desarrollo e incluye la integración funcional y la navegación lateral compacta. La validación automatizada de la CI y la validación de código no sustituyen la comprobación E2E contra los servicios reales. El despliegue en una instalación concreta debe verificarse por separado.

La documentación de estado y las tareas pendientes se mantienen en [docs/ROADMAP_AUDITORIA.md](docs/ROADMAP_AUDITORIA.md).
