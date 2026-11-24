# HomeLabPilot — Auditoría y hoja de ruta

> Documento maestro para continuar el desarrollo. Actualizar este archivo al integrar cambios relevantes y mantener separadas las funcionalidades implementadas, las pruebas automatizadas y la validación en el servidor real.

- **Repositorio:** `rubenseglop/mcp-HomeLabPilot`
- **Rama principal:** `main`
- **Commit auditado:** `9b4d058bd6283ab67ad425f860d7ad3b0a12f2e2`
- **Fecha de auditoría:** 2026-11-24
- **Estado:** desarrollo integrado en main; validación E2E del despliegue pendiente.
- **Documentación:** README, integraciones, seguridad, hoja de ruta y validación final.

## 1. Resumen ejecutivo

La rama principal contiene el desarrollo funcional integrado durante la auditoría: servidor MCP, integraciones multimedia y de infraestructura, panel web, catálogo de aplicaciones, gateway de agentes, proxy MCP de solo lectura, gateway Docker opcional y navegación lateral compacta.

La última integración visible en main es el cambio de navegación lateral del 24-11-2026. Agrupa Radarr, Sonarr, Lidarr y Scryer en secciones plegables, mantiene Descargas como acceso directo, conserva el estado de los grupos y adapta la barra lateral a pantallas estrechas.

**No debe confundirse el estado de GitHub con el estado del mediacenter.** En esta auditoría se ha consultado GitHub; no se ha inspeccionado el checkout local ni se ha confirmado que los contenedores estén ejecutando este commit.

## 2. Inventario contrastado en el código

| Elemento | Recuento / estado | Observación |
|---|---:|---|
| Herramientas MCP en `server.py` | 52 | Declaraciones `@mcp.tool` |
| Herramientas MCP en `integrations.py` | 131 | Declaraciones `@mcp.tool` |
| Herramientas MCP en `seanime.py` | 18 | Declaraciones `@mcp.tool` |
| Total estático | **201** | 201 declaraciones y nombres únicos en esos tres módulos |
| Catálogo web | **32 aplicaciones** | Entradas declaradas en `APP_CATALOG`; no todas implican integración operativa |
| Pruebas Python | **147 funciones** | Repartidas en seis archivos de pruebas |
| Pruebas Node | **9 casos** | Suites de proxy y política |
| Script adicional | 1 | `tests/check-web-script.mjs` valida JavaScript embebido |

Estos son recuentos estáticos del commit auditado. El número de herramientas publicadas por `tools/list` debe medirse en runtime y podría variar según configuración, permisos y filtros.

## 3. Arquitectura actual

- **Aplicación principal:** servidor MCP y panel web en el mismo servicio.
- **Persistencia:** volumen de estado de HomeLabPilot; configuración de aplicaciones cifrada.
- **Gateway de agentes:** contenedor separado para los agentes CLI y su estado.
- **Proxy MCP:** allowlist exacta de herramientas de lectura, denegación por defecto y red Docker interna `agent_control`; no publica puerto del host.
- **Docker Gateway:** servicio opcional bajo perfil Compose, con acceso al socket Docker y operaciones limitadas por allowlist.
- **Servicios externos:** se conectan por URL y credenciales configuradas por el operador.

## 4. Integraciones y paneles

Las integraciones implementadas abarcan, entre otras, Radarr, Sonarr, Lidarr, Prowlarr, Bazarr, qBittorrent, Scryer, Plex, Jellyfin, Seerr, Immich, RomM, Tdarr, Seanime, Questarr, Frigate, Recyclarr, Home Assistant, Transmission, Cloudflare, Youtarr, FlareSolverr, Cleanuparr, Maintainerr, Tidarr, BookOrbit, Tracearr, Agregarr, Pulsarr y tinyMediaManager.

El catálogo web contiene 32 entradas. Hay distintos niveles de soporte: vistas nativas de gestión, paneles de consulta de solo lectura, comprobaciones de estado y soporte parcial. No presentar todos los elementos del catálogo como paneles completos.

Los detalles de capacidades y endpoints están en [INTEGRATIONS.md](INTEGRATIONS.md).

## 5. Seguridad y permisos

- El MCP principal autentica mediante Bearer token.
- Los permisos se dividen en `read`, `operations` y `admin`.
- Las operaciones sensibles utilizan previews firmados y confirmación explícita, con controles específicos por integración.
- El proxy de agentes publica únicamente herramientas incluidas en una allowlist exacta y bloquea por defecto las demás.
- El proxy no publica puertos y usa la red interna `agent_control`.
- El gateway de agentes mantiene salida externa por la red `default`.
- El Docker Gateway es opcional y restringe los contenedores y operaciones admitidos.
- Las credenciales guardadas desde el catálogo se cifran y no se devuelven al navegador.

