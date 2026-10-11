# K1N Growth Studio

Panel web protegido y agente musical para K1N / B.R.I.S.T.O.L.

Flujo: audio y portada → canciones → experimentos → clips verticales → revisión → subida privada YouTube → resultados → siguiente experimento.

Implementado: carga de archivos, SQLite durable, FFmpeg en worker, aprobaciones, OAuth Google cifrado, adaptadores de YouTube Analytics y upload resumible privado, catálogo público Spotify, CSV de métricas y CRM de borradores.

No se ha desplegado ni conectado a cuentas. No hay autopublicación pública, pauta, investigación autónoma de contactos, subtítulos ni integración TikTok/Instagram.

Ver DEPLOY.md para requisitos, configuración, limitaciones y operación.

Validación: npm run typecheck; npm run build; python3 -m unittest discover -s tests -v.
