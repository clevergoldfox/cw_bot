from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGIN_URL = "https://www.lancers.jp/user/login?ref=header_menu"
DEFAULT_COOKIES_PATH = Path("lancers_cookies.json")
DEFAULT_DOTENV_PATH = Path(".env")


class LancersLoginError(RuntimeError):
    pass


def load_dotenv(path: Path = DEFAULT_DOTENV_PATH, *, override: bool = False) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("export "):
            line = line[7:].lstrip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if value and value[0] not in "\"'":
            value = value.split("#", 1)[0].strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        if not override and key in os.environ:
            continue

        os.environ[key] = value


def build_chrome_driver(*, headless: bool = False, user_data_dir: Optional[Path] = None):
    try:
        from selenium import webdriver
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("selenium is not installed. Install with: pip install selenium") from exc

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--lang=ja-JP")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if user_data_dir:
        options.add_argument(f"--user-data-dir={str(user_data_dir)}")

    return webdriver.Chrome(options=options)


def _first_visible(elements):
    for element in elements:
        try:
            if element.is_displayed() and element.is_enabled():
                return element
        except Exception:
            continue
    return None


def _wait_ready(driver, timeout: int = 20) -> None:
    from selenium.webdriver.support.ui import WebDriverWait

    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")


def _find_login_container(driver, timeout: int = 20):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    password_input = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
    )

    try:
        return password_input.find_element(By.XPATH, "ancestor::form")
    except Exception:
        return driver


def _find_email_input(container):
    from selenium.webdriver.common.by import By

    selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[autocomplete='username']",
        "input[type='text']",
    ]

    for selector in selectors:
        element = _first_visible(container.find_elements(By.CSS_SELECTOR, selector))
        if element:
            return element

    raise LancersLoginError("Could not find the email/username input on the login page.")


def _find_password_input(container):
    from selenium.webdriver.common.by import By

    element = _first_visible(container.find_elements(By.CSS_SELECTOR, "input[type='password']"))
    if not element:
        raise LancersLoginError("Could not find the password input on the login page.")
    return element


def _submit(container, password_input) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    submit_button = _first_visible(
        container.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
    )
    if submit_button:
        submit_button.click()
        return

    password_input.send_keys(Keys.ENTER)


def _extract_error_text(driver) -> str:
    from selenium.webdriver.common.by import By

    selectors = [
        ".c-alert",
        ".alert",
        ".error",
        ".c-form__error",
        ".p-message",
        "[role='alert']",
    ]

    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            try:
                if element.is_displayed():
                    text = (element.text or "").strip()
                    if text:
                        return text
            except Exception:
                continue

    return ""


def _has_recaptcha(driver) -> bool:
    from selenium.webdriver.common.by import By

    if driver.find_elements(By.CSS_SELECTOR, "iframe[title*='reCAPTCHA'], div.g-recaptcha"):
        return True
    if driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], script[src*='recaptcha']"):
        return True
    return False


def lancers_login(
    driver,
    email: str,
    password: str,
    *,
    login_url: str = LOGIN_URL,
    timeout: int = 30,
    manual_captcha: bool = True,
) -> None:
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(login_url)
    _wait_ready(driver, timeout=timeout)

    container = _find_login_container(driver, timeout=timeout)
    email_input = _find_email_input(container)
    password_input = _find_password_input(container)

    email_input.clear()
    email_input.send_keys(email)
    password_input.clear()
    password_input.send_keys(password)
    _submit(container, password_input)

    def _logged_in(d) -> bool:
        url = (d.current_url or "").lower()
        if "/user/login" not in url and "login" not in url:
            return True
        if d.find_elements(
            By.XPATH,
            "//a[contains(@href,'logout') or contains(., 'ログアウト') or contains(., 'Logout')]",
        ):
            return True
        return False

    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(_logged_in)
        return
    except TimeoutException:
        if manual_captcha and _has_recaptcha(driver):
            print("Captcha detected. Solve it in the opened browser, then press Enter to continue...")
            input()
            _wait_ready(driver, timeout=timeout)
            wait.until(_logged_in)
            return

        error_text = _extract_error_text(driver)
        message = "Login did not complete."
        if error_text:
            message += f" Page error: {error_text}"
        else:
            message += " The page may have changed or credentials are invalid."
        raise LancersLoginError(message)


def save_cookies(driver, path: Path = DEFAULT_COOKIES_PATH) -> Path:
    cookies = driver.get_cookies()
    path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cookies(path: Path = DEFAULT_COOKIES_PATH) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="Log into Lancers and optionally save cookies.")
    parser.add_argument("--email", default=os.getenv("LANCERS_EMAIL"), help="Login email (or set LANCERS_EMAIL).")
    parser.add_argument(
        "--password", default=os.getenv("LANCERS_PASSWORD"), help="Login password (or set LANCERS_PASSWORD)."
    )
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode.")
    parser.add_argument("--user-data-dir", default=None, help="Chrome user data dir to reuse a profile.")
    parser.add_argument("--save-cookies", default=str(DEFAULT_COOKIES_PATH), help="Path to write cookies JSON.")
    parser.add_argument("--keep-open", action="store_true", help="Wait for Enter before closing the browser.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    args = _parse_args(argv)
    if not args.email or not args.password:
        print(
            "Missing credentials. Provide --email/--password or set LANCERS_EMAIL/LANCERS_PASSWORD (or put them in .env).",
            file=sys.stderr,
        )
        return 2

    user_data_dir = Path(args.user_data_dir) if args.user_data_dir else None
    driver = build_chrome_driver(headless=args.headless, user_data_dir=user_data_dir)
    try:
        lancers_login(driver, args.email, args.password, manual_captcha=not args.headless)
        if args.save_cookies:
            save_cookies(driver, Path(args.save_cookies))
            print(f"Saved cookies to: {args.save_cookies}")
        if args.keep_open:
            input("Press Enter to close the browser...")
    finally:
        driver.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
