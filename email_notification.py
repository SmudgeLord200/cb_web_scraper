import yagmail

def send_event_email(subject, body, recipient_email, sender_email):
    """
    Sends an email using yagmail
    """
    try:
        yag = yagmail.SMTP(sender_email)
        yag.send(bcc=recipient_email, subject=subject, contents=body)
        print("Email sent successfully via yagmail!")
    except Exception as e:
        print(f"Error sending email via yagmail: {e}")