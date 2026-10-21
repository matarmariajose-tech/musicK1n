# Despliegue de K1N

## Preparación
El repositorio contiene un servicio Docker con Node 24, Python 3 y FFmpeg. Incluye interfaz web protegida, agente eve, SQLite y un worker único. No requiere un segundo servicio de worker. Usar una sola instancia; no habilitar autoscaling con este SQLite.

1. En Render, crear Web Service desde este repositorio y elegir Docker, rama main.
2. Montar un disco durable en `/data` para conservar audios, clips, SQLite y workflows. Este despliegue necesita un plan compatible con disco; revisar costo antes de crear recursos. No se ha autorizado un plan pago.
3. Configurar `K1N_USERNAME`, `K1N_PASSWORD` (contraseña larga), `AI_GATEWAY_API_KEY` y `TOKEN_ENCRYPTION_KEY` (secreto aleatorio de al menos 32 caracteres). Guardarlos en Environment, no en Git.
4. Configurar `PUBLIC_URL` con el origen HTTPS del servicio, sin barra final. El contenedor usa `K1N_DATA_DIR=/data` y el puerto de Render.
5. Health check: `/eve/v1/health`. Abrir `/` e ingresar usuario y contraseña.

No usar el plan gratuito con almacenamiento efímero como despliegue definitivo: perdería datos al reemplazar el contenedor. Para un despliegue sin disco se debe implementar otro backend de persistencia; este código no lo incluye.

## Conectar YouTube
Crear un proyecto en Google Cloud y habilitar YouTube Data API v3 y YouTube Analytics API. Configurar pantalla de consentimiento y un cliente OAuth de aplicación web. Agregar tu cuenta como usuario de prueba si corresponde.

Registrar el redirect exacto `https://TU-SERVICIO/oauth/google/callback`. Cargar `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` en Render. Cargar `YOUTUBE_CHANNEL_ID` con el id UC… del canal (no el handle @k1n___); se verifica antes de guardar permisos, sincronizar métricas o subir videos. Luego hacer click en Conectar mi canal desde Resultados.

El refresh token se guarda cifrado en el disco usando `TOKEN_ENCRYPTION_KEY`. Conservar esa clave en un gestor de secretos; cambiarla sin migrar el token requiere volver a autorizar. Google puede imponer límites de cuota, revisión de aplicación y expiración del permiso de prueba. Se deben verificar esos límites para tu proyecto.

Las subidas requieren clip revisado, aprobación y confirmación explícita. Se suben como **privadas**. Abrir Studio para hacer la revisión editorial, configurar el video relacionado y publicar. La interfaz distingue uploaded-private de published. No se publican automáticamente al público.

## Spotify
Para importar el catálogo público: crear una aplicación en Spotify Developer Dashboard y cargar `SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET`. El acceso está sujeto a los permisos y restricciones de tu aplicación. No usa Spotify para reproducir canciones. Las métricas de Spotify for Artists deben exportarse y normalizarse en el formato CSV de la interfaz; no existe un conector de Analytics for Artists aquí. No atribuir streams de canciones a clips sin evidencia.

## Uso y validación
Cargar una canción y portada, crear un segmento de 5–60 segundos, generar clip, esperar al worker, descargar y revisar, aprobar. Subir privado con confirmación o publicar manualmente y vincular el id.

Pruebas: `npm run typecheck`, `npm run build`, `npm test`, `npm run test:http`. Para desarrollo local instalar ffmpeg, ffprobe y cryptography, exportar las variables y ejecutar `node launcher.mjs` después de compilar. La prueba HTTP usa una copia temporal del proyecto y termina el servidor y el worker que inicia.

El framework prepara un sandbox durante el build. La compilación local se verificó con Docker disponible; no se verificó la construcción del Dockerfile en Render. No asumir que un contenedor de build puede acceder al daemon Docker: el proveedor de sandbox debe ser compatible con el entorno elegido antes de desplegar.

`K1N_MODEL` selecciona el modelo y `K1N_MODEL_CONTEXT_TOKENS` fija el presupuesto de contexto usado por el framework, con 32.000 tokens por defecto. Se leen al compilar. Al cambiar de modelo, ajustar ese presupuesto a sus límites y volver a ejecutar el build. Sin `AI_GATEWAY_API_KEY`, el panel usa reglas y no invoca el modelo.

Los contactos quedan como borradores. El agente lee el catálogo y métricas, no tiene herramientas que publiquen ni envíen mensajes. No hay pauta automática, compra de views, scheduler de marketing ni integración TikTok/Instagram. Las variantes gráficas actuales son portada y onda sonora; aún no hay subtítulos de letra ni edición visual con IA.

## Operación
Al abrir una base existente, se agrega `cover_id` a los experimentos sin eliminar registros. Los experimentos antiguos con formato de portada conservan sus clips; antes de volver a renderizarlos, el panel exige seleccionar una imagen explícitamente. No se les asigna la última portada cargada.

Una subida privada puede registrarse como publicada después de la revisión manual en Studio. Debe conservar el mismo identificador de YouTube. Repetir la confirmación no duplica el evento de auditoría; una subida pendiente o en curso bloquea esa confirmación.

Respaldar `/data`, incluida la base SQLite de forma coherente (SQLite backup API). Un solo worker toma un lock de proceso. Al reiniciar, los renders interrumpidos se marcan fallidos y se reencolan manualmente. Subidas reintentan la misma sesión resumible; una sesión expirada exige revisión para evitar duplicados. No borrar el registro de subida sin consultar Studio.

La interfaz acepta hasta 50 MiB por archivo. Usa autenticación HTTP Basic sobre HTTPS; es un panel de un solo operador. No ofrece cuentas múltiples. FFmpeg se ejecuta con límites de duración y timeout; para procesar archivos de usuarios no confiables se necesitaría aislamiento adicional. Los endpoints externos reales deben verificarse después de configurar cuentas: las pruebas locales no reemplazan una prueba de OAuth y subida real.

## Arranque sin claves ni audios
El panel empieza con el álbum en YouTube y tres textos listos para compartir. El asistente devuelve un plan fijo identificado como reglas cuando no hay clave de IA. No finge usar un modelo ni escuchar el álbum. Los uploads, OAuth y Spotify API son opcionales para esta modalidad.
