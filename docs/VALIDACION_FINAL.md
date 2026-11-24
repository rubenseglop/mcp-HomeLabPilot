# Validación de HomeLabPilot

Este documento separa la validación del repositorio de la validación de la instalación real. La integración de funcionalidades en `main` ya se ha realizado; eso no significa que el despliegue local del usuario esté actualizado ni que todas las integraciones se hayan probado contra servicios reales.

## 1. Estado conocido del repositorio

- Rama principal: `main`.
- Commit de referencia auditado: `9b4d058bd6283ab67ad425f860d7ad3b0a12f2e2`.
- Último cambio integrado: navegación lateral compacta con grupos desplegables para Radarr, Sonarr, Lidarr y Scryer; Descargas conserva acceso directo.
- Inventario estático de herramientas MCP: 201 declaraciones únicas (`server.py`: 52, `integrations.py`: 131, `seanime.py`: 18).
- Catálogo de aplicaciones del panel: 32 entradas.
- Pruebas presentes: 147 funciones de prueba Python y 9 casos Node declarados en las suites del proxy/política. El script `check-web-script.mjs` es una comprobación adicional.
- CI de la PR de navegación: completada correctamente (run 45391666643). El estado de checks asociado al commit de merge de `main` no se ha confirmado en esta auditoría.

Estos recuentos son inventario del código fuente, no resultados de una ejecución local de todas las pruebas en el entorno del usuario.

## 2. Validación del repositorio

- [x] Confirmar repositorio y rama principal.
- [x] Confirmar commit de referencia y árbol de archivos.
- [x] Identificar los cinco documentos Markdown del repositorio.
- [x] Revisar el catálogo y las declaraciones de herramientas en el código.
- [x] Revisar la existencia y el alcance de las suites de pruebas.
- [x] Revisar la CI satisfactoria asociada a la PR de navegación lateral.
- [ ] Ejecutar de nuevo todas las suites sobre el commit actual de `main`.
- [ ] Validar `docker compose config` para los perfiles base y Docker.
- [ ] Generar inventario de herramientas MCP en runtime y compararlo con las 201 declaraciones estáticas.

## 3. Despliegue en el mediacenter

Pendiente de confirmar por el usuario. No asumir que GitHub y el checkout local están sincronizados.

- [ ] Confirmar commit local y estado limpio del checkout.
- [ ] Confirmar que el contenedor ejecuta el mismo commit/código.
- [ ] Confirmar estado y healthchecks de HomeLabPilot, proxy y gateway de agentes.
- [ ] Confirmar perfil opcional y estado del Docker Gateway.
- [ ] Confirmar que el panel responde y que la navegación compacta se muestra correctamente.
- [ ] Confirmar que los volúmenes y la configuración persistente permanecen intactos.

## 4. MCP, autenticación y proxy

- [ ] Ejecutar `initialize` y `tools/list` contra el MCP principal.
- [ ] Registrar número de herramientas y nombres únicos; detectar duplicados.
- [ ] Probar token ausente, incorrecto y correcto.
- [ ] Ejecutar `tools/list` a través del proxy y compararlo con su allowlist.
- [ ] Ejecutar una lectura inocua a través del proxy.
- [ ] Confirmar que las herramientas de escritura, preview y confirmación no se publican en el proxy.
- [ ] Probar rechazo de una llamada bloqueada no destructiva antes de alcanzar el upstream.
- [ ] Comprobar batches JSON-RPC y transporte soportado.
- [ ] Comprobar el agente CLI configurado y su acceso MCP de solo lectura.

## 5. Integraciones y panel web

Para cada servicio realmente configurado, registrar conectado/no configurado, versión si la API la facilita y resultado de una consulta inocua.

- [ ] Radarr, Sonarr, Lidarr, Prowlarr y Bazarr.
- [ ] qBittorrent y Transmission.
- [ ] Plex y Jellyfin.
- [ ] Seerr y Scryer.
- [ ] Seanime y Tdarr.
- [ ] Immich y RomM.
- [ ] Home Assistant, Frigate y Questarr.
- [ ] Recyclarr y Docker Gateway.
- [ ] BookOrbit, Youtarr, Tidarr y tinyMediaManager.
- [ ] Pulsarr, Agregarr, Cleanuparr y Maintainerr.
- [ ] Tracearr, Cloudflare y FlareSolverr.
- [ ] PostgreSQL y Redis, si están configurados.
- [ ] Revisar catálogo de 32 entradas y diferenciar integraciones activas, solo estado y soporte parcial.
- [ ] Comprobar formularios de configuración, cifrado, redacción de secretos y persistencia.
- [ ] Comprobar navegación lateral expandible, persistencia del estado y vista estrecha/móvil.

## 6. Permisos y escrituras protegidas

- [ ] Construir matriz de herramientas: nombre, servicio, efecto lateral y permiso mínimo.
- [ ] Probar nivel `read`: todas las escrituras bloqueadas.
- [ ] Probar nivel `operations`: solo operaciones permitidas.
- [ ] Probar nivel `admin`: operaciones administrativas previstas.
- [ ] Revisar expiración, firma, alcance y reutilización de previews.
- [ ] Rechazar previews caducados, alterados o con confirmación incorrecta.
- [ ] Verificar allowlists de servicios y contenedores.
- [ ] No ejecutar borrados ni acciones irreversibles sobre datos reales; utilizar mocks o recursos de prueba.

## 7. Cierre

- [ ] Ejecutar suite Python completa.
- [ ] Ejecutar suites Node del proxy y política.
- [ ] Ejecutar compilación/validación de módulos Python y JavaScript embebido.
- [ ] Validar Compose para los perfiles utilizados.
- [ ] Corregir incidencias y repetir las pruebas afectadas.
- [ ] Registrar fecha, commit, resultado y evidencia sin secretos.
- [ ] Actualizar esta documentación con resultados reales.

## Reglas

1. No imprimir ni almacenar secretos en informes.
2. No ejecutar acciones destructivas sobre datos reales durante la aceptación.
3. No considerar una integración no configurada como fallo; marcarla como no aplicable.
4. No afirmar que el servidor está actualizado hasta comparar el commit desplegado.
5. La CI y las pruebas unitarias no sustituyen la validación E2E.
