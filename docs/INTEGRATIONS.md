# Integraciones

HomeLabPilot se conecta a las API nativas de los servicios configurados. La disponibilidad depende de la versión del servicio, las credenciales, los permisos y la conectividad desde el contenedor. Una entrada en el catálogo o una herramienta implementada no demuestra por sí sola que la integración esté operativa en una instalación concreta.

## Integraciones

- **Radarr, Sonarr y Lidarr:** bibliotecas, búsquedas, colas, historial y operaciones admitidas por sus API.
- **Prowlarr y Bazarr:** integración con sus API y consultas de configuración/estado disponibles.
- **qBittorrent:** torrents, categorías, colas, transferencias y operaciones protegidas mediante previsualización y confirmación.
- **Scryer:** API GraphQL, biblioteca, solicitudes, auditoría y papelera.
- **Plex y Jellyfin:** bibliotecas, actividad y sesiones de reproducción.
- **Seerr, Immich y RomM:** solicitudes multimedia, biblioteca fotográfica y catálogo de juegos.
- **Tdarr:** estado del servidor, nodos/workers, búsqueda acotada de archivos, informes paginados y detalle de logs. Reencolar hasta 50 archivos y volver a escanear un archivo requiere permiso `operations`, preview firmado vigente y confirmación exacta.
- **Seanime:** estado, búsqueda AniList, biblioteca local, seguimiento, auditoría de asignaciones, archivos sin correspondencia, inspección de entradas y cola/ajustes del auto-downloader. Los secretos se redactan. Los cambios admitidos están limitados a preferencias booleanas de bajo riesgo o acciones específicas con permiso, preview y confirmación.
- **Questarr:** estado y lectura de biblioteca mediante clave de integración con scope `read`.
- **Frigate:** estadísticas, eventos y elementos de revisión mediante token JWT de usuario `viewer` o superior; las herramientas implementadas son de solo lectura.
- **Recyclarr:** consulta de estado y ejecución del comando fijo `recyclarr sync` mediante Docker Gateway, con contenedor permitido, preview firmado y confirmación exacta.
- **Home Assistant:** estados, entidades, historial y catálogo de servicios; ejecutar servicios requiere permiso administrativo y confirmación.
- **Docker Gateway:** lista de contenedores explícitamente permitidos y operaciones limitadas de start/stop/restart; no admite comandos arbitrarios.
- **Transmission, Cloudflare, Youtarr, FlareSolverr, Cleanuparr, Maintainerr, Tidarr, BookOrbit, Tracearr, Agregarr, Pulsarr y tinyMediaManager:** herramientas específicas según la API y configuración de cada servicio.
- **PostgreSQL y Redis:** comprobaciones de conectividad TCP.

## Catálogo y paneles web

El catálogo de aplicaciones contiene actualmente **32 entradas** definidas en el código del panel. Incluye integraciones nativas, servicios con API, comprobaciones de estado y aplicaciones cuyo soporte es parcial. La presencia en el catálogo no garantiza conexión ni un panel completo.

Los paneles de consulta adicionales cubren, entre otros, Plex, Jellyfin, Seerr, Immich, Tdarr, Home Assistant, RomM, Questarr, Frigate, BookOrbit, Tidarr, Youtarr, Pulsarr, Cleanuparr, Maintainerr, Agregarr, Tracearr, Cloudflare, Transmission, FlareSolverr y tinyMediaManager. Las vistas nativas de Radarr, Sonarr, Lidarr, qBittorrent y Scryer ofrecen los flujos principales de gestión de esas aplicaciones.

La navegación lateral agrupa las vistas de Radarr, Sonarr, Lidarr y Scryer en secciones desplegables; Descargas permanece como acceso directo. El estado abierto/cerrado de los grupos se conserva en el navegador y se adapta a pantallas estrechas.

## Herramientas MCP y proxy de agentes

Las herramientas se agrupan por servicio y operación. Las lecturas pueden usar GET o POST cuando la API nativa lo necesita para búsquedas o listados sin efectos laterales.

El proxy MCP utilizado por los agentes aplica una allowlist exacta de herramientas de lectura y deniega por defecto las no incluidas. No deben aparecer en él las herramientas de escritura, preview o confirmación. El proxy no publica un puerto del host y se conecta a la red Docker interna `agent_control`; el gateway de agentes conserva conectividad externa por la red `default`.

Las operaciones de escritura del MCP principal permanecen separadas de las lecturas y se someten al nivel de permiso correspondiente, además de los controles específicos de cada integración.

## Referencias de API y configuración

Las URL y credenciales se configuran en el archivo privado `.env` o desde los formularios de conexión admitidos en el panel. No se deben incluir credenciales en documentación, incidencias ni logs.

| Servicio | API / referencia |
|---|---|
| Radarr / Sonarr | `/api/v3` |
| Prowlarr / Lidarr | `/api/v1` |
| Bazarr | `/api` |
| Scryer | GraphQL en `/graphql` |
| qBittorrent | Web API en `/api/v2` |
| Home Assistant | REST API en `/api` |
| Seanime | REST API `/api/v1`; ajustes consultados y modificados mediante endpoints específicos |
| Tdarr | REST API `/api/v2`; búsquedas/listados POST de solo lectura y acciones protegidas |
| Questarr | API de integración `/api/integration` (clave `read`) |
| Frigate | REST API `/api` (Bearer JWT de usuario con rol viewer o superior) |

Recyclarr solo ejecuta el comando fijo `recyclarr sync` dentro del contenedor indicado en `RECYCLARR_CONTAINER`, que también debe estar en la allowlist Docker. No se admite ejecución arbitraria de comandos.

Consulta `.env.example` para conocer las variables de configuración disponibles. La configuración persistente guardada desde el catálogo se cifra en el volumen de datos y no devuelve secretos al navegador.
