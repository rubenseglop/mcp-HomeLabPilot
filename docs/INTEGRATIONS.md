# Integraciones

HomeLabPilot conecta con las API nativas de los servicios configurados. La disponibilidad concreta depende de la versión instalada y de las credenciales/permisos de cada aplicación.

## Integraciones principales

- **Radarr, Sonarr, Lidarr:** bibliotecas, búsquedas, colas, historial y operaciones compatibles con sus API.
- **Prowlarr y Bazarr:** configuración e integración con sus API.
- **qBittorrent:** torrents, categorías, colas, control de transferencias y flujos de previsualización/confirmación para operaciones sensibles.
- **Scryer:** API GraphQL, biblioteca, solicitudes, auditoría y papelera.
- **Tdarr:** estado, nodos, búsqueda de archivos e informes; algunas operaciones específicas requieren previsualización y confirmación.
- **Plex y Jellyfin:** bibliotecas, actividad y sesiones de reproducción.
- **Seerr, Immich y RomM:** solicitudes multimedia, biblioteca fotográfica y catálogo de juegos.
- **Home Assistant:** estados, entidades, historial y catálogo de servicios; ejecutar servicios requiere permiso admin y confirmación.
- **Transmission, Cloudflare, Youtarr, FlareSolverr, Cleanuparr, Maintainerr, Tidarr, BookOrbit, Tracearr, Agregarr, Pulsarr y TinyMediaManager:** herramientas específicas según la API disponible y la configuración.

El catálogo de aplicaciones de la interfaz muestra qué servicios están configurados y el estado de conexión. Una aplicación puede aparecer en el catálogo aunque todavía no tenga integración funcional completa.

## Herramientas MCP

Las herramientas se agrupan por servicio y operación. Entre las capacidades disponibles se incluyen:

- Consultar estado, bibliotecas, colas, historial y actividad.
- Buscar títulos, lanzamientos y elementos multimedia.
- Gestionar operaciones compatibles con las API nativas.
- Inspeccionar integraciones adicionales mediante llamadas API restringidas.
- Consultar el historial de operaciones de HomeLabPilot.

No todas las herramientas están disponibles para todos los niveles de permisos. Algunas integraciones son únicamente de lectura.

## API y configuración

Las URL y credenciales se configuran en el archivo privado `.env` o desde los formularios de conexión admitidos en la interfaz. Las URL deben ser accesibles desde el contenedor de HomeLabPilot.

Referencias habituales:

| Servicio | API |
|---|---|
| Radarr / Sonarr | `/api/v3` |
| Prowlarr / Lidarr | `/api/v1` |
| Bazarr | `/api` |
| Scryer | GraphQL en `/graphql` |
| qBittorrent | Web API en `/api/v2` |
| Home Assistant | REST API en `/api` |

Postgres y Redis disponen de comprobaciones de conectividad TCP. Recyclarr se identifica como integración de contenedor/CLI; no implica que exista una API MCP específica.

Consulta el archivo `.env.example` para conocer las variables de configuración disponibles.
