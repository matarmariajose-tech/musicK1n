# Empezar con K1N Growth Studio

La guía de requisitos, funcionalidades y arquitectura está en [README.md](README.md).
La configuración del servicio y de las cuentas externas está en [DEPLOY.md](DEPLOY.md).

Con Node.js 24, Python 3, FFmpeg, FFprobe, `cryptography` y un proveedor de sandbox compatible instalados:

```bash
npm ci
npm run typecheck
npm run build
npm test
npm run test:http
```

Para usar el panel, configurar las variables de entorno indicadas en `.env.example` y ejecutar:

```bash
node launcher.mjs
```

El modo basado en reglas permite empezar con enlaces existentes, sin conectar cuentas externas ni configurar una clave de modelo. Las pruebas usan archivos y datos temporales; no suben videos a YouTube.
