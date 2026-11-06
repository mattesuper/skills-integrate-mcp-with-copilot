import unittest
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from pydantic import ValidationError

from src.app import (
    activities, signup_for_activity, review_request, ApprovalDecision,
    AnnouncementInput, create_announcement, update_announcement,
    delete_announcement, unregister_from_activity,
)


class ActivityWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.original = deepcopy(activities)
        self.name = "Chess Club"
        self.activity = activities[self.name]
        self.email = "new@mergington.edu"

    def tearDown(self):
        activities.clear()
        activities.update(self.original)

    def test_signup_waits_for_approval(self):
        signup_for_activity(self.name, self.email)
        self.assertIn(self.email, self.activity["pending_requests"])
        self.assertNotIn(self.email, self.activity["participants"])
        with self.assertRaises(HTTPException):
            signup_for_activity(self.name, self.email)
        review_request(self.name, self.email, ApprovalDecision(decision="approve"))
        self.assertIn(self.email, self.activity["participants"])
        self.assertNotIn(self.email, self.activity["pending_requests"])
        with self.assertRaises(HTTPException):
            signup_for_activity(self.name, self.email)
        unregister_from_activity(self.name, self.email)
        self.assertNotIn(self.email, self.activity["participants"])

    def test_rejection_allows_reapplication(self):
        signup_for_activity(self.name, self.email)
        review_request(self.name, self.email, ApprovalDecision(decision="reject"))
        self.assertNotIn(self.email, self.activity["participants"])
        signup_for_activity(self.name, self.email)
        self.assertIn(self.email, self.activity["pending_requests"])

    def test_capacity_is_enforced_at_approval(self):
        self.activity["max_participants"] = len(self.activity["participants"]) + 1
        emails = [self.email, "other@mergington.edu"]
        for email in emails:
            signup_for_activity(self.name, email)

        def approve(email):
            try:
                review_request(self.name, email, ApprovalDecision(decision="approve"))
                return 200
            except HTTPException as error:
                return error.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(approve, emails)), [200, 409])
        self.assertEqual(len(self.activity["pending_requests"]), 1)

    def test_announcement_lifecycle(self):
        item = create_announcement(self.name, AnnouncementInput(title=" Meeting ", content=" Friday "))
        self.assertEqual(item["title"], "Meeting")
        self.assertIn(item, self.activity["announcements"])
        updated = update_announcement(self.name, item["id"],
                                      AnnouncementInput(title="Updated", content="Monday"))
        self.assertEqual(updated["content"], "Monday")
        self.assertEqual(updated["id"], item["id"])
        delete_announcement(self.name, item["id"])
        self.assertEqual(self.activity["announcements"], [])
        with self.assertRaises(HTTPException):
            delete_announcement(self.name, item["id"])

    def test_invalid_inputs_and_missing_records(self):
        with self.assertRaises(ValidationError):
            AnnouncementInput(title="  ", content="Message")
        with self.assertRaises(ValidationError):
            ApprovalDecision(decision="anything")
        with self.assertRaises(HTTPException) as missing:
            review_request(self.name, self.email, ApprovalDecision(decision="approve"))
        self.assertEqual(missing.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            create_announcement("Missing", AnnouncementInput(title="Title", content="Body"))


if __name__ == "__main__":
    unittest.main()