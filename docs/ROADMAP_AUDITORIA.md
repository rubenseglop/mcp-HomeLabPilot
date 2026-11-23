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
| Aclarar diferencia respecto a las 189 previstas | COMPLETADO | 189 declaraciones `@mcp.tool`, 187 nombres únicos por dos nombres duplicados; coincide con `tools/list` (187) |
| Revisar herramientas duplicadas, ausentes o inesperadas | PARCIAL | Confirmados dos nombres duplicados (`cleanuparr_get_health`, `maintainerr_get_health`); las dos versiones consultan el mismo endpoint GET. Clasificación estática del proxy: 133 nombres permitidos y 54 bloqueados; entre los bloqueados hay lecturas legítimas de Seanime (`seanime_search_anime`, `seanime_verify_reassignment`, `seanime_audit_library`, `seanime_inspect_entry`) y el helper puro `collection_has_media_id`. Pendiente comparar el inventario completo con la lista runtime y cerrar clasificación de efectos |

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
| Ejecutar `tools/list` a través del proxy | COMPLETADO | 23-11-2026: initialize HTTP 200, sesión creada, tools/list HTTP 200, 137 herramientas visibles, sin error JSON-RPC. La cifra coincide con la antigua política por patrón; la nueva allowlist explícita añade tres lecturas Seanime revisadas (140 permitidas). Pendiente desplegar y verificar el nuevo resultado. |
| Ejecutar una herramienta de lectura a través del proxy | PENDIENTE | |
| Verificar bloqueo de herramientas de escritura en el proxy | PENDIENTE | Prueba negativa segura; no ejecutar ninguna escritura en servicios reales |
| Verificar que las lecturas siguen permitidas | PENDIENTE | |

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
| Questarr | PARCIAL | API de lectura y panel en catálogo con estado/biblioteca; credencial `read`, límites y pruebas unitarias. Pendiente CI del panel y validación real. |
| Frigate | PARCIAL | API de estadísticas/eventos/revisión y panel en catálogo; bearer JWT, solo lectura y paginación acotada. Pendiente CI del panel y validación real. |
| Recyclarr | PARCIAL | Estado del contenedor y ejecución fija `recyclarr sync` mediante Docker Gateway, limitada a contenedor configurado/allowlist y preview firmado con confirmación exacta. Añadido panel en catálogo; pendiente CI del panel y prueba real. |
| Docker Gateway | PARCIAL | Gateway limitado a lista explícita y start/stop/restart más comando fijo Recyclarr sync. Las acciones MCP requieren preview firmado y confirmación escrita; CI runs 353–363 pasaron. Las ejecuciones 364–373 detectaron errores en tests (import de pytest y secuencia esperada de llamadas); ambos corregidos en feature. Pendiente resultado de CI run 374 y revisión final del catálogo. |

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
| Plex | PENDIENTE |
| Jellyfin | PENDIENTE |
| Seerr | PENDIENTE |
| Immich | PENDIENTE |
| Tdarr | PENDIENTE |
| Home Assistant | PENDIENTE |
| RomM | PENDIENTE |
| Resto de aplicaciones, priorizadas por utilidad | PENDIENTE |

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

## 6. Registro de comprobaciones

| Fecha | Comprobación | Resultado |
|---|---|---|
| 2026-11-23 | Repositorio, rama y commit | Checkout del servidor `44985e1`; GitHub `main` `a5ddc62`; rama de trabajo creada desde GitHub `main` |
| 2026-11-23 | `stack_status` | 10/10 servicios configurados responden correctamente |
| 2026-11-23 | MCP `tools/list` | 187 herramientas; sin error JSON-RPC |
| 2026-11-23 | Proxy `/health` | HTTP 200; modo `read-only` |
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
| 2026-11-23 | Proxy read-only | ABIERTO: regex actual deja fuera consultas Seanime de verificación/auditoría; revisar semántica antes de ampliar allowlist |
| 2026-11-23 | Cobertura CI | Workflow 337 de GitHub Actions para `main`/`a5ddc62`: `success`; la rama de desarrollo aún no ha ejecutado CI |
| 2026-11-23 | Revisión estática del inventario MCP y proxy | 189 decoradores, 187 nombres únicos. El proxy anterior mostraba 137 herramientas por patrón. `flaresolverr_request_get` no se aprueba: aunque el nombre termina en GET, realiza POST y no debe habilitarse por convención. Los duplicados `cleanuparr_get_health` y `maintainerr_get_health` se conservan como nombres publicados; su semántica está documentada en el inventario. |

## 8. Desarrollo iniciado — proxy MCP read-only

| Cambio | Estado | Detalle |
|---|---|---|
| Sustituir regex de nombres por allowlist exacta | COMPLETADO EN FEATURE | `mcp-readonly-policy.mjs`: 140 herramientas aprobadas explícitamente; las herramientas nuevas quedan denegadas por defecto. |
| Incorporar lecturas Seanime revisadas | COMPLETADO EN FEATURE | Añadidas `seanime_audit_library`, `seanime_inspect_entry` y `seanime_verify_reassignment`; no se exponen herramientas de preview ni mutación. |
| Filtrar `tools/list` en respuestas JSON-RPC batch | COMPLETADO EN FEATURE | Filtro compartido para respuestas individuales y arrays; incluye transporte JSON y SSE. |
| Rechazar batches que contengan llamadas no aprobadas | COMPLETADO EN FEATURE | El batch completo se rechaza para evitar ejecución parcial ambigua; las llamadas aprobadas individuales siguen su flujo normal. |
| Añadir pruebas Node.js de la política | COMPLETADO EN FEATURE | `tests/proxy-policy.test.mjs`; comprueba allowlist, denegación por defecto y filtrado simple/batch. |
| Incluir módulo en imagen del proxy y CI | COMPLETADO EN FEATURE | Dockerfile copia el módulo; workflow ejecuta `node --test` y se activa también en la rama feature. |
| Ejecutar CI de la rama y desplegar proxy | PARCIAL | CI run 374 pasó tras corregir pruebas de Recyclarr. Los cambios posteriores de paneles y verificación de JavaScript embebido esperan CI. Pendiente CI limpio, despliegue y validación real; no se ha reiniciado ningún contenedor. |

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

**Siguiente paso:** ejecutar CI de la rama feature tras Questarr/Frigate, corregir cualquier fallo y continuar con Recyclarr y Docker Gateway. No desplegar ni pedir al usuario pruebas repetitivas hasta tener el bloque de cambios preparado.
