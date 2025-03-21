# python
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_notification(subject, body, sender_email, receiver_email, smtp_server, login, password):
    # Hardcoded port for STARTTLS (587)
    port = 587

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