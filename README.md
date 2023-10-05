# Laptop-Distribution-Scheduling
This repository hosts a daemon-based Python script tailored for bridging Microsoft Graph with BOSSDesk, to autonomously spawn service requests in BOSSDesk triggered by new appointments scheduled in Microsoft Bookings. This integration aims at bolstering operational fluidity between the two platforms, a boon for entities eyeing streamlined service request management.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Setup](#setup)
- [Usage](#usage)
- [Error Handling](#error-handling)
- [Logging](#logging)
- [Security](#security)
- [License](#license)

## Features

- Seamless retrieval of fresh appointments from Microsoft Bookings.
- Automatic generation of corresponding service requests in BOSSDesk.
- Agile mapping of appointment intricacies to service request fields.

## Prerequisites

- Python 3.x
- Active accounts on Microsoft Bookings and BOSSDesk.
- Essential Python libraries: `requests`, `python-dotenv`.

## Configuration

- Obtain and configure OAuth 2.0 credentials from Azure AD for authenticating requests to Microsoft Graph.
- Configure the necessary API permissions and ensure Admin Consent is granted for the necessary scopes in Azure AD.
- Update the `.env` file with your credentials and endpoint information.

## Setup

1. Clone this repository to your local machine.
2. Navigate to the project directory.
3. Install the required libraries via pip:

```bash
pip install requests python-dotenv
```

## Usage
1. Once the setup and configuration are complete, run the script using:
```bash
python main.py
```
This will initiate the process of syncing new appointments from Microsoft Bookings to BOSSDesk.

## Error Handling 

- The script is equipped with basic error handling to manage common issues that may arise during the API requests.
- Logging is implemented to track the operation over time, which can be invaluable for diagnosing issues.

## Logging

- Logging is embedded within the script to capture its operation chronology, assisting in issue diagnosis.

## Security

- Sensitive information such as API keys and credentials are securely housed in a .env file, ensuring they are not exposed publicly.
- Ensure the .env file is included in your .gitignore to prevent accidental exposure.
## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

