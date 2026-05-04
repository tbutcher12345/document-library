"""
Butcher Law Office — Document Generator Server
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

# Dropbox Sign API key (for verifying webhook signatures)
DSIGN_API_KEY = os.environ.get('DSIGN_API_KEY', '4270ba333e457cc394bd924de0bdebda30c603bb3d8bddb4cd445876629cce54')

# In-memory store: signature_request_id -> payment details
# Populated by the library when sending for signature
pending_payments = {}

# ── LawPay helpers ────────────────────────────────────────────────────────

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

# ── Dropbox Sign webhook ──────────────────────────────────────────────────

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
        logger.info(f'No pending payment for {sig_req_id} — nothing to do')
        return 'Hello API Event Received', 200

    client_name  = payment.get('client_name', '')
    client_email = payment.get('client_email', '')
    amount_str   = payment.get('amount', '0')
    account_type = payment.get('account_type', 'operating')
    description  = payment.get('description', 'Legal Services — Fee Agreement')

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

# ── Pending payment registration (called by the browser app) ─────────────

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
    'extend_time_pre341_pancic': {'script': 'generate_motion_extend_time_pre341_pancic.js',  'label': 'Motion for Extension of Time — Deficient Documents (Pre-341, Trustee Pancic)'},
    'extend_time_pre341_other':  {'script': 'generate_motion_extend_time_pre341_other.js',   'label': 'Motion for Extension of Time — Deficient Documents (Pre-341)'},
    'extend_plan':               {'script': 'generate_motion_extend_plan.js',                'label': 'Motion for Extension of Time to File Chapter 13 Plan'},
    'extend_financial_mgmt':     {'script': 'generate_motion_extend_financial_mgmt.js',      'label': 'Motion for Extension of Time to File Financial Management Course Certificate'},
    'extend_filing_fee':         {'script': 'generate_motion_extend_filing_fee.js',          'label': 'Motion for Extension of Time to Pay Filing Fee'},
    'dismiss_vol':               {'script': 'generate_motion_dismiss.js',                    'label': 'Motion to Voluntarily Dismiss Case'},
    'convert_13_to_7':           {'script': 'generate_motion_convert_13_to_7.js',            'label': 'Motion to Convert Case from Chapter 13 to Chapter 7'},
    'convert_7_to_13':           {'script': 'generate_motion_convert_7_to_13.js',            'label': 'Motion to Convert Case from Chapter 7 to Chapter 13'},
    'redeem':                    {'script': 'generate_motion_redeem.js',                     'label': 'Motion to Redeem Property — 11 U.S.C. § 722'},
    'extend_stay':               {'script': 'generate_motion_extend_stay.js',                'label': 'Motion to Extend Automatic Stay — 11 U.S.C. § 362(c)(3)'},
    'declaration_extend_stay':   {'script': 'generate_declaration_extend_stay.js',           'label': 'Debtor Declaration — Motion to Extend Stay'},
    'delay_discharge':           {'script': 'generate_motion_delay_discharge.js',            'label': 'Motion to Delay Entry of Discharge'},
    'substitution':              {'script': 'generate_motion_substitution.js',               'label': 'Stipulation for Substitution of Attorney'},
    'withdraw':                  {'script': 'generate_motion_withdraw.js',                   'label': 'Motion to Withdraw as Counsel'},
    'objection_trustee_dismiss': {'script': 'generate_objection_trustee_dismiss.js',         'label': "Objection to Trustee's Motion to Dismiss"},
    'objection_trustee_convert': {'script': 'generate_objection_trustee_convert.js',         'label': "Objection to Trustee's Motion to Convert"},
    'letter_mortgage_auth':      {'script': 'generate_letter_mortgage_auth.js',              'label': 'Authorization Letter — Mortgage Servicer'},
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
    subject = f'{label} — {debtor} — Case {case_no}'
    body    = f'{label}\n\nCase: {debtor}\nCase No.: {case_no}\nGenerated: {today}\n\nAttachments:\n  • {base}.docx\n  • {base}.pdf\n'
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
    logger.info(f'Emailed: {label} — {debtor} ({case_no})')

def handle_request(motion_type):
    try:
        payload = request.get_json(force=True) or {}
        entry   = payload.get('entry', payload)
        data    = {**ATTORNEY_DEFAULTS, **entry}
        for f in ['delay_days', 'payments_due', 'payments_made']:
            if f in data:
                try: data[f] = int(data[f])
                except: pass
        logger.info(f'Generating: {DOCS[motion_type]["label"]} — {data.get("debtor_name") or data.get("client_name")} {data.get("case_number")}')
        docx_bytes, pdf_bytes, base = generate_documents(motion_type, data)
        send_email(motion_type, data, docx_bytes, pdf_bytes, base)
        return jsonify({'status': 'success', 'document': DOCS[motion_type]['label'], 'case': data.get('case_number'), 'debtor': data.get('debtor_name') or data.get('client_name'), 'emailed_to': [ATTORNEY_EMAIL, VA_EMAIL]}), 200
    except Exception as e:
        logger.error(f'Error — {motion_type}: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

# ── ROUTES ──────────────────────────────────────────────────
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

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'documents': len(DOCS), 'routes': list(DOCS.keys())}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f'Starting on port {port} — {len(DOCS)} documents registered')
    app.run(host='0.0.0.0', port=port, debug=False)
