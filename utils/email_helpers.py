import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List


def send_batch_report_email(
    total_cases: int,
    rip_cases: int,
    not_found_cases: int,
    valid_cases: int,
    recipient_emails: List[str],
    batch_name: str = "",
    report_type: str = "final",  # "halfway" or "final"
    sender_email: str = None,
    sender_password: str = None,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> bool:
    """
    Send a batch report email with case statistics.
    
    Args:
        total_cases: Total number of cases processed
        rip_cases: Number of RIP cases
        not_found_cases: Number of cases not found
        valid_cases: Number of valid cases (total - rip - not_found)
        recipient_emails: List of email addresses
        batch_name: Name of the batch (optional)
        report_type: "halfway" or "final"
        sender_email: Sender email address
        sender_password: Sender email password or app password
        smtp_server: SMTP server (default: smtp.gmail.com)
        smtp_port: SMTP port (default: 587)
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    
    # Calculate percentages
    rip_pct = (rip_cases / total_cases * 100) if total_cases > 0 else 0
    not_found_pct = (not_found_cases / total_cases * 100) if total_cases > 0 else 0
    valid_pct = (valid_cases / total_cases * 100) if total_cases > 0 else 0
    
    processed = rip_cases + not_found_cases + valid_cases
    processed_pct = (processed / total_cases * 100) if total_cases > 0 else 0
    
    # Choose emoji and title based on report type
    if report_type == "halfway":
        emoji = "⏳"
        title = "Halfway Progress Report"
        color = "#3498db"
    else:
        emoji = "✅"
        title = "Final Batch Report"
        color = "#2c3e50"
    
    # Build email
    subject = f"{emoji} {title}{f' - {batch_name}' if batch_name else ''} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px;">
        <div style="background: {color}; color: white; padding: 20px; border-radius: 8px; text-align: center;">
            <h1 style="margin: 0;">{emoji} {title}</h1>
            <p style="margin: 5px 0 0; opacity: 0.8;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            {f'<p style="margin: 10px 0 0; font-size: 18px;">📁 {batch_name}</p>' if batch_name else ''}
        </div>
        
        <div style="display: flex; justify-content: space-around; margin: 20px 0; background: #f8f9fa; padding: 20px; border-radius: 8px;">
            <div style="text-align: center;">
                <div style="font-size: 36px; font-weight: bold;">{processed}</div>
                <div style="color: #6c757d;">📊 Processed</div>
                <div style="font-size: 14px; color: #3498db;">{processed_pct:.1f}%</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 36px; font-weight: bold;">{total_cases}</div>
                <div style="color: #6c757d;">📋 Total</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 36px; font-weight: bold; color: #e74c3c;">{rip_cases}</div>
                <div style="color: #6c757d;">⛔ RIP</div>
                <div style="font-size: 14px; color: #e74c3c;">{rip_pct:.1f}%</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 36px; font-weight: bold; color: #f39c12;">{not_found_cases}</div>
                <div style="color: #6c757d;">🔍 Not Found</div>
                <div style="font-size: 14px; color: #f39c12;">{not_found_pct:.1f}%</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 36px; font-weight: bold; color: #27ae60;">{valid_cases}</div>
                <div style="color: #6c757d;">✅ Valid</div>
                <div style="font-size: 14px; color: #27ae60;">{valid_pct:.1f}%</div>
            </div>
        </div>
        
        <!-- Progress Bar -->
        <div style="margin: 20px 0;">
            <div style="display: flex; justify-content: space-between; font-size: 14px; color: #6c757d;">
                <span>Progress: {processed}/{total_cases}</span>
                <span>{processed_pct:.1f}%</span>
            </div>
            <div style="width: 100%; height: 25px; background: #ecf0f1; border-radius: 4px; overflow: hidden;">
                <div style="width: {processed_pct:.1f}%; height: 100%; background: {color}; text-align: center; line-height: 25px; color: white; font-size: 12px; font-weight: bold;">
                    {processed_pct:.1f}%
                </div>
            </div>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr style="background: {color}; color: white;">
                <th style="padding: 10px; text-align: left;">Status</th>
                <th style="padding: 10px; text-align: center;">Count</th>
                <th style="padding: 10px; text-align: center;">Percentage</th>
            </tr>
            <tr style="border-bottom: 1px solid #dee2e6;">
                <td style="padding: 10px;">✅ Valid</td>
                <td style="padding: 10px; text-align: center; font-weight: bold;">{valid_cases}</td>
                <td style="padding: 10px; text-align: center;">{valid_pct:.1f}%</td>
            </tr>
            <tr style="border-bottom: 1px solid #dee2e6;">
                <td style="padding: 10px;">⛔ RIP</td>
                <td style="padding: 10px; text-align: center; font-weight: bold;">{rip_cases}</td>
                <td style="padding: 10px; text-align: center;">{rip_pct:.1f}%</td>
            </tr>
            <tr style="border-bottom: 1px solid #dee2e6;">
                <td style="padding: 10px;">🔍 Not Found</td>
                <td style="padding: 10px; text-align: center; font-weight: bold;">{not_found_cases}</td>
                <td style="padding: 10px; text-align: center;">{not_found_pct:.1f}%</td>
            </tr>
            <tr style="font-weight: bold; border-top: 2px solid {color};">
                <td style="padding: 10px;">📊 Processed</td>
                <td style="padding: 10px; text-align: center;">{processed}</td>
                <td style="padding: 10px; text-align: center;">{processed_pct:.1f}%</td>
            </tr>
            <tr style="font-weight: bold; border-top: 1px solid #dee2e6;">
                <td style="padding: 10px;">📋 TOTAL</td>
                <td style="padding: 10px; text-align: center;">{total_cases}</td>
                <td style="padding: 10px; text-align: center;">100%</td>
            </tr>
        </table>
        
        <div style="text-align: center; font-size: 12px; color: #6c757d; border-top: 1px solid #dee2e6; padding-top: 20px; margin-top: 20px;">
            <p>This is an automated report from the Court Scraper System.</p>
            <p>{'⏳ Processing is 50% complete. You will receive a final report when done.' if report_type == 'halfway' else '✅ Batch processing is complete.'}</p>
        </div>
    </body>
    </html>
    """
    
    # Create message
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipient_emails)
    msg.attach(MIMEText(body, "html"))
    
    # Send
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"✅ {title} email sent to {len(recipient_emails)} recipients")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


def send_halfway_report(
    total_cases: int,
    rip_cases: int,
    not_found_cases: int,
    valid_cases: int,
    recipient_emails: List[str],
    batch_name: str = "",
    sender_email: str = None,
    sender_password: str = None,
) -> bool:
    """Convenience function for halfway report."""
    return send_batch_report_email(
        total_cases=total_cases,
        rip_cases=rip_cases,
        not_found_cases=not_found_cases,
        valid_cases=valid_cases,
        recipient_emails=recipient_emails,
        batch_name=batch_name,
        report_type="halfway",
        sender_email=sender_email,
        sender_password=sender_password,
    )


def send_final_report(
    total_cases: int,
    rip_cases: int,
    not_found_cases: int,
    valid_cases: int,
    recipient_emails: List[str],
    batch_name: str = "",
    sender_email: str = None,
    sender_password: str = None,
) -> bool:
    """Convenience function for final report."""
    return send_batch_report_email(
        total_cases=total_cases,
        rip_cases=rip_cases,
        not_found_cases=not_found_cases,
        valid_cases=valid_cases,
        recipient_emails=recipient_emails,
        batch_name=batch_name,
        report_type="final",
        sender_email=sender_email,
        sender_password=sender_password,
    )

