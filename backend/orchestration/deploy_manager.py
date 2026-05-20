import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

PROJECTS_DIR = Path.home() / "protopilot-projects"
PORT_RANGE_START = 5001
PORT_RANGE_END = 5999


class DeployManager:
    def __init__(self):
        self._port_registry: dict[str, int] = {}
        self._deploy_status: dict[str, str] = {}  # "building" | "running" | "failed"
        PROJECTS_DIR.mkdir(exist_ok=True)
        self._load_registry()
        self._restore_running_containers()

    def _registry_path(self) -> Path:
        return PROJECTS_DIR / "port_registry.json"

    def _load_registry(self):
        p = self._registry_path()
        if p.exists():
            self._port_registry = json.loads(p.read_text())

    def _save_registry(self):
        self._registry_path().write_text(json.dumps(self._port_registry))

    def _restore_running_containers(self):
        for project_id in list(self._port_registry.keys()):
            project_dir = PROJECTS_DIR / project_id
            if not project_dir.exists():
                self._free_port(project_id)
                continue
            result = subprocess.run(
                ["docker", "compose", "ps", "--services", "--filter", "status=running"],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
            )
            if "frontend" in result.stdout:
                self._deploy_status[project_id] = "running"
                print(f"[DEPLOY] Restored running state for {project_id}")

    def _allocate_port(self, project_id: str) -> int:
        if project_id in self._port_registry:
            return self._port_registry[project_id]
        used = set(self._port_registry.values())
        for port in range(PORT_RANGE_START, PORT_RANGE_END):
            if port not in used:
                self._port_registry[project_id] = port
                self._save_registry()
                return port
        raise RuntimeError("No available ports in range")

    def _free_port(self, project_id: str):
        self._port_registry.pop(project_id, None)
        self._save_registry()

    def _write_project_files(self, project_id: str, angular_files: dict, java_files: dict):
        project_dir = PROJECTS_DIR / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)
        project_dir.mkdir(parents=True)

        if angular_files:
            fe_dir = project_dir / "frontend"
            fe_dir.mkdir()
            for path, content in angular_files.items():
                fp = fe_dir / path
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")

        if java_files:
            be_dir = project_dir / "backend"
            be_dir.mkdir()
            for path, content in java_files.items():
                fp = be_dir / path
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")

    @staticmethod
    def _frontend_dockerfile() -> str:
        return """\
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build -- --configuration production

FROM nginx:alpine
COPY --from=build /app/dist /tmp/dist
RUN browser=$(find /tmp/dist -name "browser" -type d 2>/dev/null | head -1); \\
    if [ -n "$browser" ]; then cp -r "$browser/." /usr/share/nginx/html/; \\
    else cp -r $(find /tmp/dist -maxdepth 1 -mindepth 1 -type d | head -1)/. /usr/share/nginx/html/; fi && \\
    rm -rf /tmp/dist
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
"""

    @staticmethod
    def _nginx_conf() -> str:
        return """\
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8080/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
"""

    @staticmethod
    def _backend_dockerfile() -> str:
        return """\
FROM maven:3.9-amazoncorretto-17 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -q
COPY src ./src
RUN mvn package -DskipTests -q

FROM amazoncorretto:17-alpine
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
"""

    @staticmethod
    def _docker_compose(port: int) -> str:
        return f"""\
services:
  backend:
    build: ./backend
    networks:
      - app
  frontend:
    build: ./frontend
    ports:
      - "{port}:80"
    depends_on:
      - backend
    networks:
      - app
networks:
  app:
"""

    def _write_docker_files(self, project_id: str, port: int):
        project_dir = PROJECTS_DIR / project_id
        fe_dir = project_dir / "frontend"
        be_dir = project_dir / "backend"
        (fe_dir / "Dockerfile").write_text(self._frontend_dockerfile())
        (fe_dir / "nginx.conf").write_text(self._nginx_conf())
        (be_dir / "Dockerfile").write_text(self._backend_dockerfile())
        (project_dir / "docker-compose.yml").write_text(self._docker_compose(port))

    async def deploy(self, project_id: str, angular_files: dict, java_files: dict) -> int:
        port = self._allocate_port(project_id)
        self._write_project_files(project_id, angular_files, java_files)
        self._write_docker_files(project_id, port)
        self._deploy_status[project_id] = "building"
        asyncio.create_task(self._run_compose_up(project_id))
        return port

    async def _run_compose_up(self, project_id: str):
        project_dir = PROJECTS_DIR / project_id
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "up", "-d", "--build",
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                self._deploy_status[project_id] = "running"
                print(f"[DEPLOY] {project_id} running on port {self._port_registry.get(project_id)}")
            else:
                self._deploy_status[project_id] = "failed"
                print(f"[DEPLOY] {project_id} failed:\n{stderr.decode()}")
        except Exception as e:
            self._deploy_status[project_id] = "failed"
            print(f"[DEPLOY] {project_id} error: {e}")

    def get_status(self, project_id: str) -> dict:
        status = self._deploy_status.get(project_id, "idle")
        port = self._port_registry.get(project_id)
        host = os.environ.get("DEPLOY_HOST", "localhost")
        return {
            "status": status,
            "url": f"http://{host}:{port}" if status == "running" and port else None,
        }

    async def undeploy(self, project_id: str):
        project_dir = PROJECTS_DIR / project_id
        if project_dir.exists():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "compose", "down", "--rmi", "local",
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                print(f"[UNDEPLOY] {project_id} stopped")
            except Exception as e:
                print(f"[UNDEPLOY] {project_id} error: {e}")
        self._deploy_status.pop(project_id, None)
        self._free_port(project_id)


deploy_manager = DeployManager()
