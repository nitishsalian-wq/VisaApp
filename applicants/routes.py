"""
Applicant management routes for VisaDesk
"""
import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import desc
from extensions import db
from models import Applicant, Document, QCReport
from qc.extractor import detect_document_type, extract_text_from_pdf, extract_passport_fields, extract_fields

applicants_bp = Blueprint('applicants', __name__, url_prefix='/applicants')


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def get_applicant_directory(applicant_id):
    """Get the upload directory for an applicant"""
    return os.path.join(current_app.config['UPLOAD_FOLDER'], str(applicant_id))


@applicants_bp.route('/', methods=['GET'])
@login_required
def list_applicants():
    """List all applicants"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()

    query = Applicant.query

    # Filter by owner or show all for admin
    if not current_user.is_admin():
        query = query.filter_by(created_by_id=current_user.id)

    # Search by name or passport
    if search:
        query = query.filter(
            db.or_(
                Applicant.full_name.ilike(f'%{search}%'),
                Applicant.passport_number.ilike(f'%{search}%')
            )
        )

    # Filter by status
    if status_filter:
        query = query.filter_by(status=status_filter)

    # Sort by updated_at descending
    query = query.order_by(desc(Applicant.updated_at))

    pagination = query.paginate(page=page, per_page=20)
    applicants = pagination.items

    return render_template(
        'applicants/list.html',
        applicants=applicants,
        pagination=pagination,
        search=search,
        status_filter=status_filter
    )


def ocr_passport_text(file_path):
    """Extract text from a scanned passport using OCR (Tesseract).
    Handles both image files and scanned PDFs."""
    import re
    text = ''

    try:
        import pytesseract
        from PIL import Image

        if file_path.lower().endswith('.pdf'):
            # Convert PDF pages to images, then OCR
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(file_path, dpi=200)
                for img in images:
                    text += pytesseract.image_to_string(img) + '\n'
            except ImportError:
                pass
        else:
            # Direct image OCR
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)
    except ImportError:
        pass

    return text


def parse_passport_ocr(text):
    """Parse passport fields from OCR text using multiple strategies.
    Handles: passport bio pages (MRZ), invitation letters with tables,
    and any document containing passport details.

    Key insight for Indian passports: OCR reads Hindi labels as garbage,
    then the English label/value. The actual value is often on the NEXT
    line after the label, not the same line. So we use a "next line"
    approach for labeled fields."""
    import re
    from datetime import date
    from qc.extractor import parse_date
    fields = {}
    mrz_fields = {}

    if not text or len(text.strip()) < 10:
        return fields

    lines = text.split('\n')

    # ── Helper: get next meaningful text value after a label line ──
    def get_next_value(lines, pattern, flags=re.IGNORECASE):
        """Find a line matching pattern, return the next meaningful value.
        Checks same line remainder first, then scans next 4 lines.
        Requires at least 3 alphanumeric characters to filter OCR garbage."""
        for i, line in enumerate(lines):
            m = re.search(pattern, line, flags)
            if m:
                # Check rest of same line after the match
                after = line[m.end():].strip()
                after = re.sub(r'^[:/)\]}\s,;]+', '', after).strip()
                alpha_count = sum(1 for c in after if c.isalnum())
                if alpha_count >= 3:
                    return after

                # Scan next few lines for a meaningful value
                for j in range(i + 1, min(i + 4, len(lines))):
                    val = lines[j].strip()
                    if not val:
                        continue
                    # Strip non-ASCII (Hindi/Devanagari) and check remainder
                    val_ascii = re.sub(r'[^\x20-\x7E]', '', val).strip()
                    val_clean = re.sub(r'^[:/)\]}\s,;]+', '', val_ascii).strip()
                    alpha_count = sum(1 for c in val_clean if c.isalnum())
                    if alpha_count >= 3:
                        return val_clean
        return None

    # ── Helper: find a date (DD/MM/YYYY) near a label ──
    def find_date_near_label(lines, pattern):
        """Search for a date pattern on or near a line matching the label.
        Returns (date_string, sex_char_or_None)."""
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                # Check same line and next 4 lines for a date
                for j in range(i, min(i + 5, len(lines))):
                    dm = re.search(r'(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})', lines[j])
                    if dm:
                        # Also check for M/F sex marker on the same line
                        sm = re.search(r'\b([MF])\s*$', lines[j].strip())
                        sex = sm.group(1) if sm else None
                        return dm.group(1), sex
        return None, None

    # ── Strategy 1: MRZ (Machine Readable Zone) ──
    # Only trust MRZ if it looks clean (OCR often garbles the tiny MRZ text)
    mrz_lines_raw = re.findall(r'[A-Z0-9<]{30,}', text)
    if len(mrz_lines_raw) >= 2:
        line1 = mrz_lines_raw[0]
        line2 = mrz_lines_raw[1]

        if line1.startswith('P') and '<<' in line1:
            parts = line1[5:].split('<<', 1)
            if len(parts) == 2:
                surname = parts[0].replace('<', ' ').strip()
                given = parts[1].replace('<', ' ').strip()
                if surname and re.match(r'^[A-Z ]+$', surname):
                    mrz_fields['surname'] = surname
                if given and re.match(r'^[A-Z ]+$', given):
                    mrz_fields['first_name'] = given

        if len(line2) >= 28:
            pp_num = line2[0:9].replace('<', '').strip()
            if re.match(r'^[A-Z0-9]{6,9}$', pp_num):
                mrz_fields['passport_number'] = pp_num

            dob_raw = line2[13:19]
            if dob_raw.isdigit():
                yy, mm, dd = int(dob_raw[0:2]), int(dob_raw[2:4]), int(dob_raw[4:6])
                year = 1900 + yy if yy > 30 else 2000 + yy
                try:
                    mrz_fields['date_of_birth_parsed'] = date(year, mm, dd)
                except ValueError:
                    pass

            sex_char = line2[20:21]
            if sex_char in ('M', 'F'):
                mrz_fields['sex'] = 'Male' if sex_char == 'M' else 'Female'

            exp_raw = line2[21:27]
            if exp_raw.isdigit():
                yy, mm, dd = int(exp_raw[0:2]), int(exp_raw[2:4]), int(exp_raw[4:6])
                try:
                    mrz_fields['passport_expiry_date_parsed'] = date(2000 + yy, mm, dd)
                except ValueError:
                    pass

            if len(line2) >= 12:
                nat_code = line2[10:13].replace('<', '')
                country_map = {
                    'IND': 'Indian', 'USA': 'American', 'GBR': 'British',
                    'CAN': 'Canadian', 'AUS': 'Australian', 'DEU': 'German',
                    'FRA': 'French', 'JPN': 'Japanese', 'CHN': 'Chinese',
                    'PAK': 'Pakistani', 'BGD': 'Bangladeshi', 'LKA': 'Sri Lankan',
                    'NPL': 'Nepalese', 'SGP': 'Singaporean', 'ARE': 'Emirati',
                }
                if nat_code in country_map:
                    mrz_fields['nationality'] = country_map[nat_code]

    # ── Strategy 2: Labeled fields with next-line value lookup ──
    # Primary strategy for Indian passports where OCR reads:
    #   "Hindi_garbage / Given Names)\n\nHARISH GOVINDHAIAH\n"
    label_fields = {}

    # Surname — look for explicit "Surname" label FIRST
    # In Indian passports, surname field can be blank. Only set surname
    # if the "Surname" label exists AND has a real value after it.
    # We look for "Surname" but NOT when it's part of "/ Surname" on a
    # line that also says "Given Names" (which is the Hindi+English label line)
    surname_val = None
    for i, line in enumerate(lines):
        if re.search(r'\bSurname\b', line, re.IGNORECASE):
            # Skip if this line also contains "Given Name" — it's the label line
            if re.search(r'Given\s*Name', line, re.IGNORECASE):
                continue
            surname_val = get_next_value([line] + lines[i+1:i+4], r'\bSurname\b')
            break
    has_explicit_surname = False
    if surname_val:
        surname_clean = re.sub(r'[^A-Za-z\s]', '', surname_val).strip()
        # Reject if it contains other field labels (means no surname value exists)
        if surname_clean and len(surname_clean) >= 2 and re.match(r'^[A-Za-z\s]+$', surname_clean):
            lower = surname_clean.lower()
            if not any(kw in lower for kw in ['given', 'name', 'date', 'birth', 'sex', 'place']):
                label_fields['surname'] = surname_clean.strip().upper()
                has_explicit_surname = True

    # Given Names — the main name field in Indian passports
    val = get_next_value(lines, r'Given\s*Names?')
    if val:
        name_clean = re.sub(r'[^A-Za-z\s]', '', val).strip()
        if name_clean and len(name_clean) >= 3:
            # Put the FULL value from "Given Names" into first_name
            # Do NOT split it — the passport shows exactly what goes here
            label_fields['first_name'] = name_clean

    # Date of Birth — scan nearby lines for a date pattern
    dob_str, sex_from_dob = find_date_near_label(lines, r'Date\s*of\s*Birth|DOB')
    if dob_str:
        label_fields['date_of_birth_parsed'] = parse_date(dob_str)
    if sex_from_dob:
        label_fields['sex'] = 'Male' if sex_from_dob == 'M' else 'Female'

    # Sex (standalone, if not found on DOB line)
    if not label_fields.get('sex'):
        val = get_next_value(lines, r'\bSex\b')
        if val:
            sm = re.search(r'\b([MF])\b', val)
            if sm:
                label_fields['sex'] = 'Male' if sm.group(1) == 'M' else 'Female'

    # Place of Birth
    val = get_next_value(lines, r'Place\s*of\s*Birth')
    if val:
        val_clean = re.sub(r'[^A-Za-z,\s]', '', val).strip()
        if val_clean and len(val_clean) >= 3:
            label_fields['place_of_birth'] = val_clean

    # Place of Issue — OCR may garble "Issue" as "tssue", "lssue", etc.
    val = get_next_value(lines, r'Place\s*of\s*[A-Za-z]*ss?ue')
    if val:
        val_clean = re.sub(r'[^A-Za-z,\s]', '', val).strip()
        if val_clean and len(val_clean) >= 3:
            label_fields['place_of_issue'] = val_clean

    # Date of Issue — scan nearby lines for date
    issue_str, _ = find_date_near_label(lines, r'Date\s*of\s*[Ii]ss')
    if issue_str:
        label_fields['passport_issue_date_parsed'] = parse_date(issue_str)

    # Date of Expiry — scan nearby lines for date
    expiry_str, _ = find_date_near_label(lines, r'Date\s*of\s*Expiry|Expiry')
    if expiry_str:
        label_fields['passport_expiry_date_parsed'] = parse_date(expiry_str)

    # Passport number from labeled field
    val = get_next_value(lines, r'Passport\s*No|Passport\s*Number')
    if val:
        pm = re.search(r'([A-Z]{1,2}\d{6,7})', val)
        if pm:
            label_fields['passport_number'] = pm.group(1).upper()

    # Passport number from anywhere in text (Indian: 1-2 letters + 7 digits)
    if not label_fields.get('passport_number'):
        m = re.search(r'\b([A-Z]{1,2}\d{7})\b', text)
        if m:
            label_fields['passport_number'] = m.group(1).upper()

    # Passport number fallback: OCR may misread first letter as digit
    # e.g. "2A561391" instead of "ZA561391". Find 8-9 char alphanumeric tokens.
    if not label_fields.get('passport_number'):
        for line in lines:
            m = re.search(r'\b([A-Z0-9]{8,9})\b', line)
            if m:
                candidate = m.group(1)
                digit_count = sum(1 for c in candidate if c.isdigit())
                if 5 <= digit_count <= 8:
                    label_fields['passport_number'] = candidate
                    break

    # ── Merge: prefer label_fields (readable text) over MRZ (often garbled) ──
    for key in set(list(label_fields.keys()) + list(mrz_fields.keys())):
        if key in label_fields and label_fields[key]:
            fields[key] = label_fields[key]
        elif key in mrz_fields and mrz_fields[key]:
            fields[key] = mrz_fields[key]

    # ── Fallback strategies for remaining empty fields ──

    # Nationality — multiple approaches
    if not fields.get('nationality'):
        # Try 1: explicit nationality word in text
        m = re.search(r'\b(Indian|American|British|Canadian|Australian|French|German|Japanese|Chinese|Pakistani|Bangladeshi|Sri Lankan|Nepalese|Singaporean|Emirati)\b', text, re.IGNORECASE)
        if m:
            fields['nationality'] = m.group(1).strip().title()

    if not fields.get('nationality'):
        # Try 2: MRZ nationality code (may be in garbled MRZ line)
        if mrz_fields.get('nationality'):
            fields['nationality'] = mrz_fields['nationality']

    if not fields.get('nationality'):
        # Try 3: Find "IND", "GBR", "USA" etc. anywhere in text
        # (OCR may garble MRZ but country codes are short and survive)
        country_map = {
            'IND': 'Indian', 'USA': 'American', 'GBR': 'British',
            'CAN': 'Canadian', 'AUS': 'Australian', 'DEU': 'German',
            'FRA': 'French', 'JPN': 'Japanese', 'CHN': 'Chinese',
            'PAK': 'Pakistani', 'BGD': 'Bangladeshi', 'LKA': 'Sri Lankan',
            'NPL': 'Nepalese', 'SGP': 'Singaporean', 'ARE': 'Emirati',
        }
        for code, nationality in country_map.items():
            # Look for the code surrounded by non-alpha chars (in MRZ context)
            if re.search(r'(?<![A-Z])' + code + r'(?![A-Z])', text):
                fields['nationality'] = nationality
                break

    # Passport number: letter + 7 digits or 7-8 digits standalone
    if not fields.get('passport_number'):
        m = re.search(r'(?<!\w)([A-Z]\d{7}|\d{7,8})(?!\w)', text)
        if m:
            fields['passport_number'] = m.group(1).upper()

    # DOB: find date near "birth" keyword
    if not fields.get('date_of_birth_parsed'):
        m = re.search(r'(?:birth|dob|born).*?(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})', text, re.IGNORECASE)
        if m:
            fields['date_of_birth_parsed'] = parse_date(m.group(1))
        else:
            dates = re.findall(r'(\d{1,2}[/.-]\d{1,2}[/.-](?:19|20)\d{2})', text)
            for d in dates:
                parsed = parse_date(d)
                if parsed and hasattr(parsed, 'year') and 1940 <= parsed.year <= 2010:
                    fields['date_of_birth_parsed'] = parsed
                    break

    # Sex: standalone M/F
    if not fields.get('sex'):
        m = re.search(r'Gender\b.*?\b([MF])\b', text, re.IGNORECASE)
        if m:
            fields['sex'] = 'Male' if m.group(1).upper() == 'M' else 'Female'

    # Names from table rows near passport number (for invitation letters)
    if not fields.get('surname') and fields.get('passport_number'):
        pp = fields['passport_number']
        for line in lines:
            line_nospace = line.replace(' ', '')
            if pp in line_nospace or pp.replace(' ', '') in line_nospace:
                words_before = line.split(pp)[0] if pp in line else line
                words_before = re.sub(r'[|:;\t]', ' ', words_before)
                words_before = re.sub(r'^\s*[MF]\s+', '', words_before)
                name_parts = re.findall(r'[A-Z][a-z]+', words_before)
                if len(name_parts) >= 2:
                    fields['surname'] = name_parts[-1].upper()
                    fields['first_name'] = ' '.join(name_parts[:-1])
                    break
                name_parts = [p for p in re.findall(r'[A-Z]{2,}', words_before) if len(p) >= 3 and p not in ('MR','MRS','MS','DR')]
                if len(name_parts) >= 2:
                    fields['surname'] = name_parts[-1].upper()
                    fields['first_name'] = ' '.join(p.title() for p in name_parts[:-1])
                    break
                break

    return fields


@applicants_bp.route('/extract-passport', methods=['POST'])
@login_required
def extract_passport():
    """AJAX endpoint: extract fields from an uploaded passport PDF/image.
    Uses pdfplumber for text PDFs, falls back to OCR for scanned documents."""
    file = request.files.get('passport_file')
    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    # Save to a temp location for extraction
    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], '_temp')
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, secure_filename(file.filename))
    file.save(temp_path)

    extracted = {}
    fields = {}
    try:
        import re as _re

        def _is_valid_field(value):
            """Check if an extracted field value looks valid (not garbage)."""
            if not value or len(value.strip()) < 2:
                return False
            v = value.strip()
            # Reject if it contains too many non-alpha characters
            alpha_count = sum(1 for c in v if c.isalpha())
            if alpha_count < len(v) * 0.5:
                return False
            # Reject if it starts with common noise patterns
            noise = ['e.g.', 'eg.', 'eg ', 'i.e.', 'etc', 'n/a', 'nil', 'none']
            if v.lower().startswith(tuple(noise)):
                return False
            return True

        def _is_valid_passport_no(value):
            """Check if passport number looks valid."""
            if not value or len(value.strip()) < 5:
                return False
            v = value.strip()
            # Should be mostly alphanumeric, 6-9 chars
            if not _re.match(r'^[A-Z0-9]{6,9}$', v, _re.IGNORECASE):
                return False
            return True

        # Strategy 1: Try pdfplumber text extraction first
        pdf_fields = {}
        if temp_path.lower().endswith('.pdf'):
            pages = extract_text_from_pdf(temp_path)
            pdf_fields = extract_passport_fields(pages)

        # Strategy 2: Always try OCR as well for comparison/fallback
        ocr_fields = {}
        ocr_text = ocr_passport_text(temp_path)
        if ocr_text and len(ocr_text.strip()) > 10:
            ocr_fields = parse_passport_ocr(ocr_text)

        # Merge: prefer pdfplumber if valid, otherwise use OCR
        # For each key, pick the better result
        all_keys = set(list(pdf_fields.keys()) + list(ocr_fields.keys()))
        for key in all_keys:
            if key.startswith('_'):
                continue
            pdf_val = pdf_fields.get(key)
            ocr_val = ocr_fields.get(key)

            if key in ('surname', 'first_name', 'full_name'):
                # For name fields, validate quality
                if _is_valid_field(str(pdf_val)) if pdf_val else False:
                    fields[key] = pdf_val
                elif ocr_val:
                    fields[key] = ocr_val
            elif key == 'passport_number':
                if _is_valid_passport_no(str(pdf_val)) if pdf_val else False:
                    fields[key] = pdf_val
                elif _is_valid_passport_no(str(ocr_val)) if ocr_val else False:
                    fields[key] = ocr_val
            elif key.endswith('_parsed'):
                # For dates, prefer whichever has a valid date object
                if pdf_val and hasattr(pdf_val, 'strftime'):
                    fields[key] = pdf_val
                elif ocr_val and hasattr(ocr_val, 'strftime'):
                    fields[key] = ocr_val
                elif pdf_val:
                    fields[key] = pdf_val
                elif ocr_val:
                    fields[key] = ocr_val
            else:
                # For other fields (nationality, sex, place_of_birth, etc.)
                if pdf_val and str(pdf_val).strip():
                    fields[key] = pdf_val
                elif ocr_val and str(ocr_val).strip():
                    fields[key] = ocr_val

        # Clean up surname — remove common noise prefixes
        surname = fields.get('surname', '') or ''
        surname = _re.sub(r'^(?:e\.?g\.?\s*)', '', surname, flags=_re.IGNORECASE).strip()
        fields['surname'] = surname

        # Clean up given names
        given = fields.get('first_name', '') or ''
        # Remove non-alpha noise (parentheses, punctuation etc.)
        given = _re.sub(r'[^A-Za-z\s\-]', '', given).strip()
        fields['first_name'] = given

        # Map extracted fields to form field names
        extracted['surname'] = (fields.get('surname', '') or '').upper()
        extracted['given_names'] = fields.get('first_name', '') or ''
        extracted['passport_number'] = (fields.get('passport_number', '') or '').upper()
        extracted['nationality'] = fields.get('nationality', '') or ''
        extracted['sex'] = fields.get('sex', '') or ''
        extracted['place_of_birth'] = fields.get('place_of_birth', '') or ''

        # Parse dates into YYYY-MM-DD for date inputs
        for date_field, extracted_key in [
            ('date_of_birth_parsed', 'date_of_birth'),
            ('passport_issue_date_parsed', 'passport_issue_date'),
            ('passport_expiry_date_parsed', 'passport_expiry_date'),
        ]:
            dt = fields.get(date_field)
            if dt and hasattr(dt, 'strftime'):
                extracted[extracted_key] = dt.strftime('%Y-%m-%d')
            elif dt:
                extracted[extracted_key] = str(dt)

        # Count how many fields were extracted (for the success message)
        filled = sum(1 for k, v in extracted.items() if v and not k.startswith('_'))
        extracted['_field_count'] = filled

    except Exception as e:
        extracted['_error'] = f'Extraction error: {str(e)}'
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

    return jsonify(extracted)


@applicants_bp.route('/new', methods=['GET', 'POST'])
@login_required
def add_applicant():
    """Add new applicant"""
    if request.method == 'POST':
        # Client type fields
        client_type = request.form.get('client_type', 'retail').strip()
        corporate_name = request.form.get('corporate_name', '').strip()
        crm_id = request.form.get('crm_id', '').strip()

        # Passport-format name
        surname = request.form.get('surname', '').strip()
        given_names = request.form.get('given_names', '').strip()

        passport_number = request.form.get('passport_number', '').strip()
        nationality = request.form.get('nationality', '').strip()
        sex = request.form.get('sex', '').strip()
        place_of_birth = request.form.get('place_of_birth', '').strip()
        date_of_birth = request.form.get('date_of_birth', '').strip()
        passport_issue_date = request.form.get('passport_issue_date', '').strip()
        passport_expiry_date = request.form.get('passport_expiry_date', '').strip()
        date_of_travel = request.form.get('date_of_travel', '').strip()
        visa_type = request.form.get('visa_type', '').strip()
        destination_country = request.form.get('destination_country', '').strip()
        visa_purpose = request.form.get('visa_purpose', '').strip()
        notes = request.form.get('notes', '').strip()

        if not surname or not given_names:
            flash('Surname and Given Names are required.', 'danger')
            return render_template('applicants/form.html', applicant=None)

        if not visa_type:
            flash('Visa type is required.', 'danger')
            return render_template('applicants/form.html', applicant=None)

        if client_type == 'corporate' and not corporate_name:
            flash('Corporate name is required for corporate clients.', 'danger')
            return render_template('applicants/form.html', applicant=None)

        # Helper to parse dates safely
        def parse_date_safe(d):
            try:
                return datetime.strptime(d, '%Y-%m-%d').date() if d else None
            except ValueError:
                return None

        # Build full_name in passport format: SURNAME, Given Names
        full_name = f"{surname.upper()}, {given_names}"

        applicant = Applicant(
            client_type=client_type,
            corporate_name=corporate_name or None,
            crm_id=crm_id or None,
            surname=surname.upper(),
            given_names=given_names,
            full_name=full_name,
            passport_number=passport_number or None,
            nationality=nationality or None,
            sex=sex or None,
            place_of_birth=place_of_birth or None,
            date_of_birth=parse_date_safe(date_of_birth),
            passport_issue_date=parse_date_safe(passport_issue_date),
            passport_expiry_date=parse_date_safe(passport_expiry_date),
            date_of_travel=parse_date_safe(date_of_travel),
            visa_type=visa_type,
            destination_country=destination_country or None,
            visa_purpose=visa_purpose or None,
            status='draft',
            notes=notes or None,
            created_by_id=current_user.id
        )

        db.session.add(applicant)
        db.session.commit()

        # Handle passport copy upload if provided
        passport_file = request.files.get('passport_copy')
        if passport_file and passport_file.filename and allowed_file(passport_file.filename):
            applicant_dir = get_applicant_directory(applicant.id)
            os.makedirs(applicant_dir, exist_ok=True)

            original_filename = secure_filename(passport_file.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{original_filename}"
            file_path = os.path.join(applicant_dir, filename)
            passport_file.save(file_path)

            relative_path = os.path.join(str(applicant.id), filename)
            document = Document(
                applicant_id=applicant.id,
                filename=filename,
                original_filename=original_filename,
                file_path=relative_path,
                doc_type='passport_copy',
                uploaded_by_id=current_user.id
            )
            db.session.add(document)
            applicant.status = 'documents_uploaded'
            db.session.commit()

        flash(f'Applicant {full_name} created successfully!', 'success')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant.id))

    return render_template('applicants/form.html', applicant=None)


@applicants_bp.route('/<int:applicant_id>', methods=['GET'])
@login_required
def view_applicant(applicant_id):
    """View applicant details"""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to this applicant.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    documents = Document.query.filter_by(applicant_id=applicant_id).order_by(desc(Document.uploaded_at)).all()
    qc_reports = QCReport.query.filter_by(applicant_id=applicant_id).order_by(desc(QCReport.run_at)).all()

    return render_template('applicants/detail.html', applicant=applicant, documents=documents, qc_reports=qc_reports)


@applicants_bp.route('/<int:applicant_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_applicant(applicant_id):
    """Edit applicant"""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to edit this applicant.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    if request.method == 'POST':
        client_type = request.form.get('client_type', 'retail').strip()
        corporate_name = request.form.get('corporate_name', '').strip()
        crm_id = request.form.get('crm_id', '').strip()
        surname = request.form.get('surname', '').strip()
        given_names = request.form.get('given_names', '').strip()
        passport_number = request.form.get('passport_number', '').strip()
        nationality = request.form.get('nationality', '').strip()
        sex = request.form.get('sex', '').strip()
        place_of_birth = request.form.get('place_of_birth', '').strip()
        date_of_birth = request.form.get('date_of_birth', '').strip()
        passport_issue_date = request.form.get('passport_issue_date', '').strip()
        passport_expiry_date = request.form.get('passport_expiry_date', '').strip()
        date_of_travel = request.form.get('date_of_travel', '').strip()
        visa_type = request.form.get('visa_type', '').strip()
        destination_country = request.form.get('destination_country', '').strip()
        visa_purpose = request.form.get('visa_purpose', '').strip()
        notes = request.form.get('notes', '').strip()

        if not surname or not given_names:
            flash('Surname and Given Names are required.', 'danger')
            return render_template('applicants/form.html', applicant=applicant)

        if not visa_type:
            flash('Visa type is required.', 'danger')
            return render_template('applicants/form.html', applicant=applicant)

        def parse_date_safe(d):
            try:
                return datetime.strptime(d, '%Y-%m-%d').date() if d else None
            except ValueError:
                return None

        applicant.client_type = client_type
        applicant.corporate_name = corporate_name or None
        applicant.crm_id = crm_id or None
        applicant.surname = surname.upper()
        applicant.given_names = given_names
        applicant.full_name = f"{surname.upper()}, {given_names}"
        applicant.passport_number = passport_number or None
        applicant.nationality = nationality or None
        applicant.sex = sex or None
        applicant.place_of_birth = place_of_birth or None
        applicant.date_of_birth = parse_date_safe(date_of_birth)
        applicant.passport_issue_date = parse_date_safe(passport_issue_date)
        applicant.passport_expiry_date = parse_date_safe(passport_expiry_date)
        applicant.date_of_travel = parse_date_safe(date_of_travel)
        applicant.visa_type = visa_type
        applicant.destination_country = destination_country or None
        applicant.visa_purpose = visa_purpose or None
        applicant.notes = notes or None
        applicant.updated_at = datetime.utcnow()

        db.session.commit()

        flash(f'Applicant {applicant.full_name} updated successfully!', 'success')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant.id))

    return render_template('applicants/form.html', applicant=applicant)


@applicants_bp.route('/<int:applicant_id>/upload', methods=['POST'])
@login_required
def upload_document(applicant_id):
    """Upload document for applicant"""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        return redirect(url_for('applicants.list_applicants')), 403

    if 'file' not in request.files:
        flash('No file provided.', 'danger')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    if not allowed_file(file.filename):
        flash('File type not allowed. Allowed types: ' + ', '.join(current_app.config['ALLOWED_EXTENSIONS']), 'danger')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    # Create applicant directory if it doesn't exist
    applicant_dir = get_applicant_directory(applicant_id)
    os.makedirs(applicant_dir, exist_ok=True)

    # Save file with secure name
    original_filename = secure_filename(file.filename)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{original_filename}"
    file_path = os.path.join(applicant_dir, filename)

    file.save(file_path)

    # Detect document type if PDF
    doc_type = 'other'
    if original_filename.lower().endswith('.pdf'):
        try:
            pages = extract_text_from_pdf(file_path)
            detected_type = detect_document_type(pages)
            # Map detected type to our model choices
            type_map = {
                'schengen_visa': 'visa_application',
                'uk_visa': 'visa_application',
                'france_receipt': 'visa_application',
                'passport_copy': 'passport_copy',
                'bank_statement': 'bank_statement',
                'flight_ticket': 'flight_ticket',
                'hotel_booking': 'hotel_booking',
                'invitation_letter': 'invitation_letter',
                'covering_letter': 'cover_letter',
                'travel_insurance': 'other',
            }
            doc_type = type_map.get(detected_type, 'other')
        except Exception:
            doc_type = 'other'

    # Store in database with relative path
    relative_path = os.path.join(str(applicant_id), filename)
    document = Document(
        applicant_id=applicant_id,
        filename=filename,
        original_filename=original_filename,
        file_path=relative_path,
        doc_type=doc_type,
        uploaded_by_id=current_user.id
    )

    db.session.add(document)

    # Update applicant status if this is the first document
    if not applicant.documents:
        applicant.status = 'documents_uploaded'

    applicant.updated_at = datetime.utcnow()
    db.session.commit()

    flash(f'Document {original_filename} uploaded successfully!', 'success')
    return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))


@applicants_bp.route('/<int:applicant_id>/documents/<int:doc_id>/download', methods=['GET'])
@login_required
def download_document(applicant_id, doc_id):
    """Download document"""
    applicant = Applicant.query.get_or_404(applicant_id)
    document = Document.query.get_or_404(doc_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to this document.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], document.file_path)
    if not os.path.exists(file_path):
        flash('File not found.', 'danger')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    return send_file(file_path, as_attachment=True, download_name=document.original_filename)


@applicants_bp.route('/<int:applicant_id>/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_document(applicant_id, doc_id):
    """Delete document"""
    applicant = Applicant.query.get_or_404(applicant_id)
    document = Document.query.get_or_404(doc_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to delete this document.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    # Delete from disk
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], document.file_path)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    original_filename = document.original_filename
    db.session.delete(document)
    db.session.commit()

    flash(f'Document {original_filename} deleted successfully!', 'success')
    return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))
