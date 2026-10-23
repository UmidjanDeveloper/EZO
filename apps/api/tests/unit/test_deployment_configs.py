"""Deployment templates stay review-only: no auto-deploys, no committed secrets, no
public database. These files are what an owner would hand to Render, Vercel or a VPS."""

import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
DEPLOY = REPO / "deploy"
SECRET_KEY = re.compile(r"(TOKEN|_KEY|PASSWORD|SECRET|DATABASE_URL)$")


def test_no_root_blueprint_is_discoverable():
    # Render auto-discovers render.yaml at the repository root; keep templates elsewhere.
    assert not (REPO / "render.yaml").exists()
    assert not (REPO / "render.yml").exists()


def test_render_templates_never_auto_deploy_or_inline_secrets():
    templates = sorted(DEPLOY.glob("render-*.yaml"))
    assert templates
    for path in templates:
        blueprint = yaml.safe_load(path.read_text(encoding="utf-8"))
        for service in blueprint["services"]:
            assert service["autoDeployTrigger"] == "off", path.name
            assert service["healthCheckPath"] == "/api/health", path.name
            for env in service.get("envVars", []):
                if SECRET_KEY.search(env["key"]):
                    assert "value" not in env, f"{path.name}: {env['key']} has an inline value"


def test_vercel_project_has_git_deployments_disabled_and_no_env():
    config = json.loads((REPO / "apps/web/vercel.json").read_text(encoding="utf-8"))
    assert config["git"]["deploymentEnabled"] is False
    assert "env" not in config and "build" not in config


def test_env_examples_contain_no_secret_values():
    examples = [*DEPLOY.glob("*.env.example"), *DEPLOY.glob("*/*.env.example")]
    assert examples
    for path in examples:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if SECRET_KEY.search(key.strip()):
                # A connection-string shape is allowed only with the literal placeholder.
                placeholder = key.strip() == "DATABASE_URL" and ":PASSWORD@" in value
                assert value.strip() == "" or placeholder, f"{path.name}: {key} must stay empty"


def test_primary_compose_keeps_database_private_and_images_pinned():
    compose = yaml.safe_load((DEPLOY / "primary/compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert compose["networks"]["backend"]["internal"] is True
    assert "ports" not in services["db"] and services["db"]["networks"] == ["backend"]
    for name in ("api", "student-worker", "refresh-worker", "web"):
        assert "ports" not in services[name], name
    assert set(services["caddy"]["ports"]) == {"80:80", "443:443", "443:443/udp"}
    for name in ("db", "caddy"):
        assert "@sha256:" in services[name]["image"], name
    database_url = compose["x-api-env"]["environment"]["DATABASE_URL"]
    assert database_url.startswith("postgresql+psycopg://ezo_app:")
    assert "sslmode=verify-full" in database_url


def test_primary_secrets_are_git_ignored():
    ignored = (DEPLOY / "primary/.gitignore").read_text(encoding="utf-8").split()
    assert {"secrets/", "primary.env"} <= set(ignored)
