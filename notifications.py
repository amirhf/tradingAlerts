# python
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import threading
import os
import dotenv

# Notification management
_notification_lock = threading.Lock()
_last_email_time = {}  # Dictionary to track last email time for rate limiting


def send_email_notification(subject, body, sender_email, receiver_email, smtp_server, login, password, port=587):
    """
    Send email notification with rate limiting to prevent flooding

    Args:
        subject (str): Email subject
        body (str): Email body
        sender_email (str): Sender email address
        receiver_email (str): Receiver email address
        smtp_server (str): SMTP server address
        login (str): SMTP login
        password (str): SMTP password
        port (int, optional): SMTP port. Defaults to 587.

    Returns:
        bool: Success status
    """
    # Extract symbol from subject if available (for rate limiting per symbol)
    symbol = subject.split(':')[0].strip() if ':' in subject else 'general'

    # Check rate limiting (no more than one email per symbol per minute)
    with _notification_lock:
        current_time = time.time()
        if symbol in _last_email_time:
            time_since_last = current_time - _last_email_time[symbol]
            if time_since_last < 60:  # Less than 60 seconds since last email for this symbol
                print(f"Rate limiting email for {symbol}. Last email sent {time_since_last:.1f} seconds ago.")
                return False

        # Update last email time for this symbol
        _last_email_time[symbol] = current_time

    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()

        with smtplib.SMTP(smtp_server, port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(login, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())

        print(f"Email notification sent: {subject}")
        return True

    except Exception as e:
        print(f"Failed to send email notification: {e}")
        return False


def send_batch_notification(signals, sender_email, receiver_email, smtp_server, login, password):
    """
    Send a batch notification combining multiple signals

    Args:
        signals (list): List of signal dictionaries with 'symbol', 'time', 'type', 'levels'
        sender_email (str): Sender email address
        receiver_email (str): Receiver email address
        smtp_server (str): SMTP server address
        login (str): SMTP login
        password (str): SMTP password

    Returns:
        bool: Success status
    """
    if not signals:
        return False

    # Create a combined subject line
    symbols = [signal['symbol'] for signal in signals]
    unique_symbols = list(set(symbols))

    if len(unique_symbols) == 1:
        subject = f"{unique_symbols[0]}: Multiple Signals Detected"
    else:
        subject = f"MT5 Alert: Signals for {', '.join(unique_symbols[:3])}"
        if len(unique_symbols) > 3:
            subject += f" and {len(unique_symbols) - 3} more"

    # Create a combined body
    body = "MT5 Pattern Alerts\n" + "=" * 20 + "\n\n"

    for signal in signals:
        body += f"Symbol: {signal['symbol']}\n"
        body += f"Time: {signal['time']}\n"
        body += f"Pattern: {signal['type']}\n"
        body += f"Levels: {', '.join(signal['levels'])}\n"
        body += f"Price: {signal['price']}\n"
        body += "-" * 20 + "\n\n"

    return send_email_notification(
        subject=subject,
        body=body,
        sender_email=sender_email,
        receiver_email=receiver_email,
        smtp_server=smtp_server,
        login=login,
        password=password
    )


# Testing function
if __name__ == "__main__":
    dotenv.load_dotenv()

    # Read email settings from environment variables
    smtp_server = os.getenv("SMTP_SERVER")
    login = os.getenv("LOGIN")
    password = os.getenv("PASSWORD")
    sender_email = os.getenv("SENDER_EMAIL")
    receiver_email = os.getenv("RECEIVER_EMAIL")

    if all([smtp_server, login, password, sender_email, receiver_email]):
        # Test single notification
        send_email_notification(
            subject="Test Notification",
            body="This is a test email from the updated notification system.",
            sender_email=sender_email,
            receiver_email=receiver_email,
            smtp_server=smtp_server,
            login=login,
            password=password
        )

        # Test batch notification
        signals = [
            {
                'symbol': 'EURUSD',
                'time': '2023-01-01 12:00:00',
                'type': 'bull',
                'levels': ['yesterday_high', 'today_open'],
                'price': 1.0950
            },
            {
                'symbol': 'GBPUSD',
                'time': '2023-01-01 12:10:00',
                'type': 'bear',
                'levels': ['yesterday_low'],
                'price': 1.2650
            }
        ]

        send_batch_notification(
            signals=signals,
            sender_email=sender_email,
            receiver_email=receiver_email,
            smtp_server=smtp_server,
            login=login,
            password=password
        )
    else:
        print("Email settings not completely configured in .env file")