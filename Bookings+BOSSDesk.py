import os
import requests
import logging
import sys
from datetime import datetime
from dotenv import load_dotenv

#Implementing logging into script to handle log messages in the script
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('integration.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Constants from .env or directly from the environment
MICROSOFT_GRAPH_API_ENDPOINT = os.environ.get('MICROSOFT_GRAPH_API_ENDPOINT')
if not MICROSOFT_GRAPH_API_ENDPOINT:
    logger.error("MICROSOFT_GRAPH_API_ENDPOINT not set")
    sys.exit(1)
BOSSDESK_API_ENDPOINT = os.environ.get('BOSSDESK_API_ENDPOINT')
if not BOSSDESK_API_ENDPOINT:
    logger.error("BOSSDESK_API_ENDPOINT not set")
    sys.exit(1)
MICROSOFT_GRAPH_API_KEY = os.environ.get('MICROSOFT_GRAPH_API_KEY')
if not MICROSOFT_GRAPH_API_KEY:
    logger.error("MICROSOFT_GRAPH_API_KEY not set")
    sys.exit(1)
BOSSDESK_API_KEY = os.environ.get('BOSSDESK_API_KEY')
if not BOSSDESK_API_KEY:
    logger.error("BOSSDESK_API_KEY not set")
    sys.exit(1)


# Function to get new appointments from Microsoft Graph

def get_new_appointments():
    try:
        # Set up the headers for the request to Microsoft Graph API
        headers = {
            'Authorization': f'Bearer {MICROSOFT_GRAPH_API_KEY}',
        }

        # Get the business ID from the environment
        business_id = os.environ.get('MICROSOFT_BOOKINGS_BUSINESS_ID')

        # Define the URL to get appointments
        url = f"{MICROSOFT_GRAPH_API_ENDPOINT}/solutions/bookingBusinesses/{business_id}/appointments"
        
        # Send the request and get the response
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
        
    except requests.RequestException as e:
        logger.error(f"Error getting appointments: {e}")
        return []
    else:
        # Check if the request was successful (this is now redundant due to raise_for_status but kept for clarity)
        if response.status_code == 200:
            return response.json().get('value', [])
        else:
            logger.error(f"Unexpected status code: {response.status_code}")
            return []

# Function to create a service request in BOSSDesk
def create_service_request(appointment):
    try:
        # Map appointment details to service request fields
        service_request = map_appointment_to_service_request(appointment)
        
        # Set up the headers for the request to BOSSDesk API
        headers = {
            'Authorization': f'ApiKey {BOSSDESK_API_KEY}',
        }
        
        # Define the URL to create service requests
        url = f"{BOSSDESK_API_ENDPOINT}/service_requests"
        
        # Send the request and get the response
        response = requests.post(url, headers=headers, json=service_request)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
        
    except requests.RequestException as e:
        logger.error(f"Error creating service request: {e}")
    else:
        # Check if the request was successful (this is now redundant due to raise_for_status but kept for clarity)
        if response.status_code == 201:
            logger.info(f"Service request created successfully: {response.json().get('id')}")
        else:
            logger.error(f"Unexpected status code: {response.status_code}")


# Function to map appointment details to service request fields
def map_appointment_to_service_request(appointment):
    try:
        # Extract and map necessary details from the appointment to the service request
        service_request = {
            'customerName': appointment.get('organizer', {}).get('emailAddress', {}).get('name'),
            'appointmentTime': appointment.get('start', {}).get('dateTime'),
            'staffMember': ', '.join([att.get('emailAddress', {}).get('name') for att in appointment.get('attendees', [])]),
            # Map other necessary fields
        }
    except Exception as e:
        logger.error(f"Error mapping appointment to service request: {e}")
        return None  
    else:
        return service_request 


# Main integration logic
def main():
    try:
        logger.info("Starting integration logic")
        
        # Get new appointments from Microsoft Graph
        new_appointments = get_new_appointments()
        
        # For each new appointment, create a corresponding service request in BOSSDesk
        for appointment in new_appointments:
            create_service_request(appointment)
            
    except Exception as e:
        logger.error(f"Unexpected error in main function: {e}")
        
    finally:
        logger.info("Ending integration logic")

# Run the main integration logic
if __name__ == "__main__":
    try:
        logger.info("Script started")
        main()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        logger.info("Script ended")


