# K1N Growth Studio

Herramienta para organizar campañas musicales de K1N / B.R.I.S.T.O.L., generar clips verticales y registrar sus resultados.

El flujo conecta canciones, experimentos de promoción y métricas: cargar audio y portada, generar un clip, revisarlo y aprobar su subida privada a YouTube. También permite empezar con enlaces existentes, sin cargar archivos ni conectar cuentas externas.

## Funcionalidades

- Panel web con acceso protegido para un operador.
- Persistencia en SQLite y procesamiento de clips con FFmpeg en un worker separado.
- Revisión y aprobación antes de la subida a YouTube.
- Conexión mediante Google OAuth, almacenamiento cifrado del refresh token y subida reanudable de videos privados.
- Consulta de YouTube Analytics, importación de métricas CSV y seguimiento de borradores de contacto.
- Consulta del catálogo público de Spotify y página pública del disco en `/listen`.

El asistente admite un modelo externo mediante `AI_GATEWAY_API_KEY`. Sin esa configuración, ofrece un plan basado en reglas y lo identifica en la interfaz.

## Desarrollo y verificación

Requiere Node.js 24, Python 3, FFmpeg, FFprobe y el paquete Python `cryptography`. Consultar [DEPLOY.md](DEPLOY.md) para configurar las variables de entorno, las cuentas externas y el almacenamiento.

Desde la raíz del repositorio, con los requisitos instalados:

```bash
npm ci
npm run typecheck
npm run build
npm test
npm run test:http
```

Después de compilar y configurar el entorno, iniciar el servidor y el worker:

```bash
node launcher.mjs
```

`npm test` ejecuta 17 pruebas del motor y las integraciones, incluido un render real y callbacks OAuth concurrentes. `npm run test:http` inicia una copia temporal del servidor, comprueba sus rutas y termina sus procesos. Usa datos y credenciales de prueba; no conecta cuentas externas.

El build prepara un sandbox del framework y requiere un proveedor compatible; la verificación local se realizó con Docker. El modelo y su presupuesto de contexto se configuran antes de compilar mediante `K1N_MODEL` y `K1N_MODEL_CONTEXT_TOKENS`. El presupuesto predeterminado es de 32.000 tokens y debe ser compatible con el modelo elegido. El modo basado en reglas no requiere una clave de modelo.

## Arquitectura

| Componente | Responsabilidad |
| --- | --- |
| `agent/` | Rutas HTTP, autenticación y herramientas del asistente |
| `core/engine.py` | Entrada RPC y coordinación de las acciones del panel |
| `core/experiments.py` | Selección de portada, cola de render y registro de publicación |
| `core/storage.py` | Conexión SQLite, evolución del esquema y auditoría |
| `core/assets.py` / `core/rendering.py` | Validación de archivos y procesamiento con FFmpeg |
| `core/worker.py` | Ejecución de trabajos y recuperación tras reinicios |
| `core/oauth.py` / `core/integrations.py` | Autorización y adaptadores de servicios externos |
| `web/` | Panel de trabajo y página pública del disco |
| `tests/` | Pruebas del flujo, renderizado y adaptadores de integración |

El despliegue utiliza una sola instancia con almacenamiento persistente. El servidor y el worker se supervisan desde `launcher.mjs`; la configuración actual no admite escalar horizontalmente.

## Estado y alcance

El proyecto todavía no se desplegó ni se validó con cuentas reales. Las pruebas locales cubren renderizado con FFmpeg y adaptadores simulados; no sustituyen una validación de OAuth, métricas o subida con los servicios externos.

Las subidas a YouTube son privadas y requieren aprobación y confirmación explícitas. La publicación pública se realiza manualmente desde YouTube Studio.

Cada experimento con formato de portada conserva el archivo seleccionado. Cargar otra imagen no cambia los clips existentes. Después de publicar manualmente en Studio, el panel permite registrar la publicación con el mismo identificador del video; esa confirmación no comprueba su visibilidad en YouTube.

No incluye campañas pagadas, investigación autónoma de contactos, envío de mensajes, subtítulos ni integración con TikTok o Instagram.
