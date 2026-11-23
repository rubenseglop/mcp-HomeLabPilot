# HomeLabPilot — Flujo maestro de auditoría y desarrollo

> **Documento de referencia único para continuar el proyecto.** Antes de cada sesión de trabajo hay que leer este archivo y continuar desde el primer nodo pendiente. Después de cada tarea completada, actualizar aquí el estado y el registro.

- **Repositorio:** `rubenseglop/mcp-HomeLabPilot`
- **Rama de trabajo:** `feature/complete-homelabpilot` (base `main` en `a5ddc62`)
- **Última actualización:** 2026-11-23
- **Fase activa:** Desarrollo integral — correcciones y funcionalidades
- **Estado global:** EN CURSO
- **Autorización de trabajo:** El 23-11-2026 el usuario indicó abandonar las comprobaciones repetitivas y pasar directamente a programar. Se permite modificar código en la rama feature; `main` permanece intacta.

## 1. Flujo general

```mermaid
flowchart TD
    START([Inicio / retomar trabajo]) --> READ[Leer este documento y revisar GitHub]
    READ --> NEXT[Localizar primera tarea pendiente]
    NEXT --> P1[Prioridad 1: auditoría]
    P1 --> G1{Auditoría completa}
    G1 -- No --> P1
    G1 -- Sí --> P2[Prioridad 2: terminar integraciones]
    P2 --> G2{Integraciones terminadas}
    G2 -- No --> P2
    G2 -- Sí --> P3[Prioridad 3: paneles propios]
    P3 --> G3{Paneles terminados}
    G3 -- No --> P3
    G3 -- Sí --> P4[Prioridad 4: calidad]
    P4 --> G4{Pruebas superadas}
    G4 -- No --> FIX[Registrar y corregir problemas]
    FIX --> P4
    G4 -- Sí --> END([Proyecto validado])
    END --> UPDATE[Actualizar este documento y GitHub]
```

## 2. Prioridad 1 — Comprobar todo lo existente

```mermaid
flowchart TD
    A[Auditoría existente] --> B[Verificar código y despliegue]
    B --> C[Contar y revisar herramientas MCP]
    C --> D[Comprobar integraciones y catálogo]
    D --> E[Verificar proxy MCP]
    E --> F[Verificar conexión de Codex]
    F --> G[Comprobar bloqueo de escrituras]
    G --> H{Todos los controles superados}
    H -- No --> A
    H -- Sí --> NEXT([Prioridad 2])
```

### 1.1 Código y despliegue

| Tarea | Estado | Resultado / observaciones |
|---|---|---|
| Comprobar repositorio y rama `main` | COMPLETADO | Repositorio `rubenseglop/mcp-HomeLabPilot` |
| Comprobar árbol de trabajo limpio | COMPLETADO | Sin cambios pendientes en la comprobación del 23-11-2026 |
| Contrastar commit del servidor con GitHub | COMPLETADO | `44985e1` (comprobación previa del 23-11-2026) |
| Confirmar que el contenedor ejecuta exactamente ese código | COMPLETADO | Cinco hashes SHA-256 idénticos entre checkout local y `/app` en el contenedor; ejecuta el código del checkout `44985e1` |

### 1.2 Herramientas MCP

| Tarea | Estado | Resultado / observaciones |
|---|---|---|
| Ejecutar `tools/list` | COMPLETADO | Respuesta JSON-RPC correcta |
| Registrar recuento real | COMPLETADO | **187 herramientas** publicadas |
| Aclarar diferencia respecto a las 189 previstas | COMPLETADO | En el checkout desplegado entonces: 189 declaraciones `@mcp.tool`, 187 nombres únicos por dos duplicados; coincide con `tools/list` (187). En la rama feature actual: 199 declaraciones, 197 nombres únicos; los mismos dos duplicados. |
| Revisar herramientas duplicadas, ausentes o inesperadas | PARCIAL | Confirmados dos nombres duplicados (`cleanuparr_get_health`, `maintainerr_get_health`); las dos versiones consultan el mismo endpoint GET. Clasificación estática del proxy: 133 nombres permitidos y 54 bloqueados; entre los bloqueados hay lecturas legítimas de Seanime (`seanime_search_anime`, `seanime_verify_reassignment`, `seanime_audit_library`, `seanime_inspect_entry`) y el helper puro `collection_has_media_id`. Comparación estática feature completada: 201 nombres únicos frente a 148 permitidos; los 53 restantes permanecen denegados por defecto y están clasificados. Pendiente comparar con inventario runtime actualizado y validar semántica individual antes de ampliar la allowlist |

