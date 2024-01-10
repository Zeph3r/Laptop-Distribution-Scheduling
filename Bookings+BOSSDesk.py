import os
import requests
import logging
import certifi
import sys
import time
import json
import concurrent.futures
from datetime import datetime
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from requests.exceptions import HTTPError, ConnectionError, Timeout, JSONDecodeError

#Implementing logging into script to handle log messages. Writes the logs to a file named integration.log
logging.basicConfig(level=logging.DEBUG,
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



def get_ticket_details(ticket_id, headers):
    try:
        ticket_detail_url = f"{BOSSDESK_API_ENDPOINT}/tickets/{ticket_id}"
        response = requests.get(ticket_detail_url, headers=headers, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching ticket {ticket_id}: {e}")
        return None

# Function to get existing tickets from BOSSDesk
def get_existing_tickets():
    headers = {
        'Authorization': f'Bearer {BOSSDESK_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    filter_url = f"{BOSSDESK_API_ENDPOINT}/tickets?q[title_eq]=IT%20support"
    try:
        filter_response = requests.get(filter_url, headers=headers, verify=False)
        filter_response.raise_for_status()
        filtered_tickets = filter_response.json()

        existing_appointment_ids = set()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_ticket_details, ticket['id'], headers) for ticket in filtered_tickets]
            for future in concurrent.futures.as_completed(futures):
                ticket_details = future.result()
                if ticket_details:
                    booking_id = ticket_details.get('custom_fields', {}).get('75')
                    if booking_id:
                        existing_appointment_ids.add(booking_id)

        return existing_appointment_ids

    except requests.RequestException as e:
        logger.error(f"Error fetching and processing tickets: {e}")
        return set()



# Function to get new appointments from Microsoft Graph
def get_new_appointments():
    try:
        # Get the token
        token = get_token()
        if not token:
            logger.error("Failed to get token")
            return []

        # Set up the headers for the request to Microsoft Graph API
        headers = {'Authorization': f'Bearer {token}'}

        # Get the business ID from the environment
        business_id = os.environ.get('MICROSOFT_BOOKINGS_BUSINESS_ID')

        # Define the URL to get appointments
        url = f"{MICROSOFT_GRAPH_API_ENDPOINT}/solutions/bookingBusinesses/{business_id}/appointments"

        # Send the request and get the response
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)

        logger.debug(f"Raw response from BOSSDesk API: {response.json()}")

        appointments = response.json().get('value', [])

        #Log the full details of each appointment
        for appointment in appointments:
            logger.info(f"Appointment data: {json.dumps(appointment, indent=2)}")
        
        return appointments
    
    except requests.RequestException as e:
        logger.error(f"Error getting appointments: {e}")
        return [] # Ensures a list is returned even in case of an exception


# Function to create a service request in BOSSDesk
def create_service_request(appointment):
    try:
        # Map appointment details to service request fields
        service_request = map_appointment_to_service_request(appointment)

        # If mapping was unsuccessful, skip creating the service request
        if not service_request:
            logger.warning("Failed to map appointment to service request")
            return

        # Set up the headers for the request to BOSSDesk API
        headers = {
            'Authorization': f'Bearer {BOSSDESK_API_KEY}',
            'Content-Type': 'application/json'
        }

        # Define the URL to create the ticket
        url = f"{BOSSDESK_API_ENDPOINT}/tickets"

        # Send the request and get the response
        logger.info(f"Service request payload: {json.dumps(service_request, indent=2)}")
        response = requests.post(url, headers=headers, data=json.dumps(service_request), verify=False)  # In PROD, remove verify=False
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)

        # Log successful service request creation
        if response.status_code == 201:
            logger.info(f"Service request created successfully: {response.json().get('id')}")
        
    except ConnectionError:
        logger.error("Network error occurred while creating service request")
    except Timeout:
        logger.error("Request timed out while creating service request")
    except JSONDecodeError:
        logger.error("Response JSON decoding failed")
    except HTTPError as e:
        logger.error(f"HTTP error occurred: {e}")
    except requests.RequestException as e:
        logger.error(f"Error creating service request: {e}")


def map_staff_id_to_agent_id(staff_id):
    staff_id_agent_id_map = json.loads(os.getenv('STAFF_ID_AGENT_ID_MAP', '{}'))
    return staff_id_agent_id_map.get(staff_id, None) # Returns none if mapping is not found. 

def extract_username_from_email(email):
    if email and '@gmh.edu' in email:
        return email.split('@')[0]
    else:
        # Log a warning if the email format is invalid or not provided
        logger.warning(f"Invalid or missing email: {email}")
        return None

