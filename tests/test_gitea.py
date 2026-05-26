import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from conftest import (
    api_create_issue,
    api_create_repo,
    api_delete_repo,
    cfg,
    random_string,
)


# параметрезированный тест для будущего масшатибрования
@pytest.mark.anonymous
@pytest.mark.parametrize(
    "path,expected_in_title",
    [
        ("/explore/repos", "Explore"),
    ],
    ids=["explore"],
)
def test_page_titles(page: Page, path: str, expected_in_title: str):
    page.goto(f"{cfg.GITEA_URL}{path}", wait_until="load")
    expect(page).to_have_title(re.compile(expected_in_title, re.IGNORECASE))


@pytest.mark.anonymous
def test_homepage_navigation_links(page: Page):
    page.goto(cfg.GITEA_URL, wait_until="load")
    expect(page.get_by_role("link", name="Sign In")).to_be_visible()
    expect(page.get_by_role("link", name="Explore", exact=True)).to_be_visible()


@pytest.mark.anonymous
def test_sign_up_form_fields(page: Page):
    page.goto(f"{cfg.GITEA_URL}/user/sign_up", wait_until="load")
    expect(page.get_by_role("textbox", name="Username")).to_be_visible()
    expect(page.get_by_role("textbox", name="Email")).to_be_visible()
    expect(page.get_by_label("Password", exact=True)).to_be_visible()
    expect(page.get_by_label("Confirm Password")).to_be_visible()


@pytest.mark.anonymous
def test_login_form_validation(page: Page):
    page.goto(f"{cfg.GITEA_URL}/user/login", wait_until="load")
    page.get_by_role("textbox", name="Username").fill("invalid_user_123")
    page.get_by_label("Password").fill("wrong_password")
    page.get_by_role("button", name="Sign In").click()
    expect(page.get_by_text("Username or password is incorrect.")).to_be_visible()


@pytest.mark.anonymous
def test_explore_search_functionality(page: Page):
    page.goto(f"{cfg.GITEA_URL}/explore/repos", wait_until="load")
    search = page.get_by_role("searchbox", name="Search")
    expect(search).to_be_visible()
    search.fill("nonexistent-repo-xyz-12345")
    page.keyboard.press("Enter")
    page.wait_for_load_state("load")
    expect(page.locator("body")).to_contain_text(
        re.compile("No|0 result", re.IGNORECASE)
    )


@pytest.mark.authenticated
def test_user_dropdown_shows_username(logged_in_page: Page):
    logged_in_page.goto(cfg.GITEA_URL, wait_until="load")
    expect(logged_in_page.locator(".ui.dropdown .text").last).to_have_text(
        cfg.GITEA_USER
    )


@pytest.mark.authenticated
def test_create_repository(logged_in_page: Page, cleanup_repos):
    repo_name = f"e2e-{random_string()}"
    cleanup_repos.append(repo_name)

    logged_in_page.goto(f"{cfg.GITEA_URL}/repo/create", wait_until="load")
    expect(logged_in_page.get_by_role("heading", name="New Repository")).to_be_visible()

    logged_in_page.get_by_role("textbox", name="Repository Name").fill(repo_name)
    logged_in_page.locator("#auto-init input").uncheck(force=True)
    logged_in_page.get_by_role("button", name="Create Repository").click()
    logged_in_page.wait_for_load_state("load")

    expect(logged_in_page).to_have_url(re.compile(f"/{repo_name}$"))
    expect(logged_in_page).to_have_title(re.compile(repo_name))


@pytest.mark.authenticated
def test_create_repository_with_readme(logged_in_page: Page, cleanup_repos):
    repo_name = f"e2e-readme-{random_string()}"
    cleanup_repos.append(repo_name)

    logged_in_page.goto(f"{cfg.GITEA_URL}/repo/create", wait_until="load")
    logged_in_page.get_by_role("textbox", name="Repository Name").fill(repo_name)
    logged_in_page.locator("#auto-init input").check(force=True)
    logged_in_page.get_by_role("button", name="Create Repository").click()
    logged_in_page.wait_for_load_state("load")

    expect(logged_in_page).to_have_url(re.compile(f"/{repo_name}$"))
    logged_in_page.get_by_role("link", name="Code", exact=True).last.click()
    logged_in_page.wait_for_load_state("load")
    expect(logged_in_page.get_by_role("link", name="README.md").first).to_be_visible()