### 1.3 Integraciones

| Tarea | Estado | Resultado / observaciones |
|---|---|---|
| Ejecutar `stack_status` | COMPLETADO | 10 de 10 servicios configurados respondieron correctamente |
| Revisar versiones y campos no disponibles | PARCIAL | Bazarr, Seanime, Jellyfin y Tdarr no devolvieron versión; no equivale a fallo de conectividad |
| Revisar implementación de `integration_catalog` | PARCIAL | Código inspeccionado: 20 integraciones HTTP adicionales y 4 no HTTP; Seanime está declarado también en el bloque principal y su modo se sobrescribe en el catálogo. Falta ejecución funcional para verificar la configuración real |

### 1.4 Proxy MCP, Codex y permisos

| Tarea | Estado | Resultado / observaciones |
|---|---|---|
| Comprobar endpoint de salud del proxy | COMPLETADO | HTTP 200; modo `read-only` |
| Comprobar salud del gateway de agentes | COMPLETADO | HTTP 200 |
| Verificar autenticación/configuración MCP de Codex | PARCIAL | Gateway informó `authenticated=true` y `mcp_configured=true`; falta probar una llamada real a través del proxy |
| Revisar autenticación Bearer del MCP principal | COMPLETADO EN FEATURE | `_BearerAuthMiddleware` exige el token completo con comparación constante; se añadieron pruebas para token ausente, incorrecto y correcto. CI pendiente. |
| Ejecutar `tools/list` a través del proxy | COMPLETADO | 23-11-2026: initialize HTTP 200, sesión creada, tools/list HTTP 200, 137 herramientas visibles con la política anterior, sin error JSON-RPC. La nueva allowlist explícita contiene 148 herramientas (lecturas aprobadas de forma exacta, incluidas Questarr, Frigate, Seanime settings y Recyclarr status); pendiente desplegar y verificar el nuevo resultado. |
| Ejecutar una herramienta de lectura a través del proxy | PARCIAL | Prueba aislada del handler con lectura aprobada y cabecera Bearer superada; pendiente E2E real tras despliegue autorizado |
| Verificar bloqueo de herramientas de escritura en el proxy | PARCIAL | COMPLETADO EN FEATURE mediante pruebas del handler real: las escrituras Seanime/Tdarr se rechazan antes de llamar al upstream. Pendiente E2E contra el proxy desplegado, sin invocar mutaciones reales |
| Verificar que las lecturas siguen permitidas | PARCIAL | COMPLETADO EN FEATURE: `tdarr_search_files` atraviesa el handler con Bearer; `tools/list` filtra exactamente las lecturas. Pendiente llamada real contra el proxy desplegado |

**Criterio para cerrar Prioridad 1:** todas las tareas deben estar COMPLETADAS o tener una excepción documentada y aceptada. Los estados PARCIAL y BLOQUEADO no cierran una fase.

## 3. Prioridad 2 — Terminar las integraciones

```mermaid
flowchart TD
    A[Prioridad 2] --> B[Questarr]
    B --> C[Frigate]
    C --> D[Recyclarr]
    D --> E[Docker Gateway y catálogo]
    E --> F{Integraciones verificadas}
    F -- No --> A
    F -- Sí --> NEXT([Prioridad 3])
```