# Searches BOSSDesk for a user by username and returns their friendly_id.   
def find_user_id(username):
    query_params = {'q[username_eq]': username}
    url = f"{BOSSDESK_API_ENDPOINT}/users"

    headers = {
        'Authorization': f'Bearer {BOSSDESK_API_KEY}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers, params=query_params, verify=False)
        response.raise_for_status()
        users = response.json()
        if users:
            return users[0].get('friendly_id')
        else:
            logger.warning(f"No user found for username: {username}")
            return None
    except requests.RequestException as e:
        logger.error(f"Error searching for user by username: {e}")
        return None



def get_requester_id_by_email(email):
    if not email:
        logger.warning("Email not provided for fetching requester_id")
        return None

    try:
        url = f"{BOSSDESK_API_ENDPOINT}/users?q[email_eq]={email}"
        headers = {
            'Authorization': f'Bearer {BOSSDESK_API_KEY}',
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        users = response.json()
        if users:
            return users[0].get("id")
        else:
            logger.warning(f"No user found with email: {email}")
            return None
    except requests.RequestException as e:
        logger.error(f"Error fetching requester_id by email: {e}")
        return None

    
# Function to map appointment details to service request fields
def map_appointment_to_service_request(appointment):
    try:
        # Assuming 'customers' is always present and has at least one customer.
        customer = appointment['customers'][0]  # Get the first customer
        custom_questions = customer.get('customQuestionAnswers', [])
        
        # Define a dictionary for question ID to variable mappings
        question_mappings = {
            os.getenv('EMPLOYEE_NAME_QUESTION_ID'): 'employee_name',
            os.getenv('EMPLOYEE_EMAIL_QUESTION_ID'): 'employee_email',
            os.getenv('EMPLOYEE_PHONE_QUESTION_ID'): 'employee_phone',
            os.getenv('EMPLOYEE_TYPE_QUESTION_ID'): 'employee_type',
            os.getenv('EMPLOYEE_MANAGER_QUESTION_ID'): 'employee_manager',
            os.getenv('EMPLOYEE_MANAGER_EMAIL_QUESTION_ID'): 'employee_manager_email'
        }

        # Initialize variables for custom fields
        customer_details = {key: 'Not Provided' for key in question_mappings.values()}

        # Iterate through custom questions and map answers
        for question in custom_questions:
            question_id = question.get('questionId')
            if question_id in question_mappings:
                customer_details[question_mappings[question_id]] = question.get('answer', 'Not Provided')

               
        # Construct the description from appointment details
        description_parts = [f"<b>{label}</b> {customer_details[key]}" for key, label in {
            'employee_manager': "Manager Name",
            'employee_manager_email': "Manager Email",
            'employee_name': "Name",
            'employee_phone': "Phone Number",
            'employee_email': "Email",
            'employee_type': "Employee Type"
        }.items()]
        description_parts.append(f"<h3>Special Instructions</h3><br> {appointment.get('serviceNotes', 'No Additional Notes').split('TeamsMeetingSeparator')[0].strip()}")
        description = "<br><br>".join(description_parts)
        
        # Extract the staff member's email or identifier
        booking_staff_member = appointment.get('bookingStaffMember')
        staff_email = booking_staff_member.get('customerEmailAddress') if booking_staff_member else None

        # Extract staff member ID from the appointment
        staff_member_id = appointment.get('staffMemberIds', [])[0] if appointment.get('staffMemberIds') else None

        if staff_member_id:
            # Map staff member ID to agent ID in BOSSDesk
            agent_id = map_staff_id_to_agent_id(staff_member_id)
        else:
            logger.warning("No staff member ID found in the appointment")

        # Extracting username from employee's email
        employee_username = extract_username_from_email(customer_details['employee_email'])

        # Fetch requester_id based on employee email
        requester_id = None
        if employee_username:
            requester_id = find_user_id(employee_username)
            if not requester_id:
                logger.warning(f"Could not find requester_id for username: {employee_username}")
            else:
                logger.warning("Employee username could not be extracted from email")
        
        # Contructing the service request with the new requester ID
        service_request = {
            'ticket': {
                'title': appointment.get('serviceName'),
                'description': description,
                'type_id': 99,  # Service Request (#SR) type ID
                'category_id': 34,  # Ticket category "Technical Support - Hardware - Laptop"
                'team_id': 48,
                'priority_id': 4,
                'custom_fields': {
                    '75': appointment.get('id'),  # Microsoft Bookings appointment ID
                },
                'agent_id': agent_id,
                'requester_id': requester_id      
            }
        }
        

    except Exception as e:
        logger.error(f"Error mapping appointment to service request: {e}")
        return None
    else:
        return service_request


# Main integration logic
def main():
    iteration_count = 0
    while True:
        iteration_count += 1
        try:
            logger.info(f"Starting iteration {iteration_count} of integration logic")

            # Fetch existing booking IDs to check against new appointments
            existing_appointment_ids = get_existing_tickets()

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

        time.sleep(300)  # Introduces a 5-minute delay between iterations

if __name__ == "__main__":
    main()

