import os
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Constants from .env or directly from the environment
MICROSOFT_GRAPH_API_ENDPOINT = os.environ.get('MICROSOFT_GRAPH_API_ENDPOINT')
BOSSDESK_API_ENDPOINT = os.environ.get('BOSSDESK_API_ENDPOINT')
MICROSOFT_GRAPH_API_KEY = os.environ.get('MICROSOFT_GRAPH_API_KEY')
BOSSDESK_API_KEY = os.environ.get('BOSSDESK_API_KEY')




# Function to get new appointments from Microsoft Graph
def get_new_appointments():
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
    
    # Check if the request was successful
    if response.status_code == 200:
        return response.json().get('value', [])
    else:
        print(f"Error getting appointments: {response.status_code}")
        print(response.text)
        return []

# Function to create a service request in BOSSDesk
def create_service_request(appointment):
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
    
    # Check if the request was successful
    if response.status_code == 201:
        print(f"Service request created successfully: {response.json().get('id')}")
    else:
        print(f"Error creating service request: {response.status_code}")
        print(response.text)

# Function to map appointment details to service request fields
def map_appointment_to_service_request(appointment):
    # Extract and map necessary details from the appointment to the service request
    service_request = {
        'customerName': appointment.get('organizer', {}).get('emailAddress', {}).get('name'),
        'appointmentTime': appointment.get('start', {}).get('dateTime'),
        'staffMember': ', '.join([att.get('emailAddress', {}).get('name') for att in appointment.get('attendees', [])]),
        # Map other necessary fields
    }
    
    return service_request

# Main integration logic
def main():
    # Get new appointments from Microsoft Graph
    new_appointments = get_new_appointments()
    
    # For each new appointment, create a corresponding service request in BOSSDesk
    for appointment in new_appointments:
        create_service_request(appointment)

# Run the main integration logic
if __name__ == "__main__":
    main()
