import base64
import os
import random
import shutil
import string
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv
from playwright.sync_api import (
    APIRequestContext,
    Browser,
    Page,
    sync_playwright,
)

load_dotenv()


class GiteaConfig:
    GITEA_URL: str = os.getenv("GITEA_URL", "http://localhost:3000")
    GITEA_USER: str = os.getenv("GITEA_USER", "testuser")
    GITEA_PASS: str = os.getenv("GITEA_PASS", "testpass123")
    GITEA_EMAIL: str = os.getenv("GITEA_EMAIL", "testuser@test.com")
    GITEA_PORT: str = os.getenv("GITEA_PORT", "3000")
    GITEA_VERSION: str = os.getenv("GITEA_VERSION", "latest")
    BROWSER: str = os.getenv("BROWSER", "chromium")
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    RECORD_VIDEO: bool = os.getenv("RECORD_VIDEO", "false").lower() == "true"
    GITEA_WAIT_TIMEOUT: int = int(os.getenv("GITEA_WAIT_TIMEOUT", "60000"))
    GITEA_WAIT_INTERVAL: int = int(os.getenv("GITEA_WAIT_INTERVAL", "2000"))
    TIMEOUT_FACTOR: float = float(os.getenv("TIMEOUT_FACTOR", "1"))


cfg = GiteaConfig

SCREENSHOTS_DIR = Path("tests/screenshots")
VIDEOS_DIR = Path("tests/videos")
PAGES_DIR = Path("tests/pages")
AUTH_STATE_FILE = Path("tests/.auth/state.json")


def _api_auth_header() -> dict:
    token = base64.b64encode(f"{cfg.GITEA_USER}:{cfg.GITEA_PASS}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def random_string(length: int = 8) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def api_retry(fn, label: str, max_attempts: int = 5):
    for attempt in range(max_attempts):
        response = fn()
        if response.ok:
            return response
        if response.status in (500, 502, 503) and attempt < max_attempts - 1:
            jitter = random.random() * 500
            time.sleep(1.0 * (attempt + 1) + jitter / 1000)
            continue
        raise AssertionError(f"{label} failed: {response.status} {response.text}")


def api_create_repo(api_context: APIRequestContext, name: str, auto_init: bool = False):
    api_retry(
        lambda: api_context.post(
            "/api/v1/user/repos",
            data={"name": name, "auto_init": auto_init},
        ),
        "apiCreateRepo",
    )


def api_create_issue(
    api_context: APIRequestContext,
    owner: str,
    repo: str,
    title: str,
    body: str = "",
):
    result = {"index": 0}

    def _create():
        resp = api_context.post(
            f"/api/v1/repos/{owner}/{repo}/issues",
            data={"title": title, "body": body},
        )
        if resp.ok:
            result["index"] = resp.json()["number"]
        return resp

    api_retry(_create, "apiCreateIssue")
    return result["index"]


def api_delete_repo(api_context: APIRequestContext, owner: str, name: str):
    api_retry(
        lambda: api_context.delete(f"/api/v1/repos/{owner}/{name}"),
        "apiDeleteRepo",
    )


def pytest_sessionstart(session):
    for d in [VIDEOS_DIR, SCREENSHOTS_DIR, PAGES_DIR]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    AUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def pytest_sessionfinish(session, exitstatus):
    for d in [VIDEOS_DIR, SCREENSHOTS_DIR, PAGES_DIR, AUTH_STATE_FILE.parent]:
        if d.exists():
            has_content = any(f.stat().st_size > 0 for f in d.rglob("*") if f.is_file())
            if not has_content:
                shutil.rmtree(d)


def pytest_configure(config):
    config.addinivalue_line("markers", "anonymous: tests without auth")
    config.addinivalue_line("markers", "authenticated: tests requiring login")


@pytest.fixture(scope="session")
def gitea_config():
    return cfg


@pytest.fixture(scope="session", autouse=True)
def auth_storage_state():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        response = page.request.post(
            f"{cfg.GITEA_URL}/user/login",
            form={"user_name": cfg.GITEA_USER, "password": cfg.GITEA_PASS},
            max_redirects=0,
        )

        if response.status not in (302, 303):
            page.goto(f"{cfg.GITEA_URL}/user/sign_up", wait_until="load")
            page.get_by_label("Username").fill(cfg.GITEA_USER)
            page.get_by_label("Email").fill(cfg.GITEA_EMAIL)
            page.get_by_label("Password", exact=True).fill(cfg.GITEA_PASS)
            page.get_by_label("Confirm Password").fill(cfg.GITEA_PASS)
            page.get_by_role("button", name="Register").click()
            page.wait_for_load_state("load")

        page.goto(cfg.GITEA_URL, wait_until="load")
        context.storage_state(path=str(AUTH_STATE_FILE))
        browser.close()


@pytest.fixture(scope="session")
def api_context(playwright) -> APIRequestContext:
    ctx = playwright.request.new_context(
        base_url=cfg.GITEA_URL,
        extra_http_headers=_api_auth_header(),
    )
    yield ctx
    ctx.dispose()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    args = {**browser_context_args}
    if cfg.RECORD_VIDEO:
        args["record_video_dir"] = str(VIDEOS_DIR)
    return args


@pytest.fixture
def logged_in_page(browser: Browser) -> Page:
    context_args = {"storage_state": str(AUTH_STATE_FILE)}
    if cfg.RECORD_VIDEO:
        context_args["record_video_dir"] = str(VIDEOS_DIR)
    context = browser.new_context(**context_args)
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture(autouse=True)
def capture_artifactss(request, page):
    if "logged_in_page" in request.fixturenames:
        pg = request.getfixturevalue("logged_in_page")
    else:
        pg = request.getfixturevalue("page")

    yield pg

    test_name = request.node.name.replace("[", "_").replace("]", "_").replace("/", "_")
    pg.screenshot(path=str(SCREENSHOTS_DIR / f"{test_name}.png"), full_page=True)
    pg.content()
    content = pg.content()
    (PAGES_DIR / f"{test_name}.html").write_text(content, encoding="utf-8")


@pytest.fixture
def cleanup_repos(api_context: APIRequestContext):
    created_repos: list[str] = []
    yield created_repos

    for repo_name in created_repos:
        try:
            api_delete_repo(api_context, cfg.GITEA_USER, repo_name)
        except Exception:
            pass