@pytest.mark.authenticated
def test_create_issue(
    logged_in_page: Page, api_context: APIRequestContext, cleanup_repos
):
    repo_name = f"e2e-issues-{random_string()}"
    cleanup_repos.append(repo_name)
    api_create_repo(api_context, repo_name)

    logged_in_page.goto(
        f"{cfg.GITEA_URL}/{cfg.GITEA_USER}/{repo_name}/issues", wait_until="load"
    )
    logged_in_page.get_by_role("link", name="New Issue").click()
    logged_in_page.wait_for_load_state("load")

    issue_title = f"Test issue {random_string()}"
    logged_in_page.get_by_placeholder("Title").fill(issue_title)
    logged_in_page.locator("textarea[name='content']").fill(
        "This is a test issue created by e2e tests."
    )
    logged_in_page.get_by_role("button", name="Create").click()
    logged_in_page.wait_for_load_state("load")

    expect(logged_in_page.get_by_text(issue_title)).to_be_visible()


@pytest.mark.authenticated
def test_create_label_in_repo(
    logged_in_page: Page, api_context: APIRequestContext, cleanup_repos
):
    repo_name = f"e2e-labels-{random_string()}"
    cleanup_repos.append(repo_name)
    api_create_repo(api_context, repo_name)

    logged_in_page.goto(
        f"{cfg.GITEA_URL}/{cfg.GITEA_USER}/{repo_name}/labels", wait_until="load"
    )

    label_name = f"e2e-label-{random_string()}"
    logged_in_page.get_by_role("button", name="New Label").click()

    logged_in_page.locator("#issue-label-edit-modal").wait_for(state="visible")
    logged_in_page.locator("#issue-label-edit-modal input[name='title']").fill(
        label_name
    )
    logged_in_page.locator("#issue-label-edit-modal input[name='color']").fill(
        "#ff0000"
    )

    with logged_in_page.expect_navigation():
        logged_in_page.locator("#issue-label-edit-modal .approve.button").click()

    expect(logged_in_page.get_by_text(label_name)).to_be_visible()


@pytest.mark.authenticated
def test_repository_milestone(
    logged_in_page: Page, api_context: APIRequestContext, cleanup_repos
):
    repo_name = f"e2e-mile-{random_string()}"
    cleanup_repos.append(repo_name)
    api_create_repo(api_context, repo_name)

    logged_in_page.goto(
        f"{cfg.GITEA_URL}/{cfg.GITEA_USER}/{repo_name}/milestones", wait_until="load"
    )

    milestone_title = f"v1.0 Release {random_string()}"
    logged_in_page.get_by_role("link", name="New Milestone").click()
    logged_in_page.wait_for_load_state("load")
    logged_in_page.get_by_role("textbox", name="Title").fill(milestone_title)
    logged_in_page.get_by_role("button", name="Create Milestone").click()
    logged_in_page.wait_for_load_state("load")

    expect(logged_in_page.get_by_text(milestone_title).first).to_be_visible()


@pytest.mark.authenticated
def test_user_settings_page(logged_in_page: Page):
    logged_in_page.goto(cfg.GITEA_URL, wait_until="load")

    logged_in_page.get_by_role("menu", name="Profile and Settings…").click()
    logged_in_page.get_by_role("menuitem", name="Settings").click()
    logged_in_page.wait_for_load_state("load")

    expect(logged_in_page).to_have_url(re.compile("/user/settings"))
    expect(logged_in_page.get_by_text("User Settings")).to_be_visible()


@pytest.mark.authenticated
def test_user_profile_visible(logged_in_page: Page):
    logged_in_page.goto(f"{cfg.GITEA_URL}/{cfg.GITEA_USER}", wait_until="load")

    expect(logged_in_page).to_have_url(re.compile(f"/{cfg.GITEA_USER}$"))
    expect(logged_in_page.locator(".user.profile")).to_be_visible()


@pytest.mark.authenticated
def test_logout(logged_in_page: Page):
    logged_in_page.goto(cfg.GITEA_URL, wait_until="load")

    logged_in_page.context.clear_cookies()
    logged_in_page.goto(cfg.GITEA_URL, wait_until="load")

    expect(logged_in_page.get_by_role("link", name="Sign In")).to_be_visible()
