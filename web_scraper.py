import requests
from bs4 import BeautifulSoup
import spacy 
import json
import yagmail
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

NOTIFIED_EVENTS_FILE = "notified_event_urls.json"

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
    all_events = []
    for url_data in start_urls_with_selectors:
        url, event_container_selector, title_selector, description_selector, link_selector, base_url = url_data
        events_on_page = scrape_multiple_events_from_page(
            url, nlp, event_container_selector, title_selector, description_selector, link_selector, base_url
        )
        all_events.extend(events_on_page)
    return all_events

def load_notified_event_urls(filepath):
    """
    Loads a set of event URLs that have already been notified.
    Returns an empty set if the file doesn't exist or is invalid.
    """
    try:
        with open(filepath, "r") as f:
            urls = json.load(f)
            return set(urls)
    except FileNotFoundError:
        return set()
    except json.JSONDecodeError:
        print(f"Warning: Could not decode JSON from {filepath}. Starting with an empty set of notified events.")
        return set()

def save_notified_event_urls(filepath, urls):
    """
    Saves a set of event URLs to a JSON file.
    """
    try:
        with open(filepath, "w") as f:
            json.dump(list(urls), f, indent=4) # Store as list in JSON
    except IOError as e:
        print(f"Error saving notified event URLs to {filepath}: {e}")

def load_recipients_from_file(filepath):
    try:
        with open(filepath, 'r') as f:
            if filepath.endswith('.json'):
                return json.load(f)
            elif filepath.endswith('.txt'):
                return [line.strip() for line in f if line.strip()]
            else:
                print(f"Unsupported recipient file format: {filepath}")
                return []
    except FileNotFoundError:
        print(f"Recipient file not found: {filepath}")
        return []
    except json.JSONDecodeError:
        print(f"Error parsing JSON in recipient file: {filepath}")
        return []
    except Exception as e:
        print(f"Error loading recipients from file {filepath}: {e}")
        return []
    
def send_event_email(subject, body, recipient_email, sender_email):
    """
    Sends an email using yagmail
    """
    try:
        yag = yagmail.SMTP(sender_email)
        yag.send(bcc=recipient_email, subject=subject, contents=body)
        print("Email sent successfully via yagmail!")
    except Exception as e:
        print(f"Error sending email via yagmail: {e}")

