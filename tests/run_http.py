import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    project = Path(__file__).resolve().parents[1]
    if not (project / ".output/server/index.mjs").is_file():
        raise RuntimeError("Ejecutá npm run build antes de la prueba HTTP")
    with tempfile.TemporaryDirectory(prefix="k1n-http-") as temporary:
        workspace = Path(temporary)
        for name in ("agent", "core", "web"):
            shutil.copytree(
                project / name,
                workspace / name,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        shutil.copytree(
            project / ".eve",
            workspace / ".eve",
            ignore=shutil.ignore_patterns(".workflow-data"),
        )
        shutil.copytree(project / ".output", workspace / ".output")
        for name in (
            "package.json",
            "package-lock.json",
            "launcher.mjs",
            "campaign.json",
            "catalog.json",
        ):
            shutil.copy2(project / name, workspace / name)
        (workspace / "node_modules").symlink_to(
            project / "node_modules", target_is_directory=True
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                ("GOOGLE_", "SPOTIFY_", "YOUTUBE_", "K1N_", "AI_GATEWAY_")
            )
            and key not in ("TOKEN_ENCRYPTION_KEY", "PUBLIC_URL")
        }
        environment.update(
            {
                "PORT": str(port),
                "K1N_USERNAME": "test-operator",
                "K1N_PASSWORD": "local-test-password",
                "K1N_DATA_DIR": str(workspace / "data"),
                "K1N_PROJECT_ROOT": str(workspace),
                "K1N_TEST_URL": base,
                "PUBLIC_URL": base,
            }
        )
        with (workspace / "server.log").open("w+") as log:
            server = subprocess.Popen(
                ["node", "launcher.mjs"],
                cwd=workspace,
                env=environment,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        raise RuntimeError("El servidor terminó antes de iniciar")
                    try:
                        with urllib.request.urlopen(
                            base + "/eve/v1/health", timeout=1
                        ) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.2)
                else:
                    raise TimeoutError("El servidor no inició a tiempo")
                subprocess.run(
                    [sys.executable, str(project / "tests/http_smoke.py")],
                    cwd=workspace,
                    env=environment,
                    check=True,
                    timeout=90,
                )
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read()[-3000:], file=sys.stderr)
                raise
            finally:
                try:
                    os.killpg(server.pid, signal.SIGTERM)
                    server.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait(timeout=5)
                except ProcessLookupError:
                    server.wait(timeout=5)


if __name__ == "__main__":
    main()