| Tarea | Estado | Alcance |
|---|---|---|
| Questarr | PARCIAL | API de lectura y panel en catálogo con estado/biblioteca; credencial `read`, límites y pruebas unitarias. CI de la rama superado (run 410); pendiente validación real. |
| Frigate | PARCIAL | API de estadísticas/eventos/revisión y panel en catálogo; bearer JWT, solo lectura y paginación acotada. Pendiente CI del panel y validación real. |
| Recyclarr | PARCIAL | Estado del contenedor y ejecución fija `recyclarr sync` mediante Docker Gateway, limitada a contenedor configurado/allowlist y preview firmado con confirmación exacta. Panel en catálogo y CI de la rama superado (run 410); pendiente prueba real. |
| Docker Gateway | PARCIAL | Gateway limitado a lista explícita y start/stop/restart más comando fijo Recyclarr sync. Las acciones MCP y el panel web requieren preview firmado, comprobación previa de allowlist y confirmación escrita. CI de la rama superado hasta `a6e3b60` (run 410); pendiente validación real con el perfil Docker habilitado. |
| Seanime — gestión de configuración | COMPLETADO EN FEATURE | `seanime_get_settings` lee `/api/v1/settings` con redacción de passwords/tokens/API keys. `seanime_preview_update_setting` y `seanime_confirm_update_setting` permiten únicamente preferencias booleanas de bajo riesgo con permiso `admin`, preview firmado, revalidación del valor actual y confirmación exacta. Los cambios usan el endpoint oficial `PATCH /api/v1/settings/path`; las credenciales, rutas, clientes y ajustes sensibles quedan fuera de la allowlist. CI runs 428–430 superados; pendiente validar en la instalación real tras autorización de despliegue. |

## 4. Prioridad 3 — Paneles propios

```mermaid
flowchart TD
    A[Prioridad 3] --> B[Plex]
    B --> C[Jellyfin]
    C --> D[Seerr]
    D --> E[Immich]
    E --> F[Tdarr]
    F --> G[Home Assistant]
    G --> H[RomM]
    H --> I[Resto de aplicaciones]
    I --> J{Paneles priorizados terminados}
    J -- No --> A
    J -- Sí --> NEXT([Prioridad 4])
```

| Aplicación | Estado |
|---|---|
| Plex | PARCIAL | Panel de bibliotecas, añadidos recientes, reproducción activa y On Deck; pendiente CI y validación real. |
| Jellyfin | PARCIAL | Panel de servidor, bibliotecas y sesiones; pendiente CI y validación real. |
| Seerr | PARCIAL | Panel de estado, cola de solicitudes y datos de aplicación; pendiente CI y validación real. |
| Immich | PARCIAL | Panel de estadísticas del servidor y álbumes; pendiente CI y validación real. |
| Tdarr | COMPLETADO EN FEATURE | Cinco herramientas de lectura (estado, nodos, búsqueda, informes paginados y detalle de informe) y dos flujos de escritura (reencolar hasta 50 archivos y reescanear un archivo) con permiso `operations`, preview firmado y confirmación exacta. Pruebas unitarias específicas añadidas; CI run 434 superado (suite completa; fallos intermedios 431–433 corregidos y sustituidos); validación real pendiente de despliegue autorizado tras autorización de despliegue. |
| Home Assistant | PARCIAL | Panel de configuración, estados, catálogo de servicios, consulta individual de entidades e historial por intervalo ISO-8601; operaciones del panel exclusivamente de lectura. Corregida la validación del formato `domain.object_id`. CI run 455 superado; pendiente validación visual y funcional en la instalación real. |
| RomM | PARCIAL | Panel de plataformas, juegos y colecciones; pendiente CI y validación real. |
| Seanime | COMPLETADO EN FEATURE | Biblioteca, AniList, seguimiento, auditoría, inspección, archivos sin match y auto-downloader; ajustes booleanos seguros, añadir a AniList y reasignar archivos con preview firmado/confirmación exacta. Pruebas de redacción de secretos, permisos, token obsoleto, confirmación exacta y cambios concurrentes. Pendiente validación real tras despliegue autorizado. |
| Resto de aplicaciones, priorizadas por utilidad | PARCIAL | Añadidos paneles de solo lectura para BookOrbit, Tidarr, Youtarr, Pulsarr, Cleanuparr, Maintainerr, Agregarr, Tracearr, Cloudflare, Transmission, FlareSolverr y tinyMediaManager; pendiente CI, revisión de cobertura y validación real. |

## 5. Prioridad 4 — Calidad y validación final

```mermaid
flowchart TD
    A[Prioridad 4] --> B[Pruebas reales de integración]
    B --> C[Pruebas E2E Docker Compose]
    C --> D[Auditoría de permisos por herramienta]
    D --> E[Revisar confirmaciones de acciones sensibles]
    E --> F[Documentación automática desde catálogo]
    F --> G[Batería final de pruebas]
    G --> H{Todo superado}
    H -- No --> FIX[Registrar incidencia y corregir]
    FIX --> B
    H -- Sí --> DONE([Proyecto validado])
```

