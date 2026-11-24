# Integraciones

HomeLabPilot conecta con las API nativas de los servicios configurados. La disponibilidad concreta depende de la versión instalada y de las credenciales/permisos de cada aplicación.

## Integraciones principales

La rama feature incluye integraciones nativas, consultas específicas y flujos de escritura protegidos. La disponibilidad en ejecución depende de la configuración y de la versión de cada servicio; las funciones implementadas no implican que estén verificadas contra la instalación real.

- **Radarr, Sonarr, Lidarr:** bibliotecas, búsquedas, colas, historial y operaciones compatibles con sus API.
- **Prowlarr y Bazarr:** configuración e integración con sus API.
- **qBittorrent:** torrents, categorías, colas, control de transferencias y flujos de previsualización/confirmación para operaciones sensibles.
- **Scryer:** API GraphQL, biblioteca, solicitudes, auditoría y papelera.
- **Tdarr:** estado del servidor, nodos/workers, búsqueda acotada de archivos, informes paginados y detalle de logs. El reencolado de hasta 50 archivos y el reescaneo de un archivo requieren permiso `operations`, preview firmado vigente y confirmación escrita exacta; nunca se exponen por el proxy read-only.
- **Seanime:** estado, búsqueda AniList, biblioteca local, seguimiento, auditoría de asignaciones, archivos sin correspondencia, inspección de entradas y cola/ajustes del auto-downloader. Los ajustes consultados ocultan contraseñas/tokens. Cambios permitidos: solo preferencias booleanas de bajo riesgo incluidas en allowlist, con permiso `admin`, preview firmado y confirmación exacta. Añadir títulos a AniList y reasignar archivos también requieren preview firmado y confirmación; la reasignación no mueve archivos físicos y advierte de los cambios de `Locked`/`Ignored` que aplica Seanime.
- **Plex y Jellyfin:** bibliotecas, actividad y sesiones de reproducción.
- **Seerr, Immich y RomM:** solicitudes multimedia, biblioteca fotográfica y catálogo de juegos.
- **Questarr:** estado de la API y lectura de biblioteca mediante clave de integración con scope `read`; el catálogo de aplicaciones ofrece un panel de estado y biblioteca.
- **Frigate:** estadísticas, eventos y elementos de revisión mediante token JWT de usuario `viewer` o superior; el catálogo de aplicaciones ofrece paneles de estadísticas, eventos y revisión. Las herramientas implementadas son de solo lectura.
- **Recyclarr:** panel de estado y sincronización fija `recyclarr sync` con preview y confirmación exacta mediante Docker Gateway.
- **Home Assistant:** estados, entidades, historial y catálogo de servicios; ejecutar servicios requiere permiso admin y confirmación.
- **Docker Gateway:** lista contenedores exactos de una allowlist; start/stop/restart requiere permiso Docker `operations`, preview firmado y frase de confirmación exacta.
- **Transmission, Cloudflare, Youtarr, FlareSolverr, Cleanuparr, Maintainerr, Tidarr, BookOrbit, Tracearr, Agregarr, Pulsarr y TinyMediaManager:** herramientas específicas según la API disponible y la configuración.

El catálogo de aplicaciones de la interfaz muestra qué servicios están configurados, el estado de conexión y las consultas disponibles. Las aplicaciones con soporte de panel ofrecen operaciones explícitas; las que solo muestran configuración o estado no se presentan como paneles funcionales completos.

## Paneles de aplicaciones

El catálogo de aplicaciones incluye paneles de consulta de solo lectura para Plex, Jellyfin, Seerr, Immich, Tdarr, Home Assistant, RomM, Questarr, Frigate, BookOrbit, Tidarr, Youtarr, Pulsarr, Cleanuparr, Maintainerr, Agregarr, Tracearr, Cloudflare, Transmission, FlareSolverr y tinyMediaManager. Cada panel solo llama a operaciones incluidas en una lista explícita de lecturas; las acciones de escritura siguen en herramientas MCP separadas y protegidas por permisos/confirmaciones.

## Herramientas MCP

Las herramientas de consulta pueden usar GET o POST cuando la API nativa lo requiere para búsquedas/listados sin efectos laterales. El proxy de solo lectura usa una allowlist exacta: las herramientas no aprobadas quedan denegadas por defecto. Las operaciones de escritura permanecen separadas y requieren los permisos y confirmaciones que defina cada integración.

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
| Seanime | REST API `/api/v1`; ajustes `GET /settings` y cambio individual `PATCH /settings/path` |
| Tdarr | REST API `/api/v2`; búsquedas/listados POST read-only, acciones protegidas por preview |
| Questarr | API de integración `/api/integration` (clave `read`) |
| Frigate | REST API `/api` (token bearer de usuario viewer) |

Postgres y Redis disponen de comprobaciones de conectividad TCP. Recyclarr se ejecuta mediante el Docker Gateway restringido: solo lanza el comando fijo `recyclarr sync` dentro del contenedor exacto configurado en `RECYCLARR_CONTAINER`, que además debe estar en la allowlist Docker. La ejecución requiere permiso Docker `operations`, preview firmado y confirmación escrita; no se admite ejecutar comandos arbitrarios.

Consulta el archivo `.env.example` para conocer las variables de configuración disponibles.
