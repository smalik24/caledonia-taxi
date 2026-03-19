"""
Invoice & Receipt Service — Caledonia Taxi
==========================================
Generates professional PDF receipts using ReportLab.
Uses real Resend API when RESEND_API_KEY is set; falls back to mock logging.
"""

import os
import logging
from io import BytesIO
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# In-memory email log
_email_log: list[dict] = []


# ============================================================
# MOCK EMAIL SENDER
# ============================================================

def _send_email_mock(
    to_email: str,
    subject: str,
    body: str,
    attachments: list | None = None
) -> dict:
    """
    Mock email dispatcher. Logs and stores the email.
    Replace with Resend / SendGrid in production.
    """
    entry = {
        "id": f"EMAIL_{len(_email_log)+1:04d}",
        "to": to_email,
        "subject": subject,
        "body_preview": body[:200],
        "has_attachment": bool(attachments),
        "attachment_names": [a.get("filename","file") for a in (attachments or [])],
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "status": "sent_mock",
        "provider": "MOCK"
    }
    _email_log.append(entry)

    border = "─" * 50
    print(f"\n📧  MOCK EMAIL\n{border}")
    print(f"  To:      {to_email}")
    print(f"  Subject: {subject}")
    if attachments:
        print(f"  Attach:  {[a.get('filename') for a in attachments]}")
    print(f"{border}\n")

    logger.info(f"[MOCK EMAIL] To={to_email} | Subject={subject}")
    return entry


