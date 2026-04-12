# Productivity Guard — Overview

## Project

**Name:** Productivity Guard

**Description:** Productivity Guard is a self-hosted web access control system that blocks distracting domains at the DNS level and requires users to justify requests through a Claude AI gatekeeper before temporarily unblocking them. It is built for personal use to enforce intentional browsing habits: the FastAPI backend evaluates each request using context from Home Assistant (device room, request history) and either grants a scoped, time-limited unblock or denies access with an explanation.
