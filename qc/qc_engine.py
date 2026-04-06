"""
Visa Application QC Engine
Cross-references visa application fields against supporting documents.
Produces a structured checklist report.
"""

from datetime import datetime, timedelta
from .extractor import parse_date, format_date


# ─── Name Matching ──────────────────────────────────────────────────

def normalize_name(name):
    """Normalize a name for comparison.

    Handles:
    - Passport/visa format: SURNAME GIVEN_NAME
    - Flight ticket format: SURNAME/GIVENNAME MR, SALIAN/NITISH MR
    - Comma-separated: SURNAME, GIVEN_NAME
    - Titles: MR, MRS, MS, DR, SHRI, SMT
    """
    if not name:
        return ""
    # Convert to uppercase
    name = name.upper().strip()
    # Replace slashes and commas with spaces (handles SURNAME/GIVENNAME format)
    name = name.replace('/', ' ').replace(',', ' ')
    # Remove titles/salutations (must be whole words)
    titles = ['MR.', 'MRS.', 'MS.', 'DR.', 'MR', 'MRS', 'MS', 'DR', 'SHRI', 'SMT', 'PROF', 'SIR', 'MASTER']
    parts = name.split()
    parts = [p for p in parts if p.rstrip('.') not in [t.rstrip('.') for t in titles]]
    # Remove dots and extra whitespace
    name = ' '.join(parts)
    name = name.replace('.', ' ')
    name = ' '.join(name.split())
    return name


def name_parts(normalized_name):
    """Split a normalized name into a set of parts."""
    return set(normalized_name.split()) if normalized_name else set()