def _send_email_real(to_email: str, subject: str, body: str, attachments=None) -> dict:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return _send_email_mock(to_email, subject, body, attachments)
    try:
        import httpx
        import base64
        payload = {
            "from": "receipts@caledonia.taxi",
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        if attachments:
            payload["attachments"] = [
                {"filename": a["filename"], "content": base64.b64encode(a["data"]).decode()}
                for a in attachments
            ]
        r = httpx.post("https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=10)
        r.raise_for_status()
        result = r.json()
        entry = {
            "id": result.get("id", "resend-ok"),
            "to": to_email,
            "subject": subject,
            "body_preview": body[:200],
            "has_attachment": bool(attachments),
            "attachment_names": [a.get("filename","file") for a in (attachments or [])],
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "status": "sent",
            "provider": "resend"
        }
        _email_log.append(entry)
        logger.info(f"[Email] Sent via Resend to {to_email}")
        return entry
    except Exception as e:
        logger.error(f"[Email] Resend error: {e}")
        return _send_email_mock(to_email, subject, body, attachments)


# ============================================================
# PDF RECEIPT GENERATOR
# ============================================================

def generate_invoice_pdf(booking: dict) -> bytes:
    """
    Generate a professional PDF receipt using ReportLab.
    Falls back to a plain-text receipt if ReportLab is not installed.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable
        )
        from reportlab.lib.units import inch
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            leftMargin=0.75*inch, rightMargin=0.75*inch,
            topMargin=0.75*inch,  bottomMargin=0.75*inch
        )

        styles = getSampleStyleSheet()
        dark   = colors.HexColor('#0e0e1a')
        gold   = colors.HexColor('#FFD700')
        grey   = colors.HexColor('#666666')
        light  = colors.HexColor('#f0f0f0')
        story  = []

        # ── Header ──────────────────────────────────────────────
        title_style = ParagraphStyle('Title', parent=styles['Normal'],
            fontSize=26, fontName='Helvetica-Bold',
            textColor=dark, alignment=TA_CENTER, spaceAfter=4)

        sub_style = ParagraphStyle('Sub', parent=styles['Normal'],
            fontSize=10, textColor=grey, alignment=TA_CENTER, spaceAfter=4)

        story.append(Paragraph("CALEDONIA TAXI", title_style))
        story.append(Paragraph("Hamilton, Ontario — Professional Taxi Service", sub_style))
        story.append(Spacer(1, 0.1*inch))
        story.append(HRFlowable(width="100%", thickness=3, color=gold))
        story.append(Spacer(1, 0.2*inch))

        # ── Receipt label ────────────────────────────────────────
        receipt_style = ParagraphStyle('Receipt', parent=styles['Normal'],
            fontSize=15, fontName='Helvetica-Bold', textColor=dark,
            alignment=TA_CENTER, spaceAfter=16)
        story.append(Paragraph("TRIP RECEIPT", receipt_style))

        # ── Booking info table ───────────────────────────────────
        bid = booking.get('id', 'N/A')
        created = booking.get('created_at', datetime.now(timezone.utc).isoformat())
        try:
            dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            date_str = dt.strftime('%B %d, %Y  %I:%M %p EST')
        except Exception:
            date_str = created

        detail_data = [
            ['Booking ID:',  bid[:16].upper() + ('…' if len(bid) > 16 else '')],
            ['Date & Time:', date_str],
            ['Customer:',    booking.get('customer_name', 'N/A')],
            ['Phone:',       booking.get('customer_phone', 'N/A')],
        ]
        _add_kv_table(story, detail_data)
        story.append(Spacer(1, 0.15*inch))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#dddddd')))
        story.append(Spacer(1, 0.15*inch))

        # ── Trip details ─────────────────────────────────────────
        story.append(Paragraph("TRIP DETAILS", _section_style(styles, dark)))
        trip_data = [
            ['Pickup:',    booking.get('pickup_address',  'N/A')],
            ['Drop-off:',  booking.get('dropoff_address', 'N/A')],
            ['Distance:',  f"{float(booking.get('estimated_distance_km', 0)):.1f} km"],
        ]
        _add_kv_table(story, trip_data)
        story.append(Spacer(1, 0.15*inch))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#dddddd')))
        story.append(Spacer(1, 0.15*inch))

        # ── Fare breakdown ───────────────────────────────────────
        story.append(Paragraph("FARE BREAKDOWN", _section_style(styles, dark)))
        fare  = float(booking.get('estimated_fare', 0))
        dist  = float(booking.get('estimated_distance_km', 0))
        base  = 4.50
        km_ch = dist * 2.10

        fare_data = [
            ['Base Fare:',                     f'${base:.2f}'],
            [f'Distance ({dist:.1f} km × $2.10/km):', f'${km_ch:.2f}'],
            ['',                               ''],
            ['TOTAL FARE:',                    f'${fare:.2f}'],
        ]
        t = Table(fare_data, colWidths=[4.5*inch, 2*inch])
        t.setStyle(TableStyle([
            ('FONTNAME',    (0,0), (-1,-2), 'Helvetica'),
            ('FONTNAME',    (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE',    (0,0), (-1,-2), 10),
            ('FONTSIZE',    (0,-1), (-1,-1), 14),
            ('TEXTCOLOR',   (0,0), (-1,-2), grey),
            ('TEXTCOLOR',   (0,-1), (-1,-1), dark),
            ('ALIGN',       (1,0), (1,-1), 'RIGHT'),
            ('LINEABOVE',   (0,-1), (-1,-1), 2, gold),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('TOPPADDING',    (0,0), (-1,-1), 7),
            ('BACKGROUND',  (0,-1), (-1,-1), colors.HexColor('#FFFBEA')),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.35*inch))

        # ── Footer ───────────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#dddddd')))
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(
            "Thank you for choosing Caledonia Taxi!",
            ParagraphStyle('Thanks', parent=styles['Normal'],
                fontSize=12, fontName='Helvetica-Bold',
                textColor=dark, alignment=TA_CENTER, spaceAfter=4)
        ))
        story.append(Paragraph(
            "Hamilton, Ontario &nbsp;|&nbsp; Available 24/7 &nbsp;|&nbsp; (289) 555-1001",
            ParagraphStyle('Footer', parent=styles['Normal'],
                fontSize=9, textColor=grey, alignment=TA_CENTER, spaceAfter=4)
        ))
        story.append(Paragraph(
            f"Receipt generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            ParagraphStyle('Ts', parent=styles['Normal'],
                fontSize=8, textColor=colors.HexColor('#aaaaaa'), alignment=TA_CENTER)
        ))

        doc.build(story)
        return buffer.getvalue()

    except ImportError:
        logger.warning("[invoice] ReportLab not installed — returning text receipt")
        return _text_receipt(booking).encode('utf-8')


def _add_kv_table(story, data):
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, TableStyle
    t = Table(data, colWidths=[2.1*inch, 4.4*inch])
    t.setStyle(TableStyle([
        ('FONTNAME',  (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME',  (1,0), (1,-1), 'Helvetica'),
        ('FONTSIZE',  (0,0), (-1,-1), 10),
        ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#666666')),
        ('TEXTCOLOR', (1,0), (1,-1), colors.HexColor('#0e0e1a')),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
    ]))
    story.append(t)


def _section_style(styles, dark):
    from reportlab.lib.styles import ParagraphStyle
    return ParagraphStyle('Section', parent=styles['Normal'],
        fontSize=11, fontName='Helvetica-Bold',
        textColor=dark, spaceAfter=10)


def _text_receipt(booking: dict) -> str:
    fare = float(booking.get('estimated_fare', 0))
    dist = float(booking.get('estimated_distance_km', 0))
    return f"""
CALEDONIA TAXI — TRIP RECEIPT
================================
Booking ID : {booking.get('id', 'N/A')}
Customer   : {booking.get('customer_name', 'N/A')}
Phone      : {booking.get('customer_phone', 'N/A')}
Date       : {datetime.now(timezone.utc).strftime('%B %d, %Y %I:%M %p UTC')}

TRIP
---------
Pickup     : {booking.get('pickup_address', 'N/A')}
Drop-off   : {booking.get('dropoff_address', 'N/A')}
Distance   : {dist:.1f} km

FARE
---------
Base Fare  : $4.50
Distance   : ${dist * 2.10:.2f}
TOTAL      : ${fare:.2f} CAD

Thank you for choosing Caledonia Taxi!
Hamilton, Ontario — (289) 555-1001
================================
""".strip()


# ============================================================
# RECEIPT EMAIL TRIGGER
# ============================================================

def send_receipt_email(booking: dict) -> dict:
    """
    Generate a PDF receipt and mock-send it by email.
    Called automatically when a ride is completed.
    """
    customer_name  = booking.get('customer_name', 'Customer')
    customer_phone = booking.get('customer_phone', 'unknown')
    booking_id     = booking.get('id', 'N/A')
    fare           = float(booking.get('estimated_fare', 0))

    # Generate PDF
    pdf_bytes = generate_invoice_pdf(booking)

    # Derive a placeholder email (real system would store customer email)
    to_email = f"customer_{booking_id[:6]}@caledonia.taxi"

    body = f"""Dear {customer_name},

Thank you for choosing Caledonia Taxi!

Your trip receipt is attached to this email.

Booking Reference : {booking_id[:12].upper()}
Total Fare        : ${fare:.2f} CAD

We appreciate your business and look forward to serving you again.

Caledonia Taxi Team
Hamilton, Ontario | (289) 555-1001 | Available 24/7
"""

    return _send_email_real(
        to_email=to_email,
        subject=f"Your Caledonia Taxi Receipt — ${fare:.2f} CAD",
        body=body,
        attachments=[{
            "filename": f"receipt_{booking_id[:8].upper()}.pdf",
            "data": pdf_bytes,
            "mime": "application/pdf"
        }]
    )


# ============================================================
# ADMIN ACCESS
# ============================================================

def get_email_log() -> list[dict]:
    """Return all logged emails (newest first)."""
    return list(reversed(_email_log))


def clear_email_log() -> None:
    _email_log.clear()
