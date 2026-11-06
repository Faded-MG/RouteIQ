# ASSESSMENT.md — Spotter Backend Django Engineer assessment (verbatim extract)

Highest authority for requirements. Where any other document conflicts with this file, this file wins. Sender, greeting and hiring-process remarks are omitted on purpose; the requirement text below is copied unchanged from the email received 2026-11-04 23:59 (Africa/Addis_Ababa). Deadline: 3 days from receipt, i.e. 2026-11-07 23:59.

## Assignment

Build an API that takes inputs of start and finish location both within the USA

Return a map of the route along with optimal location to fuel up along the route -- optimal mostly means cost effective based on fuel prices

Assume the vehicle has a maximum range of 500 miles so multiple fuel ups might need to be displayed on the route

Also return the total money spent on fuel assuming the vehicle achieves 10 miles per gallon

Use the attached file below for a list of fuel prices

Find a free API yourself for the map and routing

## Requirements

Build the app in latest stable Django

Send your results for this project within 3 days of receiving the exercise

The API should return results quickly, the quicker the better

The API shouldn't need to call the free map/routing API you found too much. One call to the map/route API is ideal, two or three is acceptable

Make a Loom where you use Postman or similar API platform to demonstrate the API working while also giving a quick overview of your code (5 minutes max)

Share the Github code with us

After completing, please attach the Github code and a Loom video in the question in this message.

## Attachment

`data/fuel-prices-for-be-assessment.csv` (fuel price list; never edit).

## Clause index (used by PLAN.md and TESTING.md)

| Clause | Text (short) | Covered by |
|---|---|---|
| A1 | API takes start and finish, both in the USA | T14; R1, R2 |
| A2 | Return a map of the route | T14 (GeoJSON geometry, P0); T21–T24 (Leaflet map, P1) |
| A3 | Optimal (cost-effective) fuel-up locations | T12, T13, T14; R6, R21 |
| A4 | 500-mile maximum range, multiple fuel-ups | T12, T13; R7, R20 |
| A5 | Total money spent at 10 MPG | T12, T14; R8, R9 |
| A6 | Use the supplied fuel price file | T05, T06; R5, R19 |
| A7 | Free map/routing API | T09, T10; ARCHITECTURE §3 |
| B1 | Latest stable Django | T02; R11 |
| B2 | Within 3 days | PLAN §2 |
| B3 | Fast results | T15; R10 |
| B4 | ≤ 1 routing call ideal, ≤ 3 acceptable | T09, T10, T14; R4 |
| B5 | Loom ≤ 5 min with Postman + code overview | T15; PLAN §9 |
| B6 | GitHub code shared | PLAN §7 |
