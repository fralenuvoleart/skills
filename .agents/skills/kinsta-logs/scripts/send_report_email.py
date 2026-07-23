#!/usr/bin/env python3
"""Send the generated Kinsta Health Report PDF by email.
 
Reads SMTP credentials from ~/.config/kinsta-log-analyzer/email.json and
non-sensitive fields (recipients, subject, from_email, body signature)
from .agents/skills/kinsta-logs/config/email.json. The two configs
are merged — credentials stay outside version control; recipients/subject
live with the skill for portability.
"""
 
import json
import smtplib
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
 
CREDENTIALS_PATH = Path.home() / ".config" / "kinsta-log-analyzer" / "email.json"
SKILL_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "email.json"
DEFAULT_REPORTS_DIR = Path(os.environ.get("KINSTA_LOG_OUTPUT_DIR", Path.home() / "Downloads" / "kinsta-logs")) / "reports"
 
 
def load_config():
    """Load and merge credentials (~/.config/) and skill config (recipients/subject/etc.)."""
    if not CREDENTIALS_PATH.exists():
        print(f"Credentials config not found: {CREDENTIALS_PATH}", file=sys.stderr)
        print(
            "Create it from the example at "
            ".agents/skills/kinsta-logs/config/email.json.example",
            file=sys.stderr,
        )
        sys.exit(1)
 
    with open(CREDENTIALS_PATH) as f:
        config = json.load(f)
 
    # Merge non-sensitive fields from skill config (recipients, subject, etc.)
    if SKILL_CONFIG_PATH.exists():
        with open(SKILL_CONFIG_PATH) as f:
            skill_config = json.load(f)
        # Skill config provides defaults; credentials config can override.
        for key in ("from_email", "to_emails", "to_email", "subject",
                     "body_signature", "body"):
            if key not in config and key in skill_config:
                config[key] = skill_config[key]
 
    return config


def resolve_report_path(report_path=None):
    if report_path:
        path = Path(report_path).resolve()
        if not path.exists():
            print(f"Report not found: {path}", file=sys.stderr)
            sys.exit(1)
        return path

    if not DEFAULT_REPORTS_DIR.exists():
        print(f"Reports directory not found: {DEFAULT_REPORTS_DIR}", file=sys.stderr)
        sys.exit(1)

    pdfs = sorted(
        DEFAULT_REPORTS_DIR.glob("*.pdf"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not pdfs:
        print(f"No PDF reports found in {DEFAULT_REPORTS_DIR}", file=sys.stderr)
        sys.exit(1)

    return pdfs[0]


def build_message(report_path, config):
    report_path = Path(report_path)
    site_name = report_path.stem.replace("report_", "").replace("_", " ")

    subject = config.get("subject", "Kinsta Report from your AI Buddy").format(
        site_name=site_name
    )
    from_email = config.get("from_email", config.get("username", ""))

    # Support both single legacy `to_email` and new `to_emails` list.
    to_emails = config.get("to_emails")
    if not to_emails:
        to_emails = [config.get("to_email", from_email)]
    if isinstance(to_emails, str):
        to_emails = [to_emails]

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject

    signature = config.get("body_signature", "Your AI Buddy")
    # Allow full body override via "body" key, otherwise build from signature.
    if "body" in config:
        body = config["body"]
    else:
        body = (
            f"Please find the latest Kinsta Health Report attached.\n\n"
            f"Report: {report_path.name}\n\n"
            f"---\n"
            f"{signature}\n"
        )
    msg.attach(MIMEText(body, "plain"))

    with open(report_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename= {report_path.name}",
    )
    msg.attach(part)

    return msg, to_emails


def send_email(report_path, config):
    msg, to_emails = build_message(report_path, config)
    host = config.get("smtp_host", "smtp.gmail.com")
    port = config.get("smtp_port", 587)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(config["username"], config["password"])
        server.send_message(msg)

    print(f"Email sent to {', '.join(to_emails)}")


def main():
    report_path = resolve_report_path(sys.argv[1] if len(sys.argv) > 1 else None)
    config = load_config()
    send_email(report_path, config)


if __name__ == "__main__":
    main()
