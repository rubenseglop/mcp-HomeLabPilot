# Campaña única de validación final — HomeLabPilot

Este documento es una lista de aceptación para ejecutar **después de completar el desarrollo**. No ejecutar ahora. El despliegue requiere autorización expresa del usuario.

## 1. Preparación y seguridad

- [ ] Confirmar rama `feature/complete-homelabpilot` y commit candidato.
- [ ] Confirmar que `main` sigue intacta y que no hay cambios locales que puedan perderse.
- [ ] Revisar el diff completo feature frente a main.
- [ ] Revisar `.env` sin imprimir ni copiar secretos; comprobar únicamente presencia de variables necesarias.
- [ ] Confirmar copia/rollback de imágenes y volúmenes antes del despliegue.
- [ ] Revisar configuración Compose y perfiles opcionales.
- [ ] Desplegar solo tras autorización expresa.

## 2. Integridad del despliegue

- [ ] Confirmar estado de todos los contenedores y healthchecks.
- [ ] Comparar commit desplegado con el commit candidato.
- [ ] Comparar hashes de los archivos críticos entre checkout y contenedor.
- [ ] Confirmar que el puerto MCP principal solo se publica en la interfaz configurada.
- [ ] Confirmar que el proxy no publica puertos y que `agent_control` es una red interna.
- [ ] Confirmar que solo HomeLabPilot, el proxy y el gateway de agentes participan en `agent_control`.
- [ ] Confirmar que el gateway conserva salida externa por `default`.
- [ ] Confirmar que `docker_control` es interna y que el gateway Docker solo se activa con el perfil opcional.

## 3. MCP, autenticación y catálogo

- [ ] Ejecutar `initialize` y `tools/list` contra el MCP principal.
- [ ] Registrar número y nombres únicos de herramientas publicadas.
- [ ] Confirmar que no existen registros duplicados.
- [ ] Probar token ausente, incorrecto y correcto.
- [ ] Ejecutar `tools/list` a través del proxy y comparar con la allowlist.
- [ ] Ejecutar una consulta permitida a través del proxy.
- [ ] Confirmar que las herramientas de escritura, preview y confirmación no aparecen en el proxy.
- [ ] Intentar una llamada bloqueada no destructiva y comprobar rechazo antes del upstream.
- [ ] Comprobar batches JSON-RPC y transporte SSE.
- [ ] Comprobar conexión real de Codex, Claude y Gemini solo si están configurados.
- [ ] Comprobar historial de operaciones y redacción de secretos.

## 4. Integraciones principales

Para cada servicio configurado, registrar conectado/no configurado, versión disponible, herramientas publicadas y resultado de una consulta inocua.

- [ ] Radarr, Sonarr y Lidarr.
- [ ] Prowlarr y Bazarr.
- [ ] qBittorrent y Transmission.
- [ ] Plex y Jellyfin.
- [ ] Seerr.
- [ ] Scryer.
- [ ] Seanime.
- [ ] Immich y RomM.
- [ ] Tdarr.
- [ ] Home Assistant.
- [ ] Questarr y Frigate.
- [ ] Recyclarr y Docker Gateway.
- [ ] BookOrbit, Youtarr y Tidarr.
- [ ] Pulsarr, Agregarr, Cleanuparr y Maintainerr.
- [ ] Tracearr y Cloudflare.
- [ ] FlareSolverr y tinyMediaManager.
- [ ] PostgreSQL y Redis, si están configurados.

## 5. Panel web

- [ ] Inicio de sesión, cierre de sesión y persistencia de sesión.
- [ ] Catálogo de aplicaciones: estados, configuración y herramientas por servicio.
- [ ] Consultas de lectura en los 22 paneles adicionales.
- [ ] Paneles nativos ARR, Scryer y qBittorrent.
- [ ] Formularios de configuración y almacenamiento cifrado de credenciales.
- [ ] Presentación de errores, resultados extensos, paginación y límites.
- [ ] Diseño responsive en escritorio y móvil.

## 6. Permisos y escrituras protegidas

- [ ] Matriz de herramientas: nombre, servicio, método/endpoint, permiso mínimo y efecto lateral.
- [ ] Probar nivel `read`: toda escritura bloqueada.
- [ ] Probar nivel `operations`: solo operaciones permitidas.
- [ ] Probar nivel `admin`: operaciones administrativas previstas.
- [ ] Revisar cada preview: alcance, caducidad, firma y datos mostrados.
- [ ] Rechazar confirmaciones caducadas, alteradas, reutilizadas o con frase incorrecta.
- [ ] Verificar allowlists de servicios y contenedores.
- [ ] No ejecutar borrados ni acciones irreversibles durante la aceptación; usar mocks o recursos de prueba.

## 7. Pruebas automatizadas y cierre

- [ ] Ejecutar suite Python completa.
- [ ] Ejecutar suite Node del proxy y políticas.
- [ ] Ejecutar compilación/validación de módulos Python.
- [ ] Ejecutar validación de JavaScript embebido y assets.
- [ ] Ejecutar validación de Docker Compose.
- [ ] Corregir incidencias y repetir únicamente las suites afectadas y la batería final.
- [ ] Actualizar versión del proyecto y changelog.
- [ ] Generar documentación del catálogo real de herramientas.
- [ ] Crear release candidate y registrar hashes.
- [ ] Obtener aprobación del usuario.
- [ ] Integrar feature en `main` mediante el método acordado (squash/commit único).
- [ ] Desplegar la versión aprobada y verificar salud posterior.

## Reglas

1. No imprimir secretos ni incluirlos en logs, capturas o informes.
2. No ejecutar operaciones destructivas sobre datos reales.
3. No tocar `main` ni desplegar sin autorización.
4. Registrar resultados con fecha, commit, servicio y evidencia.
5. Si una integración no está configurada, marcarla como no aplicable; no considerarla fallida.
