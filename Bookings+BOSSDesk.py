import os
import requests
import logging
import sys
import time
import json
from datetime import datetime
from dotenv import load_dotenv

#Implementing logging into script to handle log messages. Writes the logs to a file named integration.log
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('integration.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Retrieves token and refreshes when token expires (will be replaced in prod once client cert is implemented)
def get_token():
    url = os.environ.get('TOKEN_URL')
    payload = {
        'client_id': os.environ.get('CLIENT_ID'),
        'client_secret': os.environ.get('CLIENT_SECRET'),
        'scope': 'https://graph.microsoft.com/.default',
        'grant_type': 'client_credentials'
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # This will raise an exception for HTTP errors
        token_response = response.json()
        return token_response.get('access_token')
    except requests.RequestException as e:
        logger.error(f"Error getting token: {e}")
        return None  


# Constants from .env or directly from the environment
MICROSOFT_GRAPH_API_ENDPOINT = os.environ.get('MICROSOFT_GRAPH_API_ENDPOINT')
if not MICROSOFT_GRAPH_API_ENDPOINT:
    logger.error("MICROSOFT_GRAPH_API_ENDPOINT not set")
    sys.exit(1)
BOSSDESK_API_ENDPOINT = os.environ.get('BOSSDESK_API_ENDPOINT')
if not BOSSDESK_API_ENDPOINT:
    logger.error("BOSSDESK_API_ENDPOINT not set")
    sys.exit(1)
BOSSDESK_API_KEY = os.environ.get('BOSSDESK_API_KEY')
if not BOSSDESK_API_KEY:
    logger.error("BOSSDESK_API_KEY not set")
    sys.exit(1)


# Function to get existing tickets from BOSSDesk
def get_existing_tickets():
    # Set up the headers for the request to BOSSDesk API
    headers = {
        'Authorization': f'Bearer {BOSSDESK_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # Define the URL to get tickets
    url = f"{BOSSDESK_API_ENDPOINT}/tickets"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get('value', [])
    except requests.RequestException as e:
        logger.error(f"Error getting existing tickets: {e}")
        return []



# Function to get new appointments from Microsoft Graph
def get_new_appointments():
    try:
        # Get the token
        token = get_token()
        if not token:
            logger.error("Failed to get token")
            return []

        # Set up the headers for the request to Microsoft Graph API
        headers = {
            'Authorization': f'Bearer {token}',
        }

        # Get the business ID from the environment
        business_id = os.environ.get('MICROSOFT_BOOKINGS_BUSINESS_ID')

        # Define the URL to get appointments
        url = f"{MICROSOFT_GRAPH_API_ENDPOINT}/solutions/bookingBusinesses/{business_id}/appointments"
        
        # Send the request and get the response
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
        return response.json().get('value', [])
    
    #Checks to see if the request was successful
    except requests.RequestException as e:
        logger.error(f"Error getting appointments: {e}")
        return [] #Ensures a list is returned even in case of an exception


# Function to create a service request in BOSSDesk
def create_service_request(appointment):
    try:
        # Map appointment details to service request fields
        service_request = map_appointment_to_service_request(appointment)
        
        # Set up the headers for the request to BOSSDesk API
        headers = {
            'Authorization': f'Bearer {BOSSDESK_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Define the URL to create the ticket
        url = f"{BOSSDESK_API_ENDPOINT}/tickets"
        
        # Send the request and get the response
        logger.info(f"Service request payload: {json.dumps(service_request, indent=2)}")
        response = requests.post(url, headers=headers, data=json.dumps(service_request), verify=False) #remove verify=False in PROD to prevent man in middle attacks
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
        # Construct the description from appointment details
        description = f"Name: {appointment.get('customerName')}\n" \
                      f"Email: {appointment.get('customerEmailAddress')}\n" \
                      f"Phone: {appointment.get('customerPhone')}\n" \
                      f"Notes: {appointment.get('serviceNotes')}"

        # Extract the staff member's email or identifier
        booking_staff_member = appointment.get('bookingStaffMember')
        staff_email = appointment.get('bookingStaffMember').get('customerEmailAddress') if booking_staff_member else None

        service_request = {
            'ticket': {
                'title': appointment.get('serviceName'),
                'description': description,
                'type_id': 99,  # Replace with the actual type ID for the ticket
                'priority_id': 4,  # Replace with the actual priority ID for the ticket
                'agent_email': staff_email,  # This assumes that the agent can be identified by email in BOSSDesk
                'custom_fields': {
                    '75': appointment.get('id'),  # Microsoft Bookings appointment ID
                }
                # Add any other necessary fields
            }
        }
    except Exception as e:
        logger.error(f"Error mapping appointment to service request: {e}")
        return None
    else:
        return service_request



# Main integration logic
def main():
    iteration_count = 0 #Keeps track of iterations
    while True:
        iteration_count += 1
        try:
            logger.info(f"Starting iteration {iteration_count} of integration logic")

            # Fetch existing tickets to check against new appointments
            existing_tickets = get_existing_tickets()
            existing_appointment_ids = {ticket['custom_fields']['appointment_id'] for ticket in existing_tickets}

            new_appointments = get_new_appointments()
            logger.info(f"Retrieved {len(new_appointments)} new appointments")

            for index, appointment in enumerate(new_appointments, start=1):
                if appointment['id'] not in existing_appointment_ids:
                    logger.info(f"Creating service request for new appointment {index} of {len(new_appointments)}")
                    create_service_request(appointment)
                else:
                    logger.info(f"Appointment {index} already has a service request")
        except Exception as e:
            logger.error(f"Unexpected error in main function during iteration {iteration_count}: {e}")
        finally:
            logger.info(f"Ending iteration {iteration_count} of integration logic")

        time.sleep(300) #Introduces a 5-minute delay between iterations

if __name__ == "__main__":
    main()




