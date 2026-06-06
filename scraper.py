import os
import re
import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from concurrent.futures import ProcessPoolExecutor
import concurrent.futures
from selenium_scraper_methods import get_html_with_selenium, get_html_with_selenium_base

_CATE_NAME_RE = re.compile(r"cate\s+blanchett", re.IGNORECASE)

def _normalize_event_text(text):
    """Collapse whitespace and non-breaking spaces for reliable substring checks."""
    if not text:
        return ""
    normalized = text.replace("\u00a0", " ").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", normalized).strip()

def _mentions_cate_blanchett(text):
    return bool(_CATE_NAME_RE.search(_normalize_event_text(text)))

def _cate_name_token_spans(doc):
    """Yield spaCy spans covering each 'Cate Blanchett' occurrence in the doc."""
    for i in range(len(doc) - 1):
        if doc[i].text.lower() == "cate" and doc[i + 1].text.lower() == "blanchett":
            yield doc[i : i + 2]

def is_cate_blanchett_involved(title, description, nlp):
    """
    Detect whether Cate Blanchett is actively involved in an event (hosting, performing,
    speaking, cast in a production, etc.), not merely quoted in news coverage.
    """
    combine_text = _normalize_event_text(f"{title} {description}")
    if not _mentions_cate_blanchett(combine_text):
        return False

    text_lower = combine_text.lower()
    doc = nlp(combine_text)

    # Verbs where Cate as subject usually means active participation
    subject_action_verbs = {
        "host", "present", "appear", "attend", "join", "participate",
        "introduce", "interview", "speak", "discuss", "perform", "star",
    }
    # Verbs where Cate as object often means cast / creative involvement
    object_involvement_verbs = {
        "direct", "star", "cast", "feature", "include", "join", "lead",
        "perform", "play", "present", "host", "introduce",
    }
    reporting_verbs = {
        "say", "state", "believe", "think", "express", "comment",
        "reveal", "share", "opine", "tell",
    }
    event_nouns = {
        "event", "talk", "screentalk", "panel", "discussion", "lecture", "summit",
        "party", "gala", "ceremony", "premiere", "festival", "show", "performance",
        "production", "play", "season", "screening", "conversation", "masterclass",
        "workshop", "evening", "session", "stage", "theatre", "theater",
    }

    high_confidence_phrases = (
        "hosted by cate blanchett",
        "co-hosted by cate blanchett",
        "cate blanchett hosts",
        "cate blanchett presents",
        "in conversation with cate blanchett",
        "q&a with cate blanchett",
        "featuring cate blanchett",
        "starring cate blanchett",
        "directs cate blanchett",
        "directed by cate blanchett",
        "cate blanchett stars",
        "cate blanchett performs",
        "cate blanchett leads",
        "led by cate blanchett",
        "join cate blanchett",
        "cate blanchett joins",
    )
    if any(phrase in text_lower for phrase in high_confidence_phrases):
        return True

    # News-style quotes without event context (e.g. BBC articles)
    news_only_phrases = (
        "cate blanchett said",
        "cate blanchett says",
        "cate blanchett told",
        "according to cate blanchett",
        "cate blanchett believes",
        "cate blanchett thinks",
    )
    if any(phrase in text_lower for phrase in news_only_phrases):
        if not any(noun in text_lower for noun in event_nouns):
            return False

    # --- NLP: subject or object of involvement verbs ---
    for name_span in _cate_name_token_spans(doc):
        for token in name_span:
            if token.dep_ in ("nsubj", "nsubjpass", "agent") and token.head.pos_ == "VERB":
                lemma = token.head.lemma_.lower()
                if lemma in subject_action_verbs:
                    return True
                if lemma in reporting_verbs:
                    continue

            if token.dep_ in ("dobj", "pobj", "attr", "oprd") and token.head.pos_ == "VERB":
                if token.head.lemma_.lower() in object_involvement_verbs:
                    return True

            # "directed by X" with Cate elsewhere, or passive "starring Cate Blanchett"
            if token.dep_ == "pobj" and token.head.lemma_.lower() == "by":
                verb = token.head.head
                if verb.pos_ == "VERB" and verb.lemma_.lower() in object_involvement_verbs:
                    return True

    # --- Phrase fallbacks near the name ---
    additional_involvement_phrases = (
        "with cate blanchett",
        "featuring cate blanchett",
        "cate blanchett in",
        "cate blanchett will",
        "cate blanchett and",
        "cate blanchett on",
        "cate blanchett at",
        "cate blanchett talks",
        "cate blanchett present",
        "cate blanchett interview",
        "cate blanchett discussion",
        "cate blanchett conversation",
        "cate blanchett q&a",
        "cate blanchett explores",
        "cate blanchett speaks",
        "meet cate blanchett",
    )
    if any(phrase in text_lower for phrase in additional_involvement_phrases):
        return True

    # Name near event vocabulary in the same sentence
    for sent in doc.sents:
        if not _mentions_cate_blanchett(sent.text):
            continue
        sent_lower = sent.text.lower()
        if any(noun in sent_lower for noun in event_nouns):
            return True
        for i, token in enumerate(sent):
            if token.text.lower() != "cate" or i + 1 >= len(sent) or sent[i + 1].text.lower() != "blanchett":
                continue
            window = sent[max(0, i - 8) : min(len(sent), i + 12)]
            if any(t.lemma_.lower() in event_nouns for t in window):
                return True
            if any(
                t.pos_ == "VERB"
                and t.lemma_.lower() in subject_action_verbs | object_involvement_verbs
                for t in window
            ):
                return True

    # Full-text event context (e.g. NT: "... new production." with cast credit)
    if any(noun in text_lower for noun in event_nouns):
        return True

    # Cast/creative credit patterns without explicit event nouns
    if re.search(
        r"(directs?|directed|stars?|starred|casts?|features?|performs?|"
        r"starring|featuring|includes?)\s+cate\s+blanchett",
        text_lower,
    ):
        return True

    return False

