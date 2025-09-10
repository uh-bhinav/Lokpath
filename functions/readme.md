

# LokPath Cloud Functions: The Automated Backend Brain

This document provides a complete breakdown of the serverless Cloud Functions that power the automated, real-time features of the LokPath application.

## What Are Cloud Functions? (A Simple Analogy)

Imagine you have a series of super-smart robots working for your app 24/7. Each robot has one specific job it's an expert at. You don't have to turn them on or off; they are always waiting for something to happen.

* When a user uploads a photo, one robot wakes up, processes the image, and then goes back to sleep.
* When a guide booking is created, another robot wakes up, finds the best guide, and goes back to sleep.

These "robots" are our **Cloud Functions**. They are small, independent pieces of code that run automatically in the cloud in response to specific events (like a database change or a file upload). This makes our main application faster and allows us to build powerful, automated workflows without managing a traditional server.

---

## Part 1: Content Management & Moderation Functions

These functions handle everything related to user-uploaded images, from creating thumbnails to ensuring the content is safe for the community.

### 1. `process_uploaded_image`

* **Job:** To automatically create thumbnail versions of every new image.
* **Trigger:** This function runs whenever a new file is successfully uploaded to our app's Google Cloud Storage.
* **How it Works:**
    1.  **Safety Checks:** The function first checks if the uploaded file is actually an image and not something else. It also ignores files that are already thumbnails to avoid processing them again.
    2.  **HEIC Conversion:** Many modern phones (especially iPhones) save photos in a format called HEIC. This function automatically converts any `.heic` file into a standard `.jpeg` format that can be displayed everywhere.
    3.  **Resizing:** It then creates multiple smaller versions (thumbnails) of the image, for example, a `small` (200x200) and `medium` (800x800) version. This is crucial for making the app load quickly on phones.
    4.  **Database Update:** Finally, it finds the correct document in our Firestore database that corresponds to the uploaded image and adds the URLs of the new thumbnails to it. This allows the app to easily find and display the right-sized image.

### 2. `moderate_uploaded_image`

* **Job:** To check every new image for inappropriate (NSFW) content.
* **Trigger:** Just like the thumbnail function, this also runs whenever a new image is uploaded to Cloud Storage.
* **How it Works:**
    1.  **Google Cloud Vision API:** The function sends the newly uploaded image to Google's powerful Vision AI.
    2.  **Safe Search Analysis:** The Vision AI analyzes the image for sensitive content, specifically looking for things like "adult" material or "violence".
    3.  **Flagging:** If the AI determines that the image is `LIKELY` or `VERY_LIKELY` to contain unsafe content, the function flags it.
    4.  **Database Update:** It then updates the image's document in Firestore, adding a new field called `moderation_status`. This field is set to either `APPROVED` or `REJECTED` based on the AI's analysis. If rejected, it also stores the reason why (e.g., `['ADULT']`). This allows the app to automatically hide inappropriate images from other users.

### 3. `update_guide_rating`

* **Job:** To keep a guide's average rating perfectly up-to-date.
* **Trigger:** This function runs whenever a new review document is created for a guide in Firestore (specifically at the path `guides/{guideId}/reviews/{reviewId}`).
* **How it Works:**
    1.  **Triggered by Review:** When a tourist submits a review for a guide, the app saves it to the guide's `reviews` subcollection. This action instantly triggers the function.
    2.  **Recalculation:** The function reads *all* the reviews that exist for that guide, adds up all the star ratings, and calculates a new, accurate average rating.
    3.  **Database Update:** It then updates the `average_rating` and `total_reviews` fields on the guide's main profile document in Firestore. This ensures that the guide's profile is always showing the latest, correct rating without the main app having to do any heavy calculations.

Of course. Here is the second and final segment of the detailed breakdown for your README file.

---

## Part 2: Automated Guide Booking & Notification System

This set of functions works together to create a fully automated, "hands-off" guide booking system. It handles everything from the initial request to finding the best guide, managing rejections and timeouts, and sending real-time notifications.

### 4. `assign_guide_to_booking`

* **Job:** To kick off the guide assignment process.
* **Trigger:** This function runs when a new booking document is first created in the `bookings` collection with the status `pending_assignment`.
* **How it Works:**
    1.  **Read the List:** When a tourist requests a guide, the main app creates a ranked list of all suitable and available guides and saves it in the booking document's `potential_guides` field. This function reads that list.
    2.  **Assign the Best:** It takes the very first guide from the list (who is the highest-scoring, best match).
    3.  **Set the Deadline:** It updates the booking document's status to `pending_acceptance` and, crucially, sets a `guide_response_deadline` of 60 minutes from the current time.
    4.  **Trigger Notification:** This status change is the event that our `send_booking_notifications` function (explained below) is waiting for, which then sends a "New Trip Request!" alert to the guide.

### 5. `handle_booking_rejection`

* **Job:** To automatically find the *next* best guide if the first one says no or times out. This is the core of the "cascading" logic.
* **Trigger:** This function runs whenever a booking document is updated and its status changes to `rejected_by_guide` or `timed_out`.
* **How it Works:**
    1.  **Identify Rejected Guide:** The function identifies which guide rejected the trip.
    2.  **Find the Next in Line:** It looks at the `potential_guides` list and finds the index of the guide who just rejected the request. It then moves to the next index to find the next guide.
    3.  **Re-assign:** If another guide is available in the list, the function re-assigns the booking to them and resets the 60-minute response timer. This triggers a new notification to the newly assigned guide.
    4.  **Handle Failure:** If the function gets to the end of the `potential_guides` list, it means no one was available. It then updates the booking status to `failed` and triggers a final notification to the tourist letting them know a guide could not be found.

### 6. `check_booking_status` (Scheduled Function)

* **Job:** To act as the system's "clock," constantly checking for guides who have not responded in time and sending them reminders.
* **Trigger:** This is a special type of function that is not triggered by an event. Instead, it runs automatically on a fixed schedule—**every 5 minutes**.
* **How it Works:**
    1.  **Query Pending Bookings:** Every 5 minutes, the function queries the database for all bookings that are in the `pending_acceptance` state.
    2.  **Send Reminders:** For each pending booking, it checks the `guide_response_deadline`. If there are 30 minutes or 5 minutes left, it triggers a reminder push notification to the guide's device.
    3.  **Trigger Timeouts:** If the function finds a booking where the deadline has passed, it changes the booking's status to `timed_out`. This status change automatically triggers the `handle_booking_rejection` function, which then moves the request to the next guide in the list.

### 7. `send_booking_notifications` (The Central Notifier)

* **Job:** To be the single, centralized function responsible for sending all push notifications related to bookings.
* **Trigger:** Runs whenever a booking document is updated, and its `status` field changes.
* **How it Works:**
    1.  **Detect Status Change:** The function looks at what the booking status was *before* and what it is *after* the update.
    2.  **Route the Notification:** Based on the change, it sends the correct message to the correct person:
        * If status changes to `pending_acceptance` -> Notify the **Guide** about a new trip.
        * If status changes to `accepted` -> Notify the **Tourist** that their guide is confirmed.
        * If status changes to `failed` -> Notify the **Tourist** that no guide was found.
        * If status changes to `cancelled_by_tourist` -> Notify the **Guide** that the trip was cancelled.
    3.  **Send via FCM:** It uses a helper function (`send_fcm_notification`) to look up the user's device token(s) from the `/users/{user_id}/device_tokens` collection and sends the actual push notification via Firebase Cloud Messaging. This centralized design makes the notification logic clean, reliable, and easy to manage.