def main():
    """
    Main function to orchestrate the scraping of multiple events.
    """
    # Initialize SpaCy
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        print("Error: SpaCy model 'en_core_web_sm' not found.  Please download it by running:")
        print("python -m spacy download en_core_web_sm")
        return

    # Updated structure to include selectors for multiple events
    # format is event_container_selector, title_selector, description_selector, link_selector, base_url
    start_urls_with_selectors = [
        ("https://www.barbican.org.uk/whats-on", "article.listing--event", "h2.listing-title--event", "div.search-listing__intro", "a.search-listing__link", "https://www.barbican.org.uk"),
        ("https://www.nationaltheatre.org.uk/whats-on", "div.c-event-card", "h3.c-event-card__title", "div.c-event-card__description", "a.c-event-card__cover-link", "https://www.nationaltheatre.org.uk"),
        ("https://premierescene.net/film-calendar/", "div.vsel-content", "h4.vsel-meta-title", "div.vsel-info", "a", "https://premierescene.net/film-calendar/"),
        ("https://whatson.bfi.org.uk/Online/default.asp", "div.Highlight", "h3.Highlight__heading", "p.Highlight__copy", "a.Highlight__link", "https://www.bfi.org.uk"),
        ("https://www.bbc.co.uk/news/entertainment_and_arts", "li.e1gp961v0", "div.ssrcss-espw6b-Stack", "a", "a.ssrcss-5wtq5v-PromoLink", "https://www.bbc.co.uk"),
        ("https://www.npg.org.uk/whatson/events-calendar?when=&what=event&who=", "div.o-card-standard", "a.a-link--nodec", "div.o-card-standard__text > div:last-child", "div.o-card-standard__image", "https://www.npg.org.uk"),
        ("https://www.southbankcentre.co.uk/whats-on/", "div.c-event-card", "h3.c-event-card__title", "div.c-event-card__listing-details", "a.c-event-card__cover-link", "https://www.southbankcentre.co.uk"),
        ("https://www.royalacademy.org.uk/exhibitions-and-events?page=1&what-filter=talks-lectures", "li.whats-on-listing__item", "h2.event-card__title", "h2.event-card__title", "a.event-card__link", "https://www.royalacademy.org.uk"),
        ("https://www.nationalgallery.org.uk/events/talks-and-conversations", "article.card", "div.card-title", "div.event-description", "a.dl-product-link", "https://www.nationalgallery.org.uk"),
        ("https://www.vam.ac.uk/whatson?type=talk", "li.b-event-teaser", "h2.b-event-teaser__title", "h2.b-event-teaser__title", "a.b-event-teaser__link", "https://www.vam.ac.uk"),
        ("https://www.tate.org.uk/whats-on?event_type=talk", "div.card", "h2.card__title", "div.card__description", "a", "https://www.tate.org.uk"),
        ("https://wellcomecollection.org/events?format=Wd-QYCcAACcAoiJS", "a.sc-d97058b-1", "h3.sc-4e66622a-0", "h3.sc-4e66622a-0", "a.sc-d97058b-1", "https://wellcomecollection.org"),
        ("https://www.londonlibrary.co.uk/whats-on", "li.event", "h3.title", "div.event-description p", "a", "https://www.londonlibrary.co.uk"),

        # Test link of Cate news but rather an event
        # ("https://www.bbc.co.uk/news/entertainment-arts-17725952", "div.ssrcss-1ki8hfp-StyledZone", "h1.ssrcss-1s9pby4-Heading e10rt3ze0", "div.ssrcss-suhx0k-RichTextComponentWrapper", "a", "https://www.bbc.co.uk")
        
        # Two test links for sure is Cate related
        # ("https://www.barbican.org.uk/whats-on/2025/event/acting-screentalk-hosted-by-cate-blanchett", "main", "hgroup.heading-group", "div.component-section", "a", "https://www.barbican.org.uk"),
        # ("https://wwd.com/fashion-news/fashion-scoops/cate-blanchett-cohost-serpentine-summer-party-1237099478/", "div.lrv-u-width-100p", "h1.article-title", "div.a-content", "a", "https://wwd.com/fashion-news/fashion-scoops"),
    ]

    previously_notified_urls = load_notified_event_urls(NOTIFIED_EVENTS_FILE)
    all_found_events = find_cate_blanchett_events_across_pages(start_urls_with_selectors, nlp)

    if not all_found_events:
        print("No events found during web scraping.")
        return

    current_relevant_events = [event for event in all_found_events if event['is_involved']]

    if not current_relevant_events:
        print("No relevant events involving Cate Blanchett found in this run.")
        return

    # Filter out events that have already been notified
    newly_relevant_events = [
        event for event in current_relevant_events
        if event['url'] not in previously_notified_urls
    ]

    # Save all *currently* relevant events (new and old) to cate_blanchett_events.json for a complete snapshot
    if current_relevant_events:
        print(f"\nFound {len(current_relevant_events)} relevant events involving Cate Blanchett (new and previously seen):")
        with open("cate_blanchett_events.json", "w") as f:
            json.dump(current_relevant_events, f, indent=4)
        print("All currently relevant events saved to cate_blanchett_events.json")

    if newly_relevant_events:
        print(f"\nFound {len(newly_relevant_events)} NEW relevant events involving Cate Blanchett:")
        for event in newly_relevant_events:
            print(f"- Title: {event['title']}")
            print(f"  URL: {event['url']}")
            print(f"  Description: {event['description']}")
            print("-" * 20)
        
        # Email configuration
        recipient_file_path = "recipients.json"
        recipient_email_list = load_recipients_from_file(recipient_file_path)

        if not recipient_email_list:
            print("Warning: No recipient emails loaded. Email will not be sent.")
            
        sender_email = "nicoleho1314@gmail.com" 
        
        email_subject = "New Cate Blanchett Event(s) Found"
        email_body = "The following new Cate Blanchett events were found:\n\n" + json.dumps(newly_relevant_events, indent=4)

        send_event_email(email_subject, email_body, recipient_email_list, sender_email)

        # Update the set of notified URLs and save it
        for event in newly_relevant_events:
            previously_notified_urls.add(event['url'])
        save_notified_event_urls(NOTIFIED_EVENTS_FILE, previously_notified_urls)
    else:
        print("\nNo NEW relevant events found since last check.")

if __name__ == "__main__":
    main()
