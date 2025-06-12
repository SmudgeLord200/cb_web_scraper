import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

def is_cate_blanchett_involved(title, description, nlp):
    """
    Advanced NLP check for Cate Blanchett's involvement, differentiating
    between active participation in an event and merely sharing views,
    using SpaCy's dependency parsing and rule-based matching.
    """
    combine_text = f"{title} {description}"
    doc = nlp(combine_text)
    full_name_tokens = ["Cate", "Blanchett"]

    # --- Step 1: Find "Cate Blanchett" and analyze her context ---
    found_cate = None
    for ent in doc.ents:
        if ent.label_ == "PERSON" and "Blanchett" in ent.text:
            # Prefer the exact match if available
            if "Cate Blanchett" in ent.text:
                found_cate = ent
                break
            # Otherwise, use the entity with Blanchett
            if found_cate is None: # Only assign if exact match not found yet
                 found_cate = ent

    # If "Cate Blanchett" is not found as a PERSON entity, try token-based
    if found_cate is None:
        for i in range(len(doc) - 1):
            if doc[i].text.lower() == full_name_tokens[0].lower() and doc[i+1].text.lower() == full_name_tokens[1].lower():
                found_cate = doc[i:i+2] # Slice representing the tokens
                break

    if found_cate is None:
        return False # Cate Blanchett not found in text

    # --- Step 2: Analyze the verbs related to "Cate Blanchett" ---

    # Define action verbs vs. passive/reporting verbs
    action_verbs = {"host", "hosts", "hosted", "co-host", "co-hosts", "co-hosted",
                    "present", "presents", "presented", "appear", "appears", "appeared",
                    "attend", "attends", "attended", "join", "joins", "joined",
                    "participate", "participates", "participated",
                    "introduce", "introduces", "introduced", "interview", "interviews", "interviewed"}

    # Define reporting/view-sharing verbs (to potentially exclude)
    reporting_verbs = {"say", "says", "said", "state", "states", "stated",
                       "believe", "believes", "believed", "think", "thinks", "thought",
                       "express", "expresses", "expressed", "comment", "comments", "commented",
                       "discuss", "discusses", "discussed", "reveal", "reveals", "revealed",
                       "share", "shares", "shared", "opine", "opines", "opined", "tell", "tells", "told"}

    # Iterate through tokens in a window around "Cate Blanchett" or her entity
    # And specifically look at dependency relations to verbs
    for token in found_cate:
        # Check if the token is a subject of an action verb
        if token.dep_ in ["nsubj", "nsubjpass", "agent"]: # Nominal subject, passive nominal subject, agent
            head = token.head # The verb that 'token' is the subject of
            if head.pos_ == "VERB":
                # If it's an action verb, it's likely involvement
                if head.lemma_.lower() in action_verbs:
                    # Further check for "in conversation with" pattern, etc.
                    # This is more precise than just a general verb
                    if head.lemma_.lower() == "interview" and "by" in [d.text.lower() for d in head.children]:
                         # Check if "interviewed by Cate Blanchett" (passive involvement)
                         for child in head.children:
                             if child.dep_ == "agent" and "blanchett" in child.text.lower():
                                 return True
                    elif head.lemma_.lower() == "conversation": # e.g. "in conversation with Cate Blanchett"
                         for child in head.children:
                             if child.dep_ == "prep" and child.text.lower() == "with":
                                 return True
                    else:
                        return True
                # If it's a reporting verb, it's likely sharing views, so we might *not* return True immediately
                elif head.lemma_.lower() in reporting_verbs:
                    # We want to be careful here. If "Cate Blanchett said X at Y event", it's still an event.
                    # This requires looking for event-related nouns nearby.
                    # For simplicity, we'll try to prioritize positive action verbs.
                    pass # Don't return True yet for reporting verbs

    # --- Step 3: Look for specific phrases and event-related nouns/contexts ---
    # This acts as a fallback and a reinforcing check
    text_lower = combine_text.lower()
    if "cate blanchett" in text_lower:
        # Direct phrases implying involvement
        if "hosted by cate blanchett" in text_lower or \
           "co-hosted by cate blanchett" in text_lower or \
           "cate blanchett hosts" in text_lower or \
           "cate blanchett presents" in text_lower or \
           "in conversation with cate blanchett" in text_lower or \
           "q&a with cate blanchett" in text_lower or \
           "featuring cate blanchett" in text_lower:
            return True

        # Look for proximity of name to event-related words
        event_nouns = {"event", "talk", "screentalk", "panel", "discussion", "lecture", "summit",
                       "party", "gala", "ceremony", "premiere", "festival", "show", "performance"}
        for i in range(len(doc) - 1):
            if doc[i].text.lower() == full_name_tokens[0].lower() and doc[i+1].text.lower() == full_name_tokens[1].lower():
                # Check 5 tokens before and 10 tokens after the name for event nouns
                window_start = max(0, i - 5)
                window_end = min(len(doc), i + 10)
                for j in range(window_start, window_end):
                    if doc[j].lemma_.lower() in event_nouns:
                        # Ensure there's also an action verb nearby if an event noun is found
                        # This adds confidence.
                        for k in range(window_start, window_end):
                            if doc[k].pos_ == "VERB" and doc[k].lemma_.lower() in action_verbs:
                                return True
                        # If a reporting verb is there, check for specific event context.
                        # This is the tricky part. For now, we lean towards involvement if an event noun is present.
                        if doc[j].lemma_.lower() in event_nouns: # If an event noun is found with Cate nearby, assume involvement
                            return True

    return False

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
    user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    options.add_argument(f'user-agent={user_agent}')

    driver = None # Initialize driver to None for the finally block
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        WebDriverWait(driver, 10).until(EC.presence_of_element_located(initial_wait_condition))

        if click_actions:
            for action in click_actions:
                driver.find_element(action['click_by'], action['click_value']).click()
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((action['wait_after_click_by'], action['wait_after_click_value'])))
        
        html_source = driver.page_source
    except TimeoutException:
        print(f"Timed out waiting for content on {url}")
    except WebDriverException as e:
        print(f"Selenium WebDriver error on {url}: {e}")
    finally:
        if driver:
            driver.quit()
    return html_source    