| Tarea | Estado |
|---|---|
| Pruebas reales de integración | PENDIENTE |
| Pruebas E2E de Docker Compose | PENDIENTE |
| Comprobar permisos de cada herramienta | PENDIENTE |
| Comprobar flujos de preview y confirmación de operaciones sensibles | PENDIENTE |
| Generar/actualizar documentación automáticamente desde el catálogo real | PENDIENTE |
| Ejecutar batería final de pruebas | PENDIENTE |
| Registrar versión y resultados finales | PENDIENTE |

### Mejora solicitada — herramientas por servicio en Estado de servicios

| Tarea | Estado | Detalle |
|---|---|---|
| Mostrar el número de herramientas MCP disponibles en cada servicio conectado | COMPLETADO EN FEATURE | `stack_status` añade el recuento y el catálogo de herramientas registradas por prefijo de servicio para servicios configurados y saludables. |
| Añadir listado desplegable por aplicación | COMPLETADO EN FEATURE | Cada tarjeta muestra «X herramientas disponibles» y despliega nombre y descripción de cada herramienta; no se listan herramientas de servicios desconectados. |
| Validar visualmente en despliegue real | PENDIENTE | Requiere desplegar la rama feature después de cerrar la auditoría y autorización del usuario. |

## 6. Registro de comprobaciones

| Fecha | Comprobación | Resultado |
|---|---|---|
| 2026-11-23 | Repositorio, rama y commit | Checkout del servidor `44985e1`; GitHub `main` `a5ddc62`; rama de trabajo creada desde GitHub `main` |
| 2026-11-23 | `stack_status` | 10/10 servicios configurados responden correctamente |
| 2026-11-23 | MCP `tools/list` | 187 herramientas; sin error JSON-RPC |
| 2026-11-23 | CI de mejora de inventario por servicio | run 410 (`a6e3b60`) completado con `success`; tests Python, Node y comprobación de sintaxis JS superados |
| 2026-11-23 | Proxy `/health` | HTTP 200; modo `read-only` |
| 2026-11-23 | Pruebas aisladas del handler MCP proxy | CI run 440 (`d68ddb7`) `success`: denegación previa al upstream de mutaciones Seanime/Tdarr, lecturas permitidas, Bearer, batch atómico y filtrado `tools/list` |
| 2026-11-23 | Gateway de agentes `/health` | HTTP 200; Codex autenticado y MCP configurado |
| 2026-11-23 | Revisión estática de `integration_catalog` | PARCIAL: 20 integraciones HTTP + 4 no HTTP; duplicidad de Seanime en la composición del catálogo; pendiente validación funcional |

## 7. Hallazgos de auditoría en la rama de desarrollo

| Fecha | Hallazgo | Estado / acción |
|---|---|---|
| 2026-11-23 | Rama `feature/complete-homelabpilot` creada desde `main` (`a5ddc62`) | COMPLETADO; `main` permanece intacta |
| 2026-11-23 | Servidor local en `44985e1`; GitHub `main` en `a5ddc62` | CONFIRMADO; no sincronizar ni desplegar hasta completar auditoría |
| 2026-11-23 | Hash de archivos del contenedor | COMPLETADO: cinco hashes SHA-256 coinciden entre host y contenedor; el usuario no privilegiado `10001` no podía leer los archivos, root sí |
| 2026-11-23 | Diferencia 189/187 herramientas | RESUELTO: 189 decoradores, 187 nombres únicos; dos herramientas registradas dos veces |
| 2026-11-23 | Versionado del paquete inconsistente | CORREGIDO EN FEATURE: `src/homelabpilot/__init__.py` alineado con `pyproject.toml` en `0.5.0` (commit `63804d6`). Pendiente ampliar la estrategia de versionado al completar desarrollo |
| 2026-11-23 | Proxy read-only | CORREGIDO EN FEATURE: sustituida la regex por allowlist exacta de 148 nombres revisados; las nuevas herramientas quedan denegadas por defecto. Incluye lecturas Seanime, Questarr, Frigate y estado Recyclarr; las operaciones de escritura/preview/confirmación siguen excluidas. |
| 2026-11-23 | Cobertura CI | Workflow 337 de GitHub Actions para `main`/`a5ddc62`: `success`; la rama de desarrollo aún no ha ejecutado CI |
| 2026-11-23 | Revisión estática del inventario MCP y proxy | Feature actual: 203 declaraciones `@mcp.tool`, 201 nombres únicos (dos duplicados conocidos). La allowlist read-only contiene 148; los 53 nombres restantes quedan bloqueados. De esos 53, 48 son mutaciones/acciones o previews/confirmaciones, 3 son APIs genéricas que pueden escribir (`arr_api_request`, `integration_api_request`, `scryer_graphql`), uno es helper puro (`collection_has_media_id`) y `flaresolverr_request_get` ejecuta POST pese al nombre. El proxy anterior mostraba 137 herramientas por patrón. `flaresolverr_request_get` no se aprueba: aunque el nombre termina en GET, realiza POST y no debe habilitarse por convención. Los duplicados `cleanuparr_get_health` y `maintainerr_get_health` se conservan como nombres publicados; su semántica está documentada en el inventario. |

