import os
import requests
import logging
import sys
import time
import json
from datetime import datetime
from dotenv import load_dotenv
from requests.exceptions import HTTPError, ConnectionError, Timeout, JSONDecodeError

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
        tickets = response.json().get('value', [])
        existing_appointment_ids = {ticket['custom_fields']['75'] for ticket in tickets if '75' in ticket['custom_fields']}

        # Verbose logging of API response
        logger.debug(f"BOSSDesk API Response: {response.text}")

        return existing_appointment_ids
    
    except requests.RequestException as e:
        logger.error(f"Error getting existing tickets: {e}")
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
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
        
        appointments = response.json().get('value', [])

        #Log the full details of each appointment
        for appointment in appointments:
            logger.debug(f"Appointment data: {json.dumps(appointment, indent=2)}")
        
        return appointments
    
    except requests.RequestException as e:
        logger.error(f"Error getting appointments: {e}")
        return [] # Ensures a list is returned even in case of an exception



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
        
    except ConnectionError:
        logger.error("Network error occurred while creating service request")
    except Timeout:
        logger.error("Request timed out while creating service request")
    except JSONDecodeError:
        logger.error("Response JSON decoding failed")
    except HTTPError as e:
        if e.response.status_code == 429:
            logger.error("Rate limit exceeded")
        elif e.response.status_code >= 500:
            logger.error("Server error occurred")
        else:
            logger.error(f"HTTP error occurred: {e}")
    except requests.RequestException as e:
        logger.error(f"Error creating service request: {e}")
    else:
        # Check if the request was successful (this is now redundant due to raise_for_status but kept for clarity)
        if response.status_code == 201:
            logger.info(f"Service request created successfully: {response.json().get('id')}")
        else:
            logger.error(f"Unexpected status code: {response.status_code}")


def map_staff_id_to_agent_id(staff_id):
    staff_id_agent_id_map = json.loads(os.getenv('STAFF_ID_AGENT_ID_MAP', '{}'))
    return staff_id_agent_id_map.get(staff_id, None) # Returns none if mapping is not found. 

def extract_username_from_email(email):
    if '@gmh.edu' in email:
        return email.split('@')[0]
    else:
        logger.warning(f"Invalid email format: {email}")
        return None

    
# Function to map appointment details to service request fields
def map_appointment_to_service_request(appointment):
    try:
        # Assuming 'customers' is always present and has at least one customer.
        customer = appointment['customers'][0]  # Get the first customer
        custom_questions = customer.get('customQuestionAnswers', [])
        
        # Initialize variables for custom fields
        employee_name = 'Not Provided'
        employee_email = 'Not Provided'
        employee_phone = 'Not Provided'
        employee_manager = 'Not Provided'
        employee_manager_phone = 'Not Provided'
        employee_type = 'Not Provided'
        employee_id = None

        #Initialize enviroment variables for customQuestion IDs
        employee_name_question_id = os.getenv('EMPLOYEE_NAME_QUESTION_ID')
        employee_email_question_id = os.getenv('EMPLOYEE_EMAIL_QUESTION_ID')
        employee_phone_question_id = os.getenv('EMPLOYEE_PHONE_QUESTION_ID')
        employee_type_question_id = os.getenv('EMPLOYEE_TYPE_QUESTION_ID')
        employee_manager_question_id = os.getenv('EMPLOYEE_MANAGER_QUESTION_ID')
        employee_manager_phone_question_id = os.getenv('EMPLOYEE_MANAGER_PHONE_QUESTION_ID')
        employee_id_question_id = os.getenv('EMPLOYEE_ID_NUMBER_ID')
        employee_username = extract_username_from_email(employee_email)
        #manager_username = extract_username_from_email(manager_email)


        # Iterate through custom questions and map answers
        for question in custom_questions:
            question_id = question.get('questionId')
            answer = question.get('answer')

            if question_id == employee_manager_question_id:
                employee_manager = answer
            elif question_id == employee_manager_phone_question_id:
                employee_manager_phone = answer
            elif question_id == employee_name_question_id:
                employee_name = answer
            elif question_id == employee_phone_question_id:
                employee_phone = answer
            elif question_id == employee_email_question_id:
                employee_email = answer
                logger.debug(f"Extracted employee email: {employee_email}")
            elif question_id == employee_type_question_id:
                employee_type = answer
            elif question_id == employee_id_question_id:
                employee_id = answer
                   
                
        # Construct the description from appointment details
        description = f"<b>Manager Name</b> {employee_manager}<br><b>Manager Phone Number</b> {employee_manager_phone}<br><br><br><b>Name:</b> {employee_name}<br><b>Phone Number:</b> {employee_phone}<br><b>Email:</b> {employee_email}<br><b>Employee Type:</b> {employee_type}<br><br><br><h3>Special Instructions</h3><br> {appointment.get('serviceNotes', 'No Additional Notes').split('TeamsMeetingSeparator')[0].strip()}" 

        # Add conditional logging for missing data
        if employee_name == 'Not Provided':
            logger.warning("Employee name is missing in appointment data")
        if employee_email == 'Not Provided':
            logger.warning("Employee email is missing in appointment data")
        if employee_phone == 'Not Provided':
            logger.warning("Employee phone number is missing in appointment data")

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
                'requester': {
                    "username": employee_username
                    
                }
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