def names_match(name1, name2):
    """Check if two names match (fuzzy - allows reordering of name parts).

    Designed for visa processing where:
    - Passport & visa app use: SURNAME  GIVEN_NAME(S)
    - Flight tickets use: SURNAME/GIVENNAME MR (single field)
    - Covering/invitation letters may use natural order: GIVENNAME SURNAME

    The order doesn't matter — we compare the set of name parts.
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return None  # Can't compare

    # Exact match after normalization
    if n1 == n2:
        return True

    parts1 = name_parts(n1)
    parts2 = name_parts(n2)

    # If one is a subset of the other (handles middle name present in one but not the other)
    if parts1.issubset(parts2) or parts2.issubset(parts1):
        return True

    # Check overlap — at least 2 name parts must match (handles extra initials)
    overlap = parts1 & parts2
    if len(overlap) >= 2:
        return True

    # For single-part names (rare), check if that part appears in the other
    if len(parts1) == 1 and parts1.issubset(parts2):
        return True
    if len(parts2) == 1 and parts2.issubset(parts1):
        return True

    return False


# ─── Date Matching ──────────────────────────────────────────────────

def dates_match(date1, date2):
    """Check if two dates match. Accepts datetime objects or strings."""
    d1 = date1 if isinstance(date1, datetime) else parse_date(str(date1)) if date1 else None
    d2 = date2 if isinstance(date2, datetime) else parse_date(str(date2)) if date2 else None

    if d1 is None or d2 is None:
        return None  # Can't compare
    return d1.date() == d2.date()


# ─── QC Check Functions ─────────────────────────────────────────────

def check_name(visa_fields, supporting_docs):
    """Check applicant name across all documents.

    Priority:
    - Passport copy vs visa application: CRITICAL match (same Surname/Given Name format)
    - Covering letter / invitation letter vs visa: important match
    - Flight ticket vs visa: softer check (ticket uses SURNAME/GIVENNAME MR format)
    """
    results = []
    visa_name = visa_fields.get('full_name') or visa_fields.get('surname', '')
    visa_surname = visa_fields.get('surname', '')
    visa_first = visa_fields.get('first_name', '')
    if not visa_name:
        results.append({
            'field': 'Applicant Name',
            'status': 'warning',
            'visa_value': 'NOT FOUND in visa application',
            'doc_value': '',
            'doc_source': '',
            'message': 'Could not extract applicant name from visa application'
        })
        return results

    for doc in supporting_docs:
        doc_type = doc.get('_doc_type', '')
        doc_source = doc.get('_doc_type_label', 'Unknown')
        is_flight = (doc_type == 'flight_ticket')
        is_passport = (doc_type == 'passport_copy')

        # Get the name from the document based on its type
        if is_flight:
            doc_name = doc.get('passenger_name', '')
        else:
            doc_name = doc.get('full_name') or doc.get('invitee_name') or doc.get('traveler_name') or doc.get('name_found') or ''

        if not doc_name:
            continue

        # For passport copy: also do a strict surname + given name check
        if is_passport:
            doc_surname = doc.get('surname', '')
            doc_first = doc.get('first_name', '')

            # Strict check: surname must match between passport and visa app
            surname_ok = names_match(visa_surname, doc_surname) if visa_surname and doc_surname else None
            first_ok = names_match(visa_first, doc_first) if visa_first and doc_first else None

            if surname_ok and first_ok:
                results.append({
                    'field': 'Applicant Name (Passport)',
                    'status': 'pass',
                    'visa_value': f'{visa_surname} / {visa_first}',
                    'doc_value': f'{doc_surname} / {doc_first}',
                    'doc_source': doc_source,
                    'message': 'Surname & given name match between visa application and passport'
                })
            elif surname_ok is False or first_ok is False:
                mismatch_parts = []
                if surname_ok is False:
                    mismatch_parts.append(f'Surname: visa="{visa_surname}" vs passport="{doc_surname}"')
                if first_ok is False:
                    mismatch_parts.append(f'Given name: visa="{visa_first}" vs passport="{doc_first}"')
                results.append({
                    'field': 'Applicant Name (Passport)',
                    'status': 'fail',
                    'visa_value': f'{visa_surname} / {visa_first}',
                    'doc_value': f'{doc_surname} / {doc_first}',
                    'doc_source': doc_source,
                    'message': f'NAME MISMATCH with passport! {"; ".join(mismatch_parts)}'
                })
            else:
                # Fallback to full-name comparison
                match = names_match(visa_name, doc_name)
                if match:
                    results.append({
                        'field': 'Applicant Name (Passport)',
                        'status': 'pass',
                        'visa_value': visa_name,
                        'doc_value': doc_name,
                        'doc_source': doc_source,
                        'message': 'Name matches with passport copy'
                    })
                elif match is False:
                    results.append({
                        'field': 'Applicant Name (Passport)',
                        'status': 'fail',
                        'visa_value': visa_name,
                        'doc_value': doc_name,
                        'doc_source': doc_source,
                        'message': 'NAME MISMATCH with passport copy!'
                    })

        elif is_flight:
            # Flight tickets use different format (SURNAME/GIVENNAME MR)
            # This is a softer check — informational if it matches, warning if not
            match = names_match(visa_name, doc_name)
            if match:
                results.append({
                    'field': 'Passenger Name (Flight Ticket)',
                    'status': 'pass',
                    'visa_value': visa_name,
                    'doc_value': doc_name,
                    'doc_source': doc_source,
                    'message': 'Passenger name on flight ticket matches visa application'
                })
            else:
                results.append({
                    'field': 'Passenger Name (Flight Ticket)',
                    'status': 'warning',
                    'visa_value': visa_name,
                    'doc_value': doc_name,
                    'doc_source': doc_source,
                    'message': 'Passenger name on flight ticket may not match — flight tickets use different format (SURNAME/GIVENNAME). Please verify manually.'
                })

        else:
            # Other documents (invitation letter, covering letter, generic)
            match = names_match(visa_name, doc_name)
            if match:
                results.append({
                    'field': 'Applicant Name',
                    'status': 'pass',
                    'visa_value': visa_name,
                    'doc_value': doc_name,
                    'doc_source': doc_source,
                    'message': f'Name matches with {doc_source}'
                })
            elif match is False:
                results.append({
                    'field': 'Applicant Name',
                    'status': 'fail',
                    'visa_value': visa_name,
                    'doc_value': doc_name,
                    'doc_source': doc_source,
                    'message': f'NAME MISMATCH with {doc_source}!'
                })

    if not results:
        results.append({
            'field': 'Applicant Name',
            'status': 'warning',
            'visa_value': visa_name,
            'doc_value': '',
            'doc_source': '',
            'message': 'No supporting documents to cross-check name against'
        })

    return results


def check_dob(visa_fields, supporting_docs):
    """Check date of birth across all documents."""
    results = []
    visa_dob = visa_fields.get('date_of_birth_parsed')
    visa_dob_str = visa_fields.get('date_of_birth', '')

    if not visa_dob:
        results.append({
            'field': 'Date of Birth',
            'status': 'warning',
            'visa_value': visa_dob_str or 'NOT FOUND',
            'doc_value': '',
            'doc_source': '',
            'message': 'Could not extract/parse DOB from visa application'
        })
        return results

    for doc in supporting_docs:
        doc_dob = doc.get('date_of_birth_parsed')
        doc_dob_str = doc.get('date_of_birth', '')
        doc_source = doc.get('_doc_type_label', 'Unknown')

        if doc_dob:
            if dates_match(visa_dob, doc_dob):
                results.append({
                    'field': 'Date of Birth',
                    'status': 'pass',
                    'visa_value': visa_dob_str,
                    'doc_value': doc_dob_str,
                    'doc_source': doc_source,
                    'message': f'DOB matches with {doc_source}'
                })
            else:
                results.append({
                    'field': 'Date of Birth',
                    'status': 'fail',
                    'visa_value': visa_dob_str,
                    'doc_value': doc_dob_str,
                    'doc_source': doc_source,
                    'message': f'DOB MISMATCH with {doc_source}!'
                })

    return results


def check_passport_number(visa_fields, supporting_docs):
    """Check passport number across all documents."""
    results = []
    visa_pp = visa_fields.get('passport_number', '').upper().strip()

    if not visa_pp:
        results.append({
            'field': 'Passport Number',
            'status': 'warning',
            'visa_value': 'NOT FOUND',
            'doc_value': '',
            'doc_source': '',
            'message': 'Could not extract passport number from visa application'
        })
        return results

    for doc in supporting_docs:
        doc_pp = doc.get('passport_number', '').upper().strip()
        doc_source = doc.get('_doc_type_label', 'Unknown')

        if doc_pp:
            if visa_pp == doc_pp:
                results.append({
                    'field': 'Passport Number',
                    'status': 'pass',
                    'visa_value': visa_pp,
                    'doc_value': doc_pp,
                    'doc_source': doc_source,
                    'message': f'Passport number matches with {doc_source}'
                })
            else:
                results.append({
                    'field': 'Passport Number',
                    'status': 'fail',
                    'visa_value': visa_pp,
                    'doc_value': doc_pp,
                    'doc_source': doc_source,
                    'message': f'PASSPORT NUMBER MISMATCH with {doc_source}!'
                })

    return results


def check_passport_validity(visa_fields):
    """Check if passport is valid for the travel dates."""
    results = []
    expiry = visa_fields.get('passport_expiry_date_parsed')
    travel_to = visa_fields.get('travel_date_to_parsed') or visa_fields.get('travel_date_from_parsed')
    visa_type = visa_fields.get('_type', '')

    if not expiry:
        results.append({
            'field': 'Passport Validity',
            'status': 'warning',
            'visa_value': 'Expiry date not found',
            'doc_value': '',
            'doc_source': 'Visa Application',
            'message': 'Could not verify passport validity — expiry date not extracted'
        })
        return results

    # Check if passport is expired
    if expiry < datetime.now():
        results.append({
            'field': 'Passport Validity',
            'status': 'fail',
            'visa_value': format_date(expiry),
            'doc_value': 'EXPIRED',
            'doc_source': 'Visa Application',
            'message': 'PASSPORT IS EXPIRED!'
        })
        return results

    # For Schengen: passport must be valid 3 months after intended departure
    if travel_to and 'schengen' in visa_type:
        min_validity = travel_to + timedelta(days=90)
        if expiry < min_validity:
            results.append({
                'field': 'Passport Validity (Schengen 3-month rule)',
                'status': 'fail',
                'visa_value': f'Passport expires: {format_date(expiry)}',
                'doc_value': f'Must be valid until: {format_date(min_validity)}',
                'doc_source': 'Schengen Rule',
                'message': 'Passport must be valid at least 3 months after departure date!'
            })
        else:
            results.append({
                'field': 'Passport Validity (Schengen 3-month rule)',
                'status': 'pass',
                'visa_value': f'Expires: {format_date(expiry)}',
                'doc_value': f'Departure + 3 months: {format_date(min_validity)}',
                'doc_source': 'Schengen Rule',
                'message': 'Passport validity meets Schengen 3-month requirement'
            })

    # For UK: passport should be valid for duration of stay
    if travel_to and 'uk' in visa_type:
        if expiry < travel_to:
            results.append({
                'field': 'Passport Validity',
                'status': 'fail',
                'visa_value': f'Passport expires: {format_date(expiry)}',
                'doc_value': f'Travel end: {format_date(travel_to)}',
                'doc_source': 'UK Rule',
                'message': 'Passport expires before end of travel!'
            })
        else:
            results.append({
                'field': 'Passport Validity',
                'status': 'pass',
                'visa_value': f'Expires: {format_date(expiry)}',
                'doc_value': f'Travel end: {format_date(travel_to)}',
                'doc_source': 'UK Rule',
                'message': 'Passport is valid for duration of travel'
            })

    if not results:
        results.append({
            'field': 'Passport Validity',
            'status': 'pass',
            'visa_value': f'Expires: {format_date(expiry)}',
            'doc_value': '',
            'doc_source': 'Visa Application',
            'message': 'Passport is currently valid'
        })

    return results


def check_travel_dates(visa_fields, supporting_docs):
    """Check travel dates against flight tickets and other documents."""
    results = []
    visa_from = visa_fields.get('travel_date_from_parsed')
    visa_to = visa_fields.get('travel_date_to_parsed')
    visa_from_str = visa_fields.get('travel_date_from', '')
    visa_to_str = visa_fields.get('travel_date_to', '')

    # Basic validation
    if visa_from and visa_to:
        if visa_from > visa_to:
            results.append({
                'field': 'Travel Dates (Logic)',
                'status': 'fail',
                'visa_value': f'From: {visa_from_str}',
                'doc_value': f'To: {visa_to_str}',
                'doc_source': 'Visa Application',
                'message': 'Departure date is AFTER arrival date!'
            })
        else:
            stay_days = (visa_to - visa_from).days
            results.append({
                'field': 'Travel Dates (Duration)',
                'status': 'info',
                'visa_value': f'{visa_from_str} to {visa_to_str}',
                'doc_value': f'{stay_days} days',
                'doc_source': 'Visa Application',
                'message': f'Planned stay: {stay_days} days'
            })

            # Schengen 90-day rule
            if visa_fields.get('_type') == 'schengen_visa' and stay_days > 90:
                results.append({
                    'field': 'Travel Duration (Schengen Limit)',
                    'status': 'fail',
                    'visa_value': f'{stay_days} days',
                    'doc_value': 'Maximum 90 days',
                    'doc_source': 'Schengen Rule',
                    'message': f'Stay of {stay_days} days exceeds Schengen 90-day limit!'
                })

    # Check if travel dates are in the past
    if visa_from and visa_from < datetime.now():
        results.append({
            'field': 'Travel Dates (Past Check)',
            'status': 'warning',
            'visa_value': visa_from_str,
            'doc_value': f'Today: {datetime.now().strftime("%d/%m/%Y")}',
            'doc_source': 'System',
            'message': 'Travel start date appears to be in the past'
        })

    # Cross-check with flight tickets
    for doc in supporting_docs:
        if doc.get('_doc_type') == 'flight_ticket':
            doc_source = doc.get('_doc_type_label', 'Flight Ticket')
            dep_date = doc.get('departure_date_parsed')
            ret_date = doc.get('return_date_parsed')

            if visa_from and dep_date:
                if dates_match(visa_from, dep_date):
                    results.append({
                        'field': 'Travel Start Date',
                        'status': 'pass',
                        'visa_value': visa_from_str,
                        'doc_value': doc.get('departure_date', ''),
                        'doc_source': doc_source,
                        'message': 'Arrival date matches flight departure'
                    })
                else:
                    results.append({
                        'field': 'Travel Start Date',
                        'status': 'fail',
                        'visa_value': visa_from_str,
                        'doc_value': doc.get('departure_date', ''),
                        'doc_source': doc_source,
                        'message': 'Travel start date does NOT match flight ticket!'
                    })

            if visa_to and ret_date:
                if dates_match(visa_to, ret_date):
                    results.append({
                        'field': 'Travel End Date',
                        'status': 'pass',
                        'visa_value': visa_to_str,
                        'doc_value': doc.get('return_date', ''),
                        'doc_source': doc_source,
                        'message': 'Departure date matches return flight'
                    })
                else:
                    results.append({
                        'field': 'Travel End Date',
                        'status': 'fail',
                        'visa_value': visa_to_str,
                        'doc_value': doc.get('return_date', ''),
                        'doc_source': doc_source,
                        'message': 'Travel end date does NOT match return flight!'
                    })

    return results


def check_application_date(visa_fields):
    """Verify the application date is reasonable."""
    results = []
    app_date = visa_fields.get('application_date_parsed')
    app_date_str = visa_fields.get('application_date', '')

    if app_date:
        today = datetime.now()
        if app_date > today + timedelta(days=1):
            results.append({
                'field': 'Application Date',
                'status': 'fail',
                'visa_value': app_date_str,
                'doc_value': f'Today: {today.strftime("%d/%m/%Y")}',
                'doc_source': 'System',
                'message': 'Application date is in the FUTURE!'
            })
        elif app_date < today - timedelta(days=180):
            results.append({
                'field': 'Application Date',
                'status': 'warning',
                'visa_value': app_date_str,
                'doc_value': f'Today: {today.strftime("%d/%m/%Y")}',
                'doc_source': 'System',
                'message': 'Application date is more than 6 months old'
            })
        else:
            results.append({
                'field': 'Application Date',
                'status': 'pass',
                'visa_value': app_date_str,
                'doc_value': '',
                'doc_source': 'System',
                'message': 'Application date is reasonable'
            })

    return results


def check_completeness(visa_fields):
    """Check if critical fields are filled in."""
    results = []
    visa_type = visa_fields.get('_type', '')

    critical_fields = {
        'full_name': 'Applicant Full Name',
        'date_of_birth': 'Date of Birth',
        'passport_number': 'Passport Number',
        'nationality': 'Nationality',
        'sex': 'Sex/Gender',
    }

    # Add type-specific fields
    if 'schengen' in visa_type:
        critical_fields.update({
            'travel_date_from': 'Travel Start Date',
            'travel_date_to': 'Travel End Date',
            'purpose': 'Purpose of Journey',
            'destination': 'Destination Country',
            'passport_issue_date': 'Passport Issue Date',
            'passport_expiry_date': 'Passport Expiry Date',
        })
    elif 'uk' in visa_type:
        critical_fields.update({
            'travel_date_from': 'Travel Start Date',
            'travel_date_to': 'Travel End Date',
            'purpose': 'Purpose of Visit',
        })

    for field_key, field_label in critical_fields.items():
        value = visa_fields.get(field_key, '').strip() if visa_fields.get(field_key) else ''
        if value:
            results.append({
                'field': f'Completeness: {field_label}',
                'status': 'pass',
                'visa_value': value,
                'doc_value': '',
                'doc_source': 'Visa Application',
                'message': f'{field_label} is filled in'
            })
        else:
            results.append({
                'field': f'Completeness: {field_label}',
                'status': 'fail',
                'visa_value': 'MISSING / NOT DETECTED',
                'doc_value': '',
                'doc_source': 'Visa Application',
                'message': f'{field_label} appears to be empty or could not be extracted'
            })

    return results


def check_passport_dates_consistency(visa_fields, supporting_docs):
    """Cross-check passport issue and expiry dates."""
    results = []

    visa_issue = visa_fields.get('passport_issue_date_parsed')
    visa_expiry = visa_fields.get('passport_expiry_date_parsed')

    for doc in supporting_docs:
        doc_source = doc.get('_doc_type_label', 'Unknown')
        doc_issue = doc.get('passport_issue_date_parsed')
        doc_expiry = doc.get('passport_expiry_date_parsed')

        if visa_issue and doc_issue:
            if dates_match(visa_issue, doc_issue):
                results.append({
                    'field': 'Passport Issue Date',
                    'status': 'pass',
                    'visa_value': visa_fields.get('passport_issue_date', ''),
                    'doc_value': doc.get('passport_issue_date', ''),
                    'doc_source': doc_source,
                    'message': f'Issue date matches {doc_source}'
                })
            else:
                results.append({
                    'field': 'Passport Issue Date',
                    'status': 'fail',
                    'visa_value': visa_fields.get('passport_issue_date', ''),
                    'doc_value': doc.get('passport_issue_date', ''),
                    'doc_source': doc_source,
                    'message': f'Passport issue date MISMATCH with {doc_source}!'
                })

        if visa_expiry and doc_expiry:
            if dates_match(visa_expiry, doc_expiry):
                results.append({
                    'field': 'Passport Expiry Date',
                    'status': 'pass',
                    'visa_value': visa_fields.get('passport_expiry_date', ''),
                    'doc_value': doc.get('passport_expiry_date', ''),
                    'doc_source': doc_source,
                    'message': f'Expiry date matches {doc_source}'
                })
            else:
                results.append({
                    'field': 'Passport Expiry Date',
                    'status': 'fail',
                    'visa_value': visa_fields.get('passport_expiry_date', ''),
                    'doc_value': doc.get('passport_expiry_date', ''),
                    'doc_source': doc_source,
                    'message': f'Passport expiry date MISMATCH with {doc_source}!'
                })

    return results


def check_gender_consistency(visa_fields, supporting_docs):
    """Cross-check gender/sex field."""
    results = []
    visa_sex = (visa_fields.get('sex') or '').strip().upper()

    if not visa_sex:
        return results

    for doc in supporting_docs:
        doc_sex = (doc.get('sex') or '').strip().upper()
        doc_source = doc.get('_doc_type_label', 'Unknown')

        if doc_sex:
            if visa_sex[0] == doc_sex[0]:  # Compare first letter (M/F)
                results.append({
                    'field': 'Sex/Gender',
                    'status': 'pass',
                    'visa_value': visa_fields.get('sex', ''),
                    'doc_value': doc.get('sex', ''),
                    'doc_source': doc_source,
                    'message': f'Gender matches with {doc_source}'
                })
            else:
                results.append({
                    'field': 'Sex/Gender',
                    'status': 'fail',
                    'visa_value': visa_fields.get('sex', ''),
                    'doc_value': doc.get('sex', ''),
                    'doc_source': doc_source,
                    'message': f'GENDER MISMATCH with {doc_source}!'
                })

    return results


# ─── Invitation Letter QC ───────────────────────────────────────────

def check_invitation_letter(visa_fields, supporting_docs, visa_purpose):
    """QC checks specific to the invitation letter (required for business visa).

    Checks:
    - Invitation letter is present
    - Invitee name matches visa application
    - Passport number matches
    - Travel dates match
    - Signatory name is present
    - Signatory designation is present
    - Signatory contact number is present
    """
    results = []
    invitation_docs = [d for d in supporting_docs if d.get('_doc_type') == 'invitation_letter']

    # Only enforce invitation letter for business visas
    if visa_purpose != 'business':
        return results

    if not invitation_docs:
        results.append({
            'field': 'Invitation Letter',
            'status': 'fail',
            'visa_value': 'Business Visa',
            'doc_value': 'NOT UPLOADED',
            'doc_source': 'Document Check',
            'message': 'Invitation letter is REQUIRED for business visa but was not found!'
        })
        return results

    visa_name = visa_fields.get('full_name') or visa_fields.get('surname', '')
    visa_pp = visa_fields.get('passport_number', '').upper()
    visa_from = visa_fields.get('travel_date_from_parsed')
    visa_to = visa_fields.get('travel_date_to_parsed')

    for inv in invitation_docs:
        src = 'Invitation Letter'

        # Check invitee name
        inv_name = inv.get('invitee_name', '')
        if inv_name:
            if names_match(visa_name, inv_name):
                results.append({
                    'field': 'Invitation: Traveler Name',
                    'status': 'pass',
                    'visa_value': visa_name,
                    'doc_value': inv_name,
                    'doc_source': src,
                    'message': 'Traveler name matches invitation letter'
                })
            else:
                results.append({
                    'field': 'Invitation: Traveler Name',
                    'status': 'fail',
                    'visa_value': visa_name,
                    'doc_value': inv_name,
                    'doc_source': src,
                    'message': 'Traveler name MISMATCH with invitation letter!'
                })
        else:
            results.append({
                'field': 'Invitation: Traveler Name',
                'status': 'warning',
                'visa_value': visa_name,
                'doc_value': 'NOT FOUND',
                'doc_source': src,
                'message': 'Could not extract traveler name from invitation letter'
            })

        # Check passport number
        inv_pp = inv.get('passport_number', '').upper()
        if inv_pp:
            if visa_pp == inv_pp:
                results.append({
                    'field': 'Invitation: Passport Number',
                    'status': 'pass',
                    'visa_value': visa_pp,
                    'doc_value': inv_pp,
                    'doc_source': src,
                    'message': 'Passport number matches invitation letter'
                })
            else:
                results.append({
                    'field': 'Invitation: Passport Number',
                    'status': 'fail',
                    'visa_value': visa_pp,
                    'doc_value': inv_pp,
                    'doc_source': src,
                    'message': 'Passport number MISMATCH with invitation letter!'
                })
        else:
            results.append({
                'field': 'Invitation: Passport Number',
                'status': 'warning',
                'visa_value': visa_pp,
                'doc_value': 'NOT FOUND',
                'doc_source': src,
                'message': 'Passport number not found in invitation letter — should be included'
            })

        # Check travel dates
        inv_from = inv.get('visit_from_parsed')
        inv_to = inv.get('visit_to_parsed')
        if visa_from and inv_from:
            if dates_match(visa_from, inv_from):
                results.append({
                    'field': 'Invitation: Travel Start Date',
                    'status': 'pass',
                    'visa_value': visa_fields.get('travel_date_from', ''),
                    'doc_value': inv.get('visit_from', ''),
                    'doc_source': src,
                    'message': 'Travel start date matches invitation letter'
                })
            else:
                results.append({
                    'field': 'Invitation: Travel Start Date',
                    'status': 'fail',
                    'visa_value': visa_fields.get('travel_date_from', ''),
                    'doc_value': inv.get('visit_from', ''),
                    'doc_source': src,
                    'message': 'Travel start date MISMATCH with invitation letter!'
                })

        if visa_to and inv_to:
            if dates_match(visa_to, inv_to):
                results.append({
                    'field': 'Invitation: Travel End Date',
                    'status': 'pass',
                    'visa_value': visa_fields.get('travel_date_to', ''),
                    'doc_value': inv.get('visit_to', ''),
                    'doc_source': src,
                    'message': 'Travel end date matches invitation letter'
                })
            else:
                results.append({
                    'field': 'Invitation: Travel End Date',
                    'status': 'fail',
                    'visa_value': visa_fields.get('travel_date_to', ''),
                    'doc_value': inv.get('visit_to', ''),
                    'doc_source': src,
                    'message': 'Travel end date MISMATCH with invitation letter!'
                })

        # Check signatory name
        sig_name = inv.get('signatory_name', '')
        if sig_name:
            results.append({
                'field': 'Invitation: Signatory Name',
                'status': 'pass',
                'visa_value': sig_name,
                'doc_value': '',
                'doc_source': src,
                'message': f'Signatory identified: {sig_name}'
            })
        else:
            results.append({
                'field': 'Invitation: Signatory Name',
                'status': 'fail',
                'visa_value': 'NOT FOUND',
                'doc_value': '',
                'doc_source': src,
                'message': 'Authorized signatory name is MISSING from invitation letter!'
            })

        # Check signatory designation
        sig_desig = inv.get('signatory_designation', '')
        if sig_desig:
            results.append({
                'field': 'Invitation: Signatory Designation',
                'status': 'pass',
                'visa_value': sig_desig,
                'doc_value': '',
                'doc_source': src,
                'message': f'Signatory designation: {sig_desig}'
            })
        else:
            results.append({
                'field': 'Invitation: Signatory Designation',
                'status': 'fail',
                'visa_value': 'NOT FOUND',
                'doc_value': '',
                'doc_source': src,
                'message': 'Signatory designation is MISSING from invitation letter!'
            })

        # Check signatory contact
        sig_contact = inv.get('signatory_contact', '')
        if sig_contact:
            results.append({
                'field': 'Invitation: Signatory Contact',
                'status': 'pass',
                'visa_value': sig_contact,
                'doc_value': '',
                'doc_source': src,
                'message': f'Signatory contact number: {sig_contact}'
            })
        else:
            results.append({
                'field': 'Invitation: Signatory Contact',
                'status': 'fail',
                'visa_value': 'NOT FOUND',
                'doc_value': '',
                'doc_source': src,
                'message': 'Signatory contact number is MISSING from invitation letter!'
            })

    return results


# ─── Covering Letter QC ─────────────────────────────────────────────

def check_covering_letter(visa_fields, supporting_docs, visa_purpose):
    """QC checks for the covering letter (required for all visa types).

    Checks:
    - Covering letter is present
    - Traveler name matches visa application
    - Passport number matches
    - Travel dates match
    - Purpose of travel is stated
    - Expense bearer is identified
    - For business: company is bearing expenses
    - For leisure with sponsor: sponsor details are present
    """
    results = []
    covering_docs = [d for d in supporting_docs if d.get('_doc_type') == 'covering_letter']

    if not covering_docs:
        results.append({
            'field': 'Covering Letter',
            'status': 'fail',
            'visa_value': 'Required Document',
            'doc_value': 'NOT UPLOADED',
            'doc_source': 'Document Check',
            'message': 'Covering letter is REQUIRED but was not found!'
        })
        return results

    visa_name = visa_fields.get('full_name') or visa_fields.get('surname', '')
    visa_pp = visa_fields.get('passport_number', '').upper()
    visa_from = visa_fields.get('travel_date_from_parsed')
    visa_to = visa_fields.get('travel_date_to_parsed')

    for cl in covering_docs:
        src = 'Covering Letter'

        # Check traveler name
        cl_name = cl.get('traveler_name', '')
        if cl_name:
            if names_match(visa_name, cl_name):
                results.append({
                    'field': 'Cover Letter: Traveler Name',
                    'status': 'pass',
                    'visa_value': visa_name,
                    'doc_value': cl_name,
                    'doc_source': src,
                    'message': 'Traveler name matches covering letter'
                })
            else:
                results.append({
                    'field': 'Cover Letter: Traveler Name',
                    'status': 'fail',
                    'visa_value': visa_name,
                    'doc_value': cl_name,
                    'doc_source': src,
                    'message': 'Traveler name MISMATCH with covering letter!'
                })
        else:
            results.append({
                'field': 'Cover Letter: Traveler Name',
                'status': 'warning',
                'visa_value': visa_name,
                'doc_value': 'NOT FOUND',
                'doc_source': src,
                'message': 'Could not extract traveler name from covering letter'
            })

        # Check passport number
        cl_pp = cl.get('passport_number', '').upper()
        if cl_pp:
            if visa_pp == cl_pp:
                results.append({
                    'field': 'Cover Letter: Passport Number',
                    'status': 'pass',
                    'visa_value': visa_pp,
                    'doc_value': cl_pp,
                    'doc_source': src,
                    'message': 'Passport number matches covering letter'
                })
            else:
                results.append({
                    'field': 'Cover Letter: Passport Number',
                    'status': 'fail',
                    'visa_value': visa_pp,
                    'doc_value': cl_pp,
                    'doc_source': src,
                    'message': 'Passport number MISMATCH with covering letter!'
                })
        else:
            results.append({
                'field': 'Cover Letter: Passport Number',
                'status': 'warning',
                'visa_value': visa_pp,
                'doc_value': 'NOT FOUND',
                'doc_source': src,
                'message': 'Passport number not found in covering letter'
            })

        # Check travel dates
        cl_from = cl.get('travel_from_parsed')
        cl_to = cl.get('travel_to_parsed')
        if visa_from and cl_from:
            if dates_match(visa_from, cl_from):
                results.append({
                    'field': 'Cover Letter: Travel Start Date',
                    'status': 'pass',
                    'visa_value': visa_fields.get('travel_date_from', ''),
                    'doc_value': cl.get('travel_from', ''),
                    'doc_source': src,
                    'message': 'Travel start date matches covering letter'
                })
            else:
                results.append({
                    'field': 'Cover Letter: Travel Start Date',
                    'status': 'fail',
                    'visa_value': visa_fields.get('travel_date_from', ''),
                    'doc_value': cl.get('travel_from', ''),
                    'doc_source': src,
                    'message': 'Travel start date MISMATCH with covering letter!'
                })

        if visa_to and cl_to:
            if dates_match(visa_to, cl_to):
                results.append({
                    'field': 'Cover Letter: Travel End Date',
                    'status': 'pass',
                    'visa_value': visa_fields.get('travel_date_to', ''),
                    'doc_value': cl.get('travel_to', ''),
                    'doc_source': src,
                    'message': 'Travel end date matches covering letter'
                })
            else:
                results.append({
                    'field': 'Cover Letter: Travel End Date',
                    'status': 'fail',
                    'visa_value': visa_fields.get('travel_date_to', ''),
                    'doc_value': cl.get('travel_to', ''),
                    'doc_source': src,
                    'message': 'Travel end date MISMATCH with covering letter!'
                })

        # Check purpose of travel
        cl_purpose = cl.get('purpose', '')
        if cl_purpose:
            results.append({
                'field': 'Cover Letter: Purpose of Travel',
                'status': 'pass',
                'visa_value': cl_purpose,
                'doc_value': '',
                'doc_source': src,
                'message': f'Purpose of travel stated: {cl_purpose}'
            })
        else:
            results.append({
                'field': 'Cover Letter: Purpose of Travel',
                'status': 'fail',
                'visa_value': 'NOT FOUND',
                'doc_value': '',
                'doc_source': src,
                'message': 'Purpose of travel is MISSING from covering letter!'
            })

        # Check expense bearer
        expense_bearer = cl.get('expense_bearer', '')
        if expense_bearer:
            results.append({
                'field': 'Cover Letter: Expense Bearer',
                'status': 'pass',
                'visa_value': expense_bearer,
                'doc_value': '',
                'doc_source': src,
                'message': f'Expenses borne by: {expense_bearer}'
            })

            # Business visa: expenses should be by company
            if visa_purpose == 'business' and expense_bearer == 'Self':
                results.append({
                    'field': 'Cover Letter: Expense Bearer (Business)',
                    'status': 'warning',
                    'visa_value': 'Business Visa',
                    'doc_value': expense_bearer,
                    'doc_source': src,
                    'message': 'Business visa but expenses are self-funded — typically company bears expenses for business travel'
                })

            # If sponsor, check sponsor details
            if expense_bearer == 'Sponsor/Third Party':
                sponsor_name = cl.get('sponsor_name', '')
                if sponsor_name:
                    results.append({
                        'field': 'Cover Letter: Sponsor Name',
                        'status': 'pass',
                        'visa_value': sponsor_name,
                        'doc_value': '',
                        'doc_source': src,
                        'message': f'Sponsor identified: {sponsor_name}'
                    })
                else:
                    results.append({
                        'field': 'Cover Letter: Sponsor Details',
                        'status': 'fail',
                        'visa_value': 'NOT FOUND',
                        'doc_value': '',
                        'doc_source': src,
                        'message': 'Sponsor is bearing expenses but sponsor details are MISSING!'
                    })
        else:
            results.append({
                'field': 'Cover Letter: Expense Bearer',
                'status': 'fail',
                'visa_value': 'NOT FOUND',
                'doc_value': '',
                'doc_source': src,
                'message': 'Who is bearing expenses is NOT stated in covering letter!'
            })

    return results


# ─── Document Requirement Checks ────────────────────────────────────

def check_required_documents(visa_purpose, supporting_docs):
    """Check that all required documents for the visa type are present."""
    results = []
    doc_types_present = set(d.get('_doc_type') for d in supporting_docs)

    # Common requirements for all visa types
    results.append({
        'field': 'Required Doc: Covering Letter',
        'status': 'pass' if 'covering_letter' in doc_types_present else 'fail',
        'visa_value': 'Required',
        'doc_value': 'Present' if 'covering_letter' in doc_types_present else 'MISSING',
        'doc_source': 'Document Checklist',
        'message': 'Covering letter uploaded' if 'covering_letter' in doc_types_present else 'Covering letter is MISSING!'
    })

    # Business visa requirements
    if visa_purpose == 'business':
        results.append({
            'field': 'Required Doc: Invitation Letter',
            'status': 'pass' if 'invitation_letter' in doc_types_present else 'fail',
            'visa_value': 'Required for Business',
            'doc_value': 'Present' if 'invitation_letter' in doc_types_present else 'MISSING',
            'doc_source': 'Document Checklist',
            'message': 'Invitation letter uploaded' if 'invitation_letter' in doc_types_present else 'Invitation letter is REQUIRED for business visa!'
        })

    return results


# ─── Master QC Runner ───────────────────────────────────────────────

def _make_summary(checks, visa_fields, visa_purpose, label=''):
    """Build a summary dict for a set of checks."""
    total = len(checks)
    passed = sum(1 for r in checks if r['status'] == 'pass')
    failed = sum(1 for r in checks if r['status'] == 'fail')
    warnings = sum(1 for r in checks if r['status'] == 'warning')
    info = sum(1 for r in checks if r['status'] == 'info')

    return {
        'total_checks': total,
        'passed': passed,
        'failed': failed,
        'warnings': warnings,
        'info': info,
        'overall_status': 'FAIL' if failed > 0 else ('WARNING' if warnings > 0 else 'PASS'),
        'applicant_name': visa_fields.get('full_name', visa_fields.get('surname', 'Unknown')),
        'visa_type': visa_fields.get('_doc_type_label', 'Unknown'),
        'visa_purpose': visa_purpose.capitalize(),
        'label': label,
        'timestamp': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
    }


def run_qc(visa_fields, supporting_doc_fields_list, visa_purpose='tourist', check_type='application'):
    """Run QC checks and return a structured report.

    Args:
        visa_fields: Extracted fields from the visa application
        supporting_doc_fields_list: List of extracted fields from supporting documents
        visa_purpose: 'business' or 'tourist' (default: 'tourist')
        check_type: 'application', 'covering', or 'invitation'
    """
    all_results = []

    if check_type == 'application':
        # ─── Visa Application QC ─────────────────────────────
        all_results.extend(check_required_documents(visa_purpose, supporting_doc_fields_list))
        all_results.extend(check_completeness(visa_fields))
        all_results.extend(check_application_date(visa_fields))
        all_results.extend(check_name(visa_fields, supporting_doc_fields_list))
        all_results.extend(check_dob(visa_fields, supporting_doc_fields_list))
        all_results.extend(check_passport_number(visa_fields, supporting_doc_fields_list))
        all_results.extend(check_passport_validity(visa_fields))
        all_results.extend(check_passport_dates_consistency(visa_fields, supporting_doc_fields_list))
        all_results.extend(check_gender_consistency(visa_fields, supporting_doc_fields_list))
        all_results.extend(check_travel_dates(visa_fields, supporting_doc_fields_list))

        return {
            'summary': _make_summary(all_results, visa_fields, visa_purpose, 'Visa Application QC'),
            'checks': all_results,
            'visa_fields': {k: v for k, v in visa_fields.items() if not k.startswith('_') and not k.endswith('_parsed')},
            'supporting_docs_count': len(supporting_doc_fields_list),
        }

    elif check_type == 'covering':
        # ─── Covering Letter QC ──────────────────────────────
        all_results = check_covering_letter(visa_fields, supporting_doc_fields_list, visa_purpose)

        return {
            'summary': _make_summary(all_results, visa_fields, visa_purpose, 'Covering Letter QC'),
            'checks': all_results,
            'supporting_docs_count': len(supporting_doc_fields_list),
        }

    elif check_type == 'invitation':
        # ─── Invitation Letter QC ────────────────────────────
        all_results = check_invitation_letter(visa_fields, supporting_doc_fields_list, visa_purpose)

        return {
            'summary': _make_summary(all_results, visa_fields, visa_purpose, 'Invitation Letter QC'),
            'checks': all_results,
            'supporting_docs_count': len(supporting_doc_fields_list),
        }
