# K1N Growth Agent v0
Agente eve con herramientas locales para catálogo, propuestas y evaluación. No está desplegado ni conectado a cuentas.

Requiere Node 24, npm, Python 3 y credenciales de AI Gateway para conversación. Ejecutar desde el proyecto: `npm install` y `npm run dev`.

Sin LLM: `python3 core/growth.py plan`, `python3 core/growth.py evaluate` y `python3 core/growth.py import-metrics resultados.csv`.

Completar spotify_artist y spotify_album en catalog.json. tracks empieza vacío. Ejemplo de una entrada real a cargar: {"id":"tema-1","title":"Título real","duration_seconds":180,"segments":[{"start":40,"end":60}]}.

CSV: id,views,engaged,subscribers. Los ids se obtienen de evaluate. engaged representa espectadores que superan un umbral de retención fijo elegido por el operador, no automáticamente engaged views de YouTube. Importaciones reemplazan totales. Comparar siempre misma ventana y plataforma. El mínimo de 100 es operativo, no garantía estadística.

Spotify figura como destino configurable; no hay conector ni importador Spotify for Artists. Faltan también YouTube OAuth, extracción de audio, render de clips, publicación, pauta y scheduler. No hay contactos investigados ni mensajes enviados. El LLM prepara textos; las herramientas generan y evalúan registros.

SQLite se guarda localmente. Antes de desplegar se requiere almacenamiento durable y autenticación; el disco efímero de funciones no sirve para esta base.

## Despliegue preparado en contenedor
Dockerfile incluye Node 24 y Python; compila eve y escucha en 0.0.0.0:$PORT. Configurar AI_GATEWAY_API_KEY, K1N_USERNAME, K1N_PASSWORD y K1N_DB_PATH=/data/growth.sqlite. Montar volumen durable en /data; también conserva workflows. Un disco durable requiere un servicio compatible y puede tener costo; todavía no se provisionó. El agente ofrece API y REPL remoto, no tiene interfaz web propia. El proyecto aún no tiene remoto GitHub/GitLab/Bitbucket.