def scrape_multiple_events_from_page(url, nlp, event_container_selector, title_selector, description_selector, link_selector, base_url=None):
    """
    Scrapes multiple events from a single page.
    """
    events = []
    is_bfi = "bfi.org.uk" in url
    is_NT = "nationaltheatre.org.uk" in url
    is_NG = "npg.org.uk" in url
    is_SBC = "southbankcentre.co.uk" in url
    is_RA = "royalacademy.org.uk" in url
    html = ""
    
    try:
        if is_bfi:
            bfi_initial_wait = (By.ID, "menuTop")
            bfi_click_actions = [
                {
                    'click_by': By.ID,
                    'click_value': "menuTopItem1",
                    'wait_after_click_by': By.ID,
                    'wait_after_click_value': "menuTopItem1"
                },
                {
                    'click_by': By.CLASS_NAME,
                    'click_value': 'menuSubItem',
                    'wait_after_click_by': By.CLASS_NAME,
                    'wait_after_click_value': 'Highlight'    
                },
            ]
            
            html = get_html_with_selenium(url, bfi_initial_wait, bfi_click_actions)
        elif is_NT:         
            nt_initial_wait = (By.CLASS_NAME, "c-event-card")
            nt_click_actions = None
            html = get_html_with_selenium(url, nt_initial_wait, nt_click_actions)
        elif is_NG:
            ng_initial_wait = (By.CLASS_NAME, "o-card-standard")
            ng_click_actions = None
            html = get_html_with_selenium(url, ng_initial_wait, ng_click_actions)
        elif is_SBC:
            sbc_initial_wait = (By.CLASS_NAME, "c-event-card")
            sbc_click_actions = None
            html = get_html_with_selenium(url, sbc_initial_wait, sbc_click_actions)
        elif is_RA:
            ra_initial_wait = (By.CLASS_NAME, "whats-on-listing__item")
            ra_click_actions = None
            html = get_html_with_selenium(url, ra_initial_wait, ra_click_actions)
        else:
            res = requests.get(url)
            res.raise_for_status()
            html = res.text
           
        soup = BeautifulSoup(html, 'html.parser')

        event_containers = soup.select(event_container_selector)
        print(f"Found {len(event_containers)} event containers on {url}")
        
        for container in event_containers:
            title_element = container.select_one(title_selector)
            title = title_element.text.strip() if title_element else "No Title Found"

            description_element = container.select_one(description_selector)
            description = description_element.text.strip() if description_element else "No Description Found"
            
            link_element = container.select_one(link_selector)
                
            event_url = None
            if link_element and 'href' in link_element.attrs:
                event_url = link_element['href']
                if base_url and not event_url.startswith('http'):
                        event_url = base_url + event_url
            else:
                event_url = url

            is_involved = is_cate_blanchett_involved(title, description, nlp)

            events.append({
                "title": title,
                "url": event_url if event_url else url, # Use the listing page URL if no specific event link
                "is_involved": is_involved,
                "description": description[:200] + "..." # Keep a snippet for now
            })

    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
    except Exception as e:
        print(f"scrape_multiple_events_from_page: Error processing {url}: {e}")
    return events

def find_cate_blanchett_events_across_pages(start_urls_with_selectors, nlp):
    """
    Scrapes events across multiple pages (currently only the first page of each).
    """
    all_found_events = []
    
    # Determine a reasonable number of workers.
    num_urls = len(start_urls_with_selectors)
    max_workers = min(5, num_urls if num_urls > 0 else 1)

    print(f"Starting scraping with up to {max_workers} concurrent workers for {num_urls} URLs.")

    # Run the web scraping function concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit scraping tasks to the executor
        # Key is the future object, value is the URL for context for the dictionary
        '''
        Example data structure:
            {
                <Future at ID state="pending">: url_data[0]
            }
        '''
        # url_data[0]: target url, url_data[1]: event_container_selector, url_data[2]: title_selector
        # url_data[3]: description_selector, url_data[4]: link_selector, url_data[5]: base_url
        future_to_url_data = {
            executor.submit(
                scrape_multiple_events_from_page,
                url_data[0], nlp, url_data[1], url_data[2], url_data[3], url_data[4], url_data[5]
            ): url_data[0]  
            for url_data in start_urls_with_selectors
        }

        for future in concurrent.futures.as_completed(future_to_url_data):
            source_url = future_to_url_data[future]
            try:
                events_from_page = future.result()
                if events_from_page:  # Check if the result is not None or empty
                    all_found_events.extend(events_from_page) # Append to a result dictionary
                    print(f"Successfully processed and got {len(events_from_page)} events from: {source_url}")
            except Exception as exc:
                print(f"Scraping {source_url} generated an exception: {exc}")

    print(f"Finished scraping. Total events collected before filtering: {len(all_found_events)}")
    return all_found_events