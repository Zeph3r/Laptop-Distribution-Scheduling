# Laptop-Distribution-Scheduling
This repository contains a Python script for integrating Microsoft Graph with BOSSDesk to automate service request creation in BOSSDesk based on appointments scheduled in Microsoft Graph, ensuring seamless synchronization between the two services. Ideal for organizations seeking to streamline their service request workflows.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Usage](#usage)
- [Error Handling](#error-handling)
- [Logging](#logging)
- [Contributing](#contributing)
- [License](#license)

## Features

- Retrieves new appointments from Microsoft Bookings.
- Creates corresponding service requests in BOSSDesk.
- Maps appointment details to service request fields.

## Prerequisites

- Python 3.x
- A Microsoft Bookings account and a BOSSDesk account.
- Required Python libraries: `requests`, `python-dotenv`.

## Setup

1. Clone this repository to your local machine.
2. Install the required libraries:

```bash
pip install requests python-dotenv
```

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

