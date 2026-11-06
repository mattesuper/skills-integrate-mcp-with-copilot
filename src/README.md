# Mergington High School Activities API

A simple FastAPI application with public activity listings and teacher-managed registrations.

## Features

- View all available extracurricular activities
- Teacher login/logout and teacher-only registration management
- Pending signup requests with teacher approval or rejection
- Teacher-managed activity announcements

## Getting Started

1. Install the dependencies:

   ```
   python -m pip install -r requirements.txt
   ```

2. From the repository root, assign a teacher account:

   ```
   python -m src.auth teacher
   ```

   Enter and confirm a password when prompted. This command also resets existing
   accounts; no account-management page is provided. Usernames and salted
   PBKDF2-SHA256 password hashes are stored in the backend-only
   `src/teachers.json`, not in the static directory. The checked-in file is empty:
   there are no default credentials. Do not commit populated account files or
   share passwords in issues or pull requests.

3. Run the application from the repository root:

   ```
   python -m uvicorn src.app:app --reload
   ```

4. Open http://localhost:8000. Use the user icon in the top-right corner,
   select **Log in**, and enter the assigned teacher credentials.

   Students do not log in and can still view activities and participants.
   Teachers can submit registration requests, approve/reject pending requests,
   and remove approved participants. Pending requests do not consume seats.
   Announcement management is available through the authenticated API.

   API documentation:
   - API documentation: http://localhost:8000/docs
   - Alternative documentation: http://localhost:8000/redoc

## API Endpoints

| Method | Endpoint                                                          | Description                                                         |
| ------ | ----------------------------------------------------------------- | ------------------------------------------------------------------- |
| GET    | `/activities`                                                     | Get all activities with their details and current participant count |
| POST   | `/auth/login` | Exchange a JSON username/password for an eight-hour bearer token |
| POST   | `/auth/logout` | Revoke the current teacher session |
| POST   | `/activities/{activity_name}/signup?email=student@mergington.edu` | Teacher: create a pending registration request |
| PATCH  | `/activities/{activity_name}/requests?email=student@mergington.edu` | Teacher: approve or reject with `{"decision": "approve"}` or `{"decision": "reject"}` |
| DELETE | `/activities/{activity_name}/unregister?email=student@mergington.edu` | Teacher: remove an approved participant |
| POST   | `/activities/{activity_name}/announcements` | Teacher: create an announcement with JSON title/content |
| PUT    | `/activities/{activity_name}/announcements/{announcement_id}` | Teacher: edit an announcement |
| DELETE | `/activities/{activity_name}/announcements/{announcement_id}` | Teacher: delete an announcement |

Protected API calls require `Authorization: Bearer <access_token>`. The browser
keeps the token only in memory (not local storage or cookies); refreshing the
page requires logging in again. Logout revokes the token on the server, and
sessions expire after eight hours. Restarting the server clears all sessions;
restart after resetting passwords. Use HTTPS outside local development.
This in-memory demo supports a single server process, not multiple workers.

## Tests

From the repository root:

```
python -m unittest discover -s tests -v
node --check src/static/app.js
```

Tests use temporary accounts and a local HTTP server; they do not modify assigned
teacher credentials.

## Data Model

The application uses a simple data model with meaningful identifiers:

1. **Activities** - Uses activity name as identifier:

   - Description
   - Schedule
   - Maximum number of participants allowed
   - List of student emails who are signed up

2. **Students** - Uses email as identifier:
   - Name
   - Grade level

All data is stored in memory, which means data will be reset when the server restarts.