La revisión estática del repositorio no sustituye la comprobación de la topología, permisos y credenciales efectivos en ejecución. Ver [SECURITY.md](SECURITY.md).

## 6. Estado de la última integración

| Cambio | Estado |
|---|---|
| Desarrollo funcional de integraciones y paneles | Integrado en main |
| Proxy MCP read-only y allowlist | Integrado en main |
| Aislamiento de red del proxy | Integrado en main; validación de topología real pendiente |
| Catálogo de aplicaciones y configuración cifrada | Integrado en main |
| Navegación lateral compacta | Integrada en main mediante PR #3 |
| CI de la PR de navegación | Correcta, run 45391666643 |
| Despliegue en mediacenter del commit actual | No confirmado |
| Pruebas E2E contra las API reales | Pendientes |

## 7. Hoja de ruta priorizada

### Prioridad 1 — Validación del commit actual

1. Confirmar qué commit está desplegado en el mediacenter y si el checkout está limpio.
2. Ejecutar las suites Python y Node sobre el commit actual de main.
3. Validar Compose en perfiles base y Docker.
4. Comparar el inventario estático de 201 herramientas con `tools/list` en runtime.
5. Verificar autenticación MCP, allowlist del proxy y bloqueo de escrituras.
6. Confirmar topología de red y healthchecks de los contenedores.

### Prioridad 2 — Validación funcional de servicios

1. Probar una lectura inocua por cada integración configurada.
2. Revisar catálogo, estado de conexión y formularios de configuración.
3. Validar los paneles de consulta y los paneles nativos.
4. Verificar permisos y previews con mocks o recursos de prueba.
5. Registrar las integraciones no configuradas como no aplicables.

### Prioridad 3 — Mejoras pendientes

- Completar las vistas que aún muestran solo estado/configuración o soporte parcial.
- Ampliar la matriz automatizada que relaciona cada herramienta mutante con permiso mínimo, preview y confirmación.
- Mejorar las pruebas E2E y la detección de diferencias entre catálogo, herramientas MCP y allowlist read-only.
- Mantener la documentación de endpoints y variables sincronizada con el código.

No añadir una integración nueva únicamente porque aparezca en una lista de ideas: primero comprobar que existe una API utilizable, autenticación soportada y operaciones documentadas o verificables.

## 8. Decisiones de alcance que deben respetarse

- **TrackTV:** queda aparcado. No se ha confirmado una API oficial ni un mecanismo de acceso estable. No crear un MCP ni automatización web hasta disponer de un método de integración fiable.
- **Historial de visionado:** no crear una base de datos histórica paralela. No duplicar la base de datos de Jellyfin.
- **Jellyfin/Trakt:** mantener intacta la integración y sincronización existentes. No convertir Trakt en fuente central ni modificar su plugin.
- Las integraciones nuevas deben trabajar directamente con el servicio de destino y no introducir almacenamiento duplicado sin petición expresa.

## 9. Reglas de trabajo

1. Leer este documento antes de retomar tareas.
2. Trabajar sobre la rama principal o crear una rama específica para cambios acotados; no asumir que existe una rama feature activa.
3. No afirmar que un cambio está desplegado hasta tener evidencia del mediacenter.
4. No repetir comprobaciones sin una razón concreta; agrupar validaciones relacionadas.
5. No ejecutar operaciones destructivas sobre datos reales durante pruebas.
6. Actualizar los documentos afectados en el mismo cambio que modifica el comportamiento.
7. Registrar commit, CI y validación real por separado.

## 10. Registro de auditoría — 2026-11-24

- Revisado el árbol de `main` y los cinco documentos Markdown existentes.
- Confirmado commit `9b4d058bd6283ab67ad425f860d7ad3b0a12f2e2`.
- Contraste estático: 201 declaraciones de herramientas MCP en los tres módulos principales.
- Contraste del catálogo web: 32 entradas.
- Inventario de pruebas: 147 funciones Python, 9 casos Node y un script de comprobación JavaScript.
- Confirmada la integración de la navegación lateral compacta mediante PR #3; CI de la PR completada con éxito.
- No se ha inspeccionado el servidor Proxmox/mediacenter durante esta auditoría; despliegue y E2E permanecen sin confirmar.
