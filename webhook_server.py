"""
Butcher Law Office â Document Generator Server
Serves the Document Library web app and handles all document generation webhooks.

ENV VARIABLES (set in Railway):
    GMAIL_USER, GMAIL_APP_PASSWORD, ATTORNEY_EMAIL, VA_EMAIL
"""

import os, json, subprocess, tempfile, smtplib, logging, hmac, hashlib, base64
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import date
from flask import Flask, request, jsonify, send_from_directory
import urllib.request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GMAIL_USER         = os.environ.get('GMAIL_USER', 'your.gmail@gmail.com')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')
ATTORNEY_EMAIL     = os.environ.get('ATTORNEY_EMAIL', 'tom@butcherlawoffice.com')
VA_EMAIL           = os.environ.get('VA_EMAIL', 'va@butcherlawoffice.com')
BASE_DIR           = os.path.dirname(os.path.abspath(__file__))

# LawPay credentials
LAWPAY_SECRET_KEY   = os.environ.get('LAWPAY_SECRET_KEY', 'naG8L7vhTWOai4lkJew3kwVhWCxnLjz08wJm9c2qG5bngTfBk9hFyN4OyLZ1O5NC')
LAWPAY_OPERATING_ID = os.environ.get('LAWPAY_OPERATING_ID', 'I-u7KZN9T7CgPW1WaMOndg')
LAWPAY_TRUST_ID     = os.environ.get('LAWPAY_TRUST_ID', 'ajUpcpeuTBKGIM4JMOGo2w')

# Resend API key (for payment email)
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', 're_6CS7mGhu_CDgKBwA7c2P46uwLubnMM4zc')

LOB_API_KEY    = os.environ.get('LOB_API_KEY', '')
REDFAX_DOMAIN  = os.environ.get('REDFAX_DOMAIN', 'redfax.com')  # email-to-fax gateway domain
FIRM_NAME      = os.environ.get('FIRM_NAME', 'Butcher Law Office LLC')
FIRM_ADDRESS1  = os.environ.get('FIRM_ADDRESS1', '116 Hwy 99 N #101')
FIRM_CITY      = os.environ.get('FIRM_CITY', 'Eugene')
FIRM_STATE     = os.environ.get('FIRM_STATE', 'OR')
FIRM_ZIP       = os.environ.get('FIRM_ZIP', '97402')

# Dropbox Sign API key (for verifying webhook signatures)
DSIGN_API_KEY = os.environ.get('DSIGN_API_KEY', '4270ba333e457cc394bd924de0bdebda30c603bb3d8bddb4cd445876629cce54')

# In-memory store: signature_request_id -> payment details
# Populated by the library when sending for signature
pending_payments = {}

