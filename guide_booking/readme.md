

#### 1.  **Initiating a Booking Request**

A tourist can request a guide in two main ways by making a `POST` request to the `/guides/request-assignment` endpoint:

* **From an Itinerary:** The tourist provides an `itinerary_id`. The system then automatically infers the **location**, **dates**, and required **specialties** by analyzing the tags of all the Points of Interest (POIs) in that itinerary.
* **For a Specific Leg/Segment:** A tourist can book a guide for just a part of their trip by specifying which `segments` (e.g., Day 1, POI name) they need a guide for.

#### 2.  **Finding and Filtering Eligible Guides**

Once a request is made, the system automatically finds the best guide:

* **Initial Filtering:** It queries the Firestore database for guides who are **approved** and whose `regions_covered` includes the tourist's trip location.
* **Availability Check:** Crucially, it then checks for scheduling conflicts. It queries the `bookings` collection to find which of these guides are already booked for the requested dates and filters them out. This ensures a guide is actually available.

#### 3.  **Scoring and Assigning the Best Match**

Instead of notifying all matched guides, the system **scores** the available guides to find the single best match for the tourist. The scoring is based on:

* ⭐ **Average Rating** (heavily weighted)
* 📜 **Total Tours Completed** (experience)
* 🗣️ **Matching Languages**
* 🎨 **Matching Specialties** (derived from itinerary tags)

The guide with the highest score is **automatically assigned** to the booking request.

#### 4.  **Booking and Confirmation Flow**

* A new booking document is created with a status of **`pending_acceptance`**.
* The tourist's itinerary is updated to link to this booking.
* The assigned guide would then need to accept or reject this request (though the logic for the guide's action is not yet implemented in the provided code).

***

After updates:
---
# LokPath Guide Booking System: Technical Deep Dive

This document outlines the architecture and workflow of the automated guide booking and assignment system.

## 📌 Core Concept: The Automated Assignment Workflow

The system is designed to find the best-matched, available guide for a tourist's itinerary and manage the booking process from request to confirmation. It operates on a "cascading" or "waterfall" model: the request is offered to the best guide first, and if they reject or time out, it automatically moves to the next-best guide, and so on, until the booking is accepted or no guides are left.

This entire process is automated through a combination of Flask API endpoints and event-driven Google Cloud Functions.

## 🗺️ The End-to-End Booking Flow

Here is the step-by-step journey of a guide booking request:

### **Step 1: Tourist Submits a Request**

A tourist initiates a booking by sending a `POST` request to the `/guides/request-assignment` endpoint.

* **Functionality:** This endpoint is the entry point for all guide requests.
* **Key Logic:**
    1.  **Request Cut-off:** It first checks if the trip's start date is less than 48 hours away. If so, it rejects the request to prevent last-minute failures.
    2.  **Find All Eligible Guides:** It queries the database to find all `approved` guides who cover the trip's location.
    3.  **Check Availability:** It filters out any guides who are already booked for the requested dates.
    4.  **Score and Rank:** It scores all the remaining, available guides based on their rating, experience, and matching specialties (inferred from the itinerary's POI tags).
    5.  **Create Booking Document:** Instead of assigning a guide directly, it creates a new document in the `bookings` collection with:
        * A status of `pending_assignment`.
        * A new field, `potential_guides`, which contains the **full, sorted list** of all matched guide UIDs, from highest score to lowest.

---

### **Step 2: Initial Assignment (Cloud Function)**

The creation of the new booking document in Firestore automatically triggers our first Cloud Function.

* **Function:** `assign_guide_to_booking` in `functions/main.py`.
* **Trigger:** `on_document_created` in the `bookings` collection.
* **Key Logic:**
    1.  It reads the `potential_guides` list from the new booking document.
    2.  It takes the **first guide** from the list (the highest-scoring one).
    3.  It updates the booking document's status to `pending_acceptance`.
    4.  It sets the `assigned_guide_uid` to the selected guide's ID.
    5.  It sets a `guide_response_deadline` of **60 minutes** from the current time.
    6.  (Future Work) It sends a push notification to the assigned guide's device.

---

### **Step 3: The Guide's Decision**

The assigned guide now has 60 minutes to respond. They do this by calling one of two new API endpoints from their app.

* **Accepting the Trip:**
    * **Endpoint:** `POST /guides/bookings/<booking_id>/accept`.
    * **Action:** This changes the booking status to `accepted`. The process stops here. The tourist is notified, and the booking is confirmed.

* **Rejecting the Trip:**
    * **Endpoint:** `POST /guides/bookings/<booking_id>/reject`.
    * **Action:** This changes the booking status to `rejected_by_guide`. This status change is critical, as it triggers the next step in the automation.

---

### **Step 4: Re-assignment or Timeout (Cloud Functions)**

Two scenarios can happen if the guide doesn't accept the trip: they actively reject it, or they simply don't respond in time. Our system handles both automatically.

* **Function (Rejection):** `handle_booking_rejection` in `functions/main.py`.
* **Trigger:** `on_document_updated` in the `bookings` collection, specifically watching for the status to become `rejected_by_guide` or `timed_out`.
* **Key Logic:**
    1.  It identifies the guide who just rejected the booking.
    2.  It finds that guide in the `potential_guides` list and looks for the **next guide** in sequence.
    3.  If another guide exists, it re-runs the logic from **Step 2**: it assigns the trip to the new guide, updates the `assigned_guide_uid`, and sets a fresh 60-minute deadline.
    4.  If there are no more guides in the list, it updates the booking status to `failed` and notifies the tourist.

* **Function (Timeout & Reminders):** `check_booking_status` in `functions/main.py`.
* **Trigger:** This is a **scheduled function** that runs automatically every 5 minutes.
* **Key Logic:**
    1.  It queries for all bookings with a status of `pending_acceptance`.
    2.  **Reminders:** If a guide's deadline is approaching (at the 30-minute and 5-minute marks), it sends them a reminder notification.
    3.  **Timeout:** If it finds a booking where the `guide_response_deadline` has passed, it automatically updates the booking status to `timed_out`. This change then triggers the `handle_booking_rejection` function to move on to the next guide.

## ✅ Summary: Why the New Code is Better

Your concern about the reduced line count is valid, but here’s why it’s an improvement:

* **No Lost Functionality:** All original features—finding guides, scoring them, and checking availability—are still present in the `/guides/request-assignment` route. The code is shorter because it no longer tries to handle the entire assignment process itself.
* **Increased Robustness:** The old system would fail if the single best guide was busy or didn't want the trip. The new system automatically tries the next best guide, and the next, making it far more likely a tourist will find a match.
* **Scalability & Efficiency:** By offloading the assignment and timeout logic to serverless Cloud Functions, your main application remains fast and responsive. It simply takes the request and moves on, letting the background functions handle the rest.
* **New Features Added:**
    * Guides can now **accept or reject** trips.
    * The system automatically handles **rejections and timeouts**.
    * **Booking deadlines** prevent requests from sitting in limbo forever.
    * **Reminder notifications** improve guide response times.

This new, distributed architecture is a significant upgrade that makes the guide booking feature more powerful, reliable, and user-friendly for both tourists and guides.