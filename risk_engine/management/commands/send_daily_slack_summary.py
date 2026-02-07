"""
Send daily payouts summary to Slack via incoming webhook.

Requires SLACK_WEBHOOK_URL in environment (.env). If missing, exits with a message.
Uses LLM to generate a detailed report when OPENAI_API_KEY is set.
Usage: python manage.py send_daily_slack_summary
"""

import os

from django.core.management.base import BaseCommand
from dotenv import load_dotenv

from risk_engine.models import DailyMetrics, CalibrationStats
from risk_engine.report_context import get_daily_report_context_for_date
from risk_engine.llm.client import generate_daily_report

load_dotenv()


class Command(BaseCommand):
    help = "Post the latest daily metrics and an LLM-generated detailed report to Slack via webhook."

    def handle(self, *args, **options):
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url or not webhook_url.strip():
            self.stdout.write(
                self.style.WARNING(
                    "SLACK_WEBHOOK_URL is not set. Add it to .env to send Slack summaries."
                )
            )
            return

        latest = DailyMetrics.objects.order_by("-date").first()
        if not latest:
            self.stdout.write(self.style.WARNING("No daily metrics found. Run recompute_daily_metrics first."))
            return

        calibration = CalibrationStats.objects.filter(date=latest.date).first()
        fields = [
            {"title": "Date", "value": latest.date.isoformat(), "short": True},
            {"title": "Total requests", "value": str(latest.total_requests), "short": True},
            {"title": "Auto approved", "value": str(latest.auto_approved), "short": True},
            {"title": "Auto blocked", "value": str(latest.auto_blocked), "short": True},
            {"title": "Sent to review", "value": str(latest.sent_to_review), "short": True},
        ]
        if calibration:
            fields.append({"title": "Accuracy %", "value": f"{calibration.accuracy_percent}", "short": True})
            fields.append({"title": "Overconfidence rate %", "value": f"{calibration.overconfidence_rate}", "short": True})
            fields.append({"title": "Underconfidence rate %", "value": f"{calibration.underconfidence_rate}", "short": True})

        context = get_daily_report_context_for_date(latest.date)
        detailed_report = generate_daily_report(context)

        payload = {
            "attachments": [
                {
                    "title": "Daily Payouts Summary",
                    "fields": fields,
                    "text": detailed_report,
                    "color": "#36a64f",
                }
            ]
        }

        try:
            import requests
            resp = requests.post(webhook_url, json=payload, timeout=30)
            resp.raise_for_status()
            self.stdout.write(self.style.SUCCESS("Slack summary sent."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to send to Slack: {e}"))
