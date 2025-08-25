from fake_useragent import UserAgent
from seleniumbase import Driver
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# General version for most sites
def get_html_with_selenium(url, initial_wait_condition, click_actions):
    """
    Helper function to get HTML content using Selenium, handling common setup and interactions.

    Args:
        url (str): The URL to load.
        initial_wait_condition (tuple): A tuple (By, value) for the initial explicit wait.
        click_actions (list, optional): A list of dictionaries, where each dictionary
                                        specifies 'click_by', 'click_value',
                                        'wait_after_click_by', and 'wait_after_click_value'.
                                        Defaults to None.

    Returns:
        str: The page source HTML, or an empty string if an error occurs.
    """
    html_source = ""
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox") # for Linux servers
    options.add_argument('--window-size=1920,1080')
    options.add_argument("start-maximized")
    # user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.7258.128 Safari/537.36'
    user_agent = UserAgent().random
    options.add_argument(f'user-agent={user_agent}')

    driver = None # Initialize driver to None for the finally block
    try:
        driver = webdriver.Chrome(options=options)
        
        driver.get(url)

        WebDriverWait(driver, 20).until(EC.presence_of_element_located(initial_wait_condition))

        if click_actions:
            for action in click_actions:
                WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((action['click_by'], action['click_value']))
                ).click()
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((action['wait_after_click_by'], action['wait_after_click_value'])))
        
        html_source = driver.page_source
    except TimeoutException:
        print(f"Timed out waiting for content on {url}")
    except WebDriverException as e:
        print(f"Selenium WebDriver error on {url}: {e}")
    finally:
        if driver:
            driver.quit()
    return html_source    

# Make a SeleniumBase version for some sites like BFI
def get_html_with_selenium_base(url, initial_wait_condition, click_actions):
    """
    Helper function to get HTML content using SeleniumBase, handling common setup and interactions.

    Args:
        url (str): The URL to load.
        initial_wait_condition (tuple): A tuple (By, value) for the initial explicit wait.
        click_actions (list, optional): A list of dictionaries, where each dictionary
                                        specifies 'click_by', 'click_value',
                                        'wait_after_click_by', and 'wait_after_click_value'.
                                        Defaults to None.

    Returns:
        str: The page source HTML, or an empty string if an error occurs.
    """
    html_source = ""
    driver = None # Initialize driver to None for the finally block
    try:
        driver = Driver(uc=True, headless=True, no_sandbox=True, browser="chrome", d_width=1920, d_height=1080, disable_gpu=True)
        
        driver.uc_open(url)

        WebDriverWait(driver, 20).until(EC.presence_of_element_located(initial_wait_condition))

        if click_actions:
            for action in click_actions:
                WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((action['click_by'], action['click_value']))
                ).click()
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((action['wait_after_click_by'], action['wait_after_click_value'])))
        
        html_source = driver.get_page_source()
    except TimeoutException:
        print(f"Timed out waiting for content on {url}")
    except WebDriverException as e:
        print(f"Selenium WebDriver error on {url}: {e}")
    finally:
        if driver:
            driver.quit()
    return html_source