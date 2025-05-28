import json

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

def save_to_json(filepath, data):
    """
    Saves data to a JSON file.
    """
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4) # Store as list in JSON
    except IOError as e:
        print(f"Error saving data to {filepath}: {e}")

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