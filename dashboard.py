import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "tracker.db")
OUTPUT_PATH = os.path.join(BASE_DIR, "portfolio", "dashboard.html")

# SECURITY TOGGLE: Set to True to anonymize real company names for public portfolio safety
ANONYMIZE_DASHBOARD = True

def anonymize_company(name):
    """Maps raw platform names to clean, professional placeholders."""
    if not ANONYMIZE_DASHBOARD:
        return name
    name_lower = name.lower()
    if "outlier" in name_lower:
        return "Tier-1 LLM Training Platform"
    elif "oneforma" in name_lower or "clickworker" in name_lower:
        return "Global Crowdsourcing Vendor"
    elif "welocalize" in name_lower:
        return "Localization & LLM Evaluation Provider"
    else:
        return "Confidential AI Data Platform"

def generate_dashboard():
    if not os.path.exists(DB_PATH):
        return False

    try:
        with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            
            total_sent = conn.execute("SELECT COUNT(*) FROM applications WHERE status='sent'").fetchone()[0]
            
            sent_this_week = conn.execute("""
                SELECT COUNT(*) FROM applications 
                WHERE status='sent' AND sent_at >= datetime('now', '-7 days')
            """).fetchone()[0]
            
            status_counts = {"drafted": 0, "applied": 0, "interviewing": 0, "rejected": 0, "accepted": 0}
            
            cursor = conn.execute("SELECT application_status, COUNT(*) FROM applications GROUP BY application_status")
            for row in cursor.fetchall():
                state, count = row[0], row[1]
                if state in status_counts:
                    status_counts[state] = count
            
            cursor = conn.execute("""
                SELECT role, company, application_status, sent_at 
                FROM applications WHERE status='sent' ORDER BY sent_at DESC LIMIT 10
            """)
            recent_rows = cursor.fetchall()

        table_rows_html = ""
        if not recent_rows:
            table_rows_html = """<tr><td colspan="4" class="px-6 py-8 text-center text-gray-500 font-mono text-sm">No applications currently logged in tracker.db.</td></tr>"""
        else:
            for role, company, app_status, sent_at in recent_rows:
                # SECURITY FIX: Obfuscate the exact timestamp to just the Date
                try:
                    date_obj = datetime.strptime(sent_at, "%Y-%m-%d %H:%M:%S")
                    formatted_date = date_obj.strftime("%b %d, %Y")
                except ValueError:
                    formatted_date = "Recent"
                    
                display_company = anonymize_company(company)
                
                # SECURITY FIX: Obfuscate the exact role to a generic AI category
                display_role = "AI Data Annotation & Evaluation"
                if "engineer" in role.lower() or "developer" in role.lower():
                    display_role = "AI Prompt Engineering"
                
                status_color = "text-gray-400"
                if app_status == "applied": status_color = "text-blue-400"
                elif app_status == "interviewing": status_color = "text-purple-400"
                elif app_status == "accepted": status_color = "text-emerald-400 font-bold"
                elif app_status == "rejected": status_color = "text-rose-500"
                    
                table_rows_html += f"""
                <tr class="border-b border-gray-800 hover:bg-gray-800/20 transition-colors">
                    <td class="px-6 py-4 text-sm font-semibold text-white">{display_role}</td>
                    <td class="px-6 py-4 text-sm text-emerald-400 font-mono">{display_company}</td>
                    <td class="px-6 py-4 text-sm font-mono text-center {status_color}">{app_status}</td>
                    <td class="px-6 py-4 text-sm text-gray-400 font-mono text-right">{formatted_date}</td>
                </tr>
                """

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Scout Agent | Application CRM Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 font-sans leading-relaxed">
    <nav class="max-w-4xl mx-auto px-6 pt-8 pb-4 flex justify-between items-center border-b border-gray-800">
        <a href="index.html" class="text-sm font-mono text-gray-400 hover:text-emerald-400 transition-colors">&larr; Back to Portfolio</a>
        <span class="text-xs font-mono text-gray-500">Live Agent Dashboard</span>
    </nav>
    <main class="max-w-4xl mx-auto px-6 py-12 space-y-12">
        <header class="space-y-4">
            <h1 class="text-3xl font-bold tracking-tight text-white sm:text-4xl">Application Tracking Center</h1>
            <p class="text-gray-400 text-md">This dashboard displays live, anonymized application metrics generated and written directly from my local SQLite database to Netlify upon successful application submission.</p>
            <div class="text-xs text-gray-500 font-mono">Last Compiled: {datetime.now().strftime('%b %d, %Y at %H:%M')} (WAT)</div>
        </header>
        <section class="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div class="p-6 bg-gray-800/40 rounded-lg border border-gray-800 space-y-2">
                <span class="text-xs font-mono text-gray-400 uppercase tracking-wider">Total Submissions</span>
                <div class="text-4xl font-extrabold text-white font-mono">{total_sent}</div>
                <p class="text-xs text-emerald-400 font-mono">Processed via Outreach Engine</p>
            </div>
            <div class="p-6 bg-gray-800/40 rounded-lg border border-gray-800 space-y-2">
                <span class="text-xs font-mono text-gray-400 uppercase tracking-wider">Submissions (Last 7 Days)</span>
                <div class="text-4xl font-extrabold text-white font-mono">{sent_this_week}</div>
                <p class="text-xs text-emerald-400 font-mono">Active pipeline velocity</p>
            </div>
        </section>
        <section class="space-y-4">
            <h2 class="text-lg font-bold text-white tracking-wide uppercase text-sm font-mono text-emerald-500">Application Pipeline Summary</h2>
            <div class="grid grid-cols-2 sm:grid-cols-5 gap-4">
                <div class="p-4 bg-gray-800/20 rounded-lg border border-gray-800 text-center space-y-1"><span class="text-xs font-mono text-amber-400 font-semibold uppercase">Drafted</span><div class="text-2xl font-bold text-white font-mono">{status_counts['drafted']}</div></div>
                <div class="p-4 bg-gray-800/20 rounded-lg border border-gray-800 text-center space-y-1"><span class="text-xs font-mono text-blue-400 font-semibold uppercase">Applied</span><div class="text-2xl font-bold text-white font-mono">{status_counts['applied']}</div></div>
                <div class="p-4 bg-gray-800/20 rounded-lg border border-gray-800 text-center space-y-1"><span class="text-xs font-mono text-purple-400 font-semibold uppercase">Interview</span><div class="text-2xl font-bold text-white font-mono">{status_counts['interviewing']}</div></div>
                <div class="p-4 bg-gray-800/20 rounded-lg border border-gray-800 text-center space-y-1"><span class="text-xs font-mono text-rose-500 font-semibold uppercase">Closed</span><div class="text-2xl font-bold text-white font-mono">{status_counts['rejected']}</div></div>
                <div class="p-4 bg-emerald-500/10 rounded-lg border border-emerald-500/20 text-center space-y-1"><span class="text-xs font-mono text-emerald-400 font-semibold uppercase text-emerald-400">Accepted</span><div class="text-2xl font-bold text-white font-mono">{status_counts['accepted']}</div></div>
            </div>
        </section>
        <section class="space-y-4">
            <h2 class="text-lg font-bold text-white tracking-wide uppercase text-sm font-mono text-emerald-500">Recent Applications Log</h2>
            <div class="overflow-x-auto rounded-lg border border-gray-800">
                <table class="min-w-full divide-y divide-gray-800 bg-gray-900">
                    <thead class="bg-gray-800/30">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-semibold text-gray-400 font-mono uppercase tracking-wider">Role Title</th>
                            <th class="px-6 py-3 text-left text-xs font-semibold text-gray-400 font-mono uppercase tracking-wider">Platform Category</th>
                            <th class="px-6 py-3 text-center text-xs font-semibold text-gray-400 font-mono uppercase tracking-wider">CRM Status</th>
                            <th class="px-6 py-3 text-right text-xs font-semibold text-gray-400 font-mono uppercase tracking-wider">Timestamp</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-800">
                        {table_rows_html}
                    </tbody>
                </table>
            </div>
        </section>
    </main>
    <footer class="max-w-4xl mx-auto px-6 py-8 border-t border-gray-800 text-center text-xs text-gray-500 font-mono">
        Job Scout CRM &bull; Auto-Sync Engine v1.1
    </footer>
</body>
</html>"""
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(html_template)
        return True
    except Exception as e:
        return False

if __name__ == "__main__":
    generate_dashboard()