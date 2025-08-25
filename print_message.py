def print_event_details(events, message_prefix=""):
    """
    Prints the details of a list of events to the console.

    Args:
        events (list): A list of event dictionaries.
        message_prefix (str): A string to print before the event details.
    """
    if not events:
        return
    print(f"\n{message_prefix}:")
    for event in events:
        print(f"- Title: {event['title']}")
        print(f"  URL: {event['url']}")
        print(f"  Description: {event['description']}")
        print("-" * 20)