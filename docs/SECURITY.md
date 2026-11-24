# Seguridad y permisos

HomeLabPilot puede ejecutar operaciones sobre servicios del homelab y debe tratarse como una aplicación con acceso sensible a la infraestructura. La seguridad se aplica en el servidor; ocultar un botón en la interfaz no sustituye la autorización del backend.

## Niveles de permiso MCP

Configura `HOMELABPILOT_MCP_PERMISSION_LEVEL` en el archivo privado `.env`:

- **`read`:** consultas de estado, bibliotecas, colas, lanzamientos, torrents y configuración. Bloquea escrituras.
- **`operations`:** permite las operaciones habituales habilitadas por cada integración, como añadir títulos, seleccionar lanzamientos y controlar descargas.
- **`admin`:** añade cambios de configuración y operaciones sensibles. Las eliminaciones y acciones de riesgo utilizan flujos específicos de previsualización y confirmación.

Los permisos se validan en el servidor. Los cambios de nivel requieren recrear el contenedor para aplicar la configuración.

## Previsualizaciones y confirmaciones

Las operaciones sensibles deben utilizar una previsualización vigente y una confirmación explícita. Los previews firmados vinculan la confirmación a una instantánea de la solicitud y permiten rechazar datos obsoletos o alterados. Algunas integraciones añaden allowlists, límites de cantidad o frases de confirmación exactas.

El nivel de permiso no sustituye la aprobación del usuario para una acción irreversible. No ejecutes pruebas destructivas sobre datos reales.

## Credenciales, configuración y sesiones

- Mantén `.env` fuera del repositorio y no compartas sus credenciales.
- Usa contraseñas largas y únicas para el panel.
- El token MCP es independiente de las credenciales del panel web.
- Las claves API permanecen en el servidor y se redactan en las respuestas.
- La configuración persistente del catálogo se cifra en el volumen `/data`. Define una clave estable `HOMELABPILOT_CONFIG_ENCRYPTION_KEY`; protégela y conserva una copia segura, porque perderla puede impedir descifrar la configuración guardada.
- La interfaz utiliza una cookie de sesión HttpOnly y controles de origen cruzado.
- No incluyas tokens, cookies, contraseñas ni claves API en capturas, logs o informes de auditoría.

## Red y contenedores

- Compose publica el servicio web/MCP en loopback por defecto.
- Para acceso LAN, configura `HOMELABPILOT_BIND_ADDRESS=0.0.0.0`.
- No publiques el puerto directamente en Internet. Para acceso remoto utiliza una VPN privada o una capa HTTPS de confianza.
- Las URL de los servicios deben ser accesibles desde el contenedor de HomeLabPilot.
- El contenedor principal se ejecuta sin privilegios de root, con capacidades reducidas y sistema de archivos de solo lectura, según la configuración Compose.

## Proxy MCP de solo lectura y agentes

El proxy MCP de agentes aplica una allowlist exacta de herramientas de lectura y deniega por defecto las herramientas no aprobadas. Las operaciones de escritura, preview y confirmación no deben exponerse a través de este proxy.

En Compose, el proxy no publica puertos y se conecta a la red Docker `agent_control`, declarada `internal: true`. Esa red se comparte con HomeLabPilot y el gateway de agentes; el gateway conserva salida externa mediante la red `default`. La comunicación proxy → MCP principal utiliza autenticación Bearer.

El contenedor de agentes no monta el socket Docker del host ni las carpetas multimedia. El modo sandbox de solo lectura de Codex es una capa adicional y no sustituye la política del proxy.

## Gateway Docker opcional

La gestión Docker está desactivada por defecto y se habilita mediante el perfil Compose opcional. Cuando se activa, el gateway usa una lista explícita de contenedores permitidos y limita las operaciones a listar, iniciar, detener y reiniciar. Las operaciones requieren permisos y confirmación. El socket Docker sigue siendo un recurso altamente sensible.

## Alcance de la validación

Las reglas anteriores describen el código y la configuración versionados. No implican que la topología, los permisos efectivos o la conectividad hayan sido verificados en el servidor del usuario tras el último cambio. Esa comprobación corresponde a la campaña de validación de `docs/VALIDACION_FINAL.md`.
