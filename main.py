import spacy 
import json
from data_storage import load_notified_event_urls, load_recipients_from_file, save_to_json
from email_notification import send_event_email
from print_message import print_event_details
from scraper import find_cate_blanchett_events_across_pages

NOTIFIED_EVENTS_FILE = "notified_event_urls.json"
EVENT_FILE = "cate_blanchett_events.json"
RECIPIENTS_FILE = "recipients.json"
SENDER_EMAIL = "nicoleho1314@gmail.com"

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

    # Call the web scaper function
    all_found_events = find_cate_blanchett_events_across_pages(start_urls_with_selectors, nlp)
    if not all_found_events:
        print("No events found during web scraping.")
        return

    # Extract relevant events
    current_relevant_events = [event for event in all_found_events if event['is_involved']]
    if not current_relevant_events:
        print("No relevant events involving Cate Blanchett found in this run.")
        return

    # Filter out events that have already been notified
    previously_notified_urls = load_notified_event_urls(NOTIFIED_EVENTS_FILE)
    newly_relevant_events = [
        event for event in current_relevant_events
        if event['url'] not in previously_notified_urls
    ]

    # Save all *currently* relevant events (new and old) to cate_blanchett_events.json for a complete snapshot
    if current_relevant_events:
        print_event_details(current_relevant_events, f"Found {len(current_relevant_events)} relevant events involving Cate Blanchett (new and previously seen)")
        save_to_json(EVENT_FILE, current_relevant_events)
        print(f"All currently relevant events saved to {EVENT_FILE}")

    if newly_relevant_events:
        print_event_details(newly_relevant_events, f"Found {len(newly_relevant_events)} NEW relevant events involving Cate Blanchett")

        # Email configuration
        recipient_email_list = load_recipients_from_file(RECIPIENTS_FILE)

        if not recipient_email_list:
            print("Warning: No recipient emails loaded. Email will not be sent.") 

        email_subject = "New Cate Blanchett Event(s) Found"
        email_body = "The following new Cate Blanchett events were found:\n\n" + json.dumps(newly_relevant_events, indent=4)

        send_event_email(email_subject, email_body, recipient_email_list, SENDER_EMAIL)

        # Update the set of notified URLs and save it
        for event in newly_relevant_events:
            previously_notified_urls.add(event['url'])
        save_to_json(NOTIFIED_EVENTS_FILE, list(previously_notified_urls))
    else:
        print("\nNo NEW relevant events found since last check.")

if __name__ == "__main__":
    main()
