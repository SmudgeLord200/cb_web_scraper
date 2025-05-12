import requests
from bs4 import BeautifulSoup
import spacy 
import json
import yagmail

def is_cate_blanchett_involved(text, nlp):
    """
    A more generic check for Cate Blanchett's involvement by looking at verbs
    associated with her name using SpaCy.
    """
    doc = nlp(text)
    name_parts = ["Cate", "Blanchett"]

    for i, token in enumerate(doc):
        if token.text == name_parts[0] and i + 1 < len(doc) and doc[i + 1].text == name_parts[1]:
            # Check for verbs in the dependency tree related to her name
            head_token = doc[i].head
            if head_token.pos_ == "VERB":
                return True
            if i > 0 and doc[i - 1].head.pos_ == "VERB":
                return True
            if i + 2 < len(doc) and doc[i + 2].head.pos_ == "VERB":
                return True

    # Check for "Blanchett" as a PERSON entity and look for nearby verbs
    for ent in doc.ents:
        if ent.label_ == "PERSON" and "Blanchett" in ent.text:
            # Check for verbs in the surrounding tokens
            window_start = max(0, ent.start - 2)
            window_end = min(len(doc), ent.end + 2)
            for i in range(window_start, window_end):
                if doc[i].pos_ == "VERB":
                    return True

    # Look for patterns like "Cate Blanchett [verb] ..." or "[verb] Cate Blanchett ..."
    for i in range(len(doc)):
        if doc[i].text == name_parts[0] and i + 1 < len(doc) and doc[i + 1].text == name_parts[1]:
            if i > 0 and doc[i - 1].pos_ == "VERB":
                return True
            if i < len(doc) - 2 and doc[i + 2].pos_ == "VERB":
                return True

    return False

def scrape_multiple_events_from_page(url, nlp, event_container_selector, title_selector, description_selector, link_selector, base_url=None):
    """
    Scrapes multiple events from a single page.
    """
    events = []
    try:
        res = requests.get(url)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

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
            
            is_involved = is_cate_blanchett_involved(description, nlp)

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

def send_event_email(subject, body, recipient_email, sender_email):
    """
    Sends an email using yagmail
    """
    try:
        yag = yagmail.SMTP(sender_email)
        yag.send(recipient_email, subject, body)
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
        
        # Two test links for sure is Cate related
        # ("https://www.barbican.org.uk/whats-on/2025/event/acting-screentalk-hosted-by-cate-blanchett", "main", "hgroup.heading-group", "div.component-section", "a", "https://www.barbican.org.uk"),
        # ("https://wwd.com/fashion-news/fashion-scoops/cate-blanchett-cohost-serpentine-summer-party-1237099478/", "div.lrv-u-width-100p", "h1.article-title", "div.a-content", "a", "https://wwd.com/fashion-news/fashion-scoops"),
    ]

    all_found_events = find_cate_blanchett_events_across_pages(start_urls_with_selectors, nlp)

    relevant_events = [event for event in all_found_events if event['is_involved']]

    if all_found_events:
        # print("\nAll Events Found on Initial Pages:")
        # for event in all_found_events:
        #     print(f"- Title: {event['title']}")
        #     print(f"  URL: {event['url']}")
        #     print(f"  Involved: {'Yes' if event['is_involved'] else 'No'}")
        #     print(f"  Description: {event['description']}")
        #     print("-" * 20)

        if relevant_events:
            print("\nRelevant Events Involving Cate Blanchett:")
            for event in relevant_events:
                print(f"- Title: {event['title']}")
                print(f"  URL: {event['url']}")
                print(f"  Description: {event['description']}")
                print("-" * 20)
            
            with open("cate_blanchett_events.json", "w") as f:
                json.dump(relevant_events, f, indent=4)
            print("\nRelevant events saved to cate_blanchett_events.json")
            
            # Email configuration
            recipient_email = "nicoleho1314@gmail.com"
            sender_email = "nicoleho1314@gmail.com"
            
            email_subject = "Cate Blanchett Events in London"
            email_body = "Here are the Cate Blanchett events found:\n\n" + json.dumps(relevant_events, indent=4)

            send_event_email(email_subject, email_body, recipient_email, sender_email)
        else:
            print("\nNo relevant events found.")    
    else:
        print("No events found during web scraping.")

if __name__ == "__main__":
    main()
