import requests
import os
import json

def extract_tags(description: str) -> list:
    """
    Calls the dedicated Cloud Function to extract tags.
    This keeps the main Flask app lightweight.
    """
    # Get the URL of your deployed Cloud Function from an environment variable
    function_url = os.environ.get('EXTRACT_TAGS_FUNCTION_URL')

    if not function_url:
        print("ERROR: EXTRACT_TAGS_FUNCTION_URL environment variable not set.")
        # Return a fallback or raise an error
        return ["tagging_service_unavailable"]

    try:
        headers = {"Content-Type": "application/json"}
        payload = {"description": description}

        response = requests.post(function_url, data=json.dumps(payload), headers=headers, timeout=10)

        # Raise an exception if the call failed
        response.raise_for_status() 

        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not call the extract_tags Cloud Function: {e}")
        return ["tagging_service_error"]