## 8. Desarrollo iniciado — proxy MCP read-only

| Cambio | Estado | Detalle |
|---|---|---|
| Sustituir regex de nombres por allowlist exacta | COMPLETADO EN FEATURE | `mcp-readonly-policy.mjs`: 148 herramientas aprobadas explícitamente; las herramientas nuevas quedan denegadas por defecto. |
| Incorporar lecturas Seanime revisadas | COMPLETADO EN FEATURE | Allowlist read-only incluye estado, búsqueda, biblioteca, AniList, seguimiento, auditoría, inspección, unmatched files y lectura de ajustes redactados. `seanime_get_settings` es la nueva lectura añadida. |
| Proteger todas las escrituras Seanime | COMPLETADO EN FEATURE | Añadidos previews firmados y confirmación exacta para añadir AniList y reasignar archivos; cambios de preferencias booleanas de bajo riesgo protegidos con permiso `admin`, preview firmado y revalidación del valor. Las tres familias de mutación permanecen fuera del proxy read-only. |
| Revisar semántica de herramientas Seanime permitidas | COMPLETADO EN FEATURE | `seanime_search_anime` usa POST contra un endpoint de búsqueda de AniList sin mutación; `seanime_get_settings` es GET y redacta credenciales; `seanime_verify_reassignment` consulta archivos locales; `seanime_audit_library` e `seanime_inspect_entry` solo leen datos. No se detectan efectos de escritura en estas herramientas. |
| Revisar semántica de herramientas ARR y qBittorrent permitidas | COMPLETADO EN FEATURE | Las 11 herramientas ARR/qBittorrent incluidas en este grupo usan métodos GET; no se detectan mutaciones. |
| Revisar POST de consulta de Tdarr | COMPLETADO EN FEATURE | `tdarr_search_files` (`/api/v2/search-db`) y `tdarr_list_job_reports` (`/api/v2/client/jobs`) usan POST para búsquedas/listados; no modifican trabajos ni archivos. Las herramientas de requeue/rescan siguen fuera de la allowlist. |
| Revisar FlareSolverr | COMPLETADO EN FEATURE | `flaresolverr_list_sessions` usa POST `sessions.list` y es consulta. `flaresolverr_request_get` usa POST `request.get`, realiza una petición externa arbitraria y permanece fuera de la allowlist read-only (además requiere permiso `operations`). |
| Revisar Transmission RPC | COMPLETADO EN FEATURE | `session-get`, `session-stats` y `torrent-get` son los únicos métodos RPC tratados como lectura por `TRANSMISSION_READ_METHODS`; la herramienta genérica solo admite esos métodos y la allowlist no expone acciones de modificación. |
| Verificar herramientas genéricas con capacidad de escritura | COMPLETADO EN FEATURE | `arr_api_request`, `integration_api_request` y `scryer_graphql` permanecen fuera de la allowlist. Las dos primeras admiten controles/métodos mutantes bajo permisos; GraphQL puede ejecutar mutaciones y exige nivel admin. |
| Probar el handler real del proxy sin upstream real | COMPLETADO EN FEATURE | `tests/mcp-proxy.test.mjs`: escrituras Seanime/Tdarr bloqueadas antes de upstream, lectura permitida, Bearer inyectado, batch rechazado atómicamente y filtrado de `tools/list`. CI run 440 (`d68ddb7`) superado. |
| Filtrar `tools/list` en respuestas JSON-RPC batch | COMPLETADO EN FEATURE | Filtro compartido para respuestas individuales y arrays; incluye transporte JSON y SSE. |
| Rechazar batches que contengan llamadas no aprobadas | COMPLETADO EN FEATURE | El batch completo se rechaza para evitar ejecución parcial ambigua; las llamadas aprobadas individuales siguen su flujo normal. |
| Añadir pruebas Node.js de la política | COMPLETADO EN FEATURE | `tests/proxy-policy.test.mjs`; comprueba allowlist, denegación por defecto, filtrado simple/batch y que los nuevos cambios Seanime no exponen escrituras. |
| Incluir módulo en imagen del proxy y CI | COMPLETADO EN FEATURE | Dockerfile copia el módulo; workflow ejecuta `node --test` y se activa también en la rama feature. |
| Ejecutar CI de la rama y desplegar proxy | PARCIAL | CI run 405 completado con `success`; también pasaron runs 403–405 tras corregir el chequeo de allowlist en previews Docker. Suite pytest, Node policy tests y sintaxis del JavaScript embebido superados. Pendiente E2E, despliegue y validación real; no se ha reiniciado ningún contenedor. |

