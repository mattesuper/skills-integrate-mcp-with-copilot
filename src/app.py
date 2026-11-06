"""
High School Management System API

A super simple FastAPI application that allows students to view and sign up
for extracurricular activities at Mergington High School.
"""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import os
from pathlib import Path
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from src.auth import login, logout, require_teacher

app = FastAPI(title="Mergington High School API",
              description="API for viewing and signing up for extracurricular activities")

app.post("/auth/login")(login)
app.post("/auth/logout", dependencies=[Depends(require_teacher)])(logout)
teacher_only = [Depends(require_teacher)]

# Mount the static files directory
current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(Path(__file__).parent,
          "static")), name="static")

# In-memory activity database
activities = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"]
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"]
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"]
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"]
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"]
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"]
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"]
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"]
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"]
    }
}


activity_lock = RLock()
for activity in activities.values():
    activity["pending_requests"] = []
    activity["announcements"] = []


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]


class AnnouncementInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=5000)


def find_activity(activity_name: str):
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activities[activity_name]


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def get_activities():
    return activities


@app.post("/activities/{activity_name}/signup", dependencies=teacher_only)
def signup_for_activity(activity_name: str, email: str):
    """Sign up a student for an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is not already signed up
    if email in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is already signed up"
        )

    with activity_lock:
        if email in activity["pending_requests"]:
            raise HTTPException(status_code=400, detail="Request is already pending")
        activity["pending_requests"].append(email)
    return {"message": f"Signup request for {email} is awaiting approval for {activity_name}"}


@app.patch("/activities/{activity_name}/requests", dependencies=teacher_only)
def review_request(activity_name: str, email: str, review: ApprovalDecision):
    with activity_lock:
        activity = find_activity(activity_name)
        if email not in activity["pending_requests"]:
            raise HTTPException(status_code=404, detail="Pending request not found")
        if review.decision == "approve":
            if len(activity["participants"]) >= activity["max_participants"]:
                raise HTTPException(status_code=409, detail="Activity is full")
            activity["participants"].append(email)
        activity["pending_requests"].remove(email)
    return {"message": f"Request for {email} {review.decision}d"}


@app.post("/activities/{activity_name}/announcements", status_code=201,
          dependencies=teacher_only)
def create_announcement(activity_name: str, announcement: AnnouncementInput):
    with activity_lock:
        activity = find_activity(activity_name)
        item = {"id": uuid4().hex, **announcement.model_dump(),
                "created_at": datetime.now(timezone.utc).isoformat()}
        activity["announcements"].insert(0, item)
    return item


@app.put("/activities/{activity_name}/announcements/{announcement_id}",
         dependencies=teacher_only)
def update_announcement(activity_name: str, announcement_id: str,
                        announcement: AnnouncementInput):
    with activity_lock:
        activity = find_activity(activity_name)
        for item in activity["announcements"]:
            if item["id"] == announcement_id:
                item.update(announcement.model_dump())
                return item
    raise HTTPException(status_code=404, detail="Announcement not found")


@app.delete("/activities/{activity_name}/announcements/{announcement_id}",
            dependencies=teacher_only)
def delete_announcement(activity_name: str, announcement_id: str):
    with activity_lock:
        activity = find_activity(activity_name)
        for item in activity["announcements"]:
            if item["id"] == announcement_id:
                activity["announcements"].remove(item)
                return {"message": "Announcement deleted"}
    raise HTTPException(status_code=404, detail="Announcement not found")


@app.delete("/activities/{activity_name}/unregister", dependencies=teacher_only)
def unregister_from_activity(activity_name: str, email: str):
    """Unregister a student from an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is signed up
    if email not in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is not signed up for this activity"
        )

    # Remove student
    activity["participants"].remove(email)
    return {"message": f"Unregistered {email} from {activity_name}"}
