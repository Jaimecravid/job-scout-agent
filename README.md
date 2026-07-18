# Job Scout Agent 🚀 | v1.1

> An autonomous AI pipeline that monitors IMAP mailboxes for targeted job alerts, filters them locally, screens matches using Gemini 2.5 Flash, automatically drafts tailored outreach, builds interview study guides, and maintains a local SQLite CRM that syncs live to a Netlify dashboard.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![AI-Model](https://img.shields.io/badge/AI--Screening-Gemini%202.5%20Flash-orange.svg)](https://ai.google.dev/)
[![Database](https://img.shields.io/badge/Database-SQLite3-blue.svg)]()
[![Platform](https://img.shields.io/badge/OS-Windows%20%2F%20Background%20Task-brightgreen.svg)]()

> **⚠️ Operational Security & Privacy Notice**
> This repository is a sanitized engineering demonstration. It is a self-hosted AI job-scouting and application-prep pipeline demonstrating automation, LLM orchestration, local CRM design, and CI/CD deployment. 
> 
> * **Human-in-the-Loop:** This system generates drafts for review. It does **not** auto-submit applications or contact employers without manual approval.
> * **Privacy:** Sensitive runtime data, local SQLite databases, real job-search records, and generated interview prep artifacts are actively `.gitignore`d and kept strictly private. The live dashboard is heavily anonymized.
---

## ⚡ Live Production Status
**Current Phase:** 4-Week Live Production Testing  
**Live Application Metrics:** [View Live CRM Dashboard](https://job-scout-agent.netlify.app/dashboard.html)

---

## 🧠 System Architecture & Data Flow

This project is designed as a lightweight, highly efficient autonomous microservice. The pipeline operates in six distinct phases:

### 1. Ingestion & Deduplication (`fetcher.py` & `main.py`)
* Connects to a designated email account via secure IMAP.
* Computes a deterministic SHA-256 hash for incoming job matches.
* Queries the local SQLite database (`tracker.db`) to ensure the lead hasn't already been processed, preventing redundant API calls and duplicate alerts.

### 2. AI Evaluation (`brain.py`)
* Job descriptions are passed to Gemini 2.5 Flash via a strict structured schema.
* Evaluates geographical constraints (e.g., Worldwide/Angola eligibility) and skill matching (Prompt Engineering, PT-PT Native evaluation).
* **Single-Call Efficiency:** Simultaneously generates a requirements list, strategic gap analysis, and tailored interview questions in the exact same API response.

### 3. Artifact Generation (`outreach.py` & `brain.py`)
* **Outreach Drafts:** Dynamically merges the job description with a localized `Master_Context.txt` database to write a highly technical, customized cover letter (`/outreach_drafts`).
* **Interview Prep Guides:** Silently renders the AI gap analysis and practice questions into a safe, UTF-8 Markdown study guide (`/interview_prep`).

### 4. Multi-Channel Delivery
* Triggers a native Windows Desktop Toast notification locally via background PowerShell.
* Simultaneously pushes the match metrics and the generated cover letter to a mobile device via the Telegram API.

### 5. Triage & Local CRM (`review.py`)
* A custom interactive CLI utility that allows the operator to review pending drafts and instantly copy them to the Windows clipboard.
* Handles file archival (moving processed drafts to `/sent`) and logs the application state into the local SQLite database.
* Features a full CRM manager to transition application states (`drafted` ➔ `applied` ➔ `interviewing` ➔ `accepted`).

### 6. Analytics & CI/CD (`dashboard.py`)
* Runs read-only aggregations against the SQLite database to compile a Tailwind CSS HTML dashboard.
* Automatically stages, commits, and pushes the updated database and HTML to GitHub in the background, triggering a zero-friction Netlify CI/CD redeploy.

---

## 🛠️ Engineering Highlights
* **Model Context Protocol (MCP) Ready:** Engineered to run alongside local LLM sandboxes (Claude Desktop) with Netlify MCP servers configured to natively manage static deployments.
* **Idempotent Migrations:** Database initialization uses safe `ALTER TABLE` checks to update schemas without corrupting existing application histories.
* **Watertight Trust Boundaries:** Engineered with strict `.gitignore` configurations to separate private contextual data (`Master_Context.txt`), API secrets (`.env`), and raw drafts from public-facing repositories.

---

## 🕹️ Daily Operations Manual (Testing Phase)

### The Autonomous Background Loop
The agent runs silently on Windows via Task Scheduler (`run_agent.vbs`). When a match is found:
1. You receive a Windows Toast notification on your desktop.
2. You receive the full cover letter text on your phone via Telegram.

### The Application Workflow
When you are ready to apply to the generated leads, open your terminal and run:
```sh
python review.py