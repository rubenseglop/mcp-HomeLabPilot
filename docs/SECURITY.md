# Seguridad y permisos

HomeLabPilot puede ejecutar operaciones sobre servicios multimedia y, por tanto, debe tratarse como una aplicación con acceso sensible a la infraestructura.

## Niveles de permiso MCP

Configura `HOMELABPILOT_MCP_PERMISSION_LEVEL` en el archivo privado `.env`:

- **`read`:** consultas de estado, bibliotecas, colas, lanzamientos, torrents y configuración. Bloquea escrituras.
- **`operations`:** nivel predeterminado. Permite operaciones habituales, como añadir títulos, seleccionar lanzamientos y controlar descargas.
- **`admin`:** añade cambios de configuración y operaciones sensibles. Las eliminaciones utilizan flujos específicos de previsualización y confirmación.

Los permisos se validan en el servidor. Los cambios en el nivel requieren recrear el contenedor.

## Confirmaciones

Las operaciones destructivas o sensibles deben utilizar una previsualización actual y una confirmación explícita. Los tokens de previsualización están vinculados a una instantánea de la solicitud para rechazar confirmaciones obsoletas.

No se debe interpretar el nivel de permiso como sustituto de la aprobación del usuario para una acción irreversible.

## Credenciales y sesiones

- Mantén `.env` fuera del repositorio y no compartas sus credenciales.
- Usa contraseñas largas y únicas para el acceso web.
- El token MCP es independiente de las credenciales de acceso al panel.
- Las claves API permanecen en el servidor y se omiten de las respuestas.
- La configuración persistente se cifra en el volumen de datos. Define una `HOMELABPILOT_CONFIG_ENCRYPTION_KEY` estable.
- La interfaz web utiliza una cookie de sesión HttpOnly y protección frente a solicitudes de origen cruzado.

## Red y contenedores

- Compose publica el servicio en loopback por defecto.
- Para acceder desde la LAN, configura `HOMELABPILOT_BIND_ADDRESS=0.0.0.0`.
- No publiques el puerto directamente en Internet. Para acceso remoto utiliza una VPN privada, como Tailscale, o una capa HTTPS de confianza.
- Las URL de los servicios deben ser accesibles desde el contenedor de HomeLabPilot.
- El contenedor principal se ejecuta sin privilegios de root, con capacidades reducidas y sistema de archivos de solo lectura.

## Proxy MCP de solo lectura y agentes

El proxy MCP de agentes publica una lista permitida exacta de herramientas de consulta y bloquea por defecto herramientas de escritura, confirmación y mutación de API. No publica ningún puerto y se conecta únicamente a la red Docker `agent_control`, declarada `internal: true`; esa red solo la comparten HomeLabPilot, el proxy y el gateway de agentes. El gateway mantiene su salida externa mediante la red `default`. La comunicación proxy → MCP principal usa el token Bearer configurado. El contenedor de agentes no monta el socket Docker del host ni las carpetas multimedia.

Codex se ejecuta en modo sandbox de solo lectura. Estas capas son independientes: el modo de solo lectura del agente no sustituye los controles del proxy.

## Gateway Docker opcional

La gestión Docker está desactivada por defecto. Si se habilita, utiliza un gateway separado con una lista explícita de contenedores permitidos y operaciones limitadas a listar, iniciar, detener y reiniciar. El socket Docker sigue siendo un recurso sensible; activa esta función únicamente en un host de confianza.


La topología de red descrita corresponde a la configuración de Compose de la rama feature. Debe comprobarse en ejecución durante la campaña final de validación, después del despliegue autorizado.
