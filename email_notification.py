import yagmail

def send_event_email(subject, body, recipient_email, sender_email):
    """
    Sends an email using yagmail
    """
    try:
        yag = yagmail.SMTP(sender_email)
        # Plain-text alerts; avoid premailer/cssutils/encutils HTML pipeline
        yag.send(
            bcc=recipient_email,
            subject=subject,
            contents=body,
            prettify_html=False,
        )
        print("Email sent successfully via yagmail!")
    except Exception as e:
        print(f"Error sending email via yagmail: {e}")