## 9. Protocolo obligatorio de trabajo

1. **Al iniciar o retomar:** leer la versión de este archivo en la rama `main` de GitHub. No confiar en una copia antigua de una conversación.
2. Identificar la primera tarea PENDIENTE de la fase activa y sus dependencias.
3. Ejecutar una comprobación o cambio cada vez y esperar el resultado antes de avanzar.
4. Marcar COMPLETADO solo cuando exista evidencia verificable. Usar PARCIAL si solo se ha validado una parte y BLOQUEADO si no se puede continuar.
5. Añadir al registro fecha, comprobación y resultado relevante.
6. No repetir pruebas COMPLETADAS salvo que haya cambios posteriores que puedan invalidarlas o una incidencia que lo justifique.
7. No saltar a otra fase mientras queden tareas abiertas en la fase actual, salvo excepción explícita documentada.
8. Durante Prioridad 1, limitarse a auditar: no cambiar código, configuración ni desplegar.
9. Cuando se autoricen cambios, probarlos, actualizar este documento y subir ambos cambios a GitHub.
10. Al finalizar cada sesión, dejar el estado y el siguiente paso reflejados aquí.

**Estados permitidos:** PENDIENTE · EN CURSO · COMPLETADO · PARCIAL · BLOQUEADO.

**Siguiente paso:** revisar permisos efectivos del resto del inventario MCP y la autenticación/aislamiento de entrada del proxy; después preparar E2E del proxy desplegado. No desplegar ni invocar escrituras reales hasta autorización explícita del usuario.


## 9. Correcciones detectadas durante el despliegue de prueba

| Hallazgo | Corrección en feature | Validación |
|---|---|---|
| Radarr, Sonarr y Prowlarr aparecían conectados con cero herramientas porque el inventario solo asociaba herramientas con prefijo del servicio. | Asignación explícita de las herramientas compartidas `arr_*` a cada aplicación compatible; Prowlarr incluye API genérica y operaciones de configuración. | Tests de inventario para Radarr, Sonarr y Prowlarr. |
| qBittorrent mostraba `Versión [object Object]` porque la API devuelve texto plano envuelto por `_decode_response`. | `stack_status` extrae el campo `text` y publica una versión escalar; la interfaz también trata versiones estructuradas de forma defensiva. | Test de versión qBittorrent `v5.1.2`. |
| Integraciones sin versión mostraban una segunda línea «Conectado» debajo del indicador de estado. | La tarjeta solo presenta una línea secundaria cuando existe versión o nombre de aplicación. | Renderizado frontend corregido; pendiente validación visual en el servidor. |

| 2026-11-23 | Correcciones de inventario y presentación del panel | CI run 450 (`c4c6bf7`) `success`: 148 tests Python, validación de JavaScript y pruebas del proxy superadas. |
| 2026-11-23 | Panel Home Assistant: detalle e historial de entidades | CI run 455 (`64da436`) `success`: suite Python, compilación y comprobación JavaScript superadas; incluye pruebas de entidad válida/inválida e historial con zona horaria. |