def scrape_multiple_events_from_page(url, nlp, event_container_selector, title_selector, description_selector, link_selector, base_url=None):
    """
    Scrapes multiple events from a single page.
    """
    events = []
    is_bfi = "bfi.org.uk" in url
    is_NT = "nationaltheatre.org.uk" in url
    is_SBC = "southbankcentre.co.uk" in url
    is_RA = "royalacademy.org.uk" in url
    is_NPG = "npg.org.uk" in url
    is_RAH = "royalalberthall.com" in url
    is_RBO = "rbo.org.uk" in url
    html = ""
    
    try:
        if is_bfi:
            bfi_initial_wait = (By.ID, "menuTop")
            bfi_click_actions = [
                {
                    'click_by': By.ID,
                    'click_value': "menuTopItem1",
                    'wait_after_click_by': By.CLASS_NAME,
                    'wait_after_click_value': "menuSub"
                },
                {
                    'click_by': By.CLASS_NAME,
                    'click_value': 'menuSubItem',
                    'wait_after_click_by': By.CLASS_NAME,
                    'wait_after_click_value': 'Highlight'    
                },
            ]
            
            html = get_html_with_selenium_base(url, bfi_initial_wait, bfi_click_actions)
        elif is_NT:         
            nt_initial_wait = (By.CLASS_NAME, "c-event-card")
            nt_click_actions = None
            html = get_html_with_selenium(url, nt_initial_wait, nt_click_actions)
        elif is_SBC:
            sbc_initial_wait = (By.CLASS_NAME, "c-event-card")
            sbc_click_actions = None
            html = get_html_with_selenium(url, sbc_initial_wait, sbc_click_actions)
        elif is_RA:
            ra_initial_wait = (By.CLASS_NAME, "whats-on-listing__item")
            ra_click_actions = None
            html = get_html_with_selenium(url, ra_initial_wait, ra_click_actions)
        elif is_NPG:
            npg_initial_wait = (By.CLASS_NAME, "o-card-standard")
            npg_click_actions = None
            html = get_html_with_selenium(url, npg_initial_wait, npg_click_actions)
        elif is_RAH:
            rah_initial_wait = (By.CLASS_NAME, "event-item")
            rah_click_actions = None
            html = get_html_with_selenium_base(url, rah_initial_wait, rah_click_actions)
        elif is_RBO:
            rbo_initial_wait = (By.CLASS_NAME, "sc-4ax36u-1")
            rbo_click_actions = None
            html = get_html_with_selenium(url, rbo_initial_wait, rbo_click_actions)
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
    Scrapes events across multiple pages using multiprocessing.
    """
    all_found_events = []
    
    num_urls = len(start_urls_with_selectors)
    
    # Use ProcessPoolExecutor to leverage multiple CPU cores and avoid GIL issues
    # A common practice is to use a number of processes close to the number of CPU cores
    max_workers = os.cpu_count() or 1
    
    print(f"Starting scraping with up to {max_workers} concurrent processes for {num_urls} URLs.")

    # Run the web scraping function concurrently using processes
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # submit() and as_completed() are identical for both executors
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
                if events_from_page:
                    all_found_events.extend(events_from_page)
                    print(f"Successfully processed and got {len(events_from_page)} events from: {source_url}")
            except Exception as exc:
                print(f"Scraping {source_url} generated an exception: {exc}")

    print(f"Finished scraping. Total events collected before filtering: {len(all_found_events)}")
    return all_found_events