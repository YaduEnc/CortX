import smtplib
from email.message import EmailMessage
import logging

logger = logging.getLogger(__name__)

def send_reset_email(to_email: str, reset_token: str):
    """
    Sends a password reset email via a local standard SMTP server (Mailpit).
    For completely free local development, it hits 'mailpit:1025' on the docker network.
    """
    msg = EmailMessage()
    msg['Subject'] = 'CortX: Password Reset Request'
    msg['From'] = 'noreply@cortx.local'
    msg['To'] = to_email

    # Sleek, minimal HTML email
    html_content = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1a1a1a; max-width: 500px; margin: 0 auto; padding: 20px;">
        <h2 style="font-weight: 800; font-size: 24px;">Password Reset Request</h2>
        <p style="color: #4a4a4a;">You requested a password reset for your CortX workspace. Your secure, one-time reset token is:</p>
        
        <div style="background: #f4f6f8; font-weight: 700; font-size: 20px; padding: 18px 24px; display: inline-block; border-radius: 12px; margin: 20px 0; color: #1a7bff; letter-spacing: 2px;">
            {reset_token}
        </div>
        
        <p style="color: #4a4a4a;">Return to the CortX app and enter this token along with your new password to restore your access.</p>
        <p style="color: #888; font-size: 13px; margin-top: 40px; border-top: 1px solid #eaeaea; padding-top: 20px;">If you didn't request this reset, you can safely ignore this email.</p>
      </body>
    </html>
    """
    
    msg.set_content("Please enable HTML to view this email.", subtype='html')
    msg.add_alternative(html_content, subtype='html')

    try:
        # Route to Mailpit SMTP running inside the docker network!
        with smtplib.SMTP('mailpit', 1025) as server:
            server.send_message(msg)
            logger.info(f"Test email successfully dispatched to Mailpit for {to_email}")
    except Exception as e:
        logger.error(f"Mailpit SMTP failed: {e}. Is the Mailpit container running?")