# ââ LawPay helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def lawpay_create_payment_request(client_email, amount_cents, description, account_type='operating'):
    """Create a LawPay payment request. Returns (payment_link, request_id) or raises."""
    account_id = LAWPAY_TRUST_ID if account_type == 'trust' else LAWPAY_OPERATING_ID
    payload = json.dumps({
        'amount': amount_cents,
        'account_id': account_id,
        'description': description,
        'email_address': client_email,
    }).encode('utf-8')
    auth = base64.b64encode(f'{LAWPAY_SECRET_KEY}:'.encode()).decode()
    req = urllib.request.Request(
        'https://api.affinipay.com/v1/payment_requests',
        data=payload,
        headers={'Content-Type': 'application/json', 'Authorization': f'Basic {auth}'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    pay_link = data.get('url') or f"https://secure.lawpay.com/pages/{data['id']}"
    return pay_link, data['id']

def resend_payment_email(client_name, client_email, pay_link, amount_str, description, account_type):
    """Send the payment email via Resend after signing."""
    acct_label = 'Trust / IOLTA Account' if account_type == 'trust' else 'Operating Account'
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
body{{font-family:Georgia,serif;font-size:11pt;color:#1a1612;margin:0;padding:0;background:#f5f2ec}}
.wrap{{max-width:600px;margin:0 auto;background:#fff}}
.hdr{{background:#1a1612;padding:24px 36px}}
.firm{{color:#fff;font-size:13pt;font-weight:bold}}
.sub{{color:#c8bfaa;font-size:9pt;margin-top:3px}}
.body{{padding:36px}}
p{{margin:0 0 12pt;line-height:1.65}}
.box{{background:#f5f0e8;border:2px solid #c4983a;border-radius:4px;padding:20px 24px;margin:20pt 0;text-align:center}}
.amt{{font-size:24pt;font-weight:bold;color:#1a1612;margin-bottom:8px}}
.desc{{font-size:11pt;color:#6b6355;margin-bottom:16px}}
.btn{{display:inline-block;background:#8b2020;color:white;padding:12px 32px;border-radius:3px;text-decoration:none;font-size:13pt;font-weight:bold}}
.ftr{{background:#f5f2ec;padding:14px 36px;font-size:9pt;color:#9b9080;text-align:center}}
</style></head><body><div class="wrap">
<div class="hdr"><div class="firm">Butcher Law Office, LLC</div>
<div class="sub">116 Hwy 99 N #101 &bull; Eugene, OR 97402 &bull; (541) 762-1967</div></div>
<div class="body">
<p>Dear {client_name},</p>
<p>Thank you for signing your fee agreement. Your payment request is now ready.</p>
<div class="box">
<div class="amt">${float(amount_str):.2f}</div>
<div class="desc">{description}<br><small>{acct_label}</small></div>
<a class="btn" href="{pay_link}">Pay Now</a>
</div>
<p>Your payment is processed securely through LawPay, trusted by law firms nationwide for IOLTA-compliant payment processing.</p>
<p>Sincerely,<br><strong>Tomas K. Butcher</strong><br>Attorney at Law, OSB #082807</p>
</div>
<div class="ftr">Payments processed by LawPay in compliance with ABA and IOLTA guidelines.</div>
</div></body></html>"""
    payload = json.dumps({
        'from': 'Tomas K. Butcher <tom@butcherlawoffice.com>',
        'to': [client_email],
        'subject': f'Payment Request from Butcher Law Office \u2014 ${float(amount_str):.2f}',
        'html': html,
        'reply_to': 'tom@butcherlawoffice.com',
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.resend.com/emails',
        data=payload,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {RESEND_API_KEY}'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

# ââ Dropbox Sign webhook ââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/webhook/dropbox-sign', methods=['POST'])
def dropbox_sign_webhook():
    """
    Receives Dropbox Sign event callbacks.
    When a signature request is fully signed, fires the pending LawPay payment request.
    """
    # Dropbox Sign sends JSON with a 'payload' field containing the event data
    # Content-Type is application/x-www-form-urlencoded with field 'json'
    raw = request.form.get('json') or request.get_data(as_text=True)
    if not raw:
        return 'Hello API Event Received', 200  # Dropbox Sign health check

    try:
        data = json.loads(raw)
    except Exception:
        return 'Hello API Event Received', 200

    event = data.get('event', {})
    event_type = event.get('event_type', '')
    logger.info(f'Dropbox Sign event: {event_type}')

    # We only care about fully signed events
    if event_type != 'signature_request_all_signed':
        return 'Hello API Event Received', 200

    sig_req = data.get('signature_request', {})
    sig_req_id = sig_req.get('signature_request_id', '')

    logger.info(f'All signed: {sig_req_id}')

    # Look up pending payment
    payment = pending_payments.pop(sig_req_id, None)
    if not payment:
        logger.info(f'No pending payment for {sig_req_id} â nothing to do')
        return 'Hello API Event Received', 200

    client_name  = payment.get('client_name', '')
    client_email = payment.get('client_email', '')
    amount_str   = payment.get('amount', '0')
    account_type = payment.get('account_type', 'operating')
    description  = payment.get('description', 'Legal Services â Fee Agreement')

    try:
        amount_cents = round(float(amount_str) * 100)
        pay_link, pay_id = lawpay_create_payment_request(
            client_email, amount_cents, description, account_type
        )
        logger.info(f'LawPay payment request created: {pay_id} for {client_email}')

        # Send email via Resend
        resend_payment_email(client_name, client_email, pay_link, amount_str, description, account_type)
        logger.info(f'Payment email sent to {client_email}')

    except Exception as e:
        logger.error(f'Payment request failed for {sig_req_id}: {e}')

    return 'Hello API Event Received', 200

# ââ Pending payment registration (called by the browser app) âââââââââââââ

@app.route('/webhook/register-payment', methods=['POST'])
def register_payment():
    """
    Called by the Document Execution Engine when a signature request is sent.
    Stores payment intent so it can be triggered when signing completes.
    """
    data = request.get_json(force=True) or {}
    sig_req_id   = data.get('signature_request_id', '').strip()
    client_name  = data.get('client_name', '').strip()
    client_email = data.get('client_email', '').strip()
    amount       = data.get('amount', '').strip()
    account_type = data.get('account_type', 'operating').strip()
    description  = data.get('description', '').strip()

    if not sig_req_id or not client_email or not amount:
        return jsonify({'error': 'Missing required fields'}), 400

    pending_payments[sig_req_id] = {
        'client_name':  client_name,
        'client_email': client_email,
        'amount':       amount,
        'account_type': account_type,
        'description':  description,
    }
    logger.info(f'Payment registered for {sig_req_id}: ${amount} to {client_email}')
    return jsonify({'status': 'registered', 'signature_request_id': sig_req_id}), 200

ATTORNEY_DEFAULTS = {
    'attorney_name':   'Tomas K. Butcher',
    'attorney_bar':    '082807',
    'firm_name':       'Butcher Law Office, LLC',
    'firm_address':    '116 Hwy 99 N #101',
    'firm_city_state': 'Eugene, OR 97402',
    'firm_phone':      '541 762-1967',
    'firm_email':      'tom@butcherlawoffice.com',
}

DOCS = {
    'extend_time':               {'script': 'generate_motion_extend_time.js',                'label': 'Motion for Extension of Time to File Deficient Documents'},
    'extend_time_pre341_pancic': {'script': 'generate_motion_extend_time_pre341_pancic.js',  'label': 'Motion for Extension of Time â Deficient Documents (Pre-341, Trustee Pancic)'},
    'extend_time_pre341_other':  {'script': 'generate_motion_extend_time_pre341_other.js',   'label': 'Motion for Extension of Time â Deficient Documents (Pre-341)'},
    'extend_plan':               {'script': 'generate_motion_extend_plan.js',                'label': 'Motion for Extension of Time to File Chapter 13 Plan'},
    'extend_financial_mgmt':     {'script': 'generate_motion_extend_financial_mgmt.js',      'label': 'Motion for Extension of Time to File Financial Management Course Certificate'},
    'extend_filing_fee':         {'script': 'generate_motion_extend_filing_fee.js',          'label': 'Motion for Extension of Time to Pay Filing Fee'},
    'dismiss_vol':               {'script': 'generate_motion_dismiss.js',                    'label': 'Motion to Voluntarily Dismiss Case'},
    'convert_13_to_7':           {'script': 'generate_motion_convert_13_to_7.js',            'label': 'Motion to Convert Case from Chapter 13 to Chapter 7'},
    'convert_7_to_13':           {'script': 'generate_motion_convert_7_to_13.js',            'label': 'Motion to Convert Case from Chapter 7 to Chapter 13'},
    'redeem':                    {'script': 'generate_motion_redeem.js',                     'label': 'Motion to Redeem Property â 11 U.S.C. Â§ 722'},
    'extend_stay':               {'script': 'generate_motion_extend_stay.js',                'label': 'Motion to Extend Automatic Stay â 11 U.S.C. Â§ 362(c)(3)'},
    'declaration_extend_stay':   {'script': 'generate_declaration_extend_stay.js',           'label': 'Debtor Declaration â Motion to Extend Stay'},
    'delay_discharge':           {'script': 'generate_motion_delay_discharge.js',            'label': 'Motion to Delay Entry of Discharge'},
    'substitution':              {'script': 'generate_motion_substitution.js',               'label': 'Stipulation for Substitution of Attorney'},
    'withdraw':                  {'script': 'generate_motion_withdraw.js',                   'label': 'Motion to Withdraw as Counsel'},
    'objection_trustee_dismiss': {'script': 'generate_objection_trustee_dismiss.js',         'label': "Objection to Trustee's Motion to Dismiss"},
    'objection_trustee_convert': {'script': 'generate_objection_trustee_convert.js',         'label': "Objection to Trustee's Motion to Convert"},
    'letter_mortgage_auth':      {'script': 'generate_letter_mortgage_auth.js',              'label': 'Authorization Letter â Mortgage Servicer'},
    'certificate_of_service':    {'script': 'generate_certificate_of_service.js',            'label': 'Certificate of Service'},
}

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'motion_library.html')

def generate_documents(motion_type, data):
    doc = DOCS.get(motion_type)
    if not doc:
        raise ValueError(f'Unknown motion type: {motion_type}')
    script_path = os.path.join(BASE_DIR, doc['script'])
    if not os.path.exists(script_path):
        raise FileNotFoundError(f'Generator script not found: {script_path}')
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ['node', script_path, json.dumps(data)],
            capture_output=True, text=True,
            env={**os.environ, 'OUT_DIR': tmpdir}, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f'Generator failed: {result.stderr or result.stdout}')
        docx_files = [f for f in os.listdir(tmpdir) if f.endswith('.docx')]
        if not docx_files:
            raise FileNotFoundError('No .docx file generated')
        docx_path = os.path.join(tmpdir, docx_files[0])
        subprocess.run(['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', tmpdir, docx_path], capture_output=True, timeout=60)
        pdf_path   = docx_path.replace('.docx', '.pdf')
        base       = os.path.splitext(os.path.basename(docx_path))[0]
        with open(docx_path, 'rb') as f: docx_bytes = f.read()
        pdf_bytes = None
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f: pdf_bytes = f.read()
        return docx_bytes, pdf_bytes, base

def send_email(motion_type, data, docx_bytes, pdf_bytes, base):
    label   = DOCS[motion_type]['label']
    case_no = data.get('case_number', 'Unknown')
    debtor  = data.get('debtor_name') or data.get('client_name', 'Unknown')
    today   = date.today().strftime('%B %d, %Y')
    subject = f'{label} â {debtor} â Case {case_no}'
    body    = f'{label}\n\nCase: {debtor}\nCase No.: {case_no}\nGenerated: {today}\n\nAttachments:\n  â¢ {base}.docx\n  â¢ {base}.pdf\n'
    recipients = [ATTORNEY_EMAIL, VA_EMAIL]
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER; msg['To'] = ', '.join(recipients); msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    p = MIMEBase('application', 'vnd.openxmlformats-officedocument.wordprocessingml.document')
    p.set_payload(docx_bytes); encoders.encode_base64(p)
    p.add_header('Content-Disposition', f'attachment; filename="{base}.docx"')
    msg.attach(p)
    if pdf_bytes:
        p2 = MIMEBase('application', 'pdf'); p2.set_payload(pdf_bytes); encoders.encode_base64(p2)
        p2.add_header('Content-Disposition', f'attachment; filename="{base}.pdf"')
        msg.attach(p2)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        s.sendmail(GMAIL_USER, recipients, msg.as_string())
    logger.info(f'Emailed: {label} â {debtor} ({case_no})')


# ── Internal send helpers ────────────────────────────────────────────────────
def _send_fax_internal(fax_number, pdf_b64, doc_title, client_name='', case_no=''):
    """Send a fax via RedFax email-to-fax gateway using Resend."""
    if not RESEND_API_KEY:
        return {'error': 'RESEND_API_KEY not configured'}
    digits = ''.join(c for c in fax_number if c.isdigit())
    if len(digits) == 10:
        digits = '1' + digits
    fax_email = f'{digits}@{REDFAX_DOMAIN}'
    subject = doc_title
    if client_name: subject += f' — {client_name}'
    if case_no:     subject += f' (Case {case_no})'
    import urllib.request as _ur, json as _json
    body = {
        'from':    f'{FIRM_NAME} <tom@butcherlawoffice.com>',
        'to':      [fax_email],
        'subject': subject,
        'text':    f'{FIRM_NAME}\nFax transmission: {subject}',
        'attachments': [{
            'filename': doc_title.replace(' ', '_') + '.pdf',
            'content':  pdf_b64
        }]
    }
    req = _ur.Request(
        'https://api.resend.com/emails',
        data=_json.dumps(body).encode(),
        headers={'Authorization': f'Bearer {RESEND_API_KEY}', 'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with _ur.urlopen(req) as resp:
            result = _json.loads(resp.read())
        logger.info(f'Fax queued: {doc_title} → {fax_email}')
        return {'status': 'success', 'fax_to': fax_number, 'fax_email': fax_email, 'resend_id': result.get('id')}
    except Exception as e:
        logger.error(f'Fax send error: {e}')
        return {'error': str(e)}


def _send_mail_internal(pdf_b64, doc_title, client_name='', case_no='',
                         to_name='', to_street='', to_csz='', mail_type='usps_first_class', color=False):
    """Send physical mail via Lob API."""
    if not LOB_API_KEY:
        return {'error': 'LOB_API_KEY not configured'}
    if not all([pdf_b64, to_name, to_street, to_csz]):
        return {'error': 'Missing recipient address fields'}
    import re as _re, json as _json, urllib.request as _ur, base64 as _b64
    csz_match = _re.match(r'^(.+?),?\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', to_csz.strip())
    if not csz_match:
        return {'error': f'Cannot parse city/state/zip from: {to_csz}'}
    to_city, to_state, to_zip = csz_match.groups()
    lob_body = {
        'description': f'{doc_title} — {client_name or to_name}',
        'to': {
            'name':            to_name,
            'address_line1':   to_street,
            'address_city':    to_city.strip(),
            'address_state':   to_state,
            'address_zip':     to_zip,
            'address_country': 'US'
        },
        'from': {
            'name':            f'Tomas K. Butcher, {FIRM_NAME}',
            'address_line1':   FIRM_ADDRESS1,
            'address_city':    FIRM_CITY,
            'address_state':   FIRM_STATE,
            'address_zip':     FIRM_ZIP,
            'address_country': 'US'
        },
        'file':              f'<html><head></head><body style="margin:0;padding:0"><pdf pages="all" src="data:application/pdf;base64,{pdf_b64}"/></body></html>',
        'color':             color,
        'double_sided':      False,
        'address_placement': 'insert_blank_page',
        'mail_type':         mail_type
    }
    auth_str = _b64.b64encode(f'{LOB_API_KEY}:'.encode()).decode()
    req = _ur.Request(
        'https://api.lob.com/v1/letters',
        data=_json.dumps(lob_body).encode(),
        headers={'Authorization': f'Basic {auth_str}', 'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with _ur.urlopen(req) as resp:
            result = _json.loads(resp.read())
        logger.info(f'Mail queued via Lob: {doc_title} → {to_name}, {to_city} {to_state}')
        return {
            'status': 'success',
            'lob_id': result.get('id'),
            'expected_delivery': result.get('expected_delivery_date'),
            'mail_to': f'{to_name}, {to_street}, {to_city}, {to_state} {to_zip}'
        }
    except Exception as e:
        logger.error(f'Lob mail error: {e}')
        return {'error': str(e)}


def _send_resend_doc(to_email, doc_title, debtor, case_no, pdf_bytes, docx_bytes, base):
    """Send document via Resend to a custom email address."""
    if not RESEND_API_KEY:
        return
    import urllib.request as _ur, json as _json, base64 as _b64
    attachments = []
    if docx_bytes:
        attachments.append({'filename': base+'.docx', 'content': _b64.b64encode(docx_bytes).decode()})
    if pdf_bytes:
        attachments.append({'filename': base+'.pdf', 'content': _b64.b64encode(pdf_bytes).decode()})
    body = {
        'from':        f'{FIRM_NAME} <tom@butcherlawoffice.com>',
        'to':          [to_email],
        'subject':     f'{doc_title} — {debtor} — Case {case_no}',
        'text':        f'{doc_title}\nCase: {debtor}\nCase No.: {case_no}',
        'attachments': attachments
    }
    req = _ur.Request(
        'https://api.resend.com/emails',
        data=_json.dumps(body).encode(),
        headers={'Authorization': f'Bearer {RESEND_API_KEY}', 'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with _ur.urlopen(req) as resp: pass
        logger.info(f'Resend doc email sent to {to_email}')
    except Exception as e:
        logger.error(f'Resend doc email error: {e}')


def handle_request(motion_type):
    try:
        payload = request.get_json(force=True) or {}
        entry   = payload.get('entry', payload)
        data    = {**ATTORNEY_DEFAULTS, **entry}
        for f in ['delay_days', 'payments_due', 'payments_made']:
            if f in data:
                try: data[f] = int(data[f])
                except: pass
        logger.info(f'Generating: {DOCS[motion_type]["label"]} â {data.get("debtor_name") or data.get("client_name")} {data.get("case_number")}')
        docx_bytes, pdf_bytes, base = generate_documents(motion_type, data)
        send_email(motion_type, data, docx_bytes, pdf_bytes, base)
        send_dest = entry.get('send_dest', 'email')
        resp_data = {
            'status': 'success',
            'document': DOCS[motion_type]['label'],
            'case': data.get('case_number'),
            'debtor': data.get('debtor_name') or data.get('client_name'),
            'send_dest': send_dest
        }

        if send_dest == 'fax':
            fax_number = entry.get('fax_number', '')
            if fax_number and pdf_bytes:
                fax_resp = _send_fax_internal(
                    fax_number=fax_number,
                    pdf_b64=base64.b64encode(pdf_bytes).decode(),
                    doc_title=DOCS[motion_type]['label'],
                    client_name=data.get('debtor_name') or data.get('client_name', ''),
                    case_no=data.get('case_number', '')
                )
                resp_data['fax_result'] = fax_resp
            else:
                resp_data['warning'] = 'Fax number or PDF missing; falling back to email'
                send_email(motion_type, data, docx_bytes, pdf_bytes, base)
                resp_data['emailed_to'] = [ATTORNEY_EMAIL, VA_EMAIL]

        elif send_dest == 'mail':
            if pdf_bytes:
                mail_resp = _send_mail_internal(
                    pdf_b64=base64.b64encode(pdf_bytes).decode(),
                    doc_title=DOCS[motion_type]['label'],
                    client_name=data.get('debtor_name') or data.get('client_name', ''),
                    case_no=data.get('case_number', ''),
                    to_name=entry.get('mail_name', ''),
                    to_street=entry.get('mail_street', ''),
                    to_csz=entry.get('mail_csz', ''),
                    mail_type=entry.get('mail_type', 'usps_first_class')
                )
                resp_data['mail_result'] = mail_resp
            else:
                resp_data['warning'] = 'PDF not available; falling back to email'
                send_email(motion_type, data, docx_bytes, pdf_bytes, base)
                resp_data['emailed_to'] = [ATTORNEY_EMAIL, VA_EMAIL]

        elif send_dest == 'download':
            # Return PDF as base64 for browser download
            if pdf_bytes:
                resp_data['pdf_base64'] = base64.b64encode(pdf_bytes).decode()
                resp_data['filename'] = base + '.pdf'
            else:
                resp_data['warning'] = 'PDF service unavailable'

        else:  # email (default)
            send_dest_email = entry.get('send_email', '')
            if send_dest_email:
                # Override recipients if custom email provided
                import smtplib as _smtp
                orig_atty = ATTORNEY_EMAIL
                # Use Resend to send to the custom address
                _send_resend_doc(
                    to_email=send_dest_email,
                    doc_title=DOCS[motion_type]['label'],
                    debtor=data.get('debtor_name') or data.get('client_name', ''),
                    case_no=data.get('case_number', ''),
                    pdf_bytes=pdf_bytes,
                    docx_bytes=docx_bytes,
                    base=base
                )
                resp_data['emailed_to'] = [send_dest_email]
            else:
                send_email(motion_type, data, docx_bytes, pdf_bytes, base)
                resp_data['emailed_to'] = [ATTORNEY_EMAIL, VA_EMAIL]

        return jsonify(resp_data), 200
    except Exception as e:
        logger.error(f'Error â {motion_type}: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

# ââ ROUTES ââââââââââââââââââââââââââââââââââââââââââââââââââ
@app.route('/webhook/motion-extend-time',               methods=['POST'])
def r01(): return handle_request('extend_time')
@app.route('/webhook/motion-extend-time-pre341-pancic', methods=['POST'])
def r02(): return handle_request('extend_time_pre341_pancic')
@app.route('/webhook/motion-extend-time-pre341-other',  methods=['POST'])
def r03(): return handle_request('extend_time_pre341_other')
@app.route('/webhook/motion-extend-plan',               methods=['POST'])
def r04(): return handle_request('extend_plan')
@app.route('/webhook/motion-extend-financial-mgmt',     methods=['POST'])
def r05(): return handle_request('extend_financial_mgmt')
@app.route('/webhook/motion-extend-filing-fee',         methods=['POST'])
def r06(): return handle_request('extend_filing_fee')
@app.route('/webhook/motion-dismiss',                   methods=['POST'])
def r07(): return handle_request('dismiss_vol')
@app.route('/webhook/motion-convert-13-to-7',           methods=['POST'])
def r08(): return handle_request('convert_13_to_7')
@app.route('/webhook/motion-convert-7-to-13',           methods=['POST'])
def r09(): return handle_request('convert_7_to_13')
@app.route('/webhook/motion-redeem',                    methods=['POST'])
def r10(): return handle_request('redeem')
@app.route('/webhook/motion-extend-stay',               methods=['POST'])
def r11(): return handle_request('extend_stay')
@app.route('/webhook/declaration-extend-stay',          methods=['POST'])
def r12(): return handle_request('declaration_extend_stay')
@app.route('/webhook/motion-delay-discharge',           methods=['POST'])
def r13(): return handle_request('delay_discharge')
@app.route('/webhook/motion-substitution',              methods=['POST'])
def r14(): return handle_request('substitution')
@app.route('/webhook/motion-withdraw',                  methods=['POST'])
def r15(): return handle_request('withdraw')
@app.route('/webhook/objection-trustee-dismiss',        methods=['POST'])
def r16(): return handle_request('objection_trustee_dismiss')
@app.route('/webhook/objection-trustee-convert',        methods=['POST'])
def r17(): return handle_request('objection_trustee_convert')
@app.route('/webhook/letter-mortgage-auth',             methods=['POST'])
def r18(): return handle_request('letter_mortgage_auth')
@app.route('/webhook/certificate-of-service',           methods=['POST'])
def r19(): return handle_request('certificate_of_service')


# ── Send via Fax (RedFax email-to-fax) ──────────────────────────────────────
@app.route('/send/fax', methods=['POST'])
def send_fax():
    try:
        payload    = request.get_json(force=True) or {}
        fax_number = payload.get('fax_number', '').strip()
        pdf_b64    = payload.get('pdf_base64', '')
        doc_title  = payload.get('doc_title', 'Document')
        client_name= payload.get('client_name', '')
        case_no    = payload.get('case_number', '')

        if not fax_number:
            return jsonify({'error': 'fax_number is required'}), 400
        if not pdf_b64:
            return jsonify({'error': 'pdf_base64 is required'}), 400
        if not RESEND_API_KEY:
            return jsonify({'error': 'RESEND_API_KEY not configured'}), 500

        # Normalize fax number: strip all non-digits
        digits = ''.join(c for c in fax_number if c.isdigit())
        if len(digits) == 10:
            digits = '1' + digits  # add country code
        fax_email = f'{digits}@{REDFAX_DOMAIN}'

        pdf_bytes = base64.b64decode(pdf_b64)
        subject   = f'{doc_title}'
        if client_name: subject += f' — {client_name}'
        if case_no:     subject += f' (Case {case_no})'

        # Send via Resend with PDF attachment to fax gateway
        import urllib.request as _ur, json as _json
        body = {
            'from': f'{FIRM_NAME} <tom@butcherlawoffice.com>',
            'to':   [fax_email],
            'subject': subject,
            'text': f'{FIRM_NAME}\nFax transmission: {subject}',
            'attachments': [{
                'filename': f'{doc_title.replace(" ", "_")}.pdf',
                'content':  pdf_b64
            }]
        }
        req = _ur.Request(
            'https://api.resend.com/emails',
            data=_json.dumps(body).encode(),
            headers={
                'Authorization': f'Bearer {RESEND_API_KEY}',
                'Content-Type': 'application/json'
            },
            method='POST'
        )
        with _ur.urlopen(req) as resp:
            result = _json.loads(resp.read())

        logger.info(f'Fax queued: {doc_title} → {fax_email}')
        return jsonify({'status': 'success', 'fax_to': fax_number, 'fax_email': fax_email, 'resend_id': result.get('id')}), 200

    except Exception as e:
        logger.error(f'Fax error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ── Send via Physical Mail (Lob) ─────────────────────────────────────────────
@app.route('/send/mail', methods=['POST'])
def send_mail():
    try:
        payload    = request.get_json(force=True) or {}
        pdf_b64    = payload.get('pdf_base64', '')
        doc_title  = payload.get('doc_title', 'Document')
        client_name= payload.get('client_name', '')
        case_no    = payload.get('case_number', '')
        to_name    = payload.get('mail_name', '').strip()
        to_street  = payload.get('mail_street', '').strip()
        to_csz     = payload.get('mail_city_state_zip', '').strip()  # e.g. "Portland, OR 97201"
        color      = payload.get('color', False)
        mail_type  = payload.get('mail_type', 'usps_first_class')  # or 'certified'

        if not LOB_API_KEY:
            return jsonify({'error': 'LOB_API_KEY not configured'}), 500
        if not all([pdf_b64, to_name, to_street, to_csz]):
            return jsonify({'error': 'pdf_base64, mail_name, mail_street, mail_city_state_zip are required'}), 400

        # Parse city/state/zip from "Portland, OR 97201" or "Portland OR 97201"
        import re as _re
        csz_match = _re.match(r'^(.+?),?\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', to_csz.strip())
        if not csz_match:
            return jsonify({'error': f'Cannot parse city/state/zip: {to_csz}'}), 400
        to_city, to_state, to_zip = csz_match.groups()

        pdf_bytes  = base64.b64decode(pdf_b64)

        import urllib.request as _ur, json as _json
        from urllib.parse import urlencode as _ue

        # Upload PDF to Lob
        boundary = 'ButcherLawBoundary'
        body_parts = []
        body_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="description"\r\n\r\n{doc_title}\r\n')
        pdf_part = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="letter.pdf"\r\n'
            f'Content-Type: application/pdf\r\n\r\n'
        )
        body = (
            pdf_part.encode() + pdf_bytes +
            f'\r\n--{boundary}--\r\n'.encode()
        )

        # Lob create letter endpoint
        lob_body = {
            'description':     f'{doc_title} — {client_name or to_name}',
            'to[name]':        to_name,
            'to[address_line1]': to_street,
            'to[address_city]':  to_city.strip(),
            'to[address_state]': to_state,
            'to[address_zip]':   to_zip,
            'to[address_country]': 'US',
            'from[name]':          f'Tomas K. Butcher, {FIRM_NAME}',
            'from[address_line1]': FIRM_ADDRESS1,
            'from[address_city]':  FIRM_CITY,
            'from[address_state]': FIRM_STATE,
            'from[address_zip]':   FIRM_ZIP,
            'from[address_country]': 'US',
            'color':           'true' if color else 'false',
            'double_sided':    'false',
            'address_placement': 'insert_blank_page',
            'mail_type':       mail_type,
            'file':            f'<html><head></head><body><pdf src="data:application/pdf;base64,{pdf_b64}"/></body></html>'
        }

        # Use multipart form for Lob (it prefers it for file uploads)
        # Actually Lob accepts JSON with hosted_url or HTML; we'll send as HTML wrapping the PDF
        lob_json_body = {
            'description':    f'{doc_title} — {client_name or to_name}',
            'to': {
                'name':             to_name,
                'address_line1':    to_street,
                'address_city':     to_city.strip(),
                'address_state':    to_state,
                'address_zip':      to_zip,
                'address_country':  'US'
            },
            'from': {
                'name':             f'Tomas K. Butcher, {FIRM_NAME}',
                'address_line1':    FIRM_ADDRESS1,
                'address_city':     FIRM_CITY,
                'address_state':    FIRM_STATE,
                'address_zip':      FIRM_ZIP,
                'address_country':  'US'
            },
            'file':          f'<html><head></head><body style="margin:0;padding:0"><pdf pages="all" src="data:application/pdf;base64,{pdf_b64}"/></body></html>',
            'color':         color,
            'double_sided':  False,
            'address_placement': 'insert_blank_page',
            'mail_type':     mail_type
        }

        import base64 as _b64
        auth_str = _b64.b64encode(f'{LOB_API_KEY}:'.encode()).decode()
        req = _ur.Request(
            'https://api.lob.com/v1/letters',
            data=_json.dumps(lob_json_body).encode(),
            headers={
                'Authorization': f'Basic {auth_str}',
                'Content-Type':  'application/json'
            },
            method='POST'
        )
        with _ur.urlopen(req) as resp:
            result = _json.loads(resp.read())

        logger.info(f'Mail queued via Lob: {doc_title} → {to_name}, {to_city}, {to_state}')
        return jsonify({
            'status':       'success',
            'lob_id':       result.get('id'),
            'expected_delivery': result.get('expected_delivery_date'),
            'mail_to':      f'{to_name}, {to_street}, {to_city}, {to_state} {to_zip}',
            'mail_type':    mail_type
        }), 200

    except Exception as e:
        logger.error(f'Mail error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'documents': len(DOCS), 'routes': list(DOCS.keys())}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f'Starting on port {port} â {len(DOCS)} documents registered')
    app.run(host='0.0.0.0', port=port, debug=False)
