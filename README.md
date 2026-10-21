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
python3 -m unittest discover -s tests -v
```

Después de compilar y configurar el entorno, iniciar el servidor y el worker:

```bash
node launcher.mjs
```

## Arquitectura

| Componente | Responsabilidad |
| --- | --- |
| `agent/` | Rutas HTTP, autenticación y herramientas del asistente |
| `core/` | Reglas del flujo, SQLite, procesamiento de clips e integraciones externas |
| `web/` | Panel de trabajo y página pública del disco |
| `tests/` | Pruebas del flujo, renderizado y adaptadores de integración |

El despliegue utiliza una sola instancia con almacenamiento persistente. El servidor y el worker se supervisan desde `launcher.mjs`; la configuración actual no admite escalar horizontalmente.

## Estado y alcance

El proyecto todavía no se desplegó ni se validó con cuentas reales. Las pruebas locales cubren renderizado con FFmpeg y adaptadores simulados; no sustituyen una validación de OAuth, métricas o subida con los servicios externos.

Las subidas a YouTube son privadas y requieren aprobación y confirmación explícitas. La publicación pública se realiza manualmente desde YouTube Studio.

No incluye campañas pagadas, investigación autónoma de contactos, envío de mensajes, subtítulos ni integración con TikTok o Instagram.
