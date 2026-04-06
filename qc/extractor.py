"""
Visa Application QC - PDF Field Extractor
Extracts structured data from visa applications and supporting documents.
Supports: Schengen (France), UK Visa, Passport copies, Flight tickets, Invitation letters.
"""

import re
import pdfplumber
from datetime import datetime, timedelta


# ─── Date Parsing Utility ───────────────────────────────────────────
DATE_PATTERNS = [
    (r'\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b', 'dmy'),        # 02/10/1962, 06-04-2019
    (r'\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b', 'ymd'),        # 2019-04-06
    (r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b', 'dMy'),  # 17 April 1979
    (r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b', 'Mdy'),  # April 17, 1979
]

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12
}


def parse_date(text):
    """Parse a date string into a standardized datetime object."""
    if not text:
        return None
    text = text.strip()
    for pattern, fmt in DATE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                if fmt == 'dmy':
                    return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                elif fmt == 'ymd':
                    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif fmt == 'dMy':
                    month = MONTH_MAP[m.group(2).lower()]
                    return datetime(int(m.group(3)), month, int(m.group(1)))
                elif fmt == 'Mdy':
                    month = MONTH_MAP[m.group(1).lower()]
                    return datetime(int(m.group(3)), month, int(m.group(2)))
            except (ValueError, KeyError):
                continue
    return None


def format_date(dt):
    """Format datetime to DD/MM/YYYY for display."""
    if dt:
        return dt.strftime('%d/%m/%Y')
    return None


# ─── PDF Text Extraction ────────────────────────────────────────────

def extract_text_from_pdf(filepath):
    """Extract all text from a PDF file, page by page."""
    pages = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
    except Exception as e:
        pages = [f"ERROR: Could not read PDF - {str(e)}"]
    return pages


def full_text(pages):
    """Join all pages into a single text block."""
    return "\n".join(pages)


# ─── Document Type Detection ────────────────────────────────────────

def detect_document_type(pages):
    """Detect what type of document this PDF is."""
    text = full_text(pages).lower()

    if 'application for schengen visa' in text or 'harmonised application form' in text:
        return 'schengen_visa'
    if 'uk visas & immigration' in text or 'uk visas and immigration' in text:
        return 'uk_visa'
    if 'registration receipt' in text and 'france-visas' in text:
        return 'france_receipt'
    if 'boarding pass' in text or 'e-ticket' in text or 'itinerary' in text or 'flight' in text or 'pnr' in text:
        return 'flight_ticket'
    if any(kw in text for kw in ['passport', 'republic of india', 'travel document', 'passeport']):
        # Check if it looks like a passport copy (has MRZ or passport-specific fields)
        if any(kw in text for kw in ['machine readable', 'p<ind', 'mrz', 'type p', 'date of expiry']):
            return 'passport_copy'
    # Invitation letter detection (must come before covering letter)
    if any(kw in text for kw in ['invitation', 'invite', 'pleased to invite', 'hereby invite']):
        # Distinguish from a covering letter that mentions invitation
        if any(kw in text for kw in ['hereby invite', 'pleased to invite', 'we invite',
                                      'invitation letter', 'letter of invitation', 'inviting you']):
            return 'invitation_letter'
    # Covering letter detection
    if any(kw in text for kw in ['covering letter', 'cover letter', 'to whom it may concern',
                                  'dear visa officer', 'dear sir/madam', 'dear consul',
                                  'i hereby', 'purpose of my visit', 'purpose of my travel',
                                  'i wish to apply', 'applying for a visa', 'visa application letter']):
        return 'covering_letter'
    if 'hotel' in text and ('booking' in text or 'reservation' in text or 'confirmation' in text):
        return 'hotel_booking'
    if 'insurance' in text and ('travel' in text or 'medical' in text or 'policy' in text):
        return 'travel_insurance'
    if 'bank' in text and ('statement' in text or 'balance' in text):
        return 'bank_statement'

    return 'unknown'


DOCUMENT_TYPE_LABELS = {
    'schengen_visa': 'Schengen Visa Application',
    'uk_visa': 'UK Visa Application',
    'france_receipt': 'France-Visas Registration Receipt',
    'flight_ticket': 'Flight Ticket / Itinerary',
    'passport_copy': 'Passport Copy',
    'invitation_letter': 'Invitation Letter',
    'covering_letter': 'Covering Letter',
    'hotel_booking': 'Hotel Booking',
    'travel_insurance': 'Travel Insurance',
    'bank_statement': 'Bank Statement',
    'unknown': 'Unknown Document',
}


# ─── Field Extraction: Schengen Visa ────────────────────────────────

def extract_schengen_fields(pages):
    """Extract fields from a Schengen visa application form."""
    text = full_text(pages)
    fields = {}

    # Helper to clean sidebar noise from extracted values
    def clean_value(val):
        """Remove common sidebar text that gets mixed into field values."""
        if not val:
            return val
        noise = [
            'For official use only', 'Application lodge at', 'Embassy/consulate',
            'Service provider', 'Commercial', 'intermediary', 'Border',
            '(name) :', 'Other :', 'File handled by', 'Supporting documents',
            'Travel document', 'Means of subsistence', 'Invitation', 'TMI',
            'Means of transport', 'Visa decision', 'Refused', 'Issued',
            'From .......', 'Until.....', 'Number of entries', 'Number of days',
            'Valid :', 'Multiple',
        ]
        for n in noise:
            val = val.replace(n, '')
        # Remove checkbox chars
        val = re.sub(r'[n\u25a0\u25a1\u2611\u2610■□☑☐]', '', val)
        val = re.sub(r'\s+', ' ', val).strip()
        return val

    # Field 1: Surname
    m = re.search(r'1\.\s*Surname\s*\[family\s*name\]\s*:?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['surname'] = clean_value(m.group(1))

    # Field 3: First name(s)
    m = re.search(r'3\.\s*First\s*name\(?s?\)?\s*\[given\s*name\(?s?\)?\]\s*:?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['first_name'] = clean_value(m.group(1))

    # Full name from fields 1 + 3
    if 'surname' in fields and 'first_name' in fields:
        fields['full_name'] = f"{fields['surname']} {fields['first_name']}".strip()
    elif 'surname' in fields:
        fields['full_name'] = fields['surname']

    # Field 4: Date of birth (often split across lines in Schengen forms)
    m = re.search(r'4\.\s*Date\s*of\s*birth.*?(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})', text, re.IGNORECASE | re.DOTALL)
    if m:
        fields['date_of_birth'] = m.group(1).strip()
        fields['date_of_birth_parsed'] = parse_date(m.group(1))

    # Field 5: Place of birth - value often on next line after DOB
    # In PDF: "year) : 02/10/1962 BENGALURU Indian" — BENGALURU is place of birth
    m = re.search(r'year\)\s*:\s*\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}\s+([A-Z][A-Z\s,]+?)(?:\s+[A-Z][a-z]|\s*\n)', text)
    if m:
        fields['place_of_birth'] = m.group(1).strip()
    else:
        m = re.search(r'5\.\s*Place\s*of\s*birth\s*:?\s*\n?\s*([A-Z][A-Za-z\s,]+?)(?:\s*7\.|\s*\n)', text)
        if m:
            fields['place_of_birth'] = clean_value(m.group(1))

    # Field 6: Country of birth - look for value on line after label
    m = re.search(r'6\.\s*Country\s*of\s*birth\s*:?\s*\n\s*([A-Z][a-zA-Z]+)', text)
    if m:
        val = m.group(1).strip()
        if val.lower() not in ('other', 'name'):
            fields['country_of_birth'] = val

    # Field 7: Nationality - often appears as "Indian" on the DOB/place line
    # Look for common nationality words near "nationality"
    nationalities_pattern = r'(Indian|British|American|French|German|Chinese|Japanese|Korean|Pakistani|Bangladeshi|Sri\s*Lankan|Nepalese|Canadian|Australian|Italian|Spanish|Dutch|Belgian|Swiss|Austrian|Swedish|Norwegian|Danish|Finnish|Portuguese|Greek|Turkish|Russian|Brazilian|Mexican|Filipino|Thai|Vietnamese|Indonesian|Malaysian|Singaporean|[A-Z][a-z]+an|[A-Z][a-z]+ish|[A-Z][a-z]+ese)\b'
    m = re.search(r'7\.\s*Current\s*nationality.*?' + nationalities_pattern, text, re.IGNORECASE | re.DOTALL)
    if m:
        fields['nationality'] = m.group(1).strip()
    else:
        # Try on the DOB line where nationality often appears
        m = re.search(r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}\s+[A-Z]+\s+(' + nationalities_pattern[1:], text, re.IGNORECASE)
        if m:
            fields['nationality'] = m.group(1).strip()

    # Field 8: Sex - look for "n Male" or "n Female" where n = filled checkbox
    sex_section = re.search(r'8\.\s*Sex\s*:(.*?)9\.', text, re.IGNORECASE | re.DOTALL)
    if sex_section:
        sec = sex_section.group(1)
        # In this PDF, 'n' represents a filled checkbox
        if re.search(r'n\s*Male', sec):
            fields['sex'] = 'Male'
        elif re.search(r'n\s*Female', sec):
            fields['sex'] = 'Female'
        elif 'male' in sec.lower() and 'female' not in sec.lower():
            fields['sex'] = 'Male'

    # Field 9: Civil status - look for 'n' (filled checkbox) before a status
    m = re.search(r'9\.\s*Civil\s*status\s*:(.*?)10\.', text, re.IGNORECASE | re.DOTALL)
    if m:
        sec = m.group(1)
        # Check for filled checkbox marker 'n' before each status
        statuses = [
            ('Widow', r'n\s*Widow'),
            ('Married', r'n\s*Married'),
            ('Single', r'n\s*Single'),
            ('Divorced', r'n\s*Divorced'),
            ('Separated', r'n\s*Separated'),
        ]
        for status_name, pattern in statuses:
            if re.search(pattern, sec):
                fields['civil_status'] = status_name
                break
        # Fallback: first status word found
        if 'civil_status' not in fields:
            for status in ['single', 'married', 'divorced', 'separated', 'widow']:
                if status in sec.lower():
                    fields['civil_status'] = status.capitalize()
                    break

    # Field 13: Passport number - the value is on a line below the header row
    # Look for a standalone alphanumeric code (like Z5340068) near field 13
    m = re.search(r'13\.\s*Number\s*of\s*travel\s*document.*?\n([A-Z]\d{5,})', text, re.IGNORECASE)
    if m:
        fields['passport_number'] = m.group(1).strip().upper()
    else:
        # Try on same line
        m = re.search(r'13\.\s*Number\s*of\s*travel\s*document\s*:?\s*\n?.*?([A-Z]\d{5,})', text, re.IGNORECASE | re.DOTALL)
        if m:
            fields['passport_number'] = m.group(1).strip().upper()

    # Field 14: Date of issue (= Passport Issue Date)
    # Try DD/MM/YYYY format first, then DD Month YYYY, then any parseable date
    date_pattern = r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})'
    m = re.search(r'14\.\s*Date\s*of\s*issue\s*:?\s*\n?\s*' + date_pattern, text, re.IGNORECASE)
    if not m:
        # Fallback: "Date of issue" without field number
        m = re.search(r'Date\s*of\s*issue\s*[:/]?\s*\n?\s*' + date_pattern, text, re.IGNORECASE)
    if m:
        fields['passport_issue_date'] = m.group(1).strip()
        fields['passport_issue_date_parsed'] = parse_date(m.group(1))

    # Field 15: Valid until (= Passport Expiry Date)
    m = re.search(r'15\.\s*Valid\s*until\s*:?\s*\n?\s*' + date_pattern, text, re.IGNORECASE)
    if not m:
        # Fallback: "Valid until" without field number
        m = re.search(r'Valid\s*until\s*[:/]?\s*\n?\s*' + date_pattern, text, re.IGNORECASE)
    if not m:
        # Fallback: "Date of expiry" variant
        m = re.search(r'Date\s*of\s*expiry\s*[:/]?\s*\n?\s*' + date_pattern, text, re.IGNORECASE)
    if m:
        fields['passport_expiry_date'] = m.group(1).strip()
        fields['passport_expiry_date_parsed'] = parse_date(m.group(1))

    # Field 16: Issued by (country)
    m = re.search(r'16\.\s*Issued\s*by\s*\(country\)\s*:?\s*\n?\s*([A-Z][a-zA-Z]+)', text, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        if val.lower() not in ('from', 'until', 'number', 'valid'):
            fields['passport_issued_by'] = val

    # Field 21: Occupation
    m = re.search(r'21\.\s*Current\s*occupation\s*:?\s*\n?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['occupation'] = clean_value(m.group(1))

    # Field 23: Purpose
    m = re.search(r'23\.\s*Purpose.*?journey\s*:(.*?)24\.', text, re.IGNORECASE | re.DOTALL)
    if m:
        sec = m.group(1)
        # Look for filled checkbox 'n' before purpose
        purposes_checked = [
            ('Tourism', r'n\s*Tourism'),
            ('Business', r'n\s*Business'),
            ('Visiting family or friends', r'n\s*Visiting'),
            ('Cultural', r'n\s*Cultural'),
            ('Sports', r'n\s*Sports'),
            ('Official visit', r'n\s*Official'),
            ('Medical', r'n\s*Medical'),
            ('Study', r'n\s*Study'),
            ('Airport transit', r'n\s*Airport'),
        ]
        for purpose_name, pattern in purposes_checked:
            if re.search(pattern, sec):
                fields['purpose'] = purpose_name
                break
        # Fallback
        if 'purpose' not in fields:
            for p in ['tourism', 'business', 'visiting', 'cultural', 'sports', 'official', 'medical', 'study']:
                if p in sec.lower():
                    fields['purpose'] = p.capitalize()
                    break

    # Field 25: Destination countries
    m = re.search(r'25\.\s*Member\s*State.*?destination.*?:\s*\n?\s*(.+?)(?:\n\s*\n|26\.)', text, re.IGNORECASE | re.DOTALL)
    if m:
        dest = clean_value(m.group(1))
        # Clean up "destination, if applicable) :" prefix
        dest = re.sub(r'destination,?\s*if\s*applicable\)?\s*:?\s*', '', dest, flags=re.IGNORECASE)
        if dest:
            fields['destination'] = dest

    # Travel dates - arrival
    m = re.search(r'(?:arrival|first\s*intended\s*stay).*?:\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})', text, re.IGNORECASE)
    if m:
        fields['travel_date_from'] = m.group(1).strip()
        fields['travel_date_from_parsed'] = parse_date(m.group(1))

    # Travel dates - departure
    m = re.search(r'departure.*?(?:first\s*intended\s*stay)?\s*:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})', text, re.IGNORECASE)
    if m:
        fields['travel_date_to'] = m.group(1).strip()
        fields['travel_date_to_parsed'] = parse_date(m.group(1))

    # Field 30: Accommodation
    m = re.search(r'30\..*?accommodation.*?:\s*\n?\s*(.+?)(?:\nAddress|\n\s*\n|31\.)', text, re.IGNORECASE | re.DOTALL)
    if m:
        fields['accommodation'] = clean_value(m.group(1))

    # Date of application
    m = re.search(r'Date\s*of\s*application\s*:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})', text, re.IGNORECASE)
    if m:
        fields['application_date'] = m.group(1).strip()
        fields['application_date_parsed'] = parse_date(m.group(1))

    # Application number
    m = re.search(r'Application\s*number\s*:?\s*([A-Z0-9]+)', text, re.IGNORECASE)
    if m:
        fields['application_number'] = m.group(1).strip()

    # Email
    m = re.search(r'[\w\.\-+]+@[\w\.\-]+\.\w+', text)
    if m:
        fields['email'] = m.group(0)

    # Phone
    m = re.search(r'Telephone\s*(?:no)?\s*:?\s*([\d\s\+\-]+)', text, re.IGNORECASE)
    if m:
        phone = re.sub(r'\s+', '', m.group(1).strip())
        if len(phone) >= 7:
            fields['phone'] = phone

    fields['_type'] = 'schengen_visa'
    return fields


# ─── Field Extraction: UK Visa ──────────────────────────────────────

def extract_uk_visa_fields(pages):
    """Extract fields from a UK visa application."""
    text = full_text(pages)
    fields = {}

    # Applicant name
    m = re.search(r'APPLICANT\s*NAME\s*:?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['full_name'] = m.group(1).strip()
        parts = fields['full_name'].split()
        if len(parts) >= 2:
            fields['first_name'] = ' '.join(parts[:-1])
            fields['surname'] = parts[-1]
        elif len(parts) == 1:
            fields['first_name'] = parts[0]

    # Also look for Given name / Family name format
    m_given = re.search(r'Given\s*name\(?s?\)?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    m_family = re.search(r'Family\s*name\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m_given and m_family:
        given = m_given.group(1).strip()
        family = m_family.group(1).strip()
        if given and family and given != family:
            fields['first_name'] = given
            fields['surname'] = family
            fields['full_name'] = f"{given} {family}"

    # GWF Number
    m = re.search(r'GWF\s*NUMBER\s*:?\s*(GWF\d+)', text, re.IGNORECASE)
    if m:
        fields['gwf_number'] = m.group(1).strip()

    # Application number
    m = re.search(r'UNIQUE\s*APPLICATION\s*NUMBER\s*:?\s*([\d\-/]+)', text, re.IGNORECASE)
    if m:
        fields['application_number'] = m.group(1).strip()

    # Passport number
    m = re.search(r'PASSPORT\s*NUMBER\s*:?\s*([A-Z0-9]+)', text, re.IGNORECASE)
    if not m:
        m = re.search(r'Passport\s*number\s*(?:or\s*travel\s*document)?.*?(?:number)?\s*([A-Z0-9]{5,})', text, re.IGNORECASE)
    if m:
        fields['passport_number'] = m.group(1).strip().upper()

    # Date of birth
    m = re.search(r'DATE\s*OF\s*BIRTH\s*:?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if not m:
        m = re.search(r'Date\s*of\s*birth\s*(\d{1,2}\s+\w+\s+\d{4})', text, re.IGNORECASE)
    if m:
        fields['date_of_birth'] = m.group(1).strip()
        fields['date_of_birth_parsed'] = parse_date(m.group(1))

    # Gender
    m = re.search(r'GENDER\s*:?\s*(\w+)', text, re.IGNORECASE)
    if not m:
        m = re.search(r'(?:sex|gender).*?(?:passport|travel\s*document)\??\s*(\w+)', text, re.IGNORECASE)
    if m:
        fields['sex'] = m.group(1).strip().capitalize()

    # Nationality
    m = re.search(r'COUNTRY\s*OF\s*NATIONALITY\s*:?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if not m:
        m = re.search(r'Country\s*of\s*nationality\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['nationality'] = m.group(1).strip()

    # Travel dates - extract just the date portion
    m = re.search(r'(?:Date\s*you\s*plan\s*to\s*arrive|arrive\s*in\s*the\s*UK)\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        date_text = m.group(1).strip()
        parsed = parse_date(date_text)
        if parsed:
            fields['travel_date_from'] = format_date(parsed)
            fields['travel_date_from_parsed'] = parsed
        else:
            fields['travel_date_from'] = date_text

    m = re.search(r'(?:Date\s*you\s*plan\s*to\s*leave|leave\s*the\s*UK)\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        date_text = m.group(1).strip()
        parsed = parse_date(date_text)
        if parsed:
            fields['travel_date_to'] = format_date(parsed)
            fields['travel_date_to_parsed'] = parsed
        else:
            fields['travel_date_to'] = date_text

    # Purpose - extract just the purpose value
    m = re.search(r'main\s*reason\s*for\s*your\s*visit.*?(?:UK\??\s*)(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['purpose'] = m.group(1).strip()
    else:
        m = re.search(r'(?:purpose).*?\s+(.+?)(?:\n)', text, re.IGNORECASE)
        if m:
            fields['purpose'] = m.group(1).strip()

    # Visa type
    m = re.search(r'TYPE\s*OF\s*VISA\s*/?\s*APPLICATION\s*:?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['visa_type'] = m.group(1).strip()

    # Relationship status
    m = re.search(r'(?:relationship|marital)\s*status\??\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['civil_status'] = m.group(1).strip()

    # Passport issue/expiry (= Date of Issue / Valid Until / Expiry Date)
    uk_date_pat = r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})'
    m = re.search(r'(?:Issue\s*date|Date\s*of\s*issue)\s*[:/]?\s*' + uk_date_pat, text, re.IGNORECASE)
    if m:
        fields['passport_issue_date'] = m.group(1).strip()
        fields['passport_issue_date_parsed'] = parse_date(m.group(1))

    m = re.search(r'(?:Expiry\s*date|Date\s*of\s*expiry|Valid\s*until)\s*[:/]?\s*' + uk_date_pat, text, re.IGNORECASE)
    if m:
        fields['passport_expiry_date'] = m.group(1).strip()
        fields['passport_expiry_date_parsed'] = parse_date(m.group(1))

    # Place of birth
    m = re.search(r'Place\s*of\s*birth\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['place_of_birth'] = m.group(1).strip()

    # Country of birth
    m = re.search(r'Country\s*of\s*birth\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['country_of_birth'] = m.group(1).strip()

    # Employer
    m = re.search(r"Employer'?s?\s*name\s*(.+?)(?:\n)", text, re.IGNORECASE)
    if m:
        fields['employer'] = m.group(1).strip()

    # Email
    m = re.search(r'[\w\.\-+]+@[\w\.\-]+\.\w+', text)
    if m:
        fields['email'] = m.group(0)

    # Phone
    m = re.search(r'(?:telephone|phone)\s*number\s*([\d\s\+\-]+)', text, re.IGNORECASE)
    if m:
        phone = re.sub(r'\s+', '', m.group(1).strip())
        if len(phone) >= 7:
            fields['phone'] = phone

    # Organisation being visited
    m = re.search(r'Organisation\s*name\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['host_organisation'] = m.group(1).strip()

    fields['_type'] = 'uk_visa'
    return fields


# ─── Field Extraction: Supporting Documents ─────────────────────────

def extract_passport_fields(pages):
    """Extract fields from a passport copy."""
    text = full_text(pages)
    fields = {}

    # Try to extract MRZ line data
    # Common passport fields
    m = re.search(r'(?:Surname|Family\s*Name)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['surname'] = m.group(1).strip()

    m = re.search(r'(?:Given\s*Names?|First\s*Name)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['first_name'] = m.group(1).strip()

    m = re.search(r'(?:Passport\s*No|Number)\s*[:/]?\s*([A-Z0-9]+)', text, re.IGNORECASE)
    if m:
        fields['passport_number'] = m.group(1).strip().upper()

    m = re.search(r'(?:Date\s*of\s*Birth|DOB)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['date_of_birth'] = m.group(1).strip()
        fields['date_of_birth_parsed'] = parse_date(m.group(1))

    # Passport Issue Date — "Date of Issue", "Date of Issuance", "Issue date"
    m = re.search(r'(?:Date\s*of\s*(?:Issue|Issuance)|Issue\s*date)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['passport_issue_date'] = m.group(1).strip()
        fields['passport_issue_date_parsed'] = parse_date(m.group(1))

    # Passport Expiry Date — "Date of Expiry", "Valid Until", "Expiry date", "Expiry"
    m = re.search(r'(?:Date\s*of\s*Expiry|Valid\s*Until|Expiry\s*date|Expiry)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['passport_expiry_date'] = m.group(1).strip()
        fields['passport_expiry_date_parsed'] = parse_date(m.group(1))

    m = re.search(r'(?:Place\s*of\s*Birth)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['place_of_birth'] = m.group(1).strip()

    m = re.search(r'(?:Sex|Gender)\s*[:/]?\s*([MF](?:ale|emale)?)', text, re.IGNORECASE)
    if m:
        sex = m.group(1).strip().upper()
        fields['sex'] = 'Male' if sex.startswith('M') else 'Female'

    # Build full_name from surname + first_name (passport format: SURNAME GIVEN_NAMES)
    if 'surname' in fields and 'first_name' in fields:
        fields['full_name'] = f"{fields['surname']} {fields['first_name']}".strip()
    elif 'surname' in fields:
        fields['full_name'] = fields['surname']
    elif 'first_name' in fields:
        fields['full_name'] = fields['first_name']

    fields['_type'] = 'passport_copy'
    return fields


MONTH_ABBR_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}


def parse_ticket_date(text, year_hint=None):
    """Parse flight ticket date formats like '06APR', '06 APR', '06APR2026',
    'Monday 06 April 2026', or standard DD/MM/YYYY.
    Uses year_hint (from document issue date or current year) when year is missing."""
    if not text:
        return None
    text = text.strip()

    # Try DDMON or DDMONYYYY (e.g. 06APR, 28APR, 06APR2026)
    m = re.match(r'(\d{1,2})\s*([A-Z]{3})(?:\s*(\d{4}))?', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        mon = MONTH_ABBR_MAP.get(m.group(2).upper())
        year = int(m.group(3)) if m.group(3) else (year_hint or datetime.now().year)
        if mon:
            try:
                return datetime(year, mon, day)
            except ValueError:
                pass

    # Try "Monday 06 April 2026" or "06 April 2026"
    m = re.search(r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', text, re.IGNORECASE)
    if m:
        return parse_date(m.group(0))

    # Fallback to standard parse_date
    return parse_date(text)


def extract_flight_fields(pages):
    """Extract fields from a flight ticket / itinerary.

    Handles common travel agency formats:
    - 'Traveler Mr Harish Govindhaiah' line for passenger name
    - DDMON format dates (06APR) in flight summary tables
    - 'Monday 06 April 2026' in detailed sections
    - 'Departure DDMonthHH:MM' in detail blocks
    - Separates Document Issue Date from actual flight dates
    """
    text = full_text(pages)
    fields = {}

    # ── Passenger / Traveler name ──
    # Look for "Traveler <name>" or "Traveller <name>" (common in agency-issued tickets)
    m = re.search(r'Travell?er\s+(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?)?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        # Remove trailing "Agency..." or similar if it got picked up
        name = re.split(r'\s{3,}|\bAgency\b', name)[0].strip()
        if name:
            fields['passenger_name'] = name

    # Fallback: "Passenger Name: ..." or "Passenger: ..."
    if 'passenger_name' not in fields:
        m = re.search(r'Passenger\s*(?:Name)?\s*[:/]\s*(.+?)(?:\n)', text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if name and len(name) > 3:
                fields['passenger_name'] = name

    # ── PNR / Booking Reference ──
    m = re.search(r'(?:PNR|Booking\s*[Rr]ef(?:erence)?|Confirmation)\s*[:/]?\s*([A-Z0-9]{5,8})', text, re.IGNORECASE)
    if m:
        fields['pnr'] = m.group(1).strip()

    # ── Document Issue Date (NOT a flight date) ──
    doc_issue_date = None
    m = re.search(r'(?:Document\s*Issue\s*Date|Issue\s*Date)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        doc_issue_date = parse_date(m.group(1))
        fields['ticket_issue_date'] = m.group(1).strip()

    # Determine year hint from document issue date or current year
    year_hint = doc_issue_date.year if doc_issue_date else datetime.now().year

    # ── Flight dates — Priority 1: Explicit "Departure" lines with full dates ──
    # Matches "Departure 06April01:25" or "Departure 06 April 2026 01:25"
    departure_dates = []
    for m in re.finditer(r'Departure\s+(\d{1,2})\s*([A-Za-z]+?)(\d{2}:\d{2})', text):
        day = m.group(1)
        month_str = m.group(2).strip()
        date_str = f'{day} {month_str} {year_hint}'
        d = parse_ticket_date(date_str, year_hint)
        if d:
            departure_dates.append(d)

    # ── Flight dates — Priority 2: "Day DD Month YYYY" lines (e.g., "Monday 06 April 2026") ──
    leg_dates = []
    for m in re.finditer(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2}\s+\w+\s+\d{4})', text, re.IGNORECASE):
        d = parse_date(m.group(1))
        if d:
            leg_dates.append(d)

    # ── Flight dates — Priority 3: DDMON rows in summary table (e.g., "06APR 0125 BENGALURU") ──
    summary_dates = []
    for m in re.finditer(r'^(\d{2}[A-Z]{3})\s+\d{4}\s+', text, re.MULTILINE):
        d = parse_ticket_date(m.group(1), year_hint)
        if d:
            summary_dates.append(d)

    # Pick the best source of flight dates (prefer explicit, then day-lines, then summary)
    flight_dates = []
    if departure_dates:
        flight_dates = sorted(set(departure_dates))
    elif leg_dates:
        flight_dates = sorted(set(leg_dates))
    elif summary_dates:
        flight_dates = sorted(set(summary_dates))
    else:
        # Last resort: collect all dates EXCEPT the document issue date
        for pattern, fmt in DATE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                d = parse_date(match.group(0))
                if d and d.year >= 2024:
                    # Skip the document issue date
                    if doc_issue_date and d.date() == doc_issue_date.date():
                        continue
                    flight_dates.append(d)
        flight_dates = sorted(set(flight_dates))

    if flight_dates:
        fields['departure_date'] = format_date(flight_dates[0])
        fields['departure_date_parsed'] = flight_dates[0]
        if len(flight_dates) > 1:
            fields['return_date'] = format_date(flight_dates[-1])
            fields['return_date_parsed'] = flight_dates[-1]

    # ── Route from summary or detail ──
    # Try summary table format: DDMON TIME CITY CODE CITY CODE
    m = re.search(r'\d{2}[A-Z]{3}\s+\d{4}\s+(\w[\w\s]+?)\s+[A-Z]{3}\s+(\w[\w\s]+?)\s+[A-Z]{3}', text)
    if m:
        fields['origin'] = m.group(1).strip()
        fields['destination'] = m.group(2).strip()
    else:
        m = re.search(r'(?:From|Departure|Origin)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
        if m:
            fields['origin'] = m.group(1).strip()
        m = re.search(r'(?:To|Arrival|Destination)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
        if m:
            fields['destination'] = m.group(1).strip()

    fields['_type'] = 'flight_ticket'
    return fields


def extract_invitation_fields(pages):
    """Extract fields from a business invitation letter.

    Required fields per business visa process:
    - Invitee (traveler) name
    - Invitee passport number
    - Travel/visit dates
    - Signatory name, designation, and contact number
    - Inviting company name and address
    """
    text = full_text(pages)
    fields = {}

    # ── Invitee (traveler) name ──
    # Try common invitation patterns
    for pattern in [
        r'(?:hereby\s+invite|pleased\s+to\s+invite|inviting|invite)\s+(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*([A-Z][A-Za-z\s\.]+?)(?:\s*,|\s+to\s+|\s+from\s+|\s+for\s+|\s*\(|\n)',
        r'(?:Dear|Attention)\s*:?\s*(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*([A-Z][A-Za-z\s\.]+?)(?:\s*,|\n)',
        r'(?:This\s+(?:letter|invitation)\s+is\s+(?:for|to\s+confirm))\s+(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*([A-Z][A-Za-z\s\.]+?)(?:\s*,|\s+to\s+|\n)',
        r'(?:guest|visitor|invitee)\s*:?\s*(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*([A-Z][A-Za-z\s\.]+?)(?:\n)',
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # Filter out common false positives
            if len(name) > 3 and name.lower() not in ('the', 'our', 'this', 'that', 'your'):
                fields['invitee_name'] = name
                break

    # ── Invitee passport number ──
    m = re.search(r'(?:passport\s*(?:no\.?|number)\s*[:/]?\s*)([A-Z0-9]{5,})', text, re.IGNORECASE)
    if m:
        fields['passport_number'] = m.group(1).strip().upper()

    # ── Inviting company name ──
    for pattern in [
        r'(?:on\s+behalf\s+of|from)\s+([A-Z][A-Za-z\s&\.,]+(?:Ltd|Limited|Inc|Corp|GmbH|SA|Pvt|Private|LLC|LLP|PLC|Group|Bank|Company)[\w\s\.]*)',
        r'(?:Company|Organisation|Organization|Firm)\s*[:/]?\s*([A-Z][A-Za-z\s&\.,]+?)(?:\n)',
        r'(?:we\s+at|representing)\s+([A-Z][A-Za-z\s&\.,]+?)(?:\s*,|\s+would|\s+hereby|\n)',
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            fields['company'] = m.group(1).strip().rstrip(',.')
            break

    # ── Company address ──
    m = re.search(r'(?:(?:our|company|office|business)\s+address|(?:located|situated)\s+at)\s*[:/]?\s*(.+?)(?:\n\n|\n[A-Z])', text, re.IGNORECASE | re.DOTALL)
    if m:
        fields['company_address'] = m.group(1).strip()

    # ── Visit/travel dates ──
    dates_found = []
    for pattern, fmt in DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            d = parse_date(match.group(0))
            if d and d.year >= 2024:
                dates_found.append(d)
    if dates_found:
        dates_found.sort()
        fields['visit_from'] = format_date(dates_found[0])
        fields['visit_from_parsed'] = dates_found[0]
        if len(dates_found) > 1:
            fields['visit_to'] = format_date(dates_found[-1])
            fields['visit_to_parsed'] = dates_found[-1]

    # ── Signatory details ──
    # Look for signatory name (often near "Yours sincerely", "Regards", "Authorized Signatory")
    signatory_section = re.search(
        r'(?:sincerely|regards|faithfully|authorized\s*signatory|authorised\s*signatory|signed\s*by)\s*,?\s*\n(.+)',
        text, re.IGNORECASE | re.DOTALL
    )
    if signatory_section:
        sig_text = signatory_section.group(1).strip()
        sig_lines = [l.strip() for l in sig_text.split('\n') if l.strip()]

        # First non-empty line after "Regards" is usually the name
        if sig_lines:
            fields['signatory_name'] = sig_lines[0]

        # Second line is often the designation/title
        if len(sig_lines) >= 2:
            fields['signatory_designation'] = sig_lines[1]

        # Look for phone/contact in signatory section
        for line in sig_lines:
            phone_m = re.search(r'(?:Tel|Phone|Mobile|Contact|Ph)\s*[:/.]?\s*([\+\d\s\-\(\)]{7,})', line, re.IGNORECASE)
            if phone_m:
                fields['signatory_contact'] = re.sub(r'\s+', '', phone_m.group(1))
                break

    # Also try to find contact number anywhere near signatory patterns
    if 'signatory_contact' not in fields:
        m = re.search(r'(?:contact|reach|call)\s*(?:me|us)?\s*(?:at|on)?\s*[:/]?\s*([\+\d\s\-\(\)]{7,})', text, re.IGNORECASE)
        if m:
            fields['signatory_contact'] = re.sub(r'\s+', '', m.group(1))

    # ── Signatory designation (also try outside signatory section) ──
    if 'signatory_designation' not in fields:
        for pattern in [
            r'(?:Designation|Title|Position)\s*[:/]?\s*(.+?)(?:\n)',
            r'(?:Director|Manager|CEO|CFO|CTO|VP|President|Head|Partner|Secretary|HR\s*Manager|General\s*Manager)[,\s]*(?:of\s+)?(.+?)(?:\n)',
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                fields['signatory_designation'] = m.group(0).strip()
                break

    # ── Purpose of visit ──
    m = re.search(r'(?:purpose\s+of\s+(?:visit|travel|trip)|visiting\s+for|reason\s+for\s+visit)\s*[:/]?\s*(.+?)(?:\n|\.)', text, re.IGNORECASE)
    if m:
        fields['purpose'] = m.group(1).strip()

    # ── Email from letter ──
    m = re.search(r'[\w\.\-+]+@[\w\.\-]+\.\w+', text)
    if m:
        fields['email'] = m.group(0)

    fields['_type'] = 'invitation_letter'
    return fields


# ─── Field Extraction: Covering Letter ──────────────────────────────

def extract_covering_letter_fields(pages):
    """Extract fields from a covering letter.

    A covering letter is common to both business and tourist visas.
    Required fields:
    - Traveler's name
    - Traveler's passport number
    - Travel dates
    - Purpose of travel
    - Who is bearing the expenses (company for business, self/sponsor for leisure)
    - If sponsored by someone else, the sponsor's details
    """
    text = full_text(pages)
    fields = {}

    # ── Traveler name ──
    for pattern in [
        r'(?:I|applicant)\s*,?\s*(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*([A-Z][A-Za-z\s\.]+?)\s*,?\s*(?:holder\s+of|bearing|holding|with)\s+(?:passport|Indian\s+passport)',
        r'(?:This\s+is\s+to\s+(?:certify|confirm).*?)(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*([A-Z][A-Za-z\s\.]+?)\s*(?:,|\s+is\s+)',
        r'(?:undersigned|applicant)\s*[,:]?\s*(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*([A-Z][A-Za-z\s\.]+?)(?:\s*,|\s+holder|\n)',
        r'(?:name)\s*[:/]\s*(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*([A-Z][A-Za-z\s\.]+?)(?:\n)',
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if len(name) > 3 and name.lower() not in ('the', 'our', 'this', 'that'):
                fields['traveler_name'] = name
                break

    # ── Passport number ──
    m = re.search(r'(?:passport\s*(?:no\.?|number)\s*[:/]?\s*)([A-Z0-9]{5,})', text, re.IGNORECASE)
    if m:
        fields['passport_number'] = m.group(1).strip().upper()

    # ── Travel dates ──
    dates_found = []
    for pattern, fmt in DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            d = parse_date(match.group(0))
            if d and d.year >= 2024:
                dates_found.append(d)
    if dates_found:
        dates_found.sort()
        fields['travel_from'] = format_date(dates_found[0])
        fields['travel_from_parsed'] = dates_found[0]
        if len(dates_found) > 1:
            fields['travel_to'] = format_date(dates_found[-1])
            fields['travel_to_parsed'] = dates_found[-1]

    # ── Purpose of travel ──
    for pattern in [
        r'(?:purpose\s+of\s+(?:my|the|this)?\s*(?:visit|travel|trip|journey))\s*[:/]?\s*(.+?)(?:\n|\.)',
        r'(?:traveling|travelling|visiting)\s+(?:for|to)\s+(.+?)(?:\n|\.)',
        r'(?:reason\s+for\s+(?:visit|travel))\s*[:/]?\s*(.+?)(?:\n|\.)',
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            fields['purpose'] = m.group(1).strip()
            break

    # ── Expense bearer ──
    expense_text_lower = text.lower()
    if any(kw in expense_text_lower for kw in ['company will bear', 'employer will bear', 'borne by the company',
                                                 'expenses.*company', 'funded by.*company', 'sponsored by.*employer',
                                                 'company.*bear.*expenses', 'employer.*sponsor', 'corporate.*sponsor']):
        fields['expense_bearer'] = 'Company/Employer'
    elif any(kw in expense_text_lower for kw in ['i will bear', 'self-funded', 'self funded', 'own expense',
                                                   'my own', 'borne by me', 'bear all expenses myself',
                                                   'personally bear', 'at my own cost']):
        fields['expense_bearer'] = 'Self'
    elif any(kw in expense_text_lower for kw in ['sponsored by', 'sponsor will', 'borne by my',
                                                   'expenses will be covered by', 'funded by']):
        fields['expense_bearer'] = 'Sponsor/Third Party'

    # ── Sponsor details (if sponsored by third party) ──
    if fields.get('expense_bearer') == 'Sponsor/Third Party':
        m = re.search(r'(?:sponsor|funded\s+by|expenses\s+(?:covered|borne)\s+by)\s*[:/]?\s*(?:Mr\.?|Ms\.?|Mrs\.?)?\s*([A-Z][A-Za-z\s\.]+?)(?:\s*,|\s*\(|\n)', text, re.IGNORECASE)
        if m:
            fields['sponsor_name'] = m.group(1).strip()

        m = re.search(r'(?:sponsor.*?(?:passport|relation|address|contact))\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
        if m:
            fields['sponsor_details'] = m.group(1).strip()

    # ── Company details (if company is bearing expenses) ──
    if fields.get('expense_bearer') == 'Company/Employer':
        m = re.search(r'(?:employer|company)\s*[:/]?\s*([A-Z][A-Za-z\s&\.,]+(?:Ltd|Limited|Inc|Corp|Pvt|Private|LLC|LLP)[\w\s\.]*)', text, re.IGNORECASE)
        if m:
            fields['company_name'] = m.group(1).strip()

    # ── Destination country ──
    m = re.search(r'(?:traveling|travelling|visit|trip)\s+to\s+([A-Z][a-zA-Z\s]+?)(?:\s+from|\s+for|\s+during|\s+between|\n|\.)', text, re.IGNORECASE)
    if m:
        fields['destination'] = m.group(1).strip()

    # ── Email ──
    m = re.search(r'[\w\.\-+]+@[\w\.\-]+\.\w+', text)
    if m:
        fields['email'] = m.group(0)

    # ── Phone ──
    m = re.search(r'(?:contact|phone|mobile|tel)\s*[:/]?\s*([\+\d\s\-\(\)]{7,})', text, re.IGNORECASE)
    if m:
        fields['phone'] = re.sub(r'\s+', '', m.group(1))

    fields['_type'] = 'covering_letter'
    return fields


def extract_france_receipt_fields(pages):
    """Extract fields from a France-Visas registration receipt."""
    text = full_text(pages)
    fields = {}

    m = re.search(r'Reference\s*of\s*the\s*application\s*:?\s*([A-Z0-9]+)', text, re.IGNORECASE)
    if m:
        fields['application_number'] = m.group(1).strip()

    m = re.search(r'Last\s*name/?s?\s*:?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['surname'] = m.group(1).strip()

    m = re.search(r'First\s*name/?s?\s*:?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['first_name'] = m.group(1).strip()

    if 'surname' in fields and 'first_name' in fields:
        fields['full_name'] = f"{fields['surname']} {fields['first_name']}"

    m = re.search(r'Birth\s*date.*?:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})', text, re.IGNORECASE)
    if m:
        fields['date_of_birth'] = m.group(1).strip()
        fields['date_of_birth_parsed'] = parse_date(m.group(1))

    fields['_type'] = 'france_receipt'
    return fields


def extract_generic_fields(pages):
    """Try to extract any identifiable fields from an unknown document."""
    text = full_text(pages)
    fields = {}

    # Try to find common fields
    m = re.search(r'[\w\.\-+]+@[\w\.\-]+\.\w+', text)
    if m:
        fields['email'] = m.group(0)

    # Look for passport numbers
    m = re.search(r'(?:Passport|Travel\s*Document)\s*(?:No\.?|Number)?\s*[:/]?\s*([A-Z]\d{7,})', text, re.IGNORECASE)
    if m:
        fields['passport_number'] = m.group(1).strip()

    # Look for names
    m = re.search(r'(?:Name|Applicant)\s*[:/]?\s*(.+?)(?:\n)', text, re.IGNORECASE)
    if m:
        fields['name_found'] = m.group(1).strip()

    fields['_type'] = 'unknown'
    return fields


# ─── Master Extractor ───────────────────────────────────────────────

def extract_fields(filepath):
    """Extract fields from any supported document type."""
    pages = extract_text_from_pdf(filepath)
    doc_type = detect_document_type(pages)

    extractors = {
        'schengen_visa': extract_schengen_fields,
        'uk_visa': extract_uk_visa_fields,
        'france_receipt': extract_france_receipt_fields,
        'passport_copy': extract_passport_fields,
        'flight_ticket': extract_flight_fields,
        'invitation_letter': extract_invitation_fields,
        'covering_letter': extract_covering_letter_fields,
    }

    extractor = extractors.get(doc_type, extract_generic_fields)
    fields = extractor(pages)
    fields['_doc_type'] = doc_type
    fields['_doc_type_label'] = DOCUMENT_TYPE_LABELS.get(doc_type, 'Unknown')
    fields['_raw_text'] = text_preview(full_text(pages))

    return fields


def text_preview(text, max_chars=500):
    """Return a short preview of the text."